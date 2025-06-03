import ast
import logging
import os
from importlib import import_module
from typing import Any, ClassVar

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


class Config:
    AS_DOCUMENT: bool = False
    AUTHORIZED_CHATS: str = ""
    BASE_URL: str = ""
    BASE_URL_PORT: int = 80
    BOT_TOKEN: str = ""
    CMD_SUFFIX: str = ""
    DATABASE_URL: str = ""
    DEFAULT_UPLOAD: str = "rc"
    EXCLUDED_EXTENSIONS: str = ""
    FFMPEG_CMDS: ClassVar[dict[str, list[str]]] = {}
    FILELION_API: str = ""
    GDRIVE_ID: str = ""
    HELPER_TOKENS: str = ""
    HYPER_THREADS: int = 0
    INCOMPLETE_TASK_NOTIFIER: bool = False
    INDEX_URL: str = ""
    IMDB_TEMPLATE: str = ""
    JD_EMAIL: str = ""
    JD_PASS: str = ""
    IS_TEAM_DRIVE: bool = False
    LEECH_DUMP_CHAT: ClassVar[list[str]] = []
    LEECH_FILENAME_PREFIX: str = ""
    LEECH_SUFFIX: str = ""
    LEECH_FONT: str = ""
    LEECH_FILENAME: str = ""
    LEECH_SPLIT_SIZE: int = 2097152000
    EQUAL_SPLITS: bool = False
    LOGIN_PASS: str = ""
    MEDIA_GROUP: bool = False
    HYBRID_LEECH: bool = False
    MEDIA_SEARCH_CHATS: ClassVar[list] = []
    HYDRA_IP: str = ""
    HYDRA_API_KEY: str = ""
    NAME_SUBSTITUTE: str = r""
    OWNER_ID: int = 0
    QUEUE_ALL: int = 0
    QUEUE_DOWNLOAD: int = 0
    QUEUE_UPLOAD: int = 0
    RCLONE_FLAGS: str = ""
    RCLONE_PATH: str = ""
    RCLONE_SERVE_URL: str = ""
    RCLONE_SERVE_USER: str = ""
    RCLONE_SERVE_PASS: str = ""
    RCLONE_SERVE_PORT: int = 8080
    RSS_CHAT: str = ""
    RSS_DELAY: int = 600
    RSS_SIZE_LIMIT: int = 0
    STOP_DUPLICATE: bool = False
    STREAMWISH_API: str = ""
    SUDO_USERS: str = ""
    TELEGRAM_API: int = 0
    TELEGRAM_HASH: str = ""
    TG_PROXY: ClassVar[dict[str, str]] = {}
    THUMBNAIL_LAYOUT: str = ""
    UPLOAD_PATHS: ClassVar[dict[str, str]] = {}
    UPSTREAM_REPO: str = ""
    USENET_SERVERS: ClassVar[list[dict[str, object]]] = []
    UPSTREAM_BRANCH: str = "main"
    USER_SESSION_STRING: str = ""
    USER_TRANSMISSION: bool = False
    USE_SERVICE_ACCOUNTS: bool = False
    WEB_PINCODE: bool = False

    # Streamrip Settings
    STREAMRIP_ENABLED: bool = True
    STREAMRIP_CONCURRENT_DOWNLOADS: int = 4
    STREAMRIP_MAX_SEARCH_RESULTS: int = 200
    STREAMRIP_ENABLE_DATABASE: bool = True
    STREAMRIP_AUTO_CONVERT: bool = True

    # Streamrip Quality and Format Settings
    STREAMRIP_DEFAULT_QUALITY: int = 3
    STREAMRIP_FALLBACK_QUALITY: int = 2
    STREAMRIP_DEFAULT_CODEC: str = "flac"
    STREAMRIP_SUPPORTED_CODECS: ClassVar[list[str]] = [
        "flac",
        "mp3",
        "m4a",
        "ogg",
        "opus",
    ]
    STREAMRIP_QUALITY_FALLBACK_ENABLED: bool = True

    # Streamrip Platform Settings
    STREAMRIP_QOBUZ_ENABLED: bool = True
    STREAMRIP_QOBUZ_QUALITY: int = 3
    STREAMRIP_TIDAL_ENABLED: bool = True
    STREAMRIP_TIDAL_QUALITY: int = 3
    STREAMRIP_DEEZER_ENABLED: bool = True
    STREAMRIP_DEEZER_QUALITY: int = 2
    STREAMRIP_SOUNDCLOUD_ENABLED: bool = True
    STREAMRIP_SOUNDCLOUD_QUALITY: int = 0
    STREAMRIP_LASTFM_ENABLED: bool = True
    STREAMRIP_YOUTUBE_QUALITY: int = 0

    # Streamrip Authentication
    STREAMRIP_QOBUZ_EMAIL: str = ""
    STREAMRIP_QOBUZ_PASSWORD: str = ""
    STREAMRIP_TIDAL_EMAIL: str = ""
    STREAMRIP_TIDAL_PASSWORD: str = ""
    STREAMRIP_TIDAL_ACCESS_TOKEN: str = ""
    STREAMRIP_TIDAL_REFRESH_TOKEN: str = ""
    STREAMRIP_TIDAL_USER_ID: str = ""
    STREAMRIP_TIDAL_COUNTRY_CODE: str = ""
    STREAMRIP_DEEZER_ARL: str = ""
    STREAMRIP_SOUNDCLOUD_CLIENT_ID: str = ""
    STREAMRIP_SOUNDCLOUD_APP_VERSION: str = ""

    # Streamrip Advanced Features
    STREAMRIP_FILENAME_TEMPLATE: str = ""
    STREAMRIP_FOLDER_TEMPLATE: str = ""
    STREAMRIP_EMBED_COVER_ART: bool = True
    STREAMRIP_SAVE_COVER_ART: bool = True
    STREAMRIP_COVER_ART_SIZE: str = "large"

    # Streamrip Limits
    STREAMRIP_LIMIT: float = 0  # GB

    # Streamrip Downloads Configuration
    STREAMRIP_MAX_CONNECTIONS: int = 6
    STREAMRIP_REQUESTS_PER_MINUTE: int = 60
    STREAMRIP_SOURCE_SUBDIRECTORIES: bool = False
    STREAMRIP_DISC_SUBDIRECTORIES: bool = True
    STREAMRIP_CONCURRENCY: bool = True
    STREAMRIP_VERIFY_SSL: bool = True

    # Streamrip Qobuz Configuration
    STREAMRIP_QOBUZ_DOWNLOAD_BOOKLETS: bool = True
    STREAMRIP_QOBUZ_USE_AUTH_TOKEN: bool = False
    STREAMRIP_QOBUZ_APP_ID: str = ""
    STREAMRIP_QOBUZ_SECRETS: ClassVar[list[str]] = []

    # Streamrip Tidal Configuration
    STREAMRIP_TIDAL_DOWNLOAD_VIDEOS: bool = True
    STREAMRIP_TIDAL_TOKEN_EXPIRY: str = "0"

    # Streamrip Deezer Configuration
    STREAMRIP_DEEZER_USE_DEEZLOADER: bool = True
    STREAMRIP_DEEZER_DEEZLOADER_WARNINGS: bool = True

    # Streamrip SoundCloud Configuration
    # STREAMRIP_SOUNDCLOUD_APP_VERSION already defined above

    # Streamrip YouTube Configuration
    STREAMRIP_YOUTUBE_DOWNLOAD_VIDEOS: bool = False
    STREAMRIP_YOUTUBE_VIDEO_FOLDER: str = ""
    STREAMRIP_YOUTUBE_VIDEO_DOWNLOADS_FOLDER: str = ""

    # Streamrip Database Configuration
    STREAMRIP_DATABASE_DOWNLOADS_ENABLED: bool = True
    STREAMRIP_DATABASE_DOWNLOADS_PATH: str = "./downloads.db"
    STREAMRIP_DATABASE_FAILED_DOWNLOADS_ENABLED: bool = True
    STREAMRIP_DATABASE_FAILED_DOWNLOADS_PATH: str = "./failed_downloads.db"

    # Streamrip Conversion Configuration
    STREAMRIP_CONVERSION_ENABLED: bool = False
    STREAMRIP_CONVERSION_CODEC: str = "ALAC"
    STREAMRIP_CONVERSION_SAMPLING_RATE: int = 48000
    STREAMRIP_CONVERSION_BIT_DEPTH: int = 24
    STREAMRIP_CONVERSION_LOSSY_BITRATE: int = 320

    # Streamrip Qobuz Filters Configuration
    STREAMRIP_QOBUZ_FILTERS_EXTRAS: bool = False
    STREAMRIP_QOBUZ_FILTERS_REPEATS: bool = False
    STREAMRIP_QOBUZ_FILTERS_NON_ALBUMS: bool = False
    STREAMRIP_QOBUZ_FILTERS_FEATURES: bool = False
    STREAMRIP_QOBUZ_FILTERS_NON_STUDIO_ALBUMS: bool = False
    STREAMRIP_QOBUZ_FILTERS_NON_REMASTER: bool = False

    # Streamrip Artwork Configuration
    STREAMRIP_ARTWORK_EMBED_MAX_WIDTH: int = -1
    STREAMRIP_ARTWORK_SAVED_MAX_WIDTH: int = -1

    # Streamrip Metadata Configuration
    STREAMRIP_METADATA_SET_PLAYLIST_TO_ALBUM: bool = True
    STREAMRIP_METADATA_RENUMBER_PLAYLIST_TRACKS: bool = True
    STREAMRIP_METADATA_EXCLUDE: ClassVar[list[str]] = []

    # Streamrip Filepaths Configuration
    STREAMRIP_FILEPATHS_ADD_SINGLES_TO_FOLDER: bool = False
    STREAMRIP_FILEPATHS_FOLDER_FORMAT: str = "{albumartist} - {title} ({year}) [{container}] [{bit_depth}B-{sampling_rate}kHz]"
    STREAMRIP_FILEPATHS_TRACK_FORMAT: str = (
        "{tracknumber:02}. {artist} - {title}{explicit}"
    )
    STREAMRIP_FILEPATHS_RESTRICT_CHARACTERS: bool = False
    STREAMRIP_FILEPATHS_TRUNCATE_TO: int = 120

    # Streamrip Last.fm Configuration
    STREAMRIP_LASTFM_SOURCE: str = "qobuz"
    STREAMRIP_LASTFM_FALLBACK_SOURCE: str = ""

    # Streamrip CLI Configuration
    STREAMRIP_CLI_TEXT_OUTPUT: bool = True
    STREAMRIP_CLI_PROGRESS_BARS: bool = True
    STREAMRIP_CLI_MAX_SEARCH_RESULTS: int = 200

    # Streamrip Misc Configuration
    STREAMRIP_MISC_CHECK_FOR_UPDATES: bool = True
    STREAMRIP_MISC_VERSION: str = "2.0.6"

    # Subtitle track metadata
    METADATA_SUBTITLE_TITLE: str = ""  # Subtitle track title metadata
    METADATA_SUBTITLE_AUTHOR: str = ""  # Subtitle track author metadata
    METADATA_SUBTITLE_COMMENT: str = ""  # Subtitle track comment metadata
    SET_COMMANDS: bool = True
    TOKEN_TIMEOUT: int = 0
    PAID_CHANNEL_ID: int = 0
    PAID_CHANNEL_LINK: str = ""
    DELETE_LINKS: bool = False
    FSUB_IDS: str = ""
    AD_KEYWORDS: str = ""  # Custom keywords for ad detection, separated by comma
    AD_BROADCASTER_ENABLED: bool = False  # Enable/disable ad broadcaster module
    LOG_CHAT_ID: int = 0
    LEECH_FILENAME_CAPTION: str = ""
    INSTADL_API: str = ""
    MEDIA_STORE: bool = False

    # Resource Management Settings
    PIL_MEMORY_LIMIT: int = 2048

    # Auto Restart Settings
    AUTO_RESTART_ENABLED: bool = False
    AUTO_RESTART_INTERVAL: int = 24  # in hours

    # Bulk Operation Settings
    BULK_ENABLED: bool = True  # Enable/disable bulk operations (-b flag)

    # Task Monitoring Settings
    TASK_MONITOR_ENABLED: bool = True
    TASK_MONITOR_INTERVAL: int = 60  # in seconds
    TASK_MONITOR_CONSECUTIVE_CHECKS: int = 20
    TASK_MONITOR_SPEED_THRESHOLD: int = 50  # in KB/s
    TASK_MONITOR_ELAPSED_THRESHOLD: int = 3600  # in seconds (1 hour)
    TASK_MONITOR_ETA_THRESHOLD: int = 86400  # in seconds (24 hours)
    TASK_MONITOR_WAIT_TIME: int = 600  # in seconds (10 minutes)
    TASK_MONITOR_COMPLETION_THRESHOLD: int = 86400  # in seconds (4 hours)
    TASK_MONITOR_CPU_HIGH: int = 90  # percentage
    TASK_MONITOR_CPU_LOW: int = 60  # percentage
    TASK_MONITOR_MEMORY_HIGH: int = 75  # percentage
    TASK_MONITOR_MEMORY_LOW: int = 60  # percentage

    # Limits Settings
    STORAGE_THRESHOLD: float = 0  # GB
    DIRECT_LIMIT: float = 0  # GB
    GDRIVE_LIMIT: float = 0  # GB
    CLONE_LIMIT: float = 0  # GB
    MEGA_LIMIT: float = 0  # GB
    LEECH_LIMIT: float = 0  # GB
    JD_LIMIT: float = 0  # GB
    NZB_LIMIT: float = 0  # GB
    PLAYLIST_LIMIT: int = 0  # Number of videos
    DAILY_TASK_LIMIT: int = 0  # Number of tasks per day
    DAILY_MIRROR_LIMIT: float = 0  # GB per day
    DAILY_LEECH_LIMIT: float = 0  # GB per day
    USER_MAX_TASKS: int = 0  # Maximum concurrent tasks per user
    USER_TIME_INTERVAL: int = 0  # Seconds between tasks
    BOT_MAX_TASKS: int = (
        0  # Maximum number of concurrent tasks the bot can handle (0 = unlimited)
    )
    STATUS_LIMIT: int = 10  # Number of tasks to display in status message
    SEARCH_LIMIT: int = (
        0  # Maximum number of search results to display (0 = unlimited)
    )
    SHOW_CLOUD_LINK: bool = True  # Show cloud links in upload completion message

    # Truecaller API Settings
    TRUECALLER_API_URL: str = ""

    # Extra Modules Settings
    ENABLE_EXTRA_MODULES: bool = True

    # Multi-link Settings
    MULTI_LINK_ENABLED: bool = True

    # Same Directory Settings
    SAME_DIR_ENABLED: bool = True

    # Mirror Settings
    MIRROR_ENABLED: bool = True

    # Leech Settings
    LEECH_ENABLED: bool = True

    # NZB Settings
    NZB_ENABLED: bool = True
    NZB_SEARCH_ENABLED: bool = True

    # JDownloader Settings
    JD_ENABLED: bool = True

    # Hyper Download Settings
    HYPERDL_ENABLED: bool = True

    # Media Search Settings
    MEDIA_SEARCH_ENABLED: bool = True

    # Rclone Settings
    RCLONE_ENABLED: bool = True

    # Archive Operation Settings
    ARCHIVE_FLAGS_ENABLED: bool = True

    # AI Settings
    # Default AI Provider (mistral, deepseek)
    DEFAULT_AI_PROVIDER: str = "mistral"

    # Mistral AI Settings
    MISTRAL_API_URL: str = ""

    # DeepSeek AI Settings
    DEEPSEEK_API_URL: str = ""

    # Command Suffix Settings
    CORRECT_CMD_SUFFIX: str = ""  # Comma-separated list of allowed command suffixes
    WRONG_CMD_WARNINGS_ENABLED: bool = (
        True  # Enable/disable warnings for wrong command suffixes
    )

    # VirusTotal Settings
    VT_API_KEY: str = ""
    VT_API_TIMEOUT: int = 500
    VT_ENABLED: bool = False
    VT_MAX_FILE_SIZE: int = 32 * 1024 * 1024  # 32MB default limit

    HEROKU_APP_NAME: str = ""
    HEROKU_API_KEY: str = ""

    # Branding Settings
    CREDIT: str = (
        "Powered by @aimmirror"  # Credit text shown in status messages and RSS feeds
    )
    OWNER_THUMB: str = "https://graph.org/file/80b7fb095063a18f9e232.jpg"  # Default thumbnail URL for owner

    @classmethod
    def _convert(cls, key, value):
        expected_type = type(getattr(cls, key))
        if value is None:
            return None

        if key == "LEECH_DUMP_CHAT":
            if isinstance(value, list):
                return [str(v).strip() for v in value if str(v).strip()]

            if isinstance(value, str):
                value = value.strip()
                if not value:
                    return []
                try:
                    evaluated = ast.literal_eval(value)
                    if isinstance(evaluated, list):
                        return [str(v).strip() for v in evaluated if str(v).strip()]
                except (ValueError, SyntaxError):
                    pass
                return [value] if value else []

            raise TypeError(f"{key} should be list[str], got {type(value).__name__}")

        # Special handling for MEDIA_TOOLS_ENABLED
        if key == "MEDIA_TOOLS_ENABLED":
            # If it's a string with commas, it's a list of enabled tools
            if isinstance(value, str) and "," in value:
                return value  # Keep it as a comma-separated string
            # If it's a single tool name as a string
            if (
                isinstance(value, str)
                and value.strip()
                and value.strip().lower()
                not in {"true", "1", "yes", "false", "0", "no"}
            ):
                return value  # Keep it as a string
            # If it's a boolean True or string that evaluates to True
            if value is True or (
                isinstance(value, str)
                and str(value).strip().lower() in {"true", "1", "yes"}
            ):
                # List of all available media tools
                all_tools = [
                    "watermark",
                    "merge",
                    "convert",
                    "compression",
                    "trim",
                    "extract",
                    "add",
                    "metadata",
                    "xtra",
                    "sample",
                    "screenshot",
                ]
                # Sort the tools to maintain consistent order
                all_tools.sort()
                return ",".join(all_tools)
            # If it's False or any other falsy value
            return False

        # Special handling for MEDIA_SEARCH_CHATS
        if key == "MEDIA_SEARCH_CHATS":
            # If value is None, return an empty list
            if value is None:
                return []

            # If it's already a list, check if all elements are integers
            if isinstance(value, list):
                # Convert all elements to integers if possible
                try:
                    return [
                        int(chat_id)
                        for chat_id in value
                        if str(chat_id).lstrip("-").isdigit()
                    ]
                except (ValueError, TypeError):
                    # If conversion fails, return the original list
                    return value

            # If it's a string, split by comma and convert to integers
            if isinstance(value, str):
                if not value.strip():
                    return []
                try:
                    # Split by comma and convert each value to integer
                    chat_ids = value.split(",")
                    return [
                        int(chat_id.strip())
                        for chat_id in chat_ids
                        if chat_id.strip().lstrip("-").isdigit()
                    ]
                except (ValueError, TypeError):
                    # If conversion fails, return an empty list
                    return []

            # For any other type, return an empty list
            return []

        if isinstance(value, expected_type):
            return value

        if expected_type is bool:
            return str(value).strip().lower() in {"true", "1", "yes"}

        if expected_type in [list, dict]:
            # Handle empty values for list and dict types
            if value == "" or value is None:
                # Return empty list or dict based on expected type
                return [] if expected_type is list else {}

            if not isinstance(value, str):
                raise TypeError(
                    f"{key} should be {expected_type.__name__}, got {type(value).__name__}"
                )

            try:
                evaluated = ast.literal_eval(value)
                if isinstance(evaluated, expected_type):
                    return evaluated
                raise TypeError
            except (ValueError, SyntaxError, TypeError) as e:
                # For LEECH_DUMP_CHAT specifically, return an empty list on error
                if key == "LEECH_DUMP_CHAT":
                    return []
                raise TypeError(
                    f"{key} should be {expected_type.__name__}, got invalid string: {value}"
                ) from e

        # Special handling for "none" or empty string values in numeric fields
        if isinstance(value, str) and expected_type in (int, float):
            # Convert string values to appropriate numeric types
            value_lower = value.lower()
            if value_lower == "none" or value == "":
                # For numeric types, return a default value (0) when "none" or empty string is specified
                return 0

            # Try to convert the string to the expected numeric type
            try:
                return expected_type(value)
            except (ValueError, TypeError):
                # If conversion fails, log a warning and return a default value
                logger.warning(
                    f"Failed to convert '{value}' to {expected_type.__name__} for {key}, using default value 0"
                )
                return 0

        try:
            return expected_type(value)
        except (ValueError, TypeError) as exc:
            raise TypeError(
                f"Invalid type for {key}: expected {expected_type}, got {type(value)}"
            ) from exc

    @classmethod
    def _normalize_value(cls, key: str, value: Any) -> Any:
        if isinstance(value, str):
            value = value.strip()

        if key == "DEFAULT_UPLOAD" and value != "gd":
            return "rc"

        if key in {"BASE_URL", "RCLONE_SERVE_URL", "INDEX_URL"}:
            return value.strip("/")

        if key == "USENET_SERVERS" and (
            not isinstance(value, list)
            or not value
            or not isinstance(value[0], dict)
            or not value[0].get("host")
        ):
            return []

        return value

    @classmethod
    def get(cls, key: str) -> Any:
        return getattr(cls, key, None)

    @classmethod
    def set(cls, key: str, value: Any):
        if not hasattr(cls, key):
            raise KeyError(f"{key} is not a valid configuration key.")
        converted = cls._convert(key, value)
        normalized = cls._normalize_value(key, converted)
        setattr(cls, key, normalized)

    @classmethod
    def get_all(cls) -> dict:
        return {key: getattr(cls, key) for key in sorted(cls.__annotations__)}

    @classmethod
    def load(cls):
        try:
            settings = import_module("config")
        except ModuleNotFoundError:
            logger.warning("No config.py module found.")
            return

        for attr in dir(settings):
            if not cls._is_valid_config_attr(settings, attr):
                continue

            value = getattr(settings, attr)
            if not value:
                continue

            try:
                cls.set(attr, value)
            except Exception as e:
                logger.warning(f"Skipping config '{attr}' due to error: {e}")

    @classmethod
    def load_dict(cls, config_dict: dict[str, Any]):
        for key, value in config_dict.items():
            try:
                cls.set(key, value)
            except Exception as e:
                logger.warning(f"Skipping config '{key}' due to error: {e}")

    @classmethod
    def _is_valid_config_attr(cls, module, attr: str) -> bool:
        return (
            not attr.startswith("__")
            and not callable(getattr(module, attr))
            and attr in cls.__annotations__
        )


class SystemEnv:
    @classmethod
    def load(cls):
        for key in Config.__annotations__:
            env_value = os.getenv(key)
            if env_value is not None:
                try:
                    Config.set(key, env_value)
                except Exception as e:
                    logger.warning(f"Env override failed for '{key}': {e}")
