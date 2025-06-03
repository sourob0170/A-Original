from pyrogram import filters
from pyrogram.filters import command, regex
from pyrogram.handlers import (
    CallbackQueryHandler,
    EditedMessageHandler,
    MessageHandler,
)

from bot.core.config_manager import Config
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.filters import CustomFilters

# Imports from bot.modules - to be refined based on actual function names and modules
# These are based on the target commands to keep.
from bot.modules import (
    start, log,                                  # from services.py (assuming)
    bot_help, arg_usage,                         # from help.py
    run_shell,                                   # from shell.py
    execute, aioexecute,                         # from exec.py
    bot_stats,                                   # from stats.py
    task_status, status_pages,                   # from status.py
    handle_broadcast_command,                    # from broadcast.py
    send_bot_settings, edit_bot_settings,        # from bot_settings.py
    send_user_settings, edit_user_settings         # from users_settings.py
    # ytdl, ytdl_leech # ytdlp module is present, but commands are not in BotCommands current revision
)
# streamrip.download will be imported conditionally later

from .aeon_client import TgClient


def add_handlers():
    command_filters = {
        # Core Commands
        "start": (start, BotCommands.StartCommand, None),
        "help": (bot_help, BotCommands.HelpCommand, CustomFilters.authorized),
        "log": (log, BotCommands.LogCommand, CustomFilters.sudo),
        "shell": (run_shell, BotCommands.ShellCommand, CustomFilters.owner), # run_shell is also used in EditedMessageHandler
        "exec": (execute, BotCommands.ExecCommand, CustomFilters.sudo),
        "aexec": (aioexecute, BotCommands.AExecCommand, CustomFilters.sudo),
        "stats": (bot_stats, BotCommands.StatsCommand, CustomFilters.authorized),
        "status": (task_status, BotCommands.StatusCommand, CustomFilters.authorized), # Covers status, s, statusall, sall
        "broadcast": (handle_broadcast_command, BotCommands.BroadcastCommand, CustomFilters.owner),
        "botsettings_cmd": (send_bot_settings, BotCommands.BotSetCommand, CustomFilters.sudo), # Renamed key to avoid conflict
        # UserSetCommand is handled by a direct registration below, not in command_filters
    }

    # Add streamrip handlers if streamrip is enabled
    if Config.STREAMRIP_ENABLED:
        from bot.modules.streamrip import download as streamrip_download_func
        # Using DownloadCommand for user-facing command, but handler might internally use StreamripLeechCommand logic
        # The key "download_streamrip" must be unique in command_filters
        command_filters["download_streamrip"] = (
            streamrip_download_func,
            BotCommands.DownloadCommand, # User types /download or /dl
            CustomFilters.authorized,
        )
        # If the streamrip module's download function is still tied to BotCommands.StreamripLeechCommand name
        # for some internal reason (e.g. help messages not fully updated), we might need this:
        # command_filters["streamrip_leech_internal"] = (
        # streamrip_download_func,
        # BotCommands.StreamripLeechCommand, # Internal mapping
        # CustomFilters.authorized,
        # )


    # Registering command handlers from command_filters
    for key, (handler_func, command_name_or_list, custom_filter) in command_filters.items():
        # Ensure command_name_or_list is a list
        current_command_names = command_name_or_list
        if not isinstance(current_command_names, list):
            current_command_names = [current_command_names]

        filters_to_apply = command(current_command_names, case_sensitive=True)
        if custom_filter:
            filters_to_apply &= custom_filter

        TgClient.bot.add_handler(
            MessageHandler(handler_func, filters=filters_to_apply), group=0
        )

    # Handlers for commands that might have multiple aliases not covered by list in BotCommands
    # For example, status can be /s, /status, /statusall, /sall.
    # BotCommands.StatusCommand is already a list, so the above loop handles it.
    # This section might be redundant if BotCommands lists all aliases.
    # Example: if BotCommands.StatusCommand was just "status", then:
    # if "status" in command_filters: # check if base command is registered
    #    status_handler_func, _, status_custom_filter = command_filters["status"]
    #    for alias in ["s", "statusall", "sall"]: # Add other aliases if needed
    #        filters_to_apply = command(alias, case_sensitive=True)
    #        if status_custom_filter:
    #            filters_to_apply &= status_custom_filter
    #        TgClient.bot.add_handler(MessageHandler(status_handler_func, filters=filters_to_apply), group=0)


    # Callback Query Handlers to keep
    kept_auth_regex_filters = {
        "^botset": edit_bot_settings,  # For BotSetCommand
        "^help": arg_usage,          # For HelpCommand
        "^status": status_pages,     # For StatusCommand
    }

    kept_public_regex_filters = {
         "^userset": edit_user_settings, # For UserSetCommand
    }

    for regex_filter, handler_func in kept_public_regex_filters.items():
        TgClient.bot.add_handler(
            CallbackQueryHandler(handler_func, filters=regex(regex_filter)), group=-1
        )

    for regex_filter, handler_func in kept_auth_regex_filters.items():
        TgClient.bot.add_handler(
            CallbackQueryHandler(
                handler_func, filters=regex(regex_filter) & CustomFilters.authorized
            ), group=0
        )

    # Edited Message Handler for Shell Command
    TgClient.bot.add_handler(
        EditedMessageHandler(
            run_shell,
            filters=command(BotCommands.ShellCommand, case_sensitive=True) & CustomFilters.owner,
        ), group=0
    )

    # Direct registration for UserSetCommand (as it was in original)
    # This ensures it works in PM and groups without pm_or_authorized filter by default.
    TgClient.bot.add_handler(
        MessageHandler(
            send_user_settings,
            filters=command(BotCommands.UserSetCommand, case_sensitive=True),
        ), group=-1
    )

    # Simplified handle_no_suffix_commands (if kept)
    # This regex should only contain commands that are actually active.
    # Kept commands: start, help, log, shell, exec, aexec, stats, status, broadcast, botsettings, settings, usettings, us, download, dl
    # Note: BotCommands.UserSetCommand = ["settings", "usettings", "us"]
    # Note: BotCommands.DownloadCommand = ["download", "dl"]
    # Note: BotCommands.StatusCommand includes "s", "statusall", "sall"
    # The main command handlers should catch these. This regex might be for catching them if CMD_SUFFIX is used or if they are typed without suffix.
    # For now, let's make it minimal or remove if not strictly needed.
    # If CMD_SUFFIX is empty, this handler might not be very useful unless commands are defined without suffix in BotCommands too.

    # Minimal list for no_suffix handler (commands that are single strings in BotCommands and might be used with suffix)
    # Or commands that need broader matching.
    # Given the current BotCommands, only commands like StartCommand, HelpCommand etc. are single strings.
    # DownloadCommand and UserSetCommand are lists.

    # For now, removing handle_no_suffix_commands as its complexity might introduce issues.
    # The primary command registration should handle the defined commands.
    # If commands with suffix are needed, they should be explicitly defined in BotCommands or this regex carefully crafted.

    # TgClient.bot.add_handler(
    #     MessageHandler(
    #         handle_no_suffix_commands, # This function would need to be restored/verified too
    #         filters=regex(
    #             r"^/(start|help|log|shell|exec|aexec|stats|status|s|statusall|sall|broadcast|botsettings|settings|usettings|us|download|dl)([a-zA-Z0-9_]*)($| )"
    #         )
    #         & CustomFilters.pm_or_authorized, # Or a more appropriate filter
    #     ),
    #     group=0, # Ensure this group is appropriate
    # )

    # Removed other handlers like handle_qb_commands, handle_group_gensession, media tools, font styles, cancel, broadcast media, session input, etc.
    # Removed init_media_search, init_unified_inline_search, init_ad_broadcaster.
