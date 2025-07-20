"""
Parallel streaming handler for File2Link functionality
Uses multiple helper bots for faster streaming like HyperDL
"""

import asyncio
import contextlib
from collections.abc import AsyncGenerator
from dataclasses import dataclass

from pyrogram import Client
from pyrogram.errors import FloodWait
from pyrogram.types import Message

from bot import LOGGER

from .client_manager import StreamClientManager
from .file_processor import get_fsize, get_media


@dataclass
class ChunkInfo:
    """Information about a chunk to be downloaded"""

    index: int
    start: int
    end: int
    size: int
    client_id: int
    client: Client


class ParallelByteStreamer:
    """
    Parallel streaming using multiple helper bots
    Based on HyperDL architecture but for streaming instead of downloading
    """

    def __init__(self, chat_id: int, max_workers: int | None = None):
        self.chat_id = chat_id
        self.max_workers = max_workers or min(8, len(self._get_available_clients()))
        self.chunk_size = 1024 * 1024  # 1MB chunks
        self.buffer_size = 5  # Number of chunks to buffer ahead

        # Validate channel configuration
        if not self.chat_id:
            raise ValueError("FILE2LINK_BIN_CHANNEL not configured")

    def is_parallel(self) -> bool:
        """Return True to identify this as a parallel streamer"""
        return True

    def _get_available_clients(self) -> list[tuple[Client, int]]:
        """Get all available clients for parallel streaming"""
        from bot.core.aeon_client import TgClient

        clients = []

        # Add main bot
        if hasattr(TgClient, "bot") and TgClient.bot:
            clients.append((TgClient.bot, 0))

        # Add helper bots
        if hasattr(TgClient, "helper_bots") and TgClient.helper_bots:
            for bot_id, bot in TgClient.helper_bots.items():
                clients.append((bot, bot_id))

        return clients

    async def get_message(self, message_id: int) -> Message:
        """Get message from storage channel"""
        try:
            # Use any available client to get the message
            clients = self._get_available_clients()
            if not clients:
                raise ValueError("No clients available for streaming")

            client, _ = clients[0]  # Use first available client
            message = await client.get_messages(self.chat_id, message_id)

            if not message or not get_media(message):
                raise FileNotFoundError(
                    f"Message {message_id} not found or has no media"
                )

            return message
        except Exception as e:
            LOGGER.error(f"Error getting message {message_id}: {e}")
            raise

    def _calculate_chunks(
        self, file_size: int, offset: int = 0, limit: int = 0
    ) -> list[ChunkInfo]:
        """Calculate optimal chunk distribution across available clients"""
        clients = self._get_available_clients()
        if not clients:
            raise ValueError("No clients available for parallel streaming")

        # Determine the range to stream
        start_byte = offset
        if limit > 0:
            end_byte = min(offset + limit - 1, file_size - 1)
        else:
            end_byte = file_size - 1

        total_bytes = end_byte - start_byte + 1

        # Calculate optimal number of chunks
        num_chunks = min(
            self.max_workers, len(clients), max(1, total_bytes // self.chunk_size)
        )

        if total_bytes < self.chunk_size:
            num_chunks = 1

        chunk_size = total_bytes // num_chunks
        chunks = []

        for i in range(num_chunks):
            chunk_start = start_byte + (i * chunk_size)
            if i == num_chunks - 1:
                # Last chunk gets any remaining bytes
                chunk_end = end_byte
            else:
                chunk_end = chunk_start + chunk_size - 1

            # Assign client using round-robin
            client, client_id = clients[i % len(clients)]

            chunks.append(
                ChunkInfo(
                    index=i,
                    start=chunk_start,
                    end=chunk_end,
                    size=chunk_end - chunk_start + 1,
                    client_id=client_id,
                    client=client,
                )
            )

        return chunks

    async def _download_chunk(
        self, message: Message, chunk: ChunkInfo
    ) -> tuple[int, bytes]:
        """Download a single chunk using assigned client"""
        try:
            # Increment load for this client
            StreamClientManager.increment_load(chunk.client_id)

            chunk_data = b""
            current_offset = chunk.start

            while current_offset <= chunk.end:
                try:
                    remaining = chunk.end - current_offset + 1
                    limit = min(self.chunk_size, remaining)

                    async for data in chunk.client.stream_media(
                        message, offset=current_offset, limit=limit
                    ):
                        chunk_data += data
                        current_offset += len(data)

                        if current_offset > chunk.end:
                            # Trim excess data
                            excess = current_offset - chunk.end - 1
                            if excess > 0:
                                chunk_data = chunk_data[:-excess]
                            break

                    break  # Success

                except FloodWait as e:
                    await asyncio.sleep(e.value)
                except Exception as e:
                    error_msg = str(e).lower()
                    if "unauthorized" in error_msg or "auth" in error_msg:
                        LOGGER.error(
                            f"Authentication error in chunk {chunk.index}: {e}"
                        )
                        raise ConnectionError(f"Telegram authentication failed: {e}")
                    LOGGER.error(f"Error downloading chunk {chunk.index}: {e}")
                    raise

            return chunk.index, chunk_data

        finally:
            # Decrement load for this client
            StreamClientManager.decrement_load(chunk.client_id)

    async def stream_file_parallel(
        self, message_id: int, offset: int = 0, limit: int = 0
    ) -> AsyncGenerator[bytes]:
        """Stream file content using parallel chunk downloading"""
        try:
            message = await self.get_message(message_id)
            file_size = get_fsize(message)

            if file_size == 0:
                LOGGER.error("File size is 0, cannot stream")
                return

            # Calculate chunks for parallel download
            chunks = self._calculate_chunks(file_size, offset, limit)

            if len(chunks) == 1:
                # Single chunk, use regular streaming
                chunk = chunks[0]
                async for data in chunk.client.stream_media(
                    message, offset=chunk.start, limit=chunk.size
                ):
                    yield data
                return

            # Parallel streaming with multiple chunks
            chunk_queue = asyncio.Queue(maxsize=self.buffer_size)
            completed_chunks = {}
            next_chunk_index = 0

            async def chunk_downloader():
                """Download chunks in parallel"""
                tasks = []
                for chunk in chunks:
                    task = asyncio.create_task(self._download_chunk(message, chunk))
                    tasks.append(task)

                # Process completed chunks
                for coro in asyncio.as_completed(tasks):
                    try:
                        chunk_index, chunk_data = await coro
                        await chunk_queue.put((chunk_index, chunk_data))
                    except Exception as e:
                        LOGGER.error(f"Chunk download failed: {e}")
                        await chunk_queue.put((None, None))  # Signal error

                # Signal completion
                await chunk_queue.put((None, None))

            # Start chunk downloader
            downloader_task = asyncio.create_task(chunk_downloader())

            try:
                # Yield chunks in order
                while next_chunk_index < len(chunks):
                    chunk_index, chunk_data = await chunk_queue.get()

                    if chunk_index is None:
                        # Error or completion signal
                        if chunk_data is None and next_chunk_index < len(chunks):
                            # This was an error signal
                            break
                        continue

                    # Store chunk if it's not the next one we need
                    if chunk_index != next_chunk_index:
                        completed_chunks[chunk_index] = chunk_data
                        continue

                    # Yield the next chunk
                    yield chunk_data
                    next_chunk_index += 1

                    # Check if we have subsequent chunks ready
                    while next_chunk_index in completed_chunks:
                        yield completed_chunks.pop(next_chunk_index)
                        next_chunk_index += 1

            finally:
                # Clean up
                if not downloader_task.done():
                    downloader_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await downloader_task

        except Exception as e:
            LOGGER.error(f"Error in parallel streaming: {e}")
            raise
