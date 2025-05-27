from asyncio import (
    CancelledError,
    Event,
    TimeoutError,
    create_task,
    gather,
    sleep,
    wait_for,
)
from datetime import datetime
from math import ceil, floor
from mimetypes import guess_extension
from os import path as ospath
from pathlib import Path
from re import sub
from sys import argv
from time import time

from aiofiles import open as aiopen
from aioshutil import move

from bot.helper.ext_utils.aiofiles_compat import makedirs, remove

# Import from pyrogram/electrogram (they are compatible)
try:
    # Try electrogram first
    from electrogram import raw, utils
    from electrogram.errors import AuthBytesInvalid, FloodWait
    from electrogram.errors import StopTransmissionError as StopTransmission
    from electrogram.file_id import PHOTO_TYPES, FileId, FileType, ThumbnailSource
    from electrogram.session import Auth, Session
    from electrogram.session.internals import MsgId
except ImportError:
    try:
        # Fall back to pyrogram
        from pyrogram import raw, utils

        try:
            # Try to import from pyrogram directly (older versions)
            from pyrogram import StopTransmission
        except ImportError:
            try:
                # In newer versions, it's called StopTransmissionError
                from pyrogram.errors import StopTransmissionError as StopTransmission
            except ImportError:
                # If neither is available, define a custom exception
                class StopTransmission(Exception):
                    """Custom exception to handle stop transmission"""

        from pyrogram.errors import AuthBytesInvalid, FloodWait
        from pyrogram.file_id import PHOTO_TYPES, FileId, FileType, ThumbnailSource
        from pyrogram.session import Auth, Session
        from pyrogram.session.internals import MsgId
    except ImportError:
        # If all imports fail, raise a clear error
        raise ImportError(
            "Failed to import required modules from either electrogram or pyrogram. Please check your installation."
        )

from bot import LOGGER
from bot.core.aeon_client import TgClient
from bot.core.config_manager import Config


class HyperTGDownload:
    def __init__(self):
        self.clients = TgClient.helper_bots
        if not self.clients:
            raise ValueError("No helper bots available for hyper download")

        self.work_loads = TgClient.helper_loads
        self.message = None
        self.dump_chat = None
        self.download_dir = "downloads/"
        self.directory = None
        self.num_parts = Config.HYPER_THREADS or max(8, len(self.clients))
        self.cache_file_ref = {}
        self.cache_last_access = {}
        self.cache_max_size = 100
        self._processed_bytes = 0
        self.file_size = 0
        self.chunk_size = 1024 * 1024
        self.file_name = ""
        self._cancel_event = Event()
        self.session_pool = {}
        self._clean_task = create_task(self._clean_cache())

    def __del__(self):
        if hasattr(self, "_clean_task") and not self._clean_task.done():
            self._clean_task.cancel()

    @staticmethod
    async def get_media_type(message):
        if not message:
            raise ValueError("Message is None")

        # Check if message is a media message
        media_types = (
            "audio",
            "document",
            "photo",
            "sticker",
            "animation",
            "video",
            "voice",
            "video_note",
            "new_chat_photo",
        )

        # First try direct attribute access
        for attr in media_types:
            if media := getattr(message, attr, None):
                return media

        # If that fails, try to check if message has a 'media' attribute (for forwarded messages)
        if hasattr(message, "media") and message.media:
            # Try to extract media from message.media
            for attr in media_types:
                if hasattr(message.media, attr) and getattr(message.media, attr):
                    return getattr(message.media, attr)

        # If we get here, no media was found
        LOGGER.error(
            f"No downloadable media found in message ID: {getattr(message, 'id', 'unknown')}"
        )
        raise ValueError("This message doesn't contain any downloadable media")

    def _update_cache(self, index, file_ref):
        self.cache_file_ref[index] = file_ref
        self.cache_last_access[index] = time()

        if len(self.cache_file_ref) > self.cache_max_size:
            oldest = sorted(self.cache_last_access.items(), key=lambda x: x[1])[0][0]
            del self.cache_file_ref[oldest]
            del self.cache_last_access[oldest]

    async def get_specific_file_ref(self, mid, client, max_retries=3):
        retries = 0
        last_error = None

        # Handle case where dump_chat is a list - use the first item
        chat_id = (
            self.dump_chat[0] if isinstance(self.dump_chat, list) else self.dump_chat
        )

        while retries < max_retries:
            try:
                # Adapt for electrogram API
                try:
                    media = await client.get_messages(
                        chat_id=chat_id,
                        message_ids=mid,
                    )
                except TypeError as e:
                    # Handle case where get_messages has different parameters in Electrogram
                    if "unexpected keyword argument" in str(e):
                        # Try alternative approach for Electrogram
                        media = await client.get_messages(
                            chat_id,  # chat_id as positional argument
                            mid,  # message_ids as positional argument
                        )
                    else:
                        raise

                return FileId.decode(
                    getattr(await self.get_media_type(media), "file_id", "")
                )
            except Exception as e:
                last_error = e
                retries += 1
                await sleep(1 * retries)

        LOGGER.error(
            f"Failed to get message {mid} from {chat_id} with Client {client.me.username}"
        )
        raise ValueError(
            f"Bot needs Admin access in Chat or message may be deleted. Error: {last_error}"
        )

    async def get_file_id(self, client, index) -> FileId:
        if index not in self.cache_file_ref:
            file_ref = await self.get_specific_file_ref(self.message.id, client)
            self._update_cache(index, file_ref)
        else:
            self.cache_last_access[index] = time()
        return self.cache_file_ref[index]

    async def _clean_cache(self):
        while True:
            await sleep(15 * 60)
            current_time = time()
            expired_keys = [
                k
                for k, v in self.cache_last_access.items()
                if current_time - v > 45 * 60
            ]

            for key in expired_keys:
                if key in self.cache_file_ref:
                    del self.cache_file_ref[key]
                if key in self.cache_last_access:
                    del self.cache_last_access[key]

    async def generate_media_session(self, client, file_id, index, max_retries=3):
        session_key = (index, file_id.dc_id)

        if session_key in self.session_pool:
            return self.session_pool[session_key]

        retries = 0
        while retries < max_retries:
            try:
                if file_id.dc_id != await client.storage.dc_id():
                    media_session = Session(
                        client,
                        file_id.dc_id,
                        await Auth(
                            client, file_id.dc_id, await client.storage.test_mode()
                        ).create(),
                        await client.storage.test_mode(),
                        is_media=True,
                    )
                    await media_session.start()

                    for _ in range(6):
                        exported_auth = await client.invoke(
                            raw.functions.auth.ExportAuthorization(
                                dc_id=file_id.dc_id
                            )
                        )

                        try:
                            await media_session.invoke(
                                raw.functions.auth.ImportAuthorization(
                                    id=exported_auth.id, bytes=exported_auth.bytes
                                )
                            )
                            break
                        except AuthBytesInvalid:
                            await sleep(1)
                    else:
                        await media_session.stop()
                        raise AuthBytesInvalid
                else:
                    media_session = Session(
                        client,
                        file_id.dc_id,
                        await client.storage.auth_key(),
                        await client.storage.test_mode(),
                        is_media=True,
                    )
                    await media_session.start()

                self.session_pool[session_key] = media_session
                return media_session

            except Exception:
                retries += 1
                await sleep(1)

        raise ValueError(
            f"Failed to create media session after {max_retries} attempts"
        )

    @staticmethod
    async def get_location(file_id: FileId):
        file_type = file_id.file_type

        if file_type == FileType.CHAT_PHOTO:
            if file_id.chat_id > 0:
                peer = raw.types.InputPeerUser(
                    user_id=file_id.chat_id, access_hash=file_id.chat_access_hash
                )
            else:
                peer = (
                    raw.types.InputPeerChat(chat_id=-file_id.chat_id)
                    if file_id.chat_access_hash == 0
                    else raw.types.InputPeerChannel(
                        channel_id=utils.get_channel_id(file_id.chat_id),
                        access_hash=file_id.chat_access_hash,
                    )
                )
            return raw.types.InputPeerPhotoFileLocation(
                peer=peer,
                volume_id=file_id.volume_id,
                local_id=file_id.local_id,
                big=file_id.thumbnail_source == ThumbnailSource.CHAT_PHOTO_BIG,
            )
        if file_type == FileType.PHOTO:
            return raw.types.InputPhotoFileLocation(
                id=file_id.media_id,
                access_hash=file_id.access_hash,
                file_reference=file_id.file_reference,
                thumb_size=file_id.thumbnail_size,
            )
        return raw.types.InputDocumentFileLocation(
            id=file_id.media_id,
            access_hash=file_id.access_hash,
            file_reference=file_id.file_reference,
            thumb_size=file_id.thumbnail_size,
        )

    async def get_file(
        self,
        offset_bytes: int,
        first_part_cut: int,
        last_part_cut: int,
        part_count: int,
        max_retries=5,
    ):
        index = min(self.work_loads, key=self.work_loads.get)
        client = self.clients[index]

        self.work_loads[index] += 1
        current_retry = 0

        try:
            while current_retry < max_retries:
                try:
                    if self._cancel_event.is_set():
                        raise CancelledError("Download cancelled")

                    file_id = await self.get_file_id(client, index)
                    media_session, location = await gather(
                        self.generate_media_session(client, file_id, index),
                        self.get_location(file_id),
                    )

                    current_part = 1
                    current_offset = offset_bytes

                    while current_part <= part_count:
                        if self._cancel_event.is_set():
                            raise CancelledError("Download cancelled")

                        try:
                            r = await wait_for(
                                media_session.invoke(
                                    raw.functions.upload.GetFile(
                                        location=location,
                                        offset=current_offset,
                                        limit=self.chunk_size,
                                    ),
                                ),
                                timeout=30,
                            )

                            if isinstance(r, raw.types.upload.File):
                                chunk = r.bytes

                                if not chunk:
                                    break

                                if part_count == 1:
                                    yield chunk[first_part_cut:last_part_cut]
                                elif current_part == 1:
                                    yield chunk[first_part_cut:]
                                elif current_part == part_count:
                                    yield chunk[:last_part_cut]
                                else:
                                    yield chunk

                                current_part += 1
                                current_offset += self.chunk_size
                                self._processed_bytes += len(chunk)
                            else:
                                raise ValueError(f"Unexpected response: {r}")

                        except FloodWait as e:
                            await sleep(e.value + 1)
                            continue
                        except (TimeoutError, ConnectionError):
                            await sleep(1)
                            continue

                    if current_part <= part_count:
                        raise ValueError(
                            f"Incomplete download: got {current_part - 1} of {part_count} parts"
                        )
                    break

                except (TimeoutError, ConnectionError, AttributeError):
                    current_retry += 1
                    if current_retry >= max_retries:
                        raise
                    await sleep(current_retry * 2)

        finally:
            self.work_loads[index] -= 1

    async def progress_callback(self, progress, progress_args):
        if not progress:
            return

        while not self._cancel_event.is_set():
            try:
                if callable(progress):
                    await progress(
                        self._processed_bytes, self.file_size, *progress_args
                    )
                await sleep(1)
            except (CancelledError, StopTransmission):
                # Handle cancellation
                break
            except Exception:
                await sleep(1)

    async def single_part(self, start, end, part_index, max_retries=3):
        until_bytes, from_bytes = min(end, self.file_size - 1), start

        offset = from_bytes - (from_bytes % self.chunk_size)
        first_part_cut = from_bytes - offset
        last_part_cut = until_bytes % self.chunk_size + 1

        part_count = ceil(until_bytes / self.chunk_size) - floor(
            offset / self.chunk_size
        )
        part_file_path = ospath.join(
            self.directory, f"{self.file_name}.temp.{part_index:02d}"
        )

        for attempt in range(max_retries):
            try:
                async with aiopen(part_file_path, "wb") as f:
                    async for chunk in self.get_file(
                        offset, first_part_cut, last_part_cut, part_count
                    ):
                        if self._cancel_event.is_set():
                            raise CancelledError("Download cancelled")
                        await f.write(chunk)
                return part_index, part_file_path
            except (TimeoutError, ConnectionError):
                if attempt == max_retries - 1:
                    raise
                await sleep((attempt + 1) * 2)
                self._processed_bytes = 0

        # If we reach here, all attempts failed
        raise ValueError(
            f"Failed to download part {part_index} after {max_retries} attempts"
        )

    async def handle_download(self, progress, progress_args):
        self._cancel_event.clear()

        await makedirs(self.directory, exist_ok=True)
        temp_file_path = (
            ospath.abspath(
                sub("\\\\", "/", ospath.join(self.directory, self.file_name))
            )
            + ".temp"
        )

        num_parts = min(self.num_parts, max(1, self.file_size // (10 * 1024 * 1024)))

        if self.file_size < 10 * 1024 * 1024:
            num_parts = 1

        part_size = self.file_size // num_parts if num_parts > 0 else self.file_size
        ranges = [
            (i * part_size, min((i + 1) * part_size - 1, self.file_size - 1))
            for i in range(num_parts)
        ]

        tasks = []
        prog_task = None

        try:
            for i, (start, end) in enumerate(ranges):
                tasks.append(create_task(self.single_part(start, end, i)))

            if progress:
                prog_task = create_task(
                    self.progress_callback(progress, progress_args)
                )

            results = await gather(*tasks)

            async with aiopen(temp_file_path, "wb") as temp_file:
                for _, part_file_path in sorted(results, key=lambda x: x[0]):
                    try:
                        async with aiopen(part_file_path, "rb") as part_file:
                            while True:
                                chunk = await part_file.read(8 * 1024 * 1024)
                                if not chunk:
                                    break
                                await temp_file.write(chunk)
                        await remove(part_file_path)
                    except Exception as e:
                        LOGGER.error(
                            f"Error processing part file {part_file_path}: {e}"
                        )
                        raise

            if prog_task and not prog_task.done():
                prog_task.cancel()

            file_path = ospath.splitext(temp_file_path)[0]
            await move(temp_file_path, file_path)

            return file_path

        except FloodWait as fw:
            raise fw
        except (CancelledError, StopTransmission):
            # Download was cancelled
            return None
        except Exception as e:
            LOGGER.error(f"HyperDL Error: {e}")
            return None
        finally:
            self._cancel_event.set()
            if prog_task and not prog_task.done():
                prog_task.cancel()

            for task in tasks:
                if not task.done():
                    task.cancel()

            for i in range(len(ranges)):
                part_path = ospath.join(
                    self.directory, f"{self.file_name}.temp.{i:02d}"
                )
                try:
                    if ospath.exists(part_path):
                        await remove(part_path)
                except Exception:
                    pass

    @staticmethod
    async def get_extension(file_type, mime_type):
        if file_type in PHOTO_TYPES:
            return ".jpg"

        if mime_type:
            extension = guess_extension(mime_type)
            if extension:
                return extension

        if file_type == FileType.VOICE:
            return ".ogg"
        if file_type in (FileType.VIDEO, FileType.ANIMATION, FileType.VIDEO_NOTE):
            return ".mp4"
        if file_type == FileType.DOCUMENT:
            return ".bin"
        if file_type == FileType.STICKER:
            return ".webp"
        if file_type == FileType.AUDIO:
            return ".mp3"
        return ".bin"

    async def download_media(
        self,
        message,
        file_name="downloads/",
        progress=None,
        progress_args=(),
        dump_chat=None,
    ):
        try:
            # First, verify that the original message has downloadable media
            try:
                # Check if message is a valid message object
                if not message:
                    raise ValueError("Message is None")

                # Check if message has basic attributes we expect
                if not hasattr(message, "chat") or not hasattr(message, "id"):
                    raise ValueError("Message object is missing required attributes")

                # Try to get media from the message
                original_media = await self.get_media_type(message)
                if not original_media:
                    # This should never happen as get_media_type should raise an exception if no media is found
                    raise ValueError(
                        "Original message doesn't contain any downloadable media"
                    )

                # Media found, no need to log it now that the feature is working

            except ValueError as e:
                # This is a specific error we're expecting
                LOGGER.error(f"Media verification error: {e}")
                raise
            except Exception as e:
                # This is an unexpected error
                LOGGER.error(
                    f"Unexpected error checking original message media: {e}"
                )
                raise ValueError("Failed to verify original message media") from e

            if dump_chat:
                try:
                    # For media messages, we need to forward them instead of copying
                    # as copy_message might not preserve all media attributes
                    try:
                        # Handle case where dump_chat is a list - use the first item
                        chat_id = (
                            dump_chat[0]
                            if isinstance(dump_chat, list)
                            else dump_chat
                        )

                        forwarded_msg = await TgClient.bot.forward_messages(
                            chat_id=chat_id,
                            from_chat_id=message.chat.id,
                            message_ids=message.id,
                            disable_notification=True,
                        )

                        # Handle case where forward_messages returns a list
                        if isinstance(forwarded_msg, list) and forwarded_msg:
                            self.message = forwarded_msg[0]
                        elif forwarded_msg:
                            self.message = forwarded_msg
                        else:
                            # If forwarding returns empty result, try copying
                            raise ValueError("Forward returned empty result")
                    except Exception as e:
                        LOGGER.warning(
                            f"Forwarding failed: {e}, trying copy_message instead"
                        )
                        # If forwarding fails, try copying
                        # Handle case where dump_chat is a list - use the first item
                        chat_id = (
                            dump_chat[0]
                            if isinstance(dump_chat, list)
                            else dump_chat
                        )

                        self.message = await TgClient.bot.copy_message(
                            chat_id=chat_id,
                            from_chat_id=message.chat.id,
                            message_id=message.id,
                            disable_notification=True,
                        )

                    # Verify that the forwarded/copied message has downloadable media
                    try:
                        await self.get_media_type(self.message)
                    except Exception:
                        # Fall back to using the original message
                        LOGGER.warning(
                            "Using original message as forwarded message has no media"
                        )
                        self.message = message

                except Exception as e:
                    LOGGER.warning(
                        f"Error forwarding/copying message to dump chat: {e}"
                    )
                    # Fall back to using the original message
                    self.message = message
                    # If we can't copy the message to the dump chat, we can't use hyper download
                    if not self.clients:
                        raise ValueError(
                            "No helper bots available for hyper download"
                        ) from e
            else:
                self.message = message

            # Handle case where dump_chat is a list
            if dump_chat:
                self.dump_chat = dump_chat
            else:
                self.dump_chat = message.chat.id
            media = await self.get_media_type(self.message)

            file_id_str = media if isinstance(media, str) else media.file_id
            file_id_obj = FileId.decode(file_id_str)

            file_type = file_id_obj.file_type
            media_file_name = getattr(media, "file_name", "")
            self.file_size = getattr(media, "file_size", 0)
            mime_type = getattr(media, "mime_type", "image/jpeg")
            date = getattr(media, "date", None)

            self.directory, self.file_name = ospath.split(file_name)
            self.file_name = self.file_name or media_file_name or ""

            if not ospath.isabs(self.file_name):
                self.directory = Path(argv[0]).parent / (
                    self.directory or self.download_dir
                )

            if not self.file_name:
                extension = await self.get_extension(file_type, mime_type)
                self.file_name = f"{FileType(file_id_obj.file_type).name.lower()}_{(date or datetime.now()).strftime('%Y-%m-%d_%H-%M-%S')}_{MsgId()}{extension}"

            return await self.handle_download(progress, progress_args)

        except Exception as e:
            LOGGER.error(f"Download media error: {e}")
            raise
