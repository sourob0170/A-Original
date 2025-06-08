# REQUIRED CONFIG
BOT_TOKEN = ""  # Get this from @BotFather
OWNER_ID = 0  # Your Telegram User ID (not username) as an integer
TELEGRAM_API = 0  # Get this from my.telegram.org
TELEGRAM_HASH = ""  # Get this from my.telegram.org

# Branding Settings
CREDIT = "Powered by @aimmirror"  # Credit text shown in status messages and RSS feeds (default: "Powered by @aimmirror")
OWNER_THUMB = "https://graph.org/file/80b7fb095063a18f9e232.jpg"  # Default thumbnail URL for owner (accepts Telegram file links)

# SEMI-REQUIRED, WE SUGGEST TO FILL IT FROM MONGODB
DATABASE_URL = ""  # MongoDB URI for storing user data and preferences

# OPTIONAL CONFIG
TG_PROXY = {}  # Proxy for Telegram connection, format: {'addr': 'ip:port', 'username': 'username', 'password': 'password'}
USER_SESSION_STRING = (
    ""  # Pyrogram user session string for mirror/leech authentication
)

CMD_SUFFIX = ""  # Command suffix to distinguish commands, e.g. "1" would make commands like /mirror1
CORRECT_CMD_SUFFIX = ""  # Comma-separated list of command suffixes that won't trigger warnings, e.g. "1,2,3"
WRONG_CMD_WARNINGS_ENABLED = (
    True  # Enable/disable warnings for wrong command suffixes
)
AUTHORIZED_CHATS = (
    ""  # List of authorized chat IDs where the bot can be used, separated by space
)
SUDO_USERS = (
    ""  # List of sudo user IDs who can use admin commands, separated by space
)
DEFAULT_UPLOAD = (
    "gd"  # Default upload destination: 'rc' for rclone or 'gd' for Google Drive
)
FILELION_API = ""  # FileLion API key for direct links
STREAMWISH_API = ""  # StreamWish API key for direct links
EXCLUDED_EXTENSIONS = (
    ""  # File extensions to exclude from processing, separated by space
)
INCOMPLETE_TASK_NOTIFIER = False  # Notify about incomplete tasks on bot restart
YT_DLP_OPTIONS = {}  # Additional yt-dlp options as a JSON string

NAME_SUBSTITUTE = r""  # Regex pattern to substitute in filenames
FFMPEG_CMDS = {}  # Custom FFmpeg commands for different file types
UPLOAD_PATHS = {}  # Custom upload paths for different file types
MEDIA_STORE = False  # Enable media store for faster thumbnail generation
MEDIA_SEARCH_ENABLED = True  # Enable/disable media search feature
MEDIA_SEARCH_CHATS = []  # List of chat IDs where media search is enabled
DELETE_LINKS = False  # Delete links after download
FSUB_IDS = ""  # Force subscribe channel IDs, separated by space
AD_BROADCASTER_ENABLED = (
    False  # Enable/disable automatic ad broadcasting from FSUB channels to users
)
AD_KEYWORDS = ""  # Custom keywords/phrases for ad detection, separated by comma (e.g., "#ad,#ad bangla,#sponsored,InsideAds")
TOKEN_TIMEOUT = 0  # Token timeout in seconds (0 = no timeout)
LOGIN_PASS = ""  # Password for web login
PAID_CHANNEL_ID = 0  # Paid channel ID for premium features
PAID_CHANNEL_LINK = ""  # Invite link for paid channel
SET_COMMANDS = True  # Set bot commands in Telegram UI
LOG_CHAT_ID = 0  # Chat ID where logs will be sent
MEDIAINFO_ENABLED = (
    False  # Enable/disable mediainfo command for detailed media information
)
INSTADL_API = ""  # InstaDL API key for Instagram downloads

# Feature Toggles
MIRROR_ENABLED = True  # Enable/disable mirror feature
LEECH_ENABLED = True  # Enable/disable leech feature
YTDLP_ENABLED = True  # Enable/disable YT-DLP feature
TORRENT_ENABLED = True  # Enable/disable torrent feature
TORRENT_SEARCH_ENABLED = True  # Enable/disable torrent search feature
NZB_ENABLED = True  # Enable/disable NZB feature
JD_ENABLED = True  # Enable/disable JDownloader feature
MEGA_ENABLED = True  # Enable/disable Mega.nz downloads
RCLONE_ENABLED = True  # Enable/disable Rclone feature
ARCHIVE_FLAGS_ENABLED = True  # Enable/disable archive operation flags
MULTI_LINK_ENABLED = True  # Enable/disable multi-link feature
SAME_DIR_ENABLED = True  # Enable/disable same directory feature
BULK_ENABLED = True  # Enable/disable bulk operations (-b flag)

# GDrive Tools
GDRIVE_ID = ""  # Google Drive folder/TeamDrive ID where files will be uploaded
IS_TEAM_DRIVE = False  # Whether the GDRIVE_ID is a TeamDrive
STOP_DUPLICATE = False  # Skip uploading files that are already in the drive
INDEX_URL = ""  # Index URL for Google Drive
USE_SERVICE_ACCOUNTS = False  # Whether to use service accounts for Google Drive
SHOW_CLOUD_LINK = True  # Show cloud links in upload completion message

# Rclone
RCLONE_PATH = ""  # Path to rclone.conf file
RCLONE_FLAGS = ""  # Additional rclone flags
RCLONE_SERVE_URL = ""  # URL for rclone serve
RCLONE_SERVE_PORT = 8080  # Port for rclone serve
RCLONE_SERVE_USER = ""  # Username for rclone serve
RCLONE_SERVE_PASS = ""  # Password for rclone serve
# JDownloader
JD_EMAIL = ""  # JDownloader email/username
JD_PASS = ""  # JDownloader password

# Mega.nz Settings
MEGA_EMAIL = ""  # Mega.nz account email (optional, for premium features)
MEGA_PASSWORD = ""  # Mega.nz account password (optional, for premium features)

# MEGA Upload Settings
MEGA_UPLOAD_ENABLED = True  # Enable MEGA upload functionality
MEGA_UPLOAD_FOLDER = ""  # Default upload folder path in MEGA account (empty = root)
MEGA_UPLOAD_PUBLIC = True  # Generate public links by default
MEGA_UPLOAD_PRIVATE = False  # Generate private links
MEGA_UPLOAD_UNLISTED = False  # Generate unlisted links
MEGA_UPLOAD_EXPIRY_DAYS = 0  # Link expiry in days (0 = no expiry)
MEGA_UPLOAD_PASSWORD = ""  # Password protection for uploads
MEGA_UPLOAD_ENCRYPTION_KEY = ""  # Custom encryption key for uploads
MEGA_UPLOAD_THUMBNAIL = True  # Generate thumbnails for videos using FFmpeg
MEGA_UPLOAD_DELETE_AFTER = False  # Delete local files after upload

# MEGA Clone Settings
MEGA_CLONE_ENABLED = True  # Enable MEGA clone functionality
MEGA_CLONE_TO_FOLDER = ""  # Default folder for cloned files (empty = root)
MEGA_CLONE_PRESERVE_STRUCTURE = True  # Preserve folder structure when cloning
MEGA_CLONE_OVERWRITE = False  # Overwrite existing files when cloning

# MEGA Search Settings
MEGA_SEARCH_ENABLED = True  # Enable/disable MEGA search functionality

# Sabnzbd
HYDRA_IP = ""  # Hydra IP address for direct links
HYDRA_API_KEY = ""  # Hydra API key for direct links
NZB_SEARCH_ENABLED = True  # Enable/disable NZB search feature
USENET_SERVERS = [  # List of Usenet servers for NZB downloads
    {
        "name": "main",  # Server name
        "host": "",  # Server hostname or IP
        "port": 563,  # Server port
        "timeout": 60,  # Connection timeout in seconds
        "username": "",  # Server username
        "password": "",  # Server password
        "connections": 8,  # Number of connections to use
        "ssl": 1,  # Use SSL: 0=no, 1=yes
        "ssl_verify": 2,  # SSL verification: 0=no, 1=verify host, 2=verify host and peer
        "ssl_ciphers": "",  # SSL ciphers to use
        "enable": 1,  # Enable server: 0=no, 1=yes
        "required": 0,  # Server is required: 0=no, 1=yes
        "optional": 0,  # Server is optional: 0=no, 1=yes
        "retention": 0,  # Server retention in days (0=unlimited)
        "send_group": 0,  # Send group command: 0=no, 1=yes
        "priority": 0,  # Server priority (0=highest)
    },
]

# Update
UPSTREAM_REPO = "https://github.com/AeonOrg/Aeon-MLTB"  # Repository URL for updates
UPSTREAM_BRANCH = "extended"  # Branch to use for updates

# Leech
LEECH_SPLIT_SIZE = 0  # Size of split files in bytes, 0 means no split
AS_DOCUMENT = False  # Send files as documents instead of media
MEDIA_GROUP = False  # Group media files together when sending
USER_TRANSMISSION = False  # Use transmission for torrents
HYBRID_LEECH = False  # Enable hybrid leech (both document and media)
LEECH_FILENAME_PREFIX = ""  # Prefix to add to leeched filenames
LEECH_SUFFIX = ""  # Suffix to add to leeched files
LEECH_FONT = ""  # Font to use for leech captions
LEECH_FILENAME = ""  # Custom filename template for leeched files
LEECH_FILENAME_CAPTION = (
    ""  # Caption template for leeched files (max 1024 characters)
)
LEECH_DUMP_CHAT = []  # Chat IDs ["-100123456789", "b:@mychannel", "u:-100987654321", "h:@mygroup|123456"] where leeched files will be sent
THUMBNAIL_LAYOUT = ""  # Layout for thumbnails: empty, top, bottom, or custom
EQUAL_SPLITS = False  # Create equal-sized parts when splitting files

# Hyper Download Settings
HYPERDL_ENABLED = True  # Enable/disable hyper download feature
HELPER_TOKENS = ""  # Bot tokens for helper bots, separated by space. Format: "token1 token2 token3"
HYPER_THREADS = 0  # Number of threads for hyper download (0 = auto-detect based on number of helper bots)

# qBittorrent/Aria2c
TORRENT_TIMEOUT = 0  # Timeout for torrent downloads in seconds (0 = no timeout)
BASE_URL = ""  # Base URL for web server
BASE_URL_PORT = 80  # Port for web server (0 to disable)
WEB_PINCODE = False  # Enable pincode protection for web server

# Queueing system
QUEUE_ALL = 0  # Maximum number of concurrent tasks (0 = unlimited)
QUEUE_DOWNLOAD = 0  # Maximum number of concurrent downloads (0 = unlimited)
QUEUE_UPLOAD = 0  # Maximum number of concurrent uploads (0 = unlimited)

# Heroku config for get BASE_URL automatically
HEROKU_APP_NAME = ""
HEROKU_API_KEY = ""

# RSS
RSS_DELAY = 600  # Delay between RSS feed checks in seconds
RSS_CHAT = ""  # Chat ID where RSS feed updates will be sent
RSS_SIZE_LIMIT = 0  # Maximum size for RSS downloads in bytes (0 = unlimited)

# Resource Management Settings
PIL_MEMORY_LIMIT = 2048  # Memory limit for PIL image processing in MB

# Auto Restart Settings
AUTO_RESTART_ENABLED = False  # Enable automatic bot restart
AUTO_RESTART_INTERVAL = 24  # Restart interval in hours

# Limits Settings
STORAGE_THRESHOLD = (
    0  # Storage threshold in GB, bot will stop if free space falls below this
)
TORRENT_LIMIT = 0  # Maximum size for torrent downloads in GB (0 = unlimited)
DIRECT_LIMIT = 0  # Maximum size for direct link downloads in GB (0 = unlimited)
YTDLP_LIMIT = 0  # Maximum size for YouTube/video downloads in GB (0 = unlimited)
GDRIVE_LIMIT = 0  # Maximum size for Google Drive downloads in GB (0 = unlimited)
CLONE_LIMIT = 0  # Maximum size for clone operations in GB (0 = unlimited)
MEGA_LIMIT = 0  # Maximum size for Mega downloads in GB (0 = unlimited)
LEECH_LIMIT = 0  # Maximum size for leech operations in GB (0 = unlimited)
JD_LIMIT = 0  # Maximum size for JDownloader downloads in GB (0 = unlimited)
NZB_LIMIT = 0  # Maximum size for NZB downloads in GB (0 = unlimited)
PLAYLIST_LIMIT = 0  # Maximum number of videos in a playlist (0 = unlimited)

ZOTIFY_LIMIT = 0  # Maximum size for Zotify downloads in GB (0 = unlimited)
DAILY_TASK_LIMIT = 0  # Maximum number of tasks per day per user (0 = unlimited)
DAILY_MIRROR_LIMIT = 0  # Maximum mirror size in GB per day per user (0 = unlimited)
DAILY_LEECH_LIMIT = 0  # Maximum leech size in GB per day per user (0 = unlimited)
USER_MAX_TASKS = 0  # Maximum concurrent tasks per user (0 = unlimited)
BOT_MAX_TASKS = (
    0  # Maximum number of concurrent tasks the bot can handle (0 = unlimited)
)
USER_TIME_INTERVAL = 0  # Minimum time between user tasks in seconds (0 = no delay)
STATUS_UPDATE_INTERVAL = (
    3  # Status update interval in seconds (minimum 2, recommended: 3-5)
)
STATUS_LIMIT = 10  # Number of tasks to display in status message (recommended: 4-10)
SEARCH_LIMIT = 0  # Maximum number of search results to display (0 = unlimited)

# Task Monitoring Settings
TASK_MONITOR_ENABLED = True  # Master switch to enable/disable task monitoring
TASK_MONITOR_INTERVAL = 60  # Interval between task monitoring checks in seconds
TASK_MONITOR_CONSECUTIVE_CHECKS = 20  # Number of consecutive checks for monitoring
TASK_MONITOR_SPEED_THRESHOLD = 50  # Speed threshold in KB/s
TASK_MONITOR_ELAPSED_THRESHOLD = 3600  # Elapsed time threshold in seconds (1 hour)
TASK_MONITOR_ETA_THRESHOLD = 86400  # ETA threshold in seconds (24 hours)
TASK_MONITOR_WAIT_TIME = (
    600  # Wait time before canceling a task in seconds (10 minutes)
)
TASK_MONITOR_COMPLETION_THRESHOLD = (
    86400  # Completion threshold in seconds (4 hours)
)
TASK_MONITOR_CPU_HIGH = 90  # High CPU usage threshold percentage
TASK_MONITOR_CPU_LOW = 60  # Low CPU usage threshold percentage
TASK_MONITOR_MEMORY_HIGH = 75  # High memory usage threshold percentage
TASK_MONITOR_MEMORY_LOW = 60  # Low memory usage threshold percentage

# Extra Modules Settings
ENABLE_EXTRA_MODULES = True  # Enable additional modules and features

# Security Tools Settings
VT_API_KEY = ""  # VirusTotal API key for malware scanning
VT_API_TIMEOUT = 500  # VirusTotal API timeout in seconds
VT_ENABLED = False  # Enable/disable VirusTotal functionality
VT_MAX_FILE_SIZE = (
    33554432  # Maximum file size for VirusTotal scanning in bytes (32MB)
)
TRUECALLER_API_URL = ""  # Truecaller API URL for phone number lookup

# Direct Link Generator Settings
TERABOX_PROXY = "https://teradlrobot.cheemsbackup.workers.dev/"  # Terabox proxy URL for bypassing restrictions

# Custom template for IMDB results formatting.
IMDB_TEMPLATE = """<b>🎬 Title:</b> <code>{title}</code> [{year}]
 <b>⭐ Rating:</b> <i>{rating}</i>
 <b>🎭 Genre:</b> {genres}
 <b>📅 Released:</b> <a href=\"{url_releaseinfo}\">{release_date}</a>
 <b>🎙️ Languages:</b> {languages}
 <b>🌍 Country:</b> {countries}
 <b>🎬 Type:</b> {kind}

 <b>📖 Story Line:</b>
 <blockquote>{plot}</blockquote>

 <b>🔗 IMDb URL:</b> <a href=\"{url}\">{url}</a>
 <b>👥 Cast:</b> <a href=\"{url_cast}\">{cast}</a>

 <b>👨‍💼 Director:</b> {director}
 <b>✍️ Writer:</b> {writer}
 <b>🎵 Music:</b> {composer}
 <b>🎥 Cinematography:</b> {cinematographer}

 <b>⏱️ Runtime:</b> {runtime} minutes
 <b>🏆 Awards:</b> {certificates}
 <i>Powered by IMDb</i>"""

# AI Settings
DEFAULT_AI_PROVIDER = (
    "mistral"  # Default AI provider for /ask command: mistral, deepseek
)
MISTRAL_API_URL = ""  # Custom Mistral AI API URL
DEEPSEEK_API_URL = ""  # Custom DeepSeek AI API URL

# Streamrip Settings
STREAMRIP_ENABLED = True  # Enable/disable streamrip feature
STREAMRIP_CONCURRENT_DOWNLOADS = 4  # Concurrent downloads per platform
STREAMRIP_MAX_SEARCH_RESULTS = 20  # Search results limit
STREAMRIP_ENABLE_DATABASE = True  # Enable download history tracking
STREAMRIP_AUTO_CONVERT = True  # Enable automatic format conversion

# Streamrip Quality and Format Settings
STREAMRIP_DEFAULT_QUALITY = (
    3  # Default quality (0-4: 0=128kbps, 1=320kbps, 2=CD, 3=Hi-Res, 4=Hi-Res+)
)
STREAMRIP_FALLBACK_QUALITY = 2  # Fallback if preferred quality unavailable
STREAMRIP_DEFAULT_CODEC = "flac"  # Default output format
STREAMRIP_SUPPORTED_CODECS = [
    "flac",
    "mp3",
    "m4a",
    "ogg",
    "opus",
]  # Available formats
STREAMRIP_QUALITY_FALLBACK_ENABLED = True  # Auto-fallback to lower quality

# Streamrip Platform Settings
STREAMRIP_QOBUZ_ENABLED = True  # Enable Qobuz downloads
STREAMRIP_QOBUZ_QUALITY = 3  # Qobuz quality level (0-3)
STREAMRIP_TIDAL_ENABLED = True  # Enable Tidal downloads
STREAMRIP_TIDAL_QUALITY = 3  # Tidal quality level (0-3)
STREAMRIP_DEEZER_ENABLED = True  # Enable Deezer downloads
STREAMRIP_DEEZER_QUALITY = 2  # Deezer quality level (0-2)
STREAMRIP_SOUNDCLOUD_ENABLED = True  # Enable SoundCloud downloads
STREAMRIP_SOUNDCLOUD_QUALITY = 0  # SoundCloud quality level
STREAMRIP_LASTFM_ENABLED = True  # Enable Last.fm playlist conversion
STREAMRIP_YOUTUBE_QUALITY = 0  # YouTube quality level

# Streamrip Authentication (stored securely in database)
# Qobuz - Highest quality platform (up to 24-bit/192kHz)
STREAMRIP_QOBUZ_EMAIL = ""  # Qobuz account email
STREAMRIP_QOBUZ_PASSWORD = ""  # Qobuz account password
STREAMRIP_QOBUZ_APP_ID = ""  # Qobuz app ID (get via 'python dev/get_qobuz_keys.py')
STREAMRIP_QOBUZ_SECRETS = []  # Qobuz secrets array (get via 'python dev/get_qobuz_keys.py')

# Tidal - Hi-Res/MQA platform (OAuth tokens preferred)
STREAMRIP_TIDAL_ACCESS_TOKEN = (
    ""  # Tidal access token (get via 'python dev/tidal_tokens.py')
)
STREAMRIP_TIDAL_REFRESH_TOKEN = (
    ""  # Tidal refresh token (get via 'python dev/tidal_tokens.py')
)
STREAMRIP_TIDAL_USER_ID = ""  # Tidal user ID (get via 'python dev/tidal_tokens.py')
STREAMRIP_TIDAL_COUNTRY_CODE = ""  # Tidal country code (e.g., 'US')
STREAMRIP_TIDAL_TOKEN_EXPIRY = ""  # Tidal token expiry timestamp (optional)
# Fallback authentication (limited functionality)
STREAMRIP_TIDAL_EMAIL = ""  # Tidal email (fallback method)
STREAMRIP_TIDAL_PASSWORD = ""  # Tidal password (fallback method)

# Deezer - CD quality platform
STREAMRIP_DEEZER_ARL = ""  # Deezer ARL cookie (get from browser cookies)

# SoundCloud - Free platform (optional authentication)
STREAMRIP_SOUNDCLOUD_CLIENT_ID = ""  # SoundCloud client ID (optional)
STREAMRIP_SOUNDCLOUD_APP_VERSION = ""  # SoundCloud app version (optional)

# Streamrip Advanced Features
STREAMRIP_METADATA_EXCLUDE = []  # Metadata tags to exclude (e.g., ["genre", "albumartist"])
STREAMRIP_FILENAME_TEMPLATE = ""  # Custom filename template
STREAMRIP_FOLDER_TEMPLATE = ""  # Custom folder structure template
STREAMRIP_EMBED_COVER_ART = True  # Embed album artwork in files
STREAMRIP_SAVE_COVER_ART = True  # Save separate cover art files
STREAMRIP_COVER_ART_SIZE = "large"  # Cover art size preference

# Streamrip Download Configuration
STREAMRIP_MAX_CONNECTIONS = 6  # Maximum connections per download
STREAMRIP_REQUESTS_PER_MINUTE = 60  # API requests per minute limit
STREAMRIP_SOURCE_SUBDIRECTORIES = False  # Create source subdirectories
STREAMRIP_DISC_SUBDIRECTORIES = True  # Create disc subdirectories
STREAMRIP_CONCURRENCY = True  # Enable concurrent downloads
STREAMRIP_VERIFY_SSL = True  # Verify SSL certificates

# Streamrip Platform-Specific Configuration
STREAMRIP_QOBUZ_DOWNLOAD_BOOKLETS = True  # Download PDF booklets from Qobuz
STREAMRIP_QOBUZ_USE_AUTH_TOKEN = False  # Use authentication token for Qobuz
STREAMRIP_TIDAL_DOWNLOAD_VIDEOS = True  # Download videos from Tidal
STREAMRIP_DEEZER_USE_DEEZLOADER = True  # Use Deezloader for Deezer
STREAMRIP_DEEZER_DEEZLOADER_WARNINGS = True  # Show Deezloader warnings
STREAMRIP_YOUTUBE_DOWNLOAD_VIDEOS = False  # Download videos from YouTube
STREAMRIP_YOUTUBE_VIDEO_FOLDER = ""  # YouTube video download folder
STREAMRIP_YOUTUBE_VIDEO_DOWNLOADS_FOLDER = ""  # YouTube video downloads folder

# Streamrip Database Configuration
STREAMRIP_DATABASE_DOWNLOADS_ENABLED = True  # Enable downloads database
STREAMRIP_DATABASE_DOWNLOADS_PATH = "./downloads.db"  # Downloads database path
STREAMRIP_DATABASE_FAILED_DOWNLOADS_ENABLED = (
    True  # Enable failed downloads database
)
STREAMRIP_DATABASE_FAILED_DOWNLOADS_PATH = (
    "./failed_downloads.db"  # Failed downloads database path
)

# Streamrip Conversion Configuration
STREAMRIP_CONVERSION_ENABLED = False  # Enable format conversion
STREAMRIP_CONVERSION_CODEC = "ALAC"  # Conversion codec
STREAMRIP_CONVERSION_SAMPLING_RATE = 48000  # Conversion sampling rate
STREAMRIP_CONVERSION_BIT_DEPTH = 24  # Conversion bit depth
STREAMRIP_CONVERSION_LOSSY_BITRATE = 320  # Lossy conversion bitrate

# Streamrip Filters and Metadata
STREAMRIP_QOBUZ_FILTERS_EXTRAS = False  # Filter extra content from Qobuz
STREAMRIP_QOBUZ_FILTERS_REPEATS = False  # Filter repeat content
STREAMRIP_QOBUZ_FILTERS_NON_ALBUMS = False  # Filter non-album content
STREAMRIP_QOBUZ_FILTERS_FEATURES = False  # Filter featured content
STREAMRIP_QOBUZ_FILTERS_NON_STUDIO_ALBUMS = False  # Filter non-studio albums
STREAMRIP_QOBUZ_FILTERS_NON_REMASTER = False  # Filter non-remaster content
STREAMRIP_ARTWORK_EMBED_MAX_WIDTH = (
    -1
)  # Max width for embedded artwork (-1 = no limit)
STREAMRIP_ARTWORK_SAVED_MAX_WIDTH = -1  # Max width for saved artwork (-1 = no limit)
STREAMRIP_METADATA_SET_PLAYLIST_TO_ALBUM = True  # Set playlist as album in metadata
STREAMRIP_METADATA_RENUMBER_PLAYLIST_TRACKS = True  # Renumber playlist tracks

# Streamrip File Paths and Naming
STREAMRIP_FILEPATHS_ADD_SINGLES_TO_FOLDER = False  # Add singles to folder
STREAMRIP_FILEPATHS_FOLDER_FORMAT = "{albumartist} - {title} ({year}) [{container}] [{bit_depth}B-{sampling_rate}kHz]"  # Folder naming format template
STREAMRIP_FILEPATHS_TRACK_FORMAT = (
    "{tracknumber:02}. {artist} - {title}{explicit}"  # Track naming format template
)
STREAMRIP_FILEPATHS_RESTRICT_CHARACTERS = (
    False  # Restrict special characters in filenames
)
STREAMRIP_FILEPATHS_TRUNCATE_TO = 120  # Truncate filenames to length

# Streamrip Last.fm and CLI Configuration
STREAMRIP_LASTFM_SOURCE = "qobuz"  # Last.fm source platform
STREAMRIP_LASTFM_FALLBACK_SOURCE = ""  # Last.fm fallback source platform
STREAMRIP_CLI_TEXT_OUTPUT = True  # Enable CLI text output
STREAMRIP_CLI_PROGRESS_BARS = False  # Show CLI progress bars (disabled for bot)
STREAMRIP_CLI_MAX_SEARCH_RESULTS = 200  # Max CLI search results

# Streamrip Miscellaneous
STREAMRIP_MISC_CHECK_FOR_UPDATES = True  # Check for streamrip updates
STREAMRIP_MISC_VERSION = "2.0.6"  # Streamrip version

# Zotify Settings - Spotify Music Downloader
ZOTIFY_ENABLED = True  # Enable/disable Zotify feature for Spotify downloads

# Zotify Authentication
ZOTIFY_CREDENTIALS_PATH = (
    "./zotify_credentials.json"  # Path to Spotify credentials file
)

# Zotify Library Paths - Where downloaded content is organized
ZOTIFY_ALBUM_LIBRARY = "Music/Zotify Albums"  # Directory for album downloads
ZOTIFY_PODCAST_LIBRARY = "Music/Zotify Podcasts"  # Directory for podcast downloads
ZOTIFY_PLAYLIST_LIBRARY = (
    "Music/Zotify Playlists"  # Directory for playlist downloads
)

# Zotify Output Templates - How files and folders are named
ZOTIFY_OUTPUT_ALBUM = "{album_artist}/{album}/{track_num:02d}. {artists} - {title}"  # Album track naming template
ZOTIFY_OUTPUT_PLAYLIST_TRACK = (
    "{playlist}/{artists} - {title}"  # Playlist track naming template
)
ZOTIFY_OUTPUT_PLAYLIST_EPISODE = (
    "{playlist}/{episode_number} - {title}"  # Playlist episode naming template
)
ZOTIFY_OUTPUT_PODCAST = (
    "{podcast}/{episode_number} - {title}"  # Podcast episode naming template
)
ZOTIFY_OUTPUT_SINGLE = (
    "{artists} - {title}"  # Single track naming template (not in albums)
)

# Zotify Quality and Format Settings
ZOTIFY_DOWNLOAD_QUALITY = "auto"  # Download quality: auto, normal, high, very_high
ZOTIFY_AUDIO_FORMAT = "vorbis"  # Output audio format: vorbis, mp3, flac, aac, fdk_aac, opus, wav, wavpack
ZOTIFY_ARTWORK_SIZE = "large"  # Album artwork size: small, medium, large
ZOTIFY_TRANSCODE_BITRATE = (
    -1
)  # Transcoding bitrate in kbps (-1 to use download rate)

# Zotify Download Settings
ZOTIFY_DOWNLOAD_REAL_TIME = (
    False  # Download at the same rate as track playback (slower but more stable)
)
ZOTIFY_REPLACE_EXISTING = False  # Replace existing files when downloading
ZOTIFY_SKIP_DUPLICATES = True  # Skip downloading duplicate tracks
ZOTIFY_SKIP_PREVIOUS = True  # Skip tracks that were previously downloaded

# Zotify Metadata and Files
ZOTIFY_SAVE_METADATA = True  # Save metadata tags to downloaded files
ZOTIFY_SAVE_GENRE = False  # Include genre information in metadata
ZOTIFY_ALL_ARTISTS = True  # Include all artists in metadata (not just main artist)
ZOTIFY_LYRICS_FILE = False  # Save lyrics as separate .lrc files
ZOTIFY_LYRICS_ONLY = False  # Download only lyrics without audio
ZOTIFY_SAVE_SUBTITLES = False  # Save subtitles for podcast episodes
ZOTIFY_CREATE_PLAYLIST_FILE = True  # Create .m3u playlist files for playlists

# Zotify FFmpeg Settings
ZOTIFY_FFMPEG_PATH = ""  # FFmpeg binary path or name (empty = use 'xtra', can be full path like '/usr/bin/ffmpeg' or just 'ffmpeg')
ZOTIFY_FFMPEG_ARGS = ""  # Additional FFmpeg arguments for transcoding

# Zotify Language and Locale
ZOTIFY_LANGUAGE = "en"  # Language code for metadata and interface

# Zotify Print/Logging Settings
ZOTIFY_PRINT_PROGRESS = True  # Show download progress in logs
ZOTIFY_PRINT_DOWNLOADS = False  # Print download start messages
ZOTIFY_PRINT_ERRORS = True  # Print error messages
ZOTIFY_PRINT_WARNINGS = True  # Print warning messages
ZOTIFY_PRINT_SKIPS = False  # Print skip messages for existing files

# Zotify Match Functionality
ZOTIFY_MATCH_EXISTING = False  # Match existing files for skip functionality

# YouTube Upload Settings
YOUTUBE_UPLOAD_ENABLED = False  # Enable/disable YouTube upload feature
YOUTUBE_UPLOAD_DEFAULT_PRIVACY = (
    "unlisted"  # Default privacy setting: public, unlisted, private
)
YOUTUBE_UPLOAD_DEFAULT_CATEGORY = "22"  # Default category ID (22 = People & Blogs)
YOUTUBE_UPLOAD_DEFAULT_TAGS = (
    ""  # Default tags for uploaded videos, separated by comma
)
YOUTUBE_UPLOAD_DEFAULT_DESCRIPTION = (
    "Uploaded by Aeon"  # Default description for uploaded videos
)
YOUTUBE_UPLOAD_DEFAULT_TITLE = ""  # Default title template (empty = use filename)
# Title template supports variables: {filename}, {date}, {time}, {size}
# Examples:
# "{filename} - {date}" -> "Video.mp4 - 2024-01-15"
# "My Channel - {filename}" -> "My Channel - Video.mp4"
# "" (empty) -> Uses cleaned filename as title

# Advanced YouTube API Settings
YOUTUBE_UPLOAD_DEFAULT_LANGUAGE = (
    "en"  # Default language for video metadata (ISO 639-1 code)
)
YOUTUBE_UPLOAD_DEFAULT_LICENSE = (
    "youtube"  # License: youtube (standard) or creativeCommon
)
YOUTUBE_UPLOAD_EMBEDDABLE = True  # Allow video to be embedded on other websites
YOUTUBE_UPLOAD_PUBLIC_STATS_VIEWABLE = True  # Allow public to see video statistics
YOUTUBE_UPLOAD_MADE_FOR_KIDS = (
    False  # Mark videos as made for kids (COPPA compliance)
)
YOUTUBE_UPLOAD_NOTIFY_SUBSCRIBERS = True  # Notify subscribers when video is uploaded
YOUTUBE_UPLOAD_LOCATION_DESCRIPTION = ""  # Location description for videos
YOUTUBE_UPLOAD_RECORDING_DATE = (
    ""  # Recording date (YYYY-MM-DD format, empty = upload date)
)


YOUTUBE_UPLOAD_AUTO_LEVELS = False  # Auto-enhance video levels
YOUTUBE_UPLOAD_STABILIZE = False  # Auto-stabilize shaky videos

# Media Tools Settings
MEDIA_TOOLS_ENABLED = (
    True  # Master switch to enable/disable all media tools features
)

# Watermark Settings
WATERMARK_ENABLED = False  # Master switch to enable/disable watermark feature
WATERMARK_KEY = ""  # Default watermark text to apply to videos
WATERMARK_POSITION = "none"  # Position of watermark: none, top_left, top_right, bottom_left, bottom_right, center
WATERMARK_SIZE = (
    0  # Font size for watermark text (0 = auto-size based on video dimensions)
)
WATERMARK_COLOR = "none"  # Watermark text color: none, white, black, red, green, blue, yellow, etc.
WATERMARK_FONT = "none"  # Font for watermark text: none, Arial.ttf, Roboto, etc. (supports Google Fonts)
WATERMARK_OPACITY = 0.0  # Watermark opacity: 0.0 (transparent) to 1.0 (opaque)
WATERMARK_PRIORITY = 2  # Processing priority in pipeline (lower numbers run earlier)
WATERMARK_THREADING = True  # Use multi-threading for faster watermark processing
WATERMARK_THREAD_NUMBER = 4  # Number of threads for watermark processing
WATERMARK_QUALITY = (
    "none"  # Quality setting for watermark (none = default, or specify a value)
)
WATERMARK_SPEED = (
    "none"  # Speed setting for watermark (none = default, or specify a value)
)
WATERMARK_REMOVE_ORIGINAL = (
    True  # Delete original files after successful watermarking
)

# Audio Watermark Settings
AUDIO_WATERMARK_VOLUME = (
    0.0  # Volume level for audio watermark: 0.0 (silent) to 1.0 (full volume)
)
AUDIO_WATERMARK_INTERVAL = (
    0  # Interval for audio watermarks (0 = default, or specify number of seconds)
)

# Subtitle Watermark Settings
SUBTITLE_WATERMARK_STYLE = "none"  # Style for subtitle text: none, normal, bold, italic, bold_italic, underline, strikethrough
SUBTITLE_WATERMARK_INTERVAL = (
    0  # Interval for subtitle watermarks (0 = default, or specify number of seconds)
)

# Image Watermark Settings
IMAGE_WATERMARK_ENABLED = False  # Enable/disable image watermark feature
IMAGE_WATERMARK_PATH = ""  # Path to the watermark image file
IMAGE_WATERMARK_SCALE = 10  # Scale of watermark as percentage of video width (1-100)
IMAGE_WATERMARK_OPACITY = (
    1.0  # Opacity of watermark image: 0.0 (transparent) to 1.0 (opaque)
)
IMAGE_WATERMARK_POSITION = "bottom_right"  # Position of watermark: top_left, top_right, bottom_left, bottom_right, center

# Merge Settings
MERGE_ENABLED = False  # Master switch to enable/disable merge feature
MERGE_PRIORITY = 1  # Processing priority in pipeline (lower numbers run earlier)
MERGE_THREADING = True  # Use multi-threading for faster merge processing
MERGE_THREAD_NUMBER = 4  # Number of threads for merge processing
MERGE_REMOVE_ORIGINAL = True  # Delete original files after successful merge
CONCAT_DEMUXER_ENABLED = (
    True  # Enable FFmpeg concat demuxer method (faster, requires same codecs)
)
FILTER_COMPLEX_ENABLED = (
    False  # Enable FFmpeg filter_complex method (slower but more compatible)
)

# Merge Output Formats
MERGE_OUTPUT_FORMAT_VIDEO = (
    "none"  # Output format for merged videos: none, mp4, mkv, avi, etc.
)
MERGE_OUTPUT_FORMAT_AUDIO = (
    "none"  # Output format for merged audio: none, mp3, m4a, flac, etc.
)
MERGE_OUTPUT_FORMAT_IMAGE = (
    "none"  # Output format for merged images: none, jpg, png, pdf, etc.
)
MERGE_OUTPUT_FORMAT_DOCUMENT = (
    "none"  # Output format for merged documents: none, pdf, docx, etc.
)
MERGE_OUTPUT_FORMAT_SUBTITLE = (
    "none"  # Output format for merged subtitles: none, srt, ass, etc.
)

# Merge Video Settings
MERGE_VIDEO_CODEC = (
    "none"  # Video codec for merged files: none, copy, libx264, libx265, etc.
)
MERGE_VIDEO_QUALITY = "none"  # Video quality preset: none, ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow
MERGE_VIDEO_PRESET = "none"  # Encoding preset: none, ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow
MERGE_VIDEO_CRF = "none"  # Constant Rate Factor for quality (0-51, lower is better quality): none, 18, 23, 28, etc.
MERGE_VIDEO_PIXEL_FORMAT = "none"  # Pixel format: none, yuv420p, yuv444p, etc.
MERGE_VIDEO_TUNE = "none"  # Tune option for specific content: none, film, animation, grain, stillimage, etc.
MERGE_VIDEO_FASTSTART = False  # Enable fast start for web streaming

# Merge Audio Settings
MERGE_AUDIO_CODEC = (
    "none"  # Audio codec for merged files: none, copy, aac, mp3, opus, etc.
)
MERGE_AUDIO_BITRATE = "none"  # Audio bitrate: none, 128k, 192k, 320k, etc.
MERGE_AUDIO_CHANNELS = "none"  # Number of audio channels: none, 1, 2, etc.
MERGE_AUDIO_SAMPLING = "none"  # Audio sampling rate: none, 44100, 48000, etc.
MERGE_AUDIO_VOLUME = "none"  # Volume adjustment: none, 1.0, 1.5, 0.5, etc.

# Merge Image Settings
MERGE_IMAGE_MODE = "none"  # Image merge mode: none, horizontal, vertical, grid, etc.
MERGE_IMAGE_COLUMNS = "none"  # Number of columns for grid mode: none, 2, 3, 4, etc.
MERGE_IMAGE_QUALITY = 0  # JPEG quality (0-100)
MERGE_IMAGE_DPI = "none"  # Image DPI: none, 72, 96, 300, etc.
MERGE_IMAGE_RESIZE = "none"  # Image resize dimensions: none, 1920x1080, 50%, etc.
MERGE_IMAGE_BACKGROUND = (
    "none"  # Background color for transparent images: none, white, black, etc.
)

# Merge Subtitle Settings
MERGE_SUBTITLE_ENCODING = "none"  # Character encoding: none, utf-8, utf-16, etc.
MERGE_SUBTITLE_FONT = (
    "none"  # Font for subtitles: none, Arial, Times New Roman, etc.
)
MERGE_SUBTITLE_FONT_SIZE = "none"  # Font size: none, 12, 16, etc.
MERGE_SUBTITLE_FONT_COLOR = "none"  # Font color: none, white, yellow, etc.
MERGE_SUBTITLE_BACKGROUND = (
    "none"  # Background color: none, black, transparent, etc.
)

# Merge Document Settings
MERGE_DOCUMENT_PAPER_SIZE = "none"  # Paper size: none, a4, letter, etc.
MERGE_DOCUMENT_ORIENTATION = "none"  # Page orientation: none, portrait, landscape
MERGE_DOCUMENT_MARGIN = "none"  # Page margins in mm: none, 10, 20, etc.

# Merge Metadata Settings
MERGE_METADATA_TITLE = "none"  # Title metadata for merged file
MERGE_METADATA_AUTHOR = "none"  # Author metadata for merged file
MERGE_METADATA_COMMENT = "none"  # Comment metadata for merged file

# Compression Settings
COMPRESSION_ENABLED = False  # Master switch to enable/disable compression feature
COMPRESSION_PRIORITY = (
    4  # Processing priority in pipeline (lower numbers run earlier)
)
COMPRESSION_DELETE_ORIGINAL = True  # Delete original files after successful compression (default: True, use -del flag to override)

# Video Compression Settings
COMPRESSION_VIDEO_ENABLED = False  # Enable/disable video compression
COMPRESSION_VIDEO_PRESET = "none"  # Compression preset: none, fast, medium, slow
COMPRESSION_VIDEO_CRF = "none"  # Constant Rate Factor for quality (none = use default, 0-51, lower is better quality)
COMPRESSION_VIDEO_CODEC = "none"  # Video codec: none, libx264, libx265, etc.
COMPRESSION_VIDEO_TUNE = (
    "none"  # Tune option for specific content: none, film, animation, grain, etc.
)
COMPRESSION_VIDEO_PIXEL_FORMAT = "none"  # Pixel format: none, yuv420p, yuv444p, etc.
COMPRESSION_VIDEO_FORMAT = (
    "none"  # Output format: none (use input format), mp4, mkv, avi, etc.
)
COMPRESSION_VIDEO_BITDEPTH = (
    "none"  # Video bit depth: none (use input), 8, 10, 12, etc.
)
COMPRESSION_VIDEO_BITRATE = (
    "none"  # Video bitrate: none (use input), 1M, 5M, 10M, etc.
)
COMPRESSION_VIDEO_RESOLUTION = (
    "none"  # Video resolution: none (use input), 1920x1080, 1280x720, etc.
)

# Audio Compression Settings
COMPRESSION_AUDIO_ENABLED = False  # Enable/disable audio compression
COMPRESSION_AUDIO_PRESET = "none"  # Compression preset: none, fast, medium, slow
COMPRESSION_AUDIO_CODEC = "none"  # Audio codec: none, aac, mp3, opus, etc.
COMPRESSION_AUDIO_BITRATE = "none"  # Audio bitrate: none, 128k, 192k, 320k, etc.
COMPRESSION_AUDIO_CHANNELS = (
    "none"  # Number of audio channels: none (use input), 1 (mono), 2 (stereo), etc.
)
COMPRESSION_AUDIO_FORMAT = (
    "none"  # Output format: none (use input format), mp3, m4a, flac, etc.
)
COMPRESSION_AUDIO_BITDEPTH = (
    "none"  # Audio bit depth: none (use input), 16, 24, 32, etc.
)

# Image Compression Settings
COMPRESSION_IMAGE_ENABLED = False  # Enable/disable image compression
COMPRESSION_IMAGE_PRESET = "none"  # Compression preset: none, fast, medium, slow
COMPRESSION_IMAGE_QUALITY = (
    "none"  # Image quality: none (use default), 0-100 (higher is better quality)
)
COMPRESSION_IMAGE_RESIZE = (
    "none"  # Image resize dimensions: none, 1920x1080, 50%, etc.
)
COMPRESSION_IMAGE_FORMAT = (
    "none"  # Output format: none (use input format), jpg, png, webp, etc.
)

# Document Compression Settings
COMPRESSION_DOCUMENT_ENABLED = False  # Enable/disable document compression
COMPRESSION_DOCUMENT_PRESET = "none"  # Compression preset: none, fast, medium, slow
COMPRESSION_DOCUMENT_DPI = (
    "none"  # Document DPI: none (use input), 72, 96, 300, etc.
)
COMPRESSION_DOCUMENT_FORMAT = (
    "none"  # Output format: none (use input format), pdf, docx, etc.
)

# Subtitle Compression Settings
COMPRESSION_SUBTITLE_ENABLED = False  # Enable/disable subtitle compression
COMPRESSION_SUBTITLE_PRESET = "none"  # Compression preset: none, fast, medium, slow
COMPRESSION_SUBTITLE_ENCODING = (
    "none"  # Character encoding: none, utf-8, utf-16, etc.
)
COMPRESSION_SUBTITLE_FORMAT = (
    "none"  # Output format: none (use input format), srt, ass, vtt, etc.
)

# Archive Compression Settings
COMPRESSION_ARCHIVE_ENABLED = False  # Enable/disable archive compression
COMPRESSION_ARCHIVE_PRESET = "none"  # Compression preset: none, fast, medium, slow
COMPRESSION_ARCHIVE_LEVEL = (
    "none"  # Compression level: none (use default), 0-9 (higher is more compression)
)
COMPRESSION_ARCHIVE_METHOD = "none"  # Compression method: none, deflate, lzma, etc.
COMPRESSION_ARCHIVE_FORMAT = (
    "none"  # Output format: none (use input format), zip, 7z, tar.gz, etc.
)
COMPRESSION_ARCHIVE_PASSWORD = (
    "none"  # Password for archive: none or password string
)
COMPRESSION_ARCHIVE_ALGORITHM = "none"  # Archive algorithm: none, 7z, zip, etc.

# Trim Settings
TRIM_ENABLED = False  # Master switch to enable/disable trim feature
TRIM_PRIORITY = 5  # Processing priority in pipeline (lower numbers run earlier)
TRIM_START_TIME = "00:00:00"  # Start time for trimming in HH:MM:SS format
TRIM_END_TIME = ""  # End time for trimming in HH:MM:SS format (empty = end of file)
TRIM_DELETE_ORIGINAL = False  # Delete original files after successful trimming

# Video Trim Settings
TRIM_VIDEO_ENABLED = False  # Enable/disable video trimming
TRIM_VIDEO_CODEC = (
    "none"  # Video codec: none, copy (fastest), libx264, libx265, etc.
)
TRIM_VIDEO_PRESET = (
    "none"  # Encoding preset: none, ultrafast, fast, medium, slow, etc.
)
TRIM_VIDEO_FORMAT = "none"  # Output format: none, mp4, mkv, avi, etc.

# Audio Trim Settings
TRIM_AUDIO_ENABLED = False  # Enable/disable audio trimming
TRIM_AUDIO_CODEC = "none"  # Audio codec: none, copy (fastest), aac, mp3, etc.
TRIM_AUDIO_PRESET = "none"  # Encoding preset: none, fast, medium, slow
TRIM_AUDIO_FORMAT = "none"  # Output format: none, mp3, m4a, flac, etc.

# Image Trim Settings
TRIM_IMAGE_ENABLED = False  # Enable/disable image trimming (crop)
TRIM_IMAGE_QUALITY = 90  # Image quality: 0-100 (higher is better quality)
TRIM_IMAGE_FORMAT = "none"  # Output format: none, jpg, png, webp, etc.

# Document Trim Settings
TRIM_DOCUMENT_ENABLED = False  # Enable/disable document trimming (page range)
TRIM_DOCUMENT_QUALITY = 90  # Document quality: 0-100 (higher is better quality)
TRIM_DOCUMENT_FORMAT = "none"  # Output format: none, pdf, docx, etc.

# Subtitle Trim Settings
TRIM_SUBTITLE_ENABLED = False  # Enable/disable subtitle trimming (time range)
TRIM_SUBTITLE_ENCODING = "none"  # Character encoding: none, utf-8, utf-16, etc.
TRIM_SUBTITLE_FORMAT = "none"  # Output format: none, srt, ass, vtt, etc.

# Archive Trim Settings
TRIM_ARCHIVE_ENABLED = False  # Enable/disable archive trimming (file selection)
TRIM_ARCHIVE_FORMAT = "none"  # Output format: none, zip, 7z, tar.gz, etc.

# Extract Settings
EXTRACT_ENABLED = False  # Master switch to enable/disable extract feature
EXTRACT_PRIORITY = 6  # Processing priority in pipeline (lower numbers run earlier)
EXTRACT_DELETE_ORIGINAL = True  # Delete original files after successful extraction

# Video Extract Settings
EXTRACT_VIDEO_ENABLED = False  # Enable/disable video stream extraction
EXTRACT_VIDEO_CODEC = (
    "none"  # Video codec: none, copy (fastest), libx264, libx265, etc.
)
EXTRACT_VIDEO_FORMAT = "none"  # Output format: none, mp4, mkv, avi, etc.
EXTRACT_VIDEO_INDEX = None  # Stream index to extract: None (all), 0, 1, 2, etc.
EXTRACT_VIDEO_QUALITY = "none"  # Video quality: none, high, medium, low, etc.
EXTRACT_VIDEO_PRESET = (
    "none"  # Encoding preset: none, ultrafast, fast, medium, slow, etc.
)
EXTRACT_VIDEO_BITRATE = "none"  # Video bitrate: none, 1M, 5M, etc.
EXTRACT_VIDEO_RESOLUTION = (
    "none"  # Video resolution: none, 1920x1080, 1280x720, etc.
)
EXTRACT_VIDEO_FPS = "none"  # Frame rate: none, 30, 60, etc.

# Audio Extract Settings
EXTRACT_AUDIO_ENABLED = False  # Enable/disable audio stream extraction
EXTRACT_AUDIO_CODEC = "none"  # Audio codec: none, copy (fastest), aac, mp3, etc.
EXTRACT_AUDIO_FORMAT = "none"  # Output format: none, mp3, m4a, flac, etc.
EXTRACT_AUDIO_INDEX = None  # Stream index to extract: None (all), 0, 1, 2, etc.
EXTRACT_AUDIO_BITRATE = "none"  # Audio bitrate: none, 128k, 192k, 320k, etc.
EXTRACT_AUDIO_CHANNELS = (
    "none"  # Number of audio channels: none, 1 (mono), 2 (stereo), etc.
)
EXTRACT_AUDIO_SAMPLING = "none"  # Audio sampling rate: none, 44100, 48000, etc.
EXTRACT_AUDIO_VOLUME = "none"  # Volume adjustment: none, 1.0, 1.5, 0.5, etc.

# Subtitle Extract Settings
EXTRACT_SUBTITLE_ENABLED = False  # Enable/disable subtitle stream extraction
EXTRACT_SUBTITLE_CODEC = "none"  # Subtitle codec: none, copy, mov_text, etc.
EXTRACT_SUBTITLE_FORMAT = "none"  # Output format: none, srt, ass, vtt, etc.
EXTRACT_SUBTITLE_INDEX = None  # Stream index to extract: None (all), 0, 1, 2, etc.
EXTRACT_SUBTITLE_LANGUAGE = "none"  # Language code: none, eng, spa, etc.
EXTRACT_SUBTITLE_ENCODING = "none"  # Character encoding: none, utf-8, utf-16, etc.
EXTRACT_SUBTITLE_FONT = (
    "none"  # Font for subtitles: none, Arial, Times New Roman, etc.
)
EXTRACT_SUBTITLE_FONT_SIZE = "none"  # Font size: none, 12, 16, etc.

# Attachment Extract Settings
EXTRACT_ATTACHMENT_ENABLED = False  # Enable/disable attachment extraction
EXTRACT_ATTACHMENT_FORMAT = "none"  # Output format: none, original, etc.
EXTRACT_ATTACHMENT_INDEX = (
    None  # Attachment index to extract: None (all), 0, 1, 2, etc.
)
EXTRACT_ATTACHMENT_FILTER = "none"  # Filter pattern: none, *.ttf, *.png, etc.
EXTRACT_MAINTAIN_QUALITY = True  # Maintain original quality during extraction

# Add Settings
ADD_ENABLED = False  # Master switch to enable/disable add feature
ADD_PRIORITY = 7  # Processing priority in pipeline (lower numbers run earlier)
ADD_DELETE_ORIGINAL = True  # Delete original files after successful add operation
ADD_PRESERVE_TRACKS = False  # Preserve existing tracks when adding new ones
ADD_REPLACE_TRACKS = False  # Replace existing tracks with new ones at the same index

# Video Add Settings
ADD_VIDEO_ENABLED = False  # Enable/disable video track addition
# ADD_VIDEO_PATH has been removed
ADD_VIDEO_INDEX = None  # Stream index to add: None (all), 0, 1, 2, etc.
ADD_VIDEO_CODEC = "copy"  # Video codec: copy (fastest), libx264, libx265, etc.
ADD_VIDEO_QUALITY = "none"  # Video quality: none, high, medium, low, etc.
ADD_VIDEO_PRESET = (
    "none"  # Encoding preset: none, ultrafast, fast, medium, slow, etc.
)
ADD_VIDEO_BITRATE = "none"  # Video bitrate: none, 1M, 5M, etc.
ADD_VIDEO_RESOLUTION = "none"  # Video resolution: none, 1920x1080, 1280x720, etc.
ADD_VIDEO_FPS = "none"  # Frame rate: none, 30, 60, etc.

# Audio Add Settings
ADD_AUDIO_ENABLED = False  # Enable/disable audio track addition
# ADD_AUDIO_PATH has been removed
ADD_AUDIO_INDEX = None  # Stream index to add: None (all), 0, 1, 2, etc.
ADD_AUDIO_CODEC = "copy"  # Audio codec: copy (fastest), aac, mp3, etc.
ADD_AUDIO_BITRATE = "none"  # Audio bitrate: none, 128k, 192k, 320k, etc.
ADD_AUDIO_CHANNELS = (
    "none"  # Number of audio channels: none, 1 (mono), 2 (stereo), etc.
)
ADD_AUDIO_SAMPLING = "none"  # Audio sampling rate: none, 44100, 48000, etc.
ADD_AUDIO_VOLUME = "none"  # Volume adjustment: none, 1.0, 1.5, 0.5, etc.

# Subtitle Add Settings
ADD_SUBTITLE_ENABLED = False  # Enable/disable subtitle track addition
# ADD_SUBTITLE_PATH has been removed
ADD_SUBTITLE_INDEX = None  # Stream index to add: None (all), 0, 1, 2, etc.
ADD_SUBTITLE_CODEC = "copy"  # Subtitle codec: copy, mov_text, etc.
ADD_SUBTITLE_LANGUAGE = "none"  # Language code: none, eng, spa, etc.
ADD_SUBTITLE_ENCODING = "none"  # Character encoding: none, utf-8, utf-16, etc.
ADD_SUBTITLE_FONT = "none"  # Font for subtitles: none, Arial, Times New Roman, etc.
ADD_SUBTITLE_FONT_SIZE = "none"  # Font size: none, 12, 16, etc.

# Attachment Add Settings
ADD_ATTACHMENT_ENABLED = False  # Enable/disable attachment addition
# ADD_ATTACHMENT_PATH has been removed
ADD_ATTACHMENT_INDEX = None  # Attachment index to add: None (all), 0, 1, 2, etc.
ADD_ATTACHMENT_MIMETYPE = "none"  # MIME type: none, font/ttf, image/png, etc.

# Convert Settings
CONVERT_ENABLED = False  # Master switch to enable/disable convert feature
CONVERT_PRIORITY = 3  # Processing priority in pipeline (lower numbers run earlier)
CONVERT_DELETE_ORIGINAL = True  # Delete original files after successful conversion (default: True, use -del flag to override)

# Video Convert Settings
CONVERT_VIDEO_ENABLED = False  # Enable/disable video conversion
CONVERT_VIDEO_FORMAT = "none"  # Target format: none, mp4, mkv, avi, webm, etc.
CONVERT_VIDEO_CODEC = "none"  # Video codec: none, libx264, libx265, vp9, etc.
CONVERT_VIDEO_QUALITY = "none"  # Video quality preset: none, high, medium, low
CONVERT_VIDEO_CRF = 0  # Constant Rate Factor (0-51, lower is better quality)
CONVERT_VIDEO_PRESET = (
    "none"  # Encoding preset: none, ultrafast, fast, medium, slow, etc.
)
CONVERT_VIDEO_MAINTAIN_QUALITY = True  # Maintain original quality during conversion
CONVERT_VIDEO_RESOLUTION = (
    "none"  # Target resolution: none, 1920x1080, 1280x720, etc.
)
CONVERT_VIDEO_FPS = "none"  # Target frame rate: none, 30, 60, etc.

# Audio Convert Settings
CONVERT_AUDIO_ENABLED = False  # Enable/disable audio conversion
CONVERT_AUDIO_FORMAT = "none"  # Target format: none, mp3, m4a, flac, ogg, etc.
CONVERT_AUDIO_CODEC = "none"  # Audio codec: none, aac, mp3, opus, flac, etc.
CONVERT_AUDIO_BITRATE = "none"  # Target bitrate: none, 128k, 192k, 320k, etc.
CONVERT_AUDIO_CHANNELS = (
    0  # Target channels: 0 (original), 1 (mono), 2 (stereo), etc.
)
CONVERT_AUDIO_SAMPLING = 0  # Target sampling rate: 0 (original), 44100, 48000, etc.
CONVERT_AUDIO_VOLUME = 0.0  # Volume adjustment: 0.0 (original), 1.0, 1.5, 0.5, etc.

# Subtitle Convert Settings
CONVERT_SUBTITLE_ENABLED = False  # Enable/disable subtitle conversion
CONVERT_SUBTITLE_FORMAT = "none"  # Target format: none, srt, ass, vtt, etc.
CONVERT_SUBTITLE_ENCODING = "none"  # Target encoding: none, utf-8, utf-16, etc.
CONVERT_SUBTITLE_LANGUAGE = "none"  # Target language code: none, eng, spa, etc.

# Document Convert Settings
CONVERT_DOCUMENT_ENABLED = False  # Enable/disable document conversion
CONVERT_DOCUMENT_FORMAT = "none"  # Target format: none, pdf, docx, txt, etc.
CONVERT_DOCUMENT_QUALITY = 0  # Document quality (0-100, higher is better)
CONVERT_DOCUMENT_DPI = 0  # Document DPI: 0 (original), 72, 96, 300, etc.

# Archive Convert Settings
CONVERT_ARCHIVE_ENABLED = False  # Enable/disable archive conversion
CONVERT_ARCHIVE_FORMAT = "none"  # Target format: none, zip, 7z, tar.gz, etc.
CONVERT_ARCHIVE_LEVEL = 0  # Compression level (0-9, higher is more compression)
CONVERT_ARCHIVE_METHOD = "none"  # Compression method: none, deflate, lzma, etc.

# Metadata Settings
METADATA_KEY = ""  # Legacy metadata key
METADATA_ALL = ""  # Global metadata template for all media types
METADATA_TITLE = ""  # Default title metadata for all media types
METADATA_AUTHOR = ""  # Default author metadata for all media types
METADATA_COMMENT = ""  # Default comment metadata for all media types
METADATA_VIDEO_TITLE = ""  # Default title metadata specifically for video files
METADATA_VIDEO_AUTHOR = ""  # Default author metadata specifically for video files
METADATA_VIDEO_COMMENT = ""  # Default comment metadata specifically for video files
METADATA_AUDIO_TITLE = ""  # Default title metadata specifically for audio files
METADATA_AUDIO_AUTHOR = ""  # Default author metadata specifically for audio files
METADATA_AUDIO_COMMENT = ""  # Default comment metadata specifically for audio files
METADATA_SUBTITLE_TITLE = (
    ""  # Default title metadata specifically for subtitle files
)
METADATA_SUBTITLE_AUTHOR = (
    ""  # Default author metadata specifically for subtitle files
)
METADATA_SUBTITLE_COMMENT = (
    ""  # Default comment metadata specifically for subtitle files
)
