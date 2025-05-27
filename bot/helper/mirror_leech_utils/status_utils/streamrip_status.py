import time

from bot import LOGGER
from bot.helper.ext_utils.status_utils import (
    MirrorStatus,
    get_readable_file_size,
    get_readable_time,
)


class StreamripDownloadStatus:
    """Status class for streamrip downloads following standard bot pattern"""

    def __init__(
        self, listener, download_helper, url: str, quality=None, codec=None
    ):
        self.listener = listener
        self.download_helper = download_helper
        self.url = url
        self.quality = quality
        self.codec = codec
        self._start_time = time.time()
        self.tool = "streamrip"  # Required by status system

    def gid(self):
        """Get unique identifier"""
        return self.listener.mid

    def status(self):
        """Get current status"""
        if self.listener.is_cancelled:
            return MirrorStatus.STATUS_PAUSED
        return MirrorStatus.STATUS_DOWNLOAD

    def name(self):
        """Get download name"""
        if (
            hasattr(self.download_helper, "_current_track")
            and self.download_helper._current_track
        ):
            return self.download_helper._current_track
        if (
            hasattr(self.download_helper, "current_track")
            and self.download_helper.current_track
        ):
            return self.download_helper.current_track
        return self.listener.name or "Streamrip Download"

    def size(self):
        """Get total size"""
        try:
            size = getattr(self.download_helper, "_size", 0) or getattr(
                self.download_helper, "size", 0
            )
            return get_readable_file_size(size)
        except Exception:
            return "N/A"

    def processed_bytes(self):
        """Get processed bytes"""
        try:
            processed = getattr(
                self.download_helper, "_last_downloaded", 0
            ) or getattr(self.download_helper, "processed_bytes", 0)
            return get_readable_file_size(processed)
        except Exception:
            return "0 B"

    def speed(self):
        """Get download speed"""
        try:
            speed = getattr(self.download_helper, "_speed", 0) or getattr(
                self.download_helper, "speed", 0
            )
            return f"{get_readable_file_size(speed)}/s"
        except Exception:
            return "0 B/s"

    def eta(self):
        """Get estimated time of arrival"""
        try:
            eta = getattr(self.download_helper, "_eta", 0) or getattr(
                self.download_helper, "eta", 0
            )
            if eta > 0:
                return get_readable_time(eta)
            return "-"
        except Exception:
            return "-"

    def progress(self):
        """Get download progress"""
        try:
            if hasattr(self.download_helper, "progress"):
                progress_val = self.download_helper.progress
            else:
                # Calculate progress from completed/total tracks
                completed = getattr(self.download_helper, "_completed_tracks", 0)
                total = getattr(self.download_helper, "_total_tracks", 1)
                progress_val = (completed / total) * 100 if total > 0 else 0

            return f"{progress_val:.1f}%"
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

        LOGGER.info(f"Cancelling Streamrip Download: {self.name()}")
        await self.listener.on_download_error("Stopped by user!")
