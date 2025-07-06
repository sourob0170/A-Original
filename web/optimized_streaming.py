#!/usr/bin/env python3

"""
Optimized Streaming Module

High-performance streaming implementation with minimal memory usage
and optimized response times for file-to-link functionality.
"""

import asyncio
from collections.abc import AsyncGenerator

from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse
from pyrogram.types import Message

from bot import LOGGER


class OptimizedStreaming:
    """Optimized streaming implementation with reduced memory footprint and efficient caching"""

    # Optimized chunk sizes for different file types (further reduced for memory efficiency)
    CHUNK_SIZES = {
        "video": 1024 * 256,  # 256KB for video (reduced for better memory usage)
        "audio": 1024 * 128,  # 128KB for audio (reduced for better memory usage)
        "image": 1024 * 64,  # 64KB for images (reduced for better memory usage)
        "default": 1024 * 128,  # 128KB default (reduced for better memory usage)
    }

    # Cache for MIME type mappings with size limit
    _mime_cache = {}
    _cache_max_size = 100  # Limit cache size to prevent memory bloat
    _cache_stats = {"hits": 0, "misses": 0}

    @staticmethod
    def get_optimal_chunk_size(mime_type: str, file_size: int) -> int:
        """Get optimal chunk size based on file type and size"""
        # For small files, use smaller chunks
        if file_size < 1024 * 1024:  # < 1MB
            return min(OptimizedStreaming.CHUNK_SIZES["default"], file_size // 10)

        # For large files, use larger chunks but cap at reasonable size
        if file_size > 100 * 1024 * 1024:  # > 100MB
            base_size = OptimizedStreaming.CHUNK_SIZES.get(
                "video", OptimizedStreaming.CHUNK_SIZES["default"]
            )
            return min(base_size * 2, 1024 * 1024)  # Cap at 1MB

        # Determine by MIME type
        if mime_type.startswith("video/"):
            return OptimizedStreaming.CHUNK_SIZES["video"]
        if mime_type.startswith("audio/"):
            return OptimizedStreaming.CHUNK_SIZES["audio"]
        if mime_type.startswith("image/"):
            return OptimizedStreaming.CHUNK_SIZES["image"]
        return OptimizedStreaming.CHUNK_SIZES["default"]

    @staticmethod
    def get_browser_compatible_mime_type(original_mime_type: str) -> str:
        """Cached MIME type conversion for browser compatibility with size-limited cache"""
        if original_mime_type in OptimizedStreaming._mime_cache:
            OptimizedStreaming._cache_stats["hits"] += 1
            return OptimizedStreaming._mime_cache[original_mime_type]

        OptimizedStreaming._cache_stats["misses"] += 1

        # For MKV files, serve as MP4 for better browser compatibility
        if original_mime_type == "video/x-matroska":
            result = "video/mp4"
        else:
            # Optimized mapping with most common types first
            mime_map = {
                "video/x-msvideo": "video/mp4",
                "video/quicktime": "video/mp4",
                "audio/x-flac": "audio/mpeg",
                "audio/x-wav": "audio/wav",
                "audio/x-m4a": "audio/mp4",
            }

            result = mime_map.get(original_mime_type)
            if not result:
                # Fallback logic
                if original_mime_type.startswith(
                    "video/"
                ) and original_mime_type not in [
                    "video/mp4",
                    "video/webm",
                    "video/ogg",
                ]:
                    result = "video/mp4"
                elif original_mime_type.startswith(
                    "audio/"
                ) and original_mime_type not in [
                    "audio/mpeg",
                    "audio/wav",
                    "audio/ogg",
                    "audio/mp4",
                ]:
                    result = "audio/mpeg"
                else:
                    result = original_mime_type

        # Manage cache size to prevent memory bloat
        if len(OptimizedStreaming._mime_cache) >= OptimizedStreaming._cache_max_size:
            # Remove oldest entries (simple FIFO)
            keys_to_remove = list(OptimizedStreaming._mime_cache.keys())[:20]
            for key in keys_to_remove:
                del OptimizedStreaming._mime_cache[key]

        # Cache result
        OptimizedStreaming._mime_cache[original_mime_type] = result
        return result

    @staticmethod
    def parse_range_header(range_header: str, file_size: int) -> tuple[int, int]:
        """Optimized range header parsing"""
        try:
            # Extract range values efficiently
            range_match = range_header.replace("bytes=", "").split("-")
            start = int(range_match[0]) if range_match[0] else 0
            end = (
                int(range_match[1])
                if len(range_match) > 1 and range_match[1]
                else file_size - 1
            )

            # Validate and clamp values
            start = max(0, min(start, file_size - 1))
            end = max(start, min(end, file_size - 1))

            return start, end
        except (ValueError, IndexError):
            return 0, file_size - 1

    @staticmethod
    async def stream_file_optimized(
        message: Message, file_info: dict, request: Request, client, client_id: int
    ) -> StreamingResponse:
        """Optimized file streaming with minimal memory usage"""
        try:
            file_info["file_name"]
            file_size = file_info["file_size"]
            mime_type = file_info["mime_type"]

            # Get optimal chunk size
            chunk_size = OptimizedStreaming.get_optimal_chunk_size(
                mime_type, file_size
            )

            # Handle range requests efficiently
            range_header = request.headers.get("range")
            if range_header:
                start, end = OptimizedStreaming.parse_range_header(
                    range_header, file_size
                )
                content_length = end - start + 1

                async def generate_range() -> AsyncGenerator[bytes]:
                    """Optimized range streaming generator"""
                    try:
                        bytes_yielded = 0
                        current_offset = start

                        # Use chunk-based streaming to avoid OFFSET_INVALID errors
                        chunk_size = 1024 * 1024  # 1MB chunks
                        start_chunk = start // chunk_size
                        end_chunk = (end + chunk_size - 1) // chunk_size
                        chunks_needed = end_chunk - start_chunk

                        try:
                            async for chunk in client.stream_media(
                                message, offset=start_chunk, limit=chunks_needed
                            ):
                                if not chunk:
                                    break

                                # Calculate which part of this chunk we need
                                chunk_start_byte = (
                                    start_chunk * chunk_size + bytes_yielded
                                )

                                # Trim chunk to requested range
                                if chunk_start_byte < start:
                                    skip_bytes = start - chunk_start_byte
                                    chunk = chunk[skip_bytes:]

                                if chunk_start_byte + len(chunk) > end + 1:
                                    trim_bytes = (chunk_start_byte + len(chunk)) - (
                                        end + 1
                                    )
                                    chunk = chunk[:-trim_bytes]

                                if chunk:
                                    bytes_yielded += len(chunk)
                                    current_offset += len(chunk)
                                    yield chunk

                                    if bytes_yielded >= content_length:
                                        break
                        except Exception as e:
                            if "OFFSET_INVALID" in str(e) or "OffsetInvalid" in str(
                                e
                            ):
                                LOGGER.warning(
                                    "OFFSET_INVALID in range streaming, falling back to full stream"
                                )
                                # Fallback to full stream and skip to range
                                bytes_skipped = 0
                                async for chunk in client.stream_media(message):
                                    if bytes_skipped < start:
                                        skip_amount = min(
                                            len(chunk), start - bytes_skipped
                                        )
                                        chunk = chunk[skip_amount:]
                                        bytes_skipped += skip_amount

                                    if chunk and bytes_yielded < content_length:
                                        remaining = content_length - bytes_yielded
                                        if len(chunk) > remaining:
                                            chunk = chunk[:remaining]

                                        bytes_yielded += len(chunk)
                                        yield chunk

                                        if bytes_yielded >= content_length:
                                            break
                            elif "FILE_REFERENCE_EXPIRED" in str(
                                e
                            ) or "FILE_REFERENCE_X_EXPIRED" in str(e):
                                LOGGER.warning(
                                    "FILE_REFERENCE_EXPIRED in range streaming, attempting to refresh message"
                                )
                                try:
                                    # Refresh file reference by getting fresh message
                                    fresh_message = await client.get_messages(
                                        message.chat.id, message.id
                                    )
                                    if fresh_message and fresh_message.media:
                                        LOGGER.info(
                                            f"Got fresh message for {message.id}, retrying range stream"
                                        )
                                        # Retry streaming with fresh message
                                        async for chunk in client.stream_media(
                                            fresh_message,
                                            offset=start_chunk,
                                            limit=chunks_needed,
                                        ):
                                            if not chunk:
                                                break

                                            # Calculate which part of this chunk we need
                                            chunk_start_byte = (
                                                start_chunk * chunk_size
                                                + bytes_yielded
                                            )

                                            # Trim chunk to requested range
                                            if chunk_start_byte < start:
                                                skip_bytes = start - chunk_start_byte
                                                chunk = chunk[skip_bytes:]

                                            if (
                                                chunk_start_byte + len(chunk)
                                                > end + 1
                                            ):
                                                trim_bytes = (
                                                    chunk_start_byte + len(chunk)
                                                ) - (end + 1)
                                                chunk = chunk[:-trim_bytes]

                                            if chunk:
                                                bytes_yielded += len(chunk)
                                                current_offset += len(chunk)
                                                yield chunk

                                                if bytes_yielded >= content_length:
                                                    break
                                        return
                                except Exception as refresh_error:
                                    LOGGER.error(
                                        f"Failed to refresh file reference for range streaming: {refresh_error}"
                                    )
                                    raise
                            else:
                                raise

                    except Exception as e:
                        LOGGER.error(f"Error in range streaming: {e}")
                        raise

                # Use optimized headers that properly handle force_download
                headers = OptimizedStreaming.generate_optimized_headers(
                    file_info, is_range=True
                )
                # Add range-specific headers
                headers.update(
                    {
                        "Content-Range": f"bytes {start}-{end}/{file_size}",
                        "Content-Length": str(content_length),
                    }
                )

                return StreamingResponse(
                    generate_range(), status_code=206, headers=headers
                )

            # Full file streaming with memory optimization
            async def generate_full() -> AsyncGenerator[bytes]:
                """Optimized full file streaming generator with memory management"""
                try:
                    bytes_yielded = 0
                    chunk_count = 0

                    async for chunk in client.stream_media(message):
                        if chunk:
                            bytes_yielded += len(chunk)
                            chunk_count += 1
                            yield chunk

                            # Memory management: periodic cleanup and throttling
                            if chunk_count % 100 == 0:  # Every 100 chunks
                                # Small delay to prevent memory pressure
                                await asyncio.sleep(0.001)

                                # Force garbage collection for large files
                                if bytes_yielded > 100 * 1024 * 1024:  # > 100MB
                                    import gc

                                    gc.collect()

                except Exception as e:
                    # Handle FILE_REFERENCE_EXPIRED for full streaming
                    if "FILE_REFERENCE_EXPIRED" in str(
                        e
                    ) or "FILE_REFERENCE_X_EXPIRED" in str(e):
                        LOGGER.warning(
                            "FILE_REFERENCE_EXPIRED in full streaming, attempting to refresh message"
                        )
                        try:
                            # Refresh file reference by getting fresh message
                            fresh_message = await client.get_messages(
                                message.chat.id, message.id
                            )
                            if fresh_message and fresh_message.media:
                                LOGGER.info(
                                    f"Got fresh message for {message.id}, retrying full stream"
                                )
                                # Retry streaming with fresh message
                                bytes_yielded = 0
                                async for chunk in client.stream_media(
                                    fresh_message
                                ):
                                    if chunk:
                                        bytes_yielded += len(chunk)
                                        yield chunk

                                        # Optional: Add small delay for very large files to prevent overwhelming
                                        if (
                                            bytes_yielded % (chunk_size * 50) == 0
                                        ):  # Every ~25MB
                                            await asyncio.sleep(0.001)  # 1ms delay
                                return
                        except Exception as refresh_error:
                            LOGGER.error(
                                f"Failed to refresh file reference for full streaming: {refresh_error}"
                            )
                            raise
                    else:
                        LOGGER.error(f"Error in full file streaming: {e}")
                        raise

            # Use optimized headers that properly handle force_download
            headers = OptimizedStreaming.generate_optimized_headers(
                file_info, is_range=False
            )

            # Don't set Content-Length for streaming to allow chunked encoding
            return StreamingResponse(generate_full(), headers=headers)

        except Exception as e:
            LOGGER.error(f"Error in optimized streaming: {e}")
            raise HTTPException(status_code=500, detail="Streaming error") from e

    @staticmethod
    def generate_optimized_headers(file_info: dict, is_range: bool = False) -> dict:
        """Generate optimized HTTP headers for streaming"""
        mime_type = file_info["mime_type"]
        file_name = file_info["file_name"]
        is_streamable = mime_type.startswith(("video/", "audio/", "image/"))
        force_download = file_info.get("force_download", False)

        # Force attachment disposition for direct downloads
        disposition = (
            "attachment"
            if force_download
            else ("inline" if is_streamable else "attachment")
        )

        headers = {
            "Content-Type": OptimizedStreaming.get_browser_compatible_mime_type(
                mime_type
            ),
            "Content-Disposition": f'{disposition}; filename="{file_name}"',
            "Accept-Ranges": "bytes",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Access-Control-Allow-Headers": "Range, Content-Type",
            "Cache-Control": "public, max-age=3600"
            if is_streamable and not force_download
            else "no-cache",
        }

        # Add security headers for streamable content
        if is_streamable:
            headers.update(
                {
                    "X-Content-Type-Options": "nosniff",
                    "X-Frame-Options": "SAMEORIGIN",
                }
            )

        return headers

    @staticmethod
    def clear_cache():
        """Clear MIME type cache to free memory"""
        OptimizedStreaming._mime_cache.clear()
        LOGGER.info("Optimized streaming cache cleared")
