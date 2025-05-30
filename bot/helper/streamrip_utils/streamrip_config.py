from pathlib import Path

from bot import DOWNLOAD_DIR, LOGGER
from bot.core.config_manager import Config
from bot.helper.ext_utils.db_handler import database

try:
    from streamrip.config import Config as StreamripConfig

    STREAMRIP_AVAILABLE = True
except ImportError:
    STREAMRIP_AVAILABLE = False
    LOGGER.warning("Streamrip not installed. Streamrip features will be disabled.")


class StreamripConfigHelper:
    """Helper for streamrip configuration management"""

    def __init__(self):
        self.config: StreamripConfig | None = None
        self.config_path: Path | None = None
        self._initialized = False

    async def initialize(self) -> bool:
        """Initialize streamrip configuration"""
        if not STREAMRIP_AVAILABLE:
            LOGGER.error("Streamrip is not available")
            return False

        try:
            # Use temporary config location
            self.config_path = Path.home() / ".config" / "streamrip" / "config.toml"

            # Create config directory if it doesn't exist
            self.config_path.parent.mkdir(parents=True, exist_ok=True)

            # Try to load custom config from database first
            custom_config = await self._load_config_from_db()

            if custom_config:
                # Save custom config to file and load it
                from aiofiles import open as aiopen

                async with aiopen(self.config_path, "w") as f:
                    await f.write(custom_config)
                self.config = StreamripConfig.from_file(str(self.config_path))
                LOGGER.info("Loaded custom streamrip config from database")
            else:
                # Create default config using proper API
                try:
                    # Try the newer API first
                    self.config = StreamripConfig()
                    LOGGER.info(
                        "Created default streamrip config using StreamripConfig()"
                    )
                except Exception:
                    try:
                        # Try alternative initialization
                        self.config = StreamripConfig.defaults()
                        LOGGER.info(
                            "Created default streamrip config using defaults()"
                        )
                    except Exception:
                        # Fallback: create config file manually and load it
                        await self._create_default_config_file()
                        self.config = StreamripConfig.from_file(
                            str(self.config_path)
                        )

            # Always apply bot settings to override any config values
            await self._apply_bot_settings()
            await self.save_config()

            self._initialized = True
            return True

        except Exception as e:
            LOGGER.error(f"Failed to initialize streamrip config: {e}")
            LOGGER.warning("Streamrip will be disabled due to configuration errors")
            # Disable streamrip if initialization fails
            Config.STREAMRIP_ENABLED = False
            self._initialized = False
            self.config = None
            return False

    async def _create_default_config_file(self):
        """Create a default streamrip config file manually"""
        default_config = """
[session]
[session.downloads]
folder = "/tmp/downloads"
concurrency = 4

[session.qobuz]
quality = 3
email_or_userid = ""
password_or_token = ""
use_auth_token = false

[session.tidal]
quality = 3
username = ""
password = ""
user_id = ""
country_code = ""
access_token = ""
refresh_token = ""
token_expiry = ""

[session.deezer]
quality = 2
arl = ""

[session.soundcloud]
quality = 1

[session.youtube]
quality = 0

[session.conversion]
enabled = false
codec = "flac"

[session.database]
downloads_enabled = true
failed_downloads_enabled = true
downloads_path = "~/.config/streamrip/streamrip_downloads.db"
failed_downloads_path = "~/.config/streamrip/streamrip_failed.db"

[session.filepaths]
track_format = "{artist} - {title}"
folder_format = "{artist} - {album}"

[session.artwork]
embed = true
save_artwork = false
embed_size = 1200
saved_max_width = 1200

[session.metadata]
exclude = []
set_playlist_to_album = true
renumber_playlist_tracks = true

[session.misc]
max_search_results = 20
"""

        try:
            from aiofiles import open as aiopen

            async with aiopen(self.config_path, "w") as f:
                await f.write(default_config.strip())
            LOGGER.info(f"Created default config file at {self.config_path}")
        except Exception as e:
            LOGGER.error(f"Failed to create default config file: {e}")
            raise

    async def _apply_bot_settings(self):
        """Apply bot configuration settings to streamrip config"""
        if not self.config:
            return

        try:
            # Download settings - use DOWNLOAD_DIR
            if hasattr(self.config, "session") and hasattr(
                self.config.session, "downloads"
            ):
                self.config.session.downloads.folder = DOWNLOAD_DIR

            # Platform-specific quality settings
            if hasattr(self.config, "session"):
                if hasattr(self.config.session, "qobuz"):
                    qobuz_quality = (
                        Config.STREAMRIP_QOBUZ_QUALITY
                        or Config.STREAMRIP_DEFAULT_QUALITY
                        or 3
                    )
                    self.config.session.qobuz.quality = qobuz_quality

                if hasattr(self.config.session, "tidal"):
                    tidal_quality = (
                        Config.STREAMRIP_TIDAL_QUALITY
                        or Config.STREAMRIP_DEFAULT_QUALITY
                        or 3
                    )
                    self.config.session.tidal.quality = tidal_quality

                if hasattr(self.config.session, "deezer"):
                    deezer_quality = (
                        Config.STREAMRIP_DEEZER_QUALITY
                        or Config.STREAMRIP_DEFAULT_QUALITY
                        or 2
                    )
                    # Deezer max is 2, so cap it
                    deezer_quality = min(deezer_quality, 2)
                    self.config.session.deezer.quality = deezer_quality

                if hasattr(self.config.session, "soundcloud"):
                    soundcloud_quality = Config.STREAMRIP_SOUNDCLOUD_QUALITY or 0
                    # SoundCloud max is 1, so cap it
                    soundcloud_quality = min(soundcloud_quality, 1)
                    self.config.session.soundcloud.quality = soundcloud_quality

                if hasattr(self.config.session, "youtube"):
                    youtube_quality = Config.STREAMRIP_YOUTUBE_QUALITY or 0
                    self.config.session.youtube.quality = youtube_quality

            # Codec settings
            codec = Config.STREAMRIP_DEFAULT_CODEC
            if hasattr(self.config, "session") and hasattr(
                self.config.session, "conversion"
            ):
                self.config.session.conversion.enabled = (
                    Config.STREAMRIP_AUTO_CONVERT
                )
                self.config.session.conversion.codec = codec

            # Concurrent downloads
            concurrent = Config.STREAMRIP_CONCURRENT_DOWNLOADS
            if (
                hasattr(self.config, "session")
                and hasattr(self.config.session, "downloads")
                and hasattr(self.config.session.downloads, "concurrency")
            ):
                self.config.session.downloads.concurrency = concurrent

            # Database settings - use default streamrip location
            # Streamrip will use its own database for download tracking
            db_dir = Path.home() / ".config" / "streamrip"
            db_dir.mkdir(parents=True, exist_ok=True)

            if hasattr(self.config, "session") and hasattr(
                self.config.session, "database"
            ):
                self.config.session.database.downloads_path = str(
                    db_dir / "streamrip_downloads.db"
                )
                self.config.session.database.failed_downloads_path = str(
                    db_dir / "streamrip_failed.db"
                )

            # Authentication settings
            await self._apply_auth_settings()

            # Metadata settings
            if hasattr(self.config, "session") and hasattr(
                self.config.session, "metadata"
            ):
                # Set metadata exclusions
                if Config.STREAMRIP_METADATA_EXCLUDE:
                    self.config.session.metadata.exclude = (
                        Config.STREAMRIP_METADATA_EXCLUDE
                    )

                # Set playlist to album conversion
                if hasattr(self.config.session.metadata, "set_playlist_to_album"):
                    self.config.session.metadata.set_playlist_to_album = (
                        Config.STREAMRIP_METADATA_SET_PLAYLIST_TO_ALBUM
                    )

                # Set playlist track renumbering
                if hasattr(self.config.session.metadata, "renumber_playlist_tracks"):
                    self.config.session.metadata.renumber_playlist_tracks = (
                        Config.STREAMRIP_METADATA_RENUMBER_PLAYLIST_TRACKS
                    )

            # Cover art settings
            if hasattr(self.config, "session") and hasattr(
                self.config.session, "artwork"
            ):
                self.config.session.artwork.embed = Config.STREAMRIP_EMBED_COVER_ART
                self.config.session.artwork.save_artwork = (
                    Config.STREAMRIP_SAVE_COVER_ART
                )

                # Map cover art size to appropriate streamrip attributes
                if hasattr(self.config.session.artwork, "embed_size"):
                    # Convert size string to appropriate value for embed_size
                    size_mapping = {
                        "small": 300,
                        "medium": 600,
                        "large": 1200,
                        "original": 0,  # 0 means original size
                    }
                    embed_size = size_mapping.get(
                        Config.STREAMRIP_COVER_ART_SIZE.lower(), 1200
                    )
                    self.config.session.artwork.embed_size = embed_size

                if hasattr(self.config.session.artwork, "saved_max_width"):
                    # Set saved artwork max width based on size preference
                    size_mapping = {
                        "small": 300,
                        "medium": 600,
                        "large": 1200,
                        "original": 0,  # 0 means original size
                    }
                    saved_width = size_mapping.get(
                        Config.STREAMRIP_COVER_ART_SIZE.lower(), 1200
                    )
                    self.config.session.artwork.saved_max_width = saved_width

            # Qobuz filters
            if (
                hasattr(self.config, "session")
                and hasattr(self.config.session, "qobuz")
                and hasattr(self.config.session.qobuz, "filters")
            ):
                # Apply Qobuz filters if they exist
                if hasattr(self.config.session.qobuz.filters, "extras"):
                    self.config.session.qobuz.filters.extras = (
                        Config.STREAMRIP_QOBUZ_FILTERS_EXTRAS
                    )
                if hasattr(self.config.session.qobuz.filters, "repeats"):
                    self.config.session.qobuz.filters.repeats = (
                        Config.STREAMRIP_QOBUZ_FILTERS_REPEATS
                    )
                if hasattr(self.config.session.qobuz.filters, "non_albums"):
                    self.config.session.qobuz.filters.non_albums = (
                        Config.STREAMRIP_QOBUZ_FILTERS_NON_ALBUMS
                    )
                if hasattr(self.config.session.qobuz.filters, "features"):
                    self.config.session.qobuz.filters.features = (
                        Config.STREAMRIP_QOBUZ_FILTERS_FEATURES
                    )
                if hasattr(self.config.session.qobuz.filters, "non_studio_albums"):
                    self.config.session.qobuz.filters.non_studio_albums = (
                        Config.STREAMRIP_QOBUZ_FILTERS_NON_STUDIO_ALBUMS
                    )
                if hasattr(self.config.session.qobuz.filters, "non_remaster"):
                    self.config.session.qobuz.filters.non_remaster = (
                        Config.STREAMRIP_QOBUZ_FILTERS_NON_REMASTER
                    )

            # Additional advanced settings
            await self._apply_advanced_settings()

            # Streamlined config application without verbose logging

        except Exception as e:
            LOGGER.error(f"Error applying bot settings to streamrip config: {e}")

    async def _apply_auth_settings(self):
        """Apply authentication settings from bot config"""
        try:
            # Streamlined credential loading without verbose logging

            # Qobuz authentication
            if (
                Config.STREAMRIP_QOBUZ_EMAIL
                and Config.STREAMRIP_QOBUZ_PASSWORD
                and hasattr(self.config, "session")
                and hasattr(self.config.session, "qobuz")
            ):
                self.config.session.qobuz.email_or_userid = (
                    Config.STREAMRIP_QOBUZ_EMAIL
                )
                self.config.session.qobuz.password_or_token = (
                    Config.STREAMRIP_QOBUZ_PASSWORD
                )
                if hasattr(self.config.session.qobuz, "use_auth_token"):
                    self.config.session.qobuz.use_auth_token = (
                        Config.STREAMRIP_QOBUZ_USE_AUTH_TOKEN
                    )
                if Config.STREAMRIP_QOBUZ_APP_ID:
                    self.config.session.qobuz.app_id = Config.STREAMRIP_QOBUZ_APP_ID
                if Config.STREAMRIP_QOBUZ_SECRETS:
                    self.config.session.qobuz.secrets = (
                        Config.STREAMRIP_QOBUZ_SECRETS
                    )
                if hasattr(self.config.session.qobuz, "download_booklets"):
                    self.config.session.qobuz.download_booklets = (
                        Config.STREAMRIP_QOBUZ_DOWNLOAD_BOOKLETS
                    )

            # Tidal authentication
            if hasattr(self.config, "session") and hasattr(
                self.config.session, "tidal"
            ):
                if not hasattr(self.config.session.tidal, "token_expiry"):
                    self.config.session.tidal.token_expiry = None

                if (
                    Config.STREAMRIP_TIDAL_ACCESS_TOKEN
                    and Config.STREAMRIP_TIDAL_REFRESH_TOKEN
                ):
                    self.config.session.tidal.access_token = (
                        Config.STREAMRIP_TIDAL_ACCESS_TOKEN
                    )
                    self.config.session.tidal.refresh_token = (
                        Config.STREAMRIP_TIDAL_REFRESH_TOKEN
                    )
                    if Config.STREAMRIP_TIDAL_USER_ID:
                        self.config.session.tidal.user_id = int(
                            str(Config.STREAMRIP_TIDAL_USER_ID).strip()
                        )
                    if Config.STREAMRIP_TIDAL_COUNTRY_CODE:
                        self.config.session.tidal.country_code = (
                            str(Config.STREAMRIP_TIDAL_COUNTRY_CODE).strip().upper()
                        )
                    else:
                        self.config.session.tidal.country_code = "US"
                    if Config.STREAMRIP_TIDAL_TOKEN_EXPIRY:
                        self.config.session.tidal.token_expiry = float(
                            str(Config.STREAMRIP_TIDAL_TOKEN_EXPIRY).strip()
                        )
                    else:
                        self.config.session.tidal.token_expiry = 1748842786.0
                    if hasattr(self.config.session.tidal, "download_videos"):
                        self.config.session.tidal.download_videos = (
                            Config.STREAMRIP_TIDAL_DOWNLOAD_VIDEOS
                        )
                # Removed username/password fallback - streamrip only supports token authentication for Tidal

            # Deezer authentication
            if (
                Config.STREAMRIP_DEEZER_ARL
                and hasattr(self.config, "session")
                and hasattr(self.config.session, "deezer")
            ):
                self.config.session.deezer.arl = Config.STREAMRIP_DEEZER_ARL
                if hasattr(self.config.session.deezer, "use_deezloader"):
                    self.config.session.deezer.use_deezloader = (
                        Config.STREAMRIP_DEEZER_USE_DEEZLOADER
                    )
                if hasattr(self.config.session.deezer, "deezloader_warnings"):
                    self.config.session.deezer.deezloader_warnings = (
                        Config.STREAMRIP_DEEZER_DEEZLOADER_WARNINGS
                    )

            # SoundCloud authentication
            if hasattr(self.config, "session") and hasattr(
                self.config.session, "soundcloud"
            ):
                if Config.STREAMRIP_SOUNDCLOUD_CLIENT_ID and hasattr(
                    self.config.session.soundcloud, "client_id"
                ):
                    self.config.session.soundcloud.client_id = (
                        Config.STREAMRIP_SOUNDCLOUD_CLIENT_ID
                    )
                if (
                    hasattr(Config, "STREAMRIP_SOUNDCLOUD_APP_VERSION")
                    and Config.STREAMRIP_SOUNDCLOUD_APP_VERSION
                    and hasattr(self.config.session.soundcloud, "app_version")
                ):
                    self.config.session.soundcloud.app_version = (
                        Config.STREAMRIP_SOUNDCLOUD_APP_VERSION
                    )

            # Last.fm configuration
            if hasattr(self.config, "session") and hasattr(
                self.config.session, "lastfm"
            ):
                if hasattr(self.config.session.lastfm, "source"):
                    primary_source = (
                        "qobuz"
                        if Config.STREAMRIP_QOBUZ_ENABLED
                        else "tidal"
                        if Config.STREAMRIP_TIDAL_ENABLED
                        else "deezer"
                    )
                    self.config.session.lastfm.source = primary_source
                if hasattr(self.config.session.lastfm, "fallback_source"):
                    fallback_source = (
                        "soundcloud" if Config.STREAMRIP_SOUNDCLOUD_ENABLED else ""
                    )
                    self.config.session.lastfm.fallback_source = fallback_source

        except Exception as e:
            LOGGER.error(f"Error applying auth settings: {e}")

    async def _apply_advanced_settings(self):
        """Apply comprehensive advanced settings from bot config"""
        try:
            # Filepaths settings
            if hasattr(self.config, "session") and hasattr(
                self.config.session, "filepaths"
            ):
                if Config.STREAMRIP_FILENAME_TEMPLATE:
                    self.config.session.filepaths.track_format = (
                        Config.STREAMRIP_FILENAME_TEMPLATE
                    )
                elif hasattr(Config, "STREAMRIP_FILEPATHS_TRACK_FORMAT"):
                    self.config.session.filepaths.track_format = (
                        Config.STREAMRIP_FILEPATHS_TRACK_FORMAT
                    )

                if Config.STREAMRIP_FOLDER_TEMPLATE:
                    self.config.session.filepaths.folder_format = (
                        Config.STREAMRIP_FOLDER_TEMPLATE
                    )
                elif hasattr(Config, "STREAMRIP_FILEPATHS_FOLDER_FORMAT"):
                    self.config.session.filepaths.folder_format = (
                        Config.STREAMRIP_FILEPATHS_FOLDER_FORMAT
                    )

                if hasattr(self.config.session.filepaths, "add_singles_to_folder"):
                    self.config.session.filepaths.add_singles_to_folder = getattr(
                        Config, "STREAMRIP_FILEPATHS_ADD_SINGLES_TO_FOLDER", False
                    )
                if hasattr(self.config.session.filepaths, "restrict_characters"):
                    self.config.session.filepaths.restrict_characters = getattr(
                        Config, "STREAMRIP_FILEPATHS_RESTRICT_CHARACTERS", False
                    )
                if hasattr(self.config.session.filepaths, "truncate_to"):
                    self.config.session.filepaths.truncate_to = getattr(
                        Config, "STREAMRIP_FILEPATHS_TRUNCATE_TO", 120
                    )

            # Downloads settings
            if hasattr(self.config, "session") and hasattr(
                self.config.session, "downloads"
            ):
                if hasattr(self.config.session.downloads, "folder"):
                    self.config.session.downloads.folder = str(DOWNLOAD_DIR)
                if hasattr(self.config.session.downloads, "concurrency"):
                    self.config.session.downloads.concurrency = (
                        Config.STREAMRIP_CONCURRENT_DOWNLOADS > 1
                    )
                if hasattr(self.config.session.downloads, "max_connections"):
                    self.config.session.downloads.max_connections = getattr(
                        Config, "STREAMRIP_MAX_CONNECTIONS", 6
                    )
                if hasattr(self.config.session.downloads, "requests_per_minute"):
                    self.config.session.downloads.requests_per_minute = getattr(
                        Config, "STREAMRIP_REQUESTS_PER_MINUTE", 60
                    )
                if hasattr(self.config.session.downloads, "source_subdirectories"):
                    self.config.session.downloads.source_subdirectories = getattr(
                        Config, "STREAMRIP_SOURCE_SUBDIRECTORIES", False
                    )
                if hasattr(self.config.session.downloads, "disc_subdirectories"):
                    self.config.session.downloads.disc_subdirectories = getattr(
                        Config, "STREAMRIP_DISC_SUBDIRECTORIES", True
                    )
                if hasattr(self.config.session.downloads, "verify_ssl"):
                    self.config.session.downloads.verify_ssl = getattr(
                        Config, "STREAMRIP_VERIFY_SSL", True
                    )

            # Database settings
            if hasattr(self.config, "session") and hasattr(
                self.config.session, "database"
            ):
                if hasattr(self.config.session.database, "downloads_enabled"):
                    self.config.session.database.downloads_enabled = getattr(
                        Config, "STREAMRIP_DATABASE_DOWNLOADS_ENABLED", True
                    )
                if hasattr(self.config.session.database, "downloads_path"):
                    self.config.session.database.downloads_path = getattr(
                        Config, "STREAMRIP_DATABASE_DOWNLOADS_PATH", "./downloads.db"
                    )
                if hasattr(self.config.session.database, "failed_downloads_enabled"):
                    self.config.session.database.failed_downloads_enabled = getattr(
                        Config, "STREAMRIP_DATABASE_FAILED_DOWNLOADS_ENABLED", True
                    )
                if hasattr(self.config.session.database, "failed_downloads_path"):
                    self.config.session.database.failed_downloads_path = getattr(
                        Config,
                        "STREAMRIP_DATABASE_FAILED_DOWNLOADS_PATH",
                        "./failed_downloads.db",
                    )

            # Conversion settings
            if hasattr(self.config, "session") and hasattr(
                self.config.session, "conversion"
            ):
                if hasattr(self.config.session.conversion, "enabled"):
                    self.config.session.conversion.enabled = getattr(
                        Config, "STREAMRIP_CONVERSION_ENABLED", False
                    )
                if hasattr(self.config.session.conversion, "codec"):
                    self.config.session.conversion.codec = getattr(
                        Config, "STREAMRIP_CONVERSION_CODEC", "ALAC"
                    )
                if hasattr(self.config.session.conversion, "sampling_rate"):
                    self.config.session.conversion.sampling_rate = getattr(
                        Config, "STREAMRIP_CONVERSION_SAMPLING_RATE", 48000
                    )
                if hasattr(self.config.session.conversion, "bit_depth"):
                    self.config.session.conversion.bit_depth = getattr(
                        Config, "STREAMRIP_CONVERSION_BIT_DEPTH", 24
                    )
                if hasattr(self.config.session.conversion, "lossy_bitrate"):
                    self.config.session.conversion.lossy_bitrate = getattr(
                        Config, "STREAMRIP_CONVERSION_LOSSY_BITRATE", 320
                    )

            # Metadata settings
            if hasattr(self.config, "session") and hasattr(
                self.config.session, "metadata"
            ):
                if hasattr(self.config.session.metadata, "set_playlist_to_album"):
                    self.config.session.metadata.set_playlist_to_album = getattr(
                        Config, "STREAMRIP_METADATA_SET_PLAYLIST_TO_ALBUM", True
                    )
                if hasattr(self.config.session.metadata, "renumber_playlist_tracks"):
                    self.config.session.metadata.renumber_playlist_tracks = getattr(
                        Config, "STREAMRIP_METADATA_RENUMBER_PLAYLIST_TRACKS", True
                    )
                if hasattr(self.config.session.metadata, "exclude"):
                    self.config.session.metadata.exclude = getattr(
                        Config, "STREAMRIP_METADATA_EXCLUDE", []
                    )

            # Artwork settings
            if hasattr(self.config, "session") and hasattr(
                self.config.session, "artwork"
            ):
                if hasattr(self.config.session.artwork, "embed"):
                    self.config.session.artwork.embed = getattr(
                        Config, "STREAMRIP_EMBED_COVER_ART", True
                    )
                if hasattr(self.config.session.artwork, "save_artwork"):
                    self.config.session.artwork.save_artwork = getattr(
                        Config, "STREAMRIP_SAVE_COVER_ART", True
                    )
                if hasattr(self.config.session.artwork, "embed_max_width"):
                    self.config.session.artwork.embed_max_width = getattr(
                        Config, "STREAMRIP_ARTWORK_EMBED_MAX_WIDTH", -1
                    )
                if hasattr(self.config.session.artwork, "saved_max_width"):
                    self.config.session.artwork.saved_max_width = getattr(
                        Config, "STREAMRIP_ARTWORK_SAVED_MAX_WIDTH", -1
                    )

            # Qobuz filters
            if (
                hasattr(self.config, "session")
                and hasattr(self.config.session, "qobuz")
                and hasattr(self.config.session.qobuz, "filters")
            ):
                if hasattr(self.config.session.qobuz.filters, "extras"):
                    self.config.session.qobuz.filters.extras = getattr(
                        Config, "STREAMRIP_QOBUZ_FILTERS_EXTRAS", False
                    )
                if hasattr(self.config.session.qobuz.filters, "repeats"):
                    self.config.session.qobuz.filters.repeats = getattr(
                        Config, "STREAMRIP_QOBUZ_FILTERS_REPEATS", False
                    )
                if hasattr(self.config.session.qobuz.filters, "non_albums"):
                    self.config.session.qobuz.filters.non_albums = getattr(
                        Config, "STREAMRIP_QOBUZ_FILTERS_NON_ALBUMS", False
                    )
                if hasattr(self.config.session.qobuz.filters, "features"):
                    self.config.session.qobuz.filters.features = getattr(
                        Config, "STREAMRIP_QOBUZ_FILTERS_FEATURES", False
                    )
                if hasattr(self.config.session.qobuz.filters, "non_studio_albums"):
                    self.config.session.qobuz.filters.non_studio_albums = getattr(
                        Config, "STREAMRIP_QOBUZ_FILTERS_NON_STUDIO_ALBUMS", False
                    )
                if hasattr(self.config.session.qobuz.filters, "non_remaster"):
                    self.config.session.qobuz.filters.non_remaster = getattr(
                        Config, "STREAMRIP_QOBUZ_FILTERS_NON_REMASTER", False
                    )

            # Last.fm settings
            if hasattr(self.config, "session") and hasattr(
                self.config.session, "lastfm"
            ):
                if hasattr(self.config.session.lastfm, "source"):
                    self.config.session.lastfm.source = getattr(
                        Config, "STREAMRIP_LASTFM_SOURCE", "qobuz"
                    )
                if hasattr(self.config.session.lastfm, "fallback_source"):
                    self.config.session.lastfm.fallback_source = getattr(
                        Config, "STREAMRIP_LASTFM_FALLBACK_SOURCE", ""
                    )

            # CLI settings
            if hasattr(self.config, "session") and hasattr(
                self.config.session, "cli"
            ):
                if hasattr(self.config.session.cli, "text_output"):
                    self.config.session.cli.text_output = getattr(
                        Config, "STREAMRIP_CLI_TEXT_OUTPUT", True
                    )
                if hasattr(self.config.session.cli, "progress_bars"):
                    self.config.session.cli.progress_bars = getattr(
                        Config, "STREAMRIP_CLI_PROGRESS_BARS", True
                    )
                if hasattr(self.config.session.cli, "max_search_results"):
                    self.config.session.cli.max_search_results = getattr(
                        Config, "STREAMRIP_CLI_MAX_SEARCH_RESULTS", 100
                    )

            # Misc settings
            if hasattr(self.config, "session") and hasattr(
                self.config.session, "misc"
            ):
                if hasattr(self.config.session.misc, "version"):
                    self.config.session.misc.version = getattr(
                        Config, "STREAMRIP_MISC_VERSION", "2.0.6"
                    )
                if hasattr(self.config.session.misc, "check_for_updates"):
                    self.config.session.misc.check_for_updates = getattr(
                        Config, "STREAMRIP_MISC_CHECK_FOR_UPDATES", True
                    )

            # YouTube settings
            if hasattr(self.config, "session") and hasattr(
                self.config.session, "youtube"
            ):
                if hasattr(self.config.session.youtube, "download_videos"):
                    self.config.session.youtube.download_videos = getattr(
                        Config, "STREAMRIP_YOUTUBE_DOWNLOAD_VIDEOS", False
                    )
                if hasattr(self.config.session.youtube, "video_downloads_folder"):
                    self.config.session.youtube.video_downloads_folder = getattr(
                        Config, "STREAMRIP_YOUTUBE_VIDEO_DOWNLOADS_FOLDER", ""
                    )

        except Exception as e:
            LOGGER.error(f"Error applying advanced settings: {e}")

    async def save_config(self) -> bool:
        """Save streamrip configuration to file"""
        if not self.config or not self.config_path:
            return False

        try:
            # Ensure directory exists
            self.config_path.parent.mkdir(parents=True, exist_ok=True)

            # Save config - use in-memory config only to avoid API issues
            # Streamrip will use the in-memory configuration we've set up

            return True

        except Exception as e:
            LOGGER.error(f"Failed to save streamrip config: {e}")
            return False

    def get_config(self) -> StreamripConfig | None:
        """Get the streamrip configuration"""
        return self.config if self._initialized else None

    def is_initialized(self) -> bool:
        """Check if config helper is initialized"""
        return self._initialized

    def is_database_enabled(self) -> bool:
        """Check if streamrip database is enabled in bot settings"""
        return Config.STREAMRIP_ENABLE_DATABASE

    def get_platform_status(self) -> dict[str, bool]:
        """Get simplified platform status"""
        return {
            "qobuz": bool(
                Config.STREAMRIP_QOBUZ_ENABLED and Config.STREAMRIP_QOBUZ_EMAIL
            ),
            "tidal": bool(
                Config.STREAMRIP_TIDAL_ENABLED
                and Config.STREAMRIP_TIDAL_ACCESS_TOKEN
            ),
            "deezer": bool(
                Config.STREAMRIP_DEEZER_ENABLED and Config.STREAMRIP_DEEZER_ARL
            ),
            "soundcloud": Config.STREAMRIP_SOUNDCLOUD_ENABLED,
            "lastfm": Config.STREAMRIP_LASTFM_ENABLED,
        }

    async def _load_config_from_db(self) -> str | None:
        """Load custom streamrip config from database"""
        try:
            if database.db is not None:
                # Try to get custom streamrip config from private files
                from bot.core.aeon_client import TgClient

                files_doc = await database.db.settings.files.find_one(
                    {"_id": TgClient.ID}, {"_id": 0}
                )

                if files_doc and "streamrip_config__toml" in files_doc:
                    config_data = files_doc["streamrip_config__toml"]
                    if config_data:
                        return config_data.decode("utf-8")
            return None
        except Exception as e:
            LOGGER.error(f"Error loading streamrip config from database: {e}")
            return None

    async def save_custom_config_to_db(self, config_content: str) -> bool:
        """Save custom streamrip config to database"""
        try:
            if database.db is not None:
                from bot.core.aeon_client import TgClient

                # Save custom streamrip config as private file using existing pattern
                await database.db.settings.files.update_one(
                    {"_id": TgClient.ID},
                    {
                        "$set": {
                            "streamrip_config__toml": config_content.encode("utf-8")
                        }
                    },
                    upsert=True,
                )
                LOGGER.info("Saved custom streamrip config to database")
                return True
            return False
        except Exception as e:
            LOGGER.error(f"Error saving streamrip config to database: {e}")
            return False

    async def get_custom_config_from_db(self) -> str | None:
        """Get custom streamrip config from database for display"""
        return await self._load_config_from_db()

    async def delete_custom_config_from_db(self) -> bool:
        """Delete custom streamrip config from database"""
        try:
            if database.db is not None:
                from bot.core.aeon_client import TgClient

                # Delete custom streamrip config from database
                await database.db.settings.files.update_one(
                    {"_id": TgClient.ID},
                    {"$unset": {"streamrip_config__toml": ""}},
                    upsert=True,
                )
                LOGGER.info("Deleted custom streamrip config from database")
                return True
            return False
        except Exception as e:
            LOGGER.error(f"Error deleting streamrip config from database: {e}")
            return False


# Global config helper instance
streamrip_config = StreamripConfigHelper()
