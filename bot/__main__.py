# ruff: noqa: E402
import gc
from asyncio import create_task, gather # Keep gather

from pyrogram.types import BotCommand

from . import LOGGER, bot_loop
from .core.config_manager import Config, SystemEnv

LOGGER.info("Loading config...")
Config.load()
SystemEnv.load()

# load_settings needs to be called before TgClient is imported for proxy settings
from .core.startup import load_settings
bot_loop.run_until_complete(load_settings())

from .core.aeon_client import TgClient
from .helper.telegram_helper.bot_commands import BotCommands

# Define kept commands and their descriptions
# StreamripLeechCommand is used internally by handlers for the download function from streamrip.py
# DownloadCommand is the user-facing command.
KEPT_COMMANDS = {
    "StartCommand": "- Start the bot",
    "HelpCommand": "- Get help",
    "LogCommand": "- [ADMIN] View bot log",
    "ShellCommand": "- [ADMIN] Execute shell commands",
    "ExecCommand": "- [ADMIN] Execute python code",
    "AExecCommand": "- [ADMIN] Execute async python code",
    "StatsCommand": "- [ADMIN] Check Bot & System stats",
    "StatusCommand": "- [ADMIN] Get task status", # Aliases s, statusall, sall handled by BotCommands.StatusCommand
    "BroadcastCommand": "- [ADMIN] Broadcast a message",
    "BotSetCommand": "- [ADMIN] Open Bot settings",
    "UserSetCommand": "- User settings", # Aliases usettings, us handled by BotCommands.UserSetCommand
    "DownloadCommand": "- Download music using Streamrip", # /download, /dl
    # "StreamripLeechCommand": "- Download music (Streamrip internal alias)", # Not user-facing
}

COMMAND_OBJECTS = []
for cmd_attr, description in KEPT_COMMANDS.items():
    if hasattr(BotCommands, cmd_attr):
        cmd_val = getattr(BotCommands, cmd_attr)
        # Handle cases where BotCommand attribute is a list (for aliases)
        actual_cmd = cmd_val[0] if isinstance(cmd_val, list) else cmd_val
        COMMAND_OBJECTS.append(BotCommand(actual_cmd, description))
    else:
        LOGGER.warning(f"Command attribute {cmd_attr} not found in BotCommands. Skipping.")


# Set Bot Commands
async def set_commands():
    if Config.SET_COMMANDS:
        await TgClient.bot.set_bot_commands(COMMAND_OBJECTS)


# Main Function
async def main():
    LOGGER.info("Configuring garbage collection...")
    gc.enable()
    gc.set_threshold(700, 10, 10)

    from .core.startup import (
        load_configurations, # Loads some basic configs
        save_settings,       # Saves bot settings (if changed via UI)
        start_bot,           # Starts scheduler, loads plugins
        update_variables,    # Updates some dynamic variables
    )

    await TgClient.start_bot() # Only start the main bot client
    # User client and helper bots are disabled in aeon_client.py

    await gather(load_configurations(), update_variables())

    # Removed initializers for TorrentManager, Aria2, qBittorrent, NZB, JDownloader

    await start_bot() # Starts scheduler, calls on_startup tasks like ensure_streamrip_config

    from .helper.ext_utils.files_utils import clean_all
    from .helper.ext_utils.gc_utils import (
        log_memory_usage,
        smart_garbage_collection,
    )

    from .modules import ( # Assuming these are general purpose enough
        get_packages_version,
        restart_notification,
    )

    await gather(
        set_commands(),
        # jdownloader.boot(), # Removed
    )

    from .helper.ext_utils.task_monitor import start_monitoring # Generic task monitor

    await gather(
        save_settings(), # Saves bot_settings.json and user_settings.json
        clean_all(),     # Cleans up temp directories
        # initiate_search_tools(), # Removed
        get_packages_version(),
        restart_notification(),
    )

    create_task(start_monitoring())

    from .helper.ext_utils.auto_restart import init_auto_restart
    init_auto_restart()

    from .helper.ext_utils.bot_utils import _load_user_data # For user-specific limits/settings
    LOGGER.info("Loading user data...")
    await _load_user_data()

    LOGGER.info("Performing initial garbage collection...")
    smart_garbage_collection(aggressive=True)
    log_memory_usage()


bot_loop.run_until_complete(main())

from .core.handlers import add_handlers
# from .helper.ext_utils.bot_utils import create_help_buttons # create_help_buttons might be too tied to old help
# from .helper.listeners.aria2_listener import add_aria2_callbacks # Aria2 removed

# add_aria2_callbacks() # Removed
# create_help_buttons() # Potentially remove or ensure it's compatible with new help
add_handlers()


import atexit
from .helper.ext_utils.db_handler import database # Assuming db_handler is used for settings

async def cleanup():
    LOGGER.info("Performing cleanup before shutdown...")
    # Removed streamrip session cleanup from search_handler as it was deleted

    if database.is_connected: # Check if db was connected
        await database.disconnect()
        LOGGER.info("Database disconnected.")
    else:
        LOGGER.info("Database was not connected, no disconnection needed.")

    LOGGER.info("Cleanup completed")


def run_cleanup():
    bot_loop.run_until_complete(cleanup())

atexit.register(run_cleanup)

LOGGER.info("Bot Started!")
try:
    bot_loop.run_forever()
except (KeyboardInterrupt, SystemExit):
    LOGGER.info("Bot stopping...")
    run_cleanup() # Ensure cleanup is called
    LOGGER.info("Bot stopped gracefully")
