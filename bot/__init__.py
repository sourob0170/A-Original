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

getLogger("requests").setLevel(WARNING)
getLogger("urllib3").setLevel(WARNING)
getLogger("pyrogram").setLevel(ERROR)
getLogger("httpx").setLevel(WARNING)
getLogger("pymongo").setLevel(WARNING)
getLogger("aiohttp").setLevel(WARNING)
getLogger("bot.modules.media_search").setLevel(ERROR)

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

stream_handler = StreamHandler()
stream_handler.setFormatter(formatter)

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

# Initialize Sabnzbd client with proper error handling and retry logic
sabnzbd_client = None
retry_count = 0
max_retries = 3

while retry_count < max_retries:
    try:
        LOGGER.info(
            f"Initializing SABnzbd client (attempt {retry_count + 1}/{max_retries})..."
        )
        sabnzbd_client = SabnzbdClient(
            host="http://localhost",
            api_key="admin",  # Use the same value as the password in SABnzbd.ini
            port="8070",
            RETRIES=5,  # Increase retries for better reliability
        )
        LOGGER.info("SABnzbd client initialized successfully")
        break
    except Exception as e:
        retry_count += 1
        if retry_count >= max_retries:
            LOGGER.error(f"All attempts to initialize SABnzbd client failed: {e}")
            sabnzbd_client = None
        else:
            # Wait before retrying with exponential backoff
            wait_time = 2**retry_count
            LOGGER.info(
                f"SABnzbd client initialization failed: {e}. Waiting {wait_time} seconds before retrying..."
            )
            import time

            time.sleep(wait_time)

# Properly manage qBittorrent startup
try:
    # First, try to kill any existing qBittorrent processes
    LOGGER.info("Stopping any existing qBittorrent processes...")
    subprocess.run(["pkill", "-f", "xnox"], check=False)
    import time

    time.sleep(2)  # Give more time for processes to terminate

    # Now start qBittorrent with proper error handling
    LOGGER.info("Starting qBittorrent...")
    result = subprocess.run(
        ["xnox", "-d", f"--profile={os.getcwd()}"],
        check=False,
        capture_output=True,
        text=True,
    )

    # Log any output from the command
    if result.stdout:
        LOGGER.info(f"qBittorrent startup output: {result.stdout}")
    if result.stderr:
        pass

    # Wait for qBittorrent to initialize
    time.sleep(3)
except Exception as e:
    LOGGER.error(f"Error managing qBittorrent: {e}")

# Start Sabnzbd with proper error handling and retry logic
try:
    # First, try to kill any existing SABnzbd processes
    LOGGER.info("Stopping any existing SABnzbd processes...")
    subprocess.run(["pkill", "-9", "-f", "xnzb"], check=False)
    time.sleep(2)  # Give more time for processes to terminate

    # Now start SABnzbd with retry logic
    retry_count = 0
    max_retries = 3
    sabnzbd_started = False

    while retry_count < max_retries and not sabnzbd_started:
        try:
            LOGGER.info(
                f"Starting SABnzbd (attempt {retry_count + 1}/{max_retries})..."
            )
            result = subprocess.run(
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
                capture_output=True,
                text=True,
                timeout=30,  # Add timeout to prevent hanging
            )

            # Log any output from the command
            if result.stdout:
                LOGGER.info(f"SABnzbd startup output: {result.stdout}")
            if result.stderr:
                LOGGER.warning(f"SABnzbd startup error output: {result.stderr}")

            # Check if the process started successfully
            if result.returncode == 0:
                LOGGER.info("SABnzbd started successfully")
                sabnzbd_started = True
            else:
                LOGGER.warning(
                    f"SABnzbd start returned non-zero exit code: {result.returncode}"
                )
                retry_count += 1
                if retry_count < max_retries:
                    wait_time = 2**retry_count
                    LOGGER.info(f"Waiting {wait_time} seconds before retrying...")
                    time.sleep(wait_time)

        except subprocess.TimeoutExpired:
            LOGGER.warning("SABnzbd start command timed out")
            retry_count += 1
            if retry_count < max_retries:
                wait_time = 2**retry_count
                LOGGER.info(f"Waiting {wait_time} seconds before retrying...")
                time.sleep(wait_time)
        except Exception as e:
            LOGGER.error(f"Error starting SABnzbd: {e}")
            retry_count += 1
            if retry_count < max_retries:
                wait_time = 2**retry_count
                LOGGER.info(f"Waiting {wait_time} seconds before retrying...")
                time.sleep(wait_time)

    # Wait for SABnzbd to initialize
    LOGGER.info("Waiting for SABnzbd to initialize...")
    time.sleep(5)  # Increased wait time for better reliability
except Exception as e:
    LOGGER.error(f"Error in SABnzbd startup process: {e}")


scheduler = AsyncIOScheduler(event_loop=bot_loop)
