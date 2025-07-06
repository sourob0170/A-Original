"""
Quality Handler for Multiple Video Qualities System
Handles user-provided quality versions with smart grouping and management
"""

import re
import time
import uuid

from bot import LOGGER
from bot.core.aeon_client import TgClient


class QualityHandler:
    """Handle multiple quality uploads with smart grouping"""

    # Supported quality definitions with priority (lower = higher priority)
    SUPPORTED_QUALITIES = {
        "4k": {
            "height": 2160,
            "label": "4K",
            "priority": 1,
            "aliases": ["4k", "2160p", "uhd"],
        },
        "2k": {
            "height": 1440,
            "label": "2K",
            "priority": 2,
            "aliases": ["2k", "1440p", "qhd"],
        },
        "1080p": {
            "height": 1080,
            "label": "1080p",
            "priority": 3,
            "aliases": ["1080p", "1080", "fhd"],
        },
        "720p": {
            "height": 720,
            "label": "720p",
            "priority": 4,
            "aliases": ["720p", "720", "hd"],
        },
        "480p": {
            "height": 480,
            "label": "480p",
            "priority": 5,
            "aliases": ["480p", "480", "sd"],
        },
        "360p": {
            "height": 360,
            "label": "360p",
            "priority": 6,
            "aliases": ["360p", "360"],
        },
        "source": {
            "height": 0,
            "label": "Source",
            "priority": 0,
            "aliases": ["source", "original", "orig"],
        },
    }

    @staticmethod
    def parse_quality_flag(quality_input: str) -> str:
        """Parse and normalize quality input from -q flag"""
        if not quality_input:
            return "source"

        quality_input = quality_input.lower().strip()

        # Find matching quality by aliases
        for quality_key, quality_data in QualityHandler.SUPPORTED_QUALITIES.items():
            if quality_input in quality_data["aliases"]:
                return quality_key

        # If no match found, default to source
        LOGGER.warning(f"Unknown quality '{quality_input}', defaulting to 'source'")
        return "source"

    # Cache for base filename extraction
    _base_filename_cache = {}
    _cache_max_size = 1000

    @staticmethod
    def extract_base_filename(filename: str) -> str:
        """Extract base filename removing quality indicators and common patterns with caching"""
        if not filename:
            return ""

        # Check cache first
        if filename in QualityHandler._base_filename_cache:
            return QualityHandler._base_filename_cache[filename]

        # Remove file extension
        base_name = filename.rsplit(".", 1)[0] if "." in filename else filename

        # Optimized quality patterns to remove (case insensitive, reduced for efficiency)
        quality_patterns = [
            r"[\.\-\s_](4k|2160p|uhd)[\.\-\s_]*",
            r"[\.\-\s_](2k|1440p|qhd)[\.\-\s_]*",
            r"[\.\-\s_](1080p?|fhd)[\.\-\s_]*",
            r"[\.\-\s_](720p?|hd)[\.\-\s_]*",
            r"[\.\-\s_](480p?|sd)[\.\-\s_]*",
            r"[\.\-\s_](360p?)[\.\-\s_]*",
            # Common encoding/release patterns (reduced)
            r"[\.\-\s_](x264|x265|h264|h265|hevc)[\.\-\s_]*",
            r"[\.\-\s_](web-?dl|webrip|bluray|brrip|dvdrip)[\.\-\s_]*",
        ]

        for pattern in quality_patterns:
            base_name = re.sub(pattern, ".", base_name, flags=re.IGNORECASE)

        # Clean up multiple separators and normalize
        base_name = re.sub(r"[.\-\s_]+", ".", base_name).strip(".-_")
        result = base_name.lower()

        # Cache result with size management
        if (
            len(QualityHandler._base_filename_cache)
            >= QualityHandler._cache_max_size
        ):
            # Remove oldest entries (simple FIFO)
            keys_to_remove = list(QualityHandler._base_filename_cache.keys())[:100]
            for key in keys_to_remove:
                del QualityHandler._base_filename_cache[key]

        QualityHandler._base_filename_cache[filename] = result
        return result

    @staticmethod
    async def find_potential_quality_matches(
        file_info: dict, database
    ) -> list[dict]:
        """Find potential quality group matches based on filename and metadata with optimized queries"""
        try:
            base_name = QualityHandler.extract_base_filename(
                file_info.get("file_name", "")
            )
            if not base_name:
                return []

            # Duration tolerance (±5% or ±30 seconds, whichever is larger)
            duration = file_info.get("duration", 0)
            if duration > 0:
                duration_tolerance = max(duration * 0.05, 30)  # 5% or 30 seconds
                duration_min = duration - duration_tolerance
                duration_max = duration + duration_tolerance
            else:
                duration_min = duration_max = 0

            # Optimized search query with better indexing
            query = {
                "hash_id": {"$ne": file_info.get("hash_id", "")},
                "base_filename": {
                    "$regex": re.escape(base_name),
                    "$options": "i",
                },
            }

            # Add duration filter if available for better performance
            if duration > 0:
                query["duration"] = {"$gte": duration_min, "$lte": duration_max}

            # Limit search to prevent performance issues (reduced limit)
            cursor = (
                database.db.media_library[TgClient.ID]
                .find(
                    query,
                    {
                        "hash_id": 1,
                        "file_name": 1,
                        "duration": 1,
                        "quality_group_id": 1,
                        "file_size": 1,
                    },  # Only fetch needed fields
                )
                .limit(10)
            )  # Reduced limit for better performance
            potential_matches = await cursor.to_list(length=10)

            LOGGER.debug(
                f"Found {len(potential_matches)} potential quality matches for {base_name}"
            )
            return potential_matches

        except Exception as e:
            LOGGER.error(f"Error finding potential quality matches: {e}")
            return []

    @staticmethod
    async def create_or_join_quality_group(
        file_info: dict, quality: str, database, group_id: str | None = None
    ) -> str | None:
        """Create new quality group or join existing one"""
        try:
            # If group_id provided, try to join existing group
            if group_id:
                existing_group = await database.get_quality_group(group_id)
                if existing_group:
                    return await QualityHandler._add_to_existing_group(
                        existing_group, file_info, quality, database
                    )

            # Find potential matches for auto-grouping
            potential_matches = await QualityHandler.find_potential_quality_matches(
                file_info, database
            )

            if potential_matches:
                # Check if any matches are already in quality groups
                for match in potential_matches:
                    if match.get("quality_group_id"):
                        # Join existing group
                        existing_group = await database.get_quality_group(
                            match["quality_group_id"]
                        )
                        if existing_group:
                            return await QualityHandler._add_to_existing_group(
                                existing_group, file_info, quality, database
                            )

                # Create new group with all matches
                return await QualityHandler._create_new_quality_group(
                    [file_info, *potential_matches], database
                )

            # No matches found, store as single quality file
            await QualityHandler._store_single_quality_file(
                file_info, quality, database
            )
            return None

        except Exception as e:
            LOGGER.error(f"Error creating/joining quality group: {e}")
            return None

    @staticmethod
    async def _create_new_quality_group(files: list[dict], database) -> str:
        """Create new quality group from list of files"""
        try:
            group_id = str(uuid.uuid4())[:8]  # Short group ID

            # Determine group metadata from first file
            first_file = files[0]
            base_name = QualityHandler.extract_base_filename(
                first_file.get("file_name", "")
            )

            group_data = {
                "group_id": group_id,
                "base_name": base_name,
                "display_name": first_file.get("file_name", "").rsplit(".", 1)[
                    0
                ],  # Remove extension
                "qualities": {},
                "default_quality": None,
                "created_at": time.time(),
                "total_size": 0,
                "duration": first_file.get("duration", 0),
                "is_video": first_file.get("is_video", False),
                "category": first_file.get("category", "other"),
            }

            # Add each file to the group
            for file_info in files:
                # Determine quality from file info or detect from resolution/filename
                file_quality = file_info.get("quality_label") or file_info.get(
                    "quality"
                )
                if not file_quality:
                    # Try to detect from filename first, then resolution
                    filename_quality = QualityHandler.detect_quality_from_filename(
                        file_info.get("file_name", "")
                    )
                    if filename_quality != "source":
                        file_quality = filename_quality
                    else:
                        file_quality = (
                            QualityHandler._detect_quality_from_resolution(file_info)
                        )

                group_data["qualities"][file_quality] = {
                    "hash_id": file_info.get("hash_id", ""),
                    "file_name": file_info.get("file_name", ""),
                    "file_size": file_info.get("file_size", 0),
                    "file_id": file_info.get("file_id", ""),
                    "message_id": file_info.get("message_id", 0),
                    "resolution": file_info.get("resolution", ""),
                    "width": file_info.get("width", 0),
                    "height": file_info.get("height", 0),
                    "duration": file_info.get("duration", 0),
                    "mime_type": file_info.get("mime_type", ""),
                    "added_at": time.time(),
                }
                group_data["total_size"] += file_info.get("file_size", 0)

            # Set default quality (highest available)
            available_qualities = list(group_data["qualities"].keys())
            if available_qualities:
                quality_priorities = {
                    q: QualityHandler.SUPPORTED_QUALITIES.get(q, {"priority": 999})[
                        "priority"
                    ]
                    for q in available_qualities
                }
                group_data["default_quality"] = min(
                    quality_priorities, key=quality_priorities.get
                )

            # Store group in database
            await database.store_quality_group(group_data)

            # Update individual media entries with group reference
            for quality_key, file_data in group_data["qualities"].items():
                await database.update_media_quality_group(
                    file_data["hash_id"],
                    group_id,
                    quality_key,
                    group_data["default_quality"],
                )

            LOGGER.info(
                f"Created quality group {group_id} with {len(group_data['qualities'])} qualities"
            )
            return group_id

        except Exception as e:
            LOGGER.error(f"Error creating new quality group: {e}")
            return None

    @staticmethod
    async def _add_to_existing_group(
        group_data: dict, file_info: dict, quality: str, database
    ) -> str:
        """Add file to existing quality group"""
        try:
            group_id = group_data["group_id"]

            # Check if quality already exists in group
            if quality in group_data["qualities"]:
                LOGGER.warning(
                    f"Quality {quality} already exists in group {group_id}, skipping"
                )
                return group_id

            # Add new quality to group
            group_data["qualities"][quality] = {
                "hash_id": file_info.get("hash_id", ""),
                "file_name": file_info.get("file_name", ""),
                "file_size": file_info.get("file_size", 0),
                "file_id": file_info.get("file_id", ""),
                "message_id": file_info.get("message_id", 0),
                "resolution": file_info.get("resolution", ""),
                "width": file_info.get("width", 0),
                "height": file_info.get("height", 0),
                "duration": file_info.get("duration", 0),
                "mime_type": file_info.get("mime_type", ""),
                "added_at": time.time(),
            }

            # Update group metadata
            group_data["total_size"] += file_info.get("file_size", 0)
            group_data["last_updated"] = time.time()

            # Recalculate default quality if needed
            available_qualities = list(group_data["qualities"].keys())
            quality_priorities = {
                q: QualityHandler.SUPPORTED_QUALITIES.get(q, {"priority": 999})[
                    "priority"
                ]
                for q in available_qualities
            }
            group_data["default_quality"] = min(
                quality_priorities, key=quality_priorities.get
            )

            # Update group in database
            await database.update_quality_group(group_data)

            # Update media entry with group reference
            await database.update_media_quality_group(
                file_info.get("hash_id", ""),
                group_id,
                quality,
                group_data["default_quality"],
            )

            LOGGER.info(f"Added {quality} quality to existing group {group_id}")
            return group_id

        except Exception as e:
            LOGGER.error(f"Error adding to existing quality group: {e}")
            return None

    @staticmethod
    async def _store_single_quality_file(file_info: dict, quality: str, database):
        """Store file as single quality (not part of group)"""
        try:
            # Update media entry with quality info but no group
            await database.update_media_quality_info(
                file_info.get("hash_id", ""),
                quality,
                QualityHandler.extract_base_filename(file_info.get("file_name", "")),
            )

            LOGGER.info(f"Stored single quality file: {quality}")

        except Exception as e:
            LOGGER.error(f"Error storing single quality file: {e}")

    @staticmethod
    def detect_quality_from_filename(filename: str) -> str:
        """Detect quality from filename patterns"""
        if not filename:
            return "source"

        filename_lower = filename.lower()

        # Check for quality patterns in filename
        quality_patterns = [
            (r"4k|2160p|uhd", "4k"),
            (r"2k|1440p|qhd", "2k"),
            (r"1080p?|fhd", "1080p"),
            (r"720p?|hd", "720p"),
            (r"480p?|sd", "480p"),
            (r"360p?", "360p"),
        ]

        for pattern, quality in quality_patterns:
            if re.search(r"[\.\-\s_](" + pattern + r")[\.\-\s_]", filename_lower):
                return quality

        return "source"

    @staticmethod
    def _detect_quality_from_resolution(file_info: dict) -> str:
        """Detect quality from video resolution"""
        height = file_info.get("height", 0)

        if height >= 2160:
            return "4k"
        if height >= 1440:
            return "2k"
        if height >= 1080:
            return "1080p"
        if height >= 720:
            return "720p"
        if height >= 480:
            return "480p"
        if height >= 360:
            return "360p"
        return "source"

    @staticmethod
    def get_quality_display_info(quality: str) -> dict:
        """Get display information for a quality"""
        quality_data = QualityHandler.SUPPORTED_QUALITIES.get(quality, {})
        return {
            "label": quality_data.get("label", quality.upper()),
            "height": quality_data.get("height", 0),
            "priority": quality_data.get("priority", 999),
        }
