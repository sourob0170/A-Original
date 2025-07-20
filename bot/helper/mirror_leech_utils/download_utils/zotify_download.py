"""
Zotify download implementation
"""

import asyncio
import contextlib
import shutil
import time
from pathlib import Path
from typing import Any

from zotify import Session
from zotify.collections import Album, Artist, Playlist, Show
from zotify.utils import AudioFormat, ImageSize

from bot import (
    DOWNLOAD_DIR,
    LOGGER,
    task_dict,
    task_dict_lock,
)
from bot.helper.ext_utils.limit_checker import limit_checker
from bot.helper.ext_utils.task_manager import (
    check_running_tasks,
    stop_duplicate_check,
)
from bot.helper.mirror_leech_utils.status_utils.zotify_status import (
    ZotifyDownloadStatus,
)
from bot.helper.mirror_leech_utils.zotify_utils.improved_session_manager import (
    improved_session_manager,
)
from bot.helper.mirror_leech_utils.zotify_utils.quality_selector import (
    show_zotify_quality_selector,
)
from bot.helper.mirror_leech_utils.zotify_utils.special_downloads import (
    get_special_download_info,
    get_special_download_type,
    is_special_download,
)
from bot.helper.mirror_leech_utils.zotify_utils.url_parser import ZotifyUrlParser
from bot.helper.mirror_leech_utils.zotify_utils.zotify_config import zotify_config
from bot.helper.telegram_helper.message_utils import send_status_message


class ZotifyDownloadHelper:
    """Helper class for Zotify downloads"""

    def __init__(self, listener, url: str):
        self.listener = listener
        self.url = url
        self._session = None
        self._download_path = None
        self._is_downloading = False
        self._current_track = ""
        self._total_tracks = 0
        self._downloaded_tracks = 0
        self._start_time = time.time()
        # Optimized progress tracking with memory efficiency
        self._current_downloaded = 0
        self._current_total = 0
        self._current_speed = 0
        self._last_update = time.time()
        # Enhanced progress tracking with bounded memory usage
        self._total_size = 0
        self._downloaded_size = 0
        self._current_file_size = 0
        self._current_file_downloaded = 0
        # Use deque for bounded speed samples (memory efficient)
        from collections import deque

        self._speed_samples = deque(maxlen=10)  # Keep only last 10 samples
        self._last_downloaded = 0
        self._progress_callback = None
        # Memory optimization
        self._last_gc_time = time.time()
        self._gc_interval = 60  # Force GC every minute

    async def get_session(self) -> Session | None:
        """Get or create Zotify session using improved session manager with enhanced error handling"""
        try:
            session = await improved_session_manager.get_session()
            if session:
                return session
            # Get health info for better error reporting
            health_info = improved_session_manager.get_session_health()
            LOGGER.warning(f"Session creation failed. Health: {health_info}")
            return None
        except Exception as e:
            error_msg = str(e)
            # Log specific error types for debugging
            if (
                "Failed reading packet" in error_msg
                or "Failed to receive packet" in error_msg
            ):
                LOGGER.warning(
                    "Connection packet error - librespot connection issue"
                )
            elif (
                "Connection reset by peer" in error_msg
                or "ConnectionResetError" in error_msg
            ):
                LOGGER.warning("Connection reset by Spotify servers")
            elif (
                "ConnectionRefusedError" in error_msg
                or "Connection refused" in error_msg
            ):
                LOGGER.warning("Connection refused by Spotify servers")
            elif "session-packet-receiver" in error_msg:
                LOGGER.warning("Session packet receiver thread error")
            elif "Bad file descriptor" in error_msg:
                LOGGER.warning("Connection descriptor error - retrying may help")
            else:
                LOGGER.error(f"Failed to get Zotify session: {error_msg}")
            return None

    async def get_zotify_config(self):
        """Get Zotify config object with validation"""
        if not hasattr(self, "_zotify_config"):
            try:
                self._zotify_config = zotify_config.create_zotify_config()

                # Validate that we got a proper config object
                if not self._zotify_config:
                    LOGGER.error("create_zotify_config returned None")
                    raise ValueError("Failed to create Zotify config")

                if isinstance(self._zotify_config, bool):
                    LOGGER.error(
                        f"create_zotify_config returned boolean: {self._zotify_config}"
                    )
                    raise ValueError(
                        "Zotify config creation returned boolean instead of config object"
                    )

            except Exception as e:
                LOGGER.error(f"Failed to create Zotify config: {e}")
                raise

        return self._zotify_config

    def get_progress_info(self) -> dict:
        """Get optimized progress information with minimal CPU overhead"""
        current_time = time.time()

        # Periodic garbage collection for memory optimization
        if current_time - self._last_gc_time > self._gc_interval:
            import gc

            gc.collect()
            self._last_gc_time = current_time

        # Calculate speed efficiently
        speed = 0
        if self._speed_samples:
            # Use simple average of recent samples
            speed = sum(self._speed_samples) / len(self._speed_samples)

        return {
            "total_tracks": self._total_tracks,
            "downloaded_tracks": self._downloaded_tracks,
            "current_track": self._current_track,
            "total_size": self._total_size,
            "downloaded_size": self._downloaded_size,
            "current_file_size": self._current_file_size,
            "current_file_downloaded": self._current_file_downloaded,
            "current_speed": speed,
            "is_downloading": self._is_downloading,
            "start_time": self._start_time,
        }

    def _update_speed(self, bytes_downloaded: int):
        """Update speed calculation with memory-efficient sampling"""
        current_time = time.time()
        time_diff = current_time - self._last_update

        if time_diff >= 1.0:  # Update every second
            if self._last_downloaded > 0:
                bytes_diff = bytes_downloaded - self._last_downloaded
                speed = bytes_diff / time_diff
                self._speed_samples.append(speed)

            self._last_downloaded = bytes_downloaded
            self._last_update = current_time

    def _estimate_total_size(self):
        """Estimate total download size based on track count and quality"""
        if self._total_tracks > 0:
            # Estimate based on quality settings
            try:
                config = (
                    self._zotify_config if hasattr(self, "_zotify_config") else None
                )
                if config and hasattr(config, "download_quality"):
                    quality = config.download_quality
                    # Rough size estimates per track based on quality
                    size_estimates = {
                        "VERY_HIGH": 8 * 1024 * 1024,  # ~8MB per track
                        "HIGH": 5 * 1024 * 1024,  # ~5MB per track
                        "NORMAL": 3 * 1024 * 1024,  # ~3MB per track
                        "AUTO": 4 * 1024 * 1024,  # ~4MB per track
                    }
                    estimated_per_track = size_estimates.get(
                        str(quality), 4 * 1024 * 1024
                    )
                else:
                    estimated_per_track = 4 * 1024 * 1024  # Default 4MB

                self._total_size = self._total_tracks * estimated_per_track
            except Exception:
                # Fallback estimation
                self._total_size = self._total_tracks * 4 * 1024 * 1024

    def _get_file_extension(self, audio_format: AudioFormat) -> str:
        """Get file extension from AudioFormat enum"""
        format_extensions = {
            AudioFormat.VORBIS: "ogg",
            AudioFormat.MP3: "mp3",
            AudioFormat.FLAC: "flac",
            AudioFormat.AAC: "m4a",
            AudioFormat.WAV: "wav",
        }
        return format_extensions.get(audio_format, "ogg")

    async def download(self) -> bool:
        """Main download method"""
        try:
            # Check if this is a special download first
            if is_special_download(self.url):
                return await self._download_special()

            # Parse URL to get content type and ID
            parsed = ZotifyUrlParser.parse_spotify_url(self.url)
            if not parsed:
                LOGGER.error(f"Invalid Spotify URL: {self.url}")
                return False

            content_type, spotify_id = parsed

            # Quality selection is now handled in add_zotify_download()
            # Get session
            session = await self.get_session()
            if not session:
                LOGGER.error("Failed to create Zotify session")
                return False

            # Setup download directory
            self._download_path = Path(DOWNLOAD_DIR) / f"zotify_{self.listener.mid}"
            self._download_path.mkdir(parents=True, exist_ok=True)

            # Set downloading flag
            self._is_downloading = True

            # Start download based on content type using Zotify's exact API
            success = False
            if content_type == "track":
                self._total_tracks = 1
                self._estimate_total_size()
                success = await self._download_track(session, spotify_id)
            elif content_type == "album":
                # Get album info first to set total tracks
                config_obj = await self.get_zotify_config()
                album = Album(spotify_id, session.api(), config_obj)
                self._total_tracks = len(album.playables)
                self._estimate_total_size()
                success = await self._download_album(session, spotify_id)
            elif content_type == "playlist":
                # Get playlist info first to set total tracks
                config_obj = await self.get_zotify_config()
                playlist = Playlist(spotify_id, session.api(), config_obj)
                self._total_tracks = len(playlist.playables)
                self._estimate_total_size()
                success = await self._download_playlist(session, spotify_id)
            elif content_type == "artist":
                # Get artist info first to set total tracks
                config_obj = await self.get_zotify_config()
                artist = Artist(spotify_id, session.api(), config_obj)
                self._total_tracks = len(artist.playables)
                self._estimate_total_size()
                success = await self._download_artist(session, spotify_id)
            elif content_type == "show":
                # Get show info first to set total tracks
                config_obj = await self.get_zotify_config()
                show = Show(spotify_id, session.api(), config_obj)
                self._total_tracks = len(show.playables)
                self._estimate_total_size()
                success = await self._download_show(session, spotify_id)
            elif content_type == "episode":
                self._total_tracks = 1
                self._estimate_total_size()
                success = await self._download_episode(session, spotify_id)
            else:
                LOGGER.error(f"Unsupported content type: {content_type}")
                return False

            if success:
                # Move downloaded files to listener directory
                await self._finalize_download()
                return True
            LOGGER.error(f"Zotify download failed: {self.url}")
            return False

        except Exception as e:
            error_msg = str(e)
            # Handle specific connection errors
            if any(
                keyword in error_msg
                for keyword in [
                    "Failed reading packet",
                    "Failed to receive packet",
                    "Connection reset by peer",
                    "ConnectionResetError",
                    "ConnectionRefusedError",
                    "Connection refused",
                    "session-packet-receiver",
                    "RuntimeError",
                ]
            ):
                LOGGER.error(f"Zotify connection error: {error_msg}")
                # Force session recreation for next attempt
                await improved_session_manager.force_session_recreation()
            else:
                LOGGER.error(f"Zotify download error: {error_msg}")
            return False

    async def _download_special(self) -> bool:
        """Download special content (liked tracks, followed artists, etc.)"""
        try:
            special_type = get_special_download_type(self.url)
            if not special_type:
                LOGGER.error(f"Unknown special download type: {self.url}")
                return False

            # Get download info
            download_info = await get_special_download_info(special_type)
            urls = download_info.get("urls", [])

            if not urls:
                LOGGER.warning(f"No items found for {download_info['description']}")
                return False

            self._total_tracks = len(urls)
            self._current_track = f"Downloading {download_info['description']} ({self._total_tracks} items)..."

            # Setup download directory
            self._download_path = Path(DOWNLOAD_DIR) / f"zotify_{self.listener.mid}"
            self._download_path.mkdir(parents=True, exist_ok=True)

            # Get session
            session = await self.get_session()
            if not session:
                LOGGER.error("Failed to create Zotify session")
                return False

            # Download each URL
            success_count = 0
            for i, url in enumerate(urls):
                if self.listener.is_cancelled:
                    break

                self._current_track = (
                    f"Item {i + 1}/{self._total_tracks}: Processing {url}"
                )

                try:
                    # Parse the individual URL
                    parsed = ZotifyUrlParser.parse_spotify_url(url)
                    if not parsed:
                        LOGGER.warning(f"Skipping invalid URL: {url}")
                        continue

                    content_type, spotify_id = parsed

                    # Download based on content type
                    item_success = False
                    if content_type == "track":
                        item_success = await self._download_track(
                            session, spotify_id
                        )
                    elif content_type == "album":
                        item_success = await self._download_album(
                            session, spotify_id
                        )
                    elif content_type == "playlist":
                        item_success = await self._download_playlist(
                            session, spotify_id
                        )
                    elif content_type == "artist":
                        item_success = await self._download_artist(
                            session, spotify_id
                        )
                    elif content_type == "show":
                        item_success = await self._download_show(session, spotify_id)
                    elif content_type == "episode":
                        item_success = await self._download_episode(
                            session, spotify_id
                        )

                    if item_success:
                        success_count += 1
                        self._downloaded_tracks += 1

                except Exception as e:
                    LOGGER.error(f"Failed to download item {url}: {e}")
                    continue

            LOGGER.info(
                f"Special download completed: {success_count}/{len(urls)} items downloaded"
            )
            return success_count > 0

        except Exception as e:
            LOGGER.error(f"Special download failed: {e}")
            return False

    async def _download_track(self, session: Session, track_id: str) -> bool:
        """Download a single track with enhanced error handling and free account optimizations"""
        try:
            self._total_tracks = 1
            self._current_track = "Downloading track..."

            # Get zotify config object
            config_obj = await self.get_zotify_config()

            # Apply rate limiting before track access for free accounts
            session.rate_limiter.apply_limit()

            # Get track with enhanced error handling
            try:
                track = session.get_track(track_id)
                if not track:
                    LOGGER.error(f"Failed to get track metadata for {track_id}")
                    return False
            except Exception as e:
                LOGGER.error(f"Track access failed for {track_id}: {e}")
                # Try one more time with longer delay for free accounts
                await asyncio.sleep(2)
                try:
                    track = session.get_track(track_id)
                except Exception as e2:
                    LOGGER.error(f"Track access retry failed for {track_id}: {e2}")
                    return False

            # Add genre and all artists if configured (these are Track methods)
            if config_obj.save_genre:
                track.add_genre()
            if config_obj.all_artists:
                track.add_all_artists()

            # Get file extension from AudioFormat enum
            file_ext = self._get_file_extension(config_obj.audio_format)

            # Create output path using Zotify's exact method signature with proper folder structure
            # Use the configured template from Config.ZOTIFY_OUTPUT_ALBUM
            from bot.core.config_manager import Config

            output_template = getattr(
                Config,
                "ZOTIFY_OUTPUT_ALBUM",
                "{album_artist}/{album}/{track_number}. {artists} - {title}",
            )

            try:
                # Use Zotify's create_output method with correct parameter order
                # Based on Zotify source: create_output(ext, library, output, replace)
                output = track.create_output(
                    ext=file_ext,  # File extension
                    library=self._download_path,  # Library path
                    output=output_template,  # Output template (parameter name is 'output', not 'template')
                    replace=config_obj.replace_existing,  # Replace existing files
                )

                # Validate that output is not a boolean and is a proper path/object
                if isinstance(output, bool):
                    LOGGER.error(f"track.create_output returned boolean: {output}")
                    return False

                if not output:
                    LOGGER.error("track.create_output returned None or empty value")
                    return False

            except Exception as e:
                LOGGER.error(
                    f"Failed to create output path for track {track_id}: {e}"
                )
                LOGGER.error(
                    f"Parameters used: ext={file_ext}, library={self._download_path}, output={output_template}, replace={config_obj.replace_existing}"
                )
                LOGGER.error(f"Config object type: {type(config_obj)}")
                LOGGER.error(f"Track object type: {type(track)}")
                return False

            self._current_track = f"Downloading: {track.name}"

            # Apply rate limiting using Zotify's built-in rate limiter
            session.rate_limiter.apply_limit()

            # Download track using Zotify's exact method signature with progress tracking
            try:
                file = await self._download_track_with_progress(
                    track, output, config_obj.download_real_time
                )

                if not file:
                    LOGGER.error("Track download returned None or empty file object")
                    return False

            except Exception as e:
                LOGGER.error(f"Track download failed: {e}")
                if "context manager protocol" in str(e):
                    LOGGER.error(
                        "Context manager error in track download - check output parameter"
                    )
                    LOGGER.error(
                        f"Output parameter: {output} (type: {type(output)})"
                    )
                    LOGGER.error(
                        f"Real-time parameter: {config_obj.download_real_time} (type: {type(config_obj.download_real_time)})"
                    )
                raise

            # Clear consecutive hits on successful download
            session.rate_limiter.clear_consec_hits()

            # Write metadata and cover art with enhanced error handling
            if config_obj.save_metadata:
                try:
                    # Get metadata with error handling
                    metadata = track.metadata
                    if metadata:
                        file.write_metadata(metadata)
                        # Metadata written (log removed for cleaner output)
                    else:
                        LOGGER.warning(f"No metadata available for: {track.name}")
                except Exception as e:
                    LOGGER.warning(f"Failed to write metadata for {track.name}: {e}")

                try:
                    # Get cover art with error handling and size fallback
                    cover_art = None
                    artwork_sizes = [
                        config_obj.artwork_size,
                        ImageSize.LARGE,
                        ImageSize.MEDIUM,
                        ImageSize.SMALL,
                    ]

                    for size in artwork_sizes:
                        try:
                            cover_art = track.get_cover_art(size)
                            if cover_art:
                                break
                        except Exception:
                            continue

                    if cover_art:
                        file.write_cover_art(cover_art)
                        # Cover art written (log removed for cleaner output)
                    else:
                        LOGGER.warning(f"No cover art available for: {track.name}")
                except Exception as e:
                    LOGGER.warning(
                        f"Failed to write cover art for {track.name}: {e}"
                    )

            # Download lyrics with free account handling
            if config_obj.lyrics_file:
                try:
                    # Check if track has lyrics
                    has_lyrics = False
                    try:
                        has_lyrics = (
                            track.track.has_lyrics
                            if hasattr(track, "track")
                            and hasattr(track.track, "has_lyrics")
                            else False
                        )
                    except Exception:
                        # For free accounts, lyrics availability might not be accessible
                        pass

                    if has_lyrics:
                        try:
                            lyrics = track.get_lyrics()
                            if lyrics:
                                # Use Zotify's built-in lyrics save method with exact signature
                                lyrics.save(output, prefer_synced=True)
                                LOGGER.info(f"Lyrics downloaded for: {track.name}")
                            else:
                                LOGGER.warning(
                                    f"No lyrics content for: {track.name}"
                                )
                        except Exception as e:
                            # Check if it's a free account limitation
                            api = session.api()
                            try:
                                user_info = api.invoke_url("me")
                                account_type = user_info.get("product", "unknown")
                                if account_type == "free":
                                    LOGGER.info(
                                        f"Lyrics not available for free account: {track.name}"
                                    )
                                else:
                                    LOGGER.warning(
                                        f"Failed to download lyrics for {track.name}: {e}"
                                    )
                            except Exception:
                                LOGGER.warning(
                                    f"Failed to download lyrics for {track.name}: {e}"
                                )
                except Exception as e:
                    LOGGER.warning(f"Lyrics check failed for {track.name}: {e}")

            # Handle transcoding if needed using Zotify's exact method
            if config_obj.audio_format.name != "VORBIS" or config_obj.ffmpeg_args:
                try:
                    file.transcode(
                        audio_format=config_obj.audio_format,  # audio_format parameter
                        download_quality=config_obj.download_quality,  # download_quality parameter
                        bitrate=config_obj.transcode_bitrate,  # bitrate parameter
                        replace=True,  # replace parameter
                        ffmpeg=config_obj.ffmpeg_path,  # ffmpeg parameter
                        opt_args=config_obj.ffmpeg_args.split()
                        if config_obj.ffmpeg_args
                        else [],  # opt_args parameter
                    )
                except Exception as e:
                    LOGGER.warning(f"Transcoding failed: {e}")

            # Clean filename using Zotify's method
            file.clean_filename()

            # Update progress tracking
            if self._total_tracks == 1:
                self._downloaded_tracks = 1
            else:
                self._downloaded_tracks += 1

            return True

        except Exception as e:
            error_msg = str(e)
            LOGGER.error(f"Failed to download track {track_id}: {error_msg}")

            # Provide specific error information for common issues
            if "context manager protocol" in error_msg:
                LOGGER.error(
                    "Context manager error - likely boolean value used where file object expected"
                )
                LOGGER.error(f"Track object type: {type(track)}")
                LOGGER.error(
                    f"Output object type: {type(output) if 'output' in locals() else 'output not created'}"
                )
                LOGGER.error(
                    f"Config object type: {type(config_obj) if 'config_obj' in locals() else 'config not created'}"
                )
            elif "write_audio_stream" in error_msg:
                LOGGER.error(
                    "Error in write_audio_stream - check Zotify library compatibility"
                )
            elif "create_output" in error_msg:
                LOGGER.error(
                    "Error creating output path - check file permissions and path validity"
                )

            return False

    async def _download_album(self, session: Session, album_id: str) -> bool:
        """Download an album"""
        try:
            # Create album collection using Zotify's exact constructor
            config_obj = await self.get_zotify_config()
            album = Album(album_id, session.api(), config_obj)

            self._total_tracks = len(album.playables)
            self._current_track = (
                f"Downloading album ({self._total_tracks} tracks)..."
            )

            # Download all tracks in album
            for i, playable_data in enumerate(album.playables):
                if self.listener.is_cancelled:
                    return False

                self._current_track = f"Track {i + 1}/{self._total_tracks}"

                # Download individual track (track method handles increment)
                await self._download_track(session, playable_data.id)

            return self._downloaded_tracks > 0

        except Exception as e:
            LOGGER.error(f"Failed to download album {album_id}: {e}")
            return False

    async def _download_playlist(self, session: Session, playlist_id: str) -> bool:
        """Download a playlist"""
        try:
            # Create playlist collection using Zotify's exact constructor
            config_obj = await self.get_zotify_config()
            playlist = Playlist(playlist_id, session.api(), config_obj)

            self._total_tracks = len(playlist.playables)
            self._current_track = (
                f"Downloading playlist ({self._total_tracks} tracks)..."
            )

            # Download all tracks in playlist
            for i, playable_data in enumerate(playlist.playables):
                if self.listener.is_cancelled:
                    return False

                self._current_track = f"Track {i + 1}/{self._total_tracks}"

                # Download based on playable type (methods handle increment)
                if playable_data.type.name == "TRACK":
                    await self._download_track(session, playable_data.id)
                elif playable_data.type.name == "EPISODE":
                    await self._download_episode(session, playable_data.id)
                else:
                    continue

            return self._downloaded_tracks > 0

        except Exception as e:
            LOGGER.error(f"Failed to download playlist {playlist_id}: {e}")
            return False

    async def _download_artist(self, session: Session, artist_id: str) -> bool:
        """Download artist's top tracks"""
        try:
            # Create artist collection using Zotify's exact constructor
            config_obj = await self.get_zotify_config()
            artist = Artist(artist_id, session.api(), config_obj)

            self._total_tracks = len(artist.playables)
            self._current_track = (
                f"Downloading artist tracks ({self._total_tracks} tracks)..."
            )

            # Download all tracks
            for i, playable_data in enumerate(artist.playables):
                if self.listener.is_cancelled:
                    return False

                self._current_track = f"Track {i + 1}/{self._total_tracks}"

                # Download track (method handles increment)
                await self._download_track(session, playable_data.id)

            return self._downloaded_tracks > 0

        except Exception as e:
            LOGGER.error(f"Failed to download artist {artist_id}: {e}")
            return False

    async def _download_show(self, session: Session, show_id: str) -> bool:
        """Download a podcast show"""
        try:
            # Create show collection using Zotify's exact constructor
            config_obj = await self.get_zotify_config()
            show = Show(show_id, session.api(), config_obj)

            self._total_tracks = len(show.playables)
            self._current_track = (
                f"Downloading show ({self._total_tracks} episodes)..."
            )

            # Download all episodes
            for i, playable_data in enumerate(show.playables):
                if self.listener.is_cancelled:
                    return False

                self._current_track = f"Episode {i + 1}/{self._total_tracks}"

                # Download episode (method handles increment)
                await self._download_episode(session, playable_data.id)

            return self._downloaded_tracks > 0

        except Exception as e:
            LOGGER.error(f"Failed to download show {show_id}: {e}")
            return False

    async def _download_episode(self, session: Session, episode_id: str) -> bool:
        """Download a podcast episode"""
        try:
            self._current_track = "Downloading episode..."

            # Get zotify config object
            config_obj = await self.get_zotify_config()

            # Get episode
            episode = session.get_episode(episode_id)

            # Get file extension from AudioFormat enum
            file_ext = self._get_file_extension(config_obj.audio_format)

            # Create output path using Zotify's exact method signature with proper folder structure
            try:
                # Use Zotify's create_output method with correct parameter order
                # Based on Zotify source: create_output(ext, library, output, replace)
                output = episode.create_output(
                    ext=file_ext,  # File extension
                    library=self._download_path,  # Library path
                    output="{podcast}/{episode_number} - {title}",  # Output template (parameter name is 'output', not 'template')
                    replace=config_obj.replace_existing,  # Replace existing files
                )

                # Validate that output is not a boolean and is a proper path/object
                if isinstance(output, bool):
                    LOGGER.error(f"episode.create_output returned boolean: {output}")
                    return False

                if not output:
                    LOGGER.error(
                        "episode.create_output returned None or empty value"
                    )
                    return False

            except Exception as e:
                LOGGER.error(
                    f"Failed to create output path for episode {episode_id}: {e}"
                )
                LOGGER.error(
                    f"Parameters used: ext={file_ext}, library={self._download_path}, output=podcast template, replace={config_obj.replace_existing}"
                )
                LOGGER.error(f"Config object type: {type(config_obj)}")
                LOGGER.error(f"Episode object type: {type(episode)}")
                return False

            self._current_track = f"Downloading: {episode.name}"

            # Apply rate limiting using Zotify's built-in rate limiter
            session.rate_limiter.apply_limit()

            # Download episode using Zotify's exact method signature with progress tracking
            file = await self._download_episode_with_progress(
                episode, output, config_obj.download_real_time
            )

            # Clear consecutive hits on successful download
            session.rate_limiter.clear_consec_hits()

            # Write metadata and cover art using Zotify's exact methods
            if config_obj.save_metadata:
                file.write_metadata(episode.metadata)
                file.write_cover_art(episode.get_cover_art(config_obj.artwork_size))

            # Handle transcoding if needed using Zotify's exact method
            if config_obj.audio_format.name != "VORBIS" or config_obj.ffmpeg_args:
                try:
                    file.transcode(
                        audio_format=config_obj.audio_format,  # audio_format parameter
                        download_quality=config_obj.download_quality,  # download_quality parameter
                        bitrate=config_obj.transcode_bitrate,  # bitrate parameter
                        replace=True,  # replace parameter
                        ffmpeg=config_obj.ffmpeg_path,  # ffmpeg parameter
                        opt_args=config_obj.ffmpeg_args.split()
                        if config_obj.ffmpeg_args
                        else [],  # opt_args parameter
                    )
                except Exception as e:
                    LOGGER.warning(f"Transcoding failed: {e}")

            file.clean_filename()

            # Update progress tracking
            if self._total_tracks == 1:
                self._downloaded_tracks = 1
            else:
                self._downloaded_tracks += 1

            return True

        except Exception as e:
            LOGGER.error(f"Failed to download episode {episode_id}: {e}")
            return False

    async def _finalize_download(self):
        """Move downloaded files to listener directory preserving folder structure"""
        try:
            if self._download_path and self._download_path.exists():
                # Move all files to listener directory preserving folder structure
                for file_path in self._download_path.rglob("*"):
                    if file_path.is_file():
                        # Preserve the relative path structure
                        relative_path = file_path.relative_to(self._download_path)
                        dest_path = Path(self.listener.dir) / relative_path

                        # Ensure destination directory exists
                        dest_path.parent.mkdir(parents=True, exist_ok=True)

                        # Move the file preserving structure
                        shutil.move(str(file_path), str(dest_path))

                # Clean up temporary directory
                shutil.rmtree(self._download_path, ignore_errors=True)

        except Exception as e:
            LOGGER.error(f"Failed to finalize download: {e}")

    def _update_progress(self, downloaded: int, total: int):
        """Update download progress with speed calculation"""
        current_time = time.time()
        self._current_file_downloaded = downloaded
        self._current_file_size = total

        # Calculate total downloaded size
        self._downloaded_size = (
            self._downloaded_tracks * 5 * 1024 * 1024
        ) + downloaded

        # Calculate speed (bytes per second)
        if current_time - self._last_update >= 1.0:  # Update every second
            bytes_diff = self._downloaded_size - self._last_downloaded
            time_diff = current_time - self._last_update

            if time_diff > 0:
                current_speed = bytes_diff / time_diff

                # Keep last 10 speed samples for smoothing
                self._speed_samples.append(current_speed)
                if len(self._speed_samples) > 10:
                    self._speed_samples.pop(0)

                # Calculate average speed
                self._current_speed = sum(self._speed_samples) / len(
                    self._speed_samples
                )

            self._last_downloaded = self._downloaded_size
            self._last_update = current_time

    def _estimate_total_size(self):
        """Estimate total download size based on content type"""
        if self._total_tracks > 0:
            # Estimate 5MB per track on average
            self._total_size = self._total_tracks * 5 * 1024 * 1024

    async def _download_track_with_progress(self, track, output, real_time=False):
        """Download track with progress tracking by monitoring file size"""
        import asyncio

        # Validate inputs before starting download
        if isinstance(output, bool):
            raise ValueError(
                f"Output parameter is boolean ({output}) instead of file path/object"
            )

        if not output:
            raise ValueError("Output parameter is None or empty")

        # Start the actual download in a separate task
        try:
            # Create a dummy progress bar for Zotify (we'll handle progress ourselves)
            from tqdm import tqdm

            dummy_pbar = tqdm(disable=True)  # Disabled progress bar

            download_task = asyncio.create_task(
                asyncio.to_thread(
                    track.write_audio_stream, output, dummy_pbar, real_time
                )
            )
        except Exception as e:
            LOGGER.error(f"Failed to create download task: {e}")
            raise

        # Monitor progress while download is running
        progress_task = asyncio.create_task(self._monitor_download_progress(output))

        try:
            # Wait for download to complete
            file = await download_task

            # Cancel progress monitoring
            progress_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await progress_task

            return file

        except Exception as e:
            # Cancel progress monitoring on error
            progress_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await progress_task
            raise e

    async def _monitor_download_progress(self, output_path):
        """Monitor download progress by checking file size"""
        import asyncio
        import os

        # Validate output_path
        if isinstance(output_path, bool):
            LOGGER.error(
                f"output_path is boolean ({output_path}) instead of file path"
            )
            return

        if not output_path:
            LOGGER.error("output_path is None or empty")
            return

        # Convert to string if it's a Path object
        output_path_str = str(output_path)

        try:
            while True:
                try:
                    if os.path.exists(output_path_str):
                        current_size = os.path.getsize(output_path_str)
                        # Estimate total file size (5MB average for high quality)
                        estimated_total = 5 * 1024 * 1024

                        # Update progress
                        self._update_progress(current_size, estimated_total)

                        # If file seems complete (close to estimated size), break
                        if current_size >= estimated_total * 0.9:
                            break

                    # Check every 0.5 seconds
                    await asyncio.sleep(0.5)

                except Exception:
                    await asyncio.sleep(1)

        except asyncio.CancelledError:
            # Task was cancelled, which is expected
            pass
        except Exception as e:
            LOGGER.warning(f"Progress monitoring failed: {e}")

    async def _download_episode_with_progress(
        self, episode, output, real_time=False
    ):
        """Download episode with progress tracking by monitoring file size"""
        import asyncio

        # Validate inputs before starting download
        if isinstance(output, bool):
            raise ValueError(
                f"Output parameter is boolean ({output}) instead of file path/object"
            )

        if not output:
            raise ValueError("Output parameter is None or empty")

        # Start the actual download in a separate task
        try:
            # Create a dummy progress bar for Zotify (we'll handle progress ourselves)
            from tqdm import tqdm

            dummy_pbar = tqdm(disable=True)  # Disabled progress bar

            download_task = asyncio.create_task(
                asyncio.to_thread(
                    episode.write_audio_stream, output, dummy_pbar, real_time
                )
            )
        except Exception as e:
            LOGGER.error(f"Failed to create episode download task: {e}")
            raise

        # Monitor progress while download is running
        progress_task = asyncio.create_task(self._monitor_download_progress(output))

        try:
            # Wait for download to complete
            file = await download_task

            # Cancel progress monitoring
            progress_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await progress_task

            return file

        except Exception as e:
            # Cancel progress monitoring on error
            progress_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await progress_task
            raise e

    def get_progress_info(self) -> dict[str, Any]:
        """Get current download progress information with real-time tracking"""
        return {
            "current_track": self._current_track,
            "downloaded_tracks": self._downloaded_tracks,
            "total_tracks": self._total_tracks,
            "is_downloading": self._is_downloading,
            "start_time": self._start_time,
            # Real-time progress tracking like Zotify
            "current_downloaded": self._current_downloaded,
            "current_total": self._current_total,
            "current_speed": self._current_speed,
            "last_update": self._last_update,
            # Enhanced progress tracking
            "total_size": self._total_size,
            "downloaded_size": self._downloaded_size,
            "current_file_size": self._current_file_size,
            "current_file_downloaded": self._current_file_downloaded,
        }


async def _estimate_zotify_size(url: str) -> int:
    """Estimate download size for Zotify based on URL type"""
    try:
        # Basic size estimates in bytes
        if "track/" in url:
            return 5 * 1024 * 1024  # ~5MB per track
        if "album/" in url:
            return 50 * 1024 * 1024  # ~50MB per album (10 tracks average)
        if "playlist/" in url:
            return 100 * 1024 * 1024  # ~100MB per playlist (20 tracks average)
        if "artist/" in url:
            return 200 * 1024 * 1024  # ~200MB for artist top tracks
        if "show/" in url or "episode/" in url:
            return 50 * 1024 * 1024  # ~50MB per podcast episode
        return 10 * 1024 * 1024  # Default ~10MB
    except Exception:
        return 10 * 1024 * 1024  # Default fallback


async def add_zotify_download(listener, url: str):
    """Add Zotify download to task queue"""
    if not zotify_config.is_enabled():
        await listener.on_download_error("Zotify is disabled")
        return

    if not await zotify_config.has_credentials():
        await listener.on_download_error("Zotify credentials not configured")
        return

    # Check if URL is valid
    if not ZotifyUrlParser.is_spotify_url(url):
        await listener.on_download_error("Invalid Spotify URL")
        return

    # Check limits
    # For Zotify, estimate size based on URL type (track ~5MB, album ~50MB, playlist ~100MB)
    estimated_size = await _estimate_zotify_size(url)
    if estimated_size > 0:
        limit_msg = await limit_checker(estimated_size, listener)
        if limit_msg:
            return

    # Check running tasks and queue management
    add_to_queue, event = await check_running_tasks(listener)

    # Check for duplicates
    msg, button = await stop_duplicate_check(listener)
    if msg:
        await listener.on_download_error(msg, button)
        return

    # Parse URL to get content type for quality selection
    parsed = ZotifyUrlParser.parse_spotify_url(url)
    if not parsed:
        await listener.on_download_error("Invalid Spotify URL format")
        return

    content_type, spotify_id = parsed

    # Show quality selector BEFORE creating task and status
    quality_selection = await show_zotify_quality_selector(listener, content_type)

    if not quality_selection:
        LOGGER.info("Quality selection cancelled or failed")
        await listener.on_download_error("Quality selection cancelled")
        return

    # Apply selected quality and format to config
    selected_quality = quality_selection["quality"]
    selected_format = quality_selection["format"]

    # Update config with user selection
    zotify_config.set_quality(selected_quality)
    zotify_config.set_audio_format(selected_format)

    try:
        # Create download helper
        download_helper = ZotifyDownloadHelper(listener, url)

        # Set zotify-specific attributes on the listener
        listener.url = url

        # Add to task dict with proper status
        async with task_dict_lock:
            task_dict[listener.mid] = ZotifyDownloadStatus(
                listener, download_helper, queued=add_to_queue
            )

        # Handle queuing
        if add_to_queue:
            LOGGER.info(f"Added zotify download to queue: {url}")
            await send_status_message(
                listener.message, "⏳ Added to download queue!"
            )
            await event.wait()
            if listener.is_cancelled:
                return
            LOGGER.info(f"Start from Queued/Download: {listener.name}")

        # Update task dict for active download
        async with task_dict_lock:
            task_dict[listener.mid] = ZotifyDownloadStatus(
                listener, download_helper, queued=False
            )

        # Send status message
        await send_status_message(listener.message)

        # Start download
        success = await download_helper.download()

        if success:
            # Initialize media tools settings before upload (only for specialized listeners)
            if hasattr(listener, "initialize_media_tools"):
                await listener.initialize_media_tools()
            await listener.on_download_complete()
        else:
            await listener.on_download_error("Zotify download failed")

    except Exception as e:
        LOGGER.error(f"Zotify download error: {e}")
        await listener.on_download_error(f"Zotify download error: {e}")
