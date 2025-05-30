import asyncio
import contextlib
import hashlib
import time as time_module
from functools import partial
from time import time
from typing import Any

from pyrogram.filters import regex, user
from pyrogram.handlers import CallbackQueryHandler
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)

from bot import LOGGER
from bot.core.config_manager import Config
from bot.helper.ext_utils.bot_utils import new_task
from bot.helper.ext_utils.status_utils import get_readable_time
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    delete_message,
    edit_message,
    send_message,
)

try:
    from streamrip.client import (
        DeezerClient,
        QobuzClient,
        SoundcloudClient,
        TidalClient,
    )

    STREAMRIP_AVAILABLE = True
except ImportError:
    STREAMRIP_AVAILABLE = False

    # Create dummy classes to prevent import errors
    class QobuzClient:
        pass

    class TidalClient:
        pass

    class DeezerClient:
        pass

    class SoundcloudClient:
        pass


class StreamripSearchHandler:
    """Ultra-optimized multi-platform search handler for streamrip with minimal complexity"""

    # Class-level constants for O(1) lookups and memory efficiency
    PLATFORM_SEARCH_TYPES = {
        "qobuz": ("track", "album", "artist", "playlist"),
        "deezer": ("track", "album", "artist", "playlist"),
        "tidal": ("track", "album", "artist", "playlist"),
        "soundcloud": ("track",),  # SoundCloud mainly supports tracks
    }

    URL_TEMPLATES = {
        "qobuz": {
            "track": "https://www.qobuz.com/track/{}",
            "album": "https://www.qobuz.com/album/{}",
            "artist": "https://www.qobuz.com/artist/{}",
            "playlist": "https://www.qobuz.com/playlist/{}",
        },
        "tidal": {
            "track": "https://listen.tidal.com/track/{}",
            "album": "https://listen.tidal.com/album/{}",
            "artist": "https://listen.tidal.com/artist/{}",
            "playlist": "https://listen.tidal.com/playlist/{}",
        },
        "deezer": {
            "track": "https://www.deezer.com/track/{}",
            "album": "https://www.deezer.com/album/{}",
            "artist": "https://www.deezer.com/artist/{}",
            "playlist": "https://www.deezer.com/playlist/{}",
        },
        "soundcloud": {
            "track": "https://soundcloud.com/track/{}",
            "playlist": "https://soundcloud.com/playlist/{}",
        },
    }

    # Pre-computed platform emojis and quality info for O(1) access
    PLATFORM_EMOJIS = {
        "qobuz": "🟦",
        "tidal": "⚫",
        "deezer": "🟣",
        "soundcloud": "🟠",
    }
    TYPE_EMOJIS = {"track": "🎵", "album": "💿", "playlist": "📋", "artist": "👤"}
    QUALITY_MAP = {
        "qobuz": "Hi-Res FLAC",
        "tidal": "MQA/Hi-Res",
        "deezer": "CD Quality",
        "soundcloud": "MP3 320kbps",
    }

    # Client class mapping for efficient initialization
    CLIENT_CLASSES = {
        "qobuz": QobuzClient,
        "tidal": TidalClient,
        "deezer": DeezerClient,
        "soundcloud": SoundcloudClient,
    }

    __slots__ = (
        "_cached_all_results",
        "_reply_to",
        "_time",
        "_timeout",
        "clients",
        "current_page",
        "event",
        "failed_platforms",
        "initial_platforms",
        "listener",
        "media_type_filter",
        "platform",
        "query",
        "result_limit",
        "results_per_page",
        "search_results",
        "selected_result",
    )

    def __init__(
        self,
        listener,
        query: str,
        platform: str | None = None,
        media_type_filter: str | None = None,
        result_limit: int = 200,
    ):
        self.listener = listener
        self.query = query
        self.platform = platform
        self.media_type_filter = media_type_filter
        self.result_limit = result_limit
        self.search_results = {}
        self.current_page = 0
        self.results_per_page = 5
        self._reply_to = None
        self._time = time()
        self._timeout = 300  # 5 minutes for search
        self.event = asyncio.Event()
        self.selected_result = None
        self.clients = {}
        self.initial_platforms = []  # Track initial platforms for comparison
        self.failed_platforms = set()  # Track platforms that failed authentication
        self._cached_all_results = None  # Cache flattened results for O(1) access

    async def initialize_clients(self):
        """Initialize platform clients"""
        if not STREAMRIP_AVAILABLE:
            return False

        try:
            from bot.helper.streamrip_utils.streamrip_config import streamrip_config

            config = streamrip_config.get_config()
            if not config:
                return False

            platform_status = streamrip_config.get_platform_status()

            # Check if any platforms are available
            enabled_platforms = [
                p for p, enabled in platform_status.items() if enabled
            ]
            if not enabled_platforms:
                return False

            # Initialize only enabled platforms using class constants for O(1) lookup
            for platform in enabled_platforms:
                if platform in self.CLIENT_CLASSES:
                    try:
                        self.clients[platform] = self.CLIENT_CLASSES[platform](
                            config
                        )
                    except Exception as e:
                        LOGGER.error(
                            f"❌ Failed to initialize {platform.title()} client: {e}"
                        )

            # Store initial platform list for comparison later
            self.initial_platforms = list(self.clients.keys())

            return len(self.clients) > 0

        except Exception as e:
            LOGGER.error(f"Failed to initialize search clients: {e}")
            return False

    async def _cleanup_clients(self):
        """Cleanup streamrip clients to prevent unclosed sessions"""
        try:
            for platform, client in self.clients.items():
                try:
                    # Try to properly close aiohttp sessions in streamrip clients with timeout
                    cleanup_tasks = []

                    if hasattr(client, "_session") and client._session:
                        if not client._session.closed:
                            cleanup_tasks.append(client._session.close())
                    elif hasattr(client, "session") and client.session:
                        if not client.session.closed:
                            cleanup_tasks.append(client.session.close())
                    elif hasattr(client, "_http_session") and client._http_session:
                        if not client._http_session.closed:
                            cleanup_tasks.append(client._http_session.close())

                    # Also try to close any connector
                    if hasattr(client, "_connector") and client._connector:
                        cleanup_tasks.append(client._connector.close())
                    elif hasattr(client, "connector") and client.connector:
                        cleanup_tasks.append(client.connector.close())

                    # Execute cleanup tasks with timeout
                    if cleanup_tasks:
                        await asyncio.wait_for(
                            asyncio.gather(*cleanup_tasks, return_exceptions=True),
                            timeout=5.0,
                        )

                except TimeoutError:
                    LOGGER.warning(
                        f"Cleanup timeout for {platform} client - forcing cleanup"
                    )
                except Exception as cleanup_error:
                    LOGGER.warning(
                        f"Failed to cleanup {platform} client: {cleanup_error}"
                    )

            # Clear clients dict
            self.clients.clear()

            # Force garbage collection to help with cleanup
            import gc

            gc.collect()

        except Exception as e:
            LOGGER.error(f"Error during client cleanup: {e}")

    def _log_search_summary(self):
        """Log summary of search results and platform status"""
        try:
            initial_platforms = getattr(self, "initial_platforms", [])
            failed_platforms = getattr(self, "failed_platforms", set())
            [p for p in initial_platforms if p not in failed_platforms]

            # Only log if there are failures or no results
            total_results = sum(
                len(results) for results in self.search_results.values()
            )

            if failed_platforms:
                LOGGER.warning(
                    f"❌ {len(failed_platforms)} platforms failed: {', '.join(failed_platforms)}"
                )

            if total_results == 0:
                LOGGER.warning("No search results found on any platform")

        except Exception as e:
            LOGGER.error(f"Error logging search summary: {e}")

    def _extract_results_from_containers(
        self, search_response, platform: str, search_type: str
    ):
        """Extract actual results from platform-specific response containers"""
        actual_results = []

        try:
            if platform == "qobuz":
                # Qobuz: {'query': '...', 'tracks': {'items': [...]}}
                for result_container in search_response:
                    if search_type + "s" in result_container:
                        items = result_container[search_type + "s"]
                        if isinstance(items, dict) and "items" in items:
                            actual_results.extend(items["items"])
                        elif isinstance(items, list):
                            actual_results.extend(items)
            elif platform == "deezer":
                # Deezer: {'data': [...], 'total': ..., 'next': ...}
                for result_container in search_response:
                    if "data" in result_container:
                        actual_results.extend(result_container["data"])
            elif platform == "soundcloud":
                # SoundCloud: {'collection': [...], 'total_results': ..., ...}
                for result_container in search_response:
                    if "collection" in result_container:
                        actual_results.extend(result_container["collection"])
            elif platform == "tidal":
                # Tidal: {'limit': 50, 'offset': 0, 'totalNumberOfItems': 123, 'items': [...]}
                for result_container in search_response:
                    if (
                        isinstance(result_container, dict)
                        and "items" in result_container
                    ):
                        actual_results.extend(result_container["items"])
                    elif isinstance(result_container, list):
                        actual_results.extend(result_container)
                    else:
                        # Fallback: treat as single item
                        actual_results.append(result_container)
            # Fallback: assume direct list
            elif isinstance(search_response, list):
                actual_results = search_response
            else:
                actual_results = [search_response]

        except Exception as e:
            LOGGER.warning(
                f"Failed to extract results from {platform} containers: {e}"
            )
            # Fallback to treating response as direct results
            if isinstance(search_response, list):
                actual_results = search_response
            else:
                actual_results = [search_response]

        return actual_results

    async def search(self) -> dict[str, Any] | None:
        """Perform multi-platform search"""
        try:
            if not await self.initialize_clients():
                await send_message(
                    self.listener.message,
                    f"{self.listener.tag} ❌ <b>No streamrip platforms are configured!</b>\n\n"
                    f"🎵 <b>Available platforms:</b>\n"
                    f"🟦 <code>Qobuz</code> - Hi-Res FLAC\n"
                    f"⚫ <code>Tidal</code> - MQA/Hi-Res\n"
                    f"🟣 <code>Deezer</code> - CD Quality\n"
                    f"🟠 <code>SoundCloud</code> - MP3 320kbps\n\n"
                    f"💡 <i>Configure credentials in bot settings to enable search.</i>",
                )
                return None

            # Show beautiful searching message
            platform_info = ""
            if self.platform:
                platform_emoji = {
                    "qobuz": "🟦",
                    "tidal": "⚫",
                    "deezer": "🟣",
                    "soundcloud": "🟠",
                }.get(self.platform, "🔵")
                platform_info = f"\n🎯 <b>Platform:</b> {platform_emoji} <code>{self.platform.title()}</code>"
            else:
                platform_count = len(self.clients)
                platform_info = (
                    f"\n🎯 <b>Platforms:</b> <code>{platform_count}</code> platforms"
                )

            search_msg = await send_message(
                self.listener.message,
                f"🔍 <b>Streamrip Search</b>\n\n"
                f"🎵 <b>Query:</b> <code>{self.query}</code>{platform_info}\n\n"
                f"⏳ <i>Searching across music platforms...</i>\n"
                f"🎶 <i>This may take a few seconds</i>",
            )

            # Perform search on all platforms or specific platform
            if self.platform and self.platform in self.clients:
                await self._search_platform(self.platform)
            else:
                # Search all available platforms
                search_tasks = []
                for platform_name in self.clients:
                    search_tasks.append(self._search_platform(platform_name))

                await asyncio.gather(*search_tasks, return_exceptions=True)

            # Delete searching message
            await delete_message(search_msg)

            # Log search completion summary
            self._log_search_summary()

            # Check if we have results
            total_results = sum(
                len(results) for results in self.search_results.values()
            )

            if total_results == 0:
                # Check if any platforms were disabled
                failed_platforms = getattr(self, "failed_platforms", set())

                error_msg = f"{self.listener.tag} ❌ <b>No results found for:</b> <code>{self.query}</code>"
                if failed_platforms:
                    error_msg += "\n\n⚠️ <b>Some platforms were disabled due to authentication issues:</b>\n"
                    error_msg += f"<pre>{', '.join(failed_platforms)}</pre>\n"
                    error_msg += "💡 <i>Check your credentials in bot settings and try again.</i>"

                no_results_msg = await send_message(self.listener.message, error_msg)
                asyncio.create_task(auto_delete_message(no_results_msg, time=300))
                return None

            # Show search results
            await self._show_search_results()

            # Start event handler
            asyncio.create_task(self._event_handler())

            # Wait for selection
            await self.event.wait()

            return self.selected_result

        except Exception as e:
            LOGGER.error(f"Search error: {e}")
            await delete_message(search_msg)
            error_msg = await send_message(
                self.listener.message,
                f"{self.listener.tag} ❌ <b>Search failed:</b>\n\n"
                f"🔍 <i>Query:</i> <code>{self.query}</code>\n"
                f"⚠️ <i>Error:</i> <pre>{e!s}</pre>\n"
                f"💡 <i>Try again or check platform availability.</i>",
            )
            asyncio.create_task(auto_delete_message(error_msg, time=300))
            return None
        finally:
            # Always cleanup clients to prevent unclosed sessions
            await self._cleanup_clients()

    async def _perform_search(self):
        """Perform search without UI - used for auto-first functionality"""
        if not await self.initialize_clients():
            return

        # Perform search on all platforms or specific platform
        if self.platform and self.platform in self.clients:
            await self._search_platform(self.platform)
        else:
            # Search all available platforms
            search_tasks = []
            for platform_name in self.clients:
                search_tasks.append(self._search_platform(platform_name))

            await asyncio.gather(*search_tasks, return_exceptions=True)

    async def _search_platform(self, platform: str):
        """Search on a specific platform"""
        try:
            client = self.clients[platform]

            # Perform search (this is a simplified example - actual implementation depends on streamrip API)
            # Note: The actual search API may differ, this is based on typical patterns
            results = await self._perform_platform_search(client, platform)

            if results:
                # Apply result limit
                limited_results = results[: self.result_limit]
                self.search_results[platform] = limited_results

        except Exception as e:
            LOGGER.error(f"Search failed on {platform}: {e}")

    async def _perform_platform_search(
        self, client, platform: str
    ) -> list[dict[str, Any]]:
        """Perform actual search on platform"""
        results = []

        try:
            # Login to client first
            if hasattr(client, "login"):
                try:
                    await client.login()
                except Exception as auth_error:
                    # Handle authentication failures consistently for all platforms
                    LOGGER.warning(
                        f"⚠️ {platform.title()} authentication failed: {auth_error}"
                    )

                    # Mark platform as failed but don't remove from clients during search
                    # (we'll track failed platforms separately)
                    if not hasattr(self, "failed_platforms"):
                        self.failed_platforms = set()
                    self.failed_platforms.add(platform)

                    # Return empty results for this platform, but don't stop the search
                    return results

            # Perform search using correct API methods
            if hasattr(client, "search"):
                # Determine search types based on media_type_filter using class constants
                if self.media_type_filter:
                    # Use only the specified media type
                    search_types = [self.media_type_filter]
                else:
                    # Use pre-defined platform search types for better performance
                    search_types = list(
                        self.PLATFORM_SEARCH_TYPES.get(platform, ("track",))
                    )

                for search_type in search_types:
                    try:
                        # Correct API signature: search(media_type, query, limit)
                        search_response = await client.search(
                            search_type,  # Use singular forms for all platforms
                            self.query,
                            limit=self.result_limit,
                        )

                        # Extract actual results from platform-specific containers
                        if search_response:
                            actual_results = self._extract_results_from_containers(
                                search_response, platform, search_type
                            )

                            for item in actual_results:
                                # Extract metadata based on platform and type
                                result = await self._extract_search_result(
                                    item, platform, search_type
                                )
                                if result:
                                    results.append(result)

                    except Exception as search_error:
                        LOGGER.warning(
                            f"Search type '{search_type}' failed on {platform}: {search_error}"
                        )
                        continue

            else:
                LOGGER.warning(
                    f"Platform {platform} does not support search functionality"
                )

        except Exception as e:
            LOGGER.error(f"Platform search error for {platform}: {e}")
            if "authentication" in str(e).lower() or "login" in str(e).lower():
                LOGGER.info(
                    f"💡 {platform.title()} authentication may be required. Check your credentials."
                )

        return results

    async def _extract_search_result(
        self, item, platform: str, search_type: str
    ) -> dict[str, Any] | None:
        """Extract search result metadata"""
        try:
            result = {
                "platform": platform,
                "type": search_type,
                "title": "Unknown",
                "artist": "Unknown Artist",
                "album": "",
                "duration": 0,
                "url": "",
                "id": "",
                "quality": "Unknown",
                "cover_url": "",
            }

            # Extract metadata from dict structure (all platforms return dicts)
            if isinstance(item, dict):
                # Extract title
                result["title"] = item.get("title", item.get("name", "Unknown"))

                # Platform-specific artist extraction
                if platform == "qobuz":
                    if "performer" in item:
                        if isinstance(item["performer"], dict):
                            result["artist"] = item["performer"].get(
                                "name", str(item["performer"])
                            )
                        else:
                            result["artist"] = str(item["performer"])
                    elif "artist" in item:
                        if isinstance(item["artist"], dict):
                            result["artist"] = item["artist"].get(
                                "name", str(item["artist"])
                            )
                        else:
                            result["artist"] = str(item["artist"])
                elif platform == "deezer":
                    # Deezer can have multiple artist field formats
                    if "artist" in item:
                        if isinstance(item["artist"], dict):
                            result["artist"] = item["artist"].get(
                                "name", str(item["artist"])
                            )
                        else:
                            result["artist"] = str(item["artist"])
                    elif item.get("artists"):
                        if isinstance(item["artists"], list) and item["artists"]:
                            first_artist = item["artists"][0]
                            if isinstance(first_artist, dict):
                                result["artist"] = first_artist.get(
                                    "name", str(first_artist)
                                )
                            else:
                                result["artist"] = str(first_artist)
                        elif isinstance(item["artists"], dict):
                            result["artist"] = item["artists"].get(
                                "name", str(item["artists"])
                            )
                    elif item.get("contributors"):
                        # Deezer sometimes uses 'contributors' field
                        if (
                            isinstance(item["contributors"], list)
                            and item["contributors"]
                        ):
                            first_contributor = item["contributors"][0]
                            if isinstance(first_contributor, dict):
                                result["artist"] = first_contributor.get(
                                    "name", str(first_contributor)
                                )
                            else:
                                result["artist"] = str(first_contributor)
                elif platform == "soundcloud":
                    if "user" in item:
                        if isinstance(item["user"], dict):
                            result["artist"] = item["user"].get(
                                "username", str(item["user"])
                            )
                        else:
                            result["artist"] = str(item["user"])
                    elif "uploader" in item:
                        result["artist"] = str(item["uploader"])
                elif platform == "tidal":
                    if "artist" in item:
                        if isinstance(item["artist"], dict):
                            result["artist"] = item["artist"].get(
                                "name", str(item["artist"])
                            )
                        else:
                            result["artist"] = str(item["artist"])
                    elif item.get("artists"):
                        if isinstance(item["artists"], list) and item["artists"]:
                            first_artist = item["artists"][0]
                            if isinstance(first_artist, dict):
                                result["artist"] = first_artist.get(
                                    "name", str(first_artist)
                                )
                            else:
                                result["artist"] = str(first_artist)

                # Enhanced generic fallbacks for artist
                if result["artist"] == "Unknown Artist":
                    # Try different artist field variations
                    for artist_field in [
                        "artists",
                        "performer",
                        "artist",
                        "albumartist",
                        "composer",
                    ]:
                        if item.get(artist_field):
                            field_value = item[artist_field]
                            if isinstance(field_value, list) and field_value:
                                first_item = field_value[0]
                                if isinstance(first_item, dict):
                                    result["artist"] = first_item.get(
                                        "name", str(first_item)
                                    )
                                else:
                                    result["artist"] = str(first_item)
                                break
                            if isinstance(field_value, dict):
                                result["artist"] = field_value.get(
                                    "name", str(field_value)
                                )
                                break
                            if isinstance(field_value, str):
                                result["artist"] = field_value
                                break

                # Special handling for artist and playlist search types
                if search_type in ["artist", "playlist"]:
                    if search_type == "artist":
                        # For artist searches, the title IS the artist name
                        result["artist"] = result["title"]
                    elif search_type == "playlist":
                        # For playlist searches, try to get the creator/owner
                        if "owner" in item:
                            if isinstance(item["owner"], dict):
                                result["artist"] = item["owner"].get(
                                    "name", item["owner"].get("username", "Unknown")
                                )
                            else:
                                result["artist"] = str(item["owner"])
                        elif "user" in item:
                            if isinstance(item["user"], dict):
                                result["artist"] = item["user"].get(
                                    "name", item["user"].get("username", "Unknown")
                                )
                            else:
                                result["artist"] = str(item["user"])
                        elif "creator" in item:
                            if isinstance(item["creator"], dict):
                                result["artist"] = item["creator"].get(
                                    "name",
                                    item["creator"].get("username", "Unknown"),
                                )
                            else:
                                result["artist"] = str(item["creator"])

                # Extract album
                if "album" in item:
                    if isinstance(item["album"], dict):
                        result["album"] = item["album"].get(
                            "title", item["album"].get("name", "")
                        )
                    else:
                        result["album"] = str(item["album"])

                # Extract duration
                result["duration"] = item.get("duration", 0)

                # Extract ID
                result["id"] = str(item.get("id", ""))

            else:
                # Fallback for object attributes (shouldn't happen with current API)
                result["title"] = getattr(
                    item, "title", getattr(item, "name", "Unknown")
                )
                if hasattr(item, "artist"):
                    if hasattr(item.artist, "name"):
                        result["artist"] = item.artist.name
                    else:
                        result["artist"] = str(item.artist)

            # Generate URL based on platform and ID
            if result["id"]:
                result["url"] = self._generate_platform_url(
                    platform, search_type, result["id"]
                )

            # Set quality info
            quality_map = {
                "qobuz": "Hi-Res FLAC",
                "tidal": "MQA/Hi-Res",
                "deezer": "CD Quality",
                "soundcloud": "MP3 320kbps",
            }
            result["quality"] = quality_map.get(platform, "Unknown")

            return result

        except Exception:
            return None

    def _generate_platform_url(
        self, platform: str, media_type: str, media_id: str
    ) -> str:
        """Generate platform URL from ID using class constants for better performance"""
        # Use class-level URL templates to avoid recreating the dictionary each time
        template = self.URL_TEMPLATES.get(platform, {}).get(media_type)
        if template:
            return template.format(media_id)
        return f"https://{platform}.com/{media_type}/{media_id}"

    async def _show_search_results(self):
        """Show search results with pagination"""
        buttons = ButtonMaker()

        # Get all results flattened with caching for O(1) subsequent access
        if self._cached_all_results is None:
            self._cached_all_results = []
            for results in self.search_results.values():
                self._cached_all_results.extend(results)
        all_results = self._cached_all_results

        # Check if we have any results
        total_results = len(all_results)
        if total_results == 0:
            # No results found - show error message instead of empty button menu
            error_msg = f"{self.listener.tag} ❌ <b>No results found for:</b> <code>{self.query}</code>\n\n"
            error_msg += "💡 <i>Try a different search query or check platform availability.</i>"

            no_results_msg = await send_message(self.listener.message, error_msg)
            asyncio.create_task(auto_delete_message(no_results_msg, time=300))

            # Set event to stop waiting
            self.event.set()
            return

        # Calculate pagination
        total_pages = (
            total_results + self.results_per_page - 1
        ) // self.results_per_page
        start_idx = self.current_page * self.results_per_page
        end_idx = min(start_idx + self.results_per_page, total_results)

        # Build message with beautiful HTML formatting
        msg = f"🔍 <b>Search Results for:</b> <code>{self.query}</code>\n"
        msg += f"📊 Found <b>{total_results}</b> results across <b>{len(self.search_results)}</b> platforms\n"
        msg += f"📄 Page <b>{self.current_page + 1}</b>/<b>{total_pages}</b>\n\n"

        # Show results for current page
        for i in range(start_idx, end_idx):
            result = all_results[i]
            result_num = i + 1

            # Format result display with proper truncation
            title = (
                result["title"][:45] + "..."
                if len(result["title"]) > 45
                else result["title"]
            )
            artist = (
                result["artist"][:35] + "..."
                if len(result["artist"]) > 35
                else result["artist"]
            )

            platform_emoji = {
                "qobuz": "🟦",
                "tidal": "⚫",
                "deezer": "🟣",
                "soundcloud": "🟠",
            }.get(result["platform"], "🔵")

            type_emoji = {
                "track": "🎵",
                "album": "💿",
                "playlist": "📋",
                "artist": "👤",
            }.get(result["type"], "🎵")

            # Beautiful formatted result with HTML tags
            msg += f"<b>{result_num}.</b> {platform_emoji} {type_emoji} <b>{title}</b>\n"
            msg += f"   👤 <i>{artist}</i>"

            if result["album"]:
                album = (
                    result["album"][:35] + "..."
                    if len(result["album"]) > 35
                    else result["album"]
                )
                msg += f" • 💿 <code>{album}</code>"

            if result["duration"]:
                duration_str = self._format_duration(result["duration"])
                msg += f" • ⏱️ <code>{duration_str}</code>"

            # Platform and quality info
            quality_info = result.get("quality", "")
            if quality_info:
                msg += f" • 🎯 <b>{result['platform'].title()}</b> <pre>{quality_info}</pre>\n\n"
            else:
                msg += f" • 🎯 <b>{result['platform'].title()}</b>\n\n"

            # Add download button
            buttons.data_button(
                f"{result_num}. {type_emoji} {title[:25]}...",
                f"srs select {i}",
                "header",
            )

        # Add pagination buttons
        if total_pages > 1:
            nav_buttons = []
            if self.current_page > 0:
                nav_buttons.append(
                    ("⬅️ Previous", f"srs page {self.current_page - 1}")
                )

            nav_buttons.append(
                (f"📄 {self.current_page + 1}/{total_pages}", "srs noop")
            )

            if self.current_page < total_pages - 1:
                nav_buttons.append(("Next ➡️", f"srs page {self.current_page + 1}"))

            for text, data in nav_buttons:
                buttons.data_button(text, data, "footer")

        # Add cancel button
        buttons.data_button("❌ Cancel", "srs cancel", "footer")

        msg += f"⏱️ <b>Timeout:</b> <code>{get_readable_time(self._timeout - (time() - self._time))}</code>"

        # Send or edit message
        if self._reply_to:
            await edit_message(self._reply_to, msg, buttons.build_menu(1))
        else:
            self._reply_to = await send_message(
                self.listener.message, msg, buttons.build_menu(1)
            )

    async def _event_handler(self):
        """Handle callback query events"""
        pfunc = partial(self._handle_callback, obj=self)
        handler = self.listener.client.add_handler(
            CallbackQueryHandler(
                pfunc,
                filters=regex("^srs") & user(self.listener.user_id),
            ),
            group=-1,
        )
        try:
            await asyncio.wait_for(self.event.wait(), timeout=self._timeout)
        except TimeoutError:
            # Send timeout message with beautiful formatting
            timeout_msg = await send_message(
                self.listener.message,
                f"{self.listener.tag} ⏰ <b>Search selection timed out.</b>\n\n"
                f"🔍 <i>Search query:</i> <code>{self.query}</code>\n"
                f"💡 <i>Use</i> <code>/srsearch {self.query}</code> <i>to search again.</i>",
            )

            # Delete the search results
            if self._reply_to:
                await delete_message(self._reply_to)

            # Auto-delete timeout message
            asyncio.create_task(auto_delete_message(timeout_msg, time=300))

            self.event.set()
        finally:
            self.listener.client.remove_handler(*handler)

    @staticmethod
    async def _handle_callback(_, query, obj):
        """Handle callback query"""
        data = query.data.split()
        await query.answer()

        if data[1] == "select":
            # Get selected result using cached results for O(1) access
            result_idx = int(data[2])
            if obj._cached_all_results is None:
                obj._cached_all_results = []
                for results in obj.search_results.values():
                    obj._cached_all_results.extend(results)
            all_results = obj._cached_all_results

            if 0 <= result_idx < len(all_results):
                obj.selected_result = all_results[result_idx]

                # Show selection confirmation with beautiful HTML formatting
                result = obj.selected_result
                msg = "✅ <b>Selected:</b>\n\n"
                msg += f"🎵 <b>{result['title']}</b>\n"
                msg += f"👤 Artist: <i>{result['artist']}</i>\n"

                if result["album"]:
                    msg += f"💿 Album: <code>{result['album']}</code>\n"

                if result["duration"]:
                    duration_str = obj._format_duration(result["duration"])
                    msg += f"⏱️ Duration: <code>{duration_str}</code>\n"

                quality_info = result.get("quality", "")
                if quality_info:
                    msg += f"🎯 Platform: <b>{result['platform'].title()}</b> <pre>{quality_info}</pre>\n"
                else:
                    msg += f"🎯 Platform: <b>{result['platform'].title()}</b>\n"

                msg += f"📁 Type: <b>{result['type'].title()}</b>\n\n"
                msg += "🚀 <b>Starting download...</b>"

                await edit_message(obj._reply_to, msg)

                # Auto-delete after 10 seconds
                asyncio.create_task(auto_delete_message(obj._reply_to, time=10))

                obj.event.set()

        elif data[1] == "page":
            # Change page
            new_page = int(data[2])
            obj.current_page = new_page
            await obj._show_search_results()

        elif data[1] == "cancel":
            # Send cancellation message with beautiful formatting
            cancel_msg = await send_message(
                obj.listener.message,
                f"{obj.listener.tag} ❌ <b>Search cancelled!</b>\n\n"
                f"🔍 <i>Search query:</i> <code>{obj.query}</code>\n"
                f"💡 <i>Use</i> <code>/srsearch {obj.query}</code> <i>to search again.</i>",
            )

            # Delete the search results
            if obj._reply_to:
                await delete_message(obj._reply_to)

            # Auto-delete cancellation message
            asyncio.create_task(auto_delete_message(cancel_msg, time=300))

            obj.listener.is_cancelled = True
            obj.event.set()

        elif data[1] == "noop":
            # No operation (for page indicator)
            pass

    def _format_duration(self, duration: int) -> str:
        """Format duration in seconds to MM:SS"""
        if not duration:
            return "Unknown"

        minutes = duration // 60
        seconds = duration % 60
        return f"{minutes}:{seconds:02d}"


async def search_music(
    listener,
    query: str,
    platform: str | None = None,
    media_type_filter: str | None = None,
    result_limit: int = 20,
) -> dict[str, Any] | None:
    """Search for music across platforms"""
    search_handler = StreamripSearchHandler(
        listener, query, platform, media_type_filter, result_limit
    )
    return await search_handler.search()


async def search_music_auto_first(
    listener,
    query: str,
    platform: str | None = None,
    media_type_filter: str | None = None,
    result_limit: int = 20,
) -> dict[str, Any] | None:
    """Search for music and automatically return first result"""
    search_handler = StreamripSearchHandler(
        listener, query, platform, media_type_filter, result_limit
    )

    try:
        # Perform search without showing interactive results
        await search_handler._perform_search()

        # Get all results
        all_results = []
        for platform_results in search_handler.search_results.values():
            all_results.extend(platform_results)

        if not all_results:
            no_results_msg = await send_message(
                listener.message,
                f"{listener.tag} ❌ <b>No results found for:</b> <code>{query}</code>\n\n"
                f"💡 <i>Try a different search query or check platform availability.</i>",
            )
            asyncio.create_task(auto_delete_message(no_results_msg, time=300))
            return None

        # Return first result
        first_result = all_results[0]

        # Show auto-selection message with beautiful HTML formatting
        msg = "⚡ <b>Auto-selected first result:</b>\n\n"
        msg += f"🎵 <b>{first_result['title']}</b>\n"
        msg += f"👤 Artist: <i>{first_result['artist']}</i>\n"

        if first_result["album"]:
            msg += f"💿 Album: <code>{first_result['album']}</code>\n"

        if first_result["duration"]:
            duration_str = search_handler._format_duration(first_result["duration"])
            msg += f"⏱️ Duration: <code>{duration_str}</code>\n"

        quality_info = first_result.get("quality", "")
        if quality_info:
            msg += f"🎯 Platform: <b>{first_result['platform'].title()}</b> <pre>{quality_info}</pre>\n"
        else:
            msg += f"🎯 Platform: <b>{first_result['platform'].title()}</b>\n"

        msg += f"📁 Type: <b>{first_result['type'].title()}</b>\n\n"
        msg += "🚀 <b>Starting download...</b>"

        auto_msg = await send_message(listener.message, msg)
        asyncio.create_task(auto_delete_message(auto_msg, time=10))

        return first_result

    finally:
        # Always cleanup clients to prevent unclosed sessions
        await search_handler._cleanup_clients()


# Global cleanup function for emergency session cleanup
async def cleanup_all_streamrip_sessions():
    """Emergency cleanup function to close any remaining aiohttp sessions"""
    try:
        import gc

        import aiohttp

        # Force garbage collection to identify unclosed sessions
        gc.collect()

        # Look for any remaining aiohttp sessions in garbage
        for obj in gc.get_objects():
            if isinstance(obj, aiohttp.ClientSession):
                try:
                    if not obj.closed:
                        await obj.close()
                except Exception as e:
                    LOGGER.warning(f"Failed to close orphaned session: {e}")

        # Final garbage collection
        gc.collect()

    except Exception as e:
        LOGGER.error(f"Error during emergency cleanup: {e}")


# ===== INLINE SEARCH FUNCTIONALITY =====

# Cache for streamrip search results to avoid redundant searches
STREAMRIP_SEARCH_CACHE = {}
STREAMRIP_CACHE_COUNTER = 0

# Cache for streamrip result info (for start command access)
STREAMRIP_RESULT_CACHE = {}

# Global cache for authenticated clients (to avoid re-authentication)
STREAMRIP_CLIENT_CACHE = {}
CLIENT_CACHE_EXPIRY = 300  # 5 minutes


def generate_streamrip_cache_key(query, platform, media_type, user_id):
    """Generate a unique key for caching streamrip search results."""
    key = f"{user_id}_{query}_{platform}_{media_type}"
    return hashlib.md5(key.encode()).hexdigest()


def encrypt_streamrip_data(data_string):
    """Create a compact token for streamrip result data."""
    global STREAMRIP_CACHE_COUNTER
    try:
        # Check if this data is already in the cache
        for key, value in STREAMRIP_RESULT_CACHE.items():
            if value == data_string:
                return key

        # Generate a new short ID
        STREAMRIP_CACHE_COUNTER += 1
        short_id = f"sr{STREAMRIP_CACHE_COUNTER}"

        # Store in cache
        STREAMRIP_RESULT_CACHE[short_id] = data_string

        # Clean up cache if it gets too large (keep last 500 entries)
        if len(STREAMRIP_RESULT_CACHE) > 500:
            # Get oldest keys (first 50)
            oldest_keys = list(STREAMRIP_RESULT_CACHE.keys())[:50]
            for key in oldest_keys:
                del STREAMRIP_RESULT_CACHE[key]

        return short_id
    except Exception as e:
        LOGGER.error(f"Streamrip ID generation error: {e}")
        return f"sr{int(time_module.time())}"


def decrypt_streamrip_data(short_id):
    """Get the original data from the short ID."""
    try:
        if short_id in STREAMRIP_RESULT_CACHE:
            return STREAMRIP_RESULT_CACHE[short_id]
        LOGGER.warning(f"Streamrip ID not found in cache: {short_id}")
        return short_id
    except Exception as e:
        LOGGER.error(f"Streamrip ID lookup error: {e}")
        return short_id


async def _get_or_create_cached_client(platform_name, config):
    """Get cached client or create new one with authentication."""
    try:
        current_time = time_module.time()
        cache_key = f"{platform_name}_client"

        # Check if we have a valid cached client
        if cache_key in STREAMRIP_CLIENT_CACHE:
            cached_time, cached_client = STREAMRIP_CLIENT_CACHE[cache_key]
            if current_time - cached_time < CLIENT_CACHE_EXPIRY:
                # Verify client is still valid
                if (
                    hasattr(cached_client, "session")
                    and cached_client.session
                    and not cached_client.session.closed
                ):
                    return cached_client
                # Remove invalid cached client
                del STREAMRIP_CLIENT_CACHE[cache_key]

        # Create new client with timeout
        client = None
        try:
            if platform_name == "qobuz":
                client = QobuzClient(config)
            elif platform_name == "tidal":
                client = TidalClient(config)
            elif platform_name == "deezer":
                client = DeezerClient(config)
            elif platform_name == "soundcloud":
                client = SoundcloudClient(config)
            else:
                LOGGER.warning(f"Unsupported platform for caching: {platform_name}")
                return None

            # Authenticate with timeout
            if hasattr(client, "login"):
                await asyncio.wait_for(
                    client.login(), timeout=10.0
                )  # 10 second auth timeout

            # Cache the authenticated client
            STREAMRIP_CLIENT_CACHE[cache_key] = (current_time, client)

            # Clean up old cache entries
            if len(STREAMRIP_CLIENT_CACHE) > 10:
                oldest_key = min(
                    STREAMRIP_CLIENT_CACHE.keys(),
                    key=lambda k: STREAMRIP_CLIENT_CACHE[k][0],
                )
                old_time, old_client = STREAMRIP_CLIENT_CACHE[oldest_key]
                # Clean up old client session
                if (
                    hasattr(old_client, "session")
                    and old_client.session
                    and not old_client.session.closed
                ):
                    with contextlib.suppress(Exception):
                        await old_client.session.close()
                del STREAMRIP_CLIENT_CACHE[oldest_key]

            return client

        except TimeoutError:
            LOGGER.warning(f"Authentication timeout for {platform_name} (10s)")
            if (
                client
                and hasattr(client, "session")
                and client.session
                and not client.session.closed
            ):
                with contextlib.suppress(Exception):
                    await client.session.close()
            return None
        except Exception as auth_error:
            LOGGER.warning(
                f"Authentication failed for {platform_name}: {auth_error}"
            )
            if (
                client
                and hasattr(client, "session")
                and client.session
                and not client.session.closed
            ):
                with contextlib.suppress(Exception):
                    await client.session.close()
            return None

    except Exception as e:
        LOGGER.error(f"Error creating cached client for {platform_name}: {e}")
        return None


async def perform_inline_streamrip_search(query, platform, media_type, user_id):
    """Perform streamrip search for inline queries with direct platform authentication."""
    try:
        # Check cache first
        cache_key = generate_streamrip_cache_key(
            query, platform, media_type, user_id
        )
        if cache_key in STREAMRIP_SEARCH_CACHE:
            cached_time, cached_results = STREAMRIP_SEARCH_CACHE[cache_key]
            # Use cached results if less than 5 minutes old
            if time_module.time() - cached_time < 300:
                return cached_results

        # Initialize streamrip clients directly for inline search
        clients = {}

        # Import streamrip configuration
        from bot.helper.streamrip_utils.streamrip_config import streamrip_config

        # Ensure streamrip config is initialized
        if not streamrip_config.is_initialized():
            await streamrip_config.initialize()

        config = streamrip_config.get_config()
        if not config:
            LOGGER.warning("Streamrip config not available for inline search")
            return []

        # Initialize clients based on available credentials
        if platform:
            # Search specific platform
            platforms_to_search = [platform]
        else:
            # Search all configured platforms based on streamrip config
            platforms_to_search = []
            platform_status = streamrip_config.get_platform_status()

            # Only include platforms that are enabled and have credentials
            for platform_name, enabled in platform_status.items():
                if enabled and platform_name in [
                    "qobuz",
                    "tidal",
                    "deezer",
                    "soundcloud",
                ]:
                    platforms_to_search.append(platform_name)

        if not platforms_to_search:
            LOGGER.warning("No streamrip platforms configured for inline search")
            return []

        # Initialize clients with caching and parallel authentication
        auth_tasks = []
        for platform_name in platforms_to_search:
            auth_tasks.append(_get_or_create_cached_client(platform_name, config))

        # Execute authentication in parallel with individual timeouts
        auth_results = await asyncio.gather(*auth_tasks, return_exceptions=True)

        # Process authentication results
        for i, result in enumerate(auth_results):
            platform_name = platforms_to_search[i]
            if isinstance(result, Exception):
                LOGGER.warning(
                    f"Failed to authenticate {platform_name} for inline search: {result}"
                )
                continue
            if result:
                clients[platform_name] = result

        if not clients:
            LOGGER.warning(
                "No streamrip clients could be initialized for inline search"
            )
            return []

        # Perform searches on all available platforms
        all_results = []
        search_tasks = []

        for platform_name, client in clients.items():
            search_tasks.append(
                _search_platform_inline(client, platform_name, query, media_type)
            )

        # Execute searches concurrently
        platform_results = await asyncio.gather(
            *search_tasks, return_exceptions=True
        )

        # Process results
        for i, result in enumerate(platform_results):
            platform_name = list(clients.keys())[i]
            if isinstance(result, Exception):
                LOGGER.warning(
                    f"Search failed for platform {platform_name}: {result}"
                )
                continue
            if result:
                all_results.extend(result)

        # Sort by relevance (title match first, then artist match)
        query_lower = query.lower()

        def relevance_score(result):
            score = 0
            title = result.get("title", "").lower()
            artist = result.get("artist", "").lower()

            if query_lower in title:
                score += 10
            if query_lower in artist:
                score += 5
            if any(word in title for word in query_lower.split()):
                score += 3
            if any(word in artist for word in query_lower.split()):
                score += 2
            return score

        all_results.sort(key=relevance_score, reverse=True)

        # Cache results
        STREAMRIP_SEARCH_CACHE[cache_key] = (time_module.time(), all_results)

        # Clean up cache if too large (increased for more results)
        if len(STREAMRIP_SEARCH_CACHE) > 50:
            oldest_key = min(
                STREAMRIP_SEARCH_CACHE.keys(),
                key=lambda k: STREAMRIP_SEARCH_CACHE[k][0],
            )
            del STREAMRIP_SEARCH_CACHE[oldest_key]

        return all_results

    except Exception as e:
        LOGGER.error(f"Error in inline streamrip search: {e}")
        return []
    finally:
        # Cleanup clients to prevent unclosed sessions
        if "clients" in locals():
            await _cleanup_inline_clients(clients)


async def _cleanup_inline_clients(clients):
    """Cleanup inline search clients to prevent session leaks"""
    for platform_name, client in clients.items():
        try:
            # Try multiple session cleanup approaches
            cleanup_tasks = []

            if (
                hasattr(client, "session")
                and client.session
                and not client.session.closed
            ):
                cleanup_tasks.append(client.session.close())
            elif (
                hasattr(client, "_session")
                and client._session
                and not client._session.closed
            ):
                cleanup_tasks.append(client._session.close())
            elif (
                hasattr(client, "_http_session")
                and client._http_session
                and not client._http_session.closed
            ):
                cleanup_tasks.append(client._http_session.close())

            # Also try to close any connector
            if hasattr(client, "connector") and client.connector:
                cleanup_tasks.append(client.connector.close())
            elif hasattr(client, "_connector") and client._connector:
                cleanup_tasks.append(client._connector.close())

            # Execute cleanup with timeout
            if cleanup_tasks:
                await asyncio.wait_for(
                    asyncio.gather(*cleanup_tasks, return_exceptions=True),
                    timeout=3.0,
                )

        except TimeoutError:
            LOGGER.warning(f"Cleanup timeout for {platform_name} inline client")
        except Exception as cleanup_error:
            LOGGER.warning(
                f"Failed to cleanup {platform_name} inline client: {cleanup_error}"
            )


async def _search_platform_inline(client, platform_name, query, media_type):
    """Perform search on a specific platform for inline queries."""
    try:
        results = []

        # Determine search types based on media_type filter
        if media_type:
            search_types = [media_type]
        else:
            # Use platform-specific search types (prioritize tracks and albums for better results)
            platform_types = {
                "qobuz": ["track", "album", "artist", "playlist"],
                "deezer": ["track", "album", "artist", "playlist"],
                "tidal": ["track", "album", "artist", "playlist"],
                "soundcloud": ["track"],  # SoundCloud mainly supports tracks
            }
            search_types = platform_types.get(platform_name, ["track"])

        # Perform search for each type with timeout and limit
        for search_type in search_types:
            try:
                # Search using streamrip client API with timeout and reasonable limit
                search_response = await asyncio.wait_for(
                    client.search(
                        search_type, query, limit=50
                    ),  # Reduced limit for faster response
                    timeout=8.0,  # 8 second timeout per search type
                )

                if search_response:
                    # Extract results from platform-specific containers
                    actual_results = _extract_results_from_containers_inline(
                        search_response, platform_name, search_type
                    )

                    for item in actual_results:
                        # Extract metadata without excessive logging
                        result = _extract_search_result_inline(
                            item, platform_name, search_type
                        )
                        if result:
                            results.append(result)
                            # Limit results per platform to avoid overwhelming the response
                            if len(results) >= 25:  # Max 25 results per platform
                                break

                    # If we have enough results, break early
                    if len(results) >= 25:
                        break
                else:
                    LOGGER.debug(
                        f"Platform {platform_name} {search_type} returned empty response"
                    )

            except TimeoutError:
                LOGGER.warning(
                    f"Search timeout for {search_type} on {platform_name} (8s)"
                )
                continue
            except Exception as search_error:
                LOGGER.warning(
                    f"Search type '{search_type}' failed on {platform_name}: {search_error}"
                )
                continue

        return results  # Return all results, no limit per platform

    except Exception as e:
        LOGGER.error(f"Platform search failed for {platform_name}: {e}")
        return []


def _extract_results_from_containers_inline(search_response, platform, search_type):
    """Extract actual results from platform-specific response containers for inline search."""
    actual_results = []

    try:
        if isinstance(search_response, dict):
            # Handle different response structures
            if "items" in search_response:
                result_container = search_response["items"]
            elif "data" in search_response:
                result_container = search_response["data"]
            elif "results" in search_response:
                result_container = search_response["results"]
            elif search_type in search_response:
                result_container = search_response[search_type]
            else:
                # Fallback: treat as single item
                actual_results.append(search_response)
                return actual_results

            # Extract from container
            if isinstance(result_container, list):
                actual_results = result_container
            elif isinstance(result_container, dict):
                if "items" in result_container:
                    actual_results = result_container["items"]
                elif "data" in result_container:
                    actual_results = result_container["data"]
                else:
                    # Fallback: treat as single item
                    actual_results.append(result_container)
        elif isinstance(search_response, list):
            # Handle list responses - check if it contains dictionaries with 'items'
            actual_results = []
            for list_item in search_response:
                if isinstance(list_item, dict):
                    # Check for nested structures like Qobuz: {'tracks': {'items': [...]}}
                    extracted_from_nested = False

                    # Check all possible nested containers
                    for container_type in [
                        "tracks",
                        "albums",
                        "artists",
                        "playlists",
                    ]:
                        if (
                            container_type in list_item
                            and isinstance(list_item[container_type], dict)
                            and "items" in list_item[container_type]
                        ):
                            items_to_add = list_item[container_type]["items"]
                            actual_results.extend(items_to_add)
                            extracted_from_nested = True
                            break

                    # If no nested container found, check for direct 'items'
                    if not extracted_from_nested and "items" in list_item:
                        # This is a paginated response wrapped in a list (Tidal format)
                        actual_results.extend(list_item["items"])
                        extracted_from_nested = True

                    # If still no extraction, treat as direct item
                    if not extracted_from_nested:
                        actual_results.append(list_item)
                else:
                    # Direct item in list
                    actual_results.append(list_item)
        else:
            # Single item response
            actual_results = [search_response]

    except Exception as e:
        LOGGER.warning(f"Failed to extract results from {platform} response: {e}")
        actual_results = []

    return actual_results


def _extract_search_result_inline(item, platform, search_type):
    """Extract search result metadata for inline search."""
    try:
        result = {
            "platform": platform,
            "type": search_type,
            "title": "Unknown",
            "artist": "Unknown Artist",
            "album": "",
            "duration": 0,
            "url": "",
            "id": "",
        }

        # Handle Deezer's nested data structure
        if platform == "deezer" and isinstance(item, dict) and "data" in item:
            # Deezer wraps results in a 'data' array, extract the first item
            if isinstance(item["data"], list) and item["data"]:
                actual_item = item["data"][0]  # Get first track from the data array
            else:
                actual_item = item
        else:
            actual_item = item

        # Extract title - handle multiple possible field names
        if actual_item.get("title"):
            result["title"] = str(actual_item["title"])
        elif actual_item.get("name"):
            result["title"] = str(actual_item["name"])
        elif actual_item.get("track_title"):
            result["title"] = str(actual_item["track_title"])
        elif actual_item.get("song_title"):
            result["title"] = str(actual_item["song_title"])

        # Platform-specific artist extraction with enhanced Deezer support
        if platform == "deezer":
            # Deezer-specific artist extraction - handle multiple possible field structures
            if "artist" in actual_item:
                if isinstance(actual_item["artist"], dict):
                    result["artist"] = actual_item["artist"].get(
                        "name", str(actual_item["artist"])
                    )
                elif isinstance(actual_item["artist"], str):
                    result["artist"] = actual_item["artist"]
                else:
                    result["artist"] = str(actual_item["artist"])
            elif actual_item.get("artists"):
                if (
                    isinstance(actual_item["artists"], list)
                    and actual_item["artists"]
                ):
                    first_artist = actual_item["artists"][0]
                    if isinstance(first_artist, dict):
                        result["artist"] = first_artist.get(
                            "name", str(first_artist)
                        )
                    else:
                        result["artist"] = str(first_artist)
                elif isinstance(actual_item["artists"], dict):
                    result["artist"] = actual_item["artists"].get(
                        "name", str(actual_item["artists"])
                    )
                elif isinstance(actual_item["artists"], str):
                    result["artist"] = actual_item["artists"]
            elif actual_item.get("contributors"):
                # Deezer sometimes uses 'contributors' field
                if (
                    isinstance(actual_item["contributors"], list)
                    and actual_item["contributors"]
                ):
                    first_contributor = actual_item["contributors"][0]
                    if isinstance(first_contributor, dict):
                        result["artist"] = first_contributor.get(
                            "name", str(first_contributor)
                        )
                    else:
                        result["artist"] = str(first_contributor)
            # Try alternative Deezer field names
            elif "artist_name" in actual_item:
                result["artist"] = str(actual_item["artist_name"])
            elif "performer" in actual_item:
                if isinstance(actual_item["performer"], dict):
                    result["artist"] = actual_item["performer"].get(
                        "name", str(actual_item["performer"])
                    )
                else:
                    result["artist"] = str(actual_item["performer"])
            # Special handling for artist and playlist search types
            elif search_type == "artist":
                # For artist searches, the title IS the artist name
                result["artist"] = result["title"]
            elif search_type == "playlist":
                # For playlist searches, try to get the creator/owner
                if "creator" in actual_item:
                    if isinstance(actual_item["creator"], dict):
                        result["artist"] = actual_item["creator"].get(
                            "name", actual_item["creator"].get("username", "Unknown")
                        )
                    else:
                        result["artist"] = str(actual_item["creator"])
                elif "user" in actual_item:
                    if isinstance(actual_item["user"], dict):
                        result["artist"] = actual_item["user"].get(
                            "name", actual_item["user"].get("username", "Unknown")
                        )
                    else:
                        result["artist"] = str(actual_item["user"])
                elif "owner" in actual_item:
                    if isinstance(actual_item["owner"], dict):
                        result["artist"] = actual_item["owner"].get(
                            "name", actual_item["owner"].get("username", "Unknown")
                        )
                    else:
                        result["artist"] = str(actual_item["owner"])
        # Generic artist extraction for other platforms
        elif "artist" in item:
            if isinstance(item["artist"], dict):
                result["artist"] = item["artist"].get("name", str(item["artist"]))
            else:
                result["artist"] = str(item["artist"])
        elif "performer" in item:
            # Qobuz uses 'performer' instead of 'artist'
            if isinstance(item["performer"], dict):
                result["artist"] = item["performer"].get(
                    "name", str(item["performer"])
                )
            else:
                result["artist"] = str(item["performer"])
        elif item.get("artists"):
            if isinstance(item["artists"], list) and item["artists"]:
                first_artist = item["artists"][0]
                if isinstance(first_artist, dict):
                    result["artist"] = first_artist.get("name", str(first_artist))
                else:
                    result["artist"] = str(first_artist)
            elif isinstance(item["artists"], dict):
                result["artist"] = item["artists"].get("name", str(item["artists"]))
        elif item.get("contributors"):
            # Deezer sometimes uses 'contributors' field
            if isinstance(item["contributors"], list) and item["contributors"]:
                first_contributor = item["contributors"][0]
                if isinstance(first_contributor, dict):
                    result["artist"] = first_contributor.get(
                        "name", str(first_contributor)
                    )
                else:
                    result["artist"] = str(first_contributor)
        elif "user" in item:
            # SoundCloud uses 'user' field
            if isinstance(item["user"], dict):
                result["artist"] = item["user"].get(
                    "username", item["user"].get("name", str(item["user"]))
                )
            else:
                result["artist"] = str(item["user"])
        elif "uploader" in item:
            # Alternative SoundCloud field
            result["artist"] = str(item["uploader"])

        # Extract album
        if "album" in actual_item:
            if isinstance(actual_item["album"], dict):
                result["album"] = actual_item["album"].get(
                    "title",
                    actual_item["album"].get("name", str(actual_item["album"])),
                )
            else:
                result["album"] = str(actual_item["album"])

        # Extract duration
        if "duration" in actual_item:
            result["duration"] = (
                int(actual_item["duration"]) if actual_item["duration"] else 0
            )

        # Extract ID and generate URL
        if "id" in actual_item:
            result["id"] = str(actual_item["id"])
            result["url"] = _generate_platform_url_inline(
                platform, search_type, result["id"]
            )

        # Enhanced fallback for missing metadata
        if result["title"] == "Unknown":
            # Try alternative title fields
            for title_field in ["name", "track_title", "song_title"]:
                if actual_item.get(title_field):
                    result["title"] = str(actual_item[title_field])
                    break

            # If still unknown, try any field that might contain a title
            if result["title"] == "Unknown":
                for key, value in actual_item.items():
                    if key.lower() in ["title", "name", "track", "song"] and value:
                        result["title"] = str(value)
                        break

        if result["artist"] == "Unknown Artist":
            # Try alternative artist fields
            for artist_field in ["artist_name", "performer_name", "creator_name"]:
                if actual_item.get(artist_field):
                    result["artist"] = str(actual_item[artist_field])
                    break

            # If still unknown, try any field that might contain an artist
            if result["artist"] == "Unknown Artist":
                for key, value in actual_item.items():
                    if (
                        key.lower()
                        in ["artist", "performer", "creator", "author", "singer"]
                        and value
                    ):
                        if isinstance(value, dict) and "name" in value:
                            result["artist"] = str(value["name"])
                        elif isinstance(value, str):
                            result["artist"] = str(value)
                        break

        return result

    except Exception as e:
        LOGGER.warning(f"Failed to extract result from {platform}: {e}")
        return None


def _generate_platform_url_inline(platform, media_type, media_id):
    """Generate platform URL for inline search results."""
    url_templates = {
        "qobuz": {
            "track": f"https://www.qobuz.com/track/{media_id}",
            "album": f"https://www.qobuz.com/album/{media_id}",
            "artist": f"https://www.qobuz.com/artist/{media_id}",
            "playlist": f"https://www.qobuz.com/playlist/{media_id}",
        },
        "tidal": {
            "track": f"https://listen.tidal.com/track/{media_id}",
            "album": f"https://listen.tidal.com/album/{media_id}",
            "artist": f"https://listen.tidal.com/artist/{media_id}",
            "playlist": f"https://listen.tidal.com/playlist/{media_id}",
        },
        "deezer": {
            "track": f"https://www.deezer.com/track/{media_id}",
            "album": f"https://www.deezer.com/album/{media_id}",
            "artist": f"https://www.deezer.com/artist/{media_id}",
            "playlist": f"https://www.deezer.com/playlist/{media_id}",
        },
        "soundcloud": {
            "track": f"https://soundcloud.com/track/{media_id}",
            "playlist": f"https://soundcloud.com/playlist/{media_id}",
        },
    }

    return url_templates.get(platform, {}).get(
        media_type, f"https://{platform}.com/{media_type}/{media_id}"
    )


@new_task
async def inline_streamrip_search(_, inline_query: InlineQuery):
    """Handle inline queries for streamrip search."""
    # Check if streamrip is enabled
    if not Config.STREAMRIP_ENABLED:
        LOGGER.warning("Streamrip is disabled")
        await inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id="disabled",
                    title="Streamrip search is disabled",
                    description="Streamrip has been disabled by the administrator",
                    input_message_content=InputTextMessageContent(
                        "🎵 Streamrip search is currently disabled by the administrator."
                    ),
                )
            ],
            cache_time=300,
        )
        return

    # Skip empty queries
    if not inline_query.query:
        await inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id="help",
                    title="🎵 Search music on streaming platforms",
                    description="Type a search query to find music",
                    input_message_content=InputTextMessageContent(
                        "🎵 <b>Streamrip Inline Search</b>\n\n"
                        "Type a query to search for music across streaming platforms.\n\n"
                        "📋 <b>Format:</b> <code>@bot_username query</code>\n"
                        "🎯 <b>Filter by type:</b> <code>@bot_username track:query</code>\n"
                        "🎛️ <b>Filter by platform:</b> <code>@bot_username qobuz:query</code>\n\n"
                        "🎵 <b>Supported types:</b> track, album, playlist, artist\n"
                        "🎧 <b>Supported platforms:</b> qobuz, tidal, deezer, soundcloud"
                    ),
                )
            ],
            cache_time=300,
        )
        return

    # Parse query for platform and media type filters
    query = inline_query.query.strip()
    platform = None
    media_type = None

    # Implement debouncing: require minimum query length to prevent searches on every character
    if len(query) < 3:
        await inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id="short_query",
                    title="⏳ Keep typing...",
                    description=f"Type at least 3 characters to search (current: {len(query)})",
                    input_message_content=InputTextMessageContent(
                        f"⏳ **Keep typing...**\n\nType at least 3 characters to search.\n\nCurrent query: `{query}` ({len(query)} characters)"
                    ),
                )
            ],
            cache_time=1,  # Very short cache for typing feedback
        )
        return

    # Check for multiple filters (platform:type:query or type:platform:query)
    platform = None
    media_type = None
    if ":" in query:
        parts = query.split(":", 2)  # Split into max 3 parts

        for part in parts[
            :-1
        ]:  # Check all parts except the last (which is the query)
            part = part.lower().strip()

            if part in ["qobuz", "tidal", "deezer", "soundcloud"] and not platform:
                platform = part
            elif part in ["track", "album", "playlist", "artist"] and not media_type:
                media_type = part

        # The remaining part is the actual query
        if len(parts) >= 2:
            query = parts[-1].strip()  # Last part is always the query

    # If query is empty after parsing, show help
    if not query:
        LOGGER.warning(
            f"Empty query after parsing. Platform: {platform}, Type: {media_type}"
        )
        await inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id="empty_query",
                    title="Please provide a search query",
                    description=f"Type your search query after {platform or media_type}:",
                    input_message_content=InputTextMessageContent(
                        f"Please provide a search query after {platform or media_type}:"
                    ),
                )
            ],
            cache_time=5,
        )
        return

    try:
        # Use asyncio.wait_for with optimized timeout for inline queries
        search_timeout = (
            35  # Increased timeout to allow for authentication and search
        )

        # Perform search with timeout protection
        results = await asyncio.wait_for(
            perform_inline_streamrip_search(
                query, platform, media_type, inline_query.from_user.id
            ),
            timeout=search_timeout,
        )

        if not results:
            LOGGER.warning(f"No results found for query '{query}'")
            await inline_query.answer(
                results=[
                    InlineQueryResultArticle(
                        id="no_results",
                        title="No music found",
                        description=f"No results found for: {query}",
                        input_message_content=InputTextMessageContent(
                            f"🎵 No music found matching: <code>{query}</code>\n\n"
                            "💡 Try different keywords or check spelling."
                        ),
                    )
                ],
                cache_time=30,
            )
            return

        # Format results for inline query (Telegram limit: 50 results)
        min(len(results), 50)  # Telegram's inline result limit
        inline_results = []

        # Add info result if we have more than 50 results
        if len(results) > 50:
            inline_results.append(
                InlineQueryResultArticle(
                    id="info_limit",
                    title=f"📊 Found {len(results)} results",
                    description="Showing top 50 results (Telegram limit). Refine your search for better results.",
                    input_message_content=InputTextMessageContent(
                        f"🔍 <b>Search Results</b>\n\n"
                        f"📊 Found <b>{len(results)}</b> total results\n"
                        f"📋 Showing top <b>50</b> results (Telegram limit)\n\n"
                        f"💡 <i>Tip: Use more specific keywords to get better results</i>"
                    ),
                )
            )

        for i, result in enumerate(
            results[: 49 if len(results) > 50 else 50]
        ):  # Reserve 1 slot for info if needed
            # Create result ID
            result_id = f"sr_{i}_{int(time_module.time())}"

            # Format title and description
            title = result.get("title", "Unknown")
            artist = result.get("artist", "")
            platform_name = result.get("platform", "").title()
            media_type_name = result.get("type", "track").title()

            # Platform emoji
            platform_emoji = {
                "qobuz": "🟦",
                "tidal": "⚫",
                "deezer": "🟣",
                "soundcloud": "🟠",
            }.get(result.get("platform", ""), "🎵")

            # Type emoji
            type_emoji = {
                "track": "🎵",
                "album": "💿",
                "playlist": "📋",
                "artist": "👤",
            }.get(result.get("type", "track"), "🎵")

            display_title = f"{platform_emoji} {title}"
            if artist:
                display_title += f" - {artist}"

            description = f"{type_emoji} {media_type_name} on {platform_name}"
            if result.get("duration"):
                minutes = result["duration"] // 60
                seconds = result["duration"] % 60
                description += f" • {minutes}:{seconds:02d}"

            # Store result data for retrieval
            result_data = {
                "url": result.get("url", ""),
                "platform": result.get("platform", ""),
                "type": result.get("type", "track"),
                "title": title,
                "artist": artist,
                "query": query,
            }

            # Create encrypted ID for callback data
            encrypted_id = encrypt_streamrip_data(str(result_data))
            callback_data = f"streamrip_dl_{encrypted_id}"

            # Check callback data length (Telegram limit is 64 bytes)
            if len(callback_data) > 64:
                LOGGER.warning(
                    f"Callback data too long ({len(callback_data)} bytes): {callback_data}"
                )
                # Truncate if necessary (this shouldn't happen with our short IDs)
                callback_data = callback_data[:64]

            # Create message content - this will be sent when user clicks the inline result
            message_text = f"🎵 <b>{title}</b>\n"
            if artist:
                message_text += f"👤 <b>Artist:</b> {artist}\n"
            if result.get("album"):
                message_text += f"💿 <b>Album:</b> {result['album']}\n"
            message_text += f"🎧 <b>Platform:</b> {platform_name}\n"
            message_text += f"📁 <b>Type:</b> {media_type_name}\n\n"
            message_text += "⏳ <i>Preparing quality selection...</i>"

            # Create reply markup with callback button that will trigger quality selector
            reply_markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            text=f"🎵 Download {media_type_name}",
                            callback_data=callback_data,
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            text="🔍 Search Again",
                            switch_inline_query_current_chat="",
                        )
                    ],
                ]
            )

            inline_results.append(
                InlineQueryResultArticle(
                    id=result_id,
                    title=display_title,
                    description=description,
                    input_message_content=InputTextMessageContent(message_text),
                    reply_markup=reply_markup,
                )
            )

        # Answer the inline query with timeout protection
        try:
            await asyncio.wait_for(
                inline_query.answer(
                    results=inline_results,
                    cache_time=300,  # Cache for 5 minutes
                    is_personal=True,
                ),
                timeout=10.0,  # 10 second timeout for sending results
            )
        except TimeoutError:
            LOGGER.warning("Timeout while sending inline query results")
            # Try to send a simple timeout message
            try:
                await asyncio.wait_for(
                    inline_query.answer(
                        results=[
                            InlineQueryResultArticle(
                                id="send_timeout",
                                title="⏰ Response Timeout",
                                description="Results took too long to send. Please try again.",
                                input_message_content=InputTextMessageContent(
                                    "⏰ **Response Timeout**\n\nResults took too long to send. Please try searching again."
                                ),
                            )
                        ],
                        cache_time=5,
                    ),
                    timeout=5.0,
                )
            except Exception:
                pass  # If we can't even send timeout message, just give up
            return

    except TimeoutError:
        LOGGER.warning(f"Search timed out after {search_timeout}s")
        # Send timeout message with suggestion to use regular search
        await inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id="timeout",
                    title="⏰ Search Timeout",
                    description=f"Search for '{query}' took too long. Try a more specific query or use /srs command.",
                    input_message_content=InputTextMessageContent(
                        f"⏰ **Search Timeout**\n\nSearch for '{query}' took too long for inline mode.\n\n💡 **Try:**\n• More specific search terms\n• Use `/srs {query}` command instead\n• Search for specific artists or albums"
                    ),
                )
            ],
            cache_time=0,
        )

    except Exception as e:
        error_msg = str(e)
        LOGGER.error(f"Error in inline streamrip search: {error_msg}")

        # Handle specific Telegram errors
        if (
            "QUERY_ID_INVALID" in error_msg
            or "query id is invalid" in error_msg.lower()
        ):
            LOGGER.warning("Query ID invalid - user typed too fast or query expired")
            # Don't try to answer an invalid query - it will just cause more errors
            return
        if "QUERY_TOO_OLD" in error_msg or "query too old" in error_msg.lower():
            LOGGER.warning("Query too old - search took too long")
            return

        # Try to answer with error message for other errors (with timeout protection)
        try:
            await asyncio.wait_for(
                inline_query.answer(
                    results=[
                        InlineQueryResultArticle(
                            id="error",
                            title="🔍 Search Error",
                            description="An error occurred while searching",
                            input_message_content=InputTextMessageContent(
                                f"❌ **Search Error**\n\n{error_msg}\n\n💡 Please try again with different keywords."
                            ),
                        )
                    ],
                    cache_time=5,
                ),
                timeout=5.0,  # 5 second timeout for error response
            )
        except TimeoutError:
            LOGGER.warning("Timeout while sending error response to inline query")
            return
        except Exception as answer_error:
            LOGGER.warning(f"Failed to answer error query: {answer_error}")
            # If we can't answer the query, just log and return
            return


async def handle_streamrip_callback(_, callback_query):
    """Handle callback queries for streamrip inline search results."""
    try:
        # Check if this is a quality selector callback
        callback_data = callback_query.data
        if callback_data.startswith("srq"):
            # Check if there's an active quality selector for this user
            from bot.helper.streamrip_utils.quality_selector import (
                get_active_quality_selector,
            )

            quality_selector = get_active_quality_selector(
                callback_query.from_user.id
            )

            if quality_selector:
                # Process the callback through the quality selector
                await quality_selector._handle_callback(
                    _, callback_query, quality_selector
                )
                return

            LOGGER.warning(
                f"No active quality selector found for user {callback_query.from_user.id}"
            )
            await callback_query.answer(
                "❌ Quality selection session expired. Please try again.",
                show_alert=True,
            )
            return

        # Extract callback data for streamrip downloads
        if not callback_data.startswith("streamrip_dl_"):
            LOGGER.warning(f"Invalid callback data format: {callback_data}")
            return

        # Get the encrypted ID
        encrypted_id = callback_data.replace("streamrip_dl_", "")

        # Decrypt the result data
        result_data_str = decrypt_streamrip_data(encrypted_id)

        if result_data_str == encrypted_id:  # Decryption failed
            LOGGER.error("Decryption failed for callback data")
            await callback_query.answer(
                "❌ Invalid or expired link. Please search again.", show_alert=True
            )
            return

        # Parse the result data
        try:
            import ast

            result_data = ast.literal_eval(result_data_str)
        except (ValueError, SyntaxError) as e:
            LOGGER.error(f"Failed to parse streamrip result data: {e}")
            await callback_query.answer(
                "❌ Invalid result data. Please search again.", show_alert=True
            )
            return

        # Check if streamrip is enabled
        if not Config.STREAMRIP_ENABLED:
            await callback_query.answer(
                "❌ Streamrip downloads are disabled!", show_alert=True
            )
            return

        # Extract data
        url = result_data.get("url", "")
        platform = result_data.get("platform", "")
        media_type = result_data.get("type", "track")

        if not url:
            await callback_query.answer(
                "❌ Invalid download URL. Please search again.", show_alert=True
            )
            return

        # Answer the callback query silently (no popup message)
        await callback_query.answer()

        # For inline callbacks, we need to create a fake message object
        # since callback_query.message is None for inline results
        if not callback_query.message:
            # Create a minimal message-like object for the listener
            from types import SimpleNamespace

            # Import TgClient to get the bot instance for sending messages
            from bot.core.aeon_client import TgClient

            fake_message = SimpleNamespace()
            fake_message.from_user = callback_query.from_user
            fake_message.chat = SimpleNamespace()
            fake_message.chat.id = (
                callback_query.from_user.id
            )  # Use user's private chat

            # Create a proper chat type object with .name attribute
            fake_chat_type = SimpleNamespace()
            fake_chat_type.name = "PRIVATE"
            fake_message.chat.type = fake_chat_type

            fake_message.id = 0  # Dummy message ID
            fake_message.reply_to_message = None
            fake_message.sender_chat = None  # Required by StreamripListener

            # Add missing attributes for streamrip listener compatibility
            from datetime import datetime

            fake_message.date = (
                datetime.now()
            )  # Required for elapsed time calculation
            fake_message.text = "🎵 Streamrip download from inline search"  # Required for message text access

            # Add delete method to prevent errors in error handler
            async def fake_delete():
                """Fake delete method that does nothing"""
                return True

            fake_message.delete = fake_delete

            # Add reply method to fake message so quality selector can send messages
            async def fake_reply(
                text,
                quote=None,
                disable_web_page_preview=True,
                disable_notification=True,
                reply_markup=None,
                parse_mode=None,
            ):
                """Fake reply method that sends message to user's private chat"""
                return await TgClient.bot.send_message(
                    chat_id=callback_query.from_user.id,
                    text=text,
                    disable_web_page_preview=disable_web_page_preview,
                    disable_notification=disable_notification,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode,
                )

            fake_message.reply = fake_reply
            message_for_listener = fake_message

        else:
            # Use the callback query message but ensure it has the right user
            message_for_listener = callback_query.message
            # Set the from_user to the callback query user (the person who clicked)
            message_for_listener.from_user = callback_query.from_user

        # Create listener for download
        from bot.helper.listeners.streamrip_listener import StreamripListener

        listener = StreamripListener(message_for_listener, isLeech=True)

        # Set platform and media_type attributes for telegram uploader
        listener.platform = platform
        listener.media_type = media_type

        # Show quality selector
        from bot.helper.streamrip_utils.quality_selector import show_quality_selector

        selection = await show_quality_selector(listener, platform, media_type)

        if not selection:
            return

        quality = selection["quality"]
        codec = selection["codec"]

        # Start download
        from bot.helper.mirror_leech_utils.download_utils.streamrip_download import (
            add_streamrip_download,
        )

        await add_streamrip_download(listener, url, quality, codec, False)

    except Exception as e:
        LOGGER.error(f"Error in streamrip callback handler: {e}")
        with contextlib.suppress(Exception):
            await callback_query.answer(f"❌ Error: {e!s}", show_alert=True)


def init_streamrip_inline_search(bot, register_inline=True):
    """Initialize streamrip inline search handlers."""
    if not Config.STREAMRIP_ENABLED:
        LOGGER.warning(
            "Streamrip is disabled, skipping inline search initialization"
        )
        return

    from pyrogram import filters as pyrogram_filters
    from pyrogram.handlers import CallbackQueryHandler, InlineQueryHandler

    # Register streamrip inline query handler only if requested
    if register_inline:
        bot.add_handler(InlineQueryHandler(inline_streamrip_search))

    # Register streamrip callback handler for inline results
    async def debug_streamrip_callback(_, callback_query):
        await handle_streamrip_callback(_, callback_query)

    # Create proper filter for streamrip callbacks (including quality selector callbacks)
    streamrip_filter = pyrogram_filters.regex(r"^(streamrip_dl_|srq)")

    bot.add_handler(
        CallbackQueryHandler(debug_streamrip_callback, filters=streamrip_filter),
        group=-1,  # Higher priority than other callback handlers
    )
