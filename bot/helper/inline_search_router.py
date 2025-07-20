#!/usr/bin/env python3
"""
Unified inline search router that handles both Zotify and Streamrip search
Based on the old working version with support for both platforms
"""

import asyncio
import os

from pyrogram.types import InlineQuery

from bot import LOGGER
from bot.core.config_manager import Config

# Global flag to track platform initialization
_platforms_initialized = False


async def ensure_platforms_initialized():
    """Ensure all platforms are properly initialized with credentials"""
    global _platforms_initialized

    if _platforms_initialized:
        return

    # Setup credentials from environment if available
    await setup_credentials_from_environment()

    # Initialize Streamrip if enabled
    if Config.STREAMRIP_ENABLED:
        try:
            from bot.helper.mirror_leech_utils.streamrip_utils.streamrip_config import (
                ensure_streamrip_initialized,
            )

            success = await ensure_streamrip_initialized()
            if not success:
                Config.STREAMRIP_ENABLED = False
        except Exception as e:
            LOGGER.error(f"❌ Streamrip initialization error: {e}")
            Config.STREAMRIP_ENABLED = False

    # Note: Zotify initialization is now lazy - only when platform-specific search is used
    # This improves startup time and prevents unnecessary initialization for unified search

    _platforms_initialized = True


async def ensure_zotify_initialized_on_demand():
    """Initialize Zotify only when needed for platform-specific searches"""
    if not Config.ZOTIFY_ENABLED:
        LOGGER.warning("⚠️ Zotify is disabled")
        return False

    # Setup credentials first
    await setup_credentials_from_environment()

    try:
        from bot.helper.mirror_leech_utils.zotify_utils.zotify_config import (
            ensure_zotify_initialized,
        )

        # Add timeout for Zotify initialization to prevent hanging
        return await asyncio.wait_for(ensure_zotify_initialized(), timeout=30.0)
    except TimeoutError:
        LOGGER.error("❌ Zotify on-demand initialization timed out after 30 seconds")
        return False
    except Exception as e:
        LOGGER.error(f"❌ Zotify on-demand initialization error: {e}")
        return False


async def setup_credentials_from_environment():
    """Setup platform credentials from environment variables with proper format"""
    try:
        # Setup Streamrip credentials with proper Config attribute assignment
        if all(
            [
                os.getenv("QOBUZ_EMAIL"),
                os.getenv("QOBUZ_PASSWORD"),
                os.getenv("QOBUZ_APP_ID"),
                os.getenv("QOBUZ_SECRETS"),
            ]
        ):
            Config.STREAMRIP_QOBUZ_EMAIL = os.getenv("QOBUZ_EMAIL")
            Config.STREAMRIP_QOBUZ_PASSWORD = os.getenv("QOBUZ_PASSWORD")
            Config.STREAMRIP_QOBUZ_APP_ID = os.getenv("QOBUZ_APP_ID")
            Config.STREAMRIP_QOBUZ_SECRETS = os.getenv("QOBUZ_SECRETS").split(",")
            Config.STREAMRIP_QOBUZ_USE_AUTH_TOKEN = False  # Use email/password auth

        if all(
            [
                os.getenv("TIDAL_ACCESS_TOKEN"),
                os.getenv("TIDAL_REFRESH_TOKEN"),
                os.getenv("TIDAL_USER_ID"),
            ]
        ):
            Config.STREAMRIP_TIDAL_ACCESS_TOKEN = os.getenv("TIDAL_ACCESS_TOKEN")
            Config.STREAMRIP_TIDAL_REFRESH_TOKEN = os.getenv("TIDAL_REFRESH_TOKEN")
            Config.STREAMRIP_TIDAL_USER_ID = os.getenv("TIDAL_USER_ID")
            Config.STREAMRIP_TIDAL_COUNTRY_CODE = os.getenv(
                "TIDAL_COUNTRY_CODE", "US"
            )
            Config.STREAMRIP_TIDAL_TOKEN_EXPIRY = os.getenv(
                "TIDAL_TOKEN_EXPIRY", "1748842786"
            )

        if os.getenv("DEEZER_ARL"):
            Config.STREAMRIP_DEEZER_ARL = os.getenv("DEEZER_ARL")

        if os.getenv("SOUNDCLOUD_CLIENT_ID"):
            Config.STREAMRIP_SOUNDCLOUD_CLIENT_ID = os.getenv("SOUNDCLOUD_CLIENT_ID")

        # Setup Zotify credentials
        if all([os.getenv("ZOTIFY_USERNAME"), os.getenv("ZOTIFY_CREDENTIALS")]):
            # Create Zotify credentials file
            import json
            from pathlib import Path

            zotify_dir = Path.home() / ".config" / "zotify"
            zotify_dir.mkdir(parents=True, exist_ok=True)

            credentials_file = zotify_dir / "credentials.json"
            with open(credentials_file, "w") as f:
                json.dump(
                    {
                        "username": os.getenv("ZOTIFY_USERNAME"),
                        "credentials": os.getenv("ZOTIFY_CREDENTIALS"),
                        "type": "AUTHENTICATION_STORED_SPOTIFY_CREDENTIALS",
                    },
                    f,
                )

        # Load from zotify_credentials.json if exists
        elif os.path.exists("zotify_credentials.json"):
            try:
                import json
                from pathlib import Path

                with open("zotify_credentials.json") as f:
                    zotify_creds = json.load(f)

                zotify_dir = Path.home() / ".config" / "zotify"
                zotify_dir.mkdir(parents=True, exist_ok=True)

                credentials_file = zotify_dir / "credentials.json"
                with open(credentials_file, "w") as f:
                    json.dump(zotify_creds, f)

            except Exception as e:
                LOGGER.error(f"❌ Failed to load Zotify credentials from file: {e}")

    except Exception as e:
        LOGGER.error(f"❌ Error setting up credentials from environment: {e}")


def should_debounce_query(query: str, previous_query: str = "") -> bool:
    """Check if query should be debounced to prevent spam"""
    if not query or len(query.strip()) < 2:
        return True

    # Don't debounce if query is significantly different
    if len(query) - len(previous_query) > 2:
        return False

    return False


def get_comprehensive_help_text() -> str:
    """Get comprehensive help text for inline search"""
    return """🎵 **Music Search Help**

**Basic Search:**
• Type any song, artist, or album name
• Example: `hello adele`

**Platform-Specific Search:**
• `spotify:query` - Search only Spotify
• `qobuz:query` - Search only Qobuz
• `tidal:query` - Search only Tidal
• `deezer:query` - Search only Deezer
• `soundcloud:query` - Search only SoundCloud

**Tips:**
• Be specific for better results
• Wait for results to load completely
• Use artist + song name for best matches

**Supported Platforms:**
🟦 Qobuz • ⚫ Tidal • 🟣 Deezer • 🟠 SoundCloud

**Note:** For Spotify results, use `spotify:query` prefix."""


def remove_duplicate_results(results):
    """Remove duplicate results based on URL and title similarity"""
    if not results:
        return results

    seen_urls = set()
    seen_titles = set()
    unique_results = []

    for result in results:
        # Check URL duplicates
        url = result.get("url", "")
        if url and url in seen_urls:
            continue

        # Check title duplicates (case-insensitive)
        title = result.get("title", result.get("name", "")).lower().strip()

        # Handle artist field (can be string or list)
        artist_raw = result.get("artist", "")
        if isinstance(artist_raw, list):
            artist = ", ".join(artist_raw[:2]).lower().strip() if artist_raw else ""
        else:
            artist = str(artist_raw).lower().strip() if artist_raw else ""

        title_key = f"{title}_{artist}"

        if title_key and title_key in seen_titles:
            continue

        # Add to unique results
        if url:
            seen_urls.add(url)
        if title_key:
            seen_titles.add(title_key)

        unique_results.append(result)

    return unique_results


async def send_no_platforms_result(inline_query, query):
    """Send result when no platforms are available"""
    try:
        from pyrogram.types import InlineQueryResultArticle, InputTextMessageContent

        await inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id="no_platforms",
                    title="❌ No Search Platforms Available",
                    description="All music search platforms are currently disabled",
                    input_message_content=InputTextMessageContent(
                        f"❌ **No Platforms Available**\n\n"
                        f"🔍 **Query:** `{query}`\n\n"
                        f"⚠️ **Issue:** All music search platforms are currently disabled or failed to initialize.\n\n"
                        f"🔧 **Solutions:**\n"
                        f"• Check platform credentials\n"
                        f"• Verify platform configurations\n"
                        f"• Contact administrator\n\n"
                        f"💡 **Tip:** Try again later as platforms may be temporarily unavailable."
                    ),
                )
            ],
            cache_time=60,
        )
    except Exception as e:
        LOGGER.error(f"Failed to send no platforms result: {e}")


class ModifiedInlineQuery:
    """Helper class to modify inline query text while preserving other attributes"""

    def __init__(self, original_query, new_query_text):
        # Copy all attributes from original
        for attr in dir(original_query):
            if not attr.startswith("_"):
                setattr(self, attr, getattr(original_query, attr))
        # Override the query text
        self.query = new_query_text


async def unified_inline_search_handler(client, inline_query: InlineQuery):
    """
    Unified inline search handler that routes queries to appropriate search modules.

    Routing logic:
    - Queries starting with 'spotify:' or 'zotify:' or 'z:' -> Zotify search
    - Queries starting with 'streamrip:' or 'sr:' or 'music:' -> Streamrip search
    - Queries starting with 'qobuz:', 'tidal:', 'deezer:', 'soundcloud:' -> Streamrip search
    - All other queries -> Unified search (both platforms)
    """
    query = inline_query.query.strip()

    # Routing inline search (log removed for cleaner output)

    # Route to Zotify search if prefixed (with lazy initialization)
    if query.startswith(("spotify:", "zotify:", "z:")):
        if Config.ZOTIFY_ENABLED:
            # Initialize Zotify on-demand
            zotify_ready = await ensure_zotify_initialized_on_demand()

            if not zotify_ready:
                # Zotify initialization failed, show error
                from pyrogram.types import (
                    InlineQueryResultArticle,
                    InputTextMessageContent,
                )

                await inline_query.answer(
                    results=[
                        InlineQueryResultArticle(
                            id="zotify_init_failed",
                            title="❌ Zotify Initialization Failed",
                            description="Failed to initialize Zotify for Spotify search",
                            input_message_content=InputTextMessageContent(
                                "❌ **Zotify Initialization Failed**\n\n"
                                "Failed to initialize Zotify for Spotify search. "
                                "This could be due to:\n"
                                "• Invalid Spotify credentials\n"
                                "• Network connectivity issues\n"
                                "• Spotify API limitations\n\n"
                                "Please try again later or contact the administrator."
                            ),
                        )
                    ],
                    cache_time=60,
                )
                return

            # Remove the prefix from query
            if query.startswith("spotify:"):
                modified_query = query[8:].strip()
            elif query.startswith("zotify:"):
                modified_query = query[7:].strip()
            elif query.startswith("z:"):
                modified_query = query[2:].strip()

            modified_inline_query = ModifiedInlineQuery(inline_query, modified_query)

            # Import and call zotify inline search
            from bot.helper.mirror_leech_utils.zotify_utils.search_handler import (
                inline_zotify_search,
            )

            await inline_zotify_search(client, modified_inline_query)
            return
        # Zotify disabled, show error
        from pyrogram.types import (
            InlineQueryResultArticle,
            InputTextMessageContent,
        )

        await inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id="zotify_disabled",
                    title="❌ Zotify Search Disabled",
                    description="Zotify search is currently disabled",
                    input_message_content=InputTextMessageContent(
                        "❌ **Zotify Search Disabled**\n\nZotify search is currently disabled. Please contact the administrator."
                    ),
                )
            ],
            cache_time=60,
        )
        return

    # Route to Streamrip search if prefixed
    if query.startswith(
        ("streamrip:", "sr:", "music:", "qobuz:", "tidal:", "deezer:", "soundcloud:")
    ):
        if Config.STREAMRIP_ENABLED:
            # Extract platform and remove prefix from query
            platform_prefix = None
            if query.startswith("streamrip:"):
                modified_query = query[10:].strip()
                platform_prefix = None  # Search all platforms
            elif query.startswith("music:"):
                modified_query = query[6:].strip()
                platform_prefix = None  # Search all platforms
            elif query.startswith("sr:"):
                modified_query = query[3:].strip()
                platform_prefix = None  # Search all platforms
            elif query.startswith("qobuz:"):
                modified_query = query[6:].strip()
                platform_prefix = "qobuz"  # Search only Qobuz
            elif query.startswith("tidal:"):
                modified_query = query[6:].strip()
                platform_prefix = "tidal"  # Search only Tidal
            elif query.startswith("deezer:"):
                modified_query = query[7:].strip()
                platform_prefix = "deezer"  # Search only Deezer
            elif query.startswith("soundcloud:"):
                modified_query = query[11:].strip()
                platform_prefix = "soundcloud"  # Search only SoundCloud

            # If platform-specific, add platform back to query for Streamrip handler
            if platform_prefix:
                # Format: "platform:query" so Streamrip handler can parse it
                modified_query = f"{platform_prefix}:{modified_query}"

            modified_inline_query = ModifiedInlineQuery(inline_query, modified_query)

            # Import and call streamrip inline search
            from bot.helper.mirror_leech_utils.streamrip_utils.search_handler import (
                inline_streamrip_search,
            )

            await inline_streamrip_search(client, modified_inline_query)
            return
        # Streamrip disabled, show error
        from pyrogram.types import (
            InlineQueryResultArticle,
            InputTextMessageContent,
        )

        await inline_query.answer(
            results=[
                InlineQueryResultArticle(
                    id="streamrip_disabled",
                    title="❌ Streamrip Search Disabled",
                    description="Streamrip search is currently disabled",
                    input_message_content=InputTextMessageContent(
                        "❌ **Streamrip Search Disabled**\n\nStreamrip search is currently disabled. Please contact the administrator."
                    ),
                )
            ],
            cache_time=60,
        )
        return

    # For all other queries, route to unified search (both platforms)
    if Config.ZOTIFY_ENABLED or Config.STREAMRIP_ENABLED:
        await unified_music_search(client, inline_query)
        return

    # If neither search is enabled, show help
    await show_search_help(inline_query)


async def unified_music_search(client, inline_query: InlineQuery):
    """
    Unified music search that combines results from both Zotify and Streamrip
    """
    query = inline_query.query.strip()

    if not query:
        await show_search_help(inline_query)
        return

    # Starting unified music search (log removed for cleaner output)

    # Note: Removed immediate "Searching..." response as it blocks real results
    # Telegram inline queries work better when we send results directly

    # Start background search
    _ = asyncio.create_task(perform_background_search(client, inline_query, query))  # noqa: RUF006
    # Note: Task runs in background, no need to await


async def perform_background_search(client, inline_query: InlineQuery, query: str):
    """
    Perform background search across both platforms and send results
    """
    try:
        all_results = []
        search_tasks = []

        # Ensure platforms are properly initialized with credentials
        await ensure_platforms_initialized()

        # Add Streamrip search task if enabled
        if Config.STREAMRIP_ENABLED:
            try:
                from bot.helper.mirror_leech_utils.streamrip_utils.search_handler import (
                    perform_inline_streamrip_search,
                )

                # Adding Streamrip search task (log removed for cleaner output)
                search_tasks.append(
                    asyncio.create_task(
                        perform_inline_streamrip_search(
                            query, None, None, inline_query.from_user.id
                        ),
                        name="streamrip_search",
                    )
                )
            except Exception as e:
                LOGGER.error(f"Failed to add Streamrip search task: {e}")

        # Note: Zotify is excluded from unified search
        # It only appears in platform-specific searches (spotify:, zotify:, z:)
        # This prevents Spotify results from cluttering the unified results

        if not search_tasks:
            LOGGER.warning(
                "No search tasks created - both platforms disabled or failed to initialize"
            )
            # Send "no platforms available" result
            await send_no_platforms_result(inline_query, query)
            return

        # Starting search tasks (log removed for cleaner output)

        # Wait for search tasks with progressive timeout and partial results
        results = []

        # First, wait for any task to complete (get quick results)
        try:
            done, pending = await asyncio.wait(
                search_tasks,
                timeout=3.0,  # Reduced to 3 seconds for much faster response
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Collect results from first completed tasks (filter out failures)
            for task in done:
                try:
                    result = await task
                    if isinstance(result, list) and len(result) > 0:
                        results.append(result)

                except Exception as e:
                    LOGGER.error(
                        f"Quick search task {task.get_name()} failed: {e} - excluding from results"
                    )
                    # Don't add failed results to the list

            # If we have pending tasks, wait a bit more for additional results
            if pending:
                # Waiting for remaining tasks (log removed for cleaner output)

                # Wait for remaining tasks with shorter timeout
                done2, still_pending = await asyncio.wait(
                    pending,
                    timeout=5.0,  # Reduced to 5 seconds for faster overall response
                    return_when=asyncio.ALL_COMPLETED,
                )

                # Collect results from remaining completed tasks (filter out failures)
                for task in done2:
                    try:
                        result = await task
                        if isinstance(result, list) and len(result) > 0:
                            results.append(result)

                    except Exception as e:
                        LOGGER.error(
                            f"Additional search task {task.get_name()} failed: {e} - excluding from results"
                        )
                        # Don't add failed results to the list

                # Cancel any still pending tasks
                if still_pending:
                    LOGGER.warning(
                        f"Cancelling {len(still_pending)} tasks that didn't complete in time"
                    )
                    for task in still_pending:
                        task.cancel()

                    # Wait briefly for cancellation
                    try:
                        await asyncio.wait(still_pending, timeout=1.0)
                    except Exception:
                        pass  # Ignore cancellation errors

        except Exception as e:
            LOGGER.error(f"Error during search task execution: {e}")
            # Continue with empty results - better to show something than nothing

        # Collect and process all results (only successful results are in the list)
        for _i, result in enumerate(results):
            if isinstance(result, list) and result:
                all_results.extend(result)

        # Remove duplicates and improve results
        if all_results:
            all_results = remove_duplicate_results(all_results)

        # Send final results
        await send_search_results(inline_query, all_results, query)

    except Exception as e:
        LOGGER.error(f"Background search failed: {e}")
        # Try to send error result (only if not query invalid)
        error_msg = str(e).lower()
        if "query id is invalid" not in error_msg and "QUERY_ID_INVALID" not in str(
            e
        ):
            try:
                from pyrogram.types import (
                    InlineQueryResultArticle,
                    InputTextMessageContent,
                )

                await inline_query.answer(
                    results=[
                        InlineQueryResultArticle(
                            id="search_error",
                            title="🔍 Search Error",
                            description="An error occurred during search",
                            input_message_content=InputTextMessageContent(
                                f"❌ **Search Error**\n\nAn error occurred while searching for: `{query}`\n\n"
                                f"🔧 **Error Details:** {str(e)[:100]}...\n\n"
                                f"💡 **Possible Solutions:**\n"
                                f"• Check your internet connection\n"
                                f"• Try a different search term\n"
                                f"• Wait a moment and try again\n"
                                f"• Contact support if the issue persists"
                            ),
                        )
                    ],
                    cache_time=5,
                )
            except Exception:
                pass  # Ignore errors when trying to send error message


async def send_search_results(
    inline_query: InlineQuery, all_results: list, query: str
):
    """
    Send the final search results to the user with query validation
    """
    try:
        # Validate query before sending results
        if not hasattr(inline_query, "id") or not inline_query.id:
            LOGGER.warning("Invalid inline query object - skipping result send")
            return

        # Check if query is still relevant (basic validation)
        if len(query.strip()) == 0:
            LOGGER.warning("Empty query - skipping result send")
            return

        # Additional validation: check if query object is still valid
        try:
            query_id = inline_query.id
            if (
                not query_id or len(query_id) < 10
            ):  # Telegram query IDs are typically longer
                LOGGER.warning(f"Suspicious query ID: {query_id} - may be invalid")
        except Exception as e:
            LOGGER.warning(f"Could not validate query ID: {e}")
            return

        from pyrogram.types import (
            InlineKeyboardButton,
            InlineKeyboardMarkup,
            InlineQueryResultArticle,
            InputTextMessageContent,
        )

        if not all_results:
            # No results found
            await inline_query.answer(
                results=[
                    InlineQueryResultArticle(
                        id="no_results",
                        title=f"🔍 No results for: {query}",
                        description="Try a different search term",
                        input_message_content=InputTextMessageContent(
                            f"🔍 **No Results Found**\n\nNo results found for: `{query}`\n\n"
                            f"💡 **Try:**\n"
                            f"• Different keywords\n"
                            f"• Artist name only\n"
                            f"• Song title only\n"
                            f"• Check spelling"
                        ),
                    )
                ],
                cache_time=60,
            )
            return

        # Sort results by relevance (exact matches first)
        def get_relevance_score(item):
            title = item.get("title", item.get("name", "")).lower()
            query_lower = query.lower()

            # Exact match gets highest priority
            exact_score = 1000 if query_lower in title else 0

            # Platform priority (Spotify first, then others)
            platform_name = item.get("platform", "").lower()
            if platform_name == "spotify":
                platform_score = 100
            elif platform_name in ["qobuz", "tidal"]:
                platform_score = 80
            elif platform_name in ["deezer", "soundcloud"]:
                platform_score = 60
            else:
                platform_score = 40

            return exact_score + platform_score

        all_results.sort(key=get_relevance_score, reverse=True)

        # Create inline results (limit to 50)
        inline_results = []

        for i, result in enumerate(
            all_results[:48]
        ):  # Reduced to 48 to avoid RESULTS_TOO_MUCH error
            try:
                # Format title and description
                title = result.get("title", result.get("name", "Unknown"))
                artist = result.get("artist", "")
                if isinstance(artist, list):
                    artist = ", ".join(artist[:2])

                platform_name = result.get("platform", "").title()
                media_type_name = result.get("type", "track").title()

                # Platform emoji
                platform_emoji = {
                    "spotify": "🎧",
                    "qobuz": "🟦",
                    "tidal": "⚫",
                    "deezer": "🟣",
                    "soundcloud": "🟠",
                }.get(result.get("platform", ""), "🎵")

                display_title = f"{platform_emoji} {title}"
                if artist:
                    display_title += f" - {artist}"

                description = f"🎵 {media_type_name} on {platform_name}"
                if result.get("duration"):
                    minutes = result["duration"] // 60
                    seconds = result["duration"] % 60
                    description += f" • {minutes}:{seconds:02d}"

                # Create callback data
                platform_name_lower = result.get("platform", "").lower()
                if platform_name_lower == "spotify":
                    # Use Zotify callback
                    from bot.helper.mirror_leech_utils.zotify_utils.search_handler import (
                        encrypt_zotify_data,
                    )

                    result_data = {
                        "url": result.get("url", ""),
                        "platform": "spotify",
                        "type": result.get("type", "track"),
                        "title": title,
                        "artist": artist,
                        "query": query,
                    }
                    encrypted_id = encrypt_zotify_data(str(result_data))
                    callback_data = f"zotify_dl_{encrypted_id}"
                else:
                    # Use Streamrip callback
                    from bot.helper.mirror_leech_utils.streamrip_utils.search_handler import (
                        encrypt_streamrip_data,
                    )

                    result_data = {
                        "url": result.get("url", ""),
                        "platform": result.get("platform", ""),
                        "type": result.get("type", "track"),
                        "title": title,
                        "artist": artist,
                        "query": query,
                    }
                    encrypted_id = encrypt_streamrip_data(str(result_data))
                    callback_data = f"streamrip_dl_{encrypted_id}"

                # Truncate callback data if too long
                if len(callback_data) > 64:
                    callback_data = callback_data[:64]

                # Create message content
                message_text = f"{platform_emoji} <b>{title}</b>\n"
                if artist:
                    message_text += f"👤 <b>Artist:</b> {artist}\n"
                if result.get("album"):
                    message_text += f"💿 <b>Album:</b> {result['album']}\n"
                message_text += f"🎧 <b>Platform:</b> {platform_name}\n"
                message_text += f"📁 <b>Type:</b> {media_type_name}\n\n"
                message_text += "⏳ <i>Preparing quality selection...</i>"

                # Create reply markup
                reply_markup = InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                text=f"{platform_emoji} Download {media_type_name}",
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

                # Add thumbnail if available
                thumbnail_url = result.get("cover_url") or result.get(
                    "thumbnail_url"
                )
                inline_result_params = {
                    "id": f"result_{i}_{hash(str(result))}",
                    "title": display_title,
                    "description": description,
                    "input_message_content": InputTextMessageContent(message_text),
                    "reply_markup": reply_markup,
                }

                if thumbnail_url and thumbnail_url.startswith("http"):
                    inline_result_params["thumb_url"] = thumbnail_url

                inline_results.append(
                    InlineQueryResultArticle(**inline_result_params)
                )

            except Exception as e:
                LOGGER.error(f"Error processing result {i}: {e}")
                continue

        # Add info result if we have more than 50 results
        if len(all_results) > 50:
            platforms_found = {
                item.get("platform", "unknown") for item in all_results
            }
            platforms_text = ", ".join(platforms_found)

            inline_results.append(
                InlineQueryResultArticle(
                    id="more_results_info",
                    title=f"📊 Found {len(all_results)} total results",
                    description=f"Showing top 50 • Platforms: {platforms_text}",
                    input_message_content=InputTextMessageContent(
                        f"📊 **Search Results Summary**\n\n"
                        f"🔍 **Query:** `{query}`\n"
                        f"📈 **Total Results:** {len(all_results)}\n"
                        f"📱 **Showing:** Top 50 results\n"
                        f"🎧 **Platforms:** {platforms_text}\n\n"
                        f"💡 **Tip:** Use more specific keywords to get better results!"
                    ),
                )
            )

        # Validate results before sending
        if not inline_results:
            LOGGER.error("No inline results to send - this should not happen")
            return

        # Validate and log first few results for debugging
        valid_results = []
        for i, result in enumerate(inline_results):
            if hasattr(result, "id") and hasattr(result, "title"):
                valid_results.append(result)

            else:
                LOGGER.warning(f"Invalid result at index {i}: missing id or title")

        if len(valid_results) != len(inline_results):
            LOGGER.warning(
                f"Filtered {len(inline_results) - len(valid_results)} invalid results"
            )
            inline_results = valid_results

        if not inline_results:
            LOGGER.error("No valid results after filtering")
            return

        # Send results with comprehensive error handling
        try:
            await inline_query.answer(
                results=inline_results,
                cache_time=60,  # Reduced cache time for better responsiveness
                is_personal=True,
            )
            LOGGER.info(
                f"✅ Successfully sent {len(inline_results)} results to Telegram"
            )
        except Exception as send_error:
            LOGGER.error(f"❌ Failed to send results to Telegram: {send_error}")
            # Try sending a smaller batch
            if len(inline_results) > 10:
                try:
                    LOGGER.info("Retrying with first 10 results only...")
                    await inline_query.answer(
                        results=inline_results[:10],
                        cache_time=60,
                        is_personal=True,
                    )
                    LOGGER.info("✅ Successfully sent reduced results")
                except Exception as retry_error:
                    LOGGER.error(f"❌ Retry also failed: {retry_error}")
                    raise send_error from retry_error
            else:
                raise send_error from None

    except Exception as e:
        error_msg = str(e).lower()
        if "query id is invalid" in error_msg or "QUERY_ID_INVALID" in str(e):
            LOGGER.warning(
                "Query ID invalid when sending results - user typed too fast"
            )
            return

        LOGGER.error(f"Failed to send search results: {e}")
        return


async def show_search_help(inline_query: InlineQuery):
    """
    Show help information for inline search
    """
    from pyrogram.types import InlineQueryResultArticle, InputTextMessageContent

    help_text = "🔍 <b>Music Search Help</b>\n\n"

    if Config.ZOTIFY_ENABLED:
        help_text += (
            "🎧 <b>Spotify Search:</b>\n"
            "<code>@bot_username spotify:query</code>\n"
            "<code>@bot_username zotify:query</code>\n"
            "<code>@bot_username z:query</code>\n\n"
        )

    if Config.STREAMRIP_ENABLED:
        help_text += (
            "🎵 <b>Multi-Platform Search:</b>\n"
            "<code>@bot_username streamrip:query</code>\n"
            "<code>@bot_username sr:query</code>\n"
            "<code>@bot_username music:query</code>\n"
            "<code>@bot_username qobuz:query</code>\n"
            "<code>@bot_username tidal:query</code>\n"
            "<code>@bot_username deezer:query</code>\n"
            "<code>@bot_username soundcloud:query</code>\n\n"
        )

    if Config.ZOTIFY_ENABLED and Config.STREAMRIP_ENABLED:
        help_text += (
            "🌟 <b>Unified Search (Default):</b>\n"
            "<code>@bot_username query</code>\n"
            "Searches both Spotify and other platforms\n\n"
        )

    if not Config.ZOTIFY_ENABLED and not Config.STREAMRIP_ENABLED:
        help_text += "❌ No music search modules are currently enabled."
    else:
        help_text += (
            "💡 <b>Tips:</b>\n"
            "• Default queries search all platforms\n"
            "• Use platform prefixes for specific searches\n"
            "• Try artist name or song title for best results"
        )

    await inline_query.answer(
        results=[
            InlineQueryResultArticle(
                id="help",
                title="🔍 Music Search Help",
                description="Learn how to use music search",
                input_message_content=InputTextMessageContent(help_text),
            )
        ],
        cache_time=300,
    )


def init_unified_inline_search(bot):
    """Initialize the unified inline search handler."""
    from pyrogram.handlers import InlineQueryHandler

    # Wrap the handler with error handling
    async def safe_unified_inline_search_handler(client, inline_query: InlineQuery):
        try:
            await unified_inline_search_handler(client, inline_query)
        except Exception as e:
            LOGGER.error(f"Error in unified inline search handler: {e}")
            # Try to answer with error for non-query-invalid exceptions
            error_msg = str(e).lower()
            if (
                "QUERY_ID_INVALID" in error_msg
                or "query id is invalid" in error_msg.lower()
            ):
                return
            # Try to answer with error for other exceptions
            try:
                from pyrogram.types import (
                    InlineQueryResultArticle,
                    InputTextMessageContent,
                )

                await inline_query.answer(
                    results=[
                        InlineQueryResultArticle(
                            id="unified_handler_error",
                            title="🔍 Search Error",
                            description="An unexpected error occurred",
                            input_message_content=InputTextMessageContent(
                                "❌ **Search Error**\n\nAn unexpected error occurred. Please try again."
                            ),
                        )
                    ],
                    cache_time=5,
                )
            except Exception:
                pass  # Ignore errors when trying to answer

    # Register the unified inline query handler with safety wrapper
    bot.add_handler(InlineQueryHandler(safe_unified_inline_search_handler))

    # Initialize individual platform handlers (non-inline)
    if Config.STREAMRIP_ENABLED:
        try:
            from bot.helper.mirror_leech_utils.streamrip_utils.search_handler import (
                init_streamrip_inline_search,
            )

            # Call with register_inline=False to skip inline handler registration
            init_streamrip_inline_search(bot, register_inline=False)
        except Exception as e:
            LOGGER.error(f"Failed to initialize Streamrip handlers: {e}")

    if Config.ZOTIFY_ENABLED:
        try:
            from bot.helper.mirror_leech_utils.zotify_utils.search_handler import (
                init_zotify_inline_search,
            )

            # Call with register_inline=False to skip inline handler registration
            init_zotify_inline_search(bot, register_inline=False)
        except Exception as e:
            LOGGER.error(f"Failed to initialize Zotify handlers: {e}")

    LOGGER.info("Unified inline search handler initialized successfully")
