"""
ReelNN File-to-Link Module
Exact implementation matching ReelNN's backend architecture
"""

import asyncio
import contextlib
import os
import re
import time
from datetime import datetime

import httpx
from pyrogram import filters
from pyrogram.enums import ParseMode
from pyrogram.handlers import MessageHandler
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import LOGGER
from bot.core.aeon_client import TgClient
from bot.core.config_manager import Config
from bot.helper.aeon_utils.access_check import error_check
from bot.helper.ext_utils.bot_utils import new_task
from bot.helper.ext_utils.db_handler import ensure_database_and_config
from bot.helper.stream_utils import (
    CacheManager,
    ConfigValidator,
    DCChecker,
    FileProcessor,
    LinkGenerator,
    LoadBalancer,
    SecurityHandler,
    SystemMonitor,
)
from bot.helper.stream_utils.quality_handler import QualityHandler
from bot.helper.stream_utils.tmdb_helper import TMDBHelper
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.message_utils import (
    delete_message,
    send_message,
)


class FileToLinkHandler:
    """
    ReelNN File-to-Link Handler
    Exact implementation matching ReelNN's backend processing pipeline
    """

    # Class-level caches for performance optimization
    _rate_limiter = {}
    _processing_cache = {}
    _last_cleanup = time.time()

    def __init__(self):
        self.active_sessions = {}
        self.processing_queue = asyncio.Queue()
        self.tmdb_helper = TMDBHelper()

    @staticmethod
    async def handle_file_message(client, message: Message):
        """
        Main entry point for file processing - ReelNN style
        Handles the complete pipeline from message to database storage
        """
        try:
            # Rate limiting check - ReelNN style
            user_id = message.from_user.id
            current_time = time.time()

            # Initialize rate limiter for user if not exists
            if user_id not in FileToLinkHandler._rate_limiter:
                FileToLinkHandler._rate_limiter[user_id] = []

            # Clean old entries (older than 1 minute)
            FileToLinkHandler._rate_limiter[user_id] = [
                timestamp
                for timestamp in FileToLinkHandler._rate_limiter[user_id]
                if current_time - timestamp < 60
            ]

            # Check rate limit (max 10 requests per minute) - ReelNN standard
            if len(FileToLinkHandler._rate_limiter[user_id]) >= 10:
                await message.reply_text(
                    "⚠️ **Rate limit exceeded!**\n\n"
                    "Please wait a moment before sending another file.\n"
                    "Maximum: 10 files per minute."
                )
                return

            # Add current request to rate limiter
            FileToLinkHandler._rate_limiter[user_id].append(current_time)

            # Process file using ReelNN pipeline
            await FileToLinkHandler.process_file_reelnn_style(client, message)

        except Exception as e:
            LOGGER.error(f"Error in handle_file_message: {e}")
            await message.reply_text(
                "❌ **Error processing file**\n\n"
                "An error occurred while processing your file. Please try again."
            )

    @staticmethod
    async def process_file_reelnn_style(client, message: Message):
        """
        Process file using ReelNN's exact processing pipeline
        """
        try:
            # Extract file information using ReelNN's FileProcessor
            file_info = FileProcessor.extract_file_info(message)
            if not file_info:
                await message.reply_text("❌ No valid file found in message")
                return

            # Generate secure links using ReelNN's LinkGenerator
            links = await LinkGenerator.generate_links(file_info, message)
            if not links:
                await message.reply_text("❌ Failed to generate file links")
                return

            # Extract ReelNN metadata using FileProcessor
            reelnn_metadata = await FileProcessor.extract_reelnn_metadata(
                message, file_info
            )

            # Store in database using ReelNN's exact schema
            await FileToLinkHandler._store_reelnn_metadata(
                file_info, links, message, reelnn_metadata
            )

            # Send response using ReelNN's format
            await FileToLinkHandler._send_reelnn_response(
                message, file_info, links, reelnn_metadata
            )

        except Exception as e:
            LOGGER.error(f"Error in process_file_reelnn_style: {e}")
            raise

    @staticmethod
    async def _store_reelnn_metadata(
        file_info: dict, links: dict, message: Message, metadata: dict
    ):
        """
        Store metadata using ReelNN's exact database schema
        """
        try:
            database = await ensure_database_and_config()
            if not database:
                LOGGER.warning("Database not available for metadata storage")
                return

            # Extract hash_id from links - ReelNN style
            hash_id = None
            if "download" in links:
                match = re.search(r"/([a-f0-9]+\d+)", links["download"])
                if match:
                    hash_id = match.group(1)

            if not hash_id:
                LOGGER.warning("Could not extract hash_id from links")
                return

            # Prepare ReelNN media data structure
            media_data = {
                # Core ReelNN fields
                "hash_id": hash_id,
                "mid": hash_id,  # ReelNN movie/show ID
                "file_name": file_info.get("file_name", ""),
                "enhanced_title": metadata.get(
                    "enhanced_title", file_info.get("file_name", "")
                ),
                "file_size": file_info.get("file_size", 0),
                "mime_type": file_info.get("mime_type", ""),
                "media_type": metadata.get("media_type", "movie"),
                "is_video": file_info.get("is_video", False),
                "is_streamable": file_info.get("is_streamable", False),
                # ReelNN URLs
                "download_url": links.get("download", ""),
                "stream_url": links.get("stream", ""),
                # TMDB data
                "tmdb_data": metadata.get("tmdb_data", {}),
                "year": metadata.get("year"),
                "quality": metadata.get("quality"),
                # ReelNN indexing
                "indexed_at": datetime.now(),
                "created_at": datetime.now(),
                "view_count": 0,
                "trending_score": 0,
                "featured": False,
                "active": True,
                # Telegram metadata
                "message_id": message.id,
                "chat_id": message.chat.id if message.chat else None,
                "uploader_id": message.from_user.id,
                "uploader_name": message.from_user.first_name or "Unknown",
            }

            # Add series data for TV shows
            if metadata.get("is_series"):
                media_data["series_data"] = {
                    "series_name": metadata.get("unique_name")
                    or metadata.get("enhanced_title"),
                    "season_number": metadata.get("season"),
                    "episode_number": metadata.get("episode"),
                    "media_type": "tv",
                }

            # Store in database
            await database.store_media_metadata(media_data)
            LOGGER.info(f"✅ Stored ReelNN metadata for: {hash_id}")

        except Exception as e:
            LOGGER.error(f"Error storing ReelNN metadata: {e}")

    @staticmethod
    async def _send_reelnn_response(
        message: Message, file_info: dict, links: dict, metadata: dict
    ):
        """
        Send response using ReelNN's exact format and styling
        """
        try:
            # Generate ReelNN-style response text
            title = metadata.get(
                "enhanced_title", file_info.get("file_name", "Unknown")
            )
            file_size = file_info.get("file_size_human", "Unknown")
            media_type = metadata.get("media_type", "movie").title()

            text = f"🎬 **{title}**\n\n"
            text += f"📁 **Size:** {file_size}\n"
            text += f"🎭 **Type:** {media_type}\n"

            # Add TMDB info if available
            tmdb_data = metadata.get("tmdb_data", {})
            if tmdb_data:
                if tmdb_data.get("release_date") or tmdb_data.get("first_air_date"):
                    year = (
                        tmdb_data.get("release_date")
                        or tmdb_data.get("first_air_date", "")
                    )[:4]
                    text += f"📅 **Year:** {year}\n"

                if tmdb_data.get("vote_average"):
                    rating = tmdb_data.get("vote_average")
                    text += f"⭐ **Rating:** {rating}/10\n"

            # Create ReelNN-style buttons
            buttons = []

            # Download button
            if "download" in links and LinkGenerator._is_valid_url(
                links["download"]
            ):
                buttons.append(
                    [InlineKeyboardButton("📥 Download", url=links["download"])]
                )

            # Stream button for videos
            if (
                "stream" in links
                and file_info.get("is_streamable")
                and LinkGenerator._is_valid_url(links["stream"])
            ):
                buttons.append(
                    [InlineKeyboardButton("🎬 Watch", url=links["stream"])]
                )

            keyboard = InlineKeyboardMarkup(buttons) if buttons else None

            # Send response
            await send_message(message, text, keyboard)

        except Exception as e:
            LOGGER.error(f"Error sending ReelNN response: {e}")

    @staticmethod
    async def _send_file_info_without_buttons(
        message, file_info, thumbnail_file_id, tracks_info, links=None
    ):
        """Send file information without buttons when URLs are invalid or localhost"""
        try:
            # Create file info text without buttons
            file_name = file_info.get("file_name", "Unknown")
            file_size = file_info.get("file_size", 0)
            file_type = file_info.get("file_type", "Unknown")

            # Format file size
            size_str = FileToLinkHandler._format_file_size(file_size)

            # Create track info text
            track_text = ""
            if tracks_info and not tracks_info.get("analysis_failed"):
                video_count = len(tracks_info.get("video_tracks", []))
                audio_count = len(tracks_info.get("audio_tracks", []))
                subtitle_count = len(tracks_info.get("subtitle_tracks", []))
                track_text = f"\n\n📊 **Track Info:**\n🎬 Video: {video_count}\n🎵 Audio: {audio_count}\n📝 Subtitles: {subtitle_count}"

            # Create message text
            text = "📁 **File Information**\n\n"
            text += f"📄 **Name:** `{file_name}`\n"
            text += f"📏 **Size:** {size_str}\n"
            text += f"🗂️ **Type:** {file_type}"
            text += track_text

            # Add direct URLs if available (for localhost/VPS deployments)
            if links:
                text += "\n\n🔗 **Direct Access URLs:**\n"
                if "download" in links:
                    text += f"📥 **Download:** `{links['download']}`\n"
                if "stream" in links:
                    text += f"🎬 **Stream:** `{links['stream']}`\n"
                text += "\n💡 **Note:** Copy and paste these URLs in your browser for direct access."
            else:
                text += "\n\n⚠️ **Note:** Streaming links are temporarily unavailable due to server configuration."

            # Send message with thumbnail if available
            if thumbnail_file_id and thumbnail_file_id not in [
                "auto_extract_video",
                "auto_extract_audio",
                "default_image",
                "default_document",
            ]:
                try:
                    await message.reply_photo(
                        photo=thumbnail_file_id,
                        caption=text,
                        parse_mode=ParseMode.MARKDOWN,
                    )
                except Exception as thumb_error:
                    LOGGER.warning(
                        f"Failed to send with thumbnail ({thumb_error}), sending as text"
                    )
                    await message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
            else:
                await message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

            LOGGER.info(
                f"Sent file info without buttons for {file_info.get('hash_id', 'unknown')}"
            )

        except Exception as e:
            LOGGER.error(f"Error sending file info without buttons: {e}")
            await message.reply_text(
                "❌ File processed but unable to generate streaming links."
            )

    @staticmethod
    def _format_file_size(size_bytes: int) -> str:
        """Format file size in human readable format"""
        try:
            if size_bytes == 0:
                return "0 B"

            size_names = ["B", "KB", "MB", "GB", "TB"]
            i = 0
            while size_bytes >= 1024 and i < len(size_names) - 1:
                size_bytes /= 1024.0
                i += 1

            return f"{size_bytes:.1f} {size_names[i]}"
        except (ValueError, TypeError):
            return "Unknown"

    @staticmethod
    async def process_file_to_link(
        client,
        message: Message,
        category: str | None = None,
        quality: str | None = None,
        season: str | None = None,
        episode: str | None = None,
        unique_name: str | None = None,
    ):
        """Process file and generate links with enhanced metadata support"""
        try:
            if not Config.FILE_TO_LINK_ENABLED:
                await send_message(
                    message, "❌ File-to-Link functionality is disabled."
                )
                return

            # Check rate limiting
            if not SecurityHandler.check_rate_limit(message.from_user.id):
                await send_message(
                    message, "⚠️ Rate limit exceeded. Please try again later."
                )
                return

            # Extract file information
            file_info = FileProcessor.extract_file_info(message)
            if not file_info:
                await send_message(
                    message, "❌ No supported file found in the message."
                )
                return

            # Validate media file if it's a video or audio file
            if file_info.get("is_video") or file_info.get("is_audio"):
                # For Telegram files, we can't validate directly, but we can check basic properties
                file_size = file_info.get("file_size", 0)
                duration = file_info.get("duration", 0)

                # Basic validation checks
                if file_size < 1024:  # Less than 1KB
                    await send_message(
                        message, "❌ File too small, likely corrupted or incomplete."
                    )
                    return

                if file_info.get("is_video") and duration == 0:
                    await send_message(
                        message,
                        "⚠️ Warning: Video file has no duration information. It may be corrupted.",
                    )
                    # Continue processing but warn user

                if file_info.get("is_audio") and duration == 0:
                    await send_message(
                        message,
                        "⚠️ Warning: Audio file has no duration information. It may be corrupted.",
                    )
                    # Continue processing but warn user

            # Check if file is already cached
            cached_links = CacheManager.get_cached_links(file_info["file_id"])
            if cached_links:
                await FileToLinkHandler._send_links_response(
                    message, file_info, cached_links
                )
                return

            # Send processing message
            processing_msg = await send_message(
                message, "🔄 Processing file and generating links..."
            )

            try:
                # ReelNN: Use STREAM_CHATS for media storage (separate from leech dump)
                stream_chats = (
                    getattr(Config, "STREAM_CHATS", None) or Config.LEECH_DUMP_CHAT
                )
                if not stream_chats:
                    await send_message(
                        message,
                        "❌ Stream chats not configured. Please contact admin.",
                    )
                    return

                # Handle STREAM_CHATS as list - get first valid chat ID
                target_chat_id = None
                if isinstance(stream_chats, list):
                    for chat_id in stream_chats:
                        # Extract actual chat ID from prefixed format (b:, u:, h:)
                        processed_chat_id = str(chat_id)
                        if ":" in processed_chat_id:
                            processed_chat_id = processed_chat_id.split(":", 1)[1]
                        if "|" in processed_chat_id:
                            processed_chat_id = processed_chat_id.split("|", 1)[0]

                        try:
                            target_chat_id = int(processed_chat_id)
                            break  # Use first valid chat ID
                        except (ValueError, TypeError):
                            continue
                else:
                    # Handle legacy single chat ID format
                    with contextlib.suppress(ValueError, TypeError):
                        target_chat_id = int(stream_chats)

                if not target_chat_id:
                    await send_message(
                        message,
                        "❌ No valid stream chat configured. Please contact admin.",
                    )
                    return

                # Get optimal client for copying using unified load balancer
                client_id, optimal_client = LoadBalancer.get_optimal_client()
                if not optimal_client:
                    await send_message(
                        message, "❌ No available clients for processing."
                    )
                    return

                LoadBalancer.increment_load(client_id)

                try:
                    # Copy media using regular copy (simpler and more reliable)
                    copied_msg = await message.copy(target_chat_id)

                    if not copied_msg:
                        await send_message(
                            message, "❌ Failed to copy media to dump chat."
                        )
                        return

                    # Generate secure links with validation
                    links = LinkGenerator.generate_links(file_info, copied_msg.id)

                    if not links:
                        await send_message(message, "❌ Failed to generate links.")
                        return

                    # Move localhost check after thumbnail processing to avoid undefined variables

                    # Validate non-localhost URLs
                    valid_links = {}
                    for link_type, url in links.items():
                        LOGGER.info(f"🔍 Validating {link_type} URL: {url}")
                        if LinkGenerator._is_valid_url(url):
                            valid_links[link_type] = url
                            LOGGER.info(f"✅ Valid {link_type} URL: {url}")
                        else:
                            LOGGER.warning(
                                f"❌ Invalid {link_type} URL generated: {url}"
                            )

                    if not valid_links:
                        LOGGER.error(
                            f"❌ No valid URLs generated. Original links: {links}"
                        )
                        LOGGER.warning(
                            "⚠️ BASE_URL may not be properly configured. Sending file info without buttons."
                        )
                        # Send file info without buttons when URLs are invalid
                        fallback_thumbnail = None
                        fallback_tracks = {
                            "analysis_failed": True,
                            "reason": "URL validation failed",
                        }
                        await FileToLinkHandler._send_file_info_without_buttons(
                            message, file_info, fallback_thumbnail, fallback_tracks
                        )
                        return

                    # Use validated links
                    links = valid_links
                    LOGGER.info(f"✅ Using validated links: {links}")

                    # Check if URLs contain localhost (which Telegram buttons don't support)
                    has_localhost = any(
                        "localhost" in url or "127.0.0.1" in url
                        for url in links.values()
                    )

                    if has_localhost:
                        LOGGER.info(
                            "🏠 Localhost URLs detected - sending file info without buttons (VPS deployment)"
                        )
                        # Need to get tracks info first (thumbnail extraction removed)
                        file_info.get("hash_id") or file_info.get(
                            "file_id", "unknown"
                        )[:6]
                        thumbnail_file_id = None  # Thumbnail extraction removed
                        tracks_info = await FileToLinkHandler._extract_tracks_from_telegram_metadata(
                            copied_msg, file_info
                        )
                        # Send file info without buttons for localhost URLs (VPS deployment)
                        await FileToLinkHandler._send_file_info_without_buttons(
                            message, file_info, thumbnail_file_id, tracks_info, links
                        )
                        return

                    # Cache the generated links efficiently
                    CacheManager.cache_file_info(file_info["file_id"], file_info)
                    CacheManager.cache_generated_links(file_info["file_id"], links)

                    # NEW PIPELINE: Full media processing with automatic extraction
                    # Use basic file-to-link without custom thumbnails
                    LOGGER.info(
                        f"📋 Using basic file-to-link for: {file_info.get('file_name', 'unknown')}"
                    )

                    # Store media metadata in database for streaming website with quality processing
                    await FileToLinkHandler._store_media_metadata(
                        file_info,
                        links,
                        copied_msg.id,
                        target_chat_id,
                        message.from_user,
                        category,
                        optimal_client,
                        quality,
                        season,
                        episode,
                        unique_name,
                        copied_msg,
                    )

                    # Update user data in database (using unified database access)
                    try:
                        database = await ensure_database_and_config()
                        if database:
                            await database.update_pm_users(message.from_user.id)
                    except Exception as db_error:
                        LOGGER.warning(f"Failed to update user data: {db_error}")
                        # Continue processing even if user update fails

                    # Send response with links
                    await FileToLinkHandler._send_links_response(
                        message, file_info, links
                    )

                finally:
                    LoadBalancer.decrement_load(client_id)

            finally:
                await delete_message(processing_msg)

        except Exception as e:
            LOGGER.error(f"Error in file-to-link processing: {e}")
            await send_message(message, f"❌ Error processing file: {e!s}")

    @staticmethod
    async def _extract_tracks_from_telegram_metadata(
        message: Message, file_info: dict
    ) -> dict:
        """Extract comprehensive track information from Telegram's built-in metadata including subtitles"""
        try:
            tracks_info = {
                "video_tracks": [],
                "audio_tracks": [],
                "subtitle_tracks": [],
                "attachment_tracks": [],
            }

            # Extract from video metadata
            if message.video and file_info.get("is_video"):
                # Primary video track
                video_track = {
                    "index": 0,
                    "id": "video_0",  # Add unique ID for frontend
                    "codec_name": "unknown",
                    "language": "und",
                    "title": "",
                    "default": True,
                    "forced": False,
                    "width": message.video.width or 0,
                    "height": message.video.height or 0,
                    "fps": "unknown",
                    "bitrate": None,
                }
                tracks_info["video_tracks"].append(video_track)

                # Primary audio track
                audio_track = {
                    "index": 1,
                    "id": "audio_0",  # Add unique ID for frontend
                    "codec_name": "unknown",
                    "language": "und",
                    "title": "",
                    "default": True,
                    "forced": False,
                    "channels": 2,  # Assume stereo
                    "sample_rate": None,
                    "bitrate": None,
                }
                tracks_info["audio_tracks"].append(audio_track)

                # Check for common subtitle patterns in filename
                filename = file_info.get("file_name", "").lower()
                subtitle_languages = (
                    FileToLinkHandler._detect_subtitle_languages_from_filename(
                        filename
                    )
                )

                # Add detected subtitle tracks
                for i, lang_info in enumerate(subtitle_languages):
                    subtitle_track = {
                        "index": i + 2,  # Start after video and audio
                        "id": f"sub_{i}",  # Add unique ID for frontend
                        "codec_name": "subrip",  # Most common subtitle format
                        "language": lang_info["code"],
                        "title": lang_info["name"],
                        "default": i == 0,  # First subtitle is default
                        "forced": lang_info.get("forced", False),
                    }
                    tracks_info["subtitle_tracks"].append(subtitle_track)

                # If no subtitles detected from filename, add common defaults for movies/shows
                if not tracks_info[
                    "subtitle_tracks"
                ] and FileToLinkHandler._is_likely_movie_or_show(filename):
                    # Add common subtitle languages for international content
                    common_subs = [
                        {"code": "eng", "name": "English", "forced": False},
                        {"code": "und", "name": "Unknown", "forced": False},
                    ]
                    for i, sub_info in enumerate(common_subs):
                        subtitle_track = {
                            "index": i + 2,
                            "codec_name": "subrip",
                            "language": sub_info["code"],
                            "title": sub_info["name"],
                            "default": i == 0,
                            "forced": sub_info["forced"],
                        }
                        tracks_info["subtitle_tracks"].append(subtitle_track)

            # Extract from audio metadata
            elif message.audio and file_info.get("is_audio"):
                audio_track = {
                    "index": 0,
                    "id": "audio_0",  # Add unique ID for frontend
                    "codec_name": "unknown",
                    "language": "und",
                    "title": message.audio.title or "",
                    "default": True,
                    "forced": False,
                    "channels": 2,  # Assume stereo
                    "sample_rate": None,
                    "bitrate": None,
                }
                tracks_info["audio_tracks"].append(audio_track)

            # Extract from voice metadata
            elif message.voice and file_info.get("is_audio"):
                audio_track = {
                    "index": 0,
                    "id": "audio_0",  # Add unique ID for frontend
                    "codec_name": "opus",  # Voice messages are usually opus
                    "language": "und",
                    "title": "",
                    "default": True,
                    "forced": False,
                    "channels": 1,  # Voice is usually mono
                    "sample_rate": 48000,  # Opus standard
                    "bitrate": None,
                }
                tracks_info["audio_tracks"].append(audio_track)

            # Extract from document metadata (could be video/audio files)
            elif message.document and (
                file_info.get("is_video") or file_info.get("is_audio")
            ):
                # Handle documents that are actually media files
                if file_info.get("is_video"):
                    # Add basic video track
                    video_track = {
                        "index": 0,
                        "id": "video_0",  # Add unique ID for frontend
                        "codec_name": "unknown",
                        "language": "und",
                        "title": "",
                        "default": True,
                        "forced": False,
                        "width": 0,
                        "height": 0,
                        "fps": "unknown",
                        "bitrate": None,
                    }
                    tracks_info["video_tracks"].append(video_track)

                    # Add basic audio track
                    audio_track = {
                        "index": 1,
                        "id": "audio_0",  # Add unique ID for frontend
                        "codec_name": "unknown",
                        "language": "und",
                        "title": "",
                        "default": True,
                        "forced": False,
                        "channels": 2,
                        "sample_rate": None,
                        "bitrate": None,
                    }
                    tracks_info["audio_tracks"].append(audio_track)

                    # Check for subtitles in filename
                    filename = file_info.get("file_name", "").lower()
                    subtitle_languages = (
                        FileToLinkHandler._detect_subtitle_languages_from_filename(
                            filename
                        )
                    )

                    for i, lang_info in enumerate(subtitle_languages):
                        subtitle_track = {
                            "index": i + 2,
                            "id": f"sub_{i}",  # Add unique ID for frontend
                            "codec_name": "subrip",
                            "language": lang_info["code"],
                            "title": lang_info["name"],
                            "default": i == 0,
                            "forced": lang_info.get("forced", False),
                        }
                        tracks_info["subtitle_tracks"].append(subtitle_track)

                elif file_info.get("is_audio"):
                    # Add basic audio track for document audio files
                    audio_track = {
                        "index": 0,
                        "id": "audio_0",  # Add unique ID for frontend
                        "codec_name": "unknown",
                        "language": "und",
                        "title": file_info.get("file_name", ""),
                        "default": True,
                        "forced": False,
                        "channels": 2,
                        "sample_rate": None,
                        "bitrate": None,
                    }
                    tracks_info["audio_tracks"].append(audio_track)

            # Check if we got useful track info
            total_tracks = (
                len(tracks_info["video_tracks"])
                + len(tracks_info["audio_tracks"])
                + len(tracks_info["subtitle_tracks"])
            )

            if total_tracks > 0:
                LOGGER.info(
                    f"📊 Extracted {total_tracks} tracks from Telegram metadata ({len(tracks_info['video_tracks'])} video, {len(tracks_info['audio_tracks'])} audio, {len(tracks_info['subtitle_tracks'])} subtitle)"
                )
                return tracks_info
            return {
                "analysis_failed": True,
                "reason": "No tracks found in Telegram metadata",
            }

        except Exception as e:
            LOGGER.warning(f"Error extracting tracks from Telegram metadata: {e}")
            return {"analysis_failed": True, "error": str(e)}

    @staticmethod
    def _detect_subtitle_languages_from_filename(filename: str) -> list:
        """Detect subtitle languages from filename patterns - optimized"""
        try:
            if not filename:
                return []

            filename_lower = filename.lower()

            # Simplified common language patterns
            common_languages = {
                "eng": ["eng", "english", "en"],
                "spa": ["spa", "spanish", "es"],
                "fre": ["fre", "french", "fr"],
                "ger": ["ger", "german", "de"],
                "ita": ["ita", "italian", "it"],
                "jpn": ["jpn", "japanese", "ja"],
                "chi": ["chi", "chinese", "zh"],
                "ara": ["ara", "arabic", "ar"],
                "rus": ["rus", "russian", "ru"],
                "hin": ["hin", "hindi", "hi"],
            }

            lang_names = {
                "eng": "English",
                "spa": "Spanish",
                "fre": "French",
                "ger": "German",
                "ita": "Italian",
                "jpn": "Japanese",
                "chi": "Chinese",
                "ara": "Arabic",
                "rus": "Russian",
                "hin": "Hindi",
            }

            subtitle_languages = []
            forced_indicators = ["forced", "sdh", "cc", "hi"]

            # Check for language patterns
            for lang_code, patterns in common_languages.items():
                if any(pattern in filename_lower for pattern in patterns):
                    is_forced = any(
                        forced in filename_lower for forced in forced_indicators
                    )
                    subtitle_languages.append(
                        {
                            "code": lang_code,
                            "name": lang_names.get(lang_code, lang_code.upper()),
                            "forced": is_forced,
                        }
                    )
                    break  # Only detect first match

            # Default fallback
            if not subtitle_languages:
                subtitle_indicators = ["sub", "srt", "ass", "vtt", "subtitle"]
                if any(
                    indicator in filename_lower for indicator in subtitle_indicators
                ):
                    subtitle_languages.append(
                        {"code": "eng", "name": "English", "forced": False}
                    )

            return subtitle_languages

        except Exception as e:
            LOGGER.warning(f"Error detecting subtitle languages: {e}")
            return []

    @staticmethod
    def _is_likely_movie_or_show(filename: str) -> bool:
        """Check if filename suggests it's a movie or TV show that likely has subtitles"""
        try:
            if not filename:
                return False

            filename_lower = filename.lower()

            # Movie/show indicators
            movie_indicators = [
                # Quality indicators
                "1080p",
                "720p",
                "480p",
                "4k",
                "uhd",
                "hd",
                "bluray",
                "brrip",
                "webrip",
                "webdl",
                # Release group indicators
                "yify",
                "rarbg",
                "eztv",
                "ettv",
                "torrent",
                "x264",
                "x265",
                "hevc",
                # Format indicators
                "mkv",
                "mp4",
                "avi",
                "mov",
                "wmv",
                # Series indicators
                "s01",
                "s02",
                "s03",
                "s04",
                "s05",
                "season",
                "episode",
                "e01",
                "e02",
                "e03",
                # Movie indicators
                "2020",
                "2021",
                "2022",
                "2023",
                "2024",
                "2025",
                "movie",
                "film",
            ]

            return any(indicator in filename_lower for indicator in movie_indicators)

        except Exception as e:
            LOGGER.warning(f"Error checking if filename is movie/show: {e}")
            return False

    @staticmethod
    async def _send_links_response(message: Message, file_info: dict, links: dict):
        """Send formatted response with generated links"""
        try:
            # Generate share text
            share_text = LinkGenerator.generate_share_text(file_info, links)

            # Create inline keyboard
            buttons = []

            # Validate URLs before creating buttons
            if "download" in links and LinkGenerator._is_valid_url(
                links["download"]
            ):
                buttons.append(
                    [InlineKeyboardButton("📥 Download", url=links["download"])]
                )
            elif "download" in links:
                LOGGER.warning(f"❌ Invalid download URL: {links['download']}")

            if (
                "stream" in links
                and file_info.get("is_streamable")
                and LinkGenerator._is_valid_url(links["stream"])
            ):
                buttons.append(
                    [InlineKeyboardButton("🎬 Stream/Watch", url=links["stream"])]
                )
            elif "stream" in links and file_info.get("is_streamable"):
                LOGGER.warning(f"❌ Invalid stream URL: {links['stream']}")

            # Add user DC info button
            dc_info = DCChecker.get_user_dc_info(message.from_user)
            if dc_info.get("dc_id"):
                dc_text = f"📍 Your DC: {dc_info['dc_id']} ({dc_info['location']})"
                buttons.append(
                    [InlineKeyboardButton(dc_text, callback_data="dc_info")]
                )

            keyboard = InlineKeyboardMarkup(buttons) if buttons else None

            # Send response
            await send_message(message, share_text, keyboard)

            # Cache user DC info
            DCChecker.cache_user_dc(message.from_user.id, dc_info)

        except Exception as e:
            LOGGER.error(f"Error sending links response: {e}")
            await send_message(message, "❌ Error sending response.")

    @staticmethod
    async def _get_comprehensive_media_info(
        file_path: str, file_info: dict, telegram_message=None
    ) -> dict:
        """Get comprehensive media information using FFprobe as primary, Telegram metadata as fallback"""
        try:
            import asyncio
            import json
            # Removed unused subprocess import

            comprehensive_info = {
                "source": "unknown",
                "format": {},
                "streams": [],
                "chapters": [],
                "video_streams": [],
                "audio_streams": [],
                "subtitle_streams": [],
                "attachment_streams": [],
                "metadata": {},
                "technical_info": {},
                "telegram_fallback": {},
            }

            # PRIMARY: Use FFprobe for detailed analysis
            try:
                LOGGER.info("🔍 Using FFprobe for comprehensive media analysis...")

                # Run ffprobe to get comprehensive JSON output
                ffprobe_cmd = [
                    "ffprobe",
                    "-v",
                    "quiet",
                    "-print_format",
                    "json",
                    "-show_format",
                    "-show_streams",
                    "-show_chapters",
                    "-show_entries",
                    "format:stream:chapter",
                    file_path,
                ]

                # Execute ffprobe with timeout
                process = await asyncio.create_subprocess_exec(
                    *ffprobe_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=30.0
                )

                if process.returncode == 0 and stdout:
                    ffprobe_data = json.loads(stdout.decode("utf-8"))

                    # Extract format information
                    if "format" in ffprobe_data:
                        format_info = ffprobe_data["format"]
                        comprehensive_info["format"] = {
                            "filename": format_info.get("filename", ""),
                            "nb_streams": int(format_info.get("nb_streams", 0)),
                            "nb_programs": int(format_info.get("nb_programs", 0)),
                            "format_name": format_info.get("format_name", ""),
                            "format_long_name": format_info.get(
                                "format_long_name", ""
                            ),
                            "start_time": float(format_info.get("start_time", 0.0)),
                            "duration": float(format_info.get("duration", 0.0)),
                            "size": int(format_info.get("size", 0)),
                            "bit_rate": int(format_info.get("bit_rate", 0))
                            if format_info.get("bit_rate")
                            else 0,
                            "probe_score": int(format_info.get("probe_score", 0)),
                            "tags": format_info.get("tags", {}),
                        }

                    # Extract stream information
                    if "streams" in ffprobe_data:
                        for stream in ffprobe_data["streams"]:
                            stream_info = {
                                "index": stream.get("index", 0),
                                "codec_name": stream.get("codec_name", ""),
                                "codec_long_name": stream.get("codec_long_name", ""),
                                "codec_type": stream.get("codec_type", ""),
                                "codec_tag_string": stream.get(
                                    "codec_tag_string", ""
                                ),
                                "codec_tag": stream.get("codec_tag", ""),
                                "profile": stream.get("profile", ""),
                                "level": stream.get("level", ""),
                                "time_base": stream.get("time_base", ""),
                                "start_pts": stream.get("start_pts", 0),
                                "start_time": float(stream.get("start_time", 0.0)),
                                "duration_ts": stream.get("duration_ts", 0),
                                "duration": float(stream.get("duration", 0.0)),
                                "bit_rate": int(stream.get("bit_rate", 0))
                                if stream.get("bit_rate")
                                else 0,
                                "nb_frames": int(stream.get("nb_frames", 0))
                                if stream.get("nb_frames")
                                else 0,
                                "disposition": stream.get("disposition", {}),
                                "tags": stream.get("tags", {}),
                            }

                            # Add codec-specific information
                            if stream.get("codec_type") == "video":
                                stream_info.update(
                                    {
                                        "width": stream.get("width", 0),
                                        "height": stream.get("height", 0),
                                        "coded_width": stream.get("coded_width", 0),
                                        "coded_height": stream.get(
                                            "coded_height", 0
                                        ),
                                        "sample_aspect_ratio": stream.get(
                                            "sample_aspect_ratio", ""
                                        ),
                                        "display_aspect_ratio": stream.get(
                                            "display_aspect_ratio", ""
                                        ),
                                        "pix_fmt": stream.get("pix_fmt", ""),
                                        "field_order": stream.get("field_order", ""),
                                        "color_range": stream.get("color_range", ""),
                                        "color_space": stream.get("color_space", ""),
                                        "color_transfer": stream.get(
                                            "color_transfer", ""
                                        ),
                                        "color_primaries": stream.get(
                                            "color_primaries", ""
                                        ),
                                        "refs": stream.get("refs", 0),
                                        "r_frame_rate": stream.get(
                                            "r_frame_rate", ""
                                        ),
                                        "avg_frame_rate": stream.get(
                                            "avg_frame_rate", ""
                                        ),
                                    }
                                )
                                comprehensive_info["video_streams"].append(
                                    stream_info
                                )

                            elif stream.get("codec_type") == "audio":
                                stream_info.update(
                                    {
                                        "sample_fmt": stream.get("sample_fmt", ""),
                                        "sample_rate": int(
                                            stream.get("sample_rate", 0)
                                        )
                                        if stream.get("sample_rate")
                                        else 0,
                                        "channels": stream.get("channels", 0),
                                        "channel_layout": stream.get(
                                            "channel_layout", ""
                                        ),
                                        "bits_per_sample": stream.get(
                                            "bits_per_sample", 0
                                        ),
                                    }
                                )
                                comprehensive_info["audio_streams"].append(
                                    stream_info
                                )

                            elif stream.get("codec_type") == "subtitle":
                                comprehensive_info["subtitle_streams"].append(
                                    stream_info
                                )

                            elif stream.get("codec_type") == "attachment":
                                stream_info.update(
                                    {
                                        "filename": stream.get("tags", {}).get(
                                            "filename", ""
                                        ),
                                        "mimetype": stream.get("tags", {}).get(
                                            "mimetype", ""
                                        ),
                                    }
                                )
                                comprehensive_info["attachment_streams"].append(
                                    stream_info
                                )

                            comprehensive_info["streams"].append(stream_info)

                    # Extract chapters
                    if "chapters" in ffprobe_data:
                        comprehensive_info["chapters"] = ffprobe_data["chapters"]

                    # Extract global metadata
                    comprehensive_info["metadata"] = comprehensive_info[
                        "format"
                    ].get("tags", {})

                    # Technical summary
                    comprehensive_info["technical_info"] = {
                        "total_streams": len(comprehensive_info["streams"]),
                        "video_stream_count": len(
                            comprehensive_info["video_streams"]
                        ),
                        "audio_stream_count": len(
                            comprehensive_info["audio_streams"]
                        ),
                        "subtitle_stream_count": len(
                            comprehensive_info["subtitle_streams"]
                        ),
                        "attachment_stream_count": len(
                            comprehensive_info["attachment_streams"]
                        ),
                        "has_chapters": len(comprehensive_info["chapters"]) > 0,
                        "primary_video_codec": comprehensive_info["video_streams"][
                            0
                        ]["codec_name"]
                        if comprehensive_info["video_streams"]
                        else None,
                        "primary_audio_codec": comprehensive_info["audio_streams"][
                            0
                        ]["codec_name"]
                        if comprehensive_info["audio_streams"]
                        else None,
                        "container_format": comprehensive_info["format"].get(
                            "format_name", ""
                        ),
                        "total_duration": comprehensive_info["format"].get(
                            "duration", 0.0
                        ),
                        "total_bitrate": comprehensive_info["format"].get(
                            "bit_rate", 0
                        ),
                        "file_size": comprehensive_info["format"].get("size", 0),
                    }

                    comprehensive_info["source"] = "ffprobe_primary"
                    LOGGER.info(
                        f"✅ FFprobe analysis successful: {comprehensive_info['technical_info']['total_streams']} streams found"
                    )

                else:
                    LOGGER.warning(
                        f"FFprobe failed with return code {process.returncode}: {stderr.decode() if stderr else 'No error output'}"
                    )
                    raise Exception("FFprobe analysis failed")

            except Exception as ffprobe_error:
                LOGGER.warning(f"FFprobe analysis failed: {ffprobe_error}")

                # FALLBACK: Use Telegram metadata
                LOGGER.info("🔄 Falling back to Telegram metadata extraction...")
                try:
                    telegram_info = await FileToLinkHandler._extract_tracks_from_telegram_metadata(
                        telegram_message, file_info
                    )

                    # Convert Telegram metadata to comprehensive format
                    comprehensive_info["telegram_fallback"] = telegram_info
                    comprehensive_info["source"] = "telegram_fallback"

                    # Basic format info from file_info
                    comprehensive_info["format"] = {
                        "filename": file_info.get("file_name", ""),
                        "duration": file_info.get("duration", 0.0),
                        "size": file_info.get("file_size", 0),
                        "format_name": "unknown",
                    }

                    # Convert Telegram tracks to stream format
                    stream_index = 0
                    for video_track in telegram_info.get("video_tracks", []):
                        stream_info = {
                            "index": stream_index,
                            "codec_type": "video",
                            "codec_name": "unknown",
                            "width": video_track.get("width", 0),
                            "height": video_track.get("height", 0),
                            "duration": file_info.get("duration", 0.0),
                        }
                        comprehensive_info["video_streams"].append(stream_info)
                        comprehensive_info["streams"].append(stream_info)
                        stream_index += 1

                    for _ in telegram_info.get("audio_tracks", []):
                        stream_info = {
                            "index": stream_index,
                            "codec_type": "audio",
                            "codec_name": "unknown",
                            "duration": file_info.get("duration", 0.0),
                        }
                        comprehensive_info["audio_streams"].append(stream_info)
                        comprehensive_info["streams"].append(stream_info)
                        stream_index += 1

                    for subtitle_track in telegram_info.get("subtitle_tracks", []):
                        stream_info = {
                            "index": stream_index,
                            "codec_type": "subtitle",
                            "codec_name": "unknown",
                            "tags": {
                                "language": subtitle_track.get("language", "und")
                            },
                        }
                        comprehensive_info["subtitle_streams"].append(stream_info)
                        comprehensive_info["streams"].append(stream_info)
                        stream_index += 1

                    comprehensive_info["technical_info"] = {
                        "total_streams": len(comprehensive_info["streams"]),
                        "video_stream_count": len(
                            comprehensive_info["video_streams"]
                        ),
                        "audio_stream_count": len(
                            comprehensive_info["audio_streams"]
                        ),
                        "subtitle_stream_count": len(
                            comprehensive_info["subtitle_streams"]
                        ),
                        "attachment_stream_count": 0,
                        "has_chapters": False,
                        "primary_video_codec": "unknown",
                        "primary_audio_codec": "unknown",
                        "container_format": "unknown",
                        "total_duration": file_info.get("duration", 0.0),
                        "total_bitrate": 0,
                        "file_size": file_info.get("file_size", 0),
                    }

                    LOGGER.info(
                        f"✅ Telegram metadata fallback successful: {comprehensive_info['technical_info']['total_streams']} streams found"
                    )

                except Exception as telegram_error:
                    LOGGER.error(
                        f"Both FFprobe and Telegram metadata extraction failed: {telegram_error}"
                    )
                    comprehensive_info["source"] = "failed"
                    return None

            return comprehensive_info

        except Exception as e:
            LOGGER.error(f"Error in comprehensive media info extraction: {e}")
            return None

    @staticmethod
    async def _extract_comprehensive_metadata_ffprobe_REMOVED(
        copied_msg, file_info: dict, hash_id: str, client=None
    ) -> dict:
        """REMOVED: FFprobe analysis disabled to prevent file downloads"""
        LOGGER.info("FFprobe analysis disabled - using Telegram metadata only")
        return {"analysis_failed": True, "reason": "FFprobe disabled"}

        # Original FFprobe code removed to prevent file downloads
        try:
            import asyncio
            import tempfile

            from bot.core.aeon_client import TgClient

            # Use the provided client or fallback to TgClient.bot
            download_client = client if client else TgClient.bot
            if not download_client:
                LOGGER.error("No client available for FFprobe metadata extraction")
                return {"analysis_failed": True, "error": "No client available"}

            # Create temporary directory for file download
            with tempfile.TemporaryDirectory() as temp_dir:
                # Download the file temporarily for FFprobe analysis
                temp_file_path = f"{temp_dir}/media_temp"

                try:
                    # Download the file
                    LOGGER.info(
                        f"📥 Downloading file for FFprobe analysis: {hash_id}"
                    )
                    await asyncio.wait_for(
                        download_client.download_media(
                            copied_msg, file_name=temp_file_path
                        ),
                        timeout=300.0,  # 5 minutes timeout for download
                    )

                    # Check if file was downloaded successfully
                    if (
                        not os.path.exists(temp_file_path)
                        or os.path.getsize(temp_file_path) == 0
                    ):
                        LOGGER.warning(
                            f"File download failed for FFprobe analysis: {hash_id}"
                        )
                        return {"analysis_failed": True, "error": "Download failed"}

                    # Extract comprehensive metadata using FFprobe
                    LOGGER.info(f"🔍 Running FFprobe analysis for {hash_id}")
                    metadata = await FileToLinkHandler._run_ffprobe_analysis(
                        temp_file_path, hash_id
                    )

                    if metadata and not metadata.get("analysis_failed"):
                        LOGGER.info(f"✅ FFprobe analysis completed for {hash_id}")
                        return metadata
                    LOGGER.warning(f"FFprobe analysis failed for {hash_id}")
                    return {
                        "analysis_failed": True,
                        "error": "FFprobe analysis failed",
                    }

                except TimeoutError:
                    LOGGER.warning(
                        f"❌ Download timeout for FFprobe analysis: {hash_id}"
                    )
                    return {"analysis_failed": True, "error": "Download timeout"}
                except Exception as download_error:
                    LOGGER.warning(
                        f"❌ Error downloading file for FFprobe analysis: {download_error}"
                    )
                    return {"analysis_failed": True, "error": str(download_error)}

        except Exception as e:
            LOGGER.error(f"Error in FFprobe metadata extraction for {hash_id}: {e}")
            return {"analysis_failed": True, "error": str(e)}

    @staticmethod
    async def _run_ffprobe_analysis(file_path: str, hash_id: str) -> dict:
        """Run FFprobe analysis on the downloaded file"""
        try:
            import json

            from bot.helper.ext_utils.bot_utils import cmd_exec

            # FFprobe command to extract comprehensive metadata
            cmd = [
                "ffprobe",
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                "-show_chapters",
                file_path,
            ]

            # Run FFprobe
            stdout, stderr, return_code = await cmd_exec(cmd)

            if return_code != 0:
                LOGGER.error(f"FFprobe failed for {hash_id}: {stderr}")
                return {"analysis_failed": True, "error": f"FFprobe error: {stderr}"}

            # Parse FFprobe output
            try:
                ffprobe_data = json.loads(stdout)
            except json.JSONDecodeError as e:
                LOGGER.error(f"Failed to parse FFprobe JSON for {hash_id}: {e}")
                return {"analysis_failed": True, "error": "JSON parse error"}

            # Extract track information from FFprobe data
            tracks_info = FileToLinkHandler._parse_ffprobe_tracks(
                ffprobe_data, hash_id
            )

            # Extract comprehensive metadata
            comprehensive_metadata = {
                "tracks": tracks_info,
                "format": ffprobe_data.get("format", {}),
                "chapters": ffprobe_data.get("chapters", []),
                "source": "ffprobe",
                "analysis_success": True,
            }

            LOGGER.info(f"✅ FFprobe analysis successful for {hash_id}")
            return comprehensive_metadata

        except TimeoutError:
            LOGGER.warning(f"❌ FFprobe timeout for {hash_id}")
            return {"analysis_failed": True, "error": "FFprobe timeout"}
        except Exception as e:
            LOGGER.error(f"Error running FFprobe analysis for {hash_id}: {e}")
            return {"analysis_failed": True, "error": str(e)}

    @staticmethod
    def _parse_ffprobe_tracks(ffprobe_data: dict, hash_id: str) -> dict:
        """Parse FFprobe output to extract track information"""
        try:
            streams = ffprobe_data.get("streams", [])

            video_tracks = []
            audio_tracks = []
            subtitle_tracks = []
            attachment_tracks = []

            for stream in streams:
                codec_type = stream.get("codec_type", "").lower()

                if codec_type == "video":
                    track_index = stream.get("index", 0)
                    video_track = {
                        "id": track_index,  # Use index as ID for consistency
                        "index": track_index,
                        "codec_name": stream.get("codec_name", "unknown"),
                        "codec_long_name": stream.get("codec_long_name", "Unknown"),
                        "width": stream.get("width", 0),
                        "height": stream.get("height", 0),
                        "duration": float(stream.get("duration", 0)),
                        "bit_rate": stream.get("bit_rate"),
                        "frame_rate": stream.get("r_frame_rate", "0/0"),
                        "pixel_format": stream.get("pix_fmt"),
                        "default": stream.get("disposition", {}).get("default", 0)
                        == 1,
                        "title": stream.get("tags", {}).get("title", ""),
                        "language": stream.get("tags", {}).get("language", "und"),
                    }
                    video_tracks.append(video_track)

                elif codec_type == "audio":
                    track_index = stream.get("index", 0)
                    audio_track = {
                        "id": track_index,  # Use index as ID for consistency
                        "index": track_index,
                        "codec_name": stream.get("codec_name", "unknown"),
                        "codec_long_name": stream.get("codec_long_name", "Unknown"),
                        "channels": stream.get("channels", 0),
                        "channel_layout": stream.get("channel_layout", "unknown"),
                        "sample_rate": stream.get("sample_rate", 0),
                        "duration": float(stream.get("duration", 0)),
                        "bit_rate": stream.get("bit_rate"),
                        "default": stream.get("disposition", {}).get("default", 0)
                        == 1,
                        "title": stream.get("tags", {}).get("title", ""),
                        "language": stream.get("tags", {}).get("language", "und"),
                    }
                    audio_tracks.append(audio_track)

                elif codec_type == "subtitle":
                    track_index = stream.get("index", 0)
                    subtitle_track = {
                        "id": track_index,  # Use index as ID for consistency
                        "index": track_index,
                        "codec_name": stream.get("codec_name", "unknown"),
                        "codec_long_name": stream.get("codec_long_name", "Unknown"),
                        "default": stream.get("disposition", {}).get("default", 0)
                        == 1,
                        "forced": stream.get("disposition", {}).get("forced", 0)
                        == 1,
                        "title": stream.get("tags", {}).get("title", ""),
                        "language": stream.get("tags", {}).get("language", "und"),
                    }
                    subtitle_tracks.append(subtitle_track)

                elif codec_type == "attachment":
                    track_index = stream.get("index", 0)
                    attachment_track = {
                        "id": track_index,  # Use index as ID for consistency
                        "index": track_index,
                        "codec_name": stream.get("codec_name", "unknown"),
                        "filename": stream.get("tags", {}).get("filename", ""),
                        "mimetype": stream.get("tags", {}).get("mimetype", ""),
                    }
                    attachment_tracks.append(attachment_track)

            tracks_info = {
                "video_tracks": video_tracks,
                "audio_tracks": audio_tracks,
                "subtitle_tracks": subtitle_tracks,
                "attachment_tracks": attachment_tracks,
                "source": "ffprobe",
                "total_streams": len(streams),
            }

            LOGGER.info(
                f"📊 FFprobe parsed {len(video_tracks)} video, {len(audio_tracks)} audio, {len(subtitle_tracks)} subtitle, {len(attachment_tracks)} attachment tracks for {hash_id}"
            )
            return tracks_info

        except Exception as e:
            LOGGER.error(f"Error parsing FFprobe tracks for {hash_id}: {e}")
            return {
                "video_tracks": [],
                "audio_tracks": [],
                "subtitle_tracks": [],
                "attachment_tracks": [],
                "source": "ffprobe_parse_error",
                "error": str(e),
            }

    @staticmethod
    async def _store_media_metadata(
        file_info: dict,
        links: dict,
        message_id: int,
        chat_id: int,
        user,
        category: str | None = None,
        client=None,
        quality: str | None = None,
        season: str | None = None,
        episode: str | None = None,
        unique_name: str | None = None,
        copied_msg=None,
    ):
        """Store media metadata using ReelNN's exact processing pipeline"""
        try:
            # Extract hash_id from links
            hash_id = None
            if "download" in links:
                # Extract hash_id from download URL
                match = re.search(r"/([a-f0-9]+\d+)", links["download"])
                if match:
                    hash_id = match.group(1)

            if not hash_id:
                LOGGER.warning("Could not extract hash_id from links")
                return

            # Smart grouping: Quality + Season + Episode grouping (only when explicitly specified or detected)
            grouped_hash_id = hash_id
            grouping_info = []

            # Smart detection from filename and metadata
            detected_quality = None
            detected_season, detected_episode = None, None

            # Smart quality detection if not explicitly provided
            if not quality:
                detected_quality = FileToLinkHandler._smart_detect_quality(file_info)
                if detected_quality:
                    quality = detected_quality
                    LOGGER.info(f"🎬 Smart detected quality: {quality}")

            # Smart season/episode detection if not explicitly provided
            if not season or not episode:
                detected_season, detected_episode = (
                    FileToLinkHandler._smart_detect_season_episode(
                        file_info.get("file_name", "")
                    )
                )
                if detected_season and not season:
                    season = detected_season
                    LOGGER.info(f"📺 Smart detected season: {season}")
                if detected_episode and not episode:
                    episode = detected_episode
                    LOGGER.info(f"🎭 Smart detected episode: {episode}")

            # Quality grouping (when -q flag used or smart detected)
            if quality:
                grouped_hash_id = f"{grouped_hash_id}_{quality.lower()}"
                grouping_info.append(f"quality:{quality}")
                source = "explicit" if quality != detected_quality else "detected"
                LOGGER.info(f"🎬 Quality grouping enabled: {quality} ({source})")

            # Season grouping (only when -s flag used or smart detected)
            if season:
                grouped_hash_id = f"{grouped_hash_id}_s{season.lower()}"
                grouping_info.append(f"season:{season}")
                source = "explicit" if season != detected_season else "detected"
                LOGGER.info(f"📺 Season grouping enabled: {season} ({source})")

            # Episode grouping (only when -ep flag used or smart detected)
            if episode:
                grouped_hash_id = f"{grouped_hash_id}_e{episode.lower()}"
                grouping_info.append(f"episode:{episode}")
                source = "explicit" if episode != detected_episode else "detected"
                LOGGER.info(f"🎭 Episode grouping enabled: {episode} ({source})")

            if grouping_info:
                LOGGER.info(f"🔗 Applied grouping: {' + '.join(grouping_info)}")
                LOGGER.info(f"🔗 Final grouped hash_id: {grouped_hash_id}")
            else:
                LOGGER.info(
                    f"🔗 No grouping applied, using original hash_id: {grouped_hash_id}"
                )

            # ReelNN-style TMDB integration - no thumbnail extraction needed
            LOGGER.info(
                f"🎬 Processing media with TMDB integration for {file_info.get('file_name', 'unknown')}"
            )

            # Enhanced TMDB processing for ReelNN
            tmdb_data = {}
            if file_info.get("enhanced_title"):
                try:
                    from bot.helper.stream_utils.tmdb_helper import TMDBHelper

                    tmdb_helper = TMDBHelper()

                    # Determine media type for TMDB search
                    is_series = any(
                        pattern in file_info.get("file_name", "").lower()
                        for pattern in [
                            "s01",
                            "s02",
                            "s03",
                            "s04",
                            "s05",
                            "s06",
                            "s07",
                            "s08",
                            "s09",
                            "s10",
                            "season",
                            "episode",
                            "e01",
                            "e02",
                            "e03",
                            "e04",
                            "e05",
                            "e06",
                            "e07",
                            "e08",
                            "e09",
                            "e10",
                        ]
                    )

                    # Search TMDB for enhanced metadata
                    if is_series:
                        tmdb_data = await tmdb_helper.search_tv_show(
                            file_info["enhanced_title"]
                        )
                    else:
                        tmdb_data = await tmdb_helper.search_movie(
                            file_info["enhanced_title"]
                        )

                    if tmdb_data:
                        LOGGER.info(
                            f"✅ TMDB data found for {file_info['enhanced_title']}"
                        )
                    else:
                        LOGGER.info(
                            f"❌ No TMDB data found for {file_info['enhanced_title']}"
                        )

                except Exception as tmdb_error:
                    LOGGER.warning(f"⚠️ TMDB lookup failed: {tmdb_error}")
                    tmdb_data = {}

            # Extract comprehensive metadata using FFprobe as primary, Telegram as fallback
            tracks_info = {}
            default_tracks = {"video": 0, "audio": 0, "subtitle": -1}

            if file_info.get("is_video") or file_info.get("is_audio"):
                try:
                    # Use Telegram metadata only (no FFprobe download)
                    LOGGER.info(
                        f"📊 Extracting metadata from Telegram for {hash_id}"
                    )
                    tracks_info = await FileToLinkHandler._extract_tracks_from_telegram_metadata(
                        copied_msg, file_info
                    )

                    if tracks_info and not tracks_info.get("analysis_failed"):
                        # Successfully got track info from Telegram metadata
                        LOGGER.info(
                            f"✅ Extracted track info from Telegram metadata for {hash_id}"
                        )

                        # Set default tracks
                        if tracks_info.get("video_tracks"):
                            default_tracks["video"] = tracks_info["video_tracks"][0][
                                "index"
                            ]
                        if tracks_info.get("audio_tracks"):
                            default_tracks["audio"] = tracks_info["audio_tracks"][0][
                                "index"
                            ]
                        if tracks_info.get("subtitle_tracks"):
                            # Find default subtitle or first one
                            for sub in tracks_info["subtitle_tracks"]:
                                if sub.get("default"):
                                    default_tracks["subtitle"] = sub["index"]
                                    break
                            else:
                                default_tracks["subtitle"] = tracks_info[
                                    "subtitle_tracks"
                                ][0]["index"]

                        LOGGER.info(
                            f"📊 Telegram metadata analysis for {hash_id}: {len(tracks_info.get('video_tracks', []))} video, {len(tracks_info.get('audio_tracks', []))} audio, {len(tracks_info.get('subtitle_tracks', []))} subtitle"
                        )

                    else:
                        # Use basic defaults if metadata extraction fails
                        LOGGER.info(f"⚡ Using basic track defaults for {hash_id}")
                        tracks_info = {
                            "video_tracks": [],
                            "audio_tracks": [],
                            "subtitle_tracks": [],
                            "attachment_tracks": [],
                            "source": "telegram_metadata_basic",
                        }

                        # Add basic track info based on file type
                        if file_info.get("is_video"):
                            tracks_info["video_tracks"].append(
                                {"id": 0, "index": 0, "default": True}
                            )
                            tracks_info["audio_tracks"].append(
                                {"id": 1, "index": 1, "default": True}
                            )
                        elif file_info.get("is_audio"):
                            tracks_info["audio_tracks"].append(
                                {"id": 0, "index": 0, "default": True}
                            )

                except Exception as e:
                    LOGGER.warning(
                        f"❌ Error during metadata extraction for {hash_id}: {e}"
                    )
                    # Use minimal track info as fallback
                    tracks_info = {
                        "video_tracks": [],
                        "audio_tracks": [],
                        "subtitle_tracks": [],
                        "attachment_tracks": [],
                        "source": "fallback_basic",
                        "error": str(e),
                    }

            # Localhost check has been moved to main function before this point

            # Extract ReelNN metadata using the exact processing pipeline
            reelnn_metadata = await FileProcessor.extract_reelnn_metadata(
                copied_msg,
                file_info,
                category,
                quality,
                season,
                episode,
                unique_name,
            )

            # Prepare ReelNN media data structure
            media_data = reelnn_metadata.copy()

            # Update with additional fields
            media_data.update(
                {
                    # Use grouped hash_id for ReelNN compatibility
                    "hash_id": grouped_hash_id,
                    "mid": grouped_hash_id,  # ReelNN movie/show ID
                    "original_hash_id": hash_id,  # Keep original for reference
                    # URLs and streaming
                    "download_url": links.get("download", ""),
                    "stream_url": links.get("stream", ""),
                    # Telegram metadata
                    "uploader_id": user.id,
                    "uploader_name": user.first_name or "Unknown",
                    "uploader_username": user.username,
                    # ReelNN indexing and stats
                    "description": f"Uploaded by {user.first_name or 'Unknown'}",
                    "tags": [],
                    "category": FileToLinkHandler._process_categories(
                        category, file_info
                    ),
                    "categories": FileToLinkHandler._get_categories_list(
                        category, file_info
                    ),
                    "is_trending": False,
                    "status": "active",
                    "featured": False,
                    "trending_score": 0,
                    # Additional ReelNN fields
                    "streamable": file_info.get("is_streamable", True),
                    "file_format": file_info.get("file_name", "")
                    .split(".")[-1]
                    .upper()
                    if "." in file_info.get("file_name", "")
                    else "MP4",
                    # Track information (container-level only)
                    "tracks": tracks_info,
                    "default_tracks": default_tracks,
                }
            )

            # Apply series/episode/quality grouping
            media_data = FileToLinkHandler._add_series_episode_quality_grouping(
                media_data, quality, season, episode, unique_name
            )

            # Fetch TMDB metadata for enhanced information
            try:
                from bot.helper.stream_utils.tmdb_helper import TMDBHelper

                LOGGER.info(
                    f"🎬 Fetching TMDB metadata for: {file_info.get('file_name', 'unknown')}"
                )
                tmdb_metadata = await TMDBHelper.auto_detect_and_fetch_metadata(
                    file_info.get("file_name", "")
                )

                if tmdb_metadata:
                    # tmdb_metadata is the direct data, not wrapped in "data" key
                    tmdb_data = tmdb_metadata
                    media_data["tmdb_data"] = tmdb_data
                    media_data["media_type"] = tmdb_metadata.get(
                        "media_type", "movie"
                    )  # "movie" or "tv"

                    # Update ReelNN fields with TMDB data
                    if tmdb_metadata.get("media_type") == "movie":
                        media_data["title"] = tmdb_data.get(
                            "title", media_data.get("title")
                        )
                        media_data["enhanced_title"] = tmdb_data.get(
                            "title", media_data.get("title")
                        )
                        media_data["original_title"] = tmdb_data.get(
                            "original_title"
                        )
                        media_data["release_date"] = tmdb_data.get("release_date")
                        media_data["runtime"] = tmdb_data.get(
                            "runtime"
                        ) or media_data.get("runtime")
                    else:
                        # For TV shows, the title field in TMDB helper is already set to "name"
                        media_data["title"] = tmdb_data.get(
                            "title", media_data.get("title")
                        )
                        media_data["enhanced_title"] = tmdb_data.get(
                            "title", media_data.get("title")
                        )
                        media_data["original_title"] = tmdb_data.get(
                            "original_title"
                        )
                        media_data["first_air_date"] = tmdb_data.get(
                            "first_air_date"
                        )

                    # Common TMDB fields for both movies and TV shows
                    media_data["overview"] = tmdb_data.get("overview")
                    media_data["vote_average"] = tmdb_data.get("vote_average")
                    media_data["vote_count"] = tmdb_data.get("vote_count")
                    media_data["popularity"] = tmdb_data.get("popularity")
                    media_data["genres"] = tmdb_data.get("genres", [])
                    media_data["poster_path"] = tmdb_data.get("poster_path")
                    media_data["backdrop_path"] = tmdb_data.get("backdrop_path")

                    LOGGER.info(
                        f"✅ TMDB metadata fetched successfully for: {media_data['title']}"
                    )
                else:
                    LOGGER.info(
                        f"ℹ️ No TMDB metadata found for: {file_info.get('file_name', 'unknown')}"
                    )
                    media_data["tmdb_data"] = {}
                    # Keep the title we set earlier
                    media_data["enhanced_title"] = media_data.get("title")

            except Exception as tmdb_error:
                LOGGER.warning(f"⚠️ Error fetching TMDB metadata: {tmdb_error}")
                media_data["tmdb_data"] = {}

            # Store in database using unified access
            database = await ensure_database_and_config()
            if not database:
                LOGGER.error("Database not available for storing media metadata")
                return

            result = await database.store_media_metadata(media_data)
            if result:
                LOGGER.info(f"Stored media metadata for hash_id: {hash_id}")

                # Process quality grouping if quality is specified and file is video
                if (
                    quality
                    and quality != "source"
                    and file_info.get("is_video", False)
                ):
                    try:
                        # Parse and normalize quality
                        normalized_quality = QualityHandler.parse_quality_flag(
                            quality
                        )

                        # Create or join quality group
                        group_id = await QualityHandler.create_or_join_quality_group(
                            media_data, normalized_quality, database
                        )

                        if group_id:
                            LOGGER.info(
                                f"Added {normalized_quality} quality to group {group_id} for hash_id: {hash_id}"
                            )
                        else:
                            LOGGER.info(
                                f"Stored as single {normalized_quality} quality file for hash_id: {hash_id}"
                            )

                    except Exception as quality_error:
                        LOGGER.error(
                            f"Error processing quality grouping: {quality_error}"
                        )
                        # Continue without quality grouping - file is still stored

            else:
                LOGGER.warning(
                    f"Failed to store media metadata for hash_id: {hash_id}"
                )

        except Exception as e:
            LOGGER.error(f"Error storing media metadata: {e}")

    @staticmethod
    def _add_series_episode_quality_grouping(
        metadata: dict, quality: str, season: str, episode: str, unique_name: str
    ) -> dict:
        """Add series/episode/quality grouping logic - Season has multiple episodes, each episode has different qualities"""
        try:
            # Create grouping metadata
            grouping_data = {}

            # Series-level grouping (if season provided)
            if season and unique_name:
                series_id = FileToLinkHandler._generate_series_id(
                    unique_name, season
                )
                grouping_data["series_id"] = series_id
                grouping_data["series_name"] = unique_name
                grouping_data["season"] = season
                grouping_data["season_group"] = season.lower()

                LOGGER.info(f"📺 Series grouping: {unique_name} Season {season}")

            # Episode-level grouping (if episode provided)
            if episode and season and unique_name:
                episode_id = FileToLinkHandler._generate_episode_id(
                    unique_name, season, episode
                )
                grouping_data["episode_id"] = episode_id
                grouping_data["episode"] = episode
                grouping_data["episode_group"] = episode.lower()

                LOGGER.info(
                    f"🎭 Episode grouping: {unique_name} S{season}E{episode}"
                )

            # Quality-level grouping (for same episode, different qualities)
            if quality:
                grouping_data["quality"] = quality
                grouping_data["quality_group"] = quality.lower()

                # Generate quality-specific ID for same episode
                if episode and season and unique_name:
                    quality_id = f"{FileToLinkHandler._generate_episode_id(unique_name, season, episode)}_{quality.lower()}"
                    grouping_data["quality_episode_id"] = quality_id

                    LOGGER.info(
                        f"🎯 Quality grouping: {unique_name} S{season}E{episode} - {quality}"
                    )

            # Generate comprehensive grouping ID
            grouping_data["grouping_id"] = FileToLinkHandler._generate_grouping_id(
                quality, season, episode
            )
            grouping_data["grouping_type"] = (
                FileToLinkHandler._determine_grouping_type(quality, season, episode)
            )

            # Add grouping data to metadata
            metadata["grouping"] = grouping_data

            # Log grouping summary
            grouping_info = []
            if season:
                grouping_info.append(f"season:{season}")
            if episode:
                grouping_info.append(f"episode:{episode}")
            if quality:
                grouping_info.append(f"quality:{quality}")

            if grouping_info:
                LOGGER.info(
                    f"✅ Applied series/episode/quality grouping: {' + '.join(grouping_info)}"
                )

            return metadata

        except Exception as e:
            LOGGER.error(f"Error adding series/episode/quality grouping: {e}")
            return metadata

    @staticmethod
    def _determine_grouping_type(quality: str, season: str, episode: str) -> str:
        """Determine the type of grouping being applied"""
        grouping_types = []
        if quality:
            grouping_types.append("quality")
        if season:
            grouping_types.append("season")
        if episode:
            grouping_types.append("episode")

        if not grouping_types:
            return "none"
        return "_".join(grouping_types)

    @staticmethod
    def _generate_series_id(unique_name: str, season: str) -> str:
        """Generate a series ID for season grouping"""
        if not unique_name or not season:
            return None

        # Clean and normalize the unique name
        clean_name = re.sub(r"[^\w\s-]", "", unique_name.lower()).strip()
        clean_name = re.sub(r"\s+", "_", clean_name)

        return f"series_{clean_name}_s{season.lower()}"

    @staticmethod
    def _generate_episode_id(unique_name: str, season: str, episode: str) -> str:
        """Generate an episode ID for episode grouping"""
        if not unique_name or not season or not episode:
            return None

        # Clean and normalize the unique name
        clean_name = re.sub(r"[^\w\s-]", "", unique_name.lower()).strip()
        clean_name = re.sub(r"\s+", "_", clean_name)

        return f"episode_{clean_name}_s{season.lower()}_e{episode.lower()}"

    @staticmethod
    def _generate_grouping_id(quality: str, season: str, episode: str) -> str:
        """Generate a comprehensive grouping ID"""
        parts = []
        if quality:
            parts.append(f"q{quality.lower()}")
        if season:
            parts.append(f"s{season.lower()}")
        if episode:
            parts.append(f"e{episode.lower()}")

        return "_".join(parts) if parts else "default"

    @staticmethod
    def _smart_detect_quality(file_info: dict) -> str:
        """Smart detection of quality from metadata and filename patterns"""
        try:
            if not file_info:
                return None

            filename = file_info.get("file_name", "")
            width = file_info.get("width", 0)
            height = file_info.get("height", 0)
            file_size = file_info.get("file_size", 0)
            duration = file_info.get("duration", 0)

            detected_quality = None
            detection_source = None

            # Priority 1: Resolution-based detection (most reliable)
            if width and height:
                if height >= 2160:  # 4K
                    detected_quality = "4K"
                    detection_source = f"resolution ({width}x{height})"
                elif height >= 1440:  # 1440p
                    detected_quality = "1440p"
                    detection_source = f"resolution ({width}x{height})"
                elif height >= 1080:  # 1080p
                    detected_quality = "1080p"
                    detection_source = f"resolution ({width}x{height})"
                elif height >= 720:  # 720p
                    detected_quality = "720p"
                    detection_source = f"resolution ({width}x{height})"
                elif height >= 480:  # 480p
                    detected_quality = "480p"
                    detection_source = f"resolution ({width}x{height})"
                elif height >= 360:  # 360p
                    detected_quality = "360p"
                    detection_source = f"resolution ({width}x{height})"
                else:  # Below 360p
                    detected_quality = "240p"
                    detection_source = f"resolution ({width}x{height})"

            # Priority 2: Filename pattern detection (if no resolution available)
            if not detected_quality and filename:
                filename_lower = filename.lower()

                # Common quality patterns in filenames
                quality_patterns = [
                    # 4K variants
                    (r"(?:4k|2160p|uhd|ultra.*hd)", "4K"),
                    # 1440p variants
                    (r"(?:1440p|2k)", "1440p"),
                    # 1080p variants
                    (r"(?:1080p|1080i|fhd|full.*hd)", "1080p"),
                    # 720p variants
                    (r"(?:720p|720i|hd)", "720p"),
                    # 480p variants
                    (r"(?:480p|480i|sd)", "480p"),
                    # 360p variants
                    (r"(?:360p)", "360p"),
                    # 240p variants
                    (r"(?:240p)", "240p"),
                    # Special quality indicators
                    (
                        r"(?:bluray|brrip|bdrip)",
                        "1080p",
                    ),  # Assume BluRay is 1080p unless specified
                    (
                        r"(?:webrip|webdl|web-dl)",
                        "1080p",
                    ),  # Assume Web releases are 1080p unless specified
                    (r"(?:dvdrip|dvd)", "480p"),  # DVD quality
                    (r"(?:cam|camrip|ts|telesync)", "240p"),  # Low quality releases
                ]

                for pattern, quality in quality_patterns:
                    if re.search(pattern, filename_lower):
                        detected_quality = quality
                        detection_source = f"filename pattern ({pattern})"
                        break

            # Priority 3: Bitrate estimation (for video files with duration)
            if (
                not detected_quality
                and file_size > 0
                and duration > 0
                and file_info.get("is_video")
            ):
                # Calculate approximate bitrate (rough estimation)
                bitrate_kbps = (file_size * 8) / (duration * 1000)  # Convert to kbps

                if bitrate_kbps >= 15000:  # High bitrate suggests 4K
                    detected_quality = "4K"
                    detection_source = (
                        f"bitrate estimation ({bitrate_kbps:.0f} kbps)"
                    )
                elif bitrate_kbps >= 8000:  # High bitrate suggests 1080p
                    detected_quality = "1080p"
                    detection_source = (
                        f"bitrate estimation ({bitrate_kbps:.0f} kbps)"
                    )
                elif bitrate_kbps >= 4000:  # Medium bitrate suggests 720p
                    detected_quality = "720p"
                    detection_source = (
                        f"bitrate estimation ({bitrate_kbps:.0f} kbps)"
                    )
                elif bitrate_kbps >= 1500:  # Lower bitrate suggests 480p
                    detected_quality = "480p"
                    detection_source = (
                        f"bitrate estimation ({bitrate_kbps:.0f} kbps)"
                    )
                else:  # Very low bitrate
                    detected_quality = "360p"
                    detection_source = (
                        f"bitrate estimation ({bitrate_kbps:.0f} kbps)"
                    )

            # Priority 4: File size heuristics (last resort for video files)
            if not detected_quality and file_size > 0 and file_info.get("is_video"):
                size_mb = file_size / (1024 * 1024)

                if size_mb >= 8000:  # Very large files likely 4K
                    detected_quality = "4K"
                    detection_source = f"file size heuristic ({size_mb:.0f} MB)"
                elif size_mb >= 3000:  # Large files likely 1080p
                    detected_quality = "1080p"
                    detection_source = f"file size heuristic ({size_mb:.0f} MB)"
                elif size_mb >= 1000:  # Medium files likely 720p
                    detected_quality = "720p"
                    detection_source = f"file size heuristic ({size_mb:.0f} MB)"
                elif size_mb >= 300:  # Smaller files likely 480p
                    detected_quality = "480p"
                    detection_source = f"file size heuristic ({size_mb:.0f} MB)"
                else:  # Very small files
                    detected_quality = "360p"
                    detection_source = f"file size heuristic ({size_mb:.0f} MB)"

            # Log results
            if detected_quality:
                LOGGER.info(
                    f"✅ Smart quality detection: {detected_quality} from {detection_source}"
                )
                LOGGER.info(
                    f"📊 File info: {width}x{height}, {file_size / 1024 / 1024:.1f}MB, {duration}s, {filename}"
                )
            else:
                LOGGER.info(f"❌ No quality detected from file: {filename}")

            return detected_quality

        except Exception as e:
            LOGGER.error(f"Error in smart quality detection: {e}")
            return None

    @staticmethod
    def _smart_detect_season_episode(filename: str) -> tuple:
        """Smart detection of season and episode from filename patterns"""
        try:
            if not filename:
                return None, None

            filename_lower = filename.lower()
            detected_season = None
            detected_episode = None

            # Common season/episode patterns
            season_episode_patterns = [
                # S01E01, S1E1, s01e01, s1e1
                r"s(\d{1,2})e(\d{1,3})",
                # Season 1 Episode 1, season 01 episode 01
                r"season\s*(\d{1,2})\s*episode\s*(\d{1,3})",
                # 1x01, 01x01
                r"(\d{1,2})x(\d{1,3})",
                # [S01][E01], [S1][E1]
                r"\[s(\d{1,2})\]\[e(\d{1,3})\]",
                # S01.E01, S1.E1
                r"s(\d{1,2})\.e(\d{1,3})",
                # Season.1.Episode.1
                r"season\.(\d{1,2})\.episode\.(\d{1,3})",
            ]

            # Try season/episode patterns first
            for pattern in season_episode_patterns:
                match = re.search(pattern, filename_lower)
                if match:
                    detected_season = match.group(1).zfill(
                        2
                    )  # Pad with zero if needed
                    detected_episode = match.group(2).zfill(
                        2
                    )  # Pad with zero if needed
                    LOGGER.info(
                        f"📺 Smart detected S{detected_season}E{detected_episode} from pattern: {pattern}"
                    )
                    return detected_season, detected_episode

            # Try season-only patterns if no season/episode found
            season_only_patterns = [
                # Season 1, Season 01, season 1
                r"season\s*(\d{1,2})",
                # S01, S1, s01, s1 (but not followed by E)
                r"s(\d{1,2})(?!e)",
                # [Season 1], [S01]
                r"\[(?:season\s*)?s?(\d{1,2})\]",
            ]

            for pattern in season_only_patterns:
                match = re.search(pattern, filename_lower)
                if match:
                    detected_season = match.group(1).zfill(2)
                    LOGGER.info(
                        f"📺 Smart detected season S{detected_season} from pattern: {pattern}"
                    )
                    break

            # Try episode-only patterns if no episode found yet
            if not detected_episode:
                episode_only_patterns = [
                    # Episode 1, Episode 01, episode 1
                    r"episode\s*(\d{1,3})",
                    # E01, E1, e01, e1 (but not preceded by S) - fixed width lookbehind
                    r"(?<!s\d)(?<!s\d\d)e(\d{1,3})",
                    # [Episode 1], [E01]
                    r"\[(?:episode\s*)?e?(\d{1,3})\]",
                    # Ep01, Ep1, ep01, ep1
                    r"ep(\d{1,3})",
                ]

                for pattern in episode_only_patterns:
                    match = re.search(pattern, filename_lower)
                    if match:
                        detected_episode = match.group(1).zfill(2)
                        LOGGER.info(
                            f"🎭 Smart detected episode E{detected_episode} from pattern: {pattern}"
                        )
                        break

            # Additional heuristics for common naming conventions
            if not detected_season and not detected_episode:
                # Try to detect from common anime/series patterns
                # Like: [Group] Series Name - 01 [Quality].mkv
                anime_pattern = r"[-\s](\d{1,3})(?:\s*\[|\s*$|\s*\.)"
                match = re.search(anime_pattern, filename_lower)
                if match:
                    episode_num = match.group(1).zfill(2)
                    # Assume it's episode if number is reasonable for episodes (1-999)
                    if 1 <= int(episode_num) <= 999:
                        detected_episode = episode_num
                        LOGGER.info(
                            f"🎭 Smart detected episode E{detected_episode} from anime pattern"
                        )

            # Log results
            if detected_season or detected_episode:
                result_parts = []
                if detected_season:
                    result_parts.append(f"S{detected_season}")
                if detected_episode:
                    result_parts.append(f"E{detected_episode}")
                LOGGER.info(
                    f"✅ Smart detection result: {' '.join(result_parts)} from filename: {filename}"
                )
            else:
                LOGGER.info(
                    f"❌ No season/episode detected from filename: {filename}"
                )

            return detected_season, detected_episode

        except Exception as e:
            LOGGER.error(f"Error in smart season/episode detection: {e}")
            return None, None

    @staticmethod
    def _get_media_category(file_info: dict) -> str:
        """Determine media category based on file info with smart categorization"""
        file_name = file_info.get("file_name", "").lower()

        # Smart categorization based on filename patterns
        if file_info.get("is_video"):
            # Check for anime patterns
            anime_patterns = [
                "anime",
                "ep",
                "episode",
                "season",
                "sub",
                "dub",
                "[",
                "]",
                "x264",
                "x265",
                "hevc",
            ]
            if any(pattern in file_name for pattern in anime_patterns):
                return "anime"

            # Check for series patterns
            series_patterns = [
                "s01",
                "s02",
                "s03",
                "s04",
                "s05",
                "s06",
                "s07",
                "s08",
                "s09",
                "s10",
                "season",
                "episode",
                "ep",
                "e01",
                "e02",
                "e03",
                "e04",
                "e05",
            ]
            if any(pattern in file_name for pattern in series_patterns):
                return "series"

            # Default to movie for other videos
            return "movie"

        if file_info.get("is_audio"):
            # Check for music patterns
            music_patterns = ["mp3", "flac", "wav", "aac", "m4a", "ogg", "wma"]
            if any(pattern in file_name for pattern in music_patterns):
                return "music"
            return "music"  # Default audio to music

        if file_info.get("is_image"):
            return "image"
        return "library"  # Changed from "document" to "library" for better categorization

    @staticmethod
    def _normalize_category(category: str) -> str:
        """Normalize category input to standard categories"""
        category = category.lower().strip()

        # Movie categories
        if category in ["movie", "movies", "film", "films"]:
            return "movie"

        # Series categories
        if category in ["series", "tv", "show", "shows", "television"]:
            return "series"

        # Anime categories
        if category in ["anime", "animes", "manga"]:
            return "anime"

        # Music/Audio categories
        if category in ["music", "audio", "song", "songs", "sound"]:
            return "music"

        # Library/General categories
        if category in ["library", "general", "misc", "other"]:
            return "library"

        # Document categories
        if category in ["document", "doc", "docs", "file", "files"]:
            return "document"

        # Default fallback
        return category

    @staticmethod
    def _process_categories(category: str, file_info: dict) -> str:
        """Process categories and return primary category for backward compatibility"""
        if category:
            # If multiple categories (comma-separated), return the first one as primary
            if "," in category:
                categories = [cat.strip() for cat in category.split(",")]
                return FileToLinkHandler._normalize_category(categories[0])
            return FileToLinkHandler._normalize_category(category)
        # Auto-detect category
        return FileToLinkHandler._get_media_category(file_info)

    @staticmethod
    def _get_categories_list(category: str, file_info: dict) -> list:
        """Get list of all categories for the media"""
        categories = []

        if category:
            if "," in category:
                # Multiple custom categories
                custom_categories = [cat.strip() for cat in category.split(",")]
                categories.extend(custom_categories)
            else:
                # Single category
                categories.append(category)
        else:
            # Auto-detected category
            auto_category = FileToLinkHandler._get_media_category(file_info)
            categories.append(auto_category)

        # Normalize all categories and remove duplicates
        normalized_categories = []
        for cat in categories:
            normalized = FileToLinkHandler._normalize_category(cat)
            if normalized not in normalized_categories:
                normalized_categories.append(normalized)

        return normalized_categories

    @staticmethod
    def _get_default_thumbnail(file_info: dict) -> str:
        """Generate default thumbnail URL based on media type"""
        try:
            # Create a default thumbnail based on media type
            if file_info.get("is_video") or file_info.get("category") in [
                "movie",
                "series",
                "anime",
            ]:
                return "/static/icons/default-video.svg"
            if file_info.get("is_audio") or file_info.get("category") == "music":
                return "/static/icons/default-audio.svg"
            if file_info.get("is_image"):
                return "/static/icons/default-image.svg"
            return "/static/icons/default-document.svg"
        except Exception as e:
            LOGGER.error(f"Error generating default thumbnail: {e}")
            return "/static/icons/default-file.svg"

    @staticmethod
    async def _handle_multi_link_mode(
        message: Message,
        category: str | None = None,
        quality: str | None = None,
        season: str | None = None,
        episode: str | None = None,
        unique_name: str | None = None,
    ):
        """Handle multi-link mode for processing multiple messages"""
        try:
            await send_message(
                message,
                "🔗 **Multi-Link Mode Activated**\n\n"
                "Please send the media files you want to process one by one.\n"
                "Send `/done` when you're finished.\n"
                "Send `/cancel` to cancel the operation.\n\n"
                f"**Settings:**\n"
                f"• Category: `{category or 'Auto-detect'}`\n"
                f"• Quality: `{quality or 'Not specified'}`\n"
                f"• Season: `{season or 'Not specified'}`\n"
                f"• Episode: `{episode or 'Not specified'}`\n"
                f"• Unique Name: `{unique_name or 'Not specified'}`",
            )

            # TODO: Implement multi-link processing logic
            # This would involve:
            # 1. Setting up a conversation state for the user
            # 2. Collecting multiple messages
            # 3. Processing them all with the same metadata
            # 4. Smart detection of series/episodes
            # 5. Grouping related media

            LOGGER.info(f"Multi-link mode requested by user {message.from_user.id}")

        except Exception as e:
            LOGGER.error(f"Error in multi-link mode: {e}")
            await send_message(message, f"❌ Error in multi-link mode: {e!s}")


@new_task
async def file_to_link_command(client, message: Message):
    """Handle /file2link and /f2l commands with category support"""
    try:
        # Check access permissions
        if not await error_check(message):
            return

        # Parse command arguments
        args = message.text.split()[1:] if len(message.text.split()) > 1 else []
        category = None
        quality = None
        season = None
        episode = None
        unique_name = None
        multi_link = False
        delete_category_mode = False
        edit_category_mode = False
        target_username = None
        old_category = None
        new_category = None

        # Parse arguments
        i = 0
        while i < len(args):
            arg = args[i].lower()
            if arg in [
                "movie",
                "movies",
                "series",
                "tv",
                "anime",
                "animes",
                "library",
                "music",
                "audio",
                "document",
                "other",
            ]:
                category = FileToLinkHandler._normalize_category(arg)
            elif arg == "-q" and i + 1 < len(args):
                # Quality flag
                quality = args[i + 1]
                i += 1  # Skip next argument as it's the quality
            elif arg == "-s" and i + 1 < len(args):
                # Season flag
                season = args[i + 1]
                i += 1  # Skip next argument as it's the season
            elif arg == "-uname" and i + 1 < len(args):
                # Unique name flag
                unique_name = args[i + 1]
                i += 1  # Skip next argument as it's the unique name
            elif arg == "-ep" and i + 1 < len(args):
                # Episode flag
                episode = args[i + 1]
                i += 1  # Skip next argument as it's the episode
            elif arg == "-c":
                # Custom categories flag - collect all following non-flag arguments
                categories = []
                i += 1  # Move to next argument
                while i < len(args) and not args[i].startswith("-"):
                    categories.append(args[i].lower().strip())
                    i += 1
                i -= 1  # Adjust because the main loop will increment
                # Join categories with comma for storage
                category = ",".join(categories) if categories else None
            elif arg == "-i":
                # Multi-link flag
                multi_link = True
            elif arg == "-delcat" and i + 2 < len(args):
                # Delete category flag: -delcat <category> <username>
                delete_category_mode = True
                category = args[i + 1].lower().strip()
                target_username = args[i + 2].strip()
                i += 2  # Skip next two arguments
            elif arg == "-editcat" and i + 3 < len(args):
                # Edit category flag: -editcat <old_category> <new_category> <username>
                edit_category_mode = True
                old_category = args[i + 1].lower().strip()
                new_category = args[i + 2].lower().strip()
                target_username = args[i + 3].strip()
                i += 3  # Skip next three arguments
            i += 1

        # Handle delete category mode
        if delete_category_mode:
            if not category or not target_username:
                await send_message(
                    message, "❌ Usage: /f2l -delcat <category> <username>"
                )
                return

            # Use unified database access
            database = await ensure_database_and_config()
            if not database:
                await send_message(message, "❌ Database not available")
                return

            # Delete all media files by category and username
            deleted_count = await database.delete_media_by_category_and_user(
                category, target_username
            )

            if deleted_count > 0:
                await send_message(
                    message,
                    f"✅ Deleted {deleted_count} media files from category '{category}' for user '{target_username}'",
                )
            else:
                await send_message(
                    message,
                    f"❌ No media files found for category '{category}' and user '{target_username}'",
                )
            return

        # Handle edit category mode
        if edit_category_mode:
            if not old_category or not new_category or not target_username:
                await send_message(
                    message,
                    "❌ Usage: /f2l -editcat <old_category> <new_category> <username>",
                )
                return

            # Use unified database access
            database = await ensure_database_and_config()
            if not database:
                await send_message(message, "❌ Database not available")
                return

            # Update category for all media files by username
            updated_count = await database.update_media_category(
                old_category, new_category, target_username
            )

            if updated_count > 0:
                await send_message(
                    message,
                    f"✅ Updated {updated_count} media files from category '{old_category}' to '{new_category}' for user '{target_username}'",
                )
            else:
                await send_message(
                    message,
                    f"❌ No media files found for category '{old_category}' and user '{target_username}'",
                )
            return

        # Handle multi-link mode
        if multi_link:
            await FileToLinkHandler._handle_multi_link_mode(
                message, category, quality, season, episode, unique_name
            )
            return

        # Check if replying to a message with media
        if not message.reply_to_message:
            help_text = """
<b>📁 File-to-Link Bot - Enhanced</b>

<b>Usage:</b>
• Reply to any media file with <code>/f2l [category] [flags]</code>

<b>Basic Examples:</b>
• <code>/f2l movie</code> - Categorize as Movie
• <code>/f2l series</code> - Categorize as TV Series
• <code>/f2l anime</code> - Categorize as Anime
• <code>/f2l music</code> - Categorize as Music/Audio

<b>Advanced Flags:</b>
• <code>-q QUALITY</code> - Media quality (1080p, 720p, 480p, etc.)
• <code>-s SEASON</code> - Season number for series
• <code>-ep EPISODE</code> - Episode number for series/anime
• <code>-uname NAME</code> - Unique name for grouping related media
• <code>-c CATEGORIES</code> - Custom categories (multiple allowed)


<b>Category Management Flags:</b>
• <code>-delcat CATEGORY USERNAME</code> - Delete all media in category for user
• <code>-editcat OLD_CAT NEW_CAT USERNAME</code> - Change category for user's media

<b>Advanced Examples:</b>
• <code>/f2l anime -q 1080p -s 1 -ep 5 -uname "Attack on Titan"</code>
• <code>/f2l series -s 2 -ep 10 -uname "Breaking Bad"</code>
• <code>/f2l -c anime action adventure -q 1080p -uname "Demon Slayer"</code>
• <code>/f2l -c movie thriller horror -q 720p</code>

<b>Category Management Examples:</b>
• <code>/f2l -delcat anime john_doe</code> - Delete all anime for user john_doe
• <code>/f2l -editcat movie film john_doe</code> - Change "movie" to "film" for john_doe

<b>Built-in Categories:</b>
• <code>movie/movies</code> - Movies and films
• <code>series/tv</code> - TV shows and series
• <code>anime/animes</code> - Anime content
• <code>music/audio</code> - Music and audio files
• <code>library</code> - General library content
• <code>document</code> - Documents and other files

<b>Custom Categories:</b>
• Use <code>-c</code> flag to add any categories you want
• Multiple categories: <code>-c action adventure comedy</code>
• Categories will appear on website if category pages exist
• Otherwise shown in "All" category section

<b>Features:</b>
• 💥 Superfast download links
• 🎬 Direct streaming for videos/audio
• 🔒 Secure hash-based access
• 💎 Permanent links (won't expire)
• 📊 Smart series/season organization
• 🎯 Quality-based categorization
• 🏷️ Custom category tagging
• 🎬 TMDB metadata integration
• 🔗 Multi-link batch processing
"""
            await send_message(message, help_text)
            return

        # Process the replied message with all flags
        await FileToLinkHandler.process_file_to_link(
            client,
            message.reply_to_message,
            category=category,
            quality=quality,
            season=season,
            episode=episode,
            unique_name=unique_name,
        )

    except Exception as e:
        LOGGER.error(f"Error in file-to-link command: {e}")
        await send_message(message, f"❌ Error: {e!s}")


@new_task
async def stream_stats_command(client, message: Message):
    """Handle /streamstats command"""
    try:
        # Check access permissions
        if not await error_check(message):
            return

        # Get system statistics
        system_stats = SystemMonitor.get_formatted_stats()
        cache_stats = CacheManager.get_cache_stats()
        dc_stats = DCChecker.format_dc_stats()

        # Get load balancer statistics via HTTP API (since bot and web server run in separate processes)
        try:
            # Get the base URL for the web server
            base_url = getattr(Config, "BASE_URL", "http://localhost")
            base_url = base_url.removesuffix("/")

            # Call the load balancer stats endpoint using httpx
            async with httpx.AsyncClient(timeout=5.0) as http_client:
                response = await http_client.get(f"{base_url}/stats/loadbalancer")
                if response.status_code == 200:
                    data = response.json()
                    lb_stats = data.get("stats", {})

                    # Format load balancer statistics like LoadBalancer.format_load_stats()
                    if not lb_stats or lb_stats.get("total_clients", 0) == 0:
                        load_stats = (
                            "📊 <b>Load Balancer:</b> <code>No data available</code>"
                        )
                    else:
                        total_load = lb_stats.get("total_load", 0)
                        healthy_clients = lb_stats.get("healthy_clients", 0)
                        total_clients = lb_stats.get("total_clients", 0)
                        average_load = lb_stats.get("average_load", 0.0)
                        client_loads = lb_stats.get("client_loads", {})

                        load_stats = "📊 <b>Load Balancer Statistics</b>\n\n"
                        load_stats += (
                            f"🤖 Total Clients: <code>{total_clients}</code>\n"
                        )
                        load_stats += (
                            f"✅ Healthy Clients: <code>{healthy_clients}</code>\n"
                        )
                        load_stats += f"⚡ Total Load: <code>{total_load}</code>\n"
                        load_stats += (
                            f"📈 Average Load: <code>{average_load:.1f}</code>\n\n"
                        )
                        load_stats += "<b>Client Details:</b>\n"

                        for client_id, load in client_loads.items():
                            if client_id == "0":
                                load_stats += (
                                    f"✅ Main: <code>{load} requests</code>\n"
                                )
                            else:
                                load_stats += f"✅ Helper-{client_id}: <code>{load} requests</code>\n"

                    LOGGER.info("Retrieved load balancer stats via HTTP")
                else:
                    raise Exception(f"HTTP {response.status_code}")
        except Exception as e:
            LOGGER.warning(f"Could not get load balancer stats via HTTP: {e}")
            # Fallback to direct import (for development/single-process setups)
            try:
                load_stats = LoadBalancer.format_load_stats()
                LOGGER.info(
                    "Retrieved load balancer stats via direct import (fallback)"
                )
            except Exception as e2:
                LOGGER.warning(f"Direct load balancer import also failed: {e2}")
                load_stats = (
                    "📊 <b>Load Balancer:</b> <code>Error retrieving data</code>"
                )

        # REMOVED: Redundant web server stats - integrated with wserver directly
        # Web server stats are now handled by the unified client management system
        wserver_stats = {
            "integrated": True,
            "note": "Stats available via /stats command in web interface",
        }

        # Format cache statistics
        cache_text = f"""
📦 <b>Cache Statistics</b>
• File Cache: <code>{cache_stats.get("file_cache_size", 0)}</code>
• Link Cache: <code>{cache_stats.get("link_cache_size", 0)}</code>
• User Cache: <code>{cache_stats.get("user_cache_size", 0)}</code>
• Total Entries: <code>{cache_stats.get("total_entries", 0)}</code>
• Status: <code>{"Enabled" if cache_stats.get("cache_enabled") else "Disabled"}</code>
"""

        # Format web server statistics (integrated approach)
        if wserver_stats.get("integrated"):
            wserver_text = f"""
🌐 <b>Web Server Integration</b>
• Status: <code>✅ Integrated with LoadBalancer</code>
• Client Management: <code>Unified with file_to_link</code>
• Stats: <code>{wserver_stats.get("note", "Available via web interface")}</code>
"""
        elif "error" in wserver_stats:
            wserver_text = f"""
🌐 <b>Web Server Clients</b>
• Status: <code>❌ Error: {wserver_stats["error"]}</code>
"""
        else:
            wserver_text = f"""
🌐 <b>Web Server Clients</b>
• Initialized: <code>{"✅ Yes" if wserver_stats.get("initialized") else "❌ No"}</code>
• Total Clients: <code>{wserver_stats.get("total_clients", 0)}</code>
• Connected: <code>{wserver_stats.get("connected_clients", 0)}</code>
• Main Client: <code>{"✅ Connected" if wserver_stats.get("main_client", {}).get("connected") else "❌ Disconnected"}</code>
"""

            # Add helper bot details
            helper_bots = wserver_stats.get("helper_bots", [])
            if helper_bots:
                wserver_text += "• Helper Bots:\n"
                for helper in helper_bots:
                    status = "✅" if helper.get("connected") else "❌"
                    wserver_text += f"  - Helper-{helper.get('id', '?')}: <code>{status} {helper.get('username', 'Unknown')}</code>\n"
            else:
                wserver_text += "• Helper Bots: <code>None configured</code>\n"

        # Add configuration validation
        is_valid, messages = ConfigValidator.validate_all()
        config_status = "✅ Valid" if is_valid else "❌ Issues Found"
        config_text = f"""
🔧 <b>Configuration Status</b>
• Status: <code>{config_status}</code>
• Issues: <code>{len([m for m in messages if "error" in m.lower() or "required" in m.lower()])}</code>
• Warnings: <code>{len([m for m in messages if "warning" in m.lower() or "disabled" in m.lower()])}</code>
"""

        # Combine all statistics
        full_stats = f"{system_stats}\n\n{load_stats}\n\n{wserver_text}\n\n{cache_text}\n\n{config_text}\n\n{dc_stats}"

        await send_message(message, full_stats)

    except Exception as e:
        LOGGER.error(f"Error in stream stats command: {e}")
        await send_message(message, f"❌ Error getting statistics: {e!s}")


@new_task
async def auto_file_handler(client, message: Message):
    """Automatically handle files sent to bot"""
    try:
        # Check if auto-processing is enabled and user has permission
        if not Config.FILE_TO_LINK_ENABLED:
            return

        # Enhanced message and user validation
        if not message:
            return

        # Check if message has required attributes
        if not hasattr(message, "from_user") or not message.from_user:
            return

        # Check if message has user ID
        if not hasattr(message.from_user, "id") or not message.from_user.id:
            return

        # Check if message is a service message or system message
        if hasattr(message, "service") and message.service:
            return

        # Check if message has content (document, photo, video, etc.)
        if not any(
            [
                hasattr(message, "document") and message.document,
                hasattr(message, "photo") and message.photo,
                hasattr(message, "video") and message.video,
                hasattr(message, "audio") and message.audio,
                hasattr(message, "animation") and message.animation,
                hasattr(message, "voice") and message.voice,
                hasattr(message, "video_note") and message.video_note,
            ]
        ):
            return

        # Check access permissions
        if not await error_check(message):
            return

        # Process file automatically
        await FileToLinkHandler.process_file_to_link(client, message)

    except Exception as e:
        LOGGER.error(f"Error in auto file handler: {e}")


# Auto file handler registration (ENABLED for dump chat processing)
async def register_auto_file_handler():
    """Register auto file handler for dump chat processing"""
    try:
        # Enable auto file handler for dump chat processing
        if Config.FILE_TO_LINK_ENABLED and hasattr(TgClient, "bot") and TgClient.bot:
            # Create a filter for dump chat messages only
            def dump_chat_filter(_, __, message):
                if not message or not message.chat:
                    return False

                # Check if message is from stream chat or dump chat (ReelNN compatibility)
                stream_chats = (
                    getattr(Config, "STREAM_CHATS", None) or Config.LEECH_DUMP_CHAT
                )
                if not stream_chats:
                    return False

                chat_id = message.chat.id
                if isinstance(stream_chats, list):
                    # Handle list of stream chats
                    for stream_chat in stream_chats:
                        try:
                            # Process chat ID format (handle prefixes like b:, u:, h:)
                            processed_chat_id = stream_chat
                            if processed_chat_id is None:
                                continue
                            if isinstance(processed_chat_id, str):
                                if ":" in processed_chat_id:
                                    processed_chat_id = processed_chat_id.split(
                                        ":", 1
                                    )[1]
                                if "|" in processed_chat_id:
                                    processed_chat_id = processed_chat_id.split(
                                        "|", 1
                                    )[0]

                            if (
                                processed_chat_id
                                and int(processed_chat_id) == chat_id
                            ):
                                return True
                        except (ValueError, TypeError):
                            if stream_chat and str(stream_chat) == str(chat_id):
                                return True
                else:
                    # Single stream chat
                    try:
                        return int(stream_chats) == chat_id
                    except (ValueError, TypeError):
                        return str(stream_chats) == str(chat_id)

                return False

            TgClient.bot.add_handler(
                MessageHandler(
                    auto_file_handler,
                    filters=filters.create(dump_chat_filter)
                    & (
                        filters.document
                        | filters.video
                        | filters.audio
                        | filters.photo
                        | filters.animation
                        | filters.voice
                        | filters.video_note
                    )
                    & ~filters.command(BotCommands.File2LinkCommand),
                ),
                group=2,  # Lower priority to not interfere with commands
            )
            LOGGER.info(
                "Auto file handler registered successfully for dump chat processing"
            )
        else:
            LOGGER.info(
                "Auto file handler disabled - FILE_TO_LINK not enabled or bot not available"
            )
    except Exception as e:
        LOGGER.error(f"Error registering auto file handler: {e}")


# Initialize components on module load
async def initialize_file_to_link():
    """Initialize file-to-link components"""
    try:
        # BASE_URL configuration is handled by the main startup process
        LOGGER.info("File-to-Link will use BASE_URL configuration...")

        # Validate configuration first
        LOGGER.info("Validating File-to-Link configuration...")
        is_valid = ConfigValidator.validate_and_log()

        if not is_valid:
            LOGGER.warning(
                "File-to-Link configuration has issues, but continuing initialization..."
            )

        # LoadBalancer initialization is handled by the web server process only
        # No need to initialize it in the main bot process

        # Register auto file handler (disabled - only manual /f2l works)
        await register_auto_file_handler()

        # Start system monitoring if enabled
        if Config.FILE_TO_LINK_ENABLED:
            asyncio.create_task(SystemMonitor.start_monitoring())

        # Start periodic cache cleanup
        async def cache_cleanup_task():
            while True:
                await asyncio.sleep(300)  # Every 5 minutes
                await CacheManager.cleanup_expired()
                SecurityHandler.clean_cache()
                DCChecker.cleanup_cache()

        asyncio.create_task(cache_cleanup_task())

        LOGGER.info("File-to-Link module initialized successfully")

    except Exception as e:
        LOGGER.error(f"Error initializing file-to-link module: {e}")


# Note: Initialization will be called from main bot startup
