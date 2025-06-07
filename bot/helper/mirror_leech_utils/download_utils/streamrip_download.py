import asyncio
import contextlib
import os
import re
import time
from pathlib import Path

from bot import (
    DOWNLOAD_DIR,
    LOGGER,
    task_dict,
    task_dict_lock,
)
from bot.core.config_manager import Config
from bot.helper.ext_utils.task_manager import check_running_tasks
from bot.helper.mirror_leech_utils.status_utils.streamrip_status import (
    StreamripDownloadStatus,
)
from bot.helper.telegram_helper.message_utils import (
    send_status_message,
)

try:
    from streamrip.client import (
        DeezerClient,
        QobuzClient,
        SoundcloudClient,
        TidalClient,
    )

    STREAMRIP_AVAILABLE = True
except ImportError:
    STREAMRIP_AVAILABLE = False


class StreamripDownloadHelper:
    """Optimized helper class for streamrip downloads"""

    # Class-level constants to reduce memory allocation
    AUDIO_EXTENSIONS = frozenset([".flac", ".mp3", ".m4a", ".ogg", ".opus", ".wav"])
    CODEC_MAPPING = {
        "ogg": "OGG",
        "flac": "FLAC",
        "mp3": "MP3",
        "opus": "OGG",
        "alac": "ALAC",
        "vorbis": "OGG",
        "m4a": "AAC",
        "aac": "AAC",
    }

    # Pre-compiled regex patterns for better performance
    PLATFORM_PATTERNS = {
        "qobuz": re.compile(r"qobuz\.com", re.IGNORECASE),
        "tidal": re.compile(r"tidal\.com|listen\.tidal\.com", re.IGNORECASE),
        "deezer": re.compile(r"deezer\.com|dzr\.page\.link", re.IGNORECASE),
        "soundcloud": re.compile(r"soundcloud\.com", re.IGNORECASE),
    }

    # Common ffmpeg locations for faster lookup
    FFMPEG_LOCATIONS = (
        "/usr/bin/xtra",
        "/usr/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        "/bin/ffmpeg",
    )

    # Pre-compiled regex for URL validation (avoid recompilation)
    URL_VALIDATION_PATTERN = re.compile(r"^https?://", re.IGNORECASE)

    # Common search paths for downloaded files (avoid recreation)
    SEARCH_PATH_TEMPLATES = ("downloads", ".config/streamrip/downloads", "downloads")

    __slots__ = (
        "_cached_config",
        "_cached_ffmpeg_path",
        "_cached_search_paths",
        "_client",
        "_codec",
        "_current_track",
        "_download_path",
        "_download_url",
        "_is_cancelled",
        "_is_downloading",
        "_media",
        "_quality",
        "_start_time",
        "_temp_files",
        "listener",
    )

    def __init__(self, listener):
        self.listener = listener
        self._start_time = time.time()
        self._is_cancelled = False
        self._download_path = None
        self._current_track = ""
        self._is_downloading = False
        # Cache frequently accessed values for O(1) access
        self._cached_config = None
        self._cached_ffmpeg_path = None
        self._temp_files = []
        self._cached_search_paths = None  # Cache search paths to avoid recreation
        # Initialize media and client attributes to None
        self._media = None
        self._client = None

    @property
    def current_track(self):
        """Get current track being downloaded"""
        return self._current_track

    async def download(
        self, url: str, quality: int | None = None, codec: str | None = None
    ) -> bool:
        """Download from streamrip URL"""
        if not STREAMRIP_AVAILABLE:
            LOGGER.error("Streamrip is not available")
            return False

        try:
            # Store quality, codec, and URL for CLI usage
            self._quality = quality
            self._codec = codec
            self._download_url = url

            # Parse URL to get platform and media info
            from bot.helper.streamrip_utils.url_parser import parse_streamrip_url

            try:
                parsed = await parse_streamrip_url(url)
            except Exception as parse_error:
                LOGGER.error(f"Error during URL parsing: {parse_error}")
                raise

            if not parsed:
                LOGGER.error(f"Failed to parse streamrip URL: {url}")
                return False

            platform, media_type, media_id = parsed

            # Set download path using existing DOWNLOAD_DIR pattern
            # Ensure all path components are strings to avoid path division errors
            try:
                base_dir = str(DOWNLOAD_DIR)
                listener_id = str(self.listener.mid)

                download_dir = Path(base_dir) / listener_id
                download_dir.mkdir(parents=True, exist_ok=True)
                self._download_path = download_dir

            except Exception as path_error:
                LOGGER.error(f"Failed to create download path: {path_error}")
                raise

            # Skip client initialization and media object creation for CLI method
            # This avoids the streamrip 2.1.0 path division bug

            # Initialize download state
            self._is_downloading = True
            self._current_track = f"Downloading from {platform.title()}"

            # Start download
            success = await self._perform_download()

            if success:
                return True
            LOGGER.error(f"Streamrip download failed: {url}")
            return False

        except Exception as e:
            LOGGER.error(f"Streamrip download error: {e}")
            return False

    async def _initialize_client(self, platform: str):
        """Initialize the appropriate client for the platform"""
        try:
            from bot.helper.streamrip_utils.streamrip_config import streamrip_config

            config = streamrip_config.get_config()
            if not config:
                LOGGER.error("Streamrip config not available")
                return

            platform_status = streamrip_config.get_platform_status()

            if not platform_status.get(platform, False):
                LOGGER.error(f"Platform {platform} is not configured or enabled")
                return

            # Initialize the appropriate client
            if platform == "qobuz":
                self._client = QobuzClient(config)
            elif platform == "tidal":
                self._client = TidalClient(config)
            elif platform == "deezer":
                self._client = DeezerClient(config)
            elif platform == "soundcloud":
                self._client = SoundcloudClient(config)
            else:
                LOGGER.error(f"Unsupported platform: {platform}")
                return

            # Login/authenticate with proper error handling
            try:
                if hasattr(self._client, "login"):
                    await self._client.login()
            except Exception as auth_error:
                if platform == "tidal":
                    LOGGER.warning(f"⚠️ Tidal authentication failed: {auth_error}")
                    return
                LOGGER.error(
                    f"❌ {platform.title()} authentication failed: {auth_error}"
                )
                return

        except Exception as e:
            LOGGER.error(f"Failed to initialize {platform} client: {e}")

    async def _create_media_object(
        self, platform: str, media_type: str, media_id: str
    ):
        """Create the appropriate media object"""
        try:
            # Use platform-specific methods to get metadata
            if platform == "qobuz":
                # Qobuz uses get_metadata for all media types
                self._media = await self._client.get_metadata(media_id, media_type)
                if not self._media:
                    LOGGER.error(f"Failed to get {media_type} metadata from Qobuz")
                    return
            elif platform == "deezer":
                # Deezer has specific methods for each media type
                if media_type == "track":
                    self._media = await self._client.get_track(media_id)
                elif media_type == "album":
                    self._media = await self._client.get_album(media_id)
                elif media_type == "playlist":
                    self._media = await self._client.get_playlist(media_id)
                elif media_type == "artist":
                    self._media = await self._client.get_artist(media_id)
                else:
                    LOGGER.error(f"Unsupported Deezer media type: {media_type}")
                    return

                if not self._media:
                    LOGGER.error(f"Failed to get {media_type} metadata from Deezer")
                    return
            elif platform == "tidal":
                # Tidal uses get_metadata similar to Qobuz
                self._media = await self._client.get_metadata(media_id, media_type)
                if not self._media:
                    LOGGER.error(f"Failed to get {media_type} metadata from Tidal")
                    return
            elif platform == "soundcloud":
                # SoundCloud uses get_metadata
                self._media = await self._client.get_metadata(media_id, media_type)
                if not self._media:
                    LOGGER.error(
                        f"Failed to get {media_type} metadata from SoundCloud"
                    )
                    return
            else:
                LOGGER.error(f"Unsupported platform: {platform}")
                return

        except Exception as e:
            LOGGER.error(f"❌ Failed to create media object: {e}")
            return

    async def _set_quality(self, quality: int):
        """Set download quality"""
        try:
            if hasattr(self._media, "set_quality"):
                await self._media.set_quality(quality)
            elif hasattr(self._client, "set_quality"):
                await self._client.set_quality(quality)
        except Exception as e:
            LOGGER.error(f"Failed to set quality: {e}")

    async def _set_codec(self, codec: str):
        """Set output codec"""
        try:
            if hasattr(self._media, "set_codec"):
                await self._media.set_codec(codec)
            elif hasattr(self._client, "set_codec"):
                await self._client.set_codec(codec)
        except Exception as e:
            LOGGER.error(f"Failed to set codec: {e}")

    async def _update_download_path(self):
        """Update streamrip config to use our download path"""
        try:
            from bot.helper.streamrip_utils.streamrip_config import streamrip_config

            config = streamrip_config.get_config()
            if (
                config
                and hasattr(config, "session")
                and hasattr(config.session, "downloads")
            ):
                # Set the download folder to our specific path
                config.session.downloads.folder = str(self._download_path)
        except Exception as e:
            LOGGER.warning(f"Failed to update streamrip download path: {e}")

    async def _perform_download(self) -> bool:
        """Perform the actual download with enhanced error handling"""
        try:
            # Due to a bug in streamrip 2.1.0 with PosixPath division operations,
            # we'll use CLI method exclusively to avoid the internal API issues
            download_success = await self._download_with_cli()

            if download_success:
                # Validate downloaded files
                downloaded_files = await self._find_downloaded_files()
                if downloaded_files:
                    return True
                LOGGER.error("No files were downloaded")
                return False
            LOGGER.error("CLI download method failed")
            return False

        except Exception as e:
            LOGGER.error(f"Download failed: {e}")
            return False

    def _map_codec_for_streamrip(self, codec: str) -> str:
        """Map user-friendly codec names to streamrip-compatible ones with optimized lookup"""
        codec_lower = codec.lower()

        # Handle AAC/M4A codecs with FFmpeg wrapper approach (O(1) lookup)
        if codec_lower in ("m4a", "aac"):
            return "AAC"

        # Use class-level mapping for O(1) efficiency
        mapped_codec = self.CODEC_MAPPING.get(codec_lower)

        if mapped_codec is None:
            LOGGER.warning(
                f"⚠️ Unknown codec '{codec}' - downloading in default format"
            )
            return None

        return mapped_codec

    async def _download_with_cli(self) -> bool:
        """Download using streamrip CLI with proper configuration"""
        try:
            import asyncio
            import os

            # Create download directory if it doesn't exist
            self._download_path.mkdir(parents=True, exist_ok=True)

            # Construct streamrip command with proper v2.1.0 syntax
            cmd = ["rip"]

            # Add global options before the command (using long form for clarity)
            if hasattr(self, "_quality") and self._quality is not None:
                cmd.extend(
                    ["--quality", str(self._quality)]
                )  # Use --quality instead of -q

            # Add codec option if specified
            if hasattr(self, "_codec") and self._codec is not None:
                # Map codec to streamrip-compatible format
                mapped_codec = self._map_codec_for_streamrip(self._codec)
                if mapped_codec is not None:
                    cmd.extend(
                        ["--codec", mapped_codec]
                    )  # Use --codec instead of -c
            # Add --no-db flag if database is disabled in bot settings OR if force download is enabled
            from bot.helper.streamrip_utils.streamrip_config import streamrip_config

            force_download = getattr(self.listener, "force_download", False)

            if not streamrip_config.is_database_enabled() or force_download:
                cmd.extend(["--no-db"])

            # Add --verbose flag for better debugging (v2.1.0 feature)
            cmd.extend(["--verbose"])

            # Add the url command and URL
            # Use the original URL passed to the download method instead of listener.url
            download_url = getattr(self, "_download_url", self.listener.url)

            # Convert URL to streamrip-compatible format if needed
            converted_url = await self._convert_url_for_streamrip(download_url)
            cmd.extend(["url", converted_url])

            # Set download directory via environment variable (may not work with all streamrip versions)
            env = os.environ.copy()
            env["STREAMRIP_DOWNLOAD_DIR"] = str(self._download_path)

            # Set FFMPEG path for streamrip to find the executable
            ffmpeg_path = self._get_ffmpeg_path()

            # Create FFmpeg wrapper for AAC encoder compatibility
            wrapper_path = await self._setup_ffmpeg_wrapper_for_aac(ffmpeg_path)

            # Set multiple environment variables that streamrip might check
            env["FFMPEG_EXECUTABLE"] = wrapper_path
            env["FFMPEG_PATH"] = wrapper_path
            env["FFMPEG"] = wrapper_path
            env["FFMPEG_BINARY"] = wrapper_path

            # Ensure the wrapper directory is in PATH
            wrapper_dir = os.path.dirname(wrapper_path)
            env["PATH"] = f"{wrapper_dir}:{env.get('PATH', '')}"

            # Check if streamrip is available
            try:
                check_process = await asyncio.create_subprocess_exec(
                    "which",
                    "rip",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout_check, stderr_check = await check_process.communicate()
                if check_process.returncode != 0:
                    LOGGER.error("Streamrip 'rip' command not found")
                    return False
            except Exception as check_error:
                LOGGER.error(f"Error checking streamrip: {check_error}")
                return False

            # Always regenerate config to ensure latest settings are applied
            await self._create_safe_config_after_reset()

            # Check FFMPEG availability
            await self._check_ffmpeg_availability()

            # Check if we have proper authentication for the URL
            if not await self._validate_authentication_for_url(download_url):
                LOGGER.error("No valid authentication found for this URL")
                # Send helpful message to user
                try:
                    from bot.helper.ext_utils.status_utils import send_status_message

                    await send_status_message(
                        self.listener.message,
                        "❌ **Authentication Required**\n\n"
                        "Please configure your streaming service credentials:\n"
                        "• `/botsettings` → **Streamrip** → **Credential settings**\n\n"
                        "**For Deezer URLs:** Set your Deezer ARL\n"
                        "**For Qobuz URLs:** Set email and password\n"
                        "**For Tidal URLs:** Set email and password",
                    )
                except Exception:
                    pass
                return False

            # Execute with timeout
            # Use home directory as working directory since streamrip uses its own config
            try:
                # For Heroku compatibility, ensure we have proper environment
                working_dir = str(Path.home())

                # Add additional environment variables for Heroku and asyncio stability
                env["PYTHONUNBUFFERED"] = "1"  # Ensure output is not buffered
                env["TERM"] = "xterm"  # Provide a terminal type
                env["PYTHONIOENCODING"] = "utf-8"  # Ensure proper encoding
                env["PYTHONDONTWRITEBYTECODE"] = (
                    "1"  # Prevent bytecode generation issues
                )

                # Add asyncio event loop isolation for Heroku
                env["PYTHONASYNCIODEBUG"] = "0"  # Disable asyncio debug mode
                env["PYTHONHASHSEED"] = "0"  # Ensure deterministic behavior

                # Create subprocess with enhanced isolation for asyncio stability
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    stdin=asyncio.subprocess.PIPE,  # Provide stdin for interactive prompts
                    cwd=working_dir,
                    env=env,
                    # Add process group isolation to prevent event loop conflicts
                    preexec_fn=None if os.name == "nt" else os.setsid,
                    # Limit subprocess resources to prevent memory issues
                    limit=1024 * 1024 * 10,  # 10MB buffer limit
                )

            except Exception as proc_error:
                LOGGER.error(f"Failed to create subprocess: {proc_error}")
                return False

            try:
                # Remove timeout restrictions for streamrip downloads (like Deezer)

                # Send empty input to stdin to prevent hanging on prompts
                # For Deezer ARL prompts, send newline to skip
                stdin_input = b"\n"
                stdout, stderr = await process.communicate(input=stdin_input)

                # Log detailed output for debugging
                stdout_text = stdout.decode() if stdout else ""
                stderr.decode() if stderr else ""

                # Log completion status
                if process.returncode != 0:
                    LOGGER.error(f"Streamrip failed with code: {process.returncode}")

                self._is_downloading = False
            except Exception as e:
                # Handle any other errors
                LOGGER.error(f"Streamrip process error: {e}")
                self._is_downloading = False
                try:
                    process.kill()
                    await process.wait()
                except Exception as kill_error:
                    LOGGER.error(f"Error killing process: {kill_error}")
                return False

            # Check result
            if process.returncode == 0:
                stdout_text = stdout.decode() if stdout else ""

                # Check for issues in output
                if (
                    "Error loading config" in stdout_text
                    or "Control characters" in stdout_text
                ):
                    LOGGER.error("Config corruption detected in output")

                # Check for config corruption and fix automatically
                config_corruption_indicators = [
                    "Error loading config",
                    "Control characters",
                    "not allowed in strings",
                    "Try running rip config reset",
                ]

                if any(
                    indicator in stdout_text
                    for indicator in config_corruption_indicators
                ):
                    LOGGER.error("Config corruption detected - fixing automatically")
                    try:
                        await self._reset_streamrip_config()
                        return False  # Retry after fix
                    except Exception:
                        return False

                # Check for download activity
                download_indicators = [
                    "Downloaded",
                    "Downloading",
                    "Converting",
                    "Saved to",
                ]
                has_download_activity = any(
                    indicator in stdout_text for indicator in download_indicators
                )

                if not has_download_activity and stdout_text:
                    LOGGER.warning(
                        "No download activity detected - check credentials/availability"
                    )

                return True

            # Handle errors
            error_output = stderr.decode() if stderr else "Unknown error"
            LOGGER.error(
                f"Streamrip failed (code {process.returncode}): {error_output}"
            )

            # Check if this might be a credential issue
            # Check for specific error patterns
            if "No such file or directory" in error_output:
                LOGGER.error("Streamrip CLI not found")
            elif (
                "Invalid URL" in error_output or "URL not supported" in error_output
            ):
                LOGGER.error("URL not supported by streamrip")
            elif "Authentication" in error_output or "login" in error_output.lower():
                LOGGER.error("Authentication failed - check credentials")
            elif any(
                x in error_output.lower()
                for x in ["enter your arl", "authenticationerror"]
            ):
                LOGGER.error("Deezer authentication failed - check ARL")
            elif any(
                x in error_output.lower()
                for x in ["enter your qobuz email", "enter your qobuz password"]
            ):
                LOGGER.error("Qobuz credentials missing - check email/password")
            elif (
                "event loop is closed" in error_output.lower()
                or "runtimeerror" in error_output.lower()
            ):
                LOGGER.error("Streamrip internal error - retrying")
                return await self._retry_download_with_isolation()
            elif "qobuz" in error_output.lower() and (
                "error" in error_output.lower() or "failed" in error_output.lower()
            ):
                LOGGER.error("Qobuz error - check credentials/subscription")
            elif "tidal" in error_output.lower() and (
                "error" in error_output.lower() or "failed" in error_output.lower()
            ):
                LOGGER.error("Tidal error - check credentials/subscription")
            elif "deezer" in error_output.lower() and (
                "error" in error_output.lower() or "failed" in error_output.lower()
            ):
                LOGGER.error("Deezer error - check ARL token")
            elif "soundcloud" in error_output.lower():
                LOGGER.error("SoundCloud error - check client ID/permissions")
            elif (
                "last.fm" in error_output.lower() or "lastfm" in error_output.lower()
            ):
                LOGGER.error("Last.fm error - check playlist access")
            elif "spotify" in error_output.lower():
                LOGGER.error("Spotify error - check playlist access")
            elif (
                "apple music" in error_output.lower()
                or "music.apple.com" in error_output.lower()
            ):
                LOGGER.error("Apple Music error - check playlist access")
            elif (
                "timeout" in error_output.lower()
                or "timed out" in error_output.lower()
            ):
                LOGGER.error("Download timed out - check network/size")
            elif "does not exist" in error_output.lower() and (
                "key" in error_output.lower() or "section" in error_output.lower()
            ):
                LOGGER.error("Config missing sections - regenerating")
                with contextlib.suppress(Exception):
                    await self._create_safe_config_after_reset()
            elif (
                "typeerror" in error_output.lower()
                and "string formatting" in error_output.lower()
            ):
                LOGGER.error("Config format error - regenerating")
                with contextlib.suppress(Exception):
                    await self._create_safe_config_after_reset()
            elif (
                "ffmpeg" in error_output.lower()
                or "could not find ffmpeg" in error_output.lower()
            ):
                LOGGER.error("FFMPEG not found - check installation")
            elif (
                "conversion" in error_output.lower()
                and "failed" in error_output.lower()
            ):
                LOGGER.error("Audio conversion failed - check FFMPEG")
            elif (
                "conversionconfig" in error_output.lower()
                and "unexpected keyword argument" in error_output.lower()
            ):
                LOGGER.error("Config compatibility issue - fixing")
                await self._create_safe_config_after_reset()
            elif "error loading config" in error_output.lower():
                LOGGER.error("Config loading error - regenerating")
            elif (
                "control characters" in error_output.lower()
                and "not allowed in strings" in error_output.lower()
            ):
                LOGGER.error("Config corruption detected - resetting")
                with contextlib.suppress(Exception):
                    await self._reset_streamrip_config()

            return False

        except Exception as e:
            LOGGER.error(f"CLI download failed: {e}")
            return False

    async def _find_downloaded_files(self) -> list:
        """Find downloaded files in the download directory with optimized caching"""
        try:
            downloaded_files = []

            # Use cached search paths for O(1) access on subsequent calls
            if self._cached_search_paths is None:
                search_paths = []
                if self._download_path and self._download_path.exists():
                    search_paths.append(self._download_path)
                    parent_dir = self._download_path.parent
                    if parent_dir.exists():
                        search_paths.append(parent_dir)

                # Add common paths only if they exist (avoid unnecessary checks)
                from pathlib import Path

                common_paths = [
                    Path.home() / "StreamripDownloads",
                    Path.home() / "Downloads",
                    Path("/tmp"),
                    Path("/usr/src/app/downloads"),
                ]

                search_paths.extend(
                    p for p in common_paths if p.exists() and p not in search_paths
                )
                self._cached_search_paths = search_paths

                LOGGER.info(
                    f"Searching {len(search_paths)} paths for downloaded files"
                )
            else:
                search_paths = self._cached_search_paths

            # Search for downloaded files
            for search_path in search_paths:
                try:
                    # Find recent audio files
                    new_files = [
                        file_path
                        for file_path in search_path.rglob("*")
                        if (
                            file_path.is_file()
                            and file_path.suffix.lower() in self.AUDIO_EXTENSIONS
                            and file_path.stat().st_mtime > self._start_time
                        )
                    ]

                    downloaded_files.extend(new_files)

                    # Early termination if we found files in primary location
                    if new_files and search_path == self._download_path:
                        break
                except Exception as search_error:
                    LOGGER.error(f"Error searching {search_path}: {search_error}")

            # Use set for deduplication (more efficient than list conversion)
            unique_files = list({f.resolve(): f for f in downloaded_files}.values())
            unique_files.sort(key=lambda x: x.stat().st_mtime)

            LOGGER.info(f"Found {len(unique_files)} downloaded audio files")

            # Move files if needed
            if unique_files:
                return await self._move_files_to_target_folder(unique_files)
            return unique_files

        except Exception as e:
            LOGGER.error(f"Failed to find downloaded files: {e}")
            return []

    async def _move_files_to_target_folder(self, files: list) -> list:
        """Move downloaded files from streamrip default folder to our target folder"""
        try:
            import shutil

            moved_files = []

            for file_path in files:
                try:
                    # Check if file is in the default streamrip folder
                    streamrip_folder = Path.home() / "StreamripDownloads"
                    if (
                        streamrip_folder in file_path.parents
                        or file_path.parent == streamrip_folder
                    ):
                        # Preserve folder structure when moving files
                        # Get the relative path from streamrip folder to maintain album/playlist structure
                        try:
                            relative_path = file_path.relative_to(streamrip_folder)
                            target_file = self._download_path / relative_path
                        except ValueError:
                            # If relative_to fails, use the full structure from parent
                            if file_path.parent != streamrip_folder:
                                # File is in a subfolder, preserve the structure
                                relative_path = file_path.relative_to(
                                    file_path.parent.parent
                                )
                                target_file = self._download_path / relative_path
                            else:
                                # File is directly in streamrip folder
                                target_file = self._download_path / file_path.name

                        # Ensure target directory exists
                        target_file.parent.mkdir(parents=True, exist_ok=True)

                        # Move the file
                        shutil.move(str(file_path), str(target_file))
                        moved_files.append(target_file)

                    else:
                        # File is already in the right location
                        moved_files.append(file_path)

                except Exception as move_error:
                    LOGGER.error(f"Failed to move file {file_path}: {move_error}")
                    # Keep the original file in the list if move fails
                    moved_files.append(file_path)

            return moved_files

        except Exception as e:
            LOGGER.error(f"Error moving files: {e}")
            return files  # Return original files if moving fails

    async def _ensure_streamrip_config(self):
        """Ensure streamrip config exists and is properly configured"""
        try:
            config_dir = Path.home() / ".config" / "streamrip"
            config_file = config_dir / "config.toml"

            if not config_file.exists():
                LOGGER.info("Streamrip config not found, creating default config...")

                # Create config directory
                config_dir.mkdir(parents=True, exist_ok=True)

                # Create basic config with Deezer ARL from bot settings
                config_content = self._create_default_config()

                # Write config file asynchronously
                import aiofiles

                async with aiofiles.open(config_file, "w") as f:
                    await f.write(config_content)

                LOGGER.info(f"Created streamrip config at: {config_file}")

        except Exception as e:
            LOGGER.error(f"Failed to ensure streamrip config: {e}")
            # Don't fail the download if config creation fails

    def _get_ffmpeg_path(self) -> str:
        """Get the path to FFMPEG executable with caching"""
        if self._cached_ffmpeg_path:
            return self._cached_ffmpeg_path

        try:
            # Use class-level constants for better performance
            for location in self.FFMPEG_LOCATIONS:
                if os.path.exists(location):
                    self._cached_ffmpeg_path = location
                    return location
            # If not found, return default
            self._cached_ffmpeg_path = "/usr/bin/xtra"
            return self._cached_ffmpeg_path
        except Exception:
            self._cached_ffmpeg_path = "/usr/bin/xtra"
            return self._cached_ffmpeg_path

    async def _setup_ffmpeg_wrapper_for_aac(self, ffmpeg_path: str) -> str:
        """Setup FFmpeg wrapper that replaces libfdk_aac with built-in aac encoder"""
        try:
            import stat
            import tempfile

            # Create a temporary directory for the wrapper
            wrapper_dir = tempfile.mkdtemp(prefix="streamrip_ffmpeg_")
            wrapper_script = os.path.join(wrapper_dir, "ffmpeg")

            # Create wrapper script that handles multiple encoder compatibility issues
            wrapper_content = f'''#!/bin/bash
# FFmpeg wrapper for streamrip encoder compatibility
# Handles libfdk_aac → aac and OGG video stream issues

args=("$@")
replaced_aac=false
fixed_ogg=false

# Replace libfdk_aac with aac encoder
for i in "${{!args[@]}}"; do
    if [[ "${{args[i]}}" == "libfdk_aac" ]]; then
        args[i]="aac"
        replaced_aac=true
        echo "🔄 Replaced libfdk_aac with aac encoder" >&2
    fi
done

# Fix OGG conversion issues with video streams
# Check if this is an OGG conversion with video copy
if [[ "${{args[*]}}" == *".ogg"* ]] && [[ "${{args[*]}}" == *"-c:v"* ]] && [[ "${{args[*]}}" == *"copy"* ]]; then
    # Replace "-c:v copy" with "-vn" (no video) for OGG files
    for i in "${{!args[@]}}"; do
        if [[ "${{args[i]}}" == "-c:v" ]] && [[ "${{args[i+1]}}" == "copy" ]]; then
            args[i]="-vn"
            unset args[i+1]
            # Reindex array to remove gaps
            args=("${{args[@]}}")
            fixed_ogg=true
            echo "🔄 Fixed OGG conversion: replaced -c:v copy with -vn" >&2
            break
        fi
    done
fi

if [[ "$replaced_aac" == "true" ]]; then
    echo "✅ Using built-in aac encoder for AAC conversion" >&2
fi

if [[ "$fixed_ogg" == "true" ]]; then
    echo "✅ Fixed OGG conversion for video stream compatibility" >&2
fi

# Execute the actual ffmpeg (xtra) with modified arguments
exec "{ffmpeg_path}" "${{args[@]}}"
'''

            # Write the wrapper script
            with open(wrapper_script, "w") as f:
                f.write(wrapper_content)

            # Make it executable
            os.chmod(wrapper_script, stat.S_IRWXU | stat.S_IRGRP | stat.S_IROTH)

            # Store wrapper path for cleanup later
            if not hasattr(self, "_temp_files"):
                self._temp_files = []
            self._temp_files.append(wrapper_dir)

            return wrapper_script

        except Exception as e:
            LOGGER.error(f"⚠️ Failed to create FFmpeg wrapper: {e}")
            LOGGER.info(f"📋 Falling back to direct ffmpeg path: {ffmpeg_path}")
            return ffmpeg_path

    async def _check_ffmpeg_availability(self):
        """Check if FFMPEG is available and log status"""
        try:
            ffmpeg_path = self._get_ffmpeg_path()
            import os

            if not os.path.exists(ffmpeg_path):
                LOGGER.warning(f"⚠️ FFMPEG not found at expected path: {ffmpeg_path}")
                LOGGER.warning("Audio conversion may fail if FFMPEG is required")
        except Exception as e:
            LOGGER.error(f"Error checking FFMPEG availability: {e}")

    async def _create_compatible_config(self):
        """Deprecated: Use safe config generation instead"""
        await self._create_safe_config_after_reset()
        return True

    async def _reset_streamrip_config(self):
        """Reset streamrip config to fix corruption issues"""
        try:
            import asyncio
            from pathlib import Path

            config_dir = Path.home() / ".config" / "streamrip"
            config_file = config_dir / "config.toml"

            # Method 1: Try using 'rip config reset' command
            try:
                reset_process = await asyncio.create_subprocess_exec(
                    "rip",
                    "config",
                    "reset",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    stdin=asyncio.subprocess.PIPE,
                )

                # Send 'y' to confirm reset
                stdout, stderr = await asyncio.wait_for(
                    reset_process.communicate(input=b"y\n"), timeout=30
                )

                if reset_process.returncode == 0:
                    # Clear our cached config to force regeneration
                    self._cached_config = None
                    # Use safe config generation after reset
                    await self._create_safe_config_after_reset()
                    return True
                LOGGER.warning(
                    f"'rip config reset' failed with code {reset_process.returncode}"
                )
                error_text = stderr.decode() if stderr else "Unknown error"
                LOGGER.warning(f"Reset error: {error_text}")

            except Exception as reset_cmd_error:
                LOGGER.warning(
                    f"'rip config reset' command failed: {reset_cmd_error}"
                )

            # Method 2: Manual config file removal and regeneration
            LOGGER.info("Attempting manual config reset...")

            # Remove corrupted config file
            if config_file.exists():
                config_file.unlink()
                LOGGER.info(f"Removed corrupted config file: {config_file}")

            # Remove entire config directory to ensure clean slate
            if config_dir.exists():
                import shutil

                shutil.rmtree(config_dir)
                LOGGER.info(f"Removed config directory: {config_dir}")

            # Clear cached config
            self._cached_config = None

            # Use safe config generation after reset
            await self._create_safe_config_after_reset()
            return True

        except Exception as e:
            LOGGER.error(f"Failed to reset streamrip config: {e}")
            return False

    async def _create_safe_config_after_reset(self):
        """Create a minimal, safe config after reset to avoid control character issues"""
        try:
            from pathlib import Path

            import aiofiles

            from bot.core.config_manager import Config

            config_dir = Path.home() / ".config" / "streamrip"
            config_file = config_dir / "config.toml"

            # Ensure directory exists
            config_dir.mkdir(parents=True, exist_ok=True)

            # Get credentials safely
            qobuz_email = getattr(Config, "STREAMRIP_QOBUZ_EMAIL", "")
            qobuz_password = getattr(Config, "STREAMRIP_QOBUZ_PASSWORD", "")
            deezer_arl = getattr(Config, "STREAMRIP_DEEZER_ARL", "")
            downloads_folder = getattr(
                Config, "DOWNLOAD_DIR", str(Path.home() / "StreamripDownloads")
            )

            # Create minimal, safe config without complex formatting
            safe_config = f"""[downloads]
folder = "{downloads_folder}"
source_subdirectories = false
disc_subdirectories = true
concurrency = true
max_connections = 6
requests_per_minute = 60
verify_ssl = true

[qobuz]
quality = 3
download_booklets = true
use_auth_token = false
email_or_userid = "{qobuz_email}"
password_or_token = "{qobuz_password}"
app_id = ""
secrets = []

[tidal]
quality = 3
download_videos = true
user_id = ""
country_code = ""
access_token = ""
refresh_token = ""
token_expiry = "0"

[deezer]
quality = 2
arl = "{deezer_arl}"
use_deezloader = true
deezloader_warnings = true

[soundcloud]
quality = 0
client_id = ""
app_version = ""

[youtube]
quality = 0
download_videos = false
video_downloads_folder = "{downloads_folder}/youtube"

[database]
downloads_enabled = true
downloads_path = "./downloads.db"
failed_downloads_enabled = true
failed_downloads_path = "./failed_downloads.db"

[conversion]
enabled = false
codec = "ALAC"
sampling_rate = 48000
bit_depth = 24
lossy_bitrate = 320

[qobuz_filters]
extras = false
repeats = false
non_albums = false
features = false
non_studio_albums = false
non_remaster = false

[artwork]
embed = true
embed_size = "large"
embed_max_width = -1
save_artwork = true
saved_max_width = -1

[metadata]
set_playlist_to_album = true
renumber_playlist_tracks = true
exclude = []

[filepaths]
add_singles_to_folder = false
folder_format = "{{albumartist}} - {{title}} ({{year}}) [{{container}}] [{{bit_depth}}B-{{sampling_rate}}kHz]"
track_format = "{{tracknumber:02}}. {{artist}} - {{title}}{{explicit}}"
restrict_characters = false
truncate_to = 120

[lastfm]
source = "qobuz"
fallback_source = ""

[cli]
text_output = true
progress_bars = false
max_search_results = 100

[misc]
version = "2.0.6"
check_for_updates = true
"""

            # Write the safe config
            async with aiofiles.open(config_file, "w", encoding="utf-8") as f:
                await f.write(safe_config)

        except Exception as e:
            LOGGER.error(f"Failed to create safe config: {e}")
            raise

    def _create_default_config(self) -> str:
        """Deprecated: Use _create_safe_config_after_reset instead"""
        # This method is kept for compatibility but redirects to safe config
        LOGGER.warning(
            "_create_default_config is deprecated, using safe config generation"
        )
        return "# Deprecated - use safe config generation"

    async def _regenerate_streamrip_config(self):
        """Deprecated: Use _create_safe_config_after_reset instead"""
        LOGGER.warning(
            "_regenerate_streamrip_config is deprecated, using safe config generation"
        )
        await self._create_safe_config_after_reset()

    async def _validate_config_credentials(self, config_file: Path):
        """Deprecated: Validation not needed with safe config generation"""

    async def _update_deezer_arl(self, new_arl: str):
        """Deprecated: Use safe config regeneration instead"""
        LOGGER.info("Regenerating config with updated Deezer ARL")
        await self._create_safe_config_after_reset()
        return True

    async def _validate_authentication_for_url(self, url: str) -> bool:
        """Validate that we have proper authentication for the given URL"""
        try:
            from bot.core.config_manager import Config

            # Parse URL to determine platform
            url_lower = url.lower()

            if "deezer.com" in url_lower or "dzr.page.link" in url_lower:
                # Deezer URL - check for ARL
                deezer_arl = Config.STREAMRIP_DEEZER_ARL or ""
                if not deezer_arl.strip():
                    LOGGER.error(
                        "❌ Deezer URL detected but no Deezer ARL configured!"
                    )
                    LOGGER.error("Please configure your Deezer ARL via:")
                    LOGGER.error(
                        "  /botsettings → Streamrip → Credential settings → Deezer arl"
                    )
                    return False
                return True

            if "qobuz.com" in url_lower:
                # Qobuz URL - check for email/password
                qobuz_email = Config.STREAMRIP_QOBUZ_EMAIL or ""
                qobuz_password = Config.STREAMRIP_QOBUZ_PASSWORD or ""
                if not qobuz_email.strip() or not qobuz_password.strip():
                    LOGGER.error(
                        "❌ Qobuz URL detected but no Qobuz credentials configured!"
                    )
                    LOGGER.error("Please configure your Qobuz credentials via:")
                    LOGGER.error(
                        "  /botsettings → Streamrip → Credential settings → Qobuz"
                    )
                    return False

                # Additional Qobuz validation
                if "@temp-mail.me" in qobuz_email.lower():
                    LOGGER.warning(
                        "⚠️ Qobuz email appears to be a temporary email address"
                    )
                    LOGGER.warning("Qobuz may block temporary email providers")
                    LOGGER.warning(
                        "Consider using a permanent email address for better reliability"
                    )

                return True

            if "tidal.com" in url_lower:
                # Tidal URL - check for credentials and tokens
                tidal_email = Config.STREAMRIP_TIDAL_EMAIL or ""
                tidal_password = Config.STREAMRIP_TIDAL_PASSWORD or ""
                tidal_access_token = Config.STREAMRIP_TIDAL_ACCESS_TOKEN or ""

                # Check if we have either email/password OR access token
                has_credentials = bool(
                    tidal_email.strip() and tidal_password.strip()
                )
                has_token = bool(tidal_access_token.strip())

                if not has_credentials and not has_token:
                    LOGGER.error(
                        "❌ Tidal URL detected but no Tidal authentication configured!"
                    )
                    LOGGER.error("Please configure your Tidal credentials via:")
                    LOGGER.error(
                        "  /botsettings → Streamrip → Credential settings → Tidal"
                    )
                    LOGGER.error(
                        "💡 Note: Tidal requires interactive authentication to generate tokens"
                    )
                    LOGGER.error(
                        "💡 You may need to run 'rip config --tidal' manually to authenticate"
                    )
                    return False

                if has_token:
                    return True
                if has_credentials:
                    # Additional Tidal validation (like Qobuz)
                    if "@temp-mail.me" in tidal_email.lower():
                        LOGGER.warning(
                            "⚠️ Tidal email appears to be a temporary email address"
                        )
                        LOGGER.warning("Tidal may block temporary email providers")
                        LOGGER.warning(
                            "Consider using a permanent email address for better reliability"
                        )

                    return True

            elif "soundcloud.com" in url_lower:
                # SoundCloud URL - check for client ID (same logic as Deezer)
                soundcloud_client_id = Config.STREAMRIP_SOUNDCLOUD_CLIENT_ID or ""
                if not soundcloud_client_id.strip():
                    LOGGER.warning(
                        "⚠️ SoundCloud URL detected but no client ID configured"
                    )
                    LOGGER.warning(
                        "SoundCloud may work without client ID for some tracks"
                    )
                    LOGGER.info(
                        "💡 For better reliability, configure SoundCloud client ID via:"
                    )
                    LOGGER.info(
                        "  /botsettings → Streamrip → Credential settings → SoundCloud"
                    )
                    return True  # Allow SoundCloud without client ID (like Deezer allows missing ARL)
                return True

            elif "last.fm" in url_lower or "lastfm" in url_lower:
                # Last.fm playlist - requires primary source authentication

                # Check if we have at least one streaming service configured
                has_deezer = bool((Config.STREAMRIP_DEEZER_ARL or "").strip())
                has_qobuz = bool(
                    (Config.STREAMRIP_QOBUZ_EMAIL or "").strip()
                    and (Config.STREAMRIP_QOBUZ_PASSWORD or "").strip()
                )
                has_tidal = bool(
                    (Config.STREAMRIP_TIDAL_EMAIL or "").strip()
                    and (Config.STREAMRIP_TIDAL_PASSWORD or "").strip()
                )

                if not (has_deezer or has_qobuz or has_tidal):
                    LOGGER.error(
                        "❌ Last.fm playlist requires at least one streaming service configured!"
                    )
                    LOGGER.error(
                        "Please configure credentials for Deezer, Qobuz, or Tidal via:"
                    )
                    LOGGER.error("  /botsettings → Streamrip → Credential settings")
                    return False

                return True

            elif "spotify.com" in url_lower or "open.spotify.com" in url_lower:
                # Spotify playlist - requires Last.fm integration

                # Check if we have streaming services for Last.fm fallback
                has_deezer = bool((Config.STREAMRIP_DEEZER_ARL or "").strip())
                has_qobuz = bool(
                    (Config.STREAMRIP_QOBUZ_EMAIL or "").strip()
                    and (Config.STREAMRIP_QOBUZ_PASSWORD or "").strip()
                )
                has_tidal = bool(
                    (Config.STREAMRIP_TIDAL_EMAIL or "").strip()
                    and (Config.STREAMRIP_TIDAL_PASSWORD or "").strip()
                )

                if not (has_deezer or has_qobuz or has_tidal):
                    LOGGER.error(
                        "❌ Spotify playlist requires streaming service credentials for Last.fm conversion!"
                    )
                    LOGGER.error(
                        "Please configure credentials for Deezer, Qobuz, or Tidal via:"
                    )
                    LOGGER.error("  /botsettings → Streamrip → Credential settings")
                    return False

                return True

            elif "music.apple.com" in url_lower:
                # Apple Music playlist - requires Last.fm integration

                # Check if we have streaming services for Last.fm fallback
                has_deezer = bool((Config.STREAMRIP_DEEZER_ARL or "").strip())
                has_qobuz = bool(
                    (Config.STREAMRIP_QOBUZ_EMAIL or "").strip()
                    and (Config.STREAMRIP_QOBUZ_PASSWORD or "").strip()
                )
                has_tidal = bool(
                    (Config.STREAMRIP_TIDAL_EMAIL or "").strip()
                    and (Config.STREAMRIP_TIDAL_PASSWORD or "").strip()
                )

                if not (has_deezer or has_qobuz or has_tidal):
                    LOGGER.error(
                        "❌ Apple Music playlist requires streaming service credentials for Last.fm conversion!"
                    )
                    LOGGER.error(
                        "Please configure credentials for Deezer, Qobuz, or Tidal via:"
                    )
                    LOGGER.error("  /botsettings → Streamrip → Credential settings")
                    return False

                return True

            else:
                # Unknown platform - allow download attempt (like Deezer logic)
                return True

        except Exception as e:
            LOGGER.error(f"Error validating authentication: {e}")
            # Don't block download on validation errors
            return True

    async def _convert_url_for_streamrip(self, url: str) -> str:
        """Convert URL to streamrip-compatible format if needed"""
        try:
            import re  # Import re module at the beginning

            url_lower = url.lower()

            # Handle Tidal mix URLs - convert to listen.tidal.com format
            if "tidal.com/browse/mix/" in url_lower:
                # Extract mix ID from browse URL
                mix_match = re.search(
                    r"tidal\.com/browse/mix/([^/?]+)", url, re.IGNORECASE
                )
                if mix_match:
                    mix_id = mix_match.group(1)
                    # Try multiple URL formats for better compatibility
                    return f"https://listen.tidal.com/playlist/{mix_id}"
                return url

            # Handle other Tidal browse URLs - convert to listen.tidal.com format
            if "tidal.com/browse/" in url_lower:
                # Convert browse URLs to listen URLs for better compatibility
                converted_url = url.replace("tidal.com/browse/", "listen.tidal.com/")
                if converted_url != url:
                    return converted_url

            # Handle Qobuz URLs - normalize to streamrip-compatible format
            elif "qobuz.com" in url_lower:
                converted_url = url

                # Remove region prefix for better compatibility
                if re.search(r"/[a-z]{2}-[a-z]{2}/", url, re.IGNORECASE):
                    converted_url = re.sub(
                        r"/[a-z]{2}-[a-z]{2}/",
                        "/",
                        converted_url,
                        flags=re.IGNORECASE,
                    )

                # Convert /interpreter/ to /artist/ for streamrip compatibility
                if "/interpreter/" in converted_url.lower():
                    converted_url = re.sub(
                        r"/interpreter/",
                        "/artist/",
                        converted_url,
                        flags=re.IGNORECASE,
                    )

                if converted_url != url:
                    return converted_url

            # Handle Deezer page.link URLs - these should be resolved by streamrip
            elif "dzr.page.link" in url_lower:
                return url

            # Handle SoundCloud URLs - ensure proper format
            elif "soundcloud.com" in url_lower:
                # SoundCloud URLs should work as-is
                return url

            # For all other URLs, return as-is
            return url

        except Exception as e:
            LOGGER.warning(f"Error converting URL: {e}")
            return url

    async def _retry_download_with_isolation(self) -> bool:
        """Retry download with enhanced process isolation for asyncio event loop errors"""
        try:
            # Add a small delay to let any hanging processes clean up
            await asyncio.sleep(2)

            # Force garbage collection to clean up any lingering objects
            import gc

            gc.collect()

            # Get the original URL for retry
            download_url = getattr(self, "_download_url", self.listener.url)
            converted_url = await self._convert_url_for_streamrip(download_url)

            # Get quality and codec from the current instance
            quality = getattr(self, "_quality", 3)  # Default to quality 3
            codec = getattr(self, "_codec", "flac")  # Default to flac

            # Map codec to streamrip-compatible format
            mapped_codec = self._map_codec_for_streamrip(codec)

            # Build codec command part
            codec_cmd_part = ""
            if mapped_codec is not None:
                codec_cmd_part = f'cmd.extend(["--codec", "{mapped_codec}"])'
            else:
                codec_cmd_part = "# No codec specified - download in native format"

            # Build command with additional isolation flags
            cmd = [
                "python3",
                "-c",
                f'''
import asyncio
import sys
import os
import subprocess

# Create a completely isolated event loop
try:
    # Close any existing event loop
    try:
        loop = asyncio.get_event_loop()
        if not loop.is_closed():
            loop.close()
    except:
        pass

    # Create new isolated event loop
    asyncio.set_event_loop(asyncio.new_event_loop())

    # Run streamrip in completely isolated subprocess
    cmd = ["rip", "--quality", "{quality}"]

    # Add codec if specified
    {codec_cmd_part}

    # Add --no-db flag only if database is disabled in bot settings
    from bot.helper.streamrip_utils.streamrip_config import streamrip_config
    if not streamrip_config.is_database_enabled():
        cmd.append("--no-db")

    cmd.extend(["--verbose", "url", "{converted_url}"])

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)

    sys.exit(result.returncode)

except Exception as e:
    print(f"Isolated retry failed: {{e}}", file=sys.stderr)
    sys.exit(1)
''',
            ]

            # Create completely isolated subprocess
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(Path.home()),
                # Maximum isolation
                preexec_fn=None if os.name == "nt" else os.setsid,
            )

            # Wait for completion with timeout
            try:
                await asyncio.wait_for(
                    process.communicate(),
                    timeout=360,  # 6 minute timeout for retry
                )

                return process.returncode == 0

            except TimeoutError:
                try:
                    process.kill()
                    await process.wait()
                except:
                    pass
                return False

        except Exception as e:
            LOGGER.error(f"Retry exception: {e}")
            return False

    async def _reset_streamrip_config_if_needed(self):
        """Reset streamrip config if it's invalid"""
        try:
            # First, try to create a proper config using streamrip's built-in method
            config_dir = Path.home() / ".config" / "streamrip"
            config_file = config_dir / "config.toml"

            # If config doesn't exist or is invalid, create a new one
            if not config_file.exists():
                # Use streamrip's config creation (v2.1.0 syntax)
                create_process = await asyncio.create_subprocess_exec(
                    "rip",
                    "config",
                    "open",  # Remove --open, use 'open' subcommand
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    stdin=asyncio.subprocess.PIPE,
                )

                # Get Deezer ARL from bot config
                deezer_arl = ""
                try:
                    from bot.core.config_manager import Config

                    deezer_arl = Config.STREAMRIP_DEEZER_ARL or ""
                except Exception:
                    pass

                # Provide ARL input
                create_input = deezer_arl.encode() + b"\n" if deezer_arl else b"\n"

                try:
                    await asyncio.wait_for(
                        create_process.communicate(input=create_input), timeout=15
                    )

                    if create_process.returncode != 0:
                        # Fallback to safe config creation
                        await self._create_safe_config_after_reset()

                except TimeoutError:
                    create_process.kill()
                    await create_process.wait()
                    await self._create_safe_config_after_reset()

        except Exception as e:
            LOGGER.error(f"Error checking/creating streamrip config: {e}")
            # Fallback to safe config creation
            await self._create_safe_config_after_reset()

    async def _create_manual_config(self):
        """Deprecated: Use safe config generation instead"""
        await self._create_safe_config_after_reset()

    def cancel_download(self):
        """Cancel the download"""
        self._is_cancelled = True

        # Cancel the media download if possible
        if self._media and hasattr(self._media, "cancel"):
            self._media.cancel()

        # Clean up temporary files
        self._cleanup_temp_files()

    def _cleanup_temp_files(self):
        """Clean up temporary files created during download"""
        try:
            if hasattr(self, "_temp_files"):
                import shutil

                for temp_path in self._temp_files:
                    try:
                        if os.path.exists(temp_path):
                            if os.path.isdir(temp_path):
                                shutil.rmtree(temp_path)
                            else:
                                os.unlink(temp_path)
                    except Exception as e:
                        LOGGER.error(f"Error cleaning temp file {temp_path}: {e}")
                self._temp_files.clear()
        except Exception as e:
            LOGGER.error(f"Error during temp file cleanup: {e}")


async def add_streamrip_download(
    listener,
    url: str,
    quality: int | None = None,
    codec: str | None = None,
    force: bool = False,
):
    """Add streamrip download to queue"""
    if not STREAMRIP_AVAILABLE:
        await send_status_message(listener.message, "❌ Streamrip is not available!")
        return

    # Check if streamrip is enabled
    if not Config.STREAMRIP_ENABLED:
        await send_status_message(
            listener.message, "❌ Streamrip downloads are disabled!"
        )
        return

    # Parse URL to validate and get platform/media_type info
    from bot.helper.streamrip_utils.url_parser import (
        is_streamrip_url,
        parse_streamrip_url,
    )

    if not await is_streamrip_url(url):
        await send_status_message(listener.message, "❌ Invalid streamrip URL!")
        return

    # Set platform and media_type attributes if not already set
    if not hasattr(listener, "platform") or not hasattr(listener, "media_type"):
        try:
            parsed = await parse_streamrip_url(url)
            if parsed:
                platform, media_type, _ = parsed
                listener.platform = platform
                listener.media_type = media_type
            else:
                # Fallback values if parsing fails
                listener.platform = "Unknown"
                listener.media_type = "Unknown"
        except Exception as e:
            LOGGER.error(f"Failed to parse URL for platform info: {e}")
            # Set fallback values
            listener.platform = "Unknown"
            listener.media_type = "Unknown"

    # Create download helper
    download_helper = StreamripDownloadHelper(listener)

    # Set streamrip-specific attributes on the listener
    listener.url = url
    listener.quality = quality
    listener.codec = codec
    listener.force_download = force

    # Check running tasks and queue management
    add_to_queue, event = await check_running_tasks(listener)

    # Add to task dict with proper status
    async with task_dict_lock:
        task_dict[listener.mid] = StreamripDownloadStatus(
            listener, download_helper, queued=add_to_queue
        )

    # Handle queuing
    if add_to_queue:
        LOGGER.info(f"Added streamrip download to queue: {url}")
        await send_status_message(listener.message, "⏳ Added to download queue!")
        await event.wait()
        if listener.is_cancelled:
            return
        LOGGER.info(f"Start from Queued/Download: {listener.name}")

    # Update task dict for active download
    async with task_dict_lock:
        task_dict[listener.mid] = StreamripDownloadStatus(
            listener, download_helper, queued=False
        )

    # Send status message automatically when download starts (instead of initial download start message)
    await send_status_message(listener.message)

    try:
        download_success = await download_helper.download(url, quality, codec)

        # If download was successful, trigger the upload process
        if download_success:
            LOGGER.info("Streamrip download completed, triggering upload process...")
            # Initialize media tools settings before upload (only for specialized listeners)
            if hasattr(listener, "initialize_media_tools"):
                await listener.initialize_media_tools()
            await listener.on_download_complete()
        else:
            LOGGER.error("Streamrip download failed")
            await listener.on_download_error("Download failed")
    except Exception as e:
        LOGGER.error(f"Exception in streamrip download: {e}")
        import traceback

        LOGGER.error(f"Traceback: {traceback.format_exc()}")
        await listener.on_download_error(f"Download error: {e}")
    finally:
        # Clean up any remaining aiohttp sessions
        try:
            from bot.helper.streamrip_utils.search_handler import (
                cleanup_all_streamrip_sessions,
            )

            await cleanup_all_streamrip_sessions()

            # Additional cleanup for any remaining sessions
            import gc

            import aiohttp

            # Force garbage collection to find unclosed sessions
            gc.collect()

            # Close any remaining aiohttp sessions
            for obj in gc.get_objects():
                if isinstance(obj, aiohttp.ClientSession | aiohttp.TCPConnector):
                    try:
                        if not obj.closed:
                            await obj.close()
                    except Exception:
                        pass

            # Final garbage collection
            gc.collect()

        except Exception as cleanup_error:
            # Only log if it's not a common cleanup error
            if "session" not in str(cleanup_error).lower():
                LOGGER.warning(f"Session cleanup error: {cleanup_error}")
