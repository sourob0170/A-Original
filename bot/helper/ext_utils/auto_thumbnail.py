"""
Auto Thumbnail Helper Module
Automatically fetches movie/TV show thumbnails from IMDB and TMDB based on filename metadata
"""

import asyncio
import os
import re

# TMDB functionality moved here from stream_utils
from datetime import datetime, timedelta
from os import path as ospath
from time import time

import aiohttp
from aiofiles import open as aioopen

from bot import LOGGER
from bot.core.config_manager import Config

# Use compatibility layer for aiofiles
from bot.helper.ext_utils.aiofiles_compat import aiopath, makedirs, remove
from bot.helper.ext_utils.template_processor import extract_metadata_from_filename


class AutoThumbnailHelper:
    """Helper class for automatically fetching thumbnails from IMDB/TMDB"""

    THUMBNAIL_DIR = "thumbnails/auto"
    CACHE_DURATION = 86400  # 24 hours
    MAX_CACHE_SIZE = 100  # Maximum number of cached thumbnails

    @classmethod
    async def get_auto_thumbnail(
        cls, filename: str, user_id: int | None = None
    ) -> str | None:
        """
        Get auto thumbnail for a file based on its metadata

        Args:
            filename: The filename to extract metadata from
            user_id: User ID for cache organization (optional)

        Returns:
            Path to downloaded thumbnail or None if not found
        """
        try:
            if not Config.AUTO_THUMBNAIL:
                return None

            # Extract metadata from filename
            metadata = await extract_metadata_from_filename(filename)
            if not metadata:
                return None

            # Clean title for search
            clean_title = cls._extract_clean_title(filename)
            if not clean_title or len(clean_title) < 3:
                LOGGER.info(f"Title too short or empty: {clean_title}")
                return None

            year = metadata.get("year")
            season = metadata.get("season")
            episode = metadata.get("episode")

            LOGGER.info(
                f"🎬 Auto thumbnail search: '{clean_title}' (year: {year}, S{season}E{episode})"
            )

            # Determine if it's a TV show or movie
            is_tv_show = bool(season or episode or cls._detect_tv_patterns(filename))

            # Try to get thumbnail from cache first
            cache_key = cls._generate_cache_key(clean_title, year, is_tv_show)
            cached_thumbnail = await cls._get_cached_thumbnail(cache_key)
            if cached_thumbnail:
                LOGGER.info(f"✅ Using cached thumbnail for: {clean_title}")
                return cached_thumbnail

            # Try TMDB first (better quality images)
            thumbnail_url = None
            search_title = clean_title

            # For TV shows, also try with just the main title (before any episode info)
            if is_tv_show:
                # Extract just the main series name
                main_title = re.split(
                    r"\s+S\d+E\d+|\s+Season|\s+Episode",
                    clean_title,
                    flags=re.IGNORECASE,
                )[0].strip()
                if main_title and main_title != clean_title:
                    search_title = main_title
                    LOGGER.info(
                        f"🔍 Using main series title for search: '{search_title}'"
                    )

            if Config.TMDB_API_KEY and Config.TMDB_ENABLED:
                thumbnail_url = await cls._get_tmdb_thumbnail(
                    search_title, year, is_tv_show
                )

                # If no result with main title, try original clean title
                if not thumbnail_url and search_title != clean_title:
                    LOGGER.info(f"🔄 Retrying TMDB with full title: '{clean_title}'")
                    thumbnail_url = await cls._get_tmdb_thumbnail(
                        clean_title, year, is_tv_show
                    )

            # Fallback to IMDB if TMDB fails
            if not thumbnail_url and Config.IMDB_ENABLED:
                LOGGER.info(f"🔄 Trying IMDB fallback for: '{search_title}'")
                thumbnail_url = await cls._get_imdb_thumbnail(search_title, year)

                # If no result with main title, try original clean title
                if not thumbnail_url and search_title != clean_title:
                    LOGGER.info(f"🔄 Retrying IMDB with full title: '{clean_title}'")
                    thumbnail_url = await cls._get_imdb_thumbnail(clean_title, year)

            if not thumbnail_url:
                LOGGER.info(
                    f"❌ No thumbnail found for: '{search_title}' (original: '{clean_title}')"
                )
                return None

            # Download and cache the thumbnail
            thumbnail_path = await cls._download_thumbnail(thumbnail_url, cache_key)
            if thumbnail_path:
                LOGGER.info(f"✅ Auto thumbnail downloaded for: {clean_title}")
                return thumbnail_path

            return None

        except Exception as e:
            LOGGER.error(f"Error getting auto thumbnail for {filename}: {e}")
            return None

    @classmethod
    def _extract_clean_title(cls, filename: str) -> str:
        """Extract clean title from filename for search"""
        if not filename:
            return ""

        # Remove file extension
        title = filename.rsplit(".", 1)[0] if "." in filename else filename
        original_title = title

        # First, extract year and preserve it
        year_match = re.search(r"\b(19|20)\d{2}\b", title)
        year = year_match.group(0) if year_match else None

        # Replace dots, underscores, and dashes with spaces first
        title = re.sub(r"[._-]+", " ", title)

        # For TV shows, extract just the series name (everything before season/episode info)
        tv_patterns = [
            r"\bS\d{1,2}E\d{1,3}\b",  # S01E01
            r"\bSeason\s*\d+\b",  # Season 1
            r"\bEpisode\s*\d+\b",  # Episode 1
            r"\b\d{1,2}x\d{1,3}\b",  # 1x01
        ]

        is_tv_show = False
        for pattern in tv_patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                # Take everything before the season/episode info
                title = title[: match.start()].strip()
                is_tv_show = True
                break

        # Remove quality and technical indicators (but be more careful)
        patterns_to_remove = [
            r"\b(2160p|1080p|720p|480p|360p|4K|UHD|FHD|HD|SD)\b",
            r"\b(BluRay|BDRip|BRRip|DVDRip|WEBRip|WEB-DL|HDTV|PDTV)\b",
            r"\b(x264|x265|H\.264|H\.265|HEVC|AVC|XVID)\b",
            r"\b(AAC|AC3|DTS|MP3|FLAC|OPUS)\b",
            r"\b(PROPER|REPACK|INTERNAL|LIMITED|EXTENDED|UNRATED)\b",
            r"\b(AMZN|NF|HULU|DSNP|HBO|MAX|ATVP)\b",  # Streaming services
            r"\[.*?\]",  # Remove bracketed content
            r"\b\d+\.\d+\b",  # Remove version numbers like 2.0, 5.1
        ]

        # Only remove these patterns if they appear after the main title
        for pattern in patterns_to_remove:
            title = re.sub(pattern, "", title, flags=re.IGNORECASE)

        # Remove specific technical terms that might remain
        tech_terms = [
            "CR",
            "WEB",
            "DL",
            "DUAL",
            "AAC2",
            "DDP",
            "GROUP",
            "RARBG",
            "YTS",
            "YIFY",
        ]
        for term in tech_terms:
            title = re.sub(rf"\b{re.escape(term)}\b", "", title, flags=re.IGNORECASE)

        # Clean up spacing
        title = re.sub(r"\s+", " ", title).strip()

        # If title is empty or too short, try a different approach
        if not title or len(title) < 3:
            # Fallback: take first few words before any technical indicators
            words = (
                original_title.replace(".", " ")
                .replace("_", " ")
                .replace("-", " ")
                .split()
            )
            title_words = []
            for word in words:
                # Stop at technical indicators
                if re.match(
                    r"(S\d+E\d+|\d{3,4}p|x264|x265|BluRay|WEBRip|HDTV)",
                    word,
                    re.IGNORECASE,
                ):
                    break
                if not re.match(r"^\d{4}$", word):  # Skip standalone years for now
                    title_words.append(word)
                if len(title_words) >= 4:  # Limit to reasonable title length
                    break
            title = " ".join(title_words)

        # Add year back if it was found and format it properly for movies
        if year and not is_tv_show:  # Don't add year to TV shows
            # Check if year is already in parentheses
            if f"({year})" not in title:
                # Remove standalone year if it exists and add it in parentheses
                title = re.sub(rf"\b{re.escape(year)}\b", "", title).strip()
                title = f"{title} ({year})"

        return title.strip()

    @classmethod
    def _detect_tv_patterns(cls, filename: str) -> bool:
        """Detect if filename indicates a TV show"""
        if not filename:
            return False

        tv_patterns = [
            r"S\d{1,2}E\d{1,3}",  # S01E01
            r"Season\s*\d+",  # Season 1
            r"Episode\s*\d+",  # Episode 1
            r"\d{1,2}x\d{1,3}",  # 1x01
        ]

        return any(
            re.search(pattern, filename, re.IGNORECASE) for pattern in tv_patterns
        )

    @classmethod
    async def _get_tmdb_thumbnail(
        cls, title: str, year: int | None = None, is_tv_show: bool = False
    ) -> str | None:
        """Get thumbnail URL from TMDB"""
        try:
            if is_tv_show:
                result = await TMDBHelper.search_tv_show(title, year)
            else:
                result = await TMDBHelper.search_movie(title, year)

            if result and result.get("poster_path"):
                return TMDBHelper.get_poster_url(result["poster_path"], "w500")

            return None

        except Exception as e:
            LOGGER.error(f"Error getting TMDB thumbnail for {title}: {e}")
            return None

    @classmethod
    async def _get_imdb_thumbnail(
        cls, title: str, year: int | None = None
    ) -> str | None:
        """Get thumbnail URL from IMDB"""
        try:
            # Dynamic import to avoid circular imports
            from bot.modules.imdb import get_poster

            # Clean title for IMDB search (remove parentheses with year)
            clean_search_title = re.sub(r"\s*\(\d{4}\)\s*", "", title).strip()

            # Use the existing IMDB helper
            search_query = (
                f"{clean_search_title} {year}" if year else clean_search_title
            )
            LOGGER.info(f"🔍 IMDB search query: '{search_query}'")

            imdb_data = await asyncio.get_event_loop().run_in_executor(
                None, get_poster, search_query, False, False
            )

            if imdb_data and imdb_data.get("poster"):
                LOGGER.info(f"✅ Found IMDB poster for: {clean_search_title}")
                return imdb_data["poster"]

            LOGGER.info(f"❌ No IMDB poster found for: {clean_search_title}")
            return None

        except Exception as e:
            LOGGER.error(f"Error getting IMDB thumbnail for {title}: {e}")
            return None

    @classmethod
    def _generate_cache_key(
        cls, title: str, year: int | None = None, is_tv_show: bool = False
    ) -> str:
        """Generate cache key for thumbnail"""
        key_parts = [title.lower().replace(" ", "_")]
        if year:
            key_parts.append(str(year))
        if is_tv_show:
            key_parts.append("tv")
        else:
            key_parts.append("movie")

        return "_".join(key_parts)

    @classmethod
    async def _get_cached_thumbnail(cls, cache_key: str) -> str | None:
        """Get cached thumbnail if it exists and is not expired"""
        try:
            await makedirs(cls.THUMBNAIL_DIR, exist_ok=True)
            cache_file = ospath.join(cls.THUMBNAIL_DIR, f"{cache_key}.jpg")

            if await aiopath.exists(cache_file):
                # Check if cache is still valid
                file_time = await aiopath.getmtime(cache_file)
                if time() - file_time < cls.CACHE_DURATION:
                    return cache_file
                # Remove expired cache
                await remove(cache_file)

            return None

        except Exception as e:
            LOGGER.error(f"Error checking cached thumbnail: {e}")
            return None

    @classmethod
    async def _download_thumbnail(cls, url: str, cache_key: str) -> str | None:
        """Download thumbnail and save to cache"""
        try:
            await makedirs(cls.THUMBNAIL_DIR, exist_ok=True)
            cache_file = ospath.join(cls.THUMBNAIL_DIR, f"{cache_key}.jpg")

            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        content = await response.read()
                        async with aioopen(cache_file, "wb") as f:
                            await f.write(content)

                        LOGGER.info(f"📥 Downloaded thumbnail: {cache_file}")

                        # Clean up old cache files if needed
                        await cls._cleanup_cache()

                        return cache_file

            return None

        except Exception as e:
            LOGGER.error(f"Error downloading thumbnail from {url}: {e}")
            return None

    @classmethod
    async def _cleanup_cache(cls) -> None:
        """Clean up old cache files to maintain cache size limit"""
        try:
            if not await aiopath.exists(cls.THUMBNAIL_DIR):
                return

            # Get all cache files with their modification times
            cache_files = []

            # Use synchronous os.listdir since aiopath doesn't have iterdir
            try:
                entries = os.listdir(cls.THUMBNAIL_DIR)
                for entry in entries:
                    if entry.endswith(".jpg"):
                        file_path = ospath.join(cls.THUMBNAIL_DIR, entry)
                        if await aiopath.exists(file_path):
                            mtime = await aiopath.getmtime(file_path)
                            cache_files.append((file_path, mtime))
            except OSError:
                # Directory doesn't exist or can't be read
                return

            # Sort by modification time (oldest first)
            cache_files.sort(key=lambda x: x[1])

            # Remove oldest files if cache size exceeds limit
            if len(cache_files) > cls.MAX_CACHE_SIZE:
                files_to_remove = cache_files[: -cls.MAX_CACHE_SIZE]
                for file_path, _ in files_to_remove:
                    await remove(file_path)
                    LOGGER.info(f"🗑️ Removed old cache file: {file_path}")

        except Exception as e:
            LOGGER.error(f"Error cleaning up thumbnail cache: {e}")


class TMDBHelper:
    """TMDB API Helper for fetching movie and TV show metadata"""

    BASE_URL = "https://api.themoviedb.org/3"
    IMAGE_BASE_URL = "https://image.tmdb.org/t/p"

    # Cache for TMDB data
    _cache = {}
    _cache_timestamps = {}

    @classmethod
    async def search_movie(cls, title: str, year: int | None = None) -> dict | None:
        """Search for a movie by title and optional year"""
        try:
            if not Config.TMDB_API_KEY:
                LOGGER.warning("TMDB API key not configured")
                return None

            # Clean title for better search results
            clean_title = cls._clean_title(title)

            # Check cache first
            cache_key = f"search_movie_{clean_title}_{year}"
            if cls._is_cached(cache_key):
                return cls._cache[cache_key]

            # Check if TMDB API key is available
            if not hasattr(Config, "TMDB_API_KEY") or not Config.TMDB_API_KEY:
                LOGGER.error("❌ TMDB_API_KEY not found in configuration")
                return None

            params = {
                "api_key": Config.TMDB_API_KEY,
                "query": clean_title,
                "language": getattr(Config, "TMDB_LANGUAGE", "en-US"),
                "include_adult": str(
                    getattr(Config, "TMDB_ADULT_CONTENT", False)
                ).lower(),
            }

            LOGGER.info(f"🔍 TMDB movie search: '{clean_title}' (year: {year})")

            if year:
                params["year"] = year

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{cls.BASE_URL}/search/movie", params=params
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("results"):
                            result = data["results"][0]  # Get first result
                            cls._cache_result(cache_key, result)
                            LOGGER.info(
                                f"✅ Found TMDB movie: {result.get('title', 'Unknown')}"
                            )
                            return result
                        LOGGER.info(f"🔍 No TMDB movie results for: {clean_title}")
                        # Try alternative search strategies for anime/niche content
                        return await cls._try_alternative_movie_search(
                            title, year, session, original_title=title
                        )
                    LOGGER.warning(
                        f"❌ TMDB API error {response.status} for movie search: {clean_title}"
                    )
                    if response.status == 401:
                        LOGGER.error("❌ TMDB API key is invalid or missing")

            return None

        except Exception as e:
            LOGGER.error(f"Error searching movie '{title}': {e}")
            return None

    @classmethod
    async def search_tv_show(
        cls, title: str, year: int | None = None
    ) -> dict | None:
        """Search for a TV show by title and optional year"""
        try:
            if not Config.TMDB_API_KEY:
                LOGGER.warning("TMDB API key not configured")
                return None

            # Clean title for better search results
            clean_title = cls._clean_title(title)

            # Check cache first
            cache_key = f"search_tv_{clean_title}_{year}"
            if cls._is_cached(cache_key):
                return cls._cache[cache_key]

            # Check if TMDB API key is available
            if not hasattr(Config, "TMDB_API_KEY") or not Config.TMDB_API_KEY:
                LOGGER.error("❌ TMDB_API_KEY not found in configuration")
                return None

            params = {
                "api_key": Config.TMDB_API_KEY,
                "query": clean_title,
                "language": getattr(Config, "TMDB_LANGUAGE", "en-US"),
                "include_adult": str(
                    getattr(Config, "TMDB_ADULT_CONTENT", False)
                ).lower(),
            }

            LOGGER.info(f"🔍 TMDB TV search: '{clean_title}' (year: {year})")

            if year:
                params["first_air_date_year"] = year

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{cls.BASE_URL}/search/tv", params=params
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("results"):
                            result = data["results"][0]  # Get first result
                            cls._cache_result(cache_key, result)
                            LOGGER.info(
                                f"✅ Found TMDB TV show: {result.get('name', 'Unknown')}"
                            )
                            return result
                        LOGGER.info(f"🔍 No TMDB TV results for: {clean_title}")
                        # Try alternative search strategies for anime/niche content
                        return await cls._try_alternative_tv_search(
                            title, year, session, original_title=title
                        )
                    LOGGER.warning(
                        f"❌ TMDB API error {response.status} for TV search: {clean_title}"
                    )
                    if response.status == 401:
                        LOGGER.error("❌ TMDB API key is invalid or missing")

            return None

        except Exception as e:
            LOGGER.error(f"Error searching TV show '{title}': {e}")
            return None

    @classmethod
    def get_poster_url(cls, poster_path: str, size: str = "w500") -> str:
        """Get full poster URL from TMDB poster path"""
        if not poster_path:
            return ""
        return f"{cls.IMAGE_BASE_URL}/{size}{poster_path}"

    @classmethod
    def get_backdrop_url(cls, backdrop_path: str, size: str = "original") -> str:
        """Get full backdrop URL from TMDB backdrop path"""
        if not backdrop_path:
            return ""
        return f"{cls.IMAGE_BASE_URL}/{size}{backdrop_path}"

    @classmethod
    def _clean_title(cls, title: str) -> str:
        """Enhanced title cleaning for better search results"""
        if not title:
            return ""

        # Store original for fallback
        original_title = title

        # Remove file extensions
        title = re.sub(r"\.[a-zA-Z0-9]{2,4}$", "", title)

        # Replace dots, underscores, and dashes with spaces first
        title = re.sub(r"[._-]+", " ", title)

        # Remove quality indicators (more comprehensive)
        quality_patterns = [
            r"\b(720p|1080p|2160p|4k|hd|uhd|bluray|brrip|webrip|web-dl|dvdrip|hdtv|cam|ts|tc)\b",
            r"\b(x264|x265|h264|h265|hevc|avc|xvid|divx)\b",
            r"\b(aac|ac3|dts|mp3|flac|dd5\.1|dd\+|atmos)\b",
            r"\b(hindi|tamil|telugu|malayalam|kannada|bengali|punjabi|gujarati|marathi)\b",
            r"\b(dubbed|dual|audio|multi|eng|english)\b",
            r"\b(esub|sub|subtitle|subs)\b",
            r"\b(rip|encode|repack|proper|real|extended|unrated|directors?\.cut)\b",
            r"\b(season|episode|s\d+|e\d+|\d+x\d+)\b",
        ]
        for pattern in quality_patterns:
            title = re.sub(pattern, "", title, flags=re.IGNORECASE)

        # Remove brackets and their contents (but preserve main title)
        title = re.sub(r"\[.*?\]", "", title)
        title = re.sub(r"\{.*?\}", "", title)

        # Handle parentheses more carefully - keep year if present
        re.search(r"\((\d{4})\)", title)
        title = re.sub(r"\(.*?\)", "", title)

        # Remove common release group patterns
        title = re.sub(r"-\w+$", "", title)
        title = re.sub(r"^\w+-", "", title)  # Remove prefix groups

        # Remove episode/season indicators for anime
        title = re.sub(
            r"\s+(ep|episode|ova|ona|special)\s*\d+.*$",
            "",
            title,
            flags=re.IGNORECASE,
        )

        # Clean up whitespace and special characters
        title = re.sub(r"\s+", " ", title)
        title = title.strip()

        # If title becomes too short or empty, try a simpler approach
        if len(title) < 3:
            # Fallback: just remove file extension and basic cleaning
            title = re.sub(r"\.[a-zA-Z0-9]{2,4}$", "", original_title)
            title = re.sub(r"[._-]+", " ", title)
            title = re.sub(r"\s+", " ", title).strip()

        return title

    @classmethod
    def _is_cached(cls, cache_key: str) -> bool:
        """Check if data is cached and not expired"""
        if cache_key not in cls._cache:
            return False

        # Check if cache is expired (24 hours)
        cache_time = cls._cache_timestamps.get(cache_key)
        if not cache_time:
            return False

        return datetime.now() - cache_time < timedelta(hours=24)

    @classmethod
    def _cache_result(cls, cache_key: str, result: dict):
        """Cache the result with timestamp"""
        cls._cache[cache_key] = result
        cls._cache_timestamps[cache_key] = datetime.now()

        # Clean old cache entries (keep only last 1000)
        if len(cls._cache) > 1000:
            # Remove oldest 100 entries
            oldest_keys = sorted(
                cls._cache_timestamps.keys(), key=lambda k: cls._cache_timestamps[k]
            )[:100]
            for key in oldest_keys:
                cls._cache.pop(key, None)
                cls._cache_timestamps.pop(key, None)

    @classmethod
    async def _try_alternative_movie_search(
        cls, title: str, year: int | None, session, original_title: str | None = None
    ) -> dict | None:
        """Enhanced alternative search strategies for anime/niche content"""
        try:
            search_attempts = []

            # Strategy 1: Try with original filename (minimal cleaning)
            if original_title and original_title != title:
                minimal_clean = re.sub(r"\.[a-zA-Z0-9]{2,4}$", "", original_title)
                minimal_clean = re.sub(r"[._-]+", " ", minimal_clean).strip()
                search_attempts.append(("original filename", minimal_clean))

            # Strategy 2: Search with just the main title (remove episode info)
            main_title = re.sub(r"\s+S\d+E\d+.*", "", title, flags=re.IGNORECASE)
            main_title = re.sub(r"\s+Episode.*", "", main_title, flags=re.IGNORECASE)
            main_title = re.sub(
                r"\s+\d+.*", "", main_title
            )  # Remove trailing numbers
            search_attempts.append(("main title", main_title))

            # Strategy 3: Try first few words only (for long titles)
            words = title.split()
            if len(words) > 3:
                short_title = " ".join(words[:3])
                search_attempts.append(("short title", short_title))

            # Try each search strategy
            for strategy_name, search_title in search_attempts:
                if not search_title or len(search_title.strip()) < 2:
                    continue

                LOGGER.info(f"🔄 Trying {strategy_name} search: '{search_title}'")
                params = {
                    "api_key": Config.TMDB_API_KEY,
                    "query": search_title,
                    "language": getattr(Config, "TMDB_LANGUAGE", "en-US"),
                    "include_adult": str(
                        getattr(Config, "TMDB_ADULT_CONTENT", False)
                    ).lower(),
                }
                if year:
                    params["year"] = year

                async with session.get(
                    f"{cls.BASE_URL}/search/movie", params=params
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("results"):
                            result = data["results"][0]
                            LOGGER.info(
                                f"✅ Found via {strategy_name}: {result.get('title', 'Unknown')}"
                            )
                            return result

            # Strategy 2: Try as TV show instead (anime often categorized as TV)
            LOGGER.info(f"🔄 Trying as TV show: '{main_title}'")
            tv_result = await cls.search_tv_show(main_title, year)
            if tv_result:
                LOGGER.info(
                    f"✅ Found as TV show: {tv_result.get('name', 'Unknown')}"
                )
                return tv_result

            return None

        except Exception as e:
            LOGGER.error(f"Error in alternative movie search: {e}")
            return None

    @classmethod
    async def _try_alternative_tv_search(
        cls, title: str, year: int | None, session, original_title: str | None = None
    ) -> dict | None:
        """Enhanced alternative search strategies for anime/niche TV content"""
        try:
            search_attempts = []

            # Strategy 1: Try with original filename (minimal cleaning)
            if original_title and original_title != title:
                minimal_clean = re.sub(r"\.[a-zA-Z0-9]{2,4}$", "", original_title)
                minimal_clean = re.sub(r"[._-]+", " ", minimal_clean).strip()
                search_attempts.append(("original filename", minimal_clean))

            # Strategy 2: Search with just the main title (remove episode info)
            main_title = re.sub(r"\s+S\d+E\d+.*", "", title, flags=re.IGNORECASE)
            main_title = re.sub(r"\s+Episode.*", "", main_title, flags=re.IGNORECASE)
            main_title = re.sub(
                r"\s+\d+.*", "", main_title
            )  # Remove trailing numbers
            search_attempts.append(("main title", main_title))

            # Strategy 3: Try first few words only (for long titles)
            words = title.split()
            if len(words) > 3:
                short_title = " ".join(words[:3])
                search_attempts.append(("short title", short_title))

            # Try each search strategy
            for strategy_name, search_title in search_attempts:
                if not search_title or len(search_title.strip()) < 2:
                    continue

                LOGGER.info(f"🔄 Trying {strategy_name} TV search: '{search_title}'")
                params = {
                    "api_key": Config.TMDB_API_KEY,
                    "query": search_title,
                    "language": getattr(Config, "TMDB_LANGUAGE", "en-US"),
                    "include_adult": str(
                        getattr(Config, "TMDB_ADULT_CONTENT", False)
                    ).lower(),
                }
                if year:
                    params["first_air_date_year"] = year

                async with session.get(
                    f"{cls.BASE_URL}/search/tv", params=params
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("results"):
                            result = data["results"][0]
                            LOGGER.info(
                                f"✅ Found via {strategy_name} TV: {result.get('name', 'Unknown')}"
                            )
                            return result

            return None

        except Exception as e:
            LOGGER.error(f"Error in alternative TV search: {e}")
            return None
