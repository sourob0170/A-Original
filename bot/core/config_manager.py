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

    # Mega.nz Settings
    MEGA_ENABLED: bool = True
    MEGA_EMAIL: str = ""
    MEGA_PASSWORD: str = ""

    # MEGA Upload Settings
    MEGA_UPLOAD_ENABLED: bool = True
    MEGA_UPLOAD_FOLDER: str = ""  # Default upload folder path in MEGA account
    MEGA_UPLOAD_PUBLIC: bool = True  # Generate public links by default
    MEGA_UPLOAD_PRIVATE: bool = False  # Generate private links
    MEGA_UPLOAD_UNLISTED: bool = False  # Generate unlisted links
    MEGA_UPLOAD_EXPIRY_DAYS: int = 0  # Link expiry in days (0 = no expiry)
    MEGA_UPLOAD_PASSWORD: str = ""  # Password protection for uploads
    MEGA_UPLOAD_ENCRYPTION_KEY: str = ""  # Custom encryption key for uploads
    MEGA_UPLOAD_THUMBNAIL: bool = True  # Generate thumbnails for videos using FFmpeg
    MEGA_UPLOAD_DELETE_AFTER: bool = False  # Delete local files after upload

    # MEGA Clone Settings
    MEGA_CLONE_ENABLED: bool = True
    MEGA_CLONE_TO_FOLDER: str = ""  # Default folder for cloned files
    MEGA_CLONE_PRESERVE_STRUCTURE: bool = (
        True  # Preserve folder structure when cloning
    )
    MEGA_CLONE_OVERWRITE: bool = False  # Overwrite existing files when cloning

    # MEGA Search Settings
    MEGA_SEARCH_ENABLED: bool = True  # Enable/disable MEGA search functionality

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
    TORRENT_TIMEOUT: int = 0
    UPLOAD_PATHS: ClassVar[dict[str, str]] = {}
    UPSTREAM_REPO: str = ""
    USENET_SERVERS: ClassVar[list[dict[str, object]]] = []
    UPSTREAM_BRANCH: str = "main"
    USER_SESSION_STRING: str = ""
    USER_TRANSMISSION: bool = False
    USE_SERVICE_ACCOUNTS: bool = False
    WEB_PINCODE: bool = False
    YT_DLP_OPTIONS: ClassVar[dict[str, Any]] = {}

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

    # Zotify Settings - Based on official Zotify CONFIG_VALUES
    ZOTIFY_ENABLED: bool = True

    # Zotify Authentication
    ZOTIFY_CREDENTIALS_PATH: str = "./zotify_credentials.json"

    # Zotify Library Paths (from LIBRARY_PATHS)
    ZOTIFY_ALBUM_LIBRARY: str = "Music/Zotify Albums"
    ZOTIFY_PODCAST_LIBRARY: str = "Music/Zotify Podcasts"
    ZOTIFY_PLAYLIST_LIBRARY: str = "Music/Zotify Playlists"

    # Zotify Output Templates (from OUTPUT_PATHS and CONFIG_VALUES)
    ZOTIFY_OUTPUT_ALBUM: str = (
        "{album_artist}/{album}/{track_num:02d}. {artists} - {title}"
    )
    ZOTIFY_OUTPUT_PLAYLIST_TRACK: str = "{playlist}/{artists} - {title}"
    ZOTIFY_OUTPUT_PLAYLIST_EPISODE: str = "{playlist}/{episode_number} - {title}"
    ZOTIFY_OUTPUT_PODCAST: str = "{podcast}/{episode_number} - {title}"
    ZOTIFY_OUTPUT_SINGLE: str = (
        "{artists} - {title}"  # For single tracks not in albums
    )

    # Zotify Quality and Format Settings (Optimized for free accounts)
    ZOTIFY_DOWNLOAD_QUALITY: str = (
        "normal"  # auto, normal, high, very_high (normal=160kbps max for free)
    )
    ZOTIFY_AUDIO_FORMAT: str = "mp3"  # vorbis, mp3, flac, aac, fdk_aac, opus, wav, wavpack (mp3 most compatible)
    ZOTIFY_ARTWORK_SIZE: str = "medium"  # small, medium, large (medium to reduce bandwidth for free accounts)
    ZOTIFY_TRANSCODE_BITRATE: int = -1  # -1 to use download rate

    # Zotify Download Settings
    ZOTIFY_DOWNLOAD_REAL_TIME: bool = False
    ZOTIFY_REPLACE_EXISTING: bool = False
    ZOTIFY_SKIP_DUPLICATES: bool = True  # Default True in Zotify
    ZOTIFY_SKIP_PREVIOUS: bool = True  # Default True in Zotify

    # Zotify Metadata and Files
    ZOTIFY_SAVE_METADATA: bool = True
    ZOTIFY_SAVE_GENRE: bool = False
    ZOTIFY_ALL_ARTISTS: bool = True  # Default True in Zotify
    ZOTIFY_LYRICS_FILE: bool = False
    ZOTIFY_LYRICS_ONLY: bool = False
    ZOTIFY_SAVE_SUBTITLES: bool = False
    ZOTIFY_CREATE_PLAYLIST_FILE: bool = True

    # Zotify FFmpeg Settings
    ZOTIFY_FFMPEG_PATH: str = ""
    ZOTIFY_FFMPEG_ARGS: str = ""

    # Zotify Language and Locale
    ZOTIFY_LANGUAGE: str = "en"

    # Zotify Print/Logging Settings (from CONFIG_VALUES)
    ZOTIFY_PRINT_PROGRESS: bool = True
    ZOTIFY_PRINT_DOWNLOADS: bool = False  # Default False in Zotify
    ZOTIFY_PRINT_ERRORS: bool = True
    ZOTIFY_PRINT_WARNINGS: bool = True
    ZOTIFY_PRINT_SKIPS: bool = False  # Default False in Zotify

    # Zotify Match Functionality (from CONFIG_VALUES)
    ZOTIFY_MATCH_EXISTING: bool = (
        False  # Match existing files for skip functionality
    )

    # Missing CONFIG_VALUES from Zotify (exact 25 total)
    # Note: We already have most, but these were missing or incorrectly named

    # Zotify Supported Formats (for validation)
    ZOTIFY_SUPPORTED_AUDIO_FORMATS: ClassVar[list[str]] = [
        "vorbis",
        "mp3",
        "flac",
        "aac",
        "fdk_aac",
        "opus",
        "wav",
        "wavpack",
    ]
    ZOTIFY_SUPPORTED_QUALITIES: ClassVar[list[str]] = [
        "auto",
        "normal",
        "high",
        "very_high",
    ]
    ZOTIFY_SUPPORTED_ARTWORK_SIZES: ClassVar[list[str]] = [
        "small",
        "medium",
        "large",
    ]

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

    # INKYPINKY
    # Global metadata settings
    METADATA_KEY: str = ""  # Legacy metadata key
    METADATA_ALL: str = ""  # Global metadata for all fields
    METADATA_TITLE: str = ""  # Global title metadata
    METADATA_AUTHOR: str = ""  # Global author metadata
    METADATA_COMMENT: str = ""  # Global comment metadata

    # Video track metadata
    METADATA_VIDEO_TITLE: str = ""  # Video track title metadata
    METADATA_VIDEO_AUTHOR: str = ""  # Video track author metadata
    METADATA_VIDEO_COMMENT: str = ""  # Video track comment metadata

    # Audio track metadata
    METADATA_AUDIO_TITLE: str = ""  # Audio track title metadata
    METADATA_AUDIO_AUTHOR: str = ""  # Audio track author metadata
    METADATA_AUDIO_COMMENT: str = ""  # Audio track comment metadata

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

    # Media Tools Settings
    MEDIA_TOOLS_ENABLED: bool = True
    MEDIAINFO_ENABLED: bool = False

    # YouTube Upload Settings
    YOUTUBE_UPLOAD_ENABLED: bool = False  # Enable/disable YouTube upload feature
    YOUTUBE_UPLOAD_DEFAULT_PRIVACY: str = (
        "unlisted"  # Default privacy setting: public, unlisted, private
    )
    YOUTUBE_UPLOAD_DEFAULT_CATEGORY: str = (
        "22"  # Default category ID (22 = People & Blogs)
    )
    YOUTUBE_UPLOAD_DEFAULT_TAGS: str = (
        ""  # Default tags for uploaded videos, separated by comma
    )
    YOUTUBE_UPLOAD_DEFAULT_DESCRIPTION: str = (
        "Uploaded by AIM"  # Default description for uploaded videos
    )
    YOUTUBE_UPLOAD_DEFAULT_TITLE: str = (
        ""  # Default title template (empty = use filename)
    )

    # Advanced YouTube API Settings
    YOUTUBE_UPLOAD_DEFAULT_LANGUAGE: str = (
        "en"  # Default language for video metadata (ISO 639-1 code)
    )
    YOUTUBE_UPLOAD_DEFAULT_LICENSE: str = (
        "youtube"  # License: youtube (standard) or creativeCommon
    )
    YOUTUBE_UPLOAD_EMBEDDABLE: bool = (
        True  # Allow video to be embedded on other websites
    )
    YOUTUBE_UPLOAD_PUBLIC_STATS_VIEWABLE: bool = (
        True  # Allow public to see video statistics
    )
    YOUTUBE_UPLOAD_MADE_FOR_KIDS: bool = (
        False  # Mark videos as made for kids (COPPA compliance)
    )
    YOUTUBE_UPLOAD_NOTIFY_SUBSCRIBERS: bool = (
        True  # Notify subscribers when video is uploaded
    )
    YOUTUBE_UPLOAD_LOCATION_DESCRIPTION: str = ""  # Location description for videos
    YOUTUBE_UPLOAD_RECORDING_DATE: str = (
        ""  # Recording date (YYYY-MM-DD format, empty = upload date)
    )

    YOUTUBE_UPLOAD_AUTO_LEVELS: bool = False  # Auto-enhance video levels
    YOUTUBE_UPLOAD_STABILIZE: bool = False  # Auto-stabilize shaky videos

    # Compression Settings
    COMPRESSION_ENABLED: bool = False
    COMPRESSION_PRIORITY: int = 4
    COMPRESSION_DELETE_ORIGINAL: bool = True

    # Video Compression Settings
    COMPRESSION_VIDEO_ENABLED: bool = False
    COMPRESSION_VIDEO_PRESET: str = "none"  # none, fast, medium, slow
    COMPRESSION_VIDEO_CRF: str = "none"
    COMPRESSION_VIDEO_CODEC: str = "none"
    COMPRESSION_VIDEO_TUNE: str = "none"
    COMPRESSION_VIDEO_PIXEL_FORMAT: str = "none"
    COMPRESSION_VIDEO_BITDEPTH: str = "none"
    COMPRESSION_VIDEO_BITRATE: str = "none"
    COMPRESSION_VIDEO_RESOLUTION: str = "none"
    COMPRESSION_VIDEO_FORMAT: str = (
        "none"  # Output format for video compression (e.g., mp4, mkv)
    )

    # Audio Compression Settings
    COMPRESSION_AUDIO_ENABLED: bool = False
    COMPRESSION_AUDIO_PRESET: str = "none"  # none, fast, medium, slow
    COMPRESSION_AUDIO_CODEC: str = "none"
    COMPRESSION_AUDIO_BITRATE: str = "none"
    COMPRESSION_AUDIO_CHANNELS: str = "none"
    COMPRESSION_AUDIO_BITDEPTH: str = "none"
    COMPRESSION_AUDIO_FORMAT: str = (
        "none"  # Output format for audio compression (e.g., mp3, aac)
    )

    # Image Compression Settings
    COMPRESSION_IMAGE_ENABLED: bool = False
    COMPRESSION_IMAGE_PRESET: str = "none"  # none, fast, medium, slow
    COMPRESSION_IMAGE_QUALITY: str = "none"
    COMPRESSION_IMAGE_RESIZE: str = "none"
    COMPRESSION_IMAGE_FORMAT: str = (
        "none"  # Output format for image compression (e.g., jpg, png)
    )

    # Document Compression Settings
    COMPRESSION_DOCUMENT_ENABLED: bool = False
    COMPRESSION_DOCUMENT_PRESET: str = "none"  # none, fast, medium, slow
    COMPRESSION_DOCUMENT_DPI: str = "none"
    COMPRESSION_DOCUMENT_FORMAT: str = (
        "none"  # Output format for document compression (e.g., pdf)
    )

    # Subtitle Compression Settings
    COMPRESSION_SUBTITLE_ENABLED: bool = False
    COMPRESSION_SUBTITLE_PRESET: str = "none"  # none, fast, medium, slow
    COMPRESSION_SUBTITLE_ENCODING: str = "none"
    COMPRESSION_SUBTITLE_FORMAT: str = (
        "none"  # Output format for subtitle compression (e.g., srt)
    )

    # Archive Compression Settings
    COMPRESSION_ARCHIVE_ENABLED: bool = False
    COMPRESSION_ARCHIVE_PRESET: str = "none"  # none, fast, medium, slow
    COMPRESSION_ARCHIVE_LEVEL: str = "none"
    COMPRESSION_ARCHIVE_METHOD: str = "none"
    COMPRESSION_ARCHIVE_FORMAT: str = (
        "none"  # Output format for archive compression (e.g., zip, 7z)
    )
    COMPRESSION_ARCHIVE_PASSWORD: str = "none"  # Password for archive protection
    COMPRESSION_ARCHIVE_ALGORITHM: str = "none"  # Archive algorithm (e.g., 7z, zip)

    # Trim Settings
    TRIM_ENABLED: bool = False
    TRIM_PRIORITY: int = 5
    TRIM_START_TIME: str = "00:00:00"
    TRIM_END_TIME: str = ""
    TRIM_DELETE_ORIGINAL: bool = False

    # Video Trim Settings
    TRIM_VIDEO_ENABLED: bool = False
    TRIM_VIDEO_CODEC: str = "none"  # none, copy, libx264, etc.
    TRIM_VIDEO_PRESET: str = "none"  # none, fast, medium, slow
    TRIM_VIDEO_FORMAT: str = (
        "none"  # Output format for video trimming (e.g., mp4, mkv)
    )

    # Audio Trim Settings
    TRIM_AUDIO_ENABLED: bool = False
    TRIM_AUDIO_CODEC: str = "none"  # none, copy, aac, etc.
    TRIM_AUDIO_PRESET: str = "none"  # none, fast, medium, slow
    TRIM_AUDIO_FORMAT: str = (
        "none"  # Output format for audio trimming (e.g., mp3, aac)
    )

    # Image Trim Settings
    TRIM_IMAGE_ENABLED: bool = False
    TRIM_IMAGE_QUALITY: int = 90
    TRIM_IMAGE_FORMAT: str = (
        "none"  # Output format for image trimming (e.g., jpg, png)
    )

    # Document Trim Settings
    TRIM_DOCUMENT_ENABLED: bool = False
    TRIM_DOCUMENT_QUALITY: int = 90
    TRIM_DOCUMENT_FORMAT: str = (
        "none"  # Output format for document trimming (e.g., pdf)
    )

    # Subtitle Trim Settings
    TRIM_SUBTITLE_ENABLED: bool = False
    TRIM_SUBTITLE_ENCODING: str = "none"
    TRIM_SUBTITLE_FORMAT: str = (
        "none"  # Output format for subtitle trimming (e.g., srt)
    )

    # Archive Trim Settings
    TRIM_ARCHIVE_ENABLED: bool = False
    TRIM_ARCHIVE_FORMAT: str = (
        "none"  # Output format for archive trimming (e.g., zip, 7z)
    )

    # Extract Settings
    EXTRACT_ENABLED: bool = False
    EXTRACT_PRIORITY: int = 6
    EXTRACT_DELETE_ORIGINAL: bool = True

    # Video Extract Settings
    EXTRACT_VIDEO_ENABLED: bool = False
    EXTRACT_VIDEO_CODEC: str = "none"
    EXTRACT_VIDEO_FORMAT: str = (
        "none"  # Output format for video extraction (e.g., mp4, mkv)
    )
    EXTRACT_VIDEO_INDEX: int | None = None
    EXTRACT_VIDEO_QUALITY: str = (
        "none"  # Quality setting for video extraction (e.g., crf value)
    )
    EXTRACT_VIDEO_PRESET: str = (
        "none"  # Preset for video encoding (e.g., medium, slow)
    )
    EXTRACT_VIDEO_BITRATE: str = "none"  # Bitrate for video encoding (e.g., 5M)
    EXTRACT_VIDEO_RESOLUTION: str = (
        "none"  # Resolution for video extraction (e.g., 1920x1080)
    )
    EXTRACT_VIDEO_FPS: str = "none"  # Frame rate for video extraction (e.g., 30)

    # Audio Extract Settings
    EXTRACT_AUDIO_ENABLED: bool = False
    EXTRACT_AUDIO_CODEC: str = "none"
    EXTRACT_AUDIO_FORMAT: str = (
        "none"  # Output format for audio extraction (e.g., mp3, aac)
    )
    EXTRACT_AUDIO_INDEX: int | None = None
    EXTRACT_AUDIO_BITRATE: str = "none"  # Bitrate for audio encoding (e.g., 320k)
    EXTRACT_AUDIO_CHANNELS: str = "none"  # Number of audio channels (e.g., 2)
    EXTRACT_AUDIO_SAMPLING: str = "none"  # Sampling rate for audio (e.g., 48000)
    EXTRACT_AUDIO_VOLUME: str = "none"  # Volume adjustment for audio (e.g., 1.5)

    # Subtitle Extract Settings
    EXTRACT_SUBTITLE_ENABLED: bool = False
    EXTRACT_SUBTITLE_CODEC: str = "none"
    EXTRACT_SUBTITLE_FORMAT: str = (
        "none"  # Output format for subtitle extraction (e.g., srt, ass)
    )
    EXTRACT_SUBTITLE_INDEX: int | None = None
    EXTRACT_SUBTITLE_LANGUAGE: str = (
        "none"  # Language code for subtitle extraction (e.g., eng)
    )
    EXTRACT_SUBTITLE_ENCODING: str = (
        "none"  # Character encoding for subtitles (e.g., UTF-8)
    )
    EXTRACT_SUBTITLE_FONT: str = (
        "none"  # Font for subtitles (for formats that support it)
    )
    EXTRACT_SUBTITLE_FONT_SIZE: str = "none"  # Font size for subtitles

    # Attachment Extract Settings
    EXTRACT_ATTACHMENT_ENABLED: bool = False
    EXTRACT_ATTACHMENT_FORMAT: str = (
        "none"  # Output format for attachment extraction (e.g., png, jpg)
    )
    EXTRACT_ATTACHMENT_INDEX: int | None = None
    EXTRACT_ATTACHMENT_FILTER: str = (
        "none"  # Filter for attachment extraction (e.g., *.ttf)
    )

    # Extract Quality Settings
    EXTRACT_MAINTAIN_QUALITY: bool = True

    # Add Settings
    ADD_ENABLED: bool = False
    ADD_PRIORITY: int = 7
    ADD_DELETE_ORIGINAL: bool = True
    ADD_PRESERVE_TRACKS: bool = False
    ADD_REPLACE_TRACKS: bool = False

    # Video Add Settings
    ADD_VIDEO_ENABLED: bool = False
    ADD_VIDEO_CODEC: str = "copy"
    ADD_VIDEO_INDEX: int | None = None
    ADD_VIDEO_QUALITY: str = "none"
    ADD_VIDEO_PRESET: str = "none"
    ADD_VIDEO_BITRATE: str = "none"
    ADD_VIDEO_RESOLUTION: str = "none"
    ADD_VIDEO_FPS: str = "none"

    # Audio Add Settings
    ADD_AUDIO_ENABLED: bool = False
    ADD_AUDIO_CODEC: str = "copy"
    ADD_AUDIO_INDEX: int | None = None
    ADD_AUDIO_BITRATE: str = "none"
    ADD_AUDIO_CHANNELS: str = "none"
    ADD_AUDIO_SAMPLING: str = "none"
    ADD_AUDIO_VOLUME: str = "none"

    # Subtitle Add Settings
    ADD_SUBTITLE_ENABLED: bool = False
    ADD_SUBTITLE_CODEC: str = "copy"
    ADD_SUBTITLE_INDEX: int | None = None
    ADD_SUBTITLE_LANGUAGE: str = "none"
    ADD_SUBTITLE_ENCODING: str = "none"
    ADD_SUBTITLE_FONT: str = "none"
    ADD_SUBTITLE_FONT_SIZE: str = "none"

    # Attachment Add Settings
    ADD_ATTACHMENT_ENABLED: bool = False
    ADD_ATTACHMENT_INDEX: int | None = None
    ADD_ATTACHMENT_MIMETYPE: str = "none"

    # Convert Settings
    CONVERT_ENABLED: bool = False
    CONVERT_PRIORITY: int = 3
    CONVERT_DELETE_ORIGINAL: bool = True

    # Video Convert Settings
    CONVERT_VIDEO_ENABLED: bool = False
    CONVERT_VIDEO_FORMAT: str = "none"
    CONVERT_VIDEO_CODEC: str = "none"
    CONVERT_VIDEO_QUALITY: str = "none"
    CONVERT_VIDEO_CRF: int = 0
    CONVERT_VIDEO_PRESET: str = "none"
    CONVERT_VIDEO_MAINTAIN_QUALITY: bool = True
    CONVERT_VIDEO_RESOLUTION: str = "none"
    CONVERT_VIDEO_FPS: str = "none"

    # Audio Convert Settings
    CONVERT_AUDIO_ENABLED: bool = False
    CONVERT_AUDIO_FORMAT: str = "none"
    CONVERT_AUDIO_CODEC: str = "none"
    CONVERT_AUDIO_BITRATE: str = "none"
    CONVERT_AUDIO_CHANNELS: int = 0
    CONVERT_AUDIO_SAMPLING: int = 0
    CONVERT_AUDIO_VOLUME: float = 0.0

    # Subtitle Convert Settings
    CONVERT_SUBTITLE_ENABLED: bool = False
    CONVERT_SUBTITLE_FORMAT: str = "none"
    CONVERT_SUBTITLE_ENCODING: str = "none"
    CONVERT_SUBTITLE_LANGUAGE: str = "none"

    # Document Convert Settings
    CONVERT_DOCUMENT_ENABLED: bool = False
    CONVERT_DOCUMENT_FORMAT: str = "none"
    CONVERT_DOCUMENT_QUALITY: int = 0
    CONVERT_DOCUMENT_DPI: int = 0

    # Archive Convert Settings
    CONVERT_ARCHIVE_ENABLED: bool = False
    CONVERT_ARCHIVE_FORMAT: str = "none"
    CONVERT_ARCHIVE_LEVEL: int = 0
    CONVERT_ARCHIVE_METHOD: str = "none"

    # Watermark Settings
    WATERMARK_ENABLED: bool = False
    WATERMARK_KEY: str = ""
    WATERMARK_POSITION: str = "none"
    WATERMARK_SIZE: int = 0
    WATERMARK_COLOR: str = "none"
    WATERMARK_FONT: str = "none"
    WATERMARK_PRIORITY: int = 2
    WATERMARK_THREADING: bool = True
    WATERMARK_THREAD_NUMBER: int = 4
    WATERMARK_QUALITY: str = "none"
    WATERMARK_SPEED: str = "none"
    WATERMARK_OPACITY: float = 0.0
    WATERMARK_REMOVE_ORIGINAL: bool = True

    # Audio Watermark Settings
    AUDIO_WATERMARK_VOLUME: float = 0.0
    AUDIO_WATERMARK_INTERVAL: int = 0

    # Subtitle Watermark Settings
    SUBTITLE_WATERMARK_STYLE: str = "none"
    SUBTITLE_WATERMARK_INTERVAL: int = 0

    # Image Watermark Settings
    IMAGE_WATERMARK_ENABLED: bool = False
    IMAGE_WATERMARK_PATH: str = ""
    IMAGE_WATERMARK_SCALE: int = 10
    IMAGE_WATERMARK_OPACITY: float = 1.0
    IMAGE_WATERMARK_POSITION: str = "bottom_right"

    # Merge Settings
    MERGE_ENABLED: bool = False
    MERGE_PRIORITY: int = 1
    MERGE_THREADING: bool = True
    MERGE_THREAD_NUMBER: int = 4
    CONCAT_DEMUXER_ENABLED: bool = True
    FILTER_COMPLEX_ENABLED: bool = False

    # Output formats
    MERGE_OUTPUT_FORMAT_VIDEO: str = "none"
    MERGE_OUTPUT_FORMAT_AUDIO: str = "none"
    MERGE_OUTPUT_FORMAT_IMAGE: str = "none"
    MERGE_OUTPUT_FORMAT_DOCUMENT: str = "none"
    MERGE_OUTPUT_FORMAT_SUBTITLE: str = "none"

    # Video settings
    MERGE_VIDEO_CODEC: str = "none"
    MERGE_VIDEO_QUALITY: str = "none"
    MERGE_VIDEO_PRESET: str = "none"
    MERGE_VIDEO_CRF: str = "none"
    MERGE_VIDEO_PIXEL_FORMAT: str = "none"
    MERGE_VIDEO_TUNE: str = "none"
    MERGE_VIDEO_FASTSTART: bool = False

    # Audio settings
    MERGE_AUDIO_CODEC: str = "none"
    MERGE_AUDIO_BITRATE: str = "none"
    MERGE_AUDIO_CHANNELS: str = "none"
    MERGE_AUDIO_SAMPLING: str = "none"
    MERGE_AUDIO_VOLUME: str = "none"

    # Image settings
    MERGE_IMAGE_MODE: str = "none"
    MERGE_IMAGE_COLUMNS: str = "none"
    MERGE_IMAGE_QUALITY: int = 0
    MERGE_IMAGE_DPI: str = "none"
    MERGE_IMAGE_RESIZE: str = "none"
    MERGE_IMAGE_BACKGROUND: str = "none"

    # Subtitle settings
    MERGE_SUBTITLE_ENCODING: str = "none"
    MERGE_SUBTITLE_FONT: str = "none"
    MERGE_SUBTITLE_FONT_SIZE: str = "none"
    MERGE_SUBTITLE_FONT_COLOR: str = "none"
    MERGE_SUBTITLE_BACKGROUND: str = "none"

    # Document settings
    MERGE_DOCUMENT_PAPER_SIZE: str = "none"
    MERGE_DOCUMENT_ORIENTATION: str = "none"
    MERGE_DOCUMENT_MARGIN: str = "none"

    # General settings
    MERGE_REMOVE_ORIGINAL: bool = True
    MERGE_METADATA_TITLE: str = "none"
    MERGE_METADATA_AUTHOR: str = "none"
    MERGE_METADATA_COMMENT: str = "none"

    # Resource Management Settings
    PIL_MEMORY_LIMIT: int = 2048

    # Auto Restart Settings
    AUTO_RESTART_ENABLED: bool = False
    AUTO_RESTART_INTERVAL: int = 24  # in hours

    # Bulk Operation Settings
    BULK_ENABLED: bool = True  # Enable/disable bulk operations (-b flag)

    # Task Monitoring Settings
    TASK_MONITOR_ENABLED: bool = False
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
    TORRENT_LIMIT: float = 0  # GB
    DIRECT_LIMIT: float = 0  # GB
    YTDLP_LIMIT: float = 0  # GB
    GDRIVE_LIMIT: float = 0  # GB
    CLONE_LIMIT: float = 0  # GB
    MEGA_LIMIT: float = 0  # GB
    LEECH_LIMIT: float = 0  # GB
    JD_LIMIT: float = 0  # GB
    NZB_LIMIT: float = 0  # GB
    ZOTIFY_LIMIT: float = 0  # GB
    PLAYLIST_LIMIT: int = 0  # Number of videos
    DAILY_TASK_LIMIT: int = 0  # Number of tasks per day
    DAILY_MIRROR_LIMIT: float = 0  # GB per day
    DAILY_LEECH_LIMIT: float = 0  # GB per day
    USER_MAX_TASKS: int = 0  # Maximum concurrent tasks per user
    USER_TIME_INTERVAL: int = 0  # Seconds between tasks
    BOT_MAX_TASKS: int = (
        0  # Maximum number of concurrent tasks the bot can handle (0 = unlimited)
    )
    STATUS_UPDATE_INTERVAL: int = 3  # Status update interval in seconds (minimum 2)
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

    # YT-DLP Settings
    YTDLP_ENABLED: bool = True

    # Torrent Settings
    TORRENT_ENABLED: bool = True
    TORRENT_SEARCH_ENABLED: bool = True

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

    # Terabox Proxy Settings
    TERABOX_PROXY: str = "https://teradlrobot.cheemsbackup.workers.dev/"

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

        if key == "DEFAULT_UPLOAD" and value not in ["gd", "yt", "mg", "rc"]:
            return "gd"

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
