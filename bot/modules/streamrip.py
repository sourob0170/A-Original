import asyncio
import os

from bot import LOGGER
from bot.core.config_manager import Config
from bot.helper.ext_utils.bot_utils import arg_parser, new_task
from bot.helper.listeners.streamrip_listener import StreamripListener
from bot.helper.mirror_leech_utils.download_utils.streamrip_download import (
    add_streamrip_download,
)
from bot.helper.streamrip_utils.quality_selector import show_quality_selector
# search_handler.py was deleted, so remove this import
from bot.helper.streamrip_utils.url_parser import (
    is_file_input,
    is_lastfm_url,
    is_streamrip_url,
    parse_file_content,
    parse_streamrip_url,
)
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    delete_message,
    send_message,
)


class StreamripCommands:
    """Streamrip download commands"""

    @staticmethod
    def _get_streamrip_args():
        """Get streamrip-specific argument definitions"""
        return {
            # Streamrip specific flags
            "-q": "",  # Quality level
            "-quality": "",  # Quality level (alias)
            "-c": "",  # Codec
            "-codec": "",  # Codec (alias)
            "-f": False,  # Force run
            "-fd": False,  # Force download
            "link": "",
        }

    # This method is no longer used after removing search functionality
    # @staticmethod
    # def _parse_search_args(args_list):
    #     ... (removed) ...

    @staticmethod
    async def _process_streamrip_download(message, is_leech: bool):
        """Shared function for processing streamrip downloads (mirror/leech)"""
        if not Config.STREAMRIP_ENABLED:
            reply = await send_message(
                message, "❌ Streamrip downloads are disabled!"
            )
            await auto_delete_message(reply, time=300)
            return

        # Parse arguments with streamrip-specific flags only
        text = message.text.split()
        args = StreamripCommands._get_streamrip_args()
        arg_parser(text[1:], args)

        # Get input from message (URL, file content, or ID format)
        input_data = ""
        if reply_to := message.reply_to_message:
            if reply_to.document:
                # Handle file upload
                try:
                    file_path = await reply_to.download()
                    from aiofiles import open as aiopen

                    async with aiopen(file_path, encoding="utf-8") as f:
                        input_data = await f.read()
                    os.remove(file_path)  # Clean up downloaded file
                except Exception as e:
                    reply = await send_message(
                        message, f"❌ Failed to read file: {e!s}"
                    )
                    await auto_delete_message(reply, time=300)
                    return
            else:
                input_data = reply_to.text.strip()
        else:
            input_data = args.get("link", "").strip()

        if not input_data:
            # Show interactive help menu using COMMAND_USAGE for consistency
            # Assuming COMMAND_USAGE will now have a "download" key for the /download command
            from bot.helper.ext_utils.bot_utils import COMMAND_USAGE

            reply = await send_message(
                message, COMMAND_USAGE["download"][0], COMMAND_USAGE["download"][1]
            )
            await auto_delete_message(reply, time=600)
            return

        # Process input and get URLs to download
        urls_to_process = await StreamripCommands._process_input(input_data, message)
        if not urls_to_process:
            return

        # Delete original command message and replied message instantly
        try:
            await delete_message(message)
            if message.reply_to_message:
                await delete_message(message.reply_to_message)
        except Exception as e:
            LOGGER.error(f"Failed to delete command messages: {e}")

        # For batch downloads, show confirmation
        if len(urls_to_process) > 1:
            download_type = "Leech" if is_leech else "Mirror"
            destination = "Telegram" if is_leech else "Cloud Storage"

            confirm_msg = f"📋 **Batch {download_type} Download**\n\n"
            confirm_msg += f"🔢 **Total Items:** {len(urls_to_process)}\n"
            confirm_msg += f"📁 **Destination:** {destination}\n\n"

            # Show first few URLs as preview
            preview_count = min(3, len(urls_to_process))
            confirm_msg += "**Preview:**\n"
            for i, url in enumerate(urls_to_process[:preview_count]):
                parsed = await parse_streamrip_url(url)
                if parsed:
                    platform, media_type, _ = parsed
                    confirm_msg += (
                        f"{i + 1}. {platform.title()} {media_type.title()}\n"
                    )
                else:
                    confirm_msg += (
                        f"{i + 1}. {url[:40]}{'...' if len(url) > 40 else ''}\n"
                    )

            if len(urls_to_process) > preview_count:
                confirm_msg += (
                    f"... and {len(urls_to_process) - preview_count} more\n"
                )

            confirm_msg += "\n🚀 Starting batch download..."

            batch_msg = await send_message(message, confirm_msg)
            await auto_delete_message(batch_msg, time=60)

        # Process each URL
        for i, url in enumerate(urls_to_process):
            try:
                # Parse URL to get platform info
                parsed = await parse_streamrip_url(url)
                if not parsed:
                    continue

                platform, media_type, _ = parsed

                # Create listener for each download
                listener = StreamripListener(message, isLeech=is_leech)

                # Set platform and media_type attributes for telegram uploader
                listener.platform = platform
                listener.media_type = media_type

                # For batch downloads, add item number to tag
                if len(urls_to_process) > 1:
                    listener.tag = f"[{i + 1}/{len(urls_to_process)}]"

                # Check for quality selection
                quality = None
                codec = None

                # Parse quality from arguments
                if "q" in args or "quality" in args:
                    try:
                        quality = int(args.get("q") or args.get("quality"))
                        if quality not in range(5):  # 0-4
                            raise ValueError("Quality must be 0-4")
                    except ValueError:
                        reply = await send_message(
                            message,
                            "❌ Invalid quality! Use 0-4:\n"
                            "• 0: 128 kbps\n• 1: 320 kbps\n• 2: CD Quality\n• 3: Hi-Res\n• 4: Hi-Res+",
                        )
                        await auto_delete_message(reply, time=300)
                        return

                # Parse codec from arguments
                if "c" in args or "codec" in args:
                    codec = args.get("c") or args.get("codec")
                    if codec not in Config.STREAMRIP_SUPPORTED_CODECS:
                        reply = await send_message(
                            message,
                            f"❌ Invalid codec! Supported: {', '.join(Config.STREAMRIP_SUPPORTED_CODECS)}",
                        )
                        await auto_delete_message(reply, time=300)
                        return

                # Show quality selector if not specified (only for first item in batch)
                if (quality is None or codec is None) and i == 0:
                    selection = await show_quality_selector(
                        listener, platform, media_type
                    )
                    if not selection:
                        return  # User cancelled or timeout

                    if quality is None:
                        quality = selection["quality"]
                    if codec is None:
                        codec = selection["codec"]

                # Check for force download flag
                force_download = args.get("f", False) or args.get("fd", False)

                # Start download
                await add_streamrip_download(
                    listener, url, quality, codec, force_download
                )

            except Exception as e:
                LOGGER.error(f"Error processing URL {url}: {e}")
                if len(urls_to_process) == 1:
                    # For single URL, show error to user
                    reply = await send_message(
                        message, f"❌ Error processing URL: {e!s}"
                    )
                    await auto_delete_message(reply, time=300)
                # For batch, just log and continue

    @staticmethod
    async def _process_input(input_data: str, message) -> list:
        """Process input data and return list of URLs to download"""
        urls_to_process = []

        # Determine input type and process accordingly
        if is_file_input(input_data):
            # Handle file content (multiple URLs/IDs)
            urls_to_process = await parse_file_content(input_data)
            if not urls_to_process:
                reply = await send_message(
                    message, "❌ No valid URLs found in file content!"
                )
                await auto_delete_message(reply, time=300)
                return []
        else:
            # Single URL or ID format
            urls_to_process = [input_data]

        # Validate all URLs/IDs
        valid_urls = []
        for url in urls_to_process:
            if await is_streamrip_url(url) or is_lastfm_url(url) or ":" in url:
                valid_urls.append(url)

        if not valid_urls:
            reply = await send_message(message, "❌ No valid streamrip URLs found!")
            await auto_delete_message(reply, time=300)
            return []

        return valid_urls

    @staticmethod
    @new_task
    async def process_download_command(_, message):
        """Handle streamrip download command (equivalent to leech)"""
        await StreamripCommands._process_streamrip_download(message, is_leech=True)

    # streamrip_search and its helper _parse_search_args are removed
    # _get_streamrip_args and _process_streamrip_download are kept as they are used by process_download_command

# Export command functions for handlers.py
# streamrip_mirror = StreamripCommands.streamrip_mirror # Removed
# streamrip_leech = StreamripCommands.streamrip_leech # Renamed/Replaced
# streamrip_search = StreamripCommands.streamrip_search # Removed
download = StreamripCommands.process_download_command
# The large block of code below this was the body of the old streamrip_search command.
# It is no longer used and is effectively dead code. It has been removed.
