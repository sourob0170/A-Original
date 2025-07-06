"""
TMDB (The Movie Database) API Helper
Provides comprehensive TMDB integration for fetching movie and TV show metadata
"""

import re
from datetime import datetime, timedelta

import aiohttp

from bot import LOGGER
from bot.core.config_manager import Config


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
                            title, year, session
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
    async def _try_alternative_movie_search(
        cls, title: str, year: int | None, session
    ) -> dict | None:
        """Try alternative search strategies for anime/niche content"""
        try:
            # Strategy 1: Search with just the main title (remove episode info)
            main_title = re.sub(r"\s+S\d+E\d+.*", "", title, flags=re.IGNORECASE)
            main_title = re.sub(r"\s+Episode.*", "", main_title, flags=re.IGNORECASE)
            main_title = cls._clean_title(main_title)

            if main_title != cls._clean_title(title):
                LOGGER.info(f"🔄 Trying main title search: '{main_title}'")
                params = {
                    "api_key": Config.TMDB_API_KEY,
                    "query": main_title,
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
                                f"✅ Found via main title: {result.get('title', 'Unknown')}"
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
                            title, year, session
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
    async def _try_alternative_tv_search(
        cls, title: str, year: int | None, session
    ) -> dict | None:
        """Try alternative search strategies for anime/niche TV content"""
        try:
            # Strategy 1: Search with just the main title (remove episode info)
            main_title = re.sub(r"\s+S\d+E\d+.*", "", title, flags=re.IGNORECASE)
            main_title = re.sub(r"\s+Episode.*", "", main_title, flags=re.IGNORECASE)
            main_title = cls._clean_title(main_title)

            if main_title != cls._clean_title(title):
                LOGGER.info(f"🔄 Trying main TV title search: '{main_title}'")
                params = {
                    "api_key": Config.TMDB_API_KEY,
                    "query": main_title,
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
                                f"✅ Found via main TV title: {result.get('name', 'Unknown')}"
                            )
                            return result

            # Strategy 2: Try with different language (anime often in Japanese)
            if getattr(Config, "TMDB_LANGUAGE", "en-US") != "ja-JP":
                LOGGER.info(f"🔄 Trying Japanese search: '{main_title}'")
                params = {
                    "api_key": Config.TMDB_API_KEY,
                    "query": main_title,
                    "language": "ja-JP",
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
                                f"✅ Found via Japanese search: {result.get('name', 'Unknown')}"
                            )
                            return result

            return None

        except Exception as e:
            LOGGER.error(f"Error in alternative TV search: {e}")
            return None

    @classmethod
    async def get_movie_details(cls, movie_id: int) -> dict | None:
        """Get detailed movie information by TMDB ID"""
        try:
            if not Config.TMDB_API_KEY:
                return None

            # Check cache first
            cache_key = f"movie_details_{movie_id}"
            if cls._is_cached(cache_key):
                return cls._cache[cache_key]

            params = {
                "api_key": Config.TMDB_API_KEY,
                "language": getattr(Config, "TMDB_LANGUAGE", "en-US"),
                "append_to_response": "credits,videos,images,keywords,recommendations",
            }

            async with (
                aiohttp.ClientSession() as session,
                session.get(
                    f"{cls.BASE_URL}/movie/{movie_id}", params=params
                ) as response,
            ):
                if response.status == 200:
                    result = await response.json()
                    cls._cache_result(cache_key, result)
                    return result

            return None

        except Exception as e:
            LOGGER.error(f"Error getting movie details for ID {movie_id}: {e}")
            return None

    @classmethod
    async def get_tv_details(cls, tv_id: int) -> dict | None:
        """Get detailed TV show information by TMDB ID"""
        try:
            if not Config.TMDB_API_KEY:
                return None

            # Check cache first
            cache_key = f"tv_details_{tv_id}"
            if cls._is_cached(cache_key):
                return cls._cache[cache_key]

            params = {
                "api_key": Config.TMDB_API_KEY,
                "language": getattr(Config, "TMDB_LANGUAGE", "en-US"),
                "append_to_response": "credits,videos,images,keywords,recommendations",
            }

            async with (
                aiohttp.ClientSession() as session,
                session.get(f"{cls.BASE_URL}/tv/{tv_id}", params=params) as response,
            ):
                if response.status == 200:
                    result = await response.json()
                    cls._cache_result(cache_key, result)
                    return result

            return None

        except Exception as e:
            LOGGER.error(f"Error getting TV details for ID {tv_id}: {e}")
            return None

    @classmethod
    async def auto_detect_and_fetch_metadata(
        cls, filename: str, category: str | None = None
    ) -> dict | None:
        """Auto-detect media type and fetch metadata from filename"""
        try:
            # Extract title and year from filename
            title, year = cls._extract_title_and_year(filename)
            if not title:
                return None

            # Determine media type
            is_tv_show = cls._detect_tv_show(filename, category)

            if is_tv_show:
                # Search for TV show
                search_result = await cls.search_tv_show(title, year)
                if search_result:
                    # Get detailed information
                    details = await cls.get_tv_details(search_result["id"])
                    if details:
                        return cls._format_tv_metadata(details)
            else:
                # Search for movie
                search_result = await cls.search_movie(title, year)
                if search_result:
                    # Get detailed information
                    details = await cls.get_movie_details(search_result["id"])
                    if details:
                        return cls._format_movie_metadata(details)

            return None

        except Exception as e:
            LOGGER.error(f"Error auto-detecting metadata for '{filename}': {e}")
            return None

    @classmethod
    def _clean_title(cls, title: str) -> str:
        """Clean title for better search results"""
        if not title:
            return ""

        # Remove file extensions
        title = re.sub(r"\.[a-zA-Z0-9]{2,4}$", "", title)

        # Remove quality indicators
        quality_patterns = [
            r"\b(720p|1080p|2160p|4k|hd|uhd|bluray|brrip|webrip|web-dl|dvdrip|hdtv)\b",
            r"\b(x264|x265|h264|h265|hevc|avc)\b",
            r"\b(aac|ac3|dts|mp3|flac)\b",
        ]
        for pattern in quality_patterns:
            title = re.sub(pattern, "", title, flags=re.IGNORECASE)

        # Remove brackets and their contents
        title = re.sub(r"\[.*?\]", "", title)
        title = re.sub(r"\(.*?\)", "", title)
        title = re.sub(r"\{.*?\}", "", title)

        # Remove common release group patterns
        title = re.sub(r"-\w+$", "", title)

        # Clean up whitespace and special characters
        title = re.sub(r"[._-]+", " ", title)
        title = re.sub(r"\s+", " ", title)

        return title.strip()

    @classmethod
    def _extract_title_and_year(cls, filename: str) -> tuple[str, int | None]:
        """Extract title and year from filename"""
        # Clean the filename first
        clean_name = cls._clean_title(filename)

        # Extract year (4 digits between 1900-2099)
        year_match = re.search(r"\b(19|20)\d{2}\b", clean_name)
        year = int(year_match.group()) if year_match else None

        # Remove year from title
        title = (
            clean_name[: year_match.start()].strip() if year_match else clean_name
        )

        return title, year

    @classmethod
    def _detect_tv_show(cls, filename: str, category: str | None = None) -> bool:
        """Detect if the file is a TV show"""
        if category and category.lower() in ["series", "tv", "show", "anime"]:
            return True

        # Check for TV show patterns in filename
        tv_patterns = [
            r"\bs\d+e\d+\b",  # S01E01
            r"\b\d+x\d+\b",  # 1x01
            r"\bepisode\s*\d+\b",  # Episode 1
            r"\bep\s*\d+\b",  # Ep 1
        ]

        filename_lower = filename.lower()
        return any(re.search(pattern, filename_lower) for pattern in tv_patterns)

    @classmethod
    def _format_movie_metadata(cls, movie_data: dict) -> dict:
        """Format movie metadata for ReelNN"""
        try:
            return {
                "tmdb_id": movie_data.get("id"),
                "title": movie_data.get("title"),
                "original_title": movie_data.get("original_title"),
                "overview": movie_data.get("overview"),
                "tagline": movie_data.get("tagline"),
                "release_date": movie_data.get("release_date"),
                "vote_average": movie_data.get("vote_average"),
                "vote_count": movie_data.get("vote_count"),
                "popularity": movie_data.get("popularity"),
                "poster_path": movie_data.get("poster_path"),
                "backdrop_path": movie_data.get("backdrop_path"),
                "genres": movie_data.get("genres", []),
                "runtime": movie_data.get("runtime"),
                "status": movie_data.get("status"),
                "production_companies": movie_data.get("production_companies", []),
                "production_countries": movie_data.get("production_countries", []),
                "spoken_languages": movie_data.get("spoken_languages", []),
                "imdb_id": movie_data.get("imdb_id"),
                "media_type": "movie",
            }
        except Exception as e:
            LOGGER.error(f"Error formatting movie metadata: {e}")
            return {}

    @classmethod
    def _format_tv_metadata(cls, tv_data: dict) -> dict:
        """Format TV show metadata for ReelNN"""
        try:
            return {
                "tmdb_id": tv_data.get("id"),
                "title": tv_data.get("name"),
                "original_title": tv_data.get("original_name"),
                "overview": tv_data.get("overview"),
                "tagline": tv_data.get("tagline"),
                "first_air_date": tv_data.get("first_air_date"),
                "last_air_date": tv_data.get("last_air_date"),
                "vote_average": tv_data.get("vote_average"),
                "vote_count": tv_data.get("vote_count"),
                "popularity": tv_data.get("popularity"),
                "poster_path": tv_data.get("poster_path"),
                "backdrop_path": tv_data.get("backdrop_path"),
                "genres": tv_data.get("genres", []),
                "number_of_seasons": tv_data.get("number_of_seasons"),
                "number_of_episodes": tv_data.get("number_of_episodes"),
                "status": tv_data.get("status"),
                "production_companies": tv_data.get("production_companies", []),
                "production_countries": tv_data.get("production_countries", []),
                "spoken_languages": tv_data.get("spoken_languages", []),
                "media_type": "tv",
            }
        except Exception as e:
            LOGGER.error(f"Error formatting TV metadata: {e}")
            return {}

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
    def extract_year_from_title(cls, title: str) -> tuple[str, str | None]:
        """Extract year from title - ReelNN style"""
        try:
            # Pattern to match year in parentheses or at end
            year_patterns = [
                r"\((\d{4})\)",  # (2023)
                r"\[(\d{4})\]",  # [2023]
                r"(\d{4})$",  # 2023 at end
                r"(\d{4})\s*$",  # 2023 with optional space at end
            ]

            for pattern in year_patterns:
                match = re.search(pattern, title)
                if match:
                    year = match.group(1)
                    clean_title = re.sub(pattern, "", title).strip()
                    return clean_title, year

            return title, None

        except Exception as e:
            LOGGER.error(f"Error extracting year from title: {e}")
            return title, None

    @classmethod
    def clean_title_for_search(cls, title: str) -> str:
        """Clean title for TMDB search - ReelNN style"""
        try:
            # Remove common patterns that interfere with search
            clean_title = title

            # Remove quality indicators
            quality_patterns = [
                r"\b(1080p|720p|480p|4K|2160p|HDRip|BRRip|DVDRip|WEBRip|HDTV)\b",
                r"\b(x264|x265|H\.264|H\.265|HEVC)\b",
                r"\b(AAC|AC3|DTS|MP3)\b",
                r"\b(YIFY|RARBG|YTS|ETRG)\b",
            ]

            for pattern in quality_patterns:
                clean_title = re.sub(pattern, "", clean_title, flags=re.IGNORECASE)

            # Remove brackets and their contents (except years)
            clean_title = re.sub(r"\[[^\]]*\]", "", clean_title)
            clean_title = re.sub(r"\{[^}]*\}", "", clean_title)

            # Remove extra dots, dashes, underscores
            clean_title = re.sub(r"[._-]+", " ", clean_title)

            # Remove multiple spaces
            clean_title = re.sub(r"\s+", " ", clean_title)

            # Remove leading/trailing whitespace
            return clean_title.strip()

        except Exception as e:
            LOGGER.error(f"Error cleaning title for search: {e}")
            return title
