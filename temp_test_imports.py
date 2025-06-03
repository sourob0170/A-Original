import sys
print(f"Python version: {sys.version}")
print(f"Python path: {sys.path}")

print("Attempting to import bot...")
try:
    import bot
    print("Successfully imported bot")
    import bot.__main__
    print("Successfully imported bot.__main__")
except Exception as e:
    print(f"Error importing bot or bot.__main__: {e}")
    sys.exit(1)

print("\nAttempting to import specific modules from bot.modules...")
try:
    from bot.modules import services
    print("Successfully imported bot.modules.services")
    from bot.modules import help as help_module
    print("Successfully imported bot.modules.help as help_module")
    from bot.modules import shell
    print("Successfully imported bot.modules.shell")
    from bot.modules import exec as exec_module
    print("Successfully imported bot.modules.exec as exec_module")
    from bot.modules import stats
    print("Successfully imported bot.modules.stats")
    from bot.modules import status
    print("Successfully imported bot.modules.status")
    from bot.modules import broadcast
    print("Successfully imported bot.modules.broadcast")
    from bot.modules import bot_settings
    print("Successfully imported bot.modules.bot_settings")
    from bot.modules import users_settings
    print("Successfully imported bot.modules.users_settings")
    from bot.modules import streamrip
    print("Successfully imported bot.modules.streamrip")
    from bot.modules import ytdlp
    print("Successfully imported bot.modules.ytdlp")
except Exception as e:
    print(f"Error importing from bot.modules: {e}")
    # sys.exit(1) # Don't exit yet, try core modules

print("\nAttempting to import specific functions from bot.modules (as in handlers.py)...")
try:
    from bot.modules import (
        start, log,
        bot_help, arg_usage,
        run_shell,
        execute, aioexecute,
        bot_stats,
        task_status, status_pages,
        handle_broadcast_command,
        send_bot_settings, edit_bot_settings,
        send_user_settings, edit_user_settings
    )
    print("Successfully imported specific functions from bot.modules")
except Exception as e:
    print(f"Error importing specific functions from bot.modules: {e}")
    # sys.exit(1)


print("\nAttempting to import core modules...")
try:
    from bot.core import handlers
    print("Successfully imported bot.core.handlers")
    from bot.core import aeon_client
    print("Successfully imported bot.core.aeon_client")
    from bot.core import config_manager
    print("Successfully imported bot.core.config_manager")
except Exception as e:
    print(f"Error importing from bot.core: {e}")
    sys.exit(1)

print("\nAll attempted imports finished.")
