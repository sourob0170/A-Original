import os
from logging import getLogger

from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from bot.helper.ext_utils.bot_utils import SetInterval, async_to_sync
from bot.helper.ext_utils.files_utils import get_mime_type
from bot.helper.mirror_leech_utils.youtube_utils.youtube_helper import YouTubeHelper

LOGGER = getLogger(__name__)


class YouTubeUpload(YouTubeHelper):
    def __init__(
        self,
        listener,
        path,
        privacy="unlisted",
        tags=None,
        category="22",
        description=None,
        playlist_id=None,
        upload_mode="playlist",
    ):
        self.listener = listener
        self._updater = None
        self._path = path
        self._is_errored = False
        self.privacy = privacy
        self.tags = tags
        self.category = category
        self.description = description
        self.playlist_id = playlist_id
        self.upload_mode = upload_mode
        super().__init__()
        self.is_uploading = True

    def _upload_playlist(self, folder_path, playlist_name):
        """Uploads all videos in a folder and adds them to a new playlist."""
        video_ids = []
        video_files_count = 0
        LOGGER.info(f"Starting playlist upload for folder: {folder_path}")

        try:
            for item_name in os.listdir(folder_path):
                item_path = os.path.join(folder_path, item_name)
                if os.path.isfile(item_path):
                    mime_type = get_mime_type(item_path)
                    if mime_type and mime_type.startswith("video/"):
                        video_files_count += 1
                        LOGGER.info(f"Uploading video file: {item_path}")
                        try:
                            video_id_or_url = self._upload_video(
                                item_path, item_name, mime_type
                            )
                            if (
                                video_id_or_url
                                and "youtube.com/watch?v=" in video_id_or_url
                            ):
                                video_id = video_id_or_url.split("=")[-1]
                                video_ids.append(video_id)
                                LOGGER.info(
                                    f"Successfully uploaded video: {item_name}, ID: {video_id}"
                                )
                            elif self.listener.is_cancelled:
                                LOGGER.info(
                                    "Playlist upload cancelled during video upload."
                                )
                                return None  # Or handle as partial success
                            else:
                                LOGGER.warning(
                                    f"Failed to upload video or extract ID: {item_name}"
                                )
                        except Exception as e:
                            LOGGER.error(f"Error uploading video {item_name}: {e}")
                            # Optionally, decide if one video failure should stop the whole playlist
                            # For now, we continue and try to upload other videos
                    else:
                        LOGGER.debug(
                            f"Skipping non-video file: {item_path} (MIME: {mime_type})"
                        )
                if self.listener.is_cancelled:
                    LOGGER.info("Playlist upload process cancelled.")
                    return None  # Or handle cleanup for partially uploaded videos

            if not video_ids:
                LOGGER.info("No videos found or uploaded in the folder.")
                if video_files_count > 0:  # Videos were found but failed to upload
                    raise ValueError(
                        "No videos were successfully uploaded from the folder."
                    )
                return "No videos to upload in playlist."  # Or specific message

            LOGGER.info(f"Creating playlist: {playlist_name}")
            playlist_request_body = {
                "snippet": {
                    "title": playlist_name,
                    "description": f"Playlist created from folder: {playlist_name}",
                    "tags": ["mirror-leech-bot", "playlist-upload"],
                },
                "status": {"privacyStatus": "private"},  # Or user-defined
            }
            playlist_insert_request = self.service.playlists().insert(
                part="snippet,status", body=playlist_request_body
            )
            playlist_response = playlist_insert_request.execute()
            playlist_id = playlist_response["id"]
            playlist_url = f"https://www.youtube.com/playlist?list={playlist_id}"
            LOGGER.info(
                f"Playlist created: {playlist_name}, ID: {playlist_id}, URL: {playlist_url}"
            )

            for video_id in video_ids:
                if self.listener.is_cancelled:
                    LOGGER.info(
                        "Playlist upload cancelled before adding all videos to playlist."
                    )
                    break  # Stop adding more videos
                LOGGER.info(f"Adding video ID {video_id} to playlist {playlist_id}")
                playlist_item_request_body = {
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {"kind": "youtube#video", "videoId": video_id},
                    }
                }
                playlist_item_insert_request = self.service.playlistItems().insert(
                    part="snippet", body=playlist_item_request_body
                )
                playlist_item_insert_request.execute()
                LOGGER.info(
                    f"Successfully added video ID {video_id} to playlist {playlist_id}"
                )

            # Update total_files for the listener, this might need adjustment based on how listener expects it
            self.total_files = len(
                video_ids
            )  # Count of successfully uploaded and added videos
            individual_video_urls = [
                f"https://www.youtube.com/watch?v={vid}" for vid in video_ids
            ]
            return {
                "playlist_url": playlist_url,
                "individual_video_urls": individual_video_urls,
            }

        except HttpError as e:
            LOGGER.error(f"YouTube API error during playlist operation: {e}")
            raise e  # Re-raise to be caught by the main upload method's error handler
        except Exception as e:
            LOGGER.error(f"Error during playlist creation or video addition: {e}")
            raise e  # Re-raise

    def user_setting(self):
        """Handle user-specific YouTube token settings"""
        if self.listener.up_dest.startswith("yt:"):
            self.token_path = f"tokens/{self.listener.user_id}.pickle"
            self.listener.up_dest = self.listener.up_dest.replace("yt:", "", 1)
        elif hasattr(self.listener, "user_id") and self.listener.user_id:
            self.token_path = f"tokens/{self.listener.user_id}.pickle"

    def upload(self):
        """Main upload function"""
        self.user_setting()
        try:
            self.service = self.authorize(
                self.listener.user_id if hasattr(self.listener, "user_id") else ""
            )
        except Exception as e:
            LOGGER.error(f"YouTube authorization failed: {e}")
            async_to_sync(
                self.listener.on_upload_error, f"YouTube authorization failed: {e!s}"
            )
            return

        LOGGER.info(f"Uploading to YouTube: {self._path}")
        self._updater = SetInterval(self.update_interval, self.progress)
        upload_result_url = None
        upload_type = None
        upload_mode = self.upload_mode
        files_processed = 0

        try:
            if os.path.isfile(self._path):
                mime_type = get_mime_type(self._path)
                if not mime_type or not mime_type.startswith("video/"):
                    raise ValueError(f"File is not a video. MIME type: {mime_type}")

                result_from_upload_video = self._upload_video(
                    self._path, self.listener.name, mime_type
                )
                upload_result_url = {"video_url": result_from_upload_video}
                upload_type = "Video"
                if result_from_upload_video:
                    files_processed = 1
                LOGGER.info(f"Uploaded Single Video To YouTube: {self._path}")

            elif os.path.isdir(self._path):
                playlist_name = os.path.basename(self._path)
                provided_playlist_id = self.playlist_id # Store original playlist_id

                if upload_mode == "playlist":
                    if provided_playlist_id:
                        self.playlist_id = provided_playlist_id # Ensure _upload_video uses it
                        individual_video_urls = []
                        files_processed = 0
                        self.total_files = 0 # Reset for this specific operation
                        for item_name in os.listdir(self._path):
                            item_path = os.path.join(self._path, item_name)
                            if os.path.isfile(item_path):
                                mime_type = get_mime_type(item_path)
                                if mime_type and mime_type.startswith("video/"):
                                    try:
                                        video_url = self._upload_video(item_path, item_name, mime_type)
                                        if video_url:
                                            individual_video_urls.append(video_url)
                                            files_processed += 1
                                    except Exception as e:
                                        LOGGER.error(f"Failed to upload {item_name} to playlist {provided_playlist_id}: {e}")
                                    if self.listener.is_cancelled:
                                        LOGGER.info("Upload process cancelled during playlist video upload.")
                                        break
                        if not self.listener.is_cancelled:
                            upload_result_url = {"playlist_url": f"https://www.youtube.com/playlist?list={provided_playlist_id}",
                                                 "individual_video_urls": individual_video_urls}
                            upload_type = "Playlist"
                            self.total_files = files_processed
                            LOGGER.info(f"Uploaded videos to existing playlist ID: {provided_playlist_id}")
                        else: # Handle cancellation
                            upload_result_url = None
                            files_processed = 0 # Or count partially uploaded if needed
                    else: # No provided_playlist_id, create new playlist
                        upload_result_url = self._upload_playlist(self._path, playlist_name)
                        upload_type = "Playlist"
                        if upload_result_url and upload_result_url.get("playlist_url"):
                            files_processed = self.total_files # self.total_files is updated in _upload_playlist
                        else:
                            files_processed = 0
                        LOGGER.info(f"Uploaded new Playlist To YouTube: {self._path}")
                elif upload_mode == "individual":
                    # This part remains largely the same as it doesn't involve playlists directly
                    self.playlist_id = None # Ensure no playlist is used for individual uploads
                    individual_video_urls = []
                    files_processed = 0
                    self.total_files = 0
                    for item_name in os.listdir(self._path):
                        item_path = os.path.join(self._path, item_name)
                        if os.path.isfile(item_path):
                            mime_type = get_mime_type(item_path)
                            if mime_type and mime_type.startswith("video/"):
                                try:
                                    video_url = self._upload_video(item_path, item_name, mime_type)
                                    if video_url:
                                        individual_video_urls.append(video_url)
                                        files_processed += 1
                                except Exception as e:
                                    LOGGER.error(f"Failed to upload {item_name}: {e}")
                                if self.listener.is_cancelled:
                                    LOGGER.info("Upload process cancelled during individual video upload.")
                                    break
                    if not self.listener.is_cancelled:
                        upload_result_url = {"individual_video_urls": individual_video_urls}
                        upload_type = "Individual Videos"
                        self.total_files = files_processed
                    else:
                        upload_result_url = None
                        files_processed = 0
                    LOGGER.info(f"Uploaded Individual Videos from folder: {self._path}")
                elif upload_mode == "playlist_and_individual":
                    if provided_playlist_id:
                        self.playlist_id = provided_playlist_id # Ensure _upload_video uses it
                        individual_video_urls = []
                        files_processed = 0
                        self.total_files = 0
                        for item_name in os.listdir(self._path):
                            item_path = os.path.join(self._path, item_name)
                            if os.path.isfile(item_path):
                                mime_type = get_mime_type(item_path)
                                if mime_type and mime_type.startswith("video/"):
                                    try:
                                        video_url = self._upload_video(item_path, item_name, mime_type)
                                        if video_url:
                                            individual_video_urls.append(video_url)
                                            files_processed += 1
                                    except Exception as e:
                                        LOGGER.error(f"Failed to upload {item_name} to playlist {provided_playlist_id} (mode: p&i): {e}")
                                    if self.listener.is_cancelled:
                                        LOGGER.info("Upload process cancelled during playlist_and_individual video upload.")
                                        break
                        if not self.listener.is_cancelled:
                            upload_result_url = {"playlist_url": f"https://www.youtube.com/playlist?list={provided_playlist_id}",
                                                 "individual_video_urls": individual_video_urls}
                            upload_type = "Playlist and Individual Videos"
                            self.total_files = files_processed
                            LOGGER.info(f"Uploaded videos to existing playlist ID {provided_playlist_id} (mode: p&i)")
                        else:
                            upload_result_url = None
                            files_processed = 0
                    else: # No provided_playlist_id, create new playlist (original behavior for p&i)
                        upload_result_url = self._upload_playlist(self._path, playlist_name)
                        upload_type = "Playlist and Individual Videos"
                        if upload_result_url and upload_result_url.get("playlist_url"):
                            files_processed = self.total_files # self.total_files is updated in _upload_playlist
                        else:
                            files_processed = 0
                        LOGGER.info(f"Uploaded new Playlist and Individual Videos To YouTube: {self._path}")
                else:
                    raise ValueError(f"Invalid upload_mode: {upload_mode}")
            else:
                raise ValueError(f"Path is not a file or directory: {self._path}")

            if self.listener.is_cancelled:
                LOGGER.info("Upload cancelled by listener.")
                return

            # Standardize check for no videos uploaded in playlist modes
            if (
                isinstance(upload_result_url, dict)
                and upload_result_url.get("playlist_url") is None
                and not upload_result_url.get("individual_video_urls")
                and upload_type in ["Playlist", "Playlist and Individual Videos"]
            ):
                if (
                    self.total_files == 0 and files_processed == 0
                ):  # No videos attempted or processed
                    LOGGER.info(
                        f"{upload_type} upload resulted in no videos uploaded."
                    )
                # If individual_video_urls has items for "playlist_and_individual", it's not a complete failure
                elif (
                    not upload_result_url.get("individual_video_urls")
                    and upload_type == "Playlist and Individual Videos"
                ):
                    LOGGER.info(
                        f"{upload_type} upload resulted in no videos uploaded for playlist part."
                    )
            elif upload_result_url is None and not self.listener.is_cancelled:
                raise ValueError(
                    "Upload result is None but not cancelled by listener and not an empty playlist scenario."
                )

        except Exception as err:
            if isinstance(err, RetryError):
                LOGGER.info(f"Total Attempts: {err.last_attempt.attempt_number}")
                err = err.last_attempt.exception()
            err = str(err).replace(">", "").replace("<", "")
            LOGGER.error(err)
            async_to_sync(self.listener.on_upload_error, err)
            self._is_errored = True
        finally:
            self._updater.cancel()

        if self.listener.is_cancelled and not self._is_errored:
            LOGGER.info("Upload process was cancelled by listener.")
            return

        if self._is_errored:
            LOGGER.error("Upload process failed with an error.")
            return

        if (
            upload_result_url is None
            and upload_type == "Playlist"
            and files_processed == 0
        ):
            # Handle case where playlist was "successful" but no videos were uploaded (e.g. empty folder)
            # The error or specific message should ideally come from _upload_playlist
            async_to_sync(
                self.listener.on_upload_error,
                "No videos found in the folder to upload to playlist.",
            )
            return

        async_to_sync(
            self.listener.on_upload_complete,
            None,
            None,
            files_processed,  # count
            upload_type,
            upload_type=upload_type,  # mime_type ("Playlist" or "Video")
            upload_result=upload_result_url,
        )
        return

    @retry(
        wait=wait_exponential(multiplier=2, min=3, max=6),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(Exception),
    )
    def _upload_video(self, file_path, file_name, mime_type):
        """Upload video to YouTube"""

        # Default video metadata
        title = file_name

        # Use resolved final settings directly
        privacy_status = self.privacy
        category_id = self.category

        # Description: base is description, append original filename
        description_base = self.description
        description = f"{description_base}\n\nOriginal filename: {file_name}"

        # Tags: use tags (already a list or None)
        # If tags is None, use application default tags.
        # If tags is an empty list [], it means user/override explicitly wanted no tags.
        tags_for_body = self.tags
        if (
            tags_for_body is None
        ):  # Neither override nor user setting provided tags (and it wasn't explicitly empty list)
            tags_for_body = ["mirror-leech-bot", "telegram-bot", "upload"]

        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags_for_body,
                "categoryId": str(category_id),
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False,
            },
        }

        # Create media upload object
        media_body = MediaFileUpload(
            file_path,
            mimetype=mime_type,
            resumable=True,
            chunksize=1024 * 1024 * 4,  # 4MB chunks
        )

        # Create the upload request
        insert_request = self.service.videos().insert(
            part=",".join(body.keys()), body=body, media_body=media_body
        )

        response = None
        retries = 0

        while response is None and not self.listener.is_cancelled:
            try:
                self.status, response = insert_request.next_chunk()
                if self.status:
                    self.upload_progress = int(self.status.progress() * 100)
                    LOGGER.info(f"Upload progress: {self.upload_progress}%")

            except HttpError as err:
                if err.resp.status in [500, 502, 503, 504, 429] and retries < 5:
                    retries += 1
                    LOGGER.warning(
                        f"HTTP error {err.resp.status}, retrying... ({retries}/5)"
                    )
                    continue
                error_content = (
                    err.content.decode("utf-8") if err.content else "Unknown error"
                )
                LOGGER.error(f"YouTube upload failed: {error_content}")
                raise err
            except Exception as e:
                LOGGER.error(f"Unexpected error during upload: {e}")
                raise e

        if self.listener.is_cancelled:
            return None

        # Clean up the file after successful upload (only if it's a single file upload path)
        # For playlists, videos are removed individually in _upload_video after each successful upload.
        # However, _upload_video is also used by _upload_playlist.
        # We need to ensure that remove(file_path) in _upload_video doesn't cause issues
        # when called from _upload_playlist where file_path is part of a larger folder operation.
        # The current implementation of _upload_video removes the file it uploads. This is fine.

        # self.file_processed_bytes and self.total_files are updated differently now.
        # For single video: self.total_files +=1 (as before, implicitly by on_upload_complete call)
        # For playlist: self.total_files is set in _upload_playlist

        # Reset file_processed_bytes for the next potential file if this method is called again in some context
        # Though typically one YouTubeUpload instance handles one upload operation (file or folder).
        # self.file_processed_bytes = 0 # This might be better handled at start of _upload_video

        if response:
            video_id = response["id"]
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            LOGGER.info(f"Video uploaded successfully: {video_url}")

            if self.playlist_id:
                LOGGER.info(
                    f"Adding video ID {video_id} to specified playlist ID {self.playlist_id}"
                )
                try:
                    playlist_item_request_body = {
                        "snippet": {
                            "playlistId": self.playlist_id,
                            "resourceId": {
                                "kind": "youtube#video",
                                "videoId": video_id,
                            },
                        }
                    }
                    playlist_item_insert_request = (
                        self.service.playlistItems().insert(
                            part="snippet", body=playlist_item_request_body
                        )
                    )
                    playlist_item_insert_request.execute()
                    LOGGER.info(
                        f"Successfully added video ID {video_id} to playlist {self.playlist_id}"
                    )
                except HttpError as e:
                    LOGGER.error(
                        f"Could not add video {video_id} to playlist {self.playlist_id}: {e}"
                    )
                    # Decide if this should be a task-failing error or just a warning.
                    # For now, log and continue. The video is uploaded, just not added to the specific playlist.
                except Exception as e:
                    LOGGER.error(
                        f"Unexpected error adding video {video_id} to playlist {self.playlist_id}: {e}"
                    )

            return video_url

        # If listener cancelled during next_chunk loop, response will be None.
        if self.listener.is_cancelled:
            LOGGER.info("Video upload cancelled during chunk upload.")
            return None  # Propagate cancellation

        raise ValueError(
            "Upload completed (or cancelled) but no response received and not handled by cancellation"
        )

    def get_upload_status(self):
        return {
            "progress": self.upload_progress,
            "speed": self.speed,
            "processed_bytes": self.processed_bytes,
            "total_files": self.total_files,
            "is_uploading": self.is_uploading,
        }
