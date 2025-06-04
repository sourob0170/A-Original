# ruff: noqa: E402
# Fix IDE issues by adding type annotations and import comments
from uvloop import install  # type: ignore

install()

import os
import subprocess
from asyncio import Lock, new_event_loop, set_event_loop
from datetime import datetime
from logging import (
    ERROR,
    INFO,
    WARNING,
    FileHandler,
    Filter,
    Formatter,
    LogRecord,
    StreamHandler,
    basicConfig,
    getLogger,
)
from time import time

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore
from pytz import timezone

from sabnzbdapi import SabnzbdClient


class SuppressUnclosedSessionFilter(Filter):
    """Filter to suppress unclosed client session and connector warnings"""

    def filter(self, record: LogRecord) -> bool:
        # Suppress unclosed client session errors
        if "Unclosed client session" in record.getMessage():
            return False
        # Suppress unclosed connector errors
        if "Unclosed connector" in record.getMessage():
            return False
        # Suppress client session object warnings
        if "client_session:" in record.getMessage():
            return False
        # Suppress connector object warnings
        if "connector:" in record.getMessage():
            return False
        # Suppress Pyrogram unknown constructor errors to prevent log flooding
        return "The server sent an unknown constructor" not in record.getMessage()


class SuppressZotifyNoiseFilter(Filter):
    """Filter to suppress specific Zotify/librespot noise logs"""

    def filter(self, record: LogRecord) -> bool:
        message = record.getMessage()

        # Suppress specific librespot core logs
        if "Received license_version:" in message:
            return False
        if "Received country_code:" in message:
            return False
        if "Skipping 1f" in message:
            return False
        if "Skipping 69" in message:
            return False
        if "Session.Receiver started" in message:
            return False
        return "Skipping unknown command cmd:" not in message


getLogger("requests").setLevel(WARNING)
getLogger("urllib3").setLevel(WARNING)
getLogger("pyrogram").setLevel(ERROR)
getLogger("httpx").setLevel(WARNING)
getLogger("pymongo").setLevel(WARNING)
getLogger("aiohttp").setLevel(WARNING)
getLogger("bot.modules.media_search").setLevel(ERROR)

# Suppress Zotify/librespot core logs for cleaner output
getLogger("librespot.core").setLevel(ERROR)  # Only show errors, suppress info logs
getLogger("librespot").setLevel(WARNING)  # Suppress all librespot info logs

# Apply the unclosed session filter to aiohttp loggers specifically
aiohttp_client_logger = getLogger("aiohttp.client")
aiohttp_client_logger.addFilter(SuppressUnclosedSessionFilter())

aiohttp_connector_logger = getLogger("aiohttp.connector")
aiohttp_connector_logger.addFilter(SuppressUnclosedSessionFilter())

# Also apply to the main aiohttp logger
aiohttp_main_logger = getLogger("aiohttp")
aiohttp_main_logger.addFilter(SuppressUnclosedSessionFilter())

bot_start_time = time()

bot_loop = new_event_loop()
set_event_loop(bot_loop)


class CustomFormatter(Formatter):
    def formatTime(
        self,
        record: LogRecord,
        datefmt: str | None,
    ) -> str:
        dt: datetime = datetime.fromtimestamp(
            record.created,
            tz=timezone("Asia/Dhaka"),
        )
        return dt.strftime(datefmt)

    def format(self, record: LogRecord) -> str:
        return super().format(record).replace(record.levelname, record.levelname[:1])


formatter = CustomFormatter(
    "[%(asctime)s] %(levelname)s - %(message)s [%(module)s:%(lineno)d]",
    datefmt="%d-%b %I:%M:%S %p",
)

file_handler = FileHandler("log.txt")
file_handler.setFormatter(formatter)
file_handler.addFilter(SuppressUnclosedSessionFilter())
file_handler.addFilter(SuppressZotifyNoiseFilter())  # Add Zotify noise filter

stream_handler = StreamHandler()
stream_handler.setFormatter(formatter)
stream_handler.addFilter(SuppressUnclosedSessionFilter())
stream_handler.addFilter(SuppressZotifyNoiseFilter())  # Add Zotify noise filter

basicConfig(handlers=[file_handler, stream_handler], level=INFO)

LOGGER = getLogger(__name__)

cpu_no = os.cpu_count()

DOWNLOAD_DIR = "/usr/src/app/downloads/"
intervals = {
    "status": {},
    "qb": "",
    "jd": "",
    "nzb": "",
    "stopAll": False,
}
qb_torrents = {}
user_data = {}
aria2_options = {}
qbit_options = {}
nzb_options = {}
queued_dl = {}
queued_up = {}
status_dict = {}
task_dict = {}
jd_downloads = {}
nzb_jobs = {}
rss_dict = {}
auth_chats = {}
excluded_extensions = ["aria2", "!qB"]
drives_names = []
drives_ids = []
index_urls = []
sudo_users = []
non_queued_dl = set()
non_queued_up = set()
multi_tags = set()
task_dict_lock = Lock()
queue_dict_lock = Lock()
qb_listener_lock = Lock()
cpu_eater_lock = Lock()
same_directory_lock = Lock()
nzb_listener_lock = Lock()
jd_listener_lock = Lock()
shorteners_list = []

sabnzbd_client = SabnzbdClient(
    host="http://localhost",
    api_key="admin",
    port="8070",
)
subprocess.run(["xnox", "-d", f"--profile={os.getcwd()}"], check=False)
subprocess.run(
    [
        "xnzb",
        "-f",
        "sabnzbd/SABnzbd.ini",
        "-s",
        ":::8070",
        "-b",
        "0",
        "-d",
        "-c",
        "-l",
        "0",
        "--console",
    ],
    check=False,
)


scheduler = AsyncIOScheduler(event_loop=bot_loop)
