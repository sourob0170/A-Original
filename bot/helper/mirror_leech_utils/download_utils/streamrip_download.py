import asyncio
import os
import re
import time
from pathlib import Path
from typing import Any

from bot import (
    DOWNLOAD_DIR,
    LOGGER,
    queue_dict_lock,
    task_dict,
    task_dict_lock,
)
from bot.core.config_manager import Config
# from bot.helper.ext_utils.limit_checker import limit_checker # Removed
# from bot.helper.mirror_leech_utils.status_utils.queue_status import QueueStatus # Removed
# from bot.helper.mirror_leech_utils.status_utils.streamrip_status import StreamripDownloadStatus # Removed
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
    from streamrip.media import Album, Artist, Label, Playlist, Track

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
    TRACK_ESTIMATES = {"track": 1, "album": 12, "playlist": 25}

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
        "_completed_tracks",
        "_current_track",
        "_download_path",
        "_download_url",
        "_eta",
        "_is_cancelled",
        "_is_downloading",
        "_last_downloaded",
        "_media",
        "_quality",
        "_size",
        "_speed",
        "_start_time",
        "_temp_files",
        "_total_tracks",
        "listener",
    )

    def __init__(self, listener):
        self.listener = listener
        self._last_downloaded = 0
        self._size = 0
        self._start_time = time.time()
        self._is_cancelled = False
        self._download_path = None
        self._current_track = ""
        self._total_tracks = 0
        self._completed_tracks = 0
        self._speed = 0
        self._eta = 0
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
    def speed(self):
        """Get current download speed"""
        return self._speed

    @property
    def processed_bytes(self):
        """Get processed bytes"""
        return self._last_downloaded

    @property
    def size(self):
        """Get total size"""
        return self._size

    @property
    def eta(self):
        """Get estimated time of arrival"""
        return self._eta

    @property
    def current_track(self):
        """Get current track being downloaded"""
        return self._current_track

    @property
    def progress(self):
        """Get download progress"""
        if self._total_tracks > 0:
            return (self._completed_tracks / self._total_tracks) * 100
        return 0

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

            # Initialize progress tracking
            self._is_downloading = True
            self._current_track = f"Downloading from {platform.title()}"

            # Use cached track estimates
            self._total_tracks = self.TRACK_ESTIMATES.get(media_type, 1)

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

            # Get media info for progress tracking
            if hasattr(self._media, "tracks"):
                self._total_tracks = len(self._media.tracks)
            elif hasattr(self._media, "track_count"):
                self._total_tracks = self._media.track_count
            else:
                self._total_tracks = 1

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
                    # Update final progress
                    self._completed_tracks = self._total_tracks
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
                    LOGGER.error("Streamrip 'rip' command not found in PATH")
                    LOGGER.error(
                        f"which rip stderr: {stderr_check.decode() if stderr_check else 'None'}"
                    )
                    return False
                stdout_check.decode().strip()
            except Exception as check_error:
                LOGGER.error(f"Error checking streamrip availability: {check_error}")
                return False

            # Always regenerate config to ensure latest settings are applied
            await self._regenerate_streamrip_config()

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

            # Start progress monitoring in background
            progress_task = asyncio.create_task(self._start_progress_monitoring())

            try:
                # Remove timeout restrictions for streamrip downloads (like Deezer)

                # Send empty input to stdin to prevent hanging on prompts
                # For Deezer ARL prompts, send newline to skip
                stdin_input = b"\n"
                stdout, stderr = await process.communicate(input=stdin_input)

                # Log detailed output for debugging
                stdout_text = stdout.decode() if stdout else ""

                self._is_downloading = False
                # Cancel progress monitoring
                progress_task.cancel()
            except Exception as e:
                # Handle any other errors
                LOGGER.error(f"Streamrip process error: {e}")
                self._is_downloading = False
                progress_task.cancel()
                try:
                    process.kill()
                    await process.wait()
                except Exception as kill_error:
                    LOGGER.error(f"Error killing process: {kill_error}")
                return False

            # Check result
            if process.returncode == 0:
                stdout_text = stdout.decode() if stdout else ""

                # Check if tracks were skipped due to being already downloaded
                if (
                    "Skipping track" in stdout_text
                    and "Marked as downloaded" in stdout_text
                ):
                    pass  # Normal behavior - tracks already downloaded

                return True

            # Handle errors
            error_output = stderr.decode() if stderr else "Unknown error"
            stdout_text = stdout.decode() if stdout else ""

            LOGGER.error(
                f"Streamrip CLI failed with return code {process.returncode}"
            )
            LOGGER.error(f"Error output: {error_output}")
            if stdout_text:
                LOGGER.error(f"Standard output: {stdout_text}")

            # Enhanced debugging for "Unknown error" cases
            if error_output == "Unknown error" or not error_output.strip():
                LOGGER.error(
                    f"⚠️ Streamrip returned no error details - return code: {process.returncode}"
                )

                # Check if this might be a credential issue
                if process.returncode == 1:
                    LOGGER.error("💡 Return code 1 often indicates:")
                    LOGGER.error("  1. Authentication failure (invalid credentials)")
                    LOGGER.error("  2. Content not available (region restrictions)")
                    LOGGER.error("  3. Subscription limitations")
                    LOGGER.error("  4. Network connectivity issues")
                    LOGGER.error("  5. Tidal API rate limiting")

                    # Check if URL conversion worked
                    converted_url = await self._convert_url_for_streamrip(
                        download_url
                    )
                    if converted_url != download_url:
                        LOGGER.error(
                            f"✅ URL conversion worked: {download_url} → {converted_url}"
                        )
                        LOGGER.error(
                            "❌ Issue is likely with Tidal credentials or content access"
                        )

                        # Provide specific Tidal troubleshooting
                        if "tidal.com" in download_url.lower():
                            LOGGER.error("🎵 Tidal-specific troubleshooting:")
                            LOGGER.error(
                                "  1. Check if your Tidal account has an active subscription"
                            )
                            LOGGER.error(
                                "  2. Verify Tidal credentials in /botsettings → Streamrip → Tidal"
                            )
                            LOGGER.error(
                                "  3. Check if the mix/playlist is public and accessible"
                            )
                            LOGGER.error(
                                "  4. Try a different Tidal URL (album/track) to test credentials"
                            )
                            LOGGER.error(
                                "  5. Ensure your Tidal account region matches the content region"
                            )

                            # Test with a simple Tidal track to verify credentials
                            LOGGER.error(
                                "💡 Consider testing with a simple Tidal track first:"
                            )
                            LOGGER.error(
                                "   Example: https://tidal.com/browse/track/123456789"
                            )
                    else:
                        LOGGER.error(
                            "⚠️ No URL conversion applied - check URL format"
                        )

            # Check for specific error patterns
            if "No such file or directory" in error_output:
                LOGGER.error(
                    "Streamrip CLI not found. Please ensure streamrip is installed and 'rip' command is available."
                )
            elif (
                "Invalid URL" in error_output or "URL not supported" in error_output
            ):
                LOGGER.error("The provided URL is not supported by streamrip.")
            elif "Authentication" in error_output or "login" in error_output.lower():
                LOGGER.error(
                    "Authentication failed. Please check your streamrip credentials."
                )
            # Enhanced error detection for all services (like Deezer)
            elif (
                "enter your arl" in error_output.lower()
                or "enter your arl" in stdout_text.lower()
                or "authenticationerror" in stdout_text.lower()
                or "authentication" in error_output.lower()
            ):
                LOGGER.error(
                    "🔐 Deezer authentication failed. This might be due to:"
                )
                LOGGER.error("  1. Deezer ARL expired or invalid")
                LOGGER.error(
                    "  2. Deezer ARL not properly configured in streamrip config"
                )
                LOGGER.error(
                    "  3. Streamrip config file corruption or version mismatch"
                )
                LOGGER.error("  4. Deezer ARL format issue or invalid characters")
                LOGGER.error(
                    "  5. Config regeneration failed to include ARL properly"
                )
                LOGGER.error(
                    "💡 Check /botsettings → Streamrip → Credential settings → Deezer arl"
                )
                LOGGER.error(
                    "💡 Ensure ARL is a long string (192+ characters) without quotes"
                )
                LOGGER.error("💡 Get a fresh ARL from your Deezer account cookies")

                # Check if ARL is configured
                from bot.core.config_manager import Config

                deezer_arl = getattr(Config, "STREAMRIP_DEEZER_ARL", "")
                if not deezer_arl:
                    LOGGER.error("❌ No Deezer ARL configured in bot settings!")
                    LOGGER.error(
                        "💡 Configure Deezer ARL in /botsettings → Streamrip → Deezer ARL"
                    )
                else:
                    LOGGER.error(f"Current ARL length: {len(deezer_arl)} characters")
                    if len(deezer_arl) < 192:
                        LOGGER.error(
                            "❌ ARL appears too short - should be 192+ characters"
                        )
                    else:
                        LOGGER.error(
                            "⚠️ ARL length looks correct but authentication failed - ARL may be expired"
                        )
            elif (
                "enter your qobuz email" in error_output.lower()
                or "enter your qobuz email" in stdout_text.lower()
                or "enter your qobuz password" in error_output.lower()
                or "enter your qobuz password" in stdout_text.lower()
            ):
                LOGGER.error(
                    "Qobuz credentials prompt detected. This might be due to:"
                )
                LOGGER.error(
                    "  1. Qobuz email/password not properly configured in streamrip config"
                )
                LOGGER.error(
                    "  2. Streamrip config file corruption or version mismatch"
                )
                LOGGER.error(
                    "  3. Qobuz credentials format issue or invalid characters"
                )
                LOGGER.error(
                    "  4. Config regeneration failed to include credentials properly"
                )
                LOGGER.error(
                    "💡 Check /botsettings → Streamrip → Credential settings → Qobuz"
                )
                LOGGER.error("💡 Ensure email is valid and password is correct")
            elif (
                "event loop is closed" in error_output.lower()
                or "runtimeerror" in error_output.lower()
            ):
                LOGGER.error(
                    "Streamrip internal error detected. This might be due to:"
                )
                LOGGER.error(
                    "  1. Streamrip asyncio event loop issue (internal bug)"
                )
                LOGGER.error("  2. Network connectivity problems during download")
                LOGGER.error("  3. Streamrip version compatibility issue")
                LOGGER.error("  4. Try again - this is often a temporary issue")
                LOGGER.error(
                    "💡 This is a known streamrip internal issue, not a credential problem"
                )

                # Attempt automatic retry for asyncio event loop errors
                LOGGER.info(
                    "🔄 Attempting automatic retry for asyncio event loop error..."
                )
                return await self._retry_download_with_isolation()
            elif "qobuz" in error_output.lower() and (
                "error" in error_output.lower() or "failed" in error_output.lower()
            ):
                LOGGER.error("Qobuz-specific error detected. This might be due to:")
                LOGGER.error("  1. Invalid Qobuz credentials")
                LOGGER.error("  2. Qobuz account region restrictions")
                LOGGER.error("  3. Qobuz subscription limitations")
                LOGGER.error("  4. Album/track not available in your region")
                LOGGER.error("  5. Temporary email provider blocked by Qobuz")
            elif "tidal" in error_output.lower() and (
                "error" in error_output.lower() or "failed" in error_output.lower()
            ):
                LOGGER.error("Tidal-specific error detected. This might be due to:")
                LOGGER.error("  1. Invalid Tidal credentials")
                LOGGER.error("  2. Tidal account region restrictions")
                LOGGER.error("  3. Tidal subscription limitations")
                LOGGER.error("  4. Album/track not available in your region")
                LOGGER.error("  5. Temporary email provider blocked by Tidal")
                LOGGER.error(
                    "💡 URL conversion successful - this is likely a credential/subscription issue"
                )
            elif "deezer" in error_output.lower() and (
                "error" in error_output.lower() or "failed" in error_output.lower()
            ):
                LOGGER.error(
                    "🎵 Deezer-specific error detected. This might be due to:"
                )
                LOGGER.error("  1. Invalid Deezer ARL token")
                LOGGER.error("  2. Deezer ARL token expired")
                LOGGER.error("  3. Deezer account region restrictions")
                LOGGER.error("  4. Album/track not available in your region")
                LOGGER.error("  5. Deezer subscription limitations")
                LOGGER.error(
                    "💡 Try updating your Deezer ARL from fresh browser cookies"
                )

                # Check if we have a fresh ARL available in bot config
                from bot.core.config_manager import Config

                current_arl = getattr(Config, "STREAMRIP_DEEZER_ARL", "")

                if current_arl:
                    LOGGER.error(
                        f"💡 Current ARL in config: ***{current_arl[-10:]} (length: {len(current_arl)})"
                    )

                    # Validate ARL format
                    if len(current_arl) < 150:
                        LOGGER.error(
                            "⚠️ ARL appears too short - should be 150+ characters"
                        )
                        LOGGER.error(
                            "💡 Get a fresh ARL from your Deezer account browser cookies"
                        )
                    else:
                        # Try to regenerate config with current ARL
                        LOGGER.error(
                            "🔄 Attempting to regenerate config with current ARL..."
                        )
                        try:
                            # Clear cached config to force regeneration
                            self._cached_config = None
                            await self._regenerate_streamrip_config()
                            LOGGER.info(
                                "✅ Config regenerated - you may retry the download"
                            )
                        except Exception as config_error:
                            LOGGER.error(
                                f"Failed to regenerate config: {config_error}"
                            )
                            LOGGER.error(
                                "💡 Please check your Deezer ARL in /botsettings"
                            )
                else:
                    LOGGER.error("❌ No Deezer ARL found in bot configuration!")
                    LOGGER.error(
                        "💡 Please configure Deezer ARL in /botsettings → Streamrip → Deezer ARL"
                    )
                    LOGGER.error(
                        "💡 Get ARL from your Deezer account browser cookies"
                    )
            elif "soundcloud" in error_output.lower() and (
                "error" in error_output.lower() or "failed" in error_output.lower()
            ):
                LOGGER.error(
                    "SoundCloud-specific error detected. This might be due to:"
                )
                LOGGER.error("  1. Invalid SoundCloud client ID")
                LOGGER.error("  2. SoundCloud API rate limiting")
                LOGGER.error("  3. Track/playlist privacy restrictions")
                LOGGER.error("  4. SoundCloud account limitations")
                LOGGER.error("  5. Track not available for download")
            elif (
                "last.fm" in error_output.lower() or "lastfm" in error_output.lower()
            ):
                LOGGER.error(
                    "Last.fm-specific error detected. This might be due to:"
                )
                LOGGER.error("  1. Last.fm playlist not accessible")
                LOGGER.error("  2. Primary streaming service credentials missing")
                LOGGER.error("  3. Tracks not found on primary streaming service")
                LOGGER.error("  4. Last.fm API limitations")
            elif "spotify" in error_output.lower() and (
                "error" in error_output.lower() or "failed" in error_output.lower()
            ):
                LOGGER.error(
                    "Spotify-specific error detected. This might be due to:"
                )
                LOGGER.error("  1. Spotify playlist not accessible")
                LOGGER.error("  2. Spotify to Last.fm conversion failed")
                LOGGER.error("  3. Primary streaming service credentials missing")
                LOGGER.error("  4. Tracks not found on streaming services")
            elif (
                "apple music" in error_output.lower()
                or "music.apple.com" in error_output.lower()
            ):
                LOGGER.error(
                    "Apple Music-specific error detected. This might be due to:"
                )
                LOGGER.error("  1. Apple Music playlist not accessible")
                LOGGER.error("  2. Apple Music to Last.fm conversion failed")
                LOGGER.error("  3. Primary streaming service credentials missing")
                LOGGER.error("  4. Tracks not found on streaming services")
            elif (
                "timeout" in error_output.lower()
                or "timed out" in error_output.lower()
            ):
                LOGGER.error("Download timed out. This might be due to:")
                LOGGER.error("  1. Slow network connection")
                LOGGER.error("  2. Large album size")
                LOGGER.error("  3. Server-side issues")
                LOGGER.error("  4. Authentication hanging (check credentials)")
            elif "does not exist" in error_output.lower() and (
                "key" in error_output.lower() or "section" in error_output.lower()
            ):
                LOGGER.error(
                    "Missing config section/key detected in streamrip config. This might be due to:"
                )
                LOGGER.error("  1. Incomplete configuration file")
                LOGGER.error("  2. Outdated config format")
                LOGGER.error("  3. Missing required sections")
                LOGGER.error("💡 Regenerating the streamrip config file...")
                # Attempt to regenerate config
                try:
                    await self._regenerate_streamrip_config()
                    LOGGER.info(
                        "✅ Config regenerated with missing sections, you may retry the download"
                    )
                except Exception as config_error:
                    LOGGER.error(f"Failed to regenerate config: {config_error}")
            elif (
                "typeerror" in error_output.lower()
                and "string formatting" in error_output.lower()
            ):
                LOGGER.error(
                    "String formatting error detected in streamrip. This might be due to:"
                )
                LOGGER.error("  1. Invalid configuration file format")
                LOGGER.error("  2. Corrupted streamrip config")
                LOGGER.error("  3. Version compatibility issues")
                LOGGER.error("💡 Try regenerating the streamrip config file")
                # Attempt to regenerate config
                try:
                    await self._regenerate_streamrip_config()
                    LOGGER.info("Config regenerated, you may retry the download")
                except Exception as config_error:
                    LOGGER.error(f"Failed to regenerate config: {config_error}")
            elif (
                "ffmpeg" in error_output.lower()
                or "could not find ffmpeg" in error_output.lower()
            ):
                LOGGER.error("FFMPEG-related error detected. This might be due to:")
                LOGGER.error("  1. FFMPEG not installed or not found in PATH")
                LOGGER.error("  2. FFMPEG executable path misconfigured")
                LOGGER.error("  3. Audio conversion failed during processing")
                LOGGER.error(f"  4. Current FFMPEG path: {self._get_ffmpeg_path()}")
                LOGGER.error(
                    "💡 Try installing FFMPEG or check if 'xtra' binary exists"
                )
            elif (
                "conversion" in error_output.lower()
                and "failed" in error_output.lower()
            ):
                LOGGER.error("Audio conversion failed. This might be due to:")
                LOGGER.error("  1. FFMPEG not available for audio conversion")
                LOGGER.error("  2. Unsupported audio format conversion")
                LOGGER.error("  3. Insufficient disk space during conversion")
                LOGGER.error(f"  4. FFMPEG path: {self._get_ffmpeg_path()}")
            elif (
                "conversionconfig" in error_output.lower()
                and "unexpected keyword argument" in error_output.lower()
            ):
                LOGGER.error("Streamrip config compatibility error detected:")
                LOGGER.error(
                    "  1. The streamrip version doesn't support 'ffmpeg_executable' in config"
                )
                LOGGER.error(
                    "  2. This is a known compatibility issue with certain streamrip versions"
                )
                LOGGER.error(
                    "  3. The bot will regenerate config without the problematic field"
                )
                LOGGER.info("🔄 Attempting to fix config compatibility...")
                # Trigger config regeneration without ffmpeg_executable
                await self._create_compatible_config()
            elif "error loading config" in error_output.lower():
                LOGGER.error("Streamrip config loading error detected:")
                LOGGER.error("  1. Config file may be corrupted or incompatible")
                LOGGER.error("  2. Try running 'rip config reset' manually")
                LOGGER.error("  3. The bot will attempt to regenerate the config")

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
            else:
                search_paths = self._cached_search_paths

            # Optimized file search with list comprehension and early filtering
            for search_path in search_paths:
                try:
                    # Use list comprehension for better performance
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
                        # Move to our target folder
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
        """Create a streamrip config compatible with the current version"""
        try:
            # Use the fallback config which doesn't include ffmpeg_executable
            config_content = self._create_fallback_config()

            config_dir = Path.home() / ".config" / "streamrip"
            config_dir.mkdir(parents=True, exist_ok=True)
            config_file = config_dir / "config.toml"

            import aiofiles

            async with aiofiles.open(config_file, "w") as f:
                await f.write(config_content)

            return True
        except Exception as e:
            LOGGER.error(f"Failed to create compatible config: {e}")
            return False

    def _create_default_config(self) -> str:
        """Create a comprehensive streamrip config with all bot settings"""
        try:
            # Return cached config if available
            if self._cached_config:
                return self._cached_config

            # Get all streamrip settings from bot config
            from bot.core.config_manager import Config

            # Creating comprehensive streamrip config

            config_template = """[downloads]
# Folder where tracks are downloaded to
folder = "{downloads_folder}"
# Put Qobuz albums in a 'Qobuz' folder, Tidal albums in 'Tidal' etc.
source_subdirectories = {source_subdirectories}
# Put tracks in an album with 2 or more discs into a subfolder named `Disc N`
disc_subdirectories = {disc_subdirectories}
# Download (and convert) tracks all at once, instead of sequentially.
# If you are converting the tracks, or have fast internet, this will
# substantially improve processing speed.
concurrency = {concurrency}
# The maximum number of tracks to download at once
# If you have very fast internet, you will benefit from a higher value,
# A value that is too high for your bandwidth may cause slowdowns
# Set to -1 for no limit
max_connections = {max_connections}
# Max number of API requests per source to handle per minute
# Set to -1 for no limit
requests_per_minute = {requests_per_minute}
# Verify SSL certificates for API connections
# Set to false if you encounter SSL certificate verification errors (not recommended)
verify_ssl = {verify_ssl}

[qobuz]
# 1: 320kbps MP3, 2: 16/44.1, 3: 24/<=96, 4: 24/>=96
quality = {qobuz_quality}
# This will download booklet pdfs that are included with some albums
download_booklets = {qobuz_download_booklets}
# Authenticate to Qobuz using auth token? Value can be true/false only
use_auth_token = {qobuz_use_auth_token}
# Enter your userid if the above use_auth_token is set to true, else enter your email
email_or_userid = "{qobuz_email}"
# Enter your auth token if the above use_auth_token is set to true, else enter the md5 hash of your plaintext password
password_or_token = "{qobuz_password}"
# Do not change
app_id = "{qobuz_app_id}"
# Do not change
secrets = {qobuz_secrets}

[tidal]
# 0: 256kbps AAC, 1: 320kbps AAC, 2: 16/44.1 "HiFi" FLAC, 3: 24/44.1 "MQA" FLAC
quality = {tidal_quality}
# This will download videos included in Video Albums.
download_videos = {tidal_download_videos}
# Do not change any of the fields below
user_id = "{tidal_user_id}"
country_code = "{tidal_country_code}"
access_token = "{tidal_access_token}"
refresh_token = "{tidal_refresh_token}"
# Tokens last 1 week after refresh. This is the Unix timestamp of the expiration
# time. If you haven't used streamrip in more than a week, you may have to log
# in again using `rip config --tidal`
token_expiry = "{tidal_token_expiry}"

[deezer]
# 0, 1, or 2
# This only applies to paid Deezer subscriptions. Those using deezloader
# are automatically limited to quality = 1
quality = {deezer_quality}
# An authentication cookie that allows streamrip to use your Deezer account
# See https://github.com/nathom/streamrip/wiki/Finding-Your-Deezer-ARL-Cookie
# for instructions on how to find this
arl = "{deezer_arl}"
# This allows for free 320kbps MP3 downloads from Deezer
# If an arl is provided, deezloader is never used
use_deezloader = {deezer_use_deezloader}
# This warns you when the paid deezer account is not logged in and rip falls
# back to deezloader, which is unreliable
deezloader_warnings = {deezer_deezloader_warnings}

[soundcloud]
# Only 0 is available for now
quality = {soundcloud_quality}
# This changes periodically, so it needs to be updated
client_id = "{soundcloud_client_id}"
app_version = "{soundcloud_app_version}"

[youtube]
# Only 0 is available for now
quality = {youtube_quality}
# Download the video along with the audio
download_videos = {youtube_download_videos}
# The path to download the videos to
video_downloads_folder = "{youtube_video_downloads_folder}"

[database]
# Create a database that contains all the track IDs downloaded so far
# Any time a track logged in the database is requested, it is skipped
# This can be disabled temporarily with the --no-db flag
downloads_enabled = {database_downloads_enabled}
# Path to the downloads database
downloads_path = "{database_downloads_path}"
# If a download fails, the item ID is stored here. Then, `rip repair` can be
# called to retry the downloads
failed_downloads_enabled = {database_failed_downloads_enabled}
failed_downloads_path = "{database_failed_downloads_path}"

# Convert tracks to a codec after downloading them.
[conversion]
enabled = {conversion_enabled}
# FLAC, ALAC, OPUS, MP3, VORBIS, or AAC
codec = "{conversion_codec}"
# In Hz. Tracks are downsampled if their sampling rate is greater than this.
# Value of 48000 is recommended to maximize quality and minimize space
sampling_rate = {conversion_sampling_rate}
# Only 16 and 24 are available. It is only applied when the bit depth is higher
# than this value.
bit_depth = {conversion_bit_depth}
# Only applicable for lossy codecs
lossy_bitrate = {conversion_lossy_bitrate}

# Filter a Qobuz artist's discography. Set to 'true' to turn on a filter.
# This will also be applied to other sources, but is not guaranteed to work correctly
[qobuz_filters]
# Remove Collectors Editions, live recordings, etc.
extras = {qobuz_filters_extras}
# Picks the highest quality out of albums with identical titles.
repeats = {qobuz_filters_repeats}
# Remove EPs and Singles
non_albums = {qobuz_filters_non_albums}
# Remove albums whose artist is not the one requested
features = {qobuz_filters_features}
# Skip non studio albums
non_studio_albums = {qobuz_filters_non_studio_albums}
# Only download remastered albums
non_remaster = {qobuz_filters_non_remaster}

[artwork]
# Write the image to the audio file
embed = {artwork_embed}
# The size of the artwork to embed. Options: thumbnail, small, large, original.
# "original" images can be up to 30MB, and may fail embedding.
# Using "large" is recommended.
embed_size = "{artwork_embed_size}"
# If this is set to a value > 0, max(width, height) of the embedded art will be set to this value in pixels
# Proportions of the image will remain the same
embed_max_width = {artwork_embed_max_width}
# Save the cover image at the highest quality as a seperate jpg file
save_artwork = {artwork_save_artwork}
# If this is set to a value > 0, max(width, height) of the saved art will be set to this value in pixels
# Proportions of the image will remain the same
saved_max_width = {artwork_saved_max_width}

[metadata]
# Sets the value of the 'ALBUM' field in the metadata to the playlist's name.
# This is useful if your music library software organizes tracks based on album name.
set_playlist_to_album = {metadata_set_playlist_to_album}
# If part of a playlist, sets the `tracknumber` field in the metadata to the track's
# position in the playlist instead of its position in its album
renumber_playlist_tracks = {metadata_renumber_playlist_tracks}
# The following metadata tags won't be applied
# See https://github.com/nathom/streamrip/wiki/Metadata-Tag-Names for more info
exclude = {metadata_exclude}

# Changes the folder and file names generated by streamrip.
[filepaths]
# Create folders for single tracks within the downloads directory using the folder_format
# template
add_singles_to_folder = {filepaths_add_singles_to_folder}
# Available keys: "albumartist", "title", "year", "bit_depth", "sampling_rate",
# "id", and "albumcomposer"
folder_format = "{folder_fmt}"
# Available keys: "tracknumber", "artist", "albumartist", "composer", "title",
# and "albumcomposer", "explicit"
track_format = "{track_fmt}"
# Only allow printable ASCII characters in filenames.
restrict_characters = {filepaths_restrict_characters}
# Truncate the filename if it is greater than this number of characters
# Setting this to false may cause downloads to fail on some systems
truncate_to = {filepaths_truncate_to}

# Last.fm playlists are downloaded by searching for the titles of the tracks
[lastfm]
# The source on which to search for the tracks.
source = "{lastfm_source}"
# If no results were found with the primary source, the item is searched for
# on this one.
fallback_source = "{lastfm_fallback_source}"

[cli]
# Print "Downloading Album name" etc. to screen
text_output = {cli_text_output}
# Show resolve, download progress bars
progress_bars = {cli_progress_bars}
# The maximum number of search results to show in the interactive menu
max_search_results = {cli_max_search_results}

[misc]
# Metadata to identify this config file. Do not change.
version = "{misc_version}"
# Print a message if a new version of streamrip is available
check_for_updates = {misc_check_for_updates}
"""

            # Format the config template with all the variables
            config = config_template.format(
                downloads_folder=getattr(
                    Config, "DOWNLOAD_DIR", str(Path.home() / "StreamripDownloads")
                ),
                source_subdirectories=str(
                    getattr(Config, "STREAMRIP_SOURCE_SUBDIRECTORIES", False)
                ).lower(),
                disc_subdirectories=str(
                    getattr(Config, "STREAMRIP_DISC_SUBDIRECTORIES", True)
                ).lower(),
                concurrency=str(
                    getattr(Config, "STREAMRIP_CONCURRENCY", True)
                ).lower(),
                max_connections=getattr(Config, "STREAMRIP_MAX_CONNECTIONS", 6),
                requests_per_minute=getattr(
                    Config, "STREAMRIP_REQUESTS_PER_MINUTE", 60
                ),
                verify_ssl=str(
                    getattr(Config, "STREAMRIP_VERIFY_SSL", True)
                ).lower(),
                qobuz_quality=getattr(Config, "STREAMRIP_QOBUZ_QUALITY", 3),
                qobuz_email=getattr(Config, "STREAMRIP_QOBUZ_EMAIL", ""),
                qobuz_password=getattr(Config, "STREAMRIP_QOBUZ_PASSWORD", ""),
                qobuz_download_booklets=str(
                    getattr(Config, "STREAMRIP_QOBUZ_DOWNLOAD_BOOKLETS", True)
                ).lower(),
                qobuz_use_auth_token=str(
                    getattr(Config, "STREAMRIP_QOBUZ_USE_AUTH_TOKEN", False)
                ).lower(),
                qobuz_app_id=getattr(Config, "STREAMRIP_QOBUZ_APP_ID", ""),
                qobuz_secrets=str(getattr(Config, "STREAMRIP_QOBUZ_SECRETS", [])),
                qobuz_filters_extras=str(
                    getattr(Config, "STREAMRIP_QOBUZ_FILTERS_EXTRAS", False)
                ).lower(),
                qobuz_filters_repeats=str(
                    getattr(Config, "STREAMRIP_QOBUZ_FILTERS_REPEATS", False)
                ).lower(),
                qobuz_filters_non_albums=str(
                    getattr(Config, "STREAMRIP_QOBUZ_FILTERS_NON_ALBUMS", False)
                ).lower(),
                qobuz_filters_features=str(
                    getattr(Config, "STREAMRIP_QOBUZ_FILTERS_FEATURES", False)
                ).lower(),
                qobuz_filters_non_studio_albums=str(
                    getattr(
                        Config, "STREAMRIP_QOBUZ_FILTERS_NON_STUDIO_ALBUMS", False
                    )
                ).lower(),
                qobuz_filters_non_remaster=str(
                    getattr(Config, "STREAMRIP_QOBUZ_FILTERS_NON_REMASTER", False)
                ).lower(),
                tidal_quality=getattr(Config, "STREAMRIP_TIDAL_QUALITY", 3),
                tidal_user_id=getattr(Config, "STREAMRIP_TIDAL_USER_ID", ""),
                tidal_country_code=getattr(
                    Config, "STREAMRIP_TIDAL_COUNTRY_CODE", ""
                ),
                tidal_access_token=getattr(
                    Config, "STREAMRIP_TIDAL_ACCESS_TOKEN", ""
                ),
                tidal_refresh_token=getattr(
                    Config, "STREAMRIP_TIDAL_REFRESH_TOKEN", ""
                ),
                tidal_token_expiry=getattr(
                    Config, "STREAMRIP_TIDAL_TOKEN_EXPIRY", "0"
                )
                or "0",
                tidal_download_videos=str(
                    getattr(Config, "STREAMRIP_TIDAL_DOWNLOAD_VIDEOS", True)
                ).lower(),
                deezer_quality=getattr(Config, "STREAMRIP_DEEZER_QUALITY", 2),
                deezer_arl=getattr(Config, "STREAMRIP_DEEZER_ARL", ""),
                deezer_use_deezloader=str(
                    getattr(Config, "STREAMRIP_DEEZER_USE_DEEZLOADER", True)
                ).lower(),
                deezer_deezloader_warnings=str(
                    getattr(Config, "STREAMRIP_DEEZER_DEEZLOADER_WARNINGS", True)
                ).lower(),
                soundcloud_quality=getattr(
                    Config, "STREAMRIP_SOUNDCLOUD_QUALITY", 0
                ),
                soundcloud_client_id=getattr(
                    Config, "STREAMRIP_SOUNDCLOUD_CLIENT_ID", ""
                ),
                soundcloud_app_version=getattr(
                    Config, "STREAMRIP_SOUNDCLOUD_APP_VERSION", ""
                ),
                youtube_quality=getattr(Config, "STREAMRIP_YOUTUBE_QUALITY", 0),
                youtube_download_videos=str(
                    getattr(Config, "STREAMRIP_YOUTUBE_DOWNLOAD_VIDEOS", False)
                ).lower(),
                youtube_video_downloads_folder=getattr(
                    Config,
                    "STREAMRIP_YOUTUBE_VIDEO_DOWNLOADS_FOLDER",
                    f"{getattr(Config, 'DOWNLOAD_DIR', str(Path.home() / 'StreamripDownloads'))}/youtube",
                ),
                database_downloads_enabled=str(
                    getattr(Config, "STREAMRIP_DATABASE_DOWNLOADS_ENABLED", True)
                ).lower(),
                database_downloads_path=getattr(
                    Config, "STREAMRIP_DATABASE_DOWNLOADS_PATH", "./downloads.db"
                ),
                database_failed_downloads_enabled=str(
                    getattr(
                        Config, "STREAMRIP_DATABASE_FAILED_DOWNLOADS_ENABLED", True
                    )
                ).lower(),
                database_failed_downloads_path=getattr(
                    Config,
                    "STREAMRIP_DATABASE_FAILED_DOWNLOADS_PATH",
                    "./failed_downloads.db",
                ),
                conversion_enabled=str(
                    getattr(Config, "STREAMRIP_CONVERSION_ENABLED", False)
                ).lower(),
                conversion_codec=getattr(
                    Config, "STREAMRIP_CONVERSION_CODEC", "ALAC"
                ),
                conversion_sampling_rate=getattr(
                    Config, "STREAMRIP_CONVERSION_SAMPLING_RATE", 48000
                ),
                conversion_bit_depth=getattr(
                    Config, "STREAMRIP_CONVERSION_BIT_DEPTH", 24
                ),
                conversion_lossy_bitrate=getattr(
                    Config, "STREAMRIP_CONVERSION_LOSSY_BITRATE", 320
                ),
                artwork_embed=str(
                    getattr(Config, "STREAMRIP_EMBED_COVER_ART", True)
                ).lower(),
                artwork_embed_size=getattr(
                    Config, "STREAMRIP_COVER_ART_SIZE", "large"
                ),
                artwork_embed_max_width=getattr(
                    Config, "STREAMRIP_ARTWORK_EMBED_MAX_WIDTH", -1
                ),
                artwork_save_artwork=str(
                    getattr(Config, "STREAMRIP_SAVE_COVER_ART", True)
                ).lower(),
                artwork_saved_max_width=getattr(
                    Config, "STREAMRIP_ARTWORK_SAVED_MAX_WIDTH", -1
                ),
                lastfm_source=getattr(Config, "STREAMRIP_LASTFM_SOURCE", "qobuz"),
                lastfm_fallback_source=getattr(
                    Config, "STREAMRIP_LASTFM_FALLBACK_SOURCE", ""
                ),
                metadata_set_playlist_to_album=str(
                    getattr(Config, "STREAMRIP_METADATA_SET_PLAYLIST_TO_ALBUM", True)
                ).lower(),
                metadata_renumber_playlist_tracks=str(
                    getattr(
                        Config, "STREAMRIP_METADATA_RENUMBER_PLAYLIST_TRACKS", True
                    )
                ).lower(),
                metadata_exclude=str(
                    getattr(Config, "STREAMRIP_METADATA_EXCLUDE", [])
                ),
                filepaths_add_singles_to_folder=str(
                    getattr(
                        Config, "STREAMRIP_FILEPATHS_ADD_SINGLES_TO_FOLDER", False
                    )
                ).lower(),
                filepaths_restrict_characters=str(
                    getattr(Config, "STREAMRIP_FILEPATHS_RESTRICT_CHARACTERS", False)
                ).lower(),
                filepaths_truncate_to=getattr(
                    Config, "STREAMRIP_FILEPATHS_TRUNCATE_TO", 120
                ),
                cli_text_output=str(
                    getattr(Config, "STREAMRIP_CLI_TEXT_OUTPUT", True)
                ).lower(),
                cli_progress_bars=str(
                    getattr(Config, "STREAMRIP_CLI_PROGRESS_BARS", True)
                ).lower(),
                cli_max_search_results=getattr(
                    Config, "STREAMRIP_CLI_MAX_SEARCH_RESULTS", 100
                ),
                misc_version=getattr(Config, "STREAMRIP_MISC_VERSION", "2.0.6"),
                misc_check_for_updates=str(
                    getattr(Config, "STREAMRIP_MISC_CHECK_FOR_UPDATES", True)
                ).lower(),
                folder_fmt=getattr(
                    Config,
                    "STREAMRIP_FILEPATHS_FOLDER_FORMAT",
                    "{albumartist} - {title} ({year}) [{container}] [{bit_depth}B-{sampling_rate}kHz]",
                ),
                track_fmt=getattr(
                    Config,
                    "STREAMRIP_FILEPATHS_TRACK_FORMAT",
                    "{tracknumber:02}. {artist} - {title}{explicit}",
                ),
            )

            # Cache the config for future use
            self._cached_config = config.strip()
            return self._cached_config

        except Exception as e:
            LOGGER.error(f"Error creating comprehensive config: {e}")
            # Return comprehensive fallback config with dynamic values
            fallback_downloads_folder = Path.home() / "StreamripDownloads"

            return f"""[downloads]
folder = "{fallback_downloads_folder}"
source_subdirectories = {str(getattr(Config, "STREAMRIP_SOURCE_SUBDIRECTORIES", False)).lower()}
disc_subdirectories = {str(getattr(Config, "STREAMRIP_DISC_SUBDIRECTORIES", True)).lower()}
concurrency = {str(getattr(Config, "STREAMRIP_CONCURRENCY", True)).lower()}
max_connections = {getattr(Config, "STREAMRIP_MAX_CONNECTIONS", 6)}
requests_per_minute = {getattr(Config, "STREAMRIP_REQUESTS_PER_MINUTE", 60)}
verify_ssl = {str(getattr(Config, "STREAMRIP_VERIFY_SSL", True)).lower()}

[qobuz]
email_or_userid = "{getattr(Config, "STREAMRIP_QOBUZ_EMAIL", "")}"
password_or_token = "{getattr(Config, "STREAMRIP_QOBUZ_PASSWORD", "")}"
quality = {getattr(Config, "STREAMRIP_QOBUZ_QUALITY", 3)}
use_auth_token = {str(getattr(Config, "STREAMRIP_QOBUZ_USE_AUTH_TOKEN", False)).lower()}
app_id = "{getattr(Config, "STREAMRIP_QOBUZ_APP_ID", "")}"
download_booklets = {str(getattr(Config, "STREAMRIP_QOBUZ_DOWNLOAD_BOOKLETS", True)).lower()}
secrets = {getattr(Config, "STREAMRIP_QOBUZ_SECRETS", [])!s}

[qobuz_filters]
extras = {str(getattr(Config, "STREAMRIP_QOBUZ_FILTERS_EXTRAS", False)).lower()}
repeats = {str(getattr(Config, "STREAMRIP_QOBUZ_FILTERS_REPEATS", False)).lower()}
non_albums = {str(getattr(Config, "STREAMRIP_QOBUZ_FILTERS_NON_ALBUMS", False)).lower()}
features = {str(getattr(Config, "STREAMRIP_QOBUZ_FILTERS_FEATURES", False)).lower()}
non_studio_albums = {str(getattr(Config, "STREAMRIP_QOBUZ_FILTERS_NON_STUDIO_ALBUMS", False)).lower()}
non_remaster = {str(getattr(Config, "STREAMRIP_QOBUZ_FILTERS_NON_REMASTER", False)).lower()}

[tidal]
quality = {getattr(Config, "STREAMRIP_TIDAL_QUALITY", 3)}
download_videos = {str(getattr(Config, "STREAMRIP_TIDAL_DOWNLOAD_VIDEOS", True)).lower()}
user_id = "{getattr(Config, "STREAMRIP_TIDAL_USER_ID", "")}"
country_code = "{getattr(Config, "STREAMRIP_TIDAL_COUNTRY_CODE", "")}"
access_token = "{getattr(Config, "STREAMRIP_TIDAL_ACCESS_TOKEN", "")}"
refresh_token = "{getattr(Config, "STREAMRIP_TIDAL_REFRESH_TOKEN", "")}"
token_expiry = "{getattr(Config, "STREAMRIP_TIDAL_TOKEN_EXPIRY", "0") or "0"}"

[deezer]
arl = "{getattr(Config, "STREAMRIP_DEEZER_ARL", "")}"
quality = {getattr(Config, "STREAMRIP_DEEZER_QUALITY", 2)}
use_deezloader = {str(getattr(Config, "STREAMRIP_DEEZER_USE_DEEZLOADER", True)).lower()}
deezloader_warnings = {str(getattr(Config, "STREAMRIP_DEEZER_DEEZLOADER_WARNINGS", True)).lower()}

[soundcloud]
quality = {getattr(Config, "STREAMRIP_SOUNDCLOUD_QUALITY", 0)}
client_id = "{getattr(Config, "STREAMRIP_SOUNDCLOUD_CLIENT_ID", "")}"
app_version = "{getattr(Config, "STREAMRIP_SOUNDCLOUD_APP_VERSION", "")}"

[youtube]
quality = {getattr(Config, "STREAMRIP_YOUTUBE_QUALITY", 0)}
download_videos = {str(getattr(Config, "STREAMRIP_YOUTUBE_DOWNLOAD_VIDEOS", False)).lower()}
video_downloads_folder = "{getattr(Config, "STREAMRIP_YOUTUBE_VIDEO_DOWNLOADS_FOLDER", f"{fallback_downloads_folder}/youtube")}"

[database]
downloads_enabled = {str(getattr(Config, "STREAMRIP_DATABASE_DOWNLOADS_ENABLED", True)).lower()}
downloads_path = "{getattr(Config, "STREAMRIP_DATABASE_DOWNLOADS_PATH", "./downloads.db")}"
failed_downloads_enabled = {str(getattr(Config, "STREAMRIP_DATABASE_FAILED_DOWNLOADS_ENABLED", True)).lower()}
failed_downloads_path = "{getattr(Config, "STREAMRIP_DATABASE_FAILED_DOWNLOADS_PATH", "./failed_downloads.db")}"

[artwork]
embed = {str(getattr(Config, "STREAMRIP_EMBED_COVER_ART", True)).lower()}
embed_size = "{getattr(Config, "STREAMRIP_COVER_ART_SIZE", "large")}"
embed_max_width = {getattr(Config, "STREAMRIP_ARTWORK_EMBED_MAX_WIDTH", -1)}
save_artwork = {str(getattr(Config, "STREAMRIP_SAVE_COVER_ART", True)).lower()}
saved_max_width = {getattr(Config, "STREAMRIP_ARTWORK_SAVED_MAX_WIDTH", -1)}

[metadata]
set_playlist_to_album = {str(getattr(Config, "STREAMRIP_METADATA_SET_PLAYLIST_TO_ALBUM", True)).lower()}
renumber_playlist_tracks = {str(getattr(Config, "STREAMRIP_METADATA_RENUMBER_PLAYLIST_TRACKS", True)).lower()}
exclude = {getattr(Config, "STREAMRIP_METADATA_EXCLUDE", [])!s}

[filepaths]
add_singles_to_folder = {str(getattr(Config, "STREAMRIP_FILEPATHS_ADD_SINGLES_TO_FOLDER", False)).lower()}
folder_format = "{getattr(Config, "STREAMRIP_FILEPATHS_FOLDER_FORMAT", "{albumartist} - {title} ({year}) [{container}] [{bit_depth}B-{sampling_rate}kHz]")}"
track_format = "{getattr(Config, "STREAMRIP_FILEPATHS_TRACK_FORMAT", "{tracknumber:02}. {artist} - {title}{explicit}")}"
restrict_characters = {str(getattr(Config, "STREAMRIP_FILEPATHS_RESTRICT_CHARACTERS", False)).lower()}
truncate_to = {getattr(Config, "STREAMRIP_FILEPATHS_TRUNCATE_TO", 120)}

[conversion]
enabled = {str(getattr(Config, "STREAMRIP_CONVERSION_ENABLED", False)).lower()}
codec = "{getattr(Config, "STREAMRIP_CONVERSION_CODEC", "ALAC")}"
sampling_rate = {getattr(Config, "STREAMRIP_CONVERSION_SAMPLING_RATE", 48000)}
bit_depth = {getattr(Config, "STREAMRIP_CONVERSION_BIT_DEPTH", 24)}
lossy_bitrate = {getattr(Config, "STREAMRIP_CONVERSION_LOSSY_BITRATE", 320)}

[lastfm]
source = "{getattr(Config, "STREAMRIP_LASTFM_SOURCE", "qobuz")}"
fallback_source = "{getattr(Config, "STREAMRIP_LASTFM_FALLBACK_SOURCE", "")}"

[cli]
text_output = {str(getattr(Config, "STREAMRIP_CLI_TEXT_OUTPUT", True)).lower()}
progress_bars = {str(getattr(Config, "STREAMRIP_CLI_PROGRESS_BARS", True)).lower()}
max_search_results = {getattr(Config, "STREAMRIP_CLI_MAX_SEARCH_RESULTS", 100)}

[misc]
version = "{getattr(Config, "STREAMRIP_MISC_VERSION", "2.0.6")}"
check_for_updates = {str(getattr(Config, "STREAMRIP_MISC_CHECK_FOR_UPDATES", True)).lower()}
"""

    async def _regenerate_streamrip_config(self):
        """Regenerate streamrip config with latest bot settings (dynamic update)"""
        try:
            LOGGER.info("Regenerating streamrip config with latest bot settings...")

            config_dir = Path.home() / ".config" / "streamrip"
            config_file = config_dir / "config.toml"

            # Ensure directory exists
            config_dir.mkdir(parents=True, exist_ok=True)

            # Get fresh config content with latest settings
            config_content = self._create_default_config()

            # Write the fresh config file
            import aiofiles

            async with aiofiles.open(config_file, "w") as f:
                await f.write(config_content)

            LOGGER.info(
                f"Streamrip config regenerated successfully at: {config_file}"
            )

            # Validate that credentials are actually in the config
            await self._validate_config_credentials(config_file)

        except Exception as e:
            LOGGER.error(f"Failed to regenerate streamrip config: {e}")
            # Don't fail the download if config regeneration fails
            # Fall back to existing config or create minimal one
            await self._create_manual_config()

    async def _validate_config_credentials(self, config_file: Path):
        """Validate that credentials are actually written to the config file"""
        try:
            # Read the config file to verify credentials are present
            import aiofiles

            from bot.core.config_manager import Config

            async with aiofiles.open(config_file) as f:
                config_content = await f.read()

            # Check for Qobuz credentials
            qobuz_email = Config.STREAMRIP_QOBUZ_EMAIL or ""
            qobuz_password = Config.STREAMRIP_QOBUZ_PASSWORD or ""

            # Only log warnings for missing credentials
            if qobuz_email and qobuz_password:
                if not (
                    qobuz_email in config_content
                    and qobuz_password in config_content
                ):
                    LOGGER.warning("⚠️ Qobuz credentials not found in config file")

            # Check for Deezer ARL
            deezer_arl = Config.STREAMRIP_DEEZER_ARL or ""
            if deezer_arl and deezer_arl not in config_content:
                LOGGER.warning("⚠️ Deezer ARL not found in config file")

            # Check for Tidal credentials
            tidal_email = Config.STREAMRIP_TIDAL_EMAIL or ""
            tidal_password = Config.STREAMRIP_TIDAL_PASSWORD or ""

            if tidal_email and tidal_password:
                if not (
                    tidal_email in config_content
                    and tidal_password in config_content
                ):
                    LOGGER.warning("⚠️ Tidal credentials not found in config file")

        except Exception as e:
            LOGGER.error(f"Error validating config credentials: {e}")

    async def _update_deezer_arl(self, new_arl: str):
        """Update Deezer ARL in the streamrip config"""
        try:
            config_dir = Path.home() / ".config" / "streamrip"
            config_file = config_dir / "config.toml"

            if not config_file.exists():
                LOGGER.error("Streamrip config file not found")
                return False

            # Read current config
            import aiofiles

            async with aiofiles.open(config_file) as f:
                config_content = await f.read()

            # Update ARL in config content
            import re

            # Pattern to match arl = "..." line
            arl_pattern = r'arl\s*=\s*"[^"]*"'
            new_arl_line = f'arl = "{new_arl}"'

            if re.search(arl_pattern, config_content):
                # Replace existing ARL
                updated_content = re.sub(arl_pattern, new_arl_line, config_content)
            # Add ARL to deezer section
            elif re.search(r"\[deezer\]", config_content):
                updated_content = re.sub(
                    r"(\[deezer\])", f"[deezer]\n{new_arl_line}", config_content
                )
            else:
                # Add entire deezer section
                updated_content = config_content + f"\n\n[deezer]\n{new_arl_line}\n"

            # Write updated config
            async with aiofiles.open(config_file, "w") as f:
                await f.write(updated_content)

            # Clear cached config to force regeneration
            self._cached_config = None

            LOGGER.info("✅ Successfully updated Deezer ARL in streamrip config")
            return True

        except Exception as e:
            LOGGER.error(f"Failed to update Deezer ARL: {e}")
            return False

    async def _regenerate_streamrip_config(self):
        """Regenerate streamrip config with current bot settings"""
        try:
            config_dir = Path.home() / ".config" / "streamrip"
            config_file = config_dir / "config.toml"

            # Create config directory if it doesn't exist
            config_dir.mkdir(parents=True, exist_ok=True)

            # Generate fresh config content
            config_content = self._create_default_config()

            # Write new config file
            import aiofiles

            async with aiofiles.open(config_file, "w") as f:
                await f.write(config_content)

            return True

        except Exception as e:
            LOGGER.error(f"Failed to regenerate streamrip config: {e}")
            return False

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
                LOGGER.info(
                    f"✅ Deezer authentication available: ***{deezer_arl[-10:]}"
                )
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

                LOGGER.info(f"✅ Qobuz authentication available: {qobuz_email}")
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
                    LOGGER.info("✅ Tidal token authentication available")
                    return True
                if has_credentials:
                    LOGGER.info(f"✅ Tidal email/password available: {tidal_email}")
                    LOGGER.warning(
                        "⚠️ Tidal authentication may require interactive token generation"
                    )
                    LOGGER.warning(
                        "💡 If download fails, you may need to run 'rip config --tidal' manually"
                    )

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
                LOGGER.info(
                    f"✅ SoundCloud authentication available: ***{soundcloud_client_id[-10:]}"
                )
                return True

            elif "last.fm" in url_lower or "lastfm" in url_lower:
                # Last.fm playlist - requires primary source authentication
                LOGGER.info(
                    "✅ Last.fm playlist detected - will use configured primary source"
                )
                LOGGER.info(
                    "💡 Last.fm playlists require a primary streaming service (Deezer/Qobuz/Tidal)"
                )

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

                primary_source = (
                    "Deezer" if has_deezer else ("Qobuz" if has_qobuz else "Tidal")
                )
                LOGGER.info(
                    f"✅ Last.fm will use {primary_source} as primary source"
                )
                return True

            elif "spotify.com" in url_lower or "open.spotify.com" in url_lower:
                # Spotify playlist - requires Last.fm integration
                LOGGER.info(
                    "✅ Spotify playlist detected - will convert via Last.fm"
                )
                LOGGER.info(
                    "💡 Spotify playlists are converted to Last.fm then downloaded from streaming services"
                )

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

                primary_source = (
                    "Deezer" if has_deezer else ("Qobuz" if has_qobuz else "Tidal")
                )
                LOGGER.info(
                    f"✅ Spotify playlist will use {primary_source} as primary source"
                )
                return True

            elif "music.apple.com" in url_lower:
                # Apple Music playlist - requires Last.fm integration
                LOGGER.info(
                    "✅ Apple Music playlist detected - will convert via Last.fm"
                )
                LOGGER.info(
                    "💡 Apple Music playlists are converted to Last.fm then downloaded from streaming services"
                )

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

                primary_source = (
                    "Deezer" if has_deezer else ("Qobuz" if has_qobuz else "Tidal")
                )
                LOGGER.info(
                    f"✅ Apple Music playlist will use {primary_source} as primary source"
                )
                return True

            else:
                # Unknown platform - allow download attempt (like Deezer logic)
                LOGGER.warning(f"⚠️ Unknown platform for URL: {url}")
                LOGGER.info(
                    "Allowing download attempt - streamrip may support this platform"
                )
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
                    converted_url = f"https://listen.tidal.com/playlist/{mix_id}"
                    LOGGER.info(f"Converting Tidal mix URL: {url} → {converted_url}")
                    LOGGER.warning(
                        "⚠️ Tidal mix URLs may require valid authentication to access"
                    )
                    LOGGER.warning(
                        "💡 If you get 404 errors, ensure your Tidal credentials are valid"
                    )
                    return converted_url
                LOGGER.warning(f"Could not extract mix ID from Tidal URL: {url}")
                return url

            # Handle other Tidal browse URLs - convert to listen.tidal.com format
            if "tidal.com/browse/" in url_lower:
                # Convert browse URLs to listen URLs for better compatibility
                converted_url = url.replace("tidal.com/browse/", "listen.tidal.com/")
                if converted_url != url:
                    LOGGER.info(
                        f"Converting Tidal browse URL: {url} → {converted_url}"
                    )
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
                    LOGGER.info(
                        f"Removing Qobuz region prefix: {url} → {converted_url}"
                    )

                # Convert /interpreter/ to /artist/ for streamrip compatibility
                if "/interpreter/" in converted_url.lower():
                    converted_url = re.sub(
                        r"/interpreter/",
                        "/artist/",
                        converted_url,
                        flags=re.IGNORECASE,
                    )
                    LOGGER.info(
                        f"Converting Qobuz interpreter URL to artist format: {converted_url}"
                    )

                if converted_url != url:
                    LOGGER.info(
                        f"Final Qobuz URL conversion: {url} → {converted_url}"
                    )
                    return converted_url

            # Handle Deezer page.link URLs - these should be resolved by streamrip
            elif "dzr.page.link" in url_lower:
                LOGGER.info(f"Using Deezer short URL as-is: {url}")
                return url

            # Handle SoundCloud URLs - ensure proper format
            elif "soundcloud.com" in url_lower:
                # SoundCloud URLs should work as-is
                LOGGER.info(f"Using SoundCloud URL as-is: {url}")
                return url

            # For all other URLs, return as-is
            return url

        except Exception as e:
            LOGGER.warning(f"Error converting URL for streamrip: {e}")
            LOGGER.info(f"Using original URL: {url}")
            return url

    async def _retry_download_with_isolation(self) -> bool:
        """Retry download with enhanced process isolation for asyncio event loop errors"""
        try:
            LOGGER.info("🔄 Starting retry with enhanced process isolation...")

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

            LOGGER.info("🔄 Executing isolated retry command...")

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
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=360,  # 6 minute timeout for retry
                )

                if process.returncode == 0:
                    LOGGER.info("✅ Isolated retry succeeded!")
                    stdout_text = stdout.decode() if stdout else ""
                    if stdout_text:
                        LOGGER.info(f"Retry output: {stdout_text}")
                    return True
                LOGGER.error("❌ Isolated retry failed")
                error_text = stderr.decode() if stderr else "Unknown error"
                LOGGER.error(f"Retry error: {error_text}")
                return False

            except TimeoutError:
                LOGGER.error("❌ Isolated retry timed out")
                try:
                    process.kill()
                    await process.wait()
                except:
                    pass
                return False

        except Exception as e:
            LOGGER.error(f"❌ Isolated retry exception: {e}")
            return False

    async def _reset_streamrip_config_if_needed(self):
        """Reset streamrip config if it's invalid"""
        try:
            # First, try to create a proper config using streamrip's built-in method
            config_dir = Path.home() / ".config" / "streamrip"
            config_file = config_dir / "config.toml"

            # If config doesn't exist or is invalid, create a new one
            if not config_file.exists():
                LOGGER.info("Creating streamrip config using built-in method...")

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
                    _, create_stderr = await asyncio.wait_for(
                        create_process.communicate(input=create_input), timeout=15
                    )

                    if create_process.returncode == 0:
                        LOGGER.info("Streamrip config created successfully")
                    else:
                        LOGGER.warning(
                            f"Config creation failed: {create_stderr.decode() if create_stderr else 'Unknown error'}"
                        )
                        # Fallback to manual config creation
                        await self._create_manual_config()

                except TimeoutError:
                    LOGGER.warning("Config creation timed out, using manual config")
                    create_process.kill()
                    await create_process.wait()
                    await self._create_manual_config()

        except Exception as e:
            LOGGER.error(f"Error checking/creating streamrip config: {e}")
            # Fallback to manual config creation
            await self._create_manual_config()

    async def _create_manual_config(self):
        """Create streamrip config manually as fallback"""
        try:
            LOGGER.info("Creating streamrip config manually...")

            config_dir = Path.home() / ".config" / "streamrip"
            config_file = config_dir / "config.toml"

            # Ensure directory exists
            config_dir.mkdir(parents=True, exist_ok=True)

            # Use the same config creation logic as _create_default_config
            config_content = self._create_default_config()

            # Write config file
            import aiofiles

            async with aiofiles.open(config_file, "w") as f:
                await f.write(config_content)

            LOGGER.info(f"Manual streamrip config created at: {config_file}")

        except Exception as e:
            LOGGER.error(f"Failed to create manual config: {e}")
            # Don't fail the download if manual config creation fails

    async def _start_progress_monitoring(self):
        """Start progress monitoring for CLI download"""
        try:
            import asyncio

            # Simulate progress updates since CLI doesn't provide real-time progress
            total_steps = 10
            for step in range(total_steps + 1):
                if not self._is_downloading:
                    break

                # Update progress
                progress = (step / total_steps) * 100
                self._completed_tracks = (step / total_steps) * self._total_tracks

                # Update current track name with progress
                if step == 0:
                    self._current_track = "Initializing download..."
                elif step < 3:
                    self._current_track = "Authenticating..."
                elif step < 5:
                    self._current_track = "Resolving URL..."
                elif step < 8:
                    self._current_track = "Downloading tracks..."
                else:
                    self._current_track = "Finalizing download..."

                # Simulate speed calculation
                elapsed = time.time() - self._start_time
                if elapsed > 0:
                    # Estimate speed based on progress
                    estimated_total_size = 30 * 1024 * 1024  # 30MB estimate
                    self._size = estimated_total_size
                    self._last_downloaded = int(
                        (progress / 100) * estimated_total_size
                    )
                    self._speed = (
                        self._last_downloaded / elapsed if elapsed > 0 else 0
                    )

                    # Calculate ETA
                    if self._speed > 0 and progress < 100:
                        remaining_bytes = (
                            estimated_total_size - self._last_downloaded
                        )
                        self._eta = remaining_bytes / self._speed

                # Wait before next update
                await asyncio.sleep(2)

        except Exception as e:
            LOGGER.error(f"Progress monitoring error: {e}")

    async def _progress_callback(self, track_info: dict[str, Any]):
        """Progress callback for download updates"""
        try:
            # Update current track info
            if "title" in track_info:
                self._current_track = track_info["title"]

            if "artist" in track_info:
                self._current_track += f" - {track_info['artist']}"

            # Update progress
            if "completed" in track_info:
                self._completed_tracks = track_info["completed"]

            if "total_size" in track_info:
                self._size = track_info["total_size"]

            if "downloaded" in track_info:
                self._last_downloaded = track_info["downloaded"]

            # Calculate speed and ETA
            elapsed = time.time() - self._start_time
            if elapsed > 0 and self._last_downloaded > 0:
                self._speed = self._last_downloaded / elapsed

                if self._speed > 0 and self._size > self._last_downloaded:
                    remaining = self._size - self._last_downloaded
                    self._eta = remaining / self._speed

        except Exception as e:
            LOGGER.error(f"Progress callback error: {e}")

    def cancel_download(self):
        """Cancel the download"""
        self._is_cancelled = True

        # Cancel the media download if possible
        if self._media and hasattr(self._media, "cancel"):
            self._media.cancel()

        # Clean up temporary files
        self._cleanup_temp_files()

        LOGGER.info("Streamrip download cancelled")

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

    # Limit checking removed for now as limit_checker.py was deleted.
    # if Config.STREAMRIP_LIMIT > 0:
    #     estimated_size = await _estimate_streamrip_size(
    #         url, quality or Config.STREAMRIP_DEFAULT_QUALITY
    #     )
    #     if estimated_size > 0:
    #         limit_msg = await limit_checker(
    #             estimated_size, listener, isStreamrip=True
    #         )
    #         if limit_msg:
    #             return

    # Create download helper
    download_helper = StreamripDownloadHelper(listener)

    # Set download info in listener so it has access to URL for error handling
    listener.set_download_info(url, quality, codec)

    # Set force flag in listener for CLI command generation
    listener.force_download = force

    # The listener (StreamripListener, which inherits TaskListener) should handle
    # adding itself or its status object to task_dict and queue_dict.
    # Direct manipulation of task_dict with StreamripDownloadStatus or QueueStatus here is removed.

    # Start download immediately
    LOGGER.info(f"Starting streamrip download: {url}")

    # Send initial status message. The listener's __init__ or a dedicated
    # on_start method (if TaskListener has one) should manage adding to task_dict.
    # For now, we rely on the fact that StreamripListener's __init__ calls super().__init__
    # which should make it part of task_dict.
    await send_status_message(listener.message)

    try:
        download_success = await download_helper.download(url, quality, codec)

        # If download was successful, trigger the upload process
        if download_success:
            LOGGER.info("Streamrip download completed, triggering upload process...")
            await listener.on_download_complete()
        else:
            LOGGER.error("Streamrip download failed")
            await listener.on_download_error("Download failed")
    except Exception as e:
        LOGGER.error(f"Exception in streamrip download: {e}")
        import traceback

        LOGGER.error(f"Traceback: {traceback.format_exc()}")
        await listener.on_download_error(f"Download error: {e}")


async def _estimate_streamrip_size(url: str, quality: int) -> int:
    """Estimate download size for streamrip content"""
    try:
        from bot.helper.streamrip_utils.url_parser import parse_streamrip_url

        parsed = await parse_streamrip_url(url)
        if not parsed:
            return 0

        _, media_type, _ = parsed

        # Size estimates in MB per track based on quality
        size_estimates = {
            0: 4,  # 128 kbps
            1: 10,  # 320 kbps
            2: 35,  # CD Quality
            3: 80,  # Hi-Res
            4: 150,  # Hi-Res+
        }

        track_size_mb = size_estimates.get(quality, 35)

        # Use class constants for track count estimation
        track_count = StreamripDownloadHelper.TRACK_ESTIMATES.get(media_type, 10)
        if media_type == "artist":
            track_count = 50  # Conservative estimate for artists

        return track_count * track_size_mb * 1024 * 1024

    except Exception as e:
        LOGGER.error(f"Error estimating streamrip size: {e}")
        return 0
