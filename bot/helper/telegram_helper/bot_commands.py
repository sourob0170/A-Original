# ruff: noqa: RUF012
from bot.core.config_manager import Config

i = Config.CMD_SUFFIX


class BotCommands:
    StartCommand = "start"
    HelpCommand = f"help{i}"
    LogCommand = f"log{i}"
    ShellCommand = f"shell{i}"
    ExecCommand = f"exec{i}"
    AExecCommand = f"aexec{i}"
    StatsCommand = f"stats{i}"
    StatusCommand = [f"status{i}", f"s{i}", "statusall", "sall"]
    BroadcastCommand = [f"broadcast{i}", "broadcastall"]
    BotSetCommand = f"botsettings{i}"
    UserSetCommand = [f"settings{i}", f"usettings{i}", f"us{i}"]

    # Kept for mapping to the streamrip download function in handlers,
    # as the streamrip.py module's download function is the old leech one.
    # The actual user-facing commands are defined in DownloadCommand.
    StreamripLeechCommand = [f"streamripleech{i}", f"srleech{i}", f"srl{i}"]

    # New primary download command for streamrip
    DownloadCommand = ["download", "dl"]

    # Other commands like MirrorCommand, LeechCommand (generic), CloneCommand,
    # YtdlCommand, JdMirrorCommand, NzbMirrorCommand, etc., have been removed
    # to streamline the bot to core functions and streamrip.
    # If any of these functionalities are desired in the future, their respective
    # modules, helper utilities, and command definitions would need to be restored or re-added.
