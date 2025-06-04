"""
Zotify download status tracking
"""

import time

from bot import LOGGER
from bot.helper.ext_utils.status_utils import (
    MirrorStatus,
    get_readable_file_size,
    get_readable_time,
)


class ZotifyDownloadStatus:
    """Status class for Zotify downloads following standard bot pattern"""

    def __init__(self, listener, download_helper, queued=False):
        self.listener = listener
        self.download_helper = download_helper
        self.queued = queued
        self._start_time = time.time()
        self.tool = "zotify"  # Required by status system

    def gid(self):
        """Get unique identifier"""
        return self.listener.mid

    def status(self):
        """Get current status"""
        if self.listener.is_cancelled:
            return MirrorStatus.STATUS_PAUSED
        if self.queued:
            return MirrorStatus.STATUS_QUEUEDL
        return MirrorStatus.STATUS_DOWNLOAD

    def name(self):
        """Get download name"""
        if (
            hasattr(self.download_helper, "_current_track")
            and self.download_helper._current_track
        ):
            return self.download_helper._current_track
        return self.listener.name or "Zotify Download"

    def size(self):
        """Get total size"""
        try:
            if hasattr(self.download_helper, "get_progress_info"):
                progress_info = self.download_helper.get_progress_info()
                total_size = progress_info.get("total_size", 0)
                if total_size > 0:
                    return get_readable_file_size(total_size)
                # Fallback to track-based estimation
                total_tracks = progress_info.get("total_tracks", 0)
                if total_tracks > 0:
                    estimated_total_size = total_tracks * 5 * 1024 * 1024
                    return get_readable_file_size(estimated_total_size)
            return "N/A"
        except Exception:
            return "N/A"

    def processed_bytes(self):
        """Get processed bytes"""
        try:
            if hasattr(self.download_helper, "get_progress_info"):
                progress_info = self.download_helper.get_progress_info()
                downloaded_size = progress_info.get("downloaded_size", 0)
                if downloaded_size > 0:
                    return get_readable_file_size(downloaded_size)
                # Fallback to track-based estimation
                downloaded_tracks = progress_info.get("downloaded_tracks", 0)
                estimated_downloaded = downloaded_tracks * 5 * 1024 * 1024
                return get_readable_file_size(estimated_downloaded)
            return "0 B"
        except Exception:
            return "0 B"

    def speed(self):
        """Get download speed"""
        try:
            if hasattr(self.download_helper, "get_progress_info"):
                progress_info = self.download_helper.get_progress_info()
                current_speed = progress_info.get("current_speed", 0)
                if current_speed > 0:
                    return f"{get_readable_file_size(int(current_speed))}/s"
                # Fallback to track-based calculation
                downloaded_tracks = progress_info.get("downloaded_tracks", 0)
                if downloaded_tracks > 0:
                    elapsed_time = time.time() - self._start_time
                    if elapsed_time > 0:
                        tracks_per_second = downloaded_tracks / elapsed_time
                        estimated_speed = tracks_per_second * 5 * 1024 * 1024
                        return f"{get_readable_file_size(int(estimated_speed))}/s"
            return "0 B/s"
        except Exception:
            return "0 B/s"

    def eta(self):
        """Get estimated time of arrival"""
        try:
            if hasattr(self.download_helper, "get_progress_info"):
                progress_info = self.download_helper.get_progress_info()
                total_tracks = progress_info.get("total_tracks", 0)
                downloaded_tracks = progress_info.get("downloaded_tracks", 0)

                if downloaded_tracks > 0 and total_tracks > downloaded_tracks:
                    elapsed_time = time.time() - self._start_time
                    tracks_per_second = downloaded_tracks / elapsed_time
                    remaining_tracks = total_tracks - downloaded_tracks

                    if tracks_per_second > 0:
                        eta_seconds = remaining_tracks / tracks_per_second
                        return get_readable_time(int(eta_seconds))
            return "-"
        except Exception:
            return "-"

    def progress(self):
        """Get download progress with detailed information"""
        try:
            if hasattr(self.download_helper, "get_progress_info"):
                progress_info = self.download_helper.get_progress_info()
                total_tracks = progress_info.get("total_tracks", 0)
                downloaded_tracks = progress_info.get("downloaded_tracks", 0)
                current_file_downloaded = progress_info.get(
                    "current_file_downloaded", 0
                )
                current_file_size = progress_info.get("current_file_size", 0)

                if total_tracks > 0:
                    # Calculate overall progress
                    overall_progress = (downloaded_tracks / total_tracks) * 100

                    # Calculate current file progress
                    current_file_progress = 0
                    if current_file_size > 0:
                        current_file_progress = (
                            current_file_downloaded / current_file_size
                        ) * 100

                    # If we're downloading a file, show combined progress
                    if (
                        current_file_progress > 0
                        and downloaded_tracks < total_tracks
                    ):
                        # Add current file progress to overall
                        file_contribution = (1 / total_tracks) * 100
                        total_progress = overall_progress + (
                            current_file_progress * file_contribution / 100
                        )
                        return f"{total_progress:.1f}% ({downloaded_tracks + 1}/{total_tracks})"
                    return f"{overall_progress:.1f}% ({downloaded_tracks}/{total_tracks})"
            return "0%"
        except Exception:
            return "0%"

    def task(self):
        """Get task object (standard method)"""
        return self

    async def cancel_task(self):
        """Cancel the download task (standard method)"""
        self.listener.is_cancelled = True
        if hasattr(self.download_helper, "cancel_download"):
            self.download_helper.cancel_download()

        # Perform music-specific cleanup
        try:
            from bot.helper.ext_utils.gc_utils import music_download_cleanup

            music_download_cleanup()
        except Exception:
            pass

        LOGGER.info(f"Cancelling Zotify Download: {self.name()}")
        await self.listener.on_download_error("Stopped by user!")
