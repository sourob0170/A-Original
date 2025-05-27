import asyncio
from functools import partial
from time import time
from typing import Any

from pyrogram.filters import regex, user
from pyrogram.handlers import CallbackQueryHandler

from bot import LOGGER
from bot.core.config_manager import Config
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


class StreamripSearchHandler:
    """Multi-platform search handler for streamrip"""

    def __init__(self, listener, query: str, platform: str | None = None):
        self.listener = listener
        self.query = query
        self.platform = platform
        self.search_results = {}
        self.current_page = 0
        self.results_per_page = 5
        self._reply_to = None
        self._time = time()
        self._timeout = 300  # 5 minutes for search
        self.event = asyncio.Event()
        self.selected_result = None
        self.clients = {}

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

            # Initialize enabled clients
            if platform_status.get("qobuz", False):
                self.clients["qobuz"] = QobuzClient(config)

            if platform_status.get("tidal", False):
                self.clients["tidal"] = TidalClient(config)

            if platform_status.get("deezer", False):
                self.clients["deezer"] = DeezerClient(config)

            if platform_status.get("soundcloud", False):
                self.clients["soundcloud"] = SoundcloudClient(config)

            return len(self.clients) > 0

        except Exception as e:
            LOGGER.error(f"Failed to initialize search clients: {e}")
            return False

    async def _cleanup_clients(self):
        """Cleanup streamrip clients to prevent unclosed sessions"""
        try:
            for platform, client in self.clients.items():
                try:
                    # Close client sessions if they have a close method
                    if hasattr(client, "close"):
                        await client.close()
                    elif hasattr(client, "session") and hasattr(
                        client.session, "close"
                    ):
                        await client.session.close()
                    elif hasattr(client, "_session") and hasattr(
                        client._session, "close"
                    ):
                        await client._session.close()

                    LOGGER.debug(f"Cleaned up {platform} client")
                except Exception as cleanup_error:
                    LOGGER.warning(
                        f"Failed to cleanup {platform} client: {cleanup_error}"
                    )

            # Clear clients dict
            self.clients.clear()

        except Exception as e:
            LOGGER.error(f"Error during client cleanup: {e}")

    async def search(self) -> dict[str, Any] | None:
        """Perform multi-platform search"""
        try:
            if not await self.initialize_clients():
                await send_message(
                    self.listener.message,
                    f"{self.listener.tag} ❌ No streamrip platforms are configured!",
                )
                return None

            # Show searching message
            search_msg = await send_message(
                self.listener.message,
                f"{self.listener.tag} 🔍 Searching for: **{self.query}**\n\n⏳ Please wait...",
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

            # Check if we have results
            total_results = sum(
                len(results) for results in self.search_results.values()
            )

            if total_results == 0:
                no_results_msg = await send_message(
                    self.listener.message,
                    f"{self.listener.tag} ❌ No results found for: **{self.query}**",
                )
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
                self.listener.message, f"{self.listener.tag} ❌ Search failed: {e!s}"
            )
            asyncio.create_task(auto_delete_message(error_msg, time=300))
            return None
        finally:
            # Always cleanup clients to prevent unclosed sessions
            await self._cleanup_clients()

    async def _search_platform(self, platform: str):
        """Search on a specific platform"""
        try:
            client = self.clients[platform]

            # Perform search (this is a simplified example - actual implementation depends on streamrip API)
            # Note: The actual search API may differ, this is based on typical patterns
            results = await self._perform_platform_search(client, platform)

            if results:
                self.search_results[platform] = results[
                    : Config.STREAMRIP_MAX_SEARCH_RESULTS
                ]
                LOGGER.info(f"Found {len(results)} results on {platform}")

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
                    if platform == "tidal":
                        LOGGER.warning(
                            f"⚠️ Tidal authentication failed: {auth_error}"
                        )
                        LOGGER.info(
                            "💡 Tidal requires interactive token setup. Use 'rip config --tidal' to authenticate."
                        )
                        return results
                    LOGGER.error(
                        f"❌ {platform.title()} authentication failed: {auth_error}"
                    )
                    return results

            # Perform search using correct API methods
            if hasattr(client, "search"):
                # Search for different media types
                search_types = ["track", "album"]  # Start with most common types

                for search_type in search_types:
                    try:
                        # Perform search with proper parameters
                        # Note: Different platforms may have different search API signatures
                        if platform == "qobuz":
                            # Qobuz search: search(query, media_type, limit)
                            search_response = await client.search(
                                self.query,
                                search_type + "s",  # Qobuz uses plural forms
                                limit=min(
                                    Config.STREAMRIP_MAX_SEARCH_RESULTS
                                    // len(search_types),
                                    10,
                                ),
                            )
                        elif platform == "deezer":
                            # Deezer search: search(query, media_type, limit)
                            search_response = await client.search(
                                self.query,
                                search_type + "s",  # Deezer uses plural forms
                                limit=min(
                                    Config.STREAMRIP_MAX_SEARCH_RESULTS
                                    // len(search_types),
                                    10,
                                ),
                            )
                        elif platform == "tidal":
                            # Tidal search: search(query, media_type, limit)
                            search_response = await client.search(
                                self.query,
                                search_type + "s",  # Tidal uses plural forms
                                limit=min(
                                    Config.STREAMRIP_MAX_SEARCH_RESULTS
                                    // len(search_types),
                                    10,
                                ),
                            )
                        else:
                            # Generic search
                            search_response = await client.search(
                                self.query,
                                search_type,
                                limit=min(
                                    Config.STREAMRIP_MAX_SEARCH_RESULTS
                                    // len(search_types),
                                    10,
                                ),
                            )

                        # Process search results
                        if search_response:
                            for item in search_response:
                                # Extract metadata based on platform and type
                                result = await self._extract_search_result(
                                    item, platform, search_type
                                )
                                if result:
                                    results.append(result)

                    except Exception as search_error:
                        LOGGER.debug(
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

            # Extract metadata based on item structure
            if hasattr(item, "title"):
                result["title"] = item.title
            elif isinstance(item, dict) and "title" in item:
                result["title"] = item["title"]
            elif hasattr(item, "name"):
                result["title"] = item.name

            if hasattr(item, "artist"):
                if hasattr(item.artist, "name"):
                    result["artist"] = item.artist.name
                else:
                    result["artist"] = str(item.artist)
            elif isinstance(item, dict) and "artist" in item:
                result["artist"] = item["artist"]

            if hasattr(item, "album") and item.album:
                if hasattr(item.album, "title"):
                    result["album"] = item.album.title
                else:
                    result["album"] = str(item.album)
            elif isinstance(item, dict) and "album" in item:
                result["album"] = item["album"]

            if hasattr(item, "duration"):
                result["duration"] = item.duration
            elif isinstance(item, dict) and "duration" in item:
                result["duration"] = item["duration"]

            if hasattr(item, "id"):
                result["id"] = str(item.id)
            elif isinstance(item, dict) and "id" in item:
                result["id"] = str(item["id"])

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

        except Exception as e:
            LOGGER.debug(f"Failed to extract search result: {e}")
            return None

    def _generate_platform_url(
        self, platform: str, media_type: str, media_id: str
    ) -> str:
        """Generate platform URL from ID"""
        url_templates = {
            "qobuz": {
                "track": f"https://www.qobuz.com/us-en/album/track/{media_id}",
                "album": f"https://www.qobuz.com/us-en/album/{media_id}",
                "artist": f"https://www.qobuz.com/us-en/interpreter/{media_id}",
                "playlist": f"https://www.qobuz.com/us-en/playlist/{media_id}",
            },
            "tidal": {
                "track": f"https://tidal.com/browse/track/{media_id}",
                "album": f"https://tidal.com/browse/album/{media_id}",
                "artist": f"https://tidal.com/browse/artist/{media_id}",
                "playlist": f"https://tidal.com/browse/playlist/{media_id}",
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

    async def _show_search_results(self):
        """Show search results with pagination"""
        buttons = ButtonMaker()

        # Get all results flattened
        all_results = []
        for results in self.search_results.values():
            all_results.extend(results)

        # Calculate pagination
        total_results = len(all_results)
        total_pages = (
            total_results + self.results_per_page - 1
        ) // self.results_per_page
        start_idx = self.current_page * self.results_per_page
        end_idx = min(start_idx + self.results_per_page, total_results)

        # Build message
        msg = f"🔍 **Search Results for:** {self.query}\n"
        msg += f"📊 Found {total_results} results across {len(self.search_results)} platforms\n"
        msg += f"📄 Page {self.current_page + 1}/{total_pages}\n\n"

        # Show results for current page
        for i in range(start_idx, end_idx):
            result = all_results[i]
            result_num = i + 1

            # Format result display
            title = (
                result["title"][:40] + "..."
                if len(result["title"]) > 40
                else result["title"]
            )
            artist = (
                result["artist"][:30] + "..."
                if len(result["artist"]) > 30
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

            msg += f"{result_num}. {platform_emoji} {type_emoji} **{title}**\n"
            msg += f"   👤 {artist}"

            if result["album"]:
                album = (
                    result["album"][:30] + "..."
                    if len(result["album"]) > 30
                    else result["album"]
                )
                msg += f" • 💿 {album}"

            if result["duration"]:
                duration_str = self._format_duration(result["duration"])
                msg += f" • ⏱️ {duration_str}"

            msg += f" • 🎯 {result['platform'].title()}\n\n"

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

        msg += (
            f"⏱️ Timeout: {get_readable_time(self._timeout - (time() - self._time))}"
        )

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
            # Send timeout message
            timeout_msg = await send_message(
                self.listener.message,
                f"{self.listener.tag} ⏰ Search selection timed out.",
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
            # Get selected result
            result_idx = int(data[2])
            all_results = []
            for results in obj.search_results.values():
                all_results.extend(results)

            if 0 <= result_idx < len(all_results):
                obj.selected_result = all_results[result_idx]

                # Show selection confirmation
                result = obj.selected_result
                msg = "✅ **Selected:**\n\n"
                msg += f"🎵 **{result['title']}**\n"
                msg += f"👤 Artist: {result['artist']}\n"

                if result["album"]:
                    msg += f"💿 Album: {result['album']}\n"

                msg += f"🎯 Platform: {result['platform'].title()}\n"
                msg += f"📁 Type: {result['type'].title()}\n\n"
                msg += "🚀 Starting download..."

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
            # Send cancellation message
            cancel_msg = await send_message(
                obj.listener.message,
                f"{obj.listener.tag} ❌ Search cancelled!",
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
    listener, query: str, platform: str | None = None
) -> dict[str, Any] | None:
    """Search for music across platforms"""
    search_handler = StreamripSearchHandler(listener, query, platform)
    return await search_handler.search()


async def search_music_auto_first(
    listener, query: str, platform: str | None = None
) -> dict[str, Any] | None:
    """Search for music and automatically return first result"""
    search_handler = StreamripSearchHandler(listener, query, platform)

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
                f"{listener.tag} ❌ No results found for: **{query}**",
            )
            asyncio.create_task(auto_delete_message(no_results_msg, time=300))
            return None

        # Return first result
        first_result = all_results[0]

        # Show auto-selection message
        msg = "⚡ **Auto-selected first result:**\n\n"
        msg += f"🎵 **{first_result['title']}**\n"
        msg += f"👤 Artist: {first_result['artist']}\n"

        if first_result["album"]:
            msg += f"💿 Album: {first_result['album']}\n"

        msg += f"🎯 Platform: {first_result['platform'].title()}\n"
        msg += f"📁 Type: {first_result['type'].title()}\n\n"
        msg += "🚀 Starting download..."

        auto_msg = await send_message(listener.message, msg)
        asyncio.create_task(auto_delete_message(auto_msg, time=10))

        return first_result

    finally:
        # Always cleanup clients to prevent unclosed sessions
        await search_handler._cleanup_clients()
