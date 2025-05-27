import asyncio
import time
from pathlib import Path

from bot import DOWNLOAD_DIR, LOGGER, task_dict, task_dict_lock
from bot.core.config_manager import Config
from bot.helper.ext_utils.status_utils import get_readable_file_size
from bot.helper.listeners.task_listener import TaskListener
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    send_message,
)


class StreamripListener(TaskListener):
    """Listener for streamrip downloads"""

    def __init__(self, message, isLeech=False, tag=None, user_id=None):
        # Set required attributes BEFORE calling super().__init__()
        # because TaskConfig.__init__ expects self.message to be available
        self.message = message
        self.isLeech = isLeech

        # Now initialize TaskListener which calls TaskConfig.__init__()
        super().__init__()

        # Streamrip-specific attributes
        self.download_helper = None
        self.url = ""
        self.quality = None
        self.codec = None
        self._start_time = time.time()
        self._last_update = 0
        self._update_interval = 5  # Update every 5 seconds

        # Set custom tag if provided, otherwise create user tag like TaskListener does
        if tag:
            self.tag = tag
        else:
            # Create user tag with proper mention formatting (same as TaskListener)
            self.tag = (
                f"@{self.user.username}"
                if hasattr(self.user, "username") and self.user.username
                else f"<a href='tg://user?id={self.user_id}'>{self.user_id}</a>"
            )

        # Initialize ALL media tool attributes that TaskListener expects
        # These are required to prevent AttributeError when TaskListener checks them

        # Basic TaskConfig attributes
        self.user = self.message.from_user or self.message.sender_chat
        self.user_id = self.user.id
        # Get user-specific settings from user_data
        from bot.core.config_manager import Config
        from bot.helper.ext_utils.bot_utils import user_data

        self.user_dict = user_data.get(self.user_id, {})
        self.mid = self.message.id  # Message ID for task tracking
        self.dir = f"{DOWNLOAD_DIR}{self.mid}"  # Download directory path
        self.up_dir = ""
        self.link = ""
        # Set upload destination based on DEFAULT_UPLOAD setting
        default_upload = (
            self.user_dict.get("DEFAULT_UPLOAD") or Config.DEFAULT_UPLOAD
        )
        if not self.isLeech:
            # For mirror operations, use default upload destination
            self.up_dest = default_upload
        else:
            # For leech operations, follow the same logic as normal leech (from TaskConfig.before_start)
            self.up_dest = (
                Config.LEECH_DUMP_CHAT[0]
                if isinstance(Config.LEECH_DUMP_CHAT, list)
                and Config.LEECH_DUMP_CHAT
                else ""
            )
        self.rc_flags = ""
        self.name = ""
        self.subname = ""
        self.name_sub = ""
        self.size = 0
        self.subsize = 0
        self.proceed_count = 0
        self.is_file = False
        self.is_leech = self.isLeech
        self.is_cancelled = False
        self.progress = True
        self.files_to_proceed = []
        self.excluded_extensions = []
        self.ffmpeg_cmds = None
        self.thumb = None
        self.subproc = None
        self.chat_thread_id = None
        self.folder_name = ""
        self.split_size = 0
        self.max_split_size = 0
        self.multi = 0
        self.seed = False
        self.extract = False
        self.compress = False
        self.select = False
        self.join = False
        self.private_link = False
        self.stop_duplicate = False
        self.sample_video = False
        self.convert_audio = False
        self.convert_video = False
        self.screen_shots = False
        self.force_run = False
        self.force_download = False
        self.force_upload = False
        self.is_torrent = False
        self.is_qbit = False
        self.is_nzb = False
        self.is_clone = False
        self.is_ytdlp = False
        self.is_jd = False
        # Set user_transmission based on config and user settings (same as normal leech)
        # This follows the exact same logic as TaskConfig.before_start() method
        from bot.core.aeon_client import TgClient

        self.user_transmission = TgClient.IS_PREMIUM_USER and (
            self.user_dict.get("USER_TRANSMISSION")
            or (
                Config.USER_TRANSMISSION
                and "USER_TRANSMISSION" not in self.user_dict
            )
        )
        self.hybrid_leech = False
        self.as_med = False
        self.as_doc = False
        self.bot_trans = False
        self.user_trans = False

        # Apply the same user_transmission logic as normal leech (from TaskConfig.before_start)
        # Handle bot_trans and user_trans flags like normal leech does
        if self.bot_trans:
            self.user_transmission = False
            self.hybrid_leech = False
        if self.user_trans:
            self.user_transmission = TgClient.IS_PREMIUM_USER

        self.same_dir = {}  # Required for TaskListener same directory handling

        # Compression attributes (all disabled for streamrip)
        self.compression_enabled = False
        self.compression_priority = 0
        self.compression_video_enabled = False
        self.compression_audio_enabled = False
        self.compression_image_enabled = False
        self.compression_document_enabled = False
        self.compression_subtitle_enabled = False
        self.compression_archive_enabled = False
        self.compression_delete_original = False
        self.compression_video_format = "none"
        self.compression_audio_format = "none"
        self.compression_image_format = "none"
        self.compression_document_format = "none"
        self.compression_subtitle_format = "none"
        self.compression_archive_format = "none"
        self.compression_video_preset = "medium"
        self.compression_audio_preset = "medium"
        self.compression_image_preset = "medium"
        self.compression_document_preset = "medium"
        self.compression_subtitle_preset = "medium"
        self.compression_archive_preset = "medium"

        # Watermark attributes (all disabled for streamrip)
        self.watermark_enabled = False
        self.watermark_priority = 0
        self.watermark = ""
        self.watermark_position = ""
        self.watermark_size = 0
        self.watermark_color = ""
        self.watermark_font = ""
        self.watermark_opacity = 1.0
        self.watermark_threading = False
        self.watermark_fast_mode = False
        self.watermark_maintain_quality = False
        self.watermark_remove_original = False
        self.audio_watermark_enabled = False
        self.audio_watermark_text = ""
        self.audio_watermark_interval = 30
        self.subtitle_watermark_enabled = False
        self.subtitle_watermark_text = ""
        self.subtitle_watermark_interval = 10
        self.image_watermark_enabled = False
        self.image_watermark_path = ""
        self.image_watermark_scale = 10
        self.image_watermark_position = "bottom_right"
        self.image_watermark_opacity = 1.0

        # Merge attributes (all disabled for streamrip)
        self.merge_enabled = False
        self.merge_priority = 0
        self.merge_threading = False
        self.merge_remove_original = False
        self.concat_demuxer_enabled = False
        self.filter_complex_enabled = False
        self.merge_output_format_video = "none"
        self.merge_output_format_audio = "none"
        self.merge_video = False
        self.merge_audio = False
        self.merge_subtitle = False
        self.merge_all = False
        self.merge_image = False
        self.merge_pdf = False

        # Trim attributes (all disabled for streamrip)
        self.trim_enabled = False
        self.trim_priority = 0
        self.trim = ""
        self.trim_start_time = "00:00:00"
        self.trim_end_time = ""
        self.trim_delete_original = False
        self.trim_video_enabled = False
        self.trim_video_codec = "copy"
        self.trim_video_preset = "medium"
        self.trim_video_format = "none"
        self.trim_audio_enabled = False
        self.trim_audio_codec = "copy"
        self.trim_audio_preset = "medium"
        self.trim_audio_format = "none"
        self.trim_image_enabled = False
        self.trim_image_quality = "none"
        self.trim_image_format = "none"
        self.trim_document_enabled = False
        self.trim_document_quality = "none"
        self.trim_document_format = "none"
        self.trim_subtitle_enabled = False
        self.trim_subtitle_encoding = "utf-8"
        self.trim_subtitle_format = "none"
        self.trim_archive_enabled = False
        self.trim_archive_format = "none"

        # Extract attributes (all disabled for streamrip)
        self.extract_enabled = False
        self.extract_priority = 0
        self.extract_maintain_quality = False
        self.extract_delete_original = False
        self.extract_video_enabled = False
        self.extract_video_index = None
        self.extract_video_indices = []
        self.extract_video_codec = "none"
        self.extract_video_format = "none"
        self.extract_video_quality = "none"
        self.extract_video_preset = "none"
        self.extract_video_bitrate = "none"
        self.extract_video_resolution = "none"
        self.extract_video_fps = "none"
        self.extract_audio_enabled = False
        self.extract_audio_index = None
        self.extract_audio_indices = []
        self.extract_audio_codec = "none"
        self.extract_audio_format = "none"
        self.extract_audio_bitrate = "none"
        self.extract_audio_channels = "none"
        self.extract_audio_sampling = "none"
        self.extract_audio_volume = "none"
        self.extract_subtitle_enabled = False
        self.extract_subtitle_index = None
        self.extract_subtitle_indices = []
        self.extract_subtitle_codec = "none"
        self.extract_subtitle_format = "none"
        self.extract_subtitle_language = "none"
        self.extract_subtitle_encoding = "none"
        self.extract_subtitle_font = "none"
        self.extract_subtitle_font_size = "none"
        self.extract_attachment_enabled = False
        self.extract_attachment_index = None
        self.extract_attachment_indices = []
        self.extract_attachment_format = "none"
        self.extract_attachment_filter = "none"

        # Add attributes (all disabled for streamrip)
        self.add_enabled = False
        self.add_priority = 0
        self.add_delete_original = False
        self.add_preserve_tracks = False
        self.add_replace_tracks = False
        self.add_video_enabled = False
        self.add_video_index = None
        self.add_video_codec = "copy"
        self.add_video_quality = "none"
        self.add_video_preset = "none"
        self.add_video_bitrate = "none"
        self.add_video_resolution = "none"
        self.add_video_fps = "none"
        self.add_audio_enabled = False
        self.add_audio_index = None
        self.add_audio_codec = "copy"
        self.add_audio_bitrate = "none"
        self.add_audio_channels = "none"
        self.add_audio_sampling = "none"
        self.add_audio_volume = "none"
        self.add_subtitle_enabled = False
        self.add_subtitle_index = None
        self.add_subtitle_codec = "copy"
        self.add_subtitle_language = "none"
        self.add_subtitle_encoding = "none"
        self.add_subtitle_font = "none"
        self.add_subtitle_font_size = "none"
        self.add_attachment_enabled = False
        self.add_attachment_index = None
        self.add_attachment_mimetype = "none"

        # Convert attributes (all disabled for streamrip)
        self.user_convert_enabled = False
        self.owner_convert_enabled = False
        self.convert_video_codec = None
        self.convert_video_crf = None
        self.convert_video_preset = None
        self.convert_video_maintain_quality = False
        self.convert_audio_bitrate = None
        self.convert_audio_channels = None
        self.convert_audio_codec = None
        self.convert_audio_sampling = None
        self.convert_audio_volume = None

        # Metadata attributes (all disabled for streamrip)
        self.metadata = ""
        self.metadata_title = ""
        self.metadata_author = ""
        self.metadata_comment = ""
        self.metadata_all = ""
        self.metadata_video_title = ""
        self.metadata_video_author = ""
        self.metadata_video_comment = ""
        self.metadata_audio_title = ""
        self.metadata_audio_author = ""
        self.metadata_audio_comment = ""
        self.metadata_subtitle_title = ""
        self.metadata_subtitle_author = ""
        self.metadata_subtitle_comment = ""

        # Other essential attributes
        self.thumbnail_layout = ""
        self.del_flag = False
        self.preserve_flag = False
        self.replace_flag = False
        self.equal_splits_enabled = False
        self.is_super_chat = self.message.chat.type.name in ["SUPERGROUP", "CHANNEL"]

        # Set client attribute for Telegram operations
        from bot.core.aeon_client import TgClient

        self.client = TgClient.bot

    def set_download_helper(self, download_helper):
        """Set the download helper"""
        self.download_helper = download_helper

    def set_download_info(
        self, url: str, quality: int | None = None, codec: str | None = None
    ):
        """Set download information"""
        self.url = url
        self.quality = quality
        self.codec = codec

    async def on_download_start(self):
        """Called when download starts"""
        try:
            # Parse URL to get platform info
            from bot.helper.streamrip_utils.url_parser import parse_streamrip_url

            parsed = await parse_streamrip_url(self.url)
            if parsed:
                platform, media_type, media_id = parsed

                # Send start message
                quality_names = {
                    0: "128 kbps",
                    1: "320 kbps",
                    2: "CD Quality",
                    3: "Hi-Res",
                    4: "Hi-Res+",
                }

                quality_name = (
                    quality_names.get(self.quality, f"Quality {self.quality}")
                    if self.quality is not None
                    else "Default"
                )
                codec_name = self.codec.upper() if self.codec else "Default"

                msg = f"{self.tag} 🎵 **Streamrip Download Started**\n\n"
                msg += f"🎯 **Platform:** {platform.title()}\n"
                msg += f"📁 **Type:** {media_type.title()}\n"
                msg += f"📊 **Quality:** {quality_name}\n"
                msg += f"🎵 **Format:** {codec_name}\n\n"
                msg += "⏳ Initializing download..."

                start_msg = await send_message(self.message, msg)

                # Auto-delete start message after 30 seconds
                asyncio.create_task(auto_delete_message(start_msg, time=30))

        except Exception as e:
            LOGGER.error(f"Error in streamrip download start: {e}")

    async def on_download_progress(self, current: int, total: int):
        """Called during download progress"""
        try:
            current_time = time.time()

            # Throttle updates
            if current_time - self._last_update < self._update_interval:
                return

            self._last_update = current_time

            # Update download helper progress
            if self.download_helper:
                self.download_helper._last_downloaded = current
                self.download_helper._size = total

                # Calculate speed and ETA
                elapsed = current_time - self._start_time
                if elapsed > 0 and current > 0:
                    self.download_helper._speed = current / elapsed

                    if self.download_helper._speed > 0 and total > current:
                        remaining = total - current
                        self.download_helper._eta = (
                            remaining / self.download_helper._speed
                        )

        except Exception as e:
            LOGGER.error(f"Error in streamrip progress update: {e}")

    async def on_download_complete(self):
        """Called when download completes - follows same pattern as TaskListener"""
        try:
            # Get download info from the download directory
            download_size = 0
            file_count = 0

            if Path(self.dir).exists():
                # Count files and total size
                for file_path in Path(self.dir).rglob("*"):
                    if file_path.is_file():
                        download_size += file_path.stat().st_size
                        file_count += 1

            # Parse URL for platform info
            from bot.helper.streamrip_utils.url_parser import parse_streamrip_url

            platform_name = "Unknown"
            media_type = "Unknown"

            parsed = await parse_streamrip_url(self.url)
            if parsed:
                platform, media_type, media_id = parsed
                platform_name = platform.title()
                media_type = media_type.title()

            # Skip sending download completion message for streamrip
            # Just log the completion details
            elapsed_time = time.time() - self._start_time
            LOGGER.info(
                f"Streamrip download complete - Platform: {platform_name}, Type: {media_type}, Files: {file_count}, Size: {get_readable_file_size(download_size)}, Time: {self._format_time(elapsed_time)}"
            )

            # Set up directory structure exactly like TaskListener expects
            if Path(self.dir).exists():
                # Get the first file/folder to determine the name
                items = list(Path(self.dir).iterdir())
                if items:
                    # Use the first item's name as the task name
                    first_item = items[0]
                    if first_item.is_file():
                        # Single file - use filename without extension as name
                        self.name = first_item.stem
                    else:
                        # Directory - use directory name
                        self.name = first_item.name

                    LOGGER.info(f"Set streamrip task name: {self.name}")

            # Set up size and other attributes like TaskListener does - crucial for proper completion message for BOTH leech and mirror
            from bot.helper.ext_utils.files_utils import get_path_size

            self.size = await get_path_size(self.dir)

            # Set up_path for mirror operations (TaskListener sets this for proper completion messaging)
            self.up_path = self.dir

            LOGGER.info(f"Set streamrip task size: {self.size} bytes")
            LOGGER.info(f"Set streamrip up_path: {self.up_path}")

            # Import required classes for upload operations
            from asyncio import gather

            from bot.helper.ext_utils.bot_utils import sync_to_async
            from bot.helper.ext_utils.links_utils import is_gdrive_id
            from bot.helper.mirror_leech_utils.gdrive_utils.upload import (
                GoogleDriveUpload,
            )
            from bot.helper.mirror_leech_utils.rclone_utils.transfer import (
                RcloneTransferHelper,
            )
            from bot.helper.mirror_leech_utils.status_utils.gdrive_status import (
                GoogleDriveStatus,
            )
            from bot.helper.mirror_leech_utils.status_utils.rclone_status import (
                RcloneStatus,
            )
            from bot.helper.mirror_leech_utils.status_utils.telegram_status import (
                TelegramStatus,
            )
            from bot.helper.mirror_leech_utils.telegram_uploader import (
                TelegramUploader,
            )
            from bot.helper.telegram_helper.message_utils import (
                update_status_message,
            )

            # For leech operations, use standard TelegramUploader like TaskListener does
            if self.isLeech:
                LOGGER.info(f"Streamrip Leech Name: {self.name}")

                # Create standard TelegramUploader (same as TaskListener)
                tg = TelegramUploader(self, self.dir)

                # Store a reference to the telegram uploader for later use (e.g., during cancellation)
                self.telegram_uploader = tg

                # Add to task dict with TelegramStatus (same as TaskListener)
                async with task_dict_lock:
                    task_dict[self.mid] = TelegramStatus(self, tg, self.mid, "up")

                # Start upload using TelegramUploader (same as TaskListener)
                await gather(
                    update_status_message(self.message.chat.id),
                    tg.upload(),
                )

                # Keep reference for cancellation (same as TaskListener)
                if hasattr(tg, "dump_chat_msgs") and tg.dump_chat_msgs:
                    pass
                elif hasattr(tg, "log_msg") and tg.log_msg:
                    LOGGER.info(f"Keeping log message in chat: {tg.log_msg.chat.id}")
            elif is_gdrive_id(self.up_dest) or self.up_dest == "gd":
                LOGGER.info(f"Streamrip Gdrive Upload Name: {self.name}")

                # If up_dest is "gd", use the configured GDRIVE_ID (same as TaskListener)
                if self.up_dest == "gd":
                    gdrive_id = self.user_dict.get("GDRIVE_ID") or Config.GDRIVE_ID
                    if gdrive_id:
                        self.up_dest = gdrive_id
                    else:
                        LOGGER.warning(
                            "DEFAULT_UPLOAD is 'gd' but no GDRIVE_ID configured, falling back to Rclone"
                        )
                        LOGGER.info(f"Streamrip Rclone Upload Name: {self.name}")
                        RCTransfer = RcloneTransferHelper(self)
                        async with task_dict_lock:
                            task_dict[self.mid] = RcloneStatus(
                                self, RCTransfer, self.mid, "up"
                            )
                        await gather(
                            update_status_message(self.message.chat.id),
                            RCTransfer.upload(self.dir),
                        )
                        del RCTransfer
                        return

                # Use Google Drive upload (same as TaskListener)
                drive = GoogleDriveUpload(self, self.dir)
                async with task_dict_lock:
                    task_dict[self.mid] = GoogleDriveStatus(
                        self, drive, self.mid, "up"
                    )
                await gather(
                    update_status_message(self.message.chat.id),
                    sync_to_async(drive.upload),
                )
                del drive
            else:
                # Use Rclone upload (default for mirror operations, same as TaskListener)
                LOGGER.info(f"Streamrip Rclone Upload Name: {self.name}")

                RCTransfer = RcloneTransferHelper(self)
                async with task_dict_lock:
                    task_dict[self.mid] = RcloneStatus(
                        self, RCTransfer, self.mid, "up"
                    )
                await gather(
                    update_status_message(self.message.chat.id),
                    RCTransfer.upload(self.dir),
                )
                del RCTransfer
            return

        except Exception as e:
            LOGGER.error(f"Error in streamrip download complete: {e}")
            await self.on_download_error(str(e))

    # Remove the custom on_upload_complete override to use standard TaskListener behavior
    # This ensures streamrip follows the same task completion and task details message logic as normal leech

    async def on_download_error(self, error: str):
        """Called when download fails"""
        try:
            # Parse URL for platform info
            from bot.helper.streamrip_utils.url_parser import parse_streamrip_url

            platform_name = "Unknown"
            parsed = await parse_streamrip_url(self.url)
            if parsed:
                platform, media_type, media_id = parsed
                platform_name = platform.title()

            # Send error message
            msg = f"{self.tag} ❌ **Streamrip Download Failed**\n\n"
            msg += f"🎯 **Platform:** {platform_name}\n"
            msg += f"⚠️ **Error:** {error}\n\n"

            # Add troubleshooting tips
            if "authentication" in error.lower() or "login" in error.lower():
                msg += "💡 **Tip:** Check your platform credentials in bot configuration"
            elif "quality" in error.lower():
                msg += "💡 **Tip:** Try a lower quality setting or check your subscription"
            elif "not found" in error.lower():
                msg += (
                    "💡 **Tip:** The content might not be available on this platform"
                )
            elif "rate limit" in error.lower():
                msg += (
                    "💡 **Tip:** Too many requests, please wait and try again later"
                )
            else:
                msg += "💡 **Tip:** Check the URL and try again"

            error_msg = await send_message(self.message, msg)

            # Auto-delete error message after 5 minutes
            asyncio.create_task(auto_delete_message(error_msg, time=300))

            # Remove from task dict
            async with task_dict_lock:
                if self.mid in task_dict:
                    del task_dict[self.mid]

            # Call parent error handler
            await super().on_download_error(error)

        except Exception as e:
            LOGGER.error(f"Error in streamrip error handler: {e}")

    # Remove custom completion message logic - use standard TaskListener approach

    def _format_time(self, seconds: float) -> str:
        """Format time in seconds to readable format"""
        if seconds < 60:
            return f"{seconds:.1f}s"
        if seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes}m {secs}s"
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"
