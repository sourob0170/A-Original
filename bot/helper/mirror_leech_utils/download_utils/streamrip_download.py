import asyncio
import os
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
from bot.helper.ext_utils.limit_checker import limit_checker
from bot.helper.mirror_leech_utils.status_utils.queue_status import QueueStatus
from bot.helper.mirror_leech_utils.status_utils.streamrip_status import (
    StreamripDownloadStatus,
)
from bot.helper.telegram_helper.message_utils import send_status_message

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
    LOGGER.warning("Streamrip not installed. Streamrip features will be disabled.")


class StreamripDownloadHelper:
    """Helper class for streamrip downloads"""

    def __init__(self, listener):
        self.listener = listener
        self._last_downloaded = 0
        self._size = 0
        self._start_time = time.time()
        self._is_cancelled = False
        self._client = None
        self._media = None
        self._download_path = None
        self._current_track = ""
        self._total_tracks = 0
        self._completed_tracks = 0
        self._speed = 0
        self._eta = 0
        self._is_downloading = False

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
            LOGGER.debug(f"About to parse URL: {url}")
            from bot.helper.streamrip_utils.url_parser import parse_streamrip_url

            try:
                parsed = await parse_streamrip_url(url)
                LOGGER.debug(f"URL parsing completed, result: {parsed}")
            except Exception as parse_error:
                LOGGER.error(f"Error during URL parsing: {parse_error}")
                LOGGER.debug(f"Parse error type: {type(parse_error)}")
                raise

            if not parsed:
                LOGGER.error(f"Failed to parse streamrip URL: {url}")
                return False

            platform, media_type, media_id = parsed
            LOGGER.info(f"Parsed {platform} {media_type}: {media_id}")

            # Set download path using existing DOWNLOAD_DIR pattern
            # Ensure all path components are strings to avoid path division errors
            try:
                base_dir = str(DOWNLOAD_DIR)
                listener_id = str(self.listener.mid)
                LOGGER.debug(f"Creating download path: {base_dir} + {listener_id}")

                download_dir = Path(base_dir) / listener_id
                download_dir.mkdir(parents=True, exist_ok=True)
                self._download_path = download_dir

                LOGGER.debug(
                    f"Download path created successfully: {self._download_path}"
                )
            except Exception as path_error:
                LOGGER.error(f"Failed to create download path: {path_error}")
                LOGGER.debug(
                    f"DOWNLOAD_DIR type: {type(DOWNLOAD_DIR)}, value: {DOWNLOAD_DIR}"
                )
                LOGGER.debug(
                    f"listener.mid type: {type(self.listener.mid)}, value: {self.listener.mid}"
                )
                raise

            # Skip client initialization and media object creation for CLI method
            # This avoids the streamrip 2.1.0 path division bug
            LOGGER.debug("Using CLI method - skipping client initialization")

            # Initialize progress tracking
            self._is_downloading = True
            self._current_track = f"Downloading from {platform.title()}"

            # Estimate total tracks for progress
            if media_type == "track":
                self._total_tracks = 1
            elif media_type == "album":
                self._total_tracks = 12  # Estimate
            elif media_type == "playlist":
                self._total_tracks = 25  # Estimate
            else:
                self._total_tracks = 1

            # Start download
            LOGGER.info(f"Starting streamrip download: {url}")
            success = await self._perform_download()

            if success:
                LOGGER.info(f"Streamrip download completed: {url}")
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
                    LOGGER.info(f"✅ {platform.title()} authentication successful")
            except Exception as auth_error:
                if platform == "tidal":
                    LOGGER.warning(f"⚠️ Tidal authentication failed: {auth_error}")
                    LOGGER.info(
                        "💡 Tidal requires interactive token setup. Use 'rip config --tidal' to authenticate."
                    )
                    return
                LOGGER.error(
                    f"❌ {platform.title()} authentication failed: {auth_error}"
                )
                return

            LOGGER.info(f"Initialized {platform} client successfully")

        except Exception as e:
            LOGGER.error(f"Failed to initialize {platform} client: {e}")

    async def _create_media_object(
        self, platform: str, media_type: str, media_id: str, url: str
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

            LOGGER.info(
                f"✅ Created {media_type} object from {platform.title()} with {self._total_tracks} tracks"
            )

        except Exception as e:
            LOGGER.error(f"❌ Failed to create media object: {e}")
            # Log more specific error information
            if "get_track" in str(e) or "get_album" in str(e):
                LOGGER.info(
                    f"💡 Platform {platform} may use different API methods. Check streamrip documentation."
                )
            return

    async def _set_quality(self, quality: int):
        """Set download quality"""
        try:
            if hasattr(self._media, "set_quality"):
                await self._media.set_quality(quality)
            elif hasattr(self._client, "set_quality"):
                await self._client.set_quality(quality)

            LOGGER.info(f"Set quality to {quality}")

        except Exception as e:
            LOGGER.error(f"Failed to set quality: {e}")

    async def _set_codec(self, codec: str):
        """Set output codec"""
        try:
            if hasattr(self._media, "set_codec"):
                await self._media.set_codec(codec)
            elif hasattr(self._client, "set_codec"):
                await self._client.set_codec(codec)

            LOGGER.info(f"Set codec to {codec}")

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
                LOGGER.debug(
                    f"Updated streamrip download folder to: {self._download_path}"
                )
        except Exception as e:
            LOGGER.warning(f"Failed to update streamrip download path: {e}")

    async def _perform_download(self) -> bool:
        """Perform the actual download with enhanced error handling"""
        try:
            LOGGER.info(f"Starting download to: {self._download_path}")

            # Due to a bug in streamrip 2.1.0 with PosixPath division operations,
            # we'll use CLI method exclusively to avoid the internal API issues
            LOGGER.debug("Using streamrip CLI method to avoid path division bug")
            download_success = await self._download_with_cli()

            if download_success:
                # Validate downloaded files
                downloaded_files = await self._find_downloaded_files()
                if downloaded_files:
                    LOGGER.info(
                        f"Download completed. Found {len(downloaded_files)} files."
                    )

                    # Update final progress
                    self._completed_tracks = self._total_tracks

                    # Don't call on_download_complete here - it will be called by the task management system
                    # Just return True to indicate successful download
                    LOGGER.info(
                        "Download completed successfully, files ready for upload"
                    )
                    return True
                LOGGER.error("No files were downloaded")
                return False
            LOGGER.error("CLI download method failed")
            return False

        except Exception as e:
            LOGGER.error(f"Download failed: {e}")
            return False

    def _map_codec_for_streamrip(self, codec: str) -> str:
        """Map user-friendly codec names to streamrip-compatible ones with FFmpeg encoder compatibility"""
        # Convert to lowercase for case-insensitive matching
        codec_lower = codec.lower()

        # Handle AAC/M4A codecs with FFmpeg wrapper approach
        if codec_lower in ["m4a", "aac"]:
            # Use FFmpeg wrapper to replace libfdk_aac with built-in aac encoder
            LOGGER.info(
                "🎵 AAC/M4A codec requested - using FFmpeg wrapper for encoder compatibility"
            )
            LOGGER.info(
                "🔧 Will replace libfdk_aac with built-in aac encoder automatically"
            )
            # Return AAC - the wrapper will handle the encoder replacement
            mapped_codec = "AAC"
            LOGGER.info(
                f"Codec mapping: {codec} → {mapped_codec} (with encoder wrapper)"
            )
            return mapped_codec

        # Standard codec mapping for supported formats
        # Note: Streamrip only accepts: "ALAC", "FLAC", "OGG", "MP3", "AAC"
        codec_mapping = {
            "ogg": "OGG",  # OGG Vorbis
            "flac": "FLAC",  # FLAC lossless
            "mp3": "MP3",  # MP3 lossy
            "opus": "OGG",  # OPUS maps to OGG in streamrip
            "alac": "ALAC",  # Apple Lossless
            "vorbis": "OGG",  # Vorbis maps to OGG in streamrip
        }

        mapped_codec = codec_mapping.get(codec_lower)

        if mapped_codec is None:
            # Unknown codec - don't specify codec, let streamrip use default
            LOGGER.warning(
                f"⚠️ Unknown codec '{codec}' - downloading in default format"
            )
            LOGGER.info(f"💡 Supported codecs: {', '.join(codec_mapping.keys())}")
            return None

        LOGGER.info(f"Codec mapping: {codec} → {mapped_codec}")
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
                else:
                    LOGGER.info(
                        "🎵 No codec specified - streamrip will download in native format"
                    )

            # Add --no-db flag only if database is disabled in bot settings
            from bot.helper.streamrip_utils.streamrip_config import streamrip_config

            if not streamrip_config.is_database_enabled():
                cmd.extend(["--no-db"])
                LOGGER.debug("Added --no-db flag (database disabled in settings)")
            else:
                LOGGER.debug(
                    "Database enabled in settings, allowing streamrip to use database"
                )

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
            wrapper_path = await self._setup_ffmpeg_wrapper_for_aac(ffmpeg_path, env)

            # Set multiple environment variables that streamrip might check
            env["FFMPEG_EXECUTABLE"] = wrapper_path
            env["FFMPEG_PATH"] = wrapper_path
            env["FFMPEG"] = wrapper_path
            env["FFMPEG_BINARY"] = wrapper_path

            # Ensure the wrapper directory is in PATH
            wrapper_dir = os.path.dirname(wrapper_path)
            env["PATH"] = f"{wrapper_dir}:{env.get('PATH', '')}"

            LOGGER.info(
                f"✅ Set FFmpeg environment variables to use wrapper: {wrapper_path}"
            )

            LOGGER.debug(f"Using FFMPEG path: {ffmpeg_path}")
            LOGGER.debug(f"Environment PATH: {env['PATH']}")

            LOGGER.info(f"Executing streamrip CLI: {' '.join(cmd)}")
            LOGGER.debug(f"Download directory: {self._download_path}")
            LOGGER.debug(f"Download URL: {download_url}")
            LOGGER.debug(f"Working directory: {Path.home()}")
            LOGGER.debug(
                f"Environment variables: STREAMRIP_DOWNLOAD_DIR={env.get('STREAMRIP_DOWNLOAD_DIR')}"
            )
            LOGGER.info(
                "Note: Streamrip will download to its default folder, files will be moved after download"
            )

            # Check if streamrip is available
            try:
                LOGGER.info("Checking streamrip availability...")
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
                rip_path = stdout_check.decode().strip()
                LOGGER.info(f"Found streamrip at: {rip_path}")
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

            # Enhanced credential testing for all services (like Deezer)
            if "qobuz.com" in download_url.lower():
                LOGGER.info("Testing Qobuz credentials before main download...")
                credential_test_result = await self._test_qobuz_credentials()
                if (
                    credential_test_result is False
                ):  # Only abort if test explicitly failed
                    LOGGER.error("Qobuz credential test failed - aborting download")
                    return False
                if credential_test_result is True:
                    LOGGER.info(
                        "✅ Qobuz credential test passed - proceeding with download"
                    )
                else:
                    LOGGER.info(
                        "⚠️ Qobuz credential test skipped - proceeding with download"
                    )

            elif "tidal.com" in download_url.lower():
                LOGGER.info("Testing Tidal credentials before main download...")
                credential_test_result = await self._test_tidal_credentials()
                if credential_test_result is False:
                    LOGGER.error("Tidal credential test failed - aborting download")
                    return False
                if credential_test_result is True:
                    LOGGER.info(
                        "✅ Tidal credential test passed - proceeding with download"
                    )
                else:
                    LOGGER.info(
                        "⚠️ Tidal credential test skipped - proceeding with download"
                    )

            elif "soundcloud.com" in download_url.lower():
                LOGGER.info("Testing SoundCloud configuration...")
                credential_test_result = await self._test_soundcloud_credentials()
                if credential_test_result is False:
                    LOGGER.error(
                        "SoundCloud configuration test failed - aborting download"
                    )
                    return False
                if credential_test_result is True:
                    LOGGER.info(
                        "✅ SoundCloud configuration test passed - proceeding with download"
                    )
                else:
                    LOGGER.info(
                        "⚠️ SoundCloud configuration test skipped - proceeding with download"
                    )

            elif (
                "deezer.com" in download_url.lower()
                or "dzr.page.link" in download_url.lower()
            ):
                LOGGER.info("Testing Deezer credentials before main download...")
                credential_test_result = await self._test_deezer_credentials()
                if credential_test_result is False:
                    LOGGER.error("Deezer credential test failed - aborting download")
                    return False
                if credential_test_result is True:
                    LOGGER.info(
                        "✅ Deezer credential test passed - proceeding with download"
                    )
                else:
                    LOGGER.info(
                        "⚠️ Deezer credential test skipped - proceeding with download"
                    )

            # Execute with timeout
            # Use home directory as working directory since streamrip uses its own config
            try:
                LOGGER.info("Creating subprocess...")

                # For Heroku compatibility, ensure we have proper environment
                working_dir = str(Path.home())
                LOGGER.debug(f"Working directory: {working_dir}")

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
                LOGGER.info(f"Subprocess created with PID: {process.pid}")
            except Exception as proc_error:
                LOGGER.error(f"Failed to create subprocess: {proc_error}")
                return False

            LOGGER.info("Waiting for streamrip process to complete (no timeout)")

            # Start progress monitoring in background
            progress_task = asyncio.create_task(self._start_progress_monitoring())

            try:
                # Remove timeout restrictions for streamrip downloads (like Deezer)
                LOGGER.info(
                    "Starting streamrip process communication (no timeout)..."
                )

                # Enhanced error detection for all services (like Deezer)
                is_qobuz = "qobuz.com" in download_url.lower()
                is_tidal = "tidal.com" in download_url.lower()
                is_soundcloud = "soundcloud.com" in download_url.lower()
                is_deezer = (
                    "deezer.com" in download_url.lower()
                    or "dzr.page.link" in download_url.lower()
                )
                is_lastfm = (
                    "last.fm" in download_url.lower()
                    or "lastfm" in download_url.lower()
                )
                is_spotify = (
                    "spotify.com" in download_url.lower()
                    or "open.spotify.com" in download_url.lower()
                )
                is_apple_music = "music.apple.com" in download_url.lower()

                if is_qobuz:
                    LOGGER.info(
                        "Detected Qobuz URL - using enhanced error detection"
                    )
                elif is_tidal:
                    LOGGER.info(
                        "Detected Tidal URL - using enhanced error detection"
                    )
                elif is_soundcloud:
                    LOGGER.info(
                        "Detected SoundCloud URL - using enhanced error detection"
                    )
                elif is_deezer:
                    LOGGER.info(
                        "Detected Deezer URL - using enhanced error detection"
                    )
                elif is_lastfm:
                    LOGGER.info(
                        "Detected Last.fm URL - using enhanced error detection"
                    )
                elif is_spotify:
                    LOGGER.info(
                        "Detected Spotify URL - using enhanced error detection"
                    )
                elif is_apple_music:
                    LOGGER.info(
                        "Detected Apple Music URL - using enhanced error detection"
                    )

                # Send empty input to stdin to prevent hanging on prompts
                # For Deezer ARL prompts, send newline to skip
                stdin_input = b"\n"
                stdout, stderr = await process.communicate(input=stdin_input)
                LOGGER.info("Streamrip process completed successfully")

                # Log detailed output for debugging
                stdout_text = stdout.decode() if stdout else ""
                stderr_text = stderr.decode() if stderr else ""

                if stdout_text:
                    LOGGER.debug(f"Streamrip stdout: {stdout_text}")
                if stderr_text:
                    LOGGER.debug(f"Streamrip stderr: {stderr_text}")
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
                LOGGER.info("Streamrip CLI download completed successfully")
                stdout_text = stdout.decode() if stdout else ""
                if stdout_text:
                    LOGGER.info(f"Streamrip output: {stdout_text}")

                    # Check if tracks were skipped due to being already downloaded
                    if (
                        "Skipping track" in stdout_text
                        and "Marked as downloaded" in stdout_text
                    ):
                        LOGGER.warning(
                            "Streamrip skipped tracks that were already downloaded"
                        )
                        LOGGER.info(
                            "This is normal behavior - streamrip avoids re-downloading existing tracks"
                        )

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
                    "⚠️ Streamrip returned no error details - investigating..."
                )
                LOGGER.error(f"🔍 Return code: {process.returncode}")
                LOGGER.error(
                    f"🔍 Stdout length: {len(stdout_text) if stdout_text else 0}"
                )
                LOGGER.error(
                    f"🔍 Stderr length: {len(stderr.decode() if stderr else '')}"
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
            ):
                LOGGER.error("Deezer ARL prompt detected. This might be due to:")
                LOGGER.error(
                    "  1. Deezer ARL not properly configured in streamrip config"
                )
                LOGGER.error(
                    "  2. Streamrip config file corruption or version mismatch"
                )
                LOGGER.error("  3. Deezer ARL format issue or invalid characters")
                LOGGER.error(
                    "  4. Config regeneration failed to include ARL properly"
                )
                LOGGER.error(
                    "💡 Check /botsettings → Streamrip → Credential settings → Deezer arl"
                )
                LOGGER.error(
                    "💡 Ensure ARL is a long string (192+ characters) without quotes"
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
                LOGGER.error("Deezer-specific error detected. This might be due to:")
                LOGGER.error("  1. Invalid Deezer ARL token")
                LOGGER.error("  2. Deezer ARL token expired")
                LOGGER.error("  3. Deezer account region restrictions")
                LOGGER.error("  4. Album/track not available in your region")
                LOGGER.error("  5. Deezer subscription limitations")
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
                LOGGER.info("🔄 Attempting to regenerate streamrip config...")

            return False

        except Exception as e:
            LOGGER.error(f"CLI download failed: {e}")
            import traceback

            LOGGER.debug(f"CLI download traceback: {traceback.format_exc()}")
            return False

    async def _find_downloaded_files(self) -> list:
        """Find downloaded files in the download directory"""
        try:
            # Find audio files
            audio_extensions = {".flac", ".mp3", ".m4a", ".ogg", ".opus", ".wav"}
            downloaded_files = []

            # Search in multiple possible locations
            search_paths = []

            # 1. Our specified download path
            if self._download_path and self._download_path.exists():
                search_paths.append(self._download_path)
                LOGGER.debug(f"Searching in specified path: {self._download_path}")

            # 2. Parent directory (in case streamrip created its own structure)
            if self._download_path:
                parent_dir = self._download_path.parent
                if parent_dir.exists() and parent_dir not in search_paths:
                    search_paths.append(parent_dir)
                    LOGGER.debug(f"Searching in parent directory: {parent_dir}")

            # 3. Common streamrip download locations
            from pathlib import Path

            common_paths = [
                Path.home() / "StreamripDownloads",  # Default streamrip folder
                Path.home() / "Downloads",
                Path("/tmp"),
                Path("/usr/src/app/downloads"),  # Docker container path
            ]

            for common_path in common_paths:
                if common_path.exists() and common_path not in search_paths:
                    search_paths.append(common_path)
                    LOGGER.debug(f"Searching in common path: {common_path}")

            # Search all paths for recent audio files
            for search_path in search_paths:
                LOGGER.debug(f"Searching for files in: {search_path}")
                try:
                    for file_path in search_path.rglob("*"):
                        if (
                            file_path.is_file()
                            and file_path.suffix.lower() in audio_extensions
                            and file_path.stat().st_mtime > self._start_time
                        ):  # Only recent files
                            downloaded_files.append(file_path)
                            LOGGER.debug(f"Found audio file: {file_path}")
                except Exception as search_error:
                    LOGGER.debug(f"Error searching {search_path}: {search_error}")

            # Remove duplicates and sort by modification time
            unique_files = list(set(downloaded_files))
            sorted_files = sorted(unique_files, key=lambda x: x.stat().st_mtime)

            LOGGER.info(f"Found {len(sorted_files)} downloaded audio files")
            for file_path in sorted_files:
                LOGGER.debug(f"  - {file_path}")

            # Move files from default streamrip folder to our target folder if needed
            if sorted_files:
                return await self._move_files_to_target_folder(sorted_files)

            return sorted_files

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
                        LOGGER.info(f"Moved file: {file_path} -> {target_file}")
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

            LOGGER.debug(f"Checking streamrip config at: {config_file}")

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
            else:
                LOGGER.debug("Streamrip config already exists")

        except Exception as e:
            LOGGER.error(f"Failed to ensure streamrip config: {e}")
            # Don't fail the download if config creation fails

    def _get_ffmpeg_path(self) -> str:
        """Get the path to FFMPEG executable"""
        try:
            import os

            # Check common ffmpeg locations
            ffmpeg_locations = [
                "/usr/bin/xtra",
                "/usr/bin/ffmpeg",
                "/usr/local/bin/ffmpeg",
                "/bin/ffmpeg",
            ]
            for location in ffmpeg_locations:
                if os.path.exists(location):
                    return location
            # If not found, return default
            return "/usr/bin/xtra"
        except Exception:
            return "/usr/bin/xtra"

    async def _setup_ffmpeg_wrapper_for_aac(
        self, ffmpeg_path: str, env: dict
    ) -> str:
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

            LOGGER.info(
                f"✅ Created FFmpeg wrapper for AAC compatibility: {wrapper_script}"
            )
            LOGGER.info("🔧 Wrapper will replace libfdk_aac → aac automatically")

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

            if os.path.exists(ffmpeg_path):
                LOGGER.info(f"✅ FFMPEG found at: {ffmpeg_path}")
                LOGGER.info(
                    "📋 Streamrip will use xtra via FFmpeg wrapper for AAC compatibility"
                )
                LOGGER.info(
                    "💡 Wrapper enables AAC/M4A downloads with built-in aac encoder"
                )
            else:
                LOGGER.warning(f"⚠️ FFMPEG not found at expected path: {ffmpeg_path}")
                LOGGER.warning("Audio conversion may fail if FFMPEG is required")
                LOGGER.info("💡 Install FFMPEG or ensure 'xtra' binary is available")
        except Exception as e:
            LOGGER.error(f"Error checking FFMPEG availability: {e}")

    async def _create_compatible_config(self):
        """Create a streamrip config compatible with the current version"""
        try:
            LOGGER.info(
                "Creating compatible streamrip config without problematic fields..."
            )
            # Use the fallback config which doesn't include ffmpeg_executable
            config_content = self._create_fallback_config()

            config_dir = Path.home() / ".config" / "streamrip"
            config_dir.mkdir(parents=True, exist_ok=True)
            config_file = config_dir / "config.toml"

            import aiofiles

            async with aiofiles.open(config_file, "w") as f:
                await f.write(config_content)

            LOGGER.info(f"✅ Compatible config created at: {config_file}")
            return True
        except Exception as e:
            LOGGER.error(f"Failed to create compatible config: {e}")
            return False

    def _create_default_config(self) -> str:
        """Create a comprehensive streamrip config with all bot settings"""
        try:
            # Get all streamrip settings from bot config
            from bot.core.config_manager import Config

            # Authentication settings
            deezer_arl = Config.STREAMRIP_DEEZER_ARL or ""
            qobuz_email = Config.STREAMRIP_QOBUZ_EMAIL or ""
            qobuz_password = Config.STREAMRIP_QOBUZ_PASSWORD or ""
            tidal_access_token = Config.STREAMRIP_TIDAL_ACCESS_TOKEN or ""
            tidal_refresh_token = Config.STREAMRIP_TIDAL_REFRESH_TOKEN or ""
            tidal_user_id = Config.STREAMRIP_TIDAL_USER_ID or ""
            tidal_country_code = Config.STREAMRIP_TIDAL_COUNTRY_CODE or ""

            # Handle token_expiry properly - must be a valid float or default
            # Use getattr to safely access the attribute in case it doesn't exist
            tidal_token_expiry = (
                getattr(Config, "STREAMRIP_TIDAL_TOKEN_EXPIRY", "") or ""
            )
            if not tidal_token_expiry or not tidal_token_expiry.strip():
                # Set to a future timestamp (1 year from now) if empty
                import time

                tidal_token_expiry = str(int(time.time()) + (365 * 24 * 60 * 60))
            else:
                # Validate existing token_expiry
                try:
                    float(tidal_token_expiry)
                except (ValueError, TypeError):
                    # Invalid format, use default future timestamp
                    import time

                    tidal_token_expiry = str(int(time.time()) + (365 * 24 * 60 * 60))

            # Quality settings based on platform enablement and defaults
            default_quality = Config.STREAMRIP_DEFAULT_QUALITY or 2

            # Platform-specific quality settings
            qobuz_quality = default_quality if Config.STREAMRIP_QOBUZ_ENABLED else 0
            tidal_quality = default_quality if Config.STREAMRIP_TIDAL_ENABLED else 0
            deezer_quality = (
                default_quality if Config.STREAMRIP_DEEZER_ENABLED else 0
            )

            # Download settings
            downloads_folder = Path.home() / "StreamripDownloads"
            source_subdirectories = (
                False  # Keep flat structure for easier bot processing
            )
            concurrent_downloads = Config.STREAMRIP_CONCURRENT_DOWNLOADS or 4

            # Database and conversion settings
            default_codec = Config.STREAMRIP_DEFAULT_CODEC or "flac"

            # Advanced settings

            # Filename and folder templates

            # Quality fallback settings

            # File path formatting settings
            folder_fmt = getattr(
                Config,
                "STREAMRIP_FILEPATHS_FOLDER_FORMAT",
                "{albumartist} - {title} ({year}) [{container}] [{bit_depth}B-{sampling_rate}kHz]",
            )
            track_fmt = getattr(
                Config,
                "STREAMRIP_FILEPATHS_TRACK_FORMAT",
                "{tracknumber:02}. {artist} - {title}{explicit}",
            )

            LOGGER.info("Creating comprehensive streamrip config with:")
            LOGGER.info(
                f"  - Deezer ARL: {'***' + deezer_arl[-10:] if deezer_arl else 'Not set'}"
            )
            LOGGER.info(
                f"  - Qobuz: {'Enabled' if Config.STREAMRIP_QOBUZ_ENABLED else 'Disabled'}"
            )
            LOGGER.info(
                f"  - Tidal: {'Enabled' if Config.STREAMRIP_TIDAL_ENABLED else 'Disabled'}"
            )
            LOGGER.info(
                f"  - SoundCloud: {'Enabled' if Config.STREAMRIP_SOUNDCLOUD_ENABLED else 'Disabled'}"
            )
            LOGGER.info(f"  - Default Quality: {default_quality}")
            LOGGER.info(f"  - Default Codec: {default_codec}")
            LOGGER.info(f"  - Concurrent Downloads: {concurrent_downloads}")

            config_template = """[downloads]
# Folder where tracks are downloaded to
folder = "{downloads_folder}"
# Put Qobuz albums in a 'Qobuz' folder, Tidal albums in 'Tidal' etc.
source_subdirectories = {source_subdirectories}
# Put tracks in an album with 2 or more discs into a subfolder named `Disc N`
disc_subdirectories = true
# Download (and convert) tracks all at once, instead of sequentially.
# If you are converting the tracks, or have fast internet, this will
# substantially improve processing speed.
concurrency = true
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
verify_ssl = true

[qobuz]
# 1: 320kbps MP3, 2: 16/44.1, 3: 24/<=96, 4: 24/>=96
quality = {qobuz_quality}
# This will download booklet pdfs that are included with some albums
download_booklets = true
# Authenticate to Qobuz using auth token? Value can be true/false only
use_auth_token = false
# Enter your userid if the above use_auth_token is set to true, else enter your email
email_or_userid = "{qobuz_email}"
# Enter your auth token if the above use_auth_token is set to true, else enter the md5 hash of your plaintext password
password_or_token = "{qobuz_password}"
# Do not change
app_id = ""
# Do not change
secrets = []

[tidal]
# 0: 256kbps AAC, 1: 320kbps AAC, 2: 16/44.1 "HiFi" FLAC, 3: 24/44.1 "MQA" FLAC
quality = {tidal_quality}
# This will download videos included in Video Albums.
download_videos = true
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
use_deezloader = true
# This warns you when the paid deezer account is not logged in and rip falls
# back to deezloader, which is unreliable
deezloader_warnings = true

[soundcloud]
# Only 0 is available for now
quality = 0
# This changes periodically, so it needs to be updated
client_id = ""
app_version = ""

[youtube]
# Only 0 is available for now
quality = 0
# Download the video along with the audio
download_videos = false
# The path to download the videos to
video_downloads_folder = "{downloads_folder}/youtube"

[database]
# Create a database that contains all the track IDs downloaded so far
# Any time a track logged in the database is requested, it is skipped
# This can be disabled temporarily with the --no-db flag
downloads_enabled = true
# Path to the downloads database
downloads_path = "./downloads.db"
# If a download fails, the item ID is stored here. Then, `rip repair` can be
# called to retry the downloads
failed_downloads_enabled = true
failed_downloads_path = "./failed_downloads.db"

# Convert tracks to a codec after downloading them.
[conversion]
enabled = false
# FLAC, ALAC, OPUS, MP3, VORBIS, or AAC
codec = "ALAC"
# In Hz. Tracks are downsampled if their sampling rate is greater than this.
# Value of 48000 is recommended to maximize quality and minimize space
sampling_rate = 48000
# Only 16 and 24 are available. It is only applied when the bit depth is higher
# than this value.
bit_depth = 24
# Only applicable for lossy codecs
lossy_bitrate = 320

# Filter a Qobuz artist's discography. Set to 'true' to turn on a filter.
# This will also be applied to other sources, but is not guaranteed to work correctly
[qobuz_filters]
# Remove Collectors Editions, live recordings, etc.
extras = false
# Picks the highest quality out of albums with identical titles.
repeats = false
# Remove EPs and Singles
non_albums = false
# Remove albums whose artist is not the one requested
features = false
# Skip non studio albums
non_studio_albums = false
# Only download remastered albums
non_remaster = false

[artwork]
# Write the image to the audio file
embed = true
# The size of the artwork to embed. Options: thumbnail, small, large, original.
# "original" images can be up to 30MB, and may fail embedding.
# Using "large" is recommended.
embed_size = "large"
# If this is set to a value > 0, max(width, height) of the embedded art will be set to this value in pixels
# Proportions of the image will remain the same
embed_max_width = -1
# Save the cover image at the highest quality as a seperate jpg file
save_artwork = true
# If this is set to a value > 0, max(width, height) of the saved art will be set to this value in pixels
# Proportions of the image will remain the same
saved_max_width = -1

[metadata]
# Sets the value of the 'ALBUM' field in the metadata to the playlist's name.
# This is useful if your music library software organizes tracks based on album name.
set_playlist_to_album = true
# If part of a playlist, sets the `tracknumber` field in the metadata to the track's
# position in the playlist instead of its position in its album
renumber_playlist_tracks = true
# The following metadata tags won't be applied
# See https://github.com/nathom/streamrip/wiki/Metadata-Tag-Names for more info
exclude = []

# Changes the folder and file names generated by streamrip.
[filepaths]
# Create folders for single tracks within the downloads directory using the folder_format
# template
add_singles_to_folder = false
# Available keys: "albumartist", "title", "year", "bit_depth", "sampling_rate",
# "id", and "albumcomposer"
folder_format = "{folder_fmt}"
# Available keys: "tracknumber", "artist", "albumartist", "composer", "title",
# and "albumcomposer", "explicit"
track_format = "{track_fmt}"
# Only allow printable ASCII characters in filenames.
restrict_characters = false
# Truncate the filename if it is greater than this number of characters
# Setting this to false may cause downloads to fail on some systems
truncate_to = 120

# Last.fm playlists are downloaded by searching for the titles of the tracks
[lastfm]
# The source on which to search for the tracks.
source = "qobuz"
# If no results were found with the primary source, the item is searched for
# on this one.
fallback_source = ""

[cli]
# Print "Downloading Album name" etc. to screen
text_output = true
# Show resolve, download progress bars
progress_bars = true
# The maximum number of search results to show in the interactive menu
max_search_results = 100

[misc]
# Metadata to identify this config file. Do not change.
version = "2.0.6"
# Print a message if a new version of streamrip is available
check_for_updates = true
"""

            # Format the config template with all the variables
            config = config_template.format(
                downloads_folder=downloads_folder,
                source_subdirectories=str(source_subdirectories).lower(),
                max_connections=getattr(Config, "STREAMRIP_MAX_CONNECTIONS", 6),
                requests_per_minute=getattr(
                    Config, "STREAMRIP_REQUESTS_PER_MINUTE", 60
                ),
                qobuz_quality=qobuz_quality,
                qobuz_email=qobuz_email,
                qobuz_password=qobuz_password,
                tidal_quality=tidal_quality,
                tidal_user_id=tidal_user_id,
                tidal_country_code=tidal_country_code,
                tidal_access_token=tidal_access_token,
                tidal_refresh_token=tidal_refresh_token,
                tidal_token_expiry=tidal_token_expiry,
                deezer_quality=deezer_quality,
                deezer_arl=deezer_arl,
                folder_fmt=folder_fmt,
                track_fmt=track_fmt,
            )

            return config.strip()

        except Exception as e:
            LOGGER.error(f"Error creating comprehensive config: {e}")
            # Return comprehensive fallback config without hardcoded credentials
            return f"""[downloads]
folder = "{Path.home() / "StreamripDownloads"}"
source_subdirectories = false
disc_subdirectories = true
concurrency = 4
max_connections = 6
requests_per_minute = 60
verify_ssl = true

[qobuz]
email_or_userid = ""
password_or_token = ""
quality = 3
use_auth_token = false
app_id = ""
download_booklets = false
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
arl = ""
quality = 2
use_deezloader = false
deezloader_warnings = true

[soundcloud]
client_id = ""
app_version = ""

[youtube]
video_downloads_folder = "{Path.home() / "StreamripDownloads"}/youtube"
quality = "best"

[database]
downloads_enabled = true
downloads_path = "./downloads.db"
failed_downloads_enabled = true
failed_downloads_path = "./failed_downloads.db"

[artwork]
embed = true
embed_size = 1400
embed_max_width = -1
save_artwork = true
saved_max_width = -1

[metadata]
set_playlist_to_album = true
new_playlist_tracknumbers = true
exclude = []

[filepaths]
folder_format = "{{albumartist}}/{{title}}"
track_format = "{{tracknumber}}. {{artist}} - {{title}}"
restrict_characters = false
truncate_to = 120

[conversion]
enabled = false
codec = "FLAC"
sampling_rate = 48000
bit_depth = 24
lossy_bitrate = 320

[misc]
version = "2.0.6"
check_for_updates = false
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
            LOGGER.info(f"Config size: {len(config_content)} bytes")

            # Validate that credentials are actually in the config
            await self._validate_config_credentials(config_file)

            LOGGER.debug("Config will reflect all current bot settings dynamically")

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

            if qobuz_email and qobuz_password:
                if (
                    qobuz_email in config_content
                    and qobuz_password in config_content
                ):
                    LOGGER.info("✅ Qobuz credentials verified in config file")
                else:
                    LOGGER.warning("⚠️ Qobuz credentials not found in config file")
                    LOGGER.warning(
                        f"Email in config: {qobuz_email in config_content}"
                    )
                    LOGGER.warning(
                        f"Password in config: {qobuz_password in config_content}"
                    )

            # Check for Deezer ARL
            deezer_arl = Config.STREAMRIP_DEEZER_ARL or ""
            if deezer_arl:
                if deezer_arl in config_content:
                    LOGGER.info("✅ Deezer ARL verified in config file")
                else:
                    LOGGER.warning("⚠️ Deezer ARL not found in config file")

            # Check for Tidal credentials
            tidal_email = Config.STREAMRIP_TIDAL_EMAIL or ""
            tidal_password = Config.STREAMRIP_TIDAL_PASSWORD or ""

            if tidal_email and tidal_password:
                if (
                    tidal_email in config_content
                    and tidal_password in config_content
                ):
                    LOGGER.info("✅ Tidal credentials verified in config file")
                else:
                    LOGGER.warning("⚠️ Tidal credentials not found in config file")

        except Exception as e:
            LOGGER.error(f"Error validating config credentials: {e}")

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

    async def _test_qobuz_credentials(self) -> bool:
        """Test Qobuz credentials using config validation (no test command in v2.1.0)"""
        try:
            from bot.core.config_manager import Config

            qobuz_email = Config.STREAMRIP_QOBUZ_EMAIL or ""
            qobuz_password = Config.STREAMRIP_QOBUZ_PASSWORD or ""

            if not qobuz_email or not qobuz_password:
                LOGGER.error("Qobuz credentials not configured")
                return False

            # Since 'rip test' doesn't exist in v2.1.0, just validate config format
            LOGGER.info("Validating Qobuz credentials format...")

            # Basic validation
            if "@" not in qobuz_email or len(qobuz_password) < 6:
                LOGGER.error("❌ Invalid Qobuz credentials format")
                LOGGER.error(
                    "Email must contain @ symbol and password must be at least 6 characters"
                )
                return False

            # Check for temporary email providers (common issue)
            temp_email_domains = [
                "temp-mail.me",
                "10minutemail.com",
                "guerrillamail.com",
                "mailinator.com",
            ]
            email_domain = qobuz_email.split("@")[-1].lower()

            if email_domain in temp_email_domains:
                LOGGER.warning(
                    "⚠️ Temporary email provider detected - may cause authentication issues"
                )
                LOGGER.warning(
                    "Consider using a permanent email address for better reliability"
                )

            LOGGER.info("✅ Qobuz credentials format validation passed")
            LOGGER.info("Note: Actual authentication will be tested during download")
            return None  # Skip test, allow download to proceed with actual streamrip validation

        except Exception as e:
            LOGGER.error(f"Error validating Qobuz credentials: {e}")
            return None  # Don't block download on validation errors

    async def _test_tidal_credentials(self) -> bool:
        """Test Tidal credentials using config validation (same logic as Qobuz)"""
        try:
            from bot.core.config_manager import Config

            tidal_email = Config.STREAMRIP_TIDAL_EMAIL or ""
            tidal_password = Config.STREAMRIP_TIDAL_PASSWORD or ""

            if not tidal_email or not tidal_password:
                LOGGER.error("Tidal credentials not configured")
                return False

            # Since 'rip test' doesn't exist in v2.1.0, just validate config format
            LOGGER.info("Validating Tidal credentials format...")

            # Basic validation (same as Qobuz)
            if "@" not in tidal_email or len(tidal_password) < 6:
                LOGGER.error("❌ Invalid Tidal credentials format")
                LOGGER.error(
                    "Email must contain @ symbol and password must be at least 6 characters"
                )
                return False

            # Check for temporary email providers (same as Qobuz)
            temp_email_domains = [
                "temp-mail.me",
                "10minutemail.com",
                "guerrillamail.com",
                "mailinator.com",
            ]
            email_domain = tidal_email.split("@")[-1].lower()

            if email_domain in temp_email_domains:
                LOGGER.warning(
                    "⚠️ Temporary email provider detected - may cause authentication issues"
                )
                LOGGER.warning(
                    "Consider using a permanent email address for better reliability"
                )

            LOGGER.info("✅ Tidal credentials format validation passed")
            LOGGER.info("Note: Actual authentication will be tested during download")
            return None  # Skip test, allow download to proceed with actual streamrip validation

        except Exception as e:
            LOGGER.error(f"Error validating Tidal credentials: {e}")
            return None  # Don't block download on validation errors

    async def _test_soundcloud_credentials(self) -> bool:
        """Test SoundCloud configuration (same logic as Deezer)"""
        try:
            from bot.core.config_manager import Config

            soundcloud_client_id = Config.STREAMRIP_SOUNDCLOUD_CLIENT_ID or ""

            # SoundCloud client ID is optional (like Deezer ARL can be missing)
            if not soundcloud_client_id.strip():
                LOGGER.warning("⚠️ SoundCloud client ID not configured")
                LOGGER.warning(
                    "SoundCloud may work without client ID for some tracks"
                )
                LOGGER.info(
                    "💡 For better reliability, configure SoundCloud client ID"
                )
                return None  # Allow download without client ID

            # Basic validation
            if len(soundcloud_client_id) < 10:
                LOGGER.warning("⚠️ SoundCloud client ID appears to be too short")
                LOGGER.warning("Please verify your SoundCloud client ID")
                return None  # Allow download attempt anyway

            LOGGER.info("✅ SoundCloud configuration validation passed")
            LOGGER.info("Note: Actual functionality will be tested during download")
            return None  # Skip test, allow download to proceed with actual streamrip validation

        except Exception as e:
            LOGGER.error(f"Error validating SoundCloud configuration: {e}")
            return None  # Don't block download on validation errors

    async def _test_deezer_credentials(self) -> bool:
        """Test Deezer credentials using config validation (same logic as Qobuz)"""
        try:
            from bot.core.config_manager import Config

            deezer_arl = Config.STREAMRIP_DEEZER_ARL or ""

            if not deezer_arl.strip():
                LOGGER.error("Deezer ARL not configured")
                return False

            # Since 'rip test' doesn't exist in v2.1.0, just validate config format
            LOGGER.info("Validating Deezer ARL format...")

            # Basic validation for Deezer ARL
            if len(deezer_arl) < 50:
                LOGGER.error("❌ Invalid Deezer ARL format")
                LOGGER.error(
                    "Deezer ARL should be a long string (typically 192+ characters)"
                )
                return False

            # Check for common ARL issues
            if deezer_arl.startswith("http"):
                LOGGER.error(
                    "❌ Invalid Deezer ARL - appears to be a URL instead of ARL token"
                )
                LOGGER.error("Please provide the ARL token, not the URL")
                return False

            LOGGER.info("✅ Deezer ARL format validation passed")
            LOGGER.info("Note: Actual authentication will be tested during download")
            return None  # Skip test, allow download to proceed with actual streamrip validation

        except Exception as e:
            LOGGER.error(f"Error validating Deezer ARL: {e}")
            return None  # Don't block download on validation errors

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
            LOGGER.debug("Checking if streamrip config reset is needed...")

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
                    LOGGER.debug(
                        f"Using Deezer ARL from config: {'***' + deezer_arl[-10:] if deezer_arl else 'Not set'}"
                    )
                except Exception:
                    LOGGER.debug("Could not get Deezer ARL from bot config")

                # Provide ARL input
                create_input = deezer_arl.encode() + b"\n" if deezer_arl else b"\n"

                try:
                    create_stdout, create_stderr = await asyncio.wait_for(
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
            else:
                LOGGER.debug("Streamrip config file exists")

        except Exception as e:
            LOGGER.debug(f"Error checking/creating streamrip config: {e}")
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
            LOGGER.info(f"Config size: {len(config_content)} bytes")

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
            LOGGER.debug(f"Progress monitoring error: {e}")

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
                            LOGGER.debug(f"Cleaned up temp file: {temp_path}")
                    except Exception as e:
                        LOGGER.debug(f"Error cleaning temp file {temp_path}: {e}")
                self._temp_files.clear()
        except Exception as e:
            LOGGER.debug(f"Error during temp file cleanup: {e}")


async def add_streamrip_download(
    listener, url: str, quality: int | None = None, codec: str | None = None
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

    # Parse URL to validate
    from bot.helper.streamrip_utils.url_parser import is_streamrip_url

    if not await is_streamrip_url(url):
        await send_status_message(listener.message, "❌ Invalid streamrip URL!")
        return

    # Check streamrip limits
    if Config.STREAMRIP_LIMIT > 0:
        # For streamrip, we'll estimate size based on quality and track count
        # This is approximate since we don't know exact size until download
        estimated_size = await _estimate_streamrip_size(
            url, quality or Config.STREAMRIP_DEFAULT_QUALITY
        )

        if estimated_size > 0:
            limit_msg = await limit_checker(
                estimated_size, listener, isStreamrip=True
            )
            if limit_msg:
                return

    # Create download helper
    download_helper = StreamripDownloadHelper(listener)

    # Add to task dict
    async with task_dict_lock:
        task_dict[listener.mid] = StreamripDownloadStatus(
            listener, download_helper, url, quality, codec
        )

    # Add to queue if needed
    async with queue_dict_lock:
        dl_count = len(
            [k for k, v in task_dict.items() if v.status() == "Downloading"]
        )

        if dl_count >= Config.QUEUE_DOWNLOAD:
            LOGGER.info(f"Added streamrip download to queue: {url}")
            task_dict[listener.mid] = QueueStatus(listener, "dl")
            await send_status_message(
                listener.message, "⏳ Added to download queue!"
            )
            return

    # Start download immediately
    LOGGER.info(f"Starting streamrip download: {url}")
    download_success = await download_helper.download(url, quality, codec)

    # If download was successful, trigger the upload process
    if download_success:
        LOGGER.info("Streamrip download completed, triggering upload process...")
        await listener.on_download_complete()
    else:
        LOGGER.error("Streamrip download failed")
        await listener.on_download_error("Download failed")


async def _estimate_streamrip_size(url: str, quality: int) -> int:
    """Estimate download size for streamrip content"""
    try:
        from bot.helper.streamrip_utils.url_parser import parse_streamrip_url

        parsed = await parse_streamrip_url(url)
        if not parsed:
            return 0

        platform, media_type, media_id = parsed

        # Size estimates in MB per track based on quality
        size_estimates = {
            0: 4,  # 128 kbps
            1: 10,  # 320 kbps
            2: 35,  # CD Quality
            3: 80,  # Hi-Res
            4: 150,  # Hi-Res+
        }

        track_size_mb = size_estimates.get(quality, 35)

        # Estimate track count based on media type
        if media_type == "track":
            track_count = 1
        elif media_type == "album":
            track_count = 12  # Average album
        elif media_type == "playlist":
            track_count = 25  # Average playlist
        elif media_type == "artist":
            track_count = 50  # Conservative estimate
        else:
            track_count = 10  # Default

        return track_count * track_size_mb * 1024 * 1024

    except Exception as e:
        LOGGER.error(f"Error estimating streamrip size: {e}")
        return 0
