# ruff: noqa: ARG005, B023
import contextlib
import gc
from asyncio import create_task
from logging import getLogger
from os import listdir
from os import path as ospath
from re import search as re_search
from secrets import token_hex

from yt_dlp import DownloadError, YoutubeDL

from bot import task_dict, task_dict_lock
from bot.helper.ext_utils.bot_utils import async_to_sync, sync_to_async
from bot.helper.ext_utils.limit_checker import limit_checker
from bot.helper.ext_utils.task_manager import (
    check_running_tasks,
    stop_duplicate_check,
)

try:
    from bot.helper.ext_utils.gc_utils import smart_garbage_collection
except ImportError:
    smart_garbage_collection = None
from bot.helper.mirror_leech_utils.status_utils.queue_status import QueueStatus
from bot.helper.mirror_leech_utils.status_utils.yt_dlp_status import YtDlpStatus
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    send_message,
    send_status_message,
)

LOGGER = getLogger(__name__)


class MyLogger:
    # Class variable to track title extraction warnings
    title_extraction_warning = False

    def __init__(self, obj, listener):
        self._obj = obj
        self._listener = listener

    def debug(self, msg):
        # Hack to fix changing extension
        if not self._obj.is_playlist and (
            match := re_search(
                r".Merger..Merging formats into..(.*?).$",
                msg,
            )
            or re_search(r".ExtractAudio..Destination..(.*?)$", msg)
        ):
            LOGGER.info(msg)
            newname = match.group(1)
            newname = newname.rsplit("/", 1)[-1]
            self._listener.name = newname

    @staticmethod
    def warning(msg):
        # Handle specific warnings that need attention
        if "Extractor failed to obtain" in msg and "title" in msg:
            LOGGER.warning(f"YT-DLP Warning: {msg}")
            # Set the class variable to indicate title extraction failed
            MyLogger.title_extraction_warning = True
        elif (
            "xtra not found" in msg
            or "ffmpeg not found" in msg
            or "Requested format is not available" in msg
        ):
            LOGGER.warning(f"YT-DLP Warning: {msg}")

    @staticmethod
    def error(msg):
        if msg != "ERROR: Cancelling...":
            LOGGER.error(msg)


class YoutubeDLHelper:
    def __init__(self, listener):
        self._last_downloaded = 0
        self._progress = 0
        self._downloaded_bytes = 0
        self._download_speed = 0
        self._eta = "-"
        self._listener = listener
        self._gid = ""
        self._ext = ""
        self.is_playlist = False

        # Check for user-specific cookies (multiple cookies support)
        user_id = listener.user_id
        self.user_cookies_list = self._get_user_cookies_list(user_id)

        # Use first available cookie or default
        if self.user_cookies_list:
            cookies_file = self.user_cookies_list[0]
            self.current_cookie_index = 0
        else:
            cookies_file = "cookies.txt"
            self.current_cookie_index = -1

        self.opts = {
            "progress_hooks": [self._on_download_progress],
            "logger": MyLogger(self, self._listener),
            "usenetrc": True,
            "cookiefile": cookies_file,
            "allow_multiple_video_streams": True,
            "allow_multiple_audio_streams": True,
            "noprogress": True,
            "allow_playlist_files": True,
            "overwrites": True,
            "writethumbnail": True,
            "trim_file_name": 220,
            "ffmpeg_location": "/usr/bin/xtra",
            "fragment_retries": 10,
            "retries": 10,
            "extractor_retries": 5,
            "file_access_retries": 5,
            "retry_sleep_functions": {
                "http": lambda n: 3,
                "fragment": lambda n: 3,
                "file_access": lambda n: 3,
                "extractor": lambda n: 3,
            },
            # YouTube TV client settings to help with SSAP experiment issues
            "extractor_args": {
                "youtube": {
                    "player_client": ["tv"],
                    "max_comments": [0],
                }
            },
        }

        # Log which cookies file is being used
        if self.user_cookies_list:
            cookie_num = (
                ospath.basename(cookies_file)
                .replace(f"{user_id}_", "")
                .replace(".txt", "")
            )
            LOGGER.info(
                f"Using user cookie #{cookie_num} for user ID: {user_id} (Total: {len(self.user_cookies_list)} cookies)"
            )
        else:
            LOGGER.info("Using default cookies.txt file")

    def _get_user_cookies_list(self, user_id):
        """Get list of all cookie files for a user (from both database and filesystem)"""
        cookies_list = []

        # First, try to get cookies from database and create temporary files
        try:
            import asyncio

            from bot.helper.ext_utils.db_handler import database

            # Get cookies from database
            db_cookies = asyncio.run(database.get_user_cookies(user_id))

            for cookie in db_cookies:
                cookie_num = cookie["number"]
                cookie_data = cookie["data"]

                # Create temporary file for this cookie
                temp_cookie_path = f"cookies/{user_id}_{cookie_num}.txt"

                # Ensure cookies directory exists
                import os

                os.makedirs("cookies", exist_ok=True)

                # Write cookie data to temporary file if it doesn't exist
                if not ospath.exists(temp_cookie_path):
                    try:
                        with open(temp_cookie_path, "wb") as f:
                            f.write(cookie_data)
                        LOGGER.info(
                            f"Created temporary cookie file #{cookie_num} for user {user_id}"
                        )
                    except Exception as e:
                        LOGGER.error(
                            f"Error creating temporary cookie file #{cookie_num}: {e}"
                        )
                        continue

                cookies_list.append(temp_cookie_path)

        except Exception as e:
            LOGGER.error(
                f"Error getting cookies from database for user {user_id}: {e}"
            )

        # Also check for existing files in filesystem
        cookies_dir = "cookies/"
        if ospath.exists(cookies_dir):
            try:
                import os

                for filename in os.listdir(cookies_dir):
                    if filename.startswith(f"{user_id}_") and filename.endswith(
                        ".txt"
                    ):
                        filepath = f"{cookies_dir}{filename}"
                        if ospath.exists(filepath) and filepath not in cookies_list:
                            cookies_list.append(filepath)
            except Exception as e:
                LOGGER.error(f"Error getting user cookies from filesystem: {e}")

        # Sort by cookie number
        try:
            cookies_list.sort(
                key=lambda x: int(
                    ospath.basename(x).replace(f"{user_id}_", "").replace(".txt", "")
                )
                if ospath.basename(x)
                .replace(f"{user_id}_", "")
                .replace(".txt", "")
                .isdigit()
                else 999
            )
        except Exception as e:
            LOGGER.error(f"Error sorting cookies list: {e}")

        return cookies_list

    def _try_next_cookie(self):
        """Try the next available cookie for the user"""
        if (
            not self.user_cookies_list
            or self.current_cookie_index >= len(self.user_cookies_list) - 1
        ):
            return False

        self.current_cookie_index += 1
        new_cookie = self.user_cookies_list[self.current_cookie_index]

        # Update the cookiefile in opts
        self.opts["cookiefile"] = new_cookie

        cookie_num = (
            ospath.basename(new_cookie)
            .replace(f"{self._listener.user_id}_", "")
            .replace(".txt", "")
        )
        LOGGER.info(
            f"Trying next cookie #{cookie_num} for user ID: {self._listener.user_id}"
        )

        return True

    def _should_try_next_cookie(self, error_str):
        """Check if the error indicates we should try the next cookie"""
        cookie_related_errors = [
            "sign in to confirm",
            "this video is unavailable",
            "private video",
            "members-only content",
            "requires authentication",
            "login required",
            "access denied",
            "forbidden",
            "unauthorized",
            "premium content",
            "subscription required",
            "age-restricted",
            "not available in your country",
            "geo-blocked",
            "region blocked",
            "unable to extract video data",
            "video unavailable",
            "cookies",
            "authentication",
            "401",
            "403",
        ]

        error_lower = error_str.lower()
        return any(
            error_phrase in error_lower for error_phrase in cookie_related_errors
        )

    @property
    def download_speed(self):
        return self._download_speed

    @property
    def downloaded_bytes(self):
        return self._downloaded_bytes

    @property
    def size(self):
        return self._listener.size

    @property
    def progress(self):
        return self._progress

    @property
    def eta(self):
        return self._eta

    def _on_download_progress(self, d):
        if self._listener.is_cancelled:
            raise ValueError("Cancelling...")
        if d["status"] == "finished":
            if self.is_playlist:
                self._last_downloaded = 0
        elif d["status"] == "downloading":
            self._download_speed = d["speed"] or 0
            if self.is_playlist:
                downloadedBytes = d["downloaded_bytes"] or 0
                chunk_size = downloadedBytes - self._last_downloaded
                self._last_downloaded = downloadedBytes
                self._downloaded_bytes += chunk_size
            else:
                if d.get("total_bytes"):
                    self._listener.size = d["total_bytes"] or 0
                elif d.get("total_bytes_estimate"):
                    self._listener.size = d["total_bytes_estimate"] or 0
                self._downloaded_bytes = d["downloaded_bytes"] or 0
                self._eta = d.get("eta", "-") or "-"
            with contextlib.suppress(Exception):
                self._progress = (self._downloaded_bytes / self._listener.size) * 100

    async def _on_download_start(self, from_queue=False):
        async with task_dict_lock:
            task_dict[self._listener.mid] = YtDlpStatus(
                self._listener,
                self,
                self._gid,
            )
        if not from_queue:
            await self._listener.on_download_start()
            if self._listener.multi <= 1:
                await send_status_message(self._listener.message)

    def _on_download_error(self, error):
        self._listener.is_cancelled = True
        try:
            async_to_sync(self._listener.on_download_error, error)
        except Exception as e:
            LOGGER.error(f"Failed to handle error through listener: {e!s}")
            # Fallback error handling
            error_msg = async_to_sync(
                send_message,
                self._listener.message,
                f"{self._listener.tag} Download: {error}",
            )
            create_task(auto_delete_message(error_msg, time=300))  # noqa: RUF006

    def _extract_meta_data(self):
        # Configure external downloader for specific protocols
        if self._listener.link.startswith(("rtmp", "mms", "rstp", "rtmps")):
            self.opts["external_downloader"] = "xtra"

        # Check for HLS streams and configure appropriately
        if ".m3u8" in self._listener.link or "hls" in self._listener.link.lower():
            LOGGER.info("HLS stream detected, configuring appropriate options")
            # Add HLS-specific options
            self.opts["external_downloader"] = "xtra"
            self.opts["hls_prefer_native"] = False
            self.opts["hls_use_mpegts"] = True

            # Disable YouTube-specific extractor args for HLS streams to prevent conflicts
            if (
                "extractor_args" in self.opts
                and "youtube" in self.opts["extractor_args"]
            ):
                # Only use YouTube extractor args for actual YouTube links
                if not (
                    "youtube.com" in self._listener.link
                    or "youtu.be" in self._listener.link
                ):
                    LOGGER.info(
                        "Non-YouTube HLS stream detected, removing YouTube extractor args"
                    )
                    del self.opts["extractor_args"]["youtube"]
                    if not self.opts["extractor_args"]:
                        del self.opts["extractor_args"]

            # For live streams
            if "live" in self._listener.link.lower():
                LOGGER.info("Live HLS stream detected, adding live stream options")
                self.opts["live_from_start"] = True
                self.opts["wait_for_video"] = (
                    5,
                    60,
                )  # Wait between 5-60 seconds for video

        # YouTube-specific optimizations
        if "youtube.com" in self._listener.link or "youtu.be" in self._listener.link:
            LOGGER.info("YouTube link detected, applying optimizations")
            # Initialize client list - we'll try these in sequence if needed
            self.youtube_clients = ["tv", "android", "web", "ios"]
            self.current_client_index = 0

            # Use TV client first to avoid SSAP experiment issues
            self.opts["extractor_args"]["youtube"]["player_client"] = [
                self.youtube_clients[self.current_client_index]
            ]
            # Skip comments to reduce memory usage
            self.opts["extractor_args"]["youtube"]["max_comments"] = [0]

            LOGGER.info(
                f"Using YouTube client: {self.youtube_clients[self.current_client_index]}"
            )

            # Check for YouTube Shorts
            if "/shorts/" in self._listener.link:
                LOGGER.info("YouTube Shorts detected, optimizing format selection")
                # Shorts often have specific format requirements
                if "format" not in self.opts or not self.opts["format"]:
                    self.opts["format"] = "bv*+ba/b"

            # Extract video ID for fallback title
            video_id = None
            if "youtu.be/" in self._listener.link:
                video_id = (
                    self._listener.link.split("youtu.be/")[1]
                    .split("?")[0]
                    .split("&")[0]
                )
            elif "watch?v=" in self._listener.link:
                video_id = self._listener.link.split("watch?v=")[1].split("&")[0]
            elif "/shorts/" in self._listener.link:
                video_id = (
                    self._listener.link.split("/shorts/")[1]
                    .split("?")[0]
                    .split("&")[0]
                )

            # Set fallback title if video ID was extracted
            if video_id and not self._listener.name:
                self._listener.name = f"youtube_video_{video_id}"

        with YoutubeDL(self.opts) as ydl:
            try:
                result = ydl.extract_info(self._listener.link, download=False)
                if result is None:
                    raise ValueError("Info result is None")

                # Check if it's a live stream and configure accordingly
                if result.get("is_live"):
                    LOGGER.info(
                        "Live stream detected from metadata, configuring appropriate options",
                    )
                    self.opts["external_downloader"] = "xtra"
                    self.opts["hls_prefer_native"] = False
                    self.opts["hls_use_mpegts"] = True
                    self.opts["live_from_start"] = True

                # Check if title extraction warning was triggered
                if MyLogger.title_extraction_warning or not result.get("title"):
                    LOGGER.warning(
                        "Title extraction failed or warning detected, attempting to use fallback methods"
                    )

                    # Reset the warning flag for future downloads
                    MyLogger.title_extraction_warning = False

                    # Try multiple approaches to extract title

                    # 1. Try direct extraction with format template first
                    try:
                        with YoutubeDL(
                            {**self.opts, "quiet": True, "skip_download": True}
                        ) as temp_ydl:
                            # Try to get title using format template
                            temp_name = temp_ydl.prepare_filename(
                                result, outtmpl="%(title)s"
                            )
                            if temp_name and temp_name != "NA":
                                result["title"] = temp_name
                                LOGGER.info(
                                    f"Successfully extracted title using format template: {temp_name}"
                                )
                    except Exception:
                        pass

                    # 2. Try alternative extraction methods
                    if not result.get("title"):
                        try:
                            # Try using different output templates
                            alternative_templates = [
                                "%(fulltitle)s",
                                "%(alt_title)s",
                                "%(display_id)s",
                                "%(uploader)s - %(id)s",
                            ]

                            for template in alternative_templates:
                                try:
                                    with YoutubeDL(
                                        {
                                            **self.opts,
                                            "quiet": True,
                                            "skip_download": True,
                                        }
                                    ) as temp_ydl:
                                        temp_name = temp_ydl.prepare_filename(
                                            result, outtmpl=template
                                        )
                                        if (
                                            temp_name
                                            and temp_name != "NA"
                                            and temp_name.strip()
                                        ):
                                            result["title"] = temp_name.strip()
                                            LOGGER.info(
                                                f"Successfully extracted title using template {template}: {temp_name}"
                                            )
                                            break
                                except Exception:
                                    continue
                        except Exception:
                            pass

                    # 3. Try to extract title from webpage_url
                    if not result.get("title") and result.get("webpage_url"):
                        try:
                            # Extract video ID from URL
                            video_id = None
                            url = result.get("webpage_url")

                            if "youtu.be/" in url:
                                video_id = (
                                    url.split("youtu.be/")[1]
                                    .split("?")[0]
                                    .split("&")[0]
                                )
                            elif "watch?v=" in url:
                                video_id = url.split("watch?v=")[1].split("&")[0]
                            elif "/shorts/" in url:
                                video_id = (
                                    url.split("/shorts/")[1]
                                    .split("?")[0]
                                    .split("&")[0]
                                )

                            if video_id:
                                # Try to get title from YouTube API (simulated)
                                result["title"] = f"youtube_video_{video_id}"
                                LOGGER.info(
                                    f"Using video ID as title: {result['title']}"
                                )
                        except Exception:
                            pass

                # 4. Try to extract from other metadata if title is still missing
                if not result.get("title"):
                    # Try to get title from various metadata fields
                    title_fields = ["fulltitle", "alt_title", "display_id"]
                    for field in title_fields:
                        if result.get(field) and result[field] != "NA":
                            result["title"] = result[field]
                            LOGGER.info(f"Using {field} as title: {result['title']}")
                            break

                # If title is still missing and no name is set, try fallbacks
                if (
                    not result.get("title") or result.get("title") == "NA"
                ) and not self._listener.name:
                    # Try to get a title from various metadata fields in priority order
                    for field in [
                        "alt_title",
                        "fulltitle",
                        "webpage_url_basename",
                        "description",
                        "id",
                        "extractor_key",
                        "uploader",
                        "channel",
                        "_filename",  # Some extractors provide this
                    ]:
                        if result.get(field):
                            # For description, use only first 50 chars
                            if field == "description" and len(result[field]) > 50:
                                field_value = result[field][:50].strip()
                            else:
                                field_value = result[field]

                            self._listener.name = (
                                f"{result.get('extractor', 'video')}_{field_value}"
                            )
                            # Title found from fallback field
                            break
                    else:
                        # If no title found, use video ID if available, otherwise timestamp
                        import time

                        if result.get("id"):
                            self._listener.name = (
                                f"{result.get('extractor', 'video')}_{result['id']}"
                            )
                            # Using ID as fallback title
                        else:
                            self._listener.name = (
                                f"untitled_video_{int(time.time())}"
                            )
                            # Using timestamp as fallback title

                # If we have a title but no listener name, use the title
                if result.get("title") and not self._listener.name:
                    self._listener.name = result.get("title")
                    # Using extracted title

                # Handle YouTube SSAP experiment issues
                if result.get("extractor") == "youtube" and not result.get(
                    "formats"
                ):
                    LOGGER.warning(
                        f"No formats found with {self.youtube_clients[self.current_client_index]} client, trying other clients"
                    )

                    # Try all available clients in sequence
                    for i in range(1, len(self.youtube_clients)):
                        next_client_index = (self.current_client_index + i) % len(
                            self.youtube_clients
                        )
                        next_client = self.youtube_clients[next_client_index]

                        LOGGER.info(f"Trying YouTube client: {next_client}")
                        self.opts["extractor_args"]["youtube"]["player_client"] = [
                            next_client
                        ]

                        # Retry extraction
                        try:
                            result = ydl.extract_info(
                                self._listener.link, download=False
                            )
                            if result and result.get("formats"):
                                LOGGER.info(
                                    f"Successfully found formats with {next_client} client"
                                )
                                self.current_client_index = next_client_index
                                break
                        except Exception as e:
                            LOGGER.warning(f"Error with {next_client} client: {e!s}")
                            continue

                    # If we still don't have formats, log a detailed error
                    if not result or not result.get("formats"):
                        LOGGER.error(
                            "All YouTube clients failed to find formats. This might be due to YouTube's SSAP experiment or region restrictions."
                        )

            except Exception as e:
                error_str = str(e)
                # Check if this is a cookie/authentication related error
                if self._should_try_next_cookie(error_str):
                    if self._try_next_cookie():
                        LOGGER.info("Retrying with next cookie...")
                        # Retry the extraction with the new cookie
                        try:
                            with YoutubeDL(self.opts) as ydl:
                                result = ydl.extract_info(
                                    self._listener.link, download=False
                                )
                                if result is None:
                                    raise ValueError("Info result is None")
                                # Continue with the rest of the extraction logic...
                                # (The rest of the code will handle the result)
                        except Exception as retry_e:
                            # If retry also fails, check if we can try another cookie
                            if (
                                self._should_try_next_cookie(str(retry_e))
                                and self._try_next_cookie()
                            ):
                                LOGGER.info("Retrying with another cookie...")
                                # One more retry attempt
                                try:
                                    with YoutubeDL(self.opts) as ydl:
                                        result = ydl.extract_info(
                                            self._listener.link, download=False
                                        )
                                        if result is None:
                                            raise ValueError("Info result is None")
                                except Exception:
                                    return self._on_download_error(
                                        f"All cookies failed. Last error: {retry_e!s}"
                                    )
                            else:
                                return self._on_download_error(
                                    f"Cookie retry failed: {retry_e!s}"
                                )
                    else:
                        return self._on_download_error(
                            f"No more cookies to try. Error: {error_str}"
                        )
                else:
                    return self._on_download_error(error_str)
            if "entries" in result:
                for entry in result["entries"]:
                    if not entry:
                        continue
                    if "filesize_approx" in entry:
                        self._listener.size += entry.get("filesize_approx", 0) or 0
                    elif "filesize" in entry:
                        self._listener.size += entry.get("filesize", 0) or 0
                    if not self._listener.name:
                        # Try multiple templates for better title extraction
                        templates = [
                            "%(series,playlist_title,channel)s%(season_number& |)s%(season_number&S|)s%(season_number|)02d.%(ext)s",
                            "%(title,fulltitle,alt_title)s.%(ext)s",
                            "%(id)s_%(uploader,channel)s.%(ext)s",
                        ]

                        for outtmpl_ in templates:
                            try:
                                name, ext = ospath.splitext(
                                    ydl.prepare_filename(entry, outtmpl=outtmpl_)
                                )
                                if name and name != "NA":
                                    self._listener.name = name
                                    if not self._ext:
                                        self._ext = ext
                                    break
                            except Exception:
                                continue

                        # If all templates failed, use entry ID
                        if not self._listener.name or self._listener.name == "NA":
                            entry_id = entry.get("id", "unknown")
                            uploader = entry.get(
                                "uploader", entry.get("channel", "unknown")
                            )
                            self._listener.name = f"{entry_id}_{uploader}"
                            # Using fallback playlist entry name
                return None

            # Try multiple templates for better title extraction
            templates = [
                # Primary template with comprehensive fallbacks
                "%(title,fulltitle,alt_title,description,webpage_url_basename)s%(season_number& |)s%(season_number&S|)s%(season_number|)02d%(episode_number&E|)s%(episode_number|)02d%(height& |)s%(height|)s%(height&p|)s%(fps|)s%(fps&fps|)s%(tbr& |)s%(tbr|)d.%(ext)s",
                # Simpler templates with fewer fields
                "%(title,fulltitle,alt_title)s.%(ext)s",
                # Metadata-based templates
                "%(id)s_%(uploader,channel)s.%(ext)s",
                # Format-based templates that include quality info
                "%(id)s_%(height)sp%(fps)s.%(ext)s",
                # Last resort templates that should always work
                "youtube_video_%(id)s.%(ext)s",
                "%(id)s.%(ext)s",
            ]

            realName = None
            for outtmpl_ in templates:
                try:
                    name = ydl.prepare_filename(result, outtmpl=outtmpl_)
                    if name and not name.startswith("NA.") and "NA" not in name:
                        realName = name
                        # Successfully extracted filename using template
                        break
                except Exception:
                    continue

            # If all templates failed, use video ID and timestamp with more info
            if not realName:
                import time

                video_id = result.get("id", "unknown")
                uploader = result.get("uploader", result.get("channel", "unknown"))
                ext = result.get("ext", "mp4")

                # Try to include quality information if available
                height = result.get("height", "")
                fps = result.get("fps", "")
                quality_info = ""

                if height:
                    quality_info += f"{height}p"
                if fps:
                    quality_info += f"{fps}fps"

                if quality_info:
                    realName = f"youtube_video_{video_id}_{quality_info}.{ext}"
                else:
                    realName = f"youtube_video_{video_id}_{int(time.time())}.{ext}"

                # Using fallback video name

            # Final filename processed

            ext = ospath.splitext(realName)[-1]
            self._listener.name = (
                f"{self._listener.name}{ext}" if self._listener.name else realName
            )
            if not self._ext:
                self._ext = ext
                return None
            return None

    def _download(self, path):
        try:
            # Track which clients we've tried
            tried_clients = []
            max_retries = 3
            retry_count = 0

            while retry_count < max_retries:
                try:
                    with YoutubeDL(self.opts) as ydl:
                        try:
                            # Log the final options being used
                            LOGGER.info(
                                f"Starting download with format: {self.opts.get('format', 'default')}"
                            )
                            if "youtube" in self._listener.link:
                                current_client = self.opts["extractor_args"][
                                    "youtube"
                                ]["player_client"][0]
                                tried_clients.append(current_client)
                                LOGGER.info(f"YouTube client: {current_client}")

                            # Attempt download
                            ydl.download([self._listener.link])
                            # If we get here, download was successful
                            break

                        except DownloadError as e:
                            error_msg = str(e)
                            if not self._listener.is_cancelled:
                                # Check for common YouTube errors and provide more helpful messages
                                if (
                                    "This video is only available to subscribers"
                                    in error_msg
                                ):
                                    error_msg += "\nTry uploading your own cookies file with YouTube Premium subscription."
                                    self._on_download_error(error_msg)
                                    return
                                if "Sign in to confirm your age" in error_msg:
                                    error_msg += "\nTry uploading your own cookies file with age verification."
                                    self._on_download_error(error_msg)
                                    return
                                if (
                                    "Unable to extract video data" in error_msg
                                    or "No video formats found" in error_msg
                                    or "YouTube is forcing SABR streaming"
                                    in error_msg
                                ) and "youtube" in self._listener.link.lower():
                                    error_msg += "\nThis might be due to YouTube's SSAP experiment or region restrictions. The bot tried multiple YouTube clients (TV, Android, Web, iOS) but all failed. You can try:\n"
                                    error_msg += "1. Try again later\n"
                                    error_msg += "2. Try with a different video\n"
                                    error_msg += "3. Try extracting just the audio with the 'ytdlpa' command\n"
                                    error_msg += "4. Upload your own cookies file with a YouTube Premium subscription"
                                    self._on_download_error(error_msg)
                                    return
                                if (
                                    "ffmpeg not found" in error_msg.lower()
                                    or "xtra not found" in error_msg.lower()
                                ):
                                    # Ignore xtra/ffmpeg path error as requested
                                    # Try to continue without xtra/ffmpeg
                                    break
                                if (
                                    "template variables not replaced"
                                    in error_msg.lower()
                                ):
                                    # Ignore name sub error as requested
                                    break
                                # For other errors, try different client if it's a YouTube link
                                if (
                                    "youtube" in self._listener.link.lower()
                                    and retry_count < max_retries - 1
                                ):
                                    retry_count += 1

                                    # Use our predefined client list and tracking
                                    if hasattr(self, "youtube_clients"):
                                        # Move to the next client in the rotation
                                        self.current_client_index = (
                                            self.current_client_index + 1
                                        ) % len(self.youtube_clients)
                                        next_client = self.youtube_clients[
                                            self.current_client_index
                                        ]

                                        # Check if we've already tried this client
                                        if next_client in tried_clients:
                                            # Find the first client we haven't tried yet
                                            untried_clients = [
                                                c
                                                for c in self.youtube_clients
                                                if c not in tried_clients
                                            ]
                                            if untried_clients:
                                                next_client = untried_clients[0]
                                                self.current_client_index = (
                                                    self.youtube_clients.index(
                                                        next_client
                                                    )
                                                )
                                            else:
                                                # We've tried all clients, just use the next one in sequence
                                                pass

                                        LOGGER.info(
                                            f"Retrying with YouTube client: {next_client}"
                                        )
                                        self.opts["extractor_args"]["youtube"][
                                            "player_client"
                                        ] = [next_client]
                                    else:
                                        # Fallback to the old method if youtube_clients isn't defined
                                        available_clients = [
                                            "tv",
                                            "android",
                                            "web",
                                            "ios",
                                        ]
                                        # Filter out clients we've already tried
                                        next_clients = [
                                            c
                                            for c in available_clients
                                            if c not in tried_clients
                                        ]

                                    if next_clients:
                                        next_client = next_clients[0]
                                        LOGGER.info(
                                            f"Retrying with different YouTube client: {next_client}"
                                        )
                                        self.opts["extractor_args"]["youtube"][
                                            "player_client"
                                        ] = [next_client]
                                        continue

                                # If we've tried all clients or it's not a YouTube link, report the error
                                self._on_download_error(error_msg)
                                return
                            return
                        finally:
                            # Force garbage collection after download attempt
                            # YT-DLP can create large objects in memory
                            if smart_garbage_collection:
                                smart_garbage_collection(aggressive=True)
                            else:
                                # Multiple collection passes to ensure memory is freed
                                gc.collect()
                                gc.collect()

                            # Try to free more memory by clearing large variables
                            try:
                                import sys

                                # Find large objects in memory and clear them
                                for name, obj in list(locals().items()):
                                    if (
                                        sys.getsizeof(obj) > 1024 * 1024
                                    ):  # Objects larger than 1MB
                                        locals()[name] = None
                            except Exception:
                                pass
                    # Break out of retry loop if we got here
                    break

                except Exception as inner_e:
                    error_str = str(inner_e)
                    # Handle specific 'can_download' error
                    if (
                        "'NoneType' object has no attribute 'can_download'"
                        in error_str
                    ):
                        LOGGER.error(f"Extractor error: {inner_e}")

                        # Check if this is an HLS stream
                        is_hls = (
                            ".m3u8" in self._listener.link
                            or "hls" in self._listener.link.lower()
                        )
                        is_youtube = (
                            "youtube" in self._listener.link.lower()
                            or "youtu.be" in self._listener.link.lower()
                        )

                        # For HLS streams that aren't YouTube, try with different options
                        if is_hls and not is_youtube:
                            LOGGER.info(
                                "HLS stream detected with extractor error, trying with modified options"
                            )
                            retry_count += 1

                            # Remove any YouTube-specific settings that might be causing conflicts
                            if "extractor_args" in self.opts:
                                if "youtube" in self.opts["extractor_args"]:
                                    del self.opts["extractor_args"]["youtube"]
                                if not self.opts["extractor_args"]:
                                    del self.opts["extractor_args"]

                            # Use more generic options for HLS streams
                            self.opts["external_downloader"] = "xtra"
                            self.opts["hls_prefer_native"] = False

                            # Try with different format specification
                            if retry_count == 1:
                                self.opts["format"] = "best"
                                LOGGER.info("Retrying HLS stream with format=best")
                            elif retry_count == 2:
                                self.opts["format"] = "bestvideo+bestaudio/best"
                                LOGGER.info(
                                    "Retrying HLS stream with format=bestvideo+bestaudio/best"
                                )

                            if retry_count < max_retries:
                                continue

                        # Only retry for YouTube links with different clients
                        elif is_youtube and retry_count < max_retries - 1:
                            retry_count += 1
                            # Try different client types in sequence
                            available_clients = ["tv", "android", "web", "ios"]
                            # Filter out clients we've already tried
                            next_clients = [
                                c
                                for c in available_clients
                                if c not in tried_clients
                            ]

                            if next_clients:
                                next_client = next_clients[0]
                                LOGGER.info(
                                    f"Retrying with different YouTube client: {next_client}"
                                )
                                if "extractor_args" not in self.opts:
                                    self.opts["extractor_args"] = {
                                        "youtube": {"player_client": [next_client]}
                                    }
                                elif "youtube" not in self.opts["extractor_args"]:
                                    self.opts["extractor_args"]["youtube"] = {
                                        "player_client": [next_client]
                                    }
                                else:
                                    self.opts["extractor_args"]["youtube"][
                                        "player_client"
                                    ] = [next_client]
                                continue

                        # If we've tried all options or max retries, provide a more helpful error message
                        if is_hls:
                            self._on_download_error(
                                "Error: Failed to download HLS stream. The stream might be protected or requires authentication. "
                                "Try downloading with a different method or check if the stream is accessible."
                            )
                            return
                        if is_youtube:
                            self._on_download_error(
                                f"Error: YouTube extractor failed to initialize properly. This is likely due to YouTube's SSAP experiment. "
                                f"We tried the following clients: {', '.join(tried_clients)}. "
                                f"Try again later or try a different format/quality."
                            )
                            return
                        # Generic error for other URLs
                        self._on_download_error(
                            "Error: The extractor failed to initialize properly. The URL might be invalid or unsupported."
                        )
                        return

                    # For other exceptions, just raise
                    raise

            # Check if download was successful
            if self.is_playlist and (
                not ospath.exists(path) or len(listdir(path)) == 0
            ):
                self._on_download_error(
                    "No video available to download from this playlist. Check logs for more details",
                )
                return
            if self._listener.is_cancelled:
                return
            async_to_sync(self._listener.on_download_complete)
        except Exception as e:
            LOGGER.error(f"Error in YT-DLP download: {e}")
            # Force garbage collection after error
            if smart_garbage_collection:
                smart_garbage_collection(aggressive=True)
            else:
                # Multiple collection passes to ensure memory is freed
                gc.collect()
                gc.collect()

            # Try to free more memory by clearing large variables
            try:
                import sys

                # Find large objects in memory and clear them
                for name, obj in list(locals().items()):
                    if sys.getsizeof(obj) > 1024 * 1024:  # Objects larger than 1MB
                        locals()[name] = None
            except Exception:
                pass
            # Try to provide more helpful error messages
            error_str = str(e)
            if "Memory" in error_str or "memory" in error_str:
                self._on_download_error(
                    "Error: Memory allocation failed. The video might be too large or in a format that requires too much memory to process. Try a lower quality format."
                )
            elif "ffmpeg" in error_str.lower() or "xtra" in error_str.lower():
                # Ignore ffmpeg errors as requested
                # Try to continue without error
                async_to_sync(self._listener.on_download_complete)
            elif "'NoneType' object has no attribute 'can_download'" in error_str:
                # Handle the specific can_download error
                is_hls = (
                    ".m3u8" in self._listener.link
                    or "hls" in self._listener.link.lower()
                )
                is_youtube = (
                    "youtube" in self._listener.link.lower()
                    or "youtu.be" in self._listener.link.lower()
                )

                if is_hls and not is_youtube:
                    self._on_download_error(
                        "Error: Failed to download HLS stream. The stream might be protected or requires authentication. "
                        "Try downloading with a different method or check if the stream is accessible."
                    )
                elif is_youtube:
                    self._on_download_error(
                        f"Error: YouTube extractor failed to initialize properly. This is likely due to YouTube's SSAP experiment. "
                        f"We tried the following clients: {', '.join(tried_clients)}. "
                        f"Try again later or try a different format/quality."
                    )
                else:
                    self._on_download_error(
                        "Error: The extractor failed to initialize properly. The URL might be invalid or unsupported."
                    )
            # Check if this is a cookie-related error and we have more cookies to try
            elif self._should_try_next_cookie(error_str) and self._try_next_cookie():
                LOGGER.info(
                    "Download failed with current cookie, retrying with next cookie..."
                )
                # Retry the entire download with the new cookie
                try:
                    self._download(path)
                    return  # If successful, exit here
                except Exception as retry_e:
                    retry_error_str = str(retry_e)
                    # If retry also fails, check if we can try another cookie
                    if (
                        self._should_try_next_cookie(retry_error_str)
                        and self._try_next_cookie()
                    ):
                        LOGGER.info("Retrying with another cookie...")
                        try:
                            self._download(path)
                            return  # If successful, exit here
                        except Exception:
                            self._on_download_error(
                                f"All cookies failed. Last error: {retry_error_str}"
                            )
                    else:
                        self._on_download_error(
                            f"Cookie retry failed: {retry_error_str}"
                        )
            else:
                self._on_download_error(f"Download error: {error_str}")
        return

    async def add_download(self, path, qual, playlist, options):
        if playlist:
            self.opts["ignoreerrors"] = True
            self.is_playlist = True

        self._gid = token_hex(4)

        await self._on_download_start()

        self.opts["postprocessors"] = [
            {
                "add_chapters": True,
                "add_infojson": "if_exists",
                "add_metadata": True,
                "key": "FFmpegMetadata",
            },
        ]

        # Handle specific audio format with quality
        if qual.startswith("ba/b-"):
            audio_info = qual.split("-")
            qual = audio_info[0]
            audio_format = audio_info[1]
            rate = audio_info[2]
            self.opts["postprocessors"].append(
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": audio_format,
                    "preferredquality": rate,
                },
            )
            if audio_format == "vorbis":
                self._ext = ".ogg"
            elif audio_format == "alac":
                self._ext = ".m4a"
            else:
                self._ext = f".{audio_format}"
        # Handle bestaudio format - ensure it's audio only
        elif qual == "bestaudio":
            # Modify format to ensure audio-only download
            qual = "bestaudio[vcodec=none]"
            # Default to mp3 format for consistency
            self.opts["postprocessors"].append(
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                },
            )
            self._ext = ".mp3"

            # Downloading audio-only format (MP3)

            # Add audio format to the filename for clarity
            if self._listener.name and not self._listener.name.endswith(self._ext):
                if "." in self._listener.name:
                    base_name = self._listener.name.rsplit(".", 1)[0]
                    self._listener.name = f"{base_name} (Audio){self._ext}"
                else:
                    self._listener.name = f"{self._listener.name} (Audio){self._ext}"

        if options:
            self._set_options(options)

        self.opts["format"] = qual

        await sync_to_async(self._extract_meta_data)
        if self._listener.is_cancelled:
            return

        base_name, ext = ospath.splitext(self._listener.name)
        trim_name = self._listener.name if self.is_playlist else base_name
        if len(trim_name.encode()) > 200:
            self._listener.name = (
                self._listener.name[:200]
                if self.is_playlist
                else f"{base_name[:200]}{ext}"
            )
            base_name = ospath.splitext(self._listener.name)[0]

        if self.is_playlist:
            self.opts["outtmpl"] = {
                "default": f"{path}/{self._listener.name}/%(title,fulltitle,alt_title)s%(season_number& |)s%(season_number&S|)s%(season_number|)02d%(episode_number&E|)s%(episode_number|)02d%(height& |)s%(height|)s%(height&p|)s%(fps|)s%(fps&fps|)s%(tbr& |)s%(tbr|)d.%(ext)s",
                "thumbnail": f"{path}/yt-dlp-thumb/%(title,fulltitle,alt_title)s%(season_number& |)s%(season_number&S|)s%(season_number|)02d%(episode_number&E|)s%(episode_number|)02d%(height& |)s%(height|)s%(height&p|)s%(fps|)s%(fps&fps|)s%(tbr& |)s%(tbr|)d.%(ext)s",
            }
        elif "download_ranges" in options:
            self.opts["outtmpl"] = {
                "default": f"{path}/{base_name}/%(section_number|)s%(section_number&.|)s%(section_title|)s%(section_title&-|)s%(title,fulltitle,alt_title)s %(section_start)s to %(section_end)s.%(ext)s",
                "thumbnail": f"{path}/yt-dlp-thumb/%(section_number|)s%(section_number&.|)s%(section_title|)s%(section_title&-|)s%(title,fulltitle,alt_title)s %(section_start)s to %(section_end)s.%(ext)s",
            }
        elif any(
            key in options
            for key in [
                "writedescription",
                "writeinfojson",
                "writeannotations",
                "writedesktoplink",
                "writewebloclink",
                "writeurllink",
                "writesubtitles",
                "writeautomaticsub",
            ]
        ):
            self.opts["outtmpl"] = {
                "default": f"{path}/{base_name}/{self._listener.name}",
                "thumbnail": f"{path}/yt-dlp-thumb/{base_name}.%(ext)s",
            }
        else:
            self.opts["outtmpl"] = {
                "default": f"{path}/{self._listener.name}",
                "thumbnail": f"{path}/yt-dlp-thumb/{base_name}.%(ext)s",
            }

        # Set proper filename for audio formats
        if qual.startswith("ba/b") or qual in {
            "bestaudio",
            "bestaudio[vcodec=none]",
        }:
            self._listener.name = f"{base_name}{self._ext}"

        # Enhanced format selection for YouTube
        if "youtube.com" in self._listener.link or "youtu.be" in self._listener.link:
            # If the user requested a specific quality but we're having issues
            if qual not in ["best", "bestaudio"]:
                # Add fallback format string that will work even with SSAP restrictions
                if "format" in self.opts:
                    original_format = self.opts["format"]
                    # Add fallback format string
                    self.opts["format"] = (
                        f"{original_format}/bestvideo+bestaudio/best"
                    )
                    LOGGER.info(
                        f"Enhanced format selection for YouTube: {self.opts['format']}"
                    )

        if self._listener.is_leech and not self._listener.thumbnail_layout:
            self.opts["postprocessors"].append(
                {
                    "format": "jpg",
                    "key": "FFmpegThumbnailsConvertor",
                    "when": "before_dl",
                },
            )
        if self._ext in [
            ".mp3",
            ".mkv",
            ".mka",
            ".ogg",
            ".opus",
            ".flac",
            ".m4a",
            ".mp4",
            ".mov",
            ".m4v",
        ]:
            self.opts["postprocessors"].append(
                {
                    "already_have_thumbnail": bool(
                        self._listener.is_leech
                        and not self._listener.thumbnail_layout,
                    ),
                    "key": "EmbedThumbnail",
                },
            )
        elif not self._listener.is_leech:
            self.opts["writethumbnail"] = False

        # Check size limits if size is available
        if self._listener.size > 0:
            limit_msg = await limit_checker(
                self._listener.size,
                self._listener,
                isYtdlp=True,
                isPlayList=self.is_playlist,
            )
            if limit_msg:
                await self._listener.on_download_error(limit_msg)
                return

        msg, button = await stop_duplicate_check(self._listener)
        if msg:
            await self._listener.on_download_error(msg, button)
            return

        add_to_queue, event = await check_running_tasks(self._listener)
        if add_to_queue:
            LOGGER.info(f"Added to Queue/Download: {self._listener.name}")
            async with task_dict_lock:
                task_dict[self._listener.mid] = QueueStatus(
                    self._listener,
                    self._gid,
                    "dl",
                )
            await event.wait()
            if self._listener.is_cancelled:
                return
            LOGGER.info(f"Start Queued Download from YT_DLP: {self._listener.name}")
            await self._on_download_start(True)

        if not add_to_queue:
            LOGGER.info(f"Download with YT_DLP: {self._listener.name}")

        await sync_to_async(self._download, path)

    async def cancel_task(self):
        self._listener.is_cancelled = True
        LOGGER.info(f"Cancelling Download: {self._listener.name}")

        # Force garbage collection after cancellation
        if smart_garbage_collection:
            smart_garbage_collection(aggressive=True)
        else:
            gc.collect()

        # Log memory usage after garbage collection if available
        try:
            import psutil

            process = psutil.Process()
            memory_info = process.memory_info()
            LOGGER.info(
                f"Memory usage after cancellation: {memory_info.rss / 1024 / 1024:.2f} MB"
            )
        except ImportError:
            pass

        await self._listener.on_download_error("Stopped by User!")

    def _set_options(self, options):
        for key, value in options.items():
            if key == "postprocessors":
                if isinstance(value, list):
                    self.opts[key].extend(tuple(value))
                elif isinstance(value, dict):
                    self.opts[key].append(value)
            elif key == "download_ranges":
                if isinstance(value, list):
                    self.opts[key] = lambda info, ytdl: value
            else:
                self.opts[key] = value
