#!/usr/bin/env python3
"""
Unified inline search router that handles both media search and streamrip search
"""

from pyrogram.types import InlineQuery

from bot import LOGGER
from bot.core.config_manager import Config


async def unified_inline_search_handler(client, inline_query: InlineQuery):
    """
    Unified inline search handler that routes queries to appropriate search modules.

    Routing logic:
    - Queries starting with 'music:' or 'streamrip:' -> Streamrip search
    - Queries starting with 'media:' -> Media search
    - All other queries -> Media search (default behavior)
    """
    query = inline_query.query.strip()

    # Route to media search if:
    # 1. Query starts with 'media:' prefix
    # 2. Media search is enabled
    if Config.MEDIA_SEARCH_ENABLED and query.startswith("media:"):
        # Remove 'media:' prefix
        modified_query = query[6:].strip()

        # Create modified inline query
        class ModifiedInlineQuery:
            def __init__(self, original_query, new_query_text):
                for attr in dir(original_query):
                    if not attr.startswith("_"):
                        setattr(self, attr, getattr(original_query, attr))
                self.query = new_query_text

        modified_inline_query = ModifiedInlineQuery(inline_query, modified_query)

        # Import and call media inline search
        from bot.modules.media_search import inline_media_search

        await inline_media_search(client, modified_inline_query)
        return

    # Route to streamrip search if:
    # 1. Query starts with 'music:' or 'streamrip:' or 'sr:' (remove prefix)
    # 2. All other queries (default behavior - streamrip is now default)
    # 3. Streamrip is enabled
    if Config.STREAMRIP_ENABLED:
        # Remove the prefix from query if present
        modified_query = query
        if query.startswith("music:"):
            modified_query = query[6:].strip()
        elif query.startswith("streamrip:"):
            modified_query = query[10:].strip()
        elif query.startswith("sr:"):
            modified_query = query[3:].strip()

        # Create a modified inline query object
        class ModifiedInlineQuery:
            def __init__(self, original_query, new_query_text):
                # Copy all attributes from original
                for attr in dir(original_query):
                    if not attr.startswith("_"):
                        setattr(self, attr, getattr(original_query, attr))
                # Override the query text
                self.query = new_query_text

        modified_inline_query = ModifiedInlineQuery(inline_query, modified_query)

        # Import and call streamrip inline search
        from bot.helper.streamrip_utils.search_handler import inline_streamrip_search

        await inline_streamrip_search(client, modified_inline_query)
        return

    # Fallback to media search if streamrip is disabled
    if Config.MEDIA_SEARCH_ENABLED:
        # Import and call media inline search
        from bot.modules.media_search import inline_media_search

        await inline_media_search(client, inline_query)
        return

    # If neither search is enabled or available, show help
    LOGGER.warning("No search modules available")

    from pyrogram.types import InlineQueryResultArticle, InputTextMessageContent

    help_text = "🔍 <b>Inline Search Help</b>\n\n"

    if Config.STREAMRIP_ENABLED:
        help_text += (
            "🎵 <b>Music Search (Default):</b>\n"
            "<code>@bot_username query</code> (default)\n"
            "<code>@bot_username music:query</code>\n"
            "<code>@bot_username streamrip:query</code>\n"
            "<code>@bot_username sr:query</code>\n\n"
        )

    if Config.MEDIA_SEARCH_ENABLED:
        help_text += (
            "📁 <b>Media Search:</b>\n<code>@bot_username media:query</code>\n\n"
        )

    if not Config.STREAMRIP_ENABLED and not Config.MEDIA_SEARCH_ENABLED:
        help_text += "❌ No search modules are currently enabled."
    else:
        help_text += (
            "💡 <b>Tips:</b>\n"
            "• Default queries now go to music search\n"
            "• Use 'media:' prefix for file search\n"
            "• Music queries support platform filters (qobuz:, tidal:, etc.)"
        )

    await inline_query.answer(
        results=[
            InlineQueryResultArticle(
                id="help",
                title="🔍 Inline Search Help",
                description="Learn how to use inline search",
                input_message_content=InputTextMessageContent(help_text),
            )
        ],
        cache_time=300,
    )


def init_unified_inline_search(bot):
    """Initialize the unified inline search handler."""
    from pyrogram.handlers import InlineQueryHandler

    # Register the unified inline query handler
    bot.add_handler(InlineQueryHandler(unified_inline_search_handler))

    # Initialize streamrip handlers (non-inline)
    if Config.STREAMRIP_ENABLED:
        from bot.helper.streamrip_utils.search_handler import (
            init_streamrip_inline_search,
        )

        # Call with register_inline=False to skip inline handler registration
        init_streamrip_inline_search(bot, register_inline=False)
