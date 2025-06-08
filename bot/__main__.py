# ruff: noqa: E402
import asyncio
import gc
from asyncio import create_task, gather

from pyrogram.types import BotCommand

from . import LOGGER, bot_loop
from .core.config_manager import Config, SystemEnv

LOGGER.info("Loading config...")
Config.load()
SystemEnv.load()

from .core.startup import load_settings

bot_loop.run_until_complete(load_settings())

from .core.aeon_client import TgClient
from .helper.telegram_helper.bot_commands import BotCommands

COMMANDS = {
    "MirrorCommand": "- Start mirroring",
    "LeechCommand": "- Start leeching",
    "JdMirrorCommand": "- Mirror using Jdownloader",
    "JdLeechCommand": "- Leech using jdownloader",
    "NzbMirrorCommand": "- Mirror nzb files",
    "NzbLeechCommand": "- Leech nzb files",
    "YtdlCommand": "- Mirror yt-dlp supported link",
    "YtdlLeechCommand": "- Leech through yt-dlp supported link",
    "StreamripMirrorCommand": "- Mirror music from streaming platforms",
    "StreamripLeechCommand": "- Leech music from streaming platforms",
    "StreamripSearchCommand": "- Search music across platforms",
    "ZotifyMirrorCommand": "- Mirror music from Spotify",
    "ZotifyLeechCommand": "- Leech music from Spotify",
    "ZotifySearchCommand": "- Search music on Spotify",
    "CloneCommand": "- Copy file/folder to Drive",
    "MegaCloneCommand": "- Clone MEGA files/folders to MEGA account",
    "MegaSearchCommand": "- Search MEGA drive for files/folders",
    "MediaInfoCommand": "- Get mediainfo",
    "SoxCommand": "- Get audio spectrum",
    "ForceStartCommand": "- Start task from queue",
    "CountCommand": "- Count file/folder on Google Drive",
    "ListCommand": "- Search in Drive",
    "SearchCommand": "- Search in Torrent",
    "UserSetCommand": "- User settings",
    "MediaToolsCommand": "- Media tools settings for watermark and other media features",
    "MediaToolsHelpCommand": "- View detailed help for merge and watermark features",
    "StatusCommand": "- Get mirror status message (/s, /statusall, /sall)",
    "StatsCommand": "- Check Bot & System stats",
    "CancelAllCommand": "- Cancel all tasks added by you to the bot",
    "HelpCommand": "- Get detailed help",
    "FontStylesCommand": "- View available font styles for leech",
    "IMDBCommand": "- Search for movies or TV series info",
    "MediaSearchCommand": "- Search for media files (/mds) or reply to a message",
    "SpeedTest": "- Get speedtest result",
    "GenSessionCommand": "- Generate Pyrogram session string",
    "TruecallerCommand": "- Lookup phone numbers using Truecaller",
    "VirusTotalCommand": "- Scan files or URLs for viruses using VirusTotal",
    "BotSetCommand": "- [ADMIN] Open Bot settings",
    "LogCommand": "- [ADMIN] View log",
    "RestartCommand": "- [ADMIN] Restart the bot",
}


# Setup Commands
COMMAND_OBJECTS = [
    BotCommand(
        getattr(BotCommands, cmd)[0]
        if isinstance(getattr(BotCommands, cmd), list)
        else getattr(BotCommands, cmd),
        description,
    )
    for cmd, description in COMMANDS.items()
]


# Set Bot Commands
async def set_commands():
    if Config.SET_COMMANDS:
        await TgClient.bot.set_bot_commands(COMMAND_OBJECTS)


# Main Function
async def main():
    # Initialize garbage collection with startup-optimized thresholds
    LOGGER.info("Configuring garbage collection for startup optimization...")
    gc.enable()
    # Use higher thresholds during startup to reduce GC overhead
    # This reduces CPU usage during the critical startup phase
    gc.set_threshold(
        1000, 15, 15
    )  # Higher thresholds to reduce GC frequency during startup

    from .core.startup import (
        load_configurations,
        save_settings,
        start_bot,
        update_aria2_options,
        update_nzb_options,
        update_qb_options,
        update_variables,
    )

    await gather(
        TgClient.start_bot(), TgClient.start_user(), TgClient.start_helper_bots()
    )
    await gather(load_configurations(), update_variables())
    from .core.torrent_manager import TorrentManager

    await TorrentManager.initiate()
    await gather(
        update_qb_options(),
        update_aria2_options(),
        update_nzb_options(),
    )

    # Start the scheduled deletion checker and other tasks
    await start_bot()
    from .core.jdownloader_booter import jdownloader
    from .helper.ext_utils.files_utils import clean_all
    from .helper.ext_utils.gc_utils import (
        log_memory_usage,
        smart_garbage_collection,
    )
    from .helper.ext_utils.telegraph_helper import telegraph
    from .helper.mirror_leech_utils.rclone_utils.serve import rclone_serve_booter
    from .modules import (
        get_packages_version,
        initiate_search_tools,
        restart_notification,
    )

    await gather(
        set_commands(),
        jdownloader.boot(),
    )
    from .helper.ext_utils.task_manager import start_queue_processor
    from .helper.ext_utils.task_monitor import start_monitoring

    await gather(
        save_settings(),
        clean_all(),
        initiate_search_tools(),
        get_packages_version(),
        restart_notification(),
        telegraph.create_account(),
        rclone_serve_booter(),
    )

    # Start background services immediately without delays
    LOGGER.info("Starting background services...")

    # Start task monitoring system and queue processor only if task monitoring is enabled
    if Config.TASK_MONITOR_ENABLED:
        LOGGER.info("Starting task monitoring system...")
        create_task(start_monitoring())  # noqa: RUF006

        # Start queue processor to ensure tasks run even under high system resources
        LOGGER.info("Starting queue processor...")
        create_task(start_queue_processor())  # noqa: RUF006
    else:
        LOGGER.info(
            "Task monitoring is disabled - skipping task monitor and queue processor"
        )

    # Initialize auto-restart scheduler
    from .helper.ext_utils.auto_restart import init_auto_restart

    init_auto_restart()

    # Load user data for limits tracking
    from .helper.ext_utils.bot_utils import _load_user_data

    LOGGER.info("Loading user data for limits tracking...")
    await _load_user_data()

    # Initial garbage collection and memory usage logging (less aggressive during startup)
    LOGGER.info("Performing initial garbage collection...")
    smart_garbage_collection(
        aggressive=False  # Use less aggressive mode during startup to reduce resource usage
    )
    log_memory_usage()

    LOGGER.info("All background services initialized successfully")

    # Adjust garbage collection thresholds for normal operation after startup
    LOGGER.info("Adjusting garbage collection thresholds for normal operation...")
    gc.set_threshold(700, 10, 10)  # More aggressive thresholds for normal operation


bot_loop.run_until_complete(main())

from .core.handlers import add_handlers
from .helper.ext_utils.bot_utils import create_help_buttons
from .helper.listeners.aria2_listener import add_aria2_callbacks

add_aria2_callbacks()
create_help_buttons()
add_handlers()


# Setup cleanup handler
import atexit

from .helper.ext_utils.db_handler import database


async def cleanup():
    """Clean up resources before shutdown"""
    LOGGER.info("Performing cleanup before shutdown...")

    # Cleanup streamrip sessions to prevent unclosed session warnings
    try:
        from .helper.streamrip_utils.search_handler import (
            cleanup_all_streamrip_sessions,
        )

        await cleanup_all_streamrip_sessions()
    except Exception as e:
        LOGGER.error(f"Error during streamrip cleanup: {e}")

    # Stop database heartbeat task
    await database.stop_heartbeat()

    # Disconnect from database
    await database.disconnect()

    LOGGER.info("Cleanup completed")


# Register cleanup function to run at exit
def run_cleanup():
    bot_loop.run_until_complete(cleanup())


atexit.register(run_cleanup)


# Set up exception handler for unhandled task exceptions
def handle_loop_exception(loop, context):
    """Handle unhandled exceptions in the event loop"""
    exception = context.get("exception")
    if exception:
        # Filter out common handler removal errors that are harmless
        if isinstance(
            exception, ValueError
        ) and "list.remove(x): x not in list" in str(exception):
            LOGGER.debug(f"Handler removal error (harmless): {exception}")
        # Filter out aria2 RPC exceptions for missing GIDs (these are expected during rapid downloads)
        elif "Aria2rpcException" in str(type(exception)) and "is not found" in str(
            exception
        ):
            LOGGER.debug(
                f"Aria2 GID not found (expected during rapid downloads): {exception}"
            )
        # Filter out transport closing errors that are harmless during shutdown
        elif "closing transport" in str(exception).lower():
            LOGGER.debug(
                f"Transport closing error (harmless during shutdown): {exception}"
            )
        else:
            LOGGER.error(f"Unhandled loop exception: {exception}")
            LOGGER.error(f"Exception context: {context}")
    else:
        LOGGER.warning(f"Loop exception without exception object: {context}")


# Set the exception handler for the event loop
bot_loop.set_exception_handler(handle_loop_exception)
asyncio.set_event_loop(bot_loop)

# Run Bot
LOGGER.info("Bot Started!")
try:
    bot_loop.run_forever()
except (KeyboardInterrupt, SystemExit):
    LOGGER.info("Bot stopping...")
    run_cleanup()
    LOGGER.info("Bot stopped gracefully")
