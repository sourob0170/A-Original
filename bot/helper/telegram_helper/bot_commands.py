# ruff: noqa: RUF012
from bot.core.config_manager import Config

i = Config.CMD_SUFFIX  # This will not be used in the simplified command structure


class BotCommands:
    DownloadCommand = ["download", "dl"]
