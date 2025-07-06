import mimetypes
import re
from pathlib import Path
from typing import ClassVar

from pyrogram.types import Message

from bot import LOGGER
from bot.helper.ext_utils.status_utils import get_readable_file_size


class FileProcessor:
    """Optimized file processing with reduced memory usage and faster extraction"""

    # Optimized MIME type sets with most common types first for faster lookup
    SUPPORTED_VIDEO_TYPES: ClassVar[frozenset[str]] = frozenset(
        {
            "video/mp4",
            "video/webm",
            "video/mkv",
            "video/avi",
            "video/mov",
            "video/x-matroska",
            "video/quicktime",
            "video/x-msvideo",
            "video/wmv",
            "video/flv",
            "video/3gp",
            "video/m4v",
            "video/mpg",
            "video/mpeg",
            "video/ogv",
            "video/ts",
            "video/x-ms-wmv",
            "video/x-flv",
            "video/mp2t",
        }
    )

    SUPPORTED_AUDIO_TYPES: ClassVar[frozenset[str]] = frozenset(
        {
            "audio/mp3",
            "audio/mpeg",
            "audio/wav",
            "audio/flac",
            "audio/aac",
            "audio/ogg",
            "audio/m4a",
            "audio/mp4",
            "audio/webm",
            "audio/opus",
            "audio/wma",
            "audio/x-wav",
            "audio/x-flac",
            "audio/x-ms-wma",
            "audio/x-m4a",
        }
    )

    SUPPORTED_IMAGE_TYPES: ClassVar[frozenset[str]] = frozenset(
        {
            "image/jpeg",
            "image/jpg",
            "image/png",
            "image/gif",
            "image/webp",
            "image/bmp",
            "image/tiff",
            "image/svg+xml",
        }
    )

    # Optimized caching with size limits to prevent memory bloat
    _mime_cache: ClassVar[dict[str, str]] = {}
    _cache_max_size: ClassVar[int] = 500  # Reduced cache size
    _streamable_types: ClassVar[frozenset[str]] = None

    @classmethod
    def _init_streamable_types(cls):
        """Initialize streamable types cache"""
        if cls._streamable_types is None:
            cls._streamable_types = (
                cls.SUPPORTED_VIDEO_TYPES | cls.SUPPORTED_AUDIO_TYPES
            )

    @staticmethod
    def extract_file_info(message: Message) -> dict | None:
        """Optimized file information extraction with caching and minimal processing"""
        try:
            # Initialize streamable types cache
            FileProcessor._init_streamable_types()

            media = FileProcessor._get_media_from_message(message)
            if not media:
                return None

            # Get basic file info with optimized attribute access
            file_name = getattr(media, "file_name", "Unknown")
            mime_type = getattr(media, "mime_type", "")
            file_size = getattr(media, "file_size", 0)

            # Optimized MIME type detection with caching
            if not mime_type or mime_type == "application/octet-stream":
                if file_name and file_name != "Unknown":
                    mime_type = FileProcessor.guess_mime_type_cached(file_name)
                else:
                    mime_type = "application/octet-stream"

            # Fast media type determination
            media_type = FileProcessor._determine_media_type_fast(message)
            is_video = media_type == "video"
            is_audio = media_type == "audio"
            is_image = media_type == "photo"

            # Enhanced thumbnail extraction with automatic generation
            thumbnail = FileProcessor._extract_thumbnail_enhanced(media)

            # Fast resolution processing
            width = getattr(media, "width", 0)
            height = getattr(media, "height", 0)
            resolution = f"{width}x{height}" if width and height else None

            # Pre-calculate readable size once with fallback
            readable_size = (
                get_readable_file_size(file_size) if file_size > 0 else "Unknown"
            )

            # Build optimized file info dict with only essential fields
            file_info = {
                "file_id": media.file_id,
                "file_unique_id": media.file_unique_id,
                "unique_id": media.file_unique_id,  # Alias for compatibility
                "file_name": file_name,
                "file_size": file_size,
                "file_size_human": readable_size,
                "formatted_size": readable_size,  # Add alias for compatibility
                "mime_type": mime_type,
                "media_type": media_type,
                "is_video": is_video,
                "is_audio": is_audio,
                "is_image": is_image,
                "is_streamable": FileProcessor._is_streamable_fast(mime_type),
                "duration": getattr(media, "duration", 0),
                "width": width,
                "height": height,
                "resolution": resolution,
                "thumbnail": thumbnail,
            }

            # Add optional metadata only if present (reduces dict size)
            performer = getattr(media, "performer", None)
            if performer:
                file_info["performer"] = performer
            title = getattr(media, "title", None)
            if title:
                file_info["title"] = title

            return file_info

        except Exception as e:
            LOGGER.error(f"Error extracting file info: {e}")
            return None

    @staticmethod
    async def extract_reelnn_metadata(
        message: Message,
        file_info: dict,
        category: str | None = None,
        quality: str | None = None,
        season: str | None = None,
        episode: str | None = None,
        unique_name: str | None = None,
    ) -> dict:
        """Extract metadata using ReelNN's exact processing pipeline"""
        try:
            from bot.helper.stream_utils.tmdb_helper import TMDBHelper

            # Start with file info
            metadata = file_info.copy()

            # Extract title from filename - ReelNN style
            filename = file_info.get("file_name", "")
            clean_title = FileProcessor._extract_title_reelnn(filename)

            # Determine media type - ReelNN logic
            is_tv_show = FileProcessor._detect_tv_show_reelnn(
                filename, season, episode
            )
            media_type = "tv" if is_tv_show else "movie"

            # Extract year from filename
            year = FileProcessor._extract_year_reelnn(filename)

            # Get TMDB data using ReelNN's exact approach
            tmdb_data = {}
            try:
                if media_type == "movie":
                    tmdb_result = await TMDBHelper.search_movie(clean_title, year)
                    if tmdb_result:
                        tmdb_data = tmdb_result
                        LOGGER.info(f"✅ Found TMDB movie data for: {clean_title}")
                else:
                    tmdb_result = await TMDBHelper.search_tv_show(clean_title, year)
                    if tmdb_result:
                        tmdb_data = tmdb_result
                        LOGGER.info(f"✅ Found TMDB TV show data for: {clean_title}")

                if not tmdb_data:
                    LOGGER.warning(f"⚠️ No TMDB data found for: {clean_title}")

            except Exception as e:
                LOGGER.error(f"❌ Error fetching TMDB data for {clean_title}: {e}")
                tmdb_data = {}

            # Build ReelNN metadata structure
            metadata.update(
                {
                    "enhanced_title": clean_title,
                    "media_type": media_type,
                    "is_series": is_tv_show,
                    "season": season,
                    "episode": episode,
                    "unique_name": unique_name or clean_title,
                    "category": category or media_type,
                    "quality": quality
                    or FileProcessor._extract_quality_reelnn(filename),
                    "year": year,
                    "tmdb_data": tmdb_data or {},
                    "is_streamable": file_info.get("is_video", False),
                    "indexed_at": message.date.timestamp() if message.date else None,
                    "message_id": message.id,
                    "chat_id": message.chat.id if message.chat else None,
                }
            )

            # Add series data for TV shows
            if is_tv_show:
                metadata["series_data"] = {
                    "series_name": unique_name or clean_title,
                    "season_number": season,
                    "episode_number": episode,
                    "media_type": "tv",
                }

            return metadata

        except Exception as e:
            LOGGER.error(f"Error extracting ReelNN metadata: {e}")
            return file_info

    @staticmethod
    def _extract_title_reelnn(filename: str) -> str:
        """Extract clean title from filename using ReelNN patterns"""
        if not filename:
            return "Unknown"

        # Remove file extension
        title = filename.rsplit(".", 1)[0] if "." in filename else filename

        # ReelNN title cleaning patterns
        # Remove quality indicators
        quality_patterns = [
            r"\b(2160p|1080p|720p|480p|360p)\b",
            r"\b(4K|UHD|FHD|HD|SD)\b",
            r"\b(BluRay|BDRip|BRRip|DVDRip|WEBRip|WEB-DL)\b",
            r"\b(x264|x265|H\.264|H\.265|HEVC)\b",
            r"\b(AAC|AC3|DTS|MP3)\b",
            r"\[.*?\]",  # Remove bracketed content
            r"\(.*?\)",  # Remove parenthetical content
        ]

        for pattern in quality_patterns:
            title = re.sub(pattern, "", title, flags=re.IGNORECASE)

        # Clean up spacing and special characters
        title = re.sub(r"[._-]+", " ", title)
        title = re.sub(r"\s+", " ", title).strip()

        return title or "Unknown"

    @staticmethod
    def _detect_tv_show_reelnn(
        filename: str, season: str | None = None, episode: str | None = None
    ) -> bool:
        """Detect if content is a TV show using ReelNN logic"""
        if season or episode:
            return True

        if not filename:
            return False

        filename_lower = filename.lower()

        # ReelNN TV show detection patterns
        tv_patterns = [
            r"s\d{1,2}e\d{1,2}",  # S01E01 format
            r"season\s*\d+",  # Season X
            r"episode\s*\d+",  # Episode X
            r"\bs\d{1,2}\b",  # S01, S02, etc.
            r"\be\d{1,2}\b",  # E01, E02, etc.
        ]

        return any(re.search(pattern, filename_lower) for pattern in tv_patterns)

    @staticmethod
    def _extract_year_reelnn(filename: str) -> int:
        """Extract year from filename using ReelNN patterns"""
        if not filename:
            return None

        # Look for 4-digit year (1900-2099)
        year_match = re.search(r"\b(19\d{2}|20\d{2})\b", filename)
        if year_match:
            return int(year_match.group(1))

        return None

    @staticmethod
    def _extract_quality_reelnn(filename: str) -> str:
        """Extract quality from filename using ReelNN patterns"""
        if not filename:
            return "HD"

        filename_lower = filename.lower()

        # ReelNN quality detection
        quality_map = {
            "2160p": "4K",
            "4k": "4K",
            "uhd": "4K",
            "1080p": "1080p",
            "fhd": "1080p",
            "720p": "720p",
            "hd": "720p",
            "480p": "480p",
            "sd": "480p",
            "360p": "360p",
            "cam": "CAM",
            "ts": "TS",
            "tc": "TC",
            "webrip": "WEBRip",
            "web-dl": "WEB-DL",
            "bluray": "BluRay",
            "bdrip": "BluRay",
            "dvdrip": "DVDRip",
        }

        for pattern, quality in quality_map.items():
            if pattern in filename_lower:
                return quality

        return "HD"

    @staticmethod
    def _get_media_from_message(message: Message):
        """Optimized media extraction with priority order"""
        # Check most common types first for better performance
        if message.document:
            return message.document
        if message.video:
            return message.video
        if message.audio:
            return message.audio
        if message.photo:
            return message.photo
        if message.animation:
            return message.animation
        if message.voice:
            return message.voice
        if message.video_note:
            return message.video_note
        if message.sticker:
            return message.sticker
        return None

    @staticmethod
    def _determine_media_type_fast(message: Message) -> str:
        """Fast media type determination with optimized checks"""
        # Use direct attribute access for speed
        if message.video:
            return "video"
        if message.audio:
            return "audio"
        if message.photo:
            return "photo"
        if message.document:
            return "document"
        if message.voice:
            return "voice"
        if message.video_note:
            return "video_note"
        if message.animation:
            return "animation"
        if message.sticker:
            return "sticker"
        return "unknown"

    @staticmethod
    def _extract_thumbnail_enhanced(media):
        """Enhanced thumbnail extraction with automatic generation for audio and other media"""
        # Check existing thumbs first (most common)
        if hasattr(media, "thumbs") and media.thumbs:
            return media.thumbs[-1].file_id
        # Check thumb attribute
        if hasattr(media, "thumb") and media.thumb:
            return media.thumb.file_id

        # For audio files without thumbnails, return None instead of placeholder
        # The website will handle default thumbnails based on media type
        if (
            hasattr(media, "mime_type")
            and media.mime_type
            and media.mime_type.startswith("audio/")
        ):
            return None

        # For video files without thumbnails, return None instead of placeholder
        # The website will handle default thumbnails based on media type
        if (
            hasattr(media, "mime_type")
            and media.mime_type
            and media.mime_type.startswith("video/")
        ):
            return None

        # For other media types, return None
        return None

    @staticmethod
    def _extract_thumbnail_fast(media):
        """Fast thumbnail extraction (legacy method for compatibility)"""
        # Check thumbs first (most common)
        if hasattr(media, "thumbs") and media.thumbs:
            return media.thumbs[-1].file_id
        # Check thumb attribute
        if hasattr(media, "thumb") and media.thumb:
            return media.thumb.file_id
        return None

    @staticmethod
    def _is_streamable_fast(mime_type: str) -> bool:
        """Optimized streamable check using cached frozenset"""
        FileProcessor._init_streamable_types()
        return mime_type in FileProcessor._streamable_types or mime_type.startswith(
            ("video/", "audio/")
        )

    @staticmethod
    def guess_mime_type_cached(filename: str) -> str:
        """Cached MIME type guessing with size-limited cache to prevent memory bloat"""
        # Check cache first
        if filename in FileProcessor._mime_cache:
            return FileProcessor._mime_cache[filename]

        # Get file extension for faster lookup
        ext = Path(filename).suffix.lower()
        if ext in FileProcessor._mime_cache:
            mime_type = FileProcessor._mime_cache[ext]
        else:
            mime_type, _ = mimetypes.guess_type(filename)
            mime_type = mime_type or "application/octet-stream"

            # Manage cache size to prevent memory bloat
            if len(FileProcessor._mime_cache) >= FileProcessor._cache_max_size:
                # Remove oldest entries (simple FIFO)
                keys_to_remove = list(FileProcessor._mime_cache.keys())[:100]
                for key in keys_to_remove:
                    del FileProcessor._mime_cache[key]

            # Cache by extension for future lookups
            FileProcessor._mime_cache[ext] = mime_type

        # Cache full filename too
        FileProcessor._mime_cache[filename] = mime_type
        return mime_type

    @staticmethod
    def _is_streamable(media) -> bool:
        """Check if media is streamable"""
        mime_type = getattr(media, "mime_type", "")

        # If no MIME type, try to guess from filename
        if not mime_type or mime_type == "application/octet-stream":
            filename = getattr(media, "file_name", "")
            if filename:
                mime_type = FileProcessor.guess_mime_type(filename)

        # Check if it's a supported streamable type
        return (
            mime_type in FileProcessor.SUPPORTED_VIDEO_TYPES
            or mime_type in FileProcessor.SUPPORTED_AUDIO_TYPES
            or mime_type.startswith(
                ("video/", "audio/")
            )  # Catch any video/* or audio/* types
        )

    @staticmethod
    def get_file_extension(filename: str) -> str:
        """Get file extension from filename"""
        return Path(filename).suffix.lower() if filename else ""

    @staticmethod
    def guess_mime_type(filename: str) -> str:
        """Guess MIME type from filename"""
        mime_type, _ = mimetypes.guess_type(filename)
        return mime_type or "application/octet-stream"

    @staticmethod
    def is_supported_format(mime_type: str) -> bool:
        """Check if format is supported for streaming"""
        return (
            mime_type in FileProcessor.SUPPORTED_VIDEO_TYPES
            or mime_type in FileProcessor.SUPPORTED_AUDIO_TYPES
            or mime_type in FileProcessor.SUPPORTED_IMAGE_TYPES
        )

    @staticmethod
    def format_duration(seconds) -> str:
        """Format duration in human readable format"""
        try:
            # Convert to int to handle both int and float values
            seconds = int(float(seconds))
        except (ValueError, TypeError):
            return "Unknown"

        if seconds <= 0:
            return "Unknown"

        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60

        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"

    @staticmethod
    def get_resolution_string(width, height) -> str:
        """Get resolution string"""
        try:
            # Convert to int to handle both int and float values
            width = int(float(width))
            height = int(float(height))
        except (ValueError, TypeError):
            return "Unknown"

        if width <= 0 or height <= 0:
            return "Unknown"
        return f"{width}x{height}"

    @staticmethod
    def get_quality_label(width, height) -> str:
        """Get quality label based on resolution"""
        try:
            # Convert to int to handle both int and float values
            width = int(float(width))
            height = int(float(height))
        except (ValueError, TypeError):
            return "Unknown"

        if width <= 0 or height <= 0:
            return "Unknown"

        if height >= 2160:
            return "4K"
        if height >= 1440:
            return "2K"
        if height >= 1080:
            return "1080p"
        if height >= 720:
            return "720p"
        if height >= 480:
            return "480p"
        if height >= 360:
            return "360p"
        return "Low Quality"

    @staticmethod
    def estimate_bitrate(file_size, duration) -> str:
        """Estimate bitrate from file size and duration"""
        try:
            # Convert to appropriate types to handle both int and float values
            file_size = int(float(file_size))
            duration = float(duration)
        except (ValueError, TypeError):
            return "Unknown"

        if duration <= 0 or file_size <= 0:
            return "Unknown"

        # Calculate bitrate in kbps
        bitrate_bps = (file_size * 8) / duration
        bitrate_kbps = bitrate_bps / 1000

        if bitrate_kbps >= 1000:
            return f"{bitrate_kbps / 1000:.1f} Mbps"
        return f"{bitrate_kbps:.0f} kbps"

    @staticmethod
    def get_file_category(mime_type: str) -> str:
        """Get file category from MIME type"""
        if mime_type.startswith("video/"):
            return "video"
        if mime_type.startswith("audio/"):
            return "audio"
        if mime_type.startswith("image/"):
            return "image"
        if mime_type.startswith("text/"):
            return "text"
        if "pdf" in mime_type:
            return "pdf"
        if any(
            archive in mime_type for archive in ["zip", "rar", "7z", "tar", "gz"]
        ):
            return "archive"
        return "document"
