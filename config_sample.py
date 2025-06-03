# REQUIRED CONFIG
BOT_TOKEN = ""  # Get this from @BotFather
OWNER_ID = 0  # Your Telegram User ID (not username) as an integer
TELEGRAM_API = 0  # Get this from my.telegram.org
TELEGRAM_HASH = ""  # Get this from my.telegram.org

# Optional: Strongly recommended for bot settings and user preferences persistence
DATABASE_URL = None  # MongoDB URI (set to a valid URI if using database features)

# USER_SESSION_STRING was removed as the user client functionality is disabled.

# Command Suffix (optional, if you run multiple bots or want to version commands)
CMD_SUFFIX = ""

# Bot Behavior
AUTHORIZED_CHATS = ""  # Space separated list of chat IDs where the bot can be used by anyone. Leave empty for public.
SUDO_USERS = ""       # Space separated list of user IDs who can use sudo commands. OWNER_ID is always a sudo user.
LOG_CHAT_ID = 0       # Chat ID where bot logs (e.g., from /log command) will be sent. Can be a group ID.

# Streamrip Settings
STREAMRIP_ENABLED = True  # Master switch for all streamrip functionality. Must be True.

# --- Streamrip Authentication (Essential for downloading from respective services) ---
# It's highly recommended to configure these in your actual config file (e.g., config.env)
# or environment variables, NOT directly in this sample.
# Streamrip also uses its own config file (typically streamrip_config.toml or similar in ~/.config/streamrip/)
# which it might generate or expect. These ENV vars can help populate that, or streamrip library might read them.

# Qobuz
STREAMRIP_QOBUZ_EMAIL = ""
STREAMRIP_QOBUZ_PASSWORD = ""
# Optional: STREAMRIP_QOBUZ_APP_ID = "" (Usually handled by streamrip library)
# Optional: STREAMRIP_QOBUZ_SECRETS = []

# Tidal (OAuth tokens are preferred and usually obtained via interactive login with streamrip CLI)
# The bot might not be able to perform the interactive login.
# Setting email/password here might work for some streamrip versions/setups, or it might expect tokens.
STREAMRIP_TIDAL_EMAIL = ""
STREAMRIP_TIDAL_PASSWORD = ""
STREAMRIP_TIDAL_ACCESS_TOKEN = "" # If you have obtained a token
STREAMRIP_TIDAL_REFRESH_TOKEN = ""
STREAMRIP_TIDAL_USER_ID = ""
STREAMRIP_TIDAL_COUNTRY_CODE = "" # e.g., US
STREAMRIP_TIDAL_TOKEN_EXPIRY = ""

# Deezer
STREAMRIP_DEEZER_ARL = ""  # Your Deezer ARL cookie. Essential for Deezer.

# SoundCloud (Often works without auth for public tracks, Client ID can help)
STREAMRIP_SOUNDCLOUD_CLIENT_ID = "" # Optional

# --- Streamrip Download Options ---
STREAMRIP_DEFAULT_QUALITY = 3  # Default quality (0-4: 0=128k, 1=320k, 2=CD, 3=Hi-Res, 4=Hi-Res+)
STREAMRIP_DEFAULT_CODEC = "flac"  # Default output format/codec
STREAMRIP_SUPPORTED_CODECS = ["flac", "mp3", "m4a", "ogg", "opus"] # Formats user can request via -c flag
STREAMRIP_LIMIT = 0  # Max download size in GB for streamrip tasks (0 = unlimited)
