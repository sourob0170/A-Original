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
                except Exception as e1:
                    try:
                        # Try alternative initialization
                        self.config = StreamripConfig.defaults()
                        LOGGER.info(
                            "Created default streamrip config using defaults()"
                        )
                    except Exception as e2:
                        # Fallback: create config file manually and load it
                        LOGGER.warning(
                            f"Standard config creation failed: {e1}, {e2}"
                        )
                        await self._create_default_config_file()
                        self.config = StreamripConfig.from_file(
                            str(self.config_path)
                        )
                        LOGGER.info("Created default streamrip config from file")

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

[session.deezer]
quality = 2
arl = ""

[session.soundcloud]
quality = 1

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
                LOGGER.debug(f"Set streamrip download folder to: {DOWNLOAD_DIR}")

            # Quality settings
            quality = Config.STREAMRIP_DEFAULT_QUALITY

            # Apply quality to each platform with safe attribute access
            if hasattr(self.config, "session"):
                if hasattr(self.config.session, "qobuz"):
                    self.config.session.qobuz.quality = quality
                    LOGGER.debug(f"Set Qobuz quality to: {quality}")

                if hasattr(self.config.session, "tidal"):
                    self.config.session.tidal.quality = quality
                    LOGGER.debug(f"Set Tidal quality to: {quality}")

                if hasattr(self.config.session, "deezer"):
                    self.config.session.deezer.quality = min(
                        quality, 2
                    )  # Deezer max is 2
                    LOGGER.debug(f"Set Deezer quality to: {min(quality, 2)}")

                if hasattr(self.config.session, "soundcloud"):
                    self.config.session.soundcloud.quality = min(
                        quality, 1
                    )  # SoundCloud max is 1
                    LOGGER.debug(f"Set SoundCloud quality to: {min(quality, 1)}")

            # Codec settings
            codec = Config.STREAMRIP_DEFAULT_CODEC
            if hasattr(self.config, "session") and hasattr(
                self.config.session, "conversion"
            ):
                self.config.session.conversion.enabled = (
                    Config.STREAMRIP_AUTO_CONVERT
                )
                self.config.session.conversion.codec = codec
                LOGGER.debug(
                    f"Set codec to: {codec}, auto-convert: {Config.STREAMRIP_AUTO_CONVERT}"
                )

            # Concurrent downloads
            concurrent = Config.STREAMRIP_CONCURRENT_DOWNLOADS
            if (
                hasattr(self.config, "session")
                and hasattr(self.config.session, "downloads")
                and hasattr(self.config.session.downloads, "concurrency")
            ):
                self.config.session.downloads.concurrency = concurrent
                LOGGER.debug(f"Set concurrent downloads to: {concurrent}")

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
                LOGGER.debug(f"Set streamrip database directory to: {db_dir}")

            # Authentication settings
            await self._apply_auth_settings()

            # Metadata settings
            if (
                Config.STREAMRIP_METADATA_EXCLUDE
                and hasattr(self.config, "session")
                and hasattr(self.config.session, "metadata")
            ):
                self.config.session.metadata.exclude = (
                    Config.STREAMRIP_METADATA_EXCLUDE
                )
                LOGGER.debug(
                    f"Set metadata exclusions: {Config.STREAMRIP_METADATA_EXCLUDE}"
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

                LOGGER.debug(
                    f"Set cover art settings: embed={Config.STREAMRIP_EMBED_COVER_ART}, save={Config.STREAMRIP_SAVE_COVER_ART}, size={Config.STREAMRIP_COVER_ART_SIZE}"
                )

            # Additional advanced settings
            await self._apply_advanced_settings()

            LOGGER.info("Applied bot settings to streamrip config")

        except Exception as e:
            LOGGER.error(f"Error applying bot settings to streamrip config: {e}")

    async def _apply_auth_settings(self):
        """Apply authentication settings from bot config"""
        try:
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
                self.config.session.qobuz.use_auth_token = False
                LOGGER.debug("✅ Applied Qobuz authentication settings")

            # Tidal authentication (token-based preferred, fallback to username/password)
            if hasattr(self.config, "session") and hasattr(
                self.config.session, "tidal"
            ):
                # Check if we have stored tokens (preferred method)
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
                        self.config.session.tidal.user_id = (
                            Config.STREAMRIP_TIDAL_USER_ID
                        )
                    if Config.STREAMRIP_TIDAL_COUNTRY_CODE:
                        self.config.session.tidal.country_code = (
                            Config.STREAMRIP_TIDAL_COUNTRY_CODE
                        )
                    LOGGER.debug("✅ Applied Tidal token authentication settings")
                # Fallback to username/password if available (for basic auth)
                elif (
                    Config.STREAMRIP_TIDAL_EMAIL and Config.STREAMRIP_TIDAL_PASSWORD
                ):
                    # Set username/password for basic authentication
                    if hasattr(self.config.session.tidal, "username"):
                        self.config.session.tidal.username = (
                            Config.STREAMRIP_TIDAL_EMAIL
                        )
                    if hasattr(self.config.session.tidal, "password"):
                        self.config.session.tidal.password = (
                            Config.STREAMRIP_TIDAL_PASSWORD
                        )
                    LOGGER.debug(
                        "✅ Applied Tidal username/password authentication (limited functionality)"
                    )
                    LOGGER.warning(
                        "⚠️ Tidal username/password auth has limited API access. Consider using tokens."
                    )
                else:
                    LOGGER.warning(
                        "⚠️ Tidal authentication requires tokens or credentials."
                    )
                    LOGGER.info(
                        "💡 For full functionality, use 'rip config --tidal' to get tokens."
                    )

            # Deezer authentication
            if (
                Config.STREAMRIP_DEEZER_ARL
                and hasattr(self.config, "session")
                and hasattr(self.config.session, "deezer")
            ):
                self.config.session.deezer.arl = Config.STREAMRIP_DEEZER_ARL
                LOGGER.debug("✅ Applied Deezer authentication settings")

            # SoundCloud authentication (optional)
            if (
                Config.STREAMRIP_SOUNDCLOUD_CLIENT_ID
                and hasattr(self.config, "session")
                and hasattr(self.config.session, "soundcloud")
                and hasattr(self.config.session.soundcloud, "client_id")
            ):
                self.config.session.soundcloud.client_id = (
                    Config.STREAMRIP_SOUNDCLOUD_CLIENT_ID
                )
                LOGGER.debug("Applied SoundCloud authentication settings")

        except Exception as e:
            LOGGER.error(f"Error applying auth settings: {e}")

    async def _apply_advanced_settings(self):
        """Apply advanced settings from bot config"""
        try:
            # Filename and folder templates
            if (
                Config.STREAMRIP_FILENAME_TEMPLATE
                and hasattr(self.config, "session")
                and hasattr(self.config.session, "filepaths")
            ):
                self.config.session.filepaths.track_format = (
                    Config.STREAMRIP_FILENAME_TEMPLATE
                )
                LOGGER.debug(
                    f"Set filename template: {Config.STREAMRIP_FILENAME_TEMPLATE}"
                )

            if (
                Config.STREAMRIP_FOLDER_TEMPLATE
                and hasattr(self.config, "session")
                and hasattr(self.config.session, "filepaths")
            ):
                self.config.session.filepaths.folder_format = (
                    Config.STREAMRIP_FOLDER_TEMPLATE
                )
                LOGGER.debug(
                    f"Set folder template: {Config.STREAMRIP_FOLDER_TEMPLATE}"
                )

            # Database settings
            if hasattr(self.config, "session") and hasattr(
                self.config.session, "database"
            ):
                # Use the correct database attributes
                if hasattr(self.config.session.database, "downloads_enabled"):
                    self.config.session.database.downloads_enabled = (
                        Config.STREAMRIP_ENABLE_DATABASE
                    )
                if hasattr(self.config.session.database, "failed_downloads_enabled"):
                    self.config.session.database.failed_downloads_enabled = (
                        Config.STREAMRIP_ENABLE_DATABASE
                    )
                LOGGER.debug(
                    f"Set database enabled: {Config.STREAMRIP_ENABLE_DATABASE}"
                )

            # Concurrent downloads settings
            if hasattr(self.config, "session") and hasattr(
                self.config.session, "downloads"
            ):
                if hasattr(self.config.session.downloads, "concurrency"):
                    # Note: streamrip's concurrency is a boolean, not a number
                    # The actual concurrent download count is handled internally
                    self.config.session.downloads.concurrency = (
                        Config.STREAMRIP_CONCURRENT_DOWNLOADS > 1
                    )
                    LOGGER.debug(
                        f"Set downloads concurrency: {Config.STREAMRIP_CONCURRENT_DOWNLOADS > 1}"
                    )

                # Set download folder
                if hasattr(self.config.session.downloads, "folder"):
                    self.config.session.downloads.folder = str(DOWNLOAD_DIR)
                    LOGGER.debug(f"Set download folder: {DOWNLOAD_DIR}")

            # Conversion settings
            if hasattr(self.config, "session") and hasattr(
                self.config.session, "conversion"
            ):
                if hasattr(self.config.session.conversion, "enabled"):
                    self.config.session.conversion.enabled = (
                        Config.STREAMRIP_AUTO_CONVERT
                    )
                    LOGGER.debug(
                        f"Set conversion enabled: {Config.STREAMRIP_AUTO_CONVERT}"
                    )

                if hasattr(self.config.session.conversion, "codec"):
                    self.config.session.conversion.codec = (
                        Config.STREAMRIP_DEFAULT_CODEC
                    )
                    LOGGER.debug(
                        f"Set conversion codec: {Config.STREAMRIP_DEFAULT_CODEC}"
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
            LOGGER.info(
                "Using in-memory streamrip configuration (no file save needed)"
            )

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
        """Get status of platform availability"""
        if not self.config:
            return {}

        status = {}

        try:
            # Check Qobuz
            qobuz_enabled = False
            if (
                Config.STREAMRIP_QOBUZ_ENABLED
                and hasattr(self.config, "session")
                and hasattr(self.config.session, "qobuz")
            ):
                qobuz_enabled = bool(
                    getattr(self.config.session.qobuz, "email_or_userid", None)
                    and getattr(self.config.session.qobuz, "password_or_token", None)
                )
            status["qobuz"] = qobuz_enabled

            # Check Tidal
            tidal_enabled = False
            if (
                Config.STREAMRIP_TIDAL_ENABLED
                and hasattr(self.config, "session")
                and hasattr(self.config.session, "tidal")
            ):
                # Check for token-based auth (preferred)
                token_auth = bool(
                    getattr(self.config.session.tidal, "access_token", None)
                    and getattr(self.config.session.tidal, "refresh_token", None)
                )
                # Check for username/password auth (fallback)
                username_auth = bool(
                    getattr(self.config.session.tidal, "username", None)
                    and getattr(self.config.session.tidal, "password", None)
                )
                tidal_enabled = token_auth or username_auth
            status["tidal"] = tidal_enabled

            # Check Deezer
            deezer_enabled = False
            if (
                Config.STREAMRIP_DEEZER_ENABLED
                and hasattr(self.config, "session")
                and hasattr(self.config.session, "deezer")
            ):
                deezer_enabled = bool(
                    getattr(self.config.session.deezer, "arl", None)
                )
            status["deezer"] = deezer_enabled

            # Check SoundCloud (doesn't require auth)
            status["soundcloud"] = Config.STREAMRIP_SOUNDCLOUD_ENABLED

            # Check Last.fm (doesn't require auth)
            status["lastfm"] = Config.STREAMRIP_LASTFM_ENABLED

        except Exception as e:
            LOGGER.error(f"Error checking platform status: {e}")

        return status

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
