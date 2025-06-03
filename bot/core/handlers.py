from pyrogram.filters import command
from pyrogram.handlers import MessageHandler

from bot.core.config_manager import Config
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.filters import CustomFilters

# Only ytdl and ytdl_leech are available from bot.modules due to __init__.py cleanup
# However, to ensure ONLY streamrip's /download works, we are not adding ytdl handlers for now.
# from bot.modules import ytdl, ytdl_leech

from .aeon_client import TgClient

def add_handlers():
    command_filters = {}

    # Add streamrip handlers if streamrip is enabled
    if Config.STREAMRIP_ENABLED:
        from bot.modules.streamrip import download  # Import the streamrip download function

        streamrip_handlers = {
            "download_streamrip": (  # Unique key for the dictionary
                download,
                BotCommands.DownloadCommand,  # This is ["download", "dl"]
                CustomFilters.authorized,
            )
        }
        command_filters.update(streamrip_handlers)

    # Iterate and add handlers
    for handler_key in command_filters:
        handler_func, command_names, custom_filter = command_filters[handler_key]

        # Ensure command_names is a list, even if it's a single command string initially
        if not isinstance(command_names, list):
            command_names_list = [command_names]
        else:
            command_names_list = command_names

        filters_to_apply = command(command_names_list, case_sensitive=True)

        if custom_filter:
            filters_to_apply &= custom_filter

        TgClient.bot.add_handler(MessageHandler(handler_func, filters=filters_to_apply))

    # All other specific command handlers, callback query handlers,
    # regex-based handlers (like handle_no_suffix_commands),
    # and module initializations (like init_media_search, init_ad_broadcaster)
    # have been removed to ensure only the explicitly defined commands
    # (i.e., /download and /dl for streamrip) are functional.

    # A very basic /start or /help could be added here if absolutely necessary,
    # but they would need to be minimal and not refer to removed features.
    # Example (if basic_commands.py with start_message existed in bot.modules):
    # from bot.modules.basic_commands import start_message
    # TgClient.bot.add_handler(MessageHandler(start_message, filters=command("start")))
