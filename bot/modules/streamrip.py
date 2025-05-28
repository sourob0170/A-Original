import os

from bot import LOGGER
from bot.core.config_manager import Config
from bot.helper.ext_utils.bot_utils import arg_parser, new_task
from bot.helper.listeners.streamrip_listener import StreamripListener
from bot.helper.mirror_leech_utils.download_utils.streamrip_download import (
    add_streamrip_download,
)
from bot.helper.streamrip_utils.quality_selector import show_quality_selector
from bot.helper.streamrip_utils.search_handler import (
    search_music,
    search_music_auto_first,
)
from bot.helper.streamrip_utils.url_parser import (
    is_file_input,
    is_lastfm_url,
    is_streamrip_url,
    parse_file_content,
    parse_streamrip_url,
)
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    send_message,
)


class StreamripCommands:
    """Streamrip download commands"""

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
            else:
                LOGGER.warning(f"Skipping invalid URL: {url}")

        if not valid_urls:
            reply = await send_message(message, "❌ No valid streamrip URLs found!")
            await auto_delete_message(reply, time=300)
            return []

        return valid_urls

    @staticmethod
    @new_task
    async def streamrip_mirror(_, message):
        """Handle streamrip mirror command"""
        if not Config.STREAMRIP_ENABLED:
            reply = await send_message(
                message, "❌ Streamrip downloads are disabled!"
            )
            await auto_delete_message(reply, time=300)
            return

        # Parse arguments with full flag support
        text = message.text.split()
        args = {
            # Streamrip specific flags
            "-q": "",  # Quality level
            "-quality": "",  # Quality level (alias)
            "-c": "",  # Codec
            "-codec": "",  # Codec (alias)
            # Standard download flags
            "-n": "",  # Custom name
            "-up": "",  # Upload path
            "-rcf": "",  # Rclone flags
            "-h": "",  # Headers
            "-z": "",  # Archive password
            "-e": "",  # Exclude extensions
            "-s": False,  # Select files
            "-j": False,  # Join files
            "-sync": False,  # Sync with cloud
            "-doc": False,  # Upload as document
            "-med": False,  # Upload as media
            "-f": False,  # Force run
            "-fd": False,  # Force download
            "-fu": False,  # Force upload
            "-t": "",  # Thumbnail
            "-d": "",  # Seed ratio:time
            "-m": "",  # Same directory
            "-au": "",  # Auth username
            "-ap": "",  # Auth password
            "-ns": "",  # Name substitute
            # Media tools flags
            "-mt": False,  # Media tools
            "-compress": False,  # Enable compression
            "-extract": False,  # Enable extraction
            "-add": False,  # Enable adding tracks
            # Compression flags
            "-comp-video": False,
            "-comp-audio": False,
            "-comp-image": False,
            "-comp-document": False,
            "-comp-subtitle": False,
            "-comp-archive": False,
            # Compression presets
            "-video-fast": False,
            "-video-medium": False,
            "-video-slow": False,
            "-audio-fast": False,
            "-audio-medium": False,
            "-audio-slow": False,
            "-image-fast": False,
            "-image-medium": False,
            "-image-slow": False,
            "-document-fast": False,
            "-document-medium": False,
            "-document-slow": False,
            "-subtitle-fast": False,
            "-subtitle-medium": False,
            "-subtitle-slow": False,
            "-archive-fast": False,
            "-archive-medium": False,
            "-archive-slow": False,
            # Conversion flags
            "-cv": "",  # Convert video
            "-ca": "",  # Convert audio
            "-cs": "",  # Convert subtitle
            "-cd": "",  # Convert document
            "-cr": "",  # Convert archive
            "-del": False,  # Delete original after conversion
            # Additional flags from help_messages.py
            "-opt": "",  # yt-dlp options
            "-tl": "",  # Thumbnail layout
            "-hl": False,  # Hybrid leech
            "-bt": False,  # Bot transmission
            "-ut": False,  # User transmission
            "-es": False,  # Enable subtitles
            # Extract flags
            "-extract-video": False,
            "-extract-audio": False,
            "-extract-subtitle": False,
            "-extract-attachment": False,
            "-extract-video-index": "",
            "-extract-audio-index": "",
            "-extract-subtitle-index": "",
            "-extract-attachment-index": "",
            "-vi": "",  # Short for extract-video-index
            "-ai": "",  # Short for extract-audio-index
            "-si": "",  # Short for extract-subtitle-index
            "-ati": "",  # Short for extract-attachment-index
            # Add flags
            "-add-video": False,
            "-add-audio": False,
            "-add-subtitle": False,
            "-add-attachment": False,
            "-add-video-index": "",
            "-add-audio-index": "",
            "-add-subtitle-index": "",
            "-add-attachment-index": "",
            "-avi": "",  # Short for add-video-index
            "-aai": "",  # Short for add-audio-index
            "-asi": "",  # Short for add-subtitle-index
            "-aati": "",  # Short for add-attachment-index
            "-preserve": False,
            "-replace": False,
            # Merge flags
            "-merge-video": False,
            "-merge-audio": False,
            "-merge-subtitle": False,
            "-merge-image": False,
            "-merge-pdf": False,
            "-merge-all": False,
            # Watermark flags
            "-watermark": "",  # Text watermark
            "-wm": "",  # Short for watermark
            "-iwm": "",  # Image watermark
            # Trim flags
            "-trim": "",  # Trim video/audio
            # Metadata flags
            "-md": False,  # Enable metadata
            "-metadata-title": "",
            "-metadata-author": "",
            "-metadata-artist": "",
            "-metadata-album": "",
            "-metadata-year": "",
            "-metadata-genre": "",
            "-metadata-comment": "",
            "-metadata-all": "",
            "-metadata-video-title": "",
            "-metadata-audio-title": "",
            "-metadata-subtitle-title": "",
            "-metadata-video-author": "",
            "-metadata-audio-author": "",
            "-metadata-subtitle-author": "",
            # FFmpeg flags
            "-ff": "",  # Custom FFmpeg command
            # Sample and screenshot flags
            "-sv": "",  # Sample video
            "-ss": "",  # Screenshots
            "link": "",
        }
        arg_parser(text[1:], args)

        # Check if media tools flags are enabled
        from bot.helper.ext_utils.bot_utils import is_flag_enabled

        # Disable flags that depend on disabled media tools
        for flag in list(args.keys()):
            if flag.startswith("-") and not is_flag_enabled(flag):
                if isinstance(args[flag], bool):
                    args[flag] = False
                elif isinstance(args[flag], set):
                    args[flag] = set()
                elif isinstance(args[flag], str):
                    args[flag] = ""
                elif isinstance(args[flag], int):
                    args[flag] = 0

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
            from bot.helper.ext_utils.bot_utils import COMMAND_USAGE

            reply = await send_message(
                message, COMMAND_USAGE["streamrip"][0], COMMAND_USAGE["streamrip"][1]
            )
            await auto_delete_message(reply, time=600)
            return

        # Process input and get URLs to download
        urls_to_process = await StreamripCommands._process_input(input_data, message)
        if not urls_to_process:
            return

        # Delete original command message and replied message instantly
        try:
            from bot.helper.telegram_helper.message_utils import delete_message

            await delete_message(message)
            if message.reply_to_message:
                await delete_message(message.reply_to_message)
        except Exception as e:
            LOGGER.debug(f"Failed to delete command messages: {e}")

        # For batch downloads, show confirmation
        if len(urls_to_process) > 1:
            confirm_msg = "📋 **Batch Mirror Download**\n\n"
            confirm_msg += f"🔢 **Total Items:** {len(urls_to_process)}\n"
            confirm_msg += "📁 **Destination:** Cloud Storage\n\n"

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
                    LOGGER.warning(f"Failed to parse URL: {url}")
                    continue

                platform, media_type, media_id = parsed

                # Create listener for each download
                listener = StreamripListener(message, isLeech=False)

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
    @new_task
    async def streamrip_leech(_, message):
        """Handle streamrip leech command"""
        if not Config.STREAMRIP_ENABLED:
            reply = await send_message(
                message, "❌ Streamrip downloads are disabled!"
            )
            await auto_delete_message(reply, time=300)
            return

        # Parse arguments with full flag support
        text = message.text.split()
        args = {
            # Streamrip specific flags
            "-q": "",  # Quality level
            "-quality": "",  # Quality level (alias)
            "-c": "",  # Codec
            "-codec": "",  # Codec (alias)
            # Standard download flags
            "-n": "",  # Custom name
            "-thumb": "",  # Thumbnail URL
            "-sp": "",  # Split size
            "-h": "",  # Headers
            "-z": "",  # Archive password
            "-e": "",  # Exclude extensions
            "-s": False,  # Select files
            "-j": False,  # Join files
            "-doc": False,  # Upload as document
            "-med": False,  # Upload as media
            "-cap": "",  # Caption
            "-f": False,  # Force run
            "-fd": False,  # Force download
            "-fu": False,  # Force upload
            "-t": "",  # Thumbnail
            "-d": "",  # Seed ratio:time
            "-m": "",  # Same directory
            "-au": "",  # Auth username
            "-ap": "",  # Auth password
            "-ns": "",  # Name substitute
            # Media tools flags
            "-mt": False,  # Media tools
            "-compress": False,  # Enable compression
            "-extract": False,  # Enable extraction
            "-add": False,  # Enable adding tracks
            # Compression flags
            "-comp-video": False,
            "-comp-audio": False,
            "-comp-image": False,
            "-comp-document": False,
            "-comp-subtitle": False,
            "-comp-archive": False,
            # Compression presets
            "-video-fast": False,
            "-video-medium": False,
            "-video-slow": False,
            "-audio-fast": False,
            "-audio-medium": False,
            "-audio-slow": False,
            "-image-fast": False,
            "-image-medium": False,
            "-image-slow": False,
            "-document-fast": False,
            "-document-medium": False,
            "-document-slow": False,
            "-subtitle-fast": False,
            "-subtitle-medium": False,
            "-subtitle-slow": False,
            "-archive-fast": False,
            "-archive-medium": False,
            "-archive-slow": False,
            # Conversion flags
            "-cv": "",  # Convert video
            "-ca": "",  # Convert audio
            "-cs": "",  # Convert subtitle
            "-cd": "",  # Convert document
            "-cr": "",  # Convert archive
            "-del": False,  # Delete original after conversion
            # Additional flags from help_messages.py
            "-opt": "",  # yt-dlp options
            "-tl": "",  # Thumbnail layout
            "-hl": False,  # Hybrid leech
            "-bt": False,  # Bot transmission
            "-ut": False,  # User transmission
            "-es": False,  # Enable subtitles
            # Extract flags
            "-extract-video": False,
            "-extract-audio": False,
            "-extract-subtitle": False,
            "-extract-attachment": False,
            "-extract-video-index": "",
            "-extract-audio-index": "",
            "-extract-subtitle-index": "",
            "-extract-attachment-index": "",
            "-vi": "",  # Short for extract-video-index
            "-ai": "",  # Short for extract-audio-index
            "-si": "",  # Short for extract-subtitle-index
            "-ati": "",  # Short for extract-attachment-index
            # Add flags
            "-add-video": False,
            "-add-audio": False,
            "-add-subtitle": False,
            "-add-attachment": False,
            "-add-video-index": "",
            "-add-audio-index": "",
            "-add-subtitle-index": "",
            "-add-attachment-index": "",
            "-avi": "",  # Short for add-video-index
            "-aai": "",  # Short for add-audio-index
            "-asi": "",  # Short for add-subtitle-index
            "-aati": "",  # Short for add-attachment-index
            "-preserve": False,
            "-replace": False,
            # Merge flags
            "-merge-video": False,
            "-merge-audio": False,
            "-merge-subtitle": False,
            "-merge-image": False,
            "-merge-pdf": False,
            "-merge-all": False,
            # Watermark flags
            "-watermark": "",  # Text watermark
            "-wm": "",  # Short for watermark
            "-iwm": "",  # Image watermark
            # Trim flags
            "-trim": "",  # Trim video/audio
            # Metadata flags
            "-md": False,  # Enable metadata
            "-metadata-title": "",
            "-metadata-author": "",
            "-metadata-artist": "",
            "-metadata-album": "",
            "-metadata-year": "",
            "-metadata-genre": "",
            "-metadata-comment": "",
            "-metadata-all": "",
            "-metadata-video-title": "",
            "-metadata-audio-title": "",
            "-metadata-subtitle-title": "",
            "-metadata-video-author": "",
            "-metadata-audio-author": "",
            "-metadata-subtitle-author": "",
            # FFmpeg flags
            "-ff": "",  # Custom FFmpeg command
            # Sample and screenshot flags
            "-sv": "",  # Sample video
            "-ss": "",  # Screenshots
            "link": "",
        }
        arg_parser(text[1:], args)

        # Check if media tools flags are enabled
        from bot.helper.ext_utils.bot_utils import is_flag_enabled

        # Disable flags that depend on disabled media tools
        for flag in list(args.keys()):
            if flag.startswith("-") and not is_flag_enabled(flag):
                if isinstance(args[flag], bool):
                    args[flag] = False
                elif isinstance(args[flag], set):
                    args[flag] = set()
                elif isinstance(args[flag], str):
                    args[flag] = ""
                elif isinstance(args[flag], int):
                    args[flag] = 0

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
            from bot.helper.ext_utils.bot_utils import COMMAND_USAGE

            reply = await send_message(
                message, COMMAND_USAGE["streamrip"][0], COMMAND_USAGE["streamrip"][1]
            )
            await auto_delete_message(reply, time=600)
            return

        # Process input and get URLs to download
        urls_to_process = await StreamripCommands._process_input(input_data, message)
        if not urls_to_process:
            return

        # Delete original command message and replied message instantly
        try:
            from bot.helper.telegram_helper.message_utils import delete_message

            await delete_message(message)
            if message.reply_to_message:
                await delete_message(message.reply_to_message)
        except Exception as e:
            LOGGER.debug(f"Failed to delete command messages: {e}")

        # For batch downloads, show confirmation
        if len(urls_to_process) > 1:
            confirm_msg = "📋 **Batch Leech Download**\n\n"
            confirm_msg += f"🔢 **Total Items:** {len(urls_to_process)}\n"
            confirm_msg += "📁 **Destination:** Telegram\n\n"

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
                    LOGGER.warning(f"Failed to parse URL: {url}")
                    continue

                platform, media_type, media_id = parsed

                # Create listener for each download
                listener = StreamripListener(message, isLeech=True)

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
    @new_task
    async def streamrip_search(_, message):
        """Handle streamrip search command"""
        if not Config.STREAMRIP_ENABLED:
            reply = await send_message(
                message, "❌ Streamrip downloads are disabled!"
            )
            await auto_delete_message(reply, time=300)
            return

        # Parse arguments
        text = message.text.split()
        args = {
            "-p": "",
            "-platform": "",
            "-t": "",
            "-type": "",
            "-f": "",
            "-first": "",
            "-n": "",
            "-num": "",
            "link": "",
        }
        arg_parser(text[1:], args)

        # Get search query (from link field which contains non-flag arguments)
        query = args.get("link", "").strip()

        if not query:
            reply = await send_message(
                message,
                "❌ Please provide a search query!\n\n"
                "**Usage:** `/srsearch <query> [options]`\n"
                "**Example:** `/srsearch Daft Punk Random Access Memories`\n\n"
                "📁 **Note:** Search results are always **leeched to Telegram** for easy access!\n\n"
                "**Available Options:**\n"
                "• `-p <platform>` - Search specific platform (qobuz, tidal, deezer, soundcloud)\n"
                "• `-t <type>` - Filter by media type (album, track, artist, playlist)\n"
                "• `-f` - Auto-download first result\n"
                "• `-n <number>` - Limit number of results (default: 20)\n\n"
                "**Examples:**\n"
                "• `/srsearch -p qobuz -t album Thriller`\n"
                "• `/srsearch -f Blinding Lights` (auto-download first result)",
            )
            await auto_delete_message(reply, time=300)
            return

        # Parse platform filter
        platform = None
        if "p" in args or "platform" in args:
            platform = (args.get("p") or args.get("platform")).lower()
            supported_platforms = ["qobuz", "tidal", "deezer", "soundcloud"]
            if platform not in supported_platforms:
                reply = await send_message(
                    message,
                    f"❌ Invalid platform! Supported: {', '.join(supported_platforms)}",
                )
                await auto_delete_message(reply, time=300)
                return

        # Parse media type filter
        media_type_filter = None
        if "t" in args or "type" in args:
            media_type_filter = (args.get("t") or args.get("type")).lower()
            supported_types = ["album", "track", "artist", "playlist"]
            if media_type_filter not in supported_types:
                reply = await send_message(
                    message,
                    f"❌ Invalid media type! Supported: {', '.join(supported_types)}",
                )
                await auto_delete_message(reply, time=300)
                return

        # Parse auto-download first result flag
        auto_first = "f" in args or "first" in args

        # Parse result limit
        result_limit = Config.STREAMRIP_MAX_SEARCH_RESULTS
        if "n" in args or "num" in args:
            try:
                result_limit = int(args.get("n") or args.get("num"))
                if result_limit < 1 or result_limit > 100:
                    raise ValueError("Result limit must be between 1-100")
            except ValueError:
                reply = await send_message(
                    message,
                    "❌ Invalid result limit! Must be a number between 1-100",
                )
                await auto_delete_message(reply, time=300)
                return

        # Create listener - always leech for search results (users expect files in Telegram)
        listener = StreamripListener(message, isLeech=True)

        # Perform search
        if auto_first:
            # For auto-first, we need to implement direct search without interactive selection
            result = await search_music_auto_first(listener, query, platform)
        else:
            # Regular interactive search
            result = await search_music(listener, query, platform)

        if not result:
            return  # Search was cancelled or failed

        # Start download with selected result
        url = result["url"]
        platform = result["platform"]
        media_type = result["type"]

        # Show quality selector
        selection = await show_quality_selector(listener, platform, media_type)
        if not selection:
            return  # User cancelled or timeout

        quality = selection["quality"]
        codec = selection["codec"]

        # Delete original command message and replied message instantly before starting download
        try:
            from bot.helper.telegram_helper.message_utils import delete_message

            await delete_message(message)
            if message.reply_to_message:
                await delete_message(message.reply_to_message)
        except Exception as e:
            LOGGER.debug(f"Failed to delete command messages: {e}")

        # Start download (search results don't support force flag currently)
        await add_streamrip_download(listener, url, quality, codec, False)


# Export command functions for handlers.py
streamrip_mirror = StreamripCommands.streamrip_mirror
streamrip_leech = StreamripCommands.streamrip_leech
streamrip_search = StreamripCommands.streamrip_search
