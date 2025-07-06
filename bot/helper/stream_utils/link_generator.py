from urllib.parse import quote_plus

from bot import LOGGER
from bot.core.config_manager import Config

from .security_handler import SecurityHandler


class LinkGenerator:
    """Generates secure download and streaming links"""

    @staticmethod
    def generate_links(file_info: dict, message_id: int) -> dict[str, str]:
        """Generate both download and streaming links for a file"""
        try:
            if not file_info:
                return {}

            # Generate secure hash
            secure_hash = SecurityHandler.generate_secure_hash(
                file_info["file_unique_id"], str(message_id)
            )

            # Determine base URL
            base_url = LinkGenerator._get_base_url()

            # Generate filename for URL
            safe_filename = LinkGenerator._make_safe_filename(file_info["file_name"])

            links = {}

            # Generate download link with download parameter
            download_url = f"{base_url}{secure_hash}{message_id}"
            if safe_filename:
                download_url += f"/{quote_plus(safe_filename)}"
            download_url += f"?hash={secure_hash}&download=1"
            links["download"] = download_url

            # Generate ReelNN-style streaming link
            if file_info.get("is_streamable", False):
                # Extract media type using ReelNN logic
                media_type = LinkGenerator._detect_media_type_reelnn(file_info)

                # Create ReelNN-style URL structure
                content_type = "show" if media_type == "tv" else "movie"

                # ReelNN URL format: /movie/{mid} or /show/{sid}
                stream_url = f"{base_url}{content_type}/{secure_hash}{message_id}"
                if safe_filename:
                    stream_url += f"/{quote_plus(safe_filename)}"
                stream_url += f"?hash={secure_hash}"
                links["stream"] = stream_url

            # Generate direct API link
            api_url = (
                f"{base_url}api/file/{secure_hash}{message_id}?hash={secure_hash}"
            )
            links["api"] = api_url

            return links

        except Exception as e:
            LOGGER.error(f"Error generating links: {e}")
            return {}

    @staticmethod
    def _detect_media_type_reelnn(file_info: dict) -> str:
        """Detect media type using ReelNN's exact logic"""
        # Check if metadata already has media_type
        if file_info.get("media_type"):
            return file_info["media_type"]

        # Check for series indicators
        if (
            file_info.get("series_data")
            or file_info.get("season")
            or file_info.get("episode")
        ):
            return "tv"

        # Check filename patterns for TV shows
        filename = file_info.get("file_name", "").lower()

        # ReelNN TV show detection patterns
        tv_patterns = [
            r"s\d{1,2}e\d{1,2}",  # S01E01 format
            r"season\s*\d+",  # Season X
            r"episode\s*\d+",  # Episode X
            r"\bs\d{1,2}\b",  # S01, S02, etc.
            r"\be\d{1,2}\b",  # E01, E02, etc.
            r"\d{1,2}x\d{1,2}",  # 1x01 format
        ]

        import re

        for pattern in tv_patterns:
            if re.search(pattern, filename):
                return "tv"

        # Default to movie
        return "movie"

    @staticmethod
    def _get_base_url() -> str:
        """Get ReelNN-style streaming base URL with Heroku auto-detection"""
        try:
            # Priority 1: Use STREAM_BASE_URL if configured (ReelNN style)
            if hasattr(Config, "STREAM_BASE_URL") and Config.STREAM_BASE_URL:
                base_url = Config.STREAM_BASE_URL
                if not base_url.endswith("/"):
                    base_url += "/"
                if LinkGenerator._is_valid_url(base_url):
                    return base_url

            # Priority 2: Auto-detect Heroku URL for streaming (ReelNN style)
            if hasattr(Config, "HEROKU_APP_NAME") and Config.HEROKU_APP_NAME:
                heroku_url = f"https://{Config.HEROKU_APP_NAME}.herokuapp.com/"
                if LinkGenerator._is_valid_url(heroku_url):
                    # Auto-set STREAM_BASE_URL for future use
                    if hasattr(Config, "set"):
                        Config.set("STREAM_BASE_URL", heroku_url.rstrip("/"))
                    return heroku_url

            # Priority 3: Use BASE_URL as fallback
            if Config.BASE_URL:
                base_url = Config.BASE_URL
                if not base_url.endswith("/"):
                    base_url += "/"
                if LinkGenerator._is_valid_url(base_url):
                    return base_url

            # Priority 4: Use web server port if available
            if Config.BASE_URL_PORT != 0:
                port = Config.BASE_URL_PORT or 80
                base_url = f"http://localhost:{port}/"
                if LinkGenerator._is_valid_url(base_url):
                    return base_url

            # Fallback to localhost with main web server port
            port = Config.BASE_URL_PORT or 80
            fallback_url = f"http://localhost:{port}/"
            LOGGER.warning(f"Using fallback URL: {fallback_url}")
            return fallback_url

        except Exception as e:
            LOGGER.error(f"Error getting base URL: {e}")
            return "http://localhost:8080/"

    @staticmethod
    def _make_safe_filename(filename: str) -> str:
        """Make filename safe for URLs"""
        try:
            if not filename or filename == "Unknown":
                return ""

            # Remove or replace unsafe characters
            safe_chars = (
                "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_"
            )
            safe_filename = ""

            for char in filename:
                if char in safe_chars:
                    safe_filename += char
                elif char == " ":
                    safe_filename += "_"
                else:
                    safe_filename += "_"

            # Limit length
            if len(safe_filename) > 100:
                name_part, ext_part = (
                    safe_filename.rsplit(".", 1)
                    if "." in safe_filename
                    else (safe_filename, "")
                )
                max_name_length = 95 - len(ext_part)
                safe_filename = name_part[:max_name_length] + (
                    "." + ext_part if ext_part else ""
                )

            return safe_filename

        except Exception as e:
            LOGGER.error(f"Error making safe filename: {e}")
            return "file"

    @staticmethod
    def _is_valid_url(url: str) -> bool:
        """Validate URL format for Telegram buttons"""
        try:
            if not url or not isinstance(url, str):
                return False

            # Check if URL has proper protocol
            if not url.startswith(("http://", "https://", "tg://")):
                return False

            # Check for basic URL structure
            if len(url) < 10:  # Minimum reasonable URL length
                return False

            # Check for invalid characters that might cause BUTTON_URL_INVALID
            invalid_chars = [" ", "\n", "\r", "\t"]
            if any(char in url for char in invalid_chars):
                return False

            # Allow localhost URLs for VPS deployments without custom domains
            # Note: Telegram buttons won't work with localhost, but URLs are valid for direct access

            return True

        except Exception as e:
            LOGGER.error(f"Error validating URL: {e}")
            return False

    @staticmethod
    def parse_link_info(url: str) -> dict[str, str] | None:
        """Parse information from generated link"""
        try:
            # Extract hash and message ID from URL
            # Format: domain/hash+message_id/filename?hash=hash
            # or: domain/watch/hash+message_id/filename?hash=hash

            parts = url.split("/")
            if len(parts) < 4:
                return None

            # Check if it's a watch URL
            is_stream = "watch" in parts

            # Find the hash+message_id part
            hash_msg_part = None
            for part in parts:
                if part and len(part) >= 7:  # 6 char hash + at least 1 digit
                    # Check if it starts with hash pattern
                    if part[:6].isalnum():
                        hash_msg_part = part
                        break

            if not hash_msg_part:
                return None

            # Extract hash (first 6 characters) and message ID
            secure_hash = hash_msg_part[:6]
            message_id = hash_msg_part[6:]

            if not message_id.isdigit():
                return None

            return {
                "hash": secure_hash,
                "message_id": message_id,
                "is_stream": is_stream,
                "url": url,
            }

        except Exception as e:
            LOGGER.error(f"Error parsing link info: {e}")
            return None

    @staticmethod
    def validate_link(url: str, file_unique_id: str) -> bool:
        """Validate if link is valid for given file"""
        try:
            link_info = LinkGenerator.parse_link_info(url)
            if not link_info:
                return False

            return SecurityHandler.validate_hash(link_info["hash"], file_unique_id)

        except Exception as e:
            LOGGER.error(f"Error validating link: {e}")
            return False

    @staticmethod
    def generate_share_text(file_info: dict, links: dict[str, str]) -> str:
        """Generate formatted text for sharing links with enhanced media preview"""
        try:
            file_name = file_info.get("file_name", "Unknown")
            # Fix: Use file_size_human instead of formatted_size
            file_size = file_info.get(
                "file_size_human", file_info.get("formatted_size", "Unknown")
            )
            mime_type = file_info.get("mime_type", "Unknown")

            # Create a rich media description for better Telegram preview
            text = f"🎬 <b>{file_name}</b>\n\n"

            # Add media type specific emoji and description
            if file_info.get("is_video"):
                text += "🎥 <b>Video File</b>\n"
                if file_info.get("duration"):
                    duration = LinkGenerator._format_duration(
                        file_info.get("duration")
                    )
                    text += f"⏱️ Duration: <code>{duration}</code>\n"
            elif file_info.get("is_audio"):
                text += "🎵 <b>Audio File</b>\n"
                if file_info.get("duration"):
                    duration = LinkGenerator._format_duration(
                        file_info.get("duration")
                    )
                    text += f"⏱️ Duration: <code>{duration}</code>\n"
                if file_info.get("performer"):
                    text += f"🎤 Artist: <code>{file_info.get('performer')}</code>\n"
                if file_info.get("title"):
                    text += f"🎼 Title: <code>{file_info.get('title')}</code>\n"
            elif file_info.get("is_image"):
                text += "🖼️ <b>Image File</b>\n"
            else:
                text += "📄 <b>Document</b>\n"

            text += f"📦 Size: <code>{file_size}</code>\n"
            text += f"🏷️ Type: <code>{mime_type}</code>\n"

            # Add resolution if available for videos/images
            try:
                width_value = file_info.get("width", 0)
                height_value = file_info.get("height", 0)
                if (
                    width_value
                    and height_value
                    and float(width_value) > 0
                    and float(height_value) > 0
                ):
                    resolution = LinkGenerator._get_resolution_string(
                        width_value, height_value
                    )
                    if resolution != "Unknown":
                        text += f"📐 Resolution: <code>{resolution}</code>\n"
            except (ValueError, TypeError) as e:
                LOGGER.info(f"Error processing resolution: {e}")

            text += "\n<b>🔗 Quick Access:</b>\n"

            if "download" in links:
                text += f"📥 <a href='{links['download']}'>Download File</a>\n"

            if "stream" in links:
                if file_info.get("is_video"):
                    text += f"🎬 <a href='{links['stream']}'>Watch Online</a>\n"
                elif file_info.get("is_audio"):
                    text += f"🎵 <a href='{links['stream']}'>Listen Online</a>\n"
                else:
                    text += f"👁️ <a href='{links['stream']}'>View Online</a>\n"

            if Config.PERMANENT_LINKS:
                text += "\n<i>💎 These links are permanent and won't expire!</i>"
            else:
                text += "\n<i>⚡ Fast and secure streaming links</i>"

            return text

        except Exception as e:
            LOGGER.error(f"Error generating share text: {e}")
            return "Error generating share text"

    @staticmethod
    def _format_duration(duration_seconds: int) -> str:
        """Format duration in seconds to human readable format"""
        try:
            duration = int(float(duration_seconds))
            hours = duration // 3600
            minutes = (duration % 3600) // 60
            seconds = duration % 60

            if hours > 0:
                return f"{hours}:{minutes:02d}:{seconds:02d}"
            return f"{minutes}:{seconds:02d}"
        except (ValueError, TypeError):
            return "Unknown"

    @staticmethod
    def _get_resolution_string(width: int, height: int) -> str:
        """Get resolution string from width and height"""
        try:
            width = int(float(width))
            height = int(float(height))

            if width <= 0 or height <= 0:
                return "Unknown"

            # Common resolution names
            if width == 1920 and height == 1080:
                return "1080p (Full HD)"
            if width == 1280 and height == 720:
                return "720p (HD)"
            if width == 854 and height == 480:
                return "480p"
            if width == 640 and height == 360:
                return "360p"
            if width == 3840 and height == 2160:
                return "4K (2160p)"
            if width == 2560 and height == 1440:
                return "1440p (2K)"
            return f"{width}x{height}"
        except (ValueError, TypeError):
            return "Unknown"
