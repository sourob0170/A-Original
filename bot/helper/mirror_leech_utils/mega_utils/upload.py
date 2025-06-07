import asyncio
import subprocess
from asyncio import Event, create_subprocess_exec
from os import path as ospath
from os import walk
from secrets import token_hex
from time import time

from aiofiles.os import path as aiopath
from aiofiles.os import remove as aioremove

# Try to import MEGA SDK at module level, but don't fail if not available
try:
    from mega import MegaApi, MegaError, MegaListener, MegaRequest, MegaTransfer

    MEGA_SDK_AVAILABLE = True
    MEGA_IMPORT_ERROR = None
except ImportError as e:
    # Create dummy classes to prevent import errors
    class MegaApi:
        pass

    class MegaListener:
        pass

    class MegaRequest:
        TYPE_LOGIN = 1
        TYPE_FETCH_NODES = 2
        TYPE_GET_PUBLIC_NODE = 3
        TYPE_COPY = 4
        TYPE_EXPORT = 5
        TYPE_CREATE_FOLDER = 6

    class MegaTransfer:
        pass

    class MegaError:
        pass

    MEGA_SDK_AVAILABLE = False
    MEGA_IMPORT_ERROR = str(e)
except Exception as e:
    # Handle other import errors
    class MegaApi:
        pass

    class MegaListener:
        pass

    class MegaRequest:
        TYPE_LOGIN = 1
        TYPE_FETCH_NODES = 2
        TYPE_GET_PUBLIC_NODE = 3
        TYPE_COPY = 4
        TYPE_EXPORT = 5
        TYPE_CREATE_FOLDER = 6

    class MegaTransfer:
        pass

    class MegaError:
        pass

    MEGA_SDK_AVAILABLE = False
    MEGA_IMPORT_ERROR = f"Unexpected error: {e!s}"

from bot import LOGGER, task_dict, task_dict_lock
from bot.core.config_manager import Config
from bot.helper.ext_utils.bot_utils import async_to_sync, sync_to_async
from bot.helper.ext_utils.task_manager import check_running_tasks
from bot.helper.mirror_leech_utils.status_utils.mega_status import MegaUploadStatus
from bot.helper.mirror_leech_utils.status_utils.queue_status import QueueStatus
from bot.helper.telegram_helper.message_utils import send_status_message


async def generate_video_thumbnail(video_path):
    """
    Generate thumbnail for video files using FFmpeg.

    Args:
        video_path: Path to the video file

    Returns:
        Path to generated thumbnail or None if failed
    """
    if not Config.MEGA_UPLOAD_THUMBNAIL:
        return None

    try:
        # Check if file is a video
        video_extensions = [
            ".mp4",
            ".mkv",
            ".avi",
            ".mov",
            ".wmv",
            ".flv",
            ".webm",
            ".m4v",
        ]
        if not any(video_path.lower().endswith(ext) for ext in video_extensions):
            return None

        thumbnail_path = f"{video_path}_thumbnail.jpg"

        # Use FFmpeg to generate thumbnail at 10% of video duration
        cmd = [
            "xtra",  # Using the renamed ffmpeg binary
            "-i",
            video_path,
            "-ss",
            "00:00:10",  # Seek to 10 seconds
            "-vframes",
            "1",  # Extract 1 frame
            "-vf",
            "scale=320:240",  # Resize to 320x240
            "-y",  # Overwrite output file
            thumbnail_path,
        ]

        LOGGER.info(f"Generating thumbnail for: {video_path}")
        process = await create_subprocess_exec(
            *cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode == 0 and ospath.exists(thumbnail_path):
            LOGGER.info(f"Thumbnail generated successfully: {thumbnail_path}")
            return thumbnail_path
        LOGGER.error(f"Failed to generate thumbnail: {stderr.decode()}")
        return None

    except Exception as e:
        LOGGER.error(f"Error generating thumbnail: {e}")
        return None


class MegaUploadListener(MegaListener):
    _NO_EVENT_ON = (MegaRequest.TYPE_LOGIN, MegaRequest.TYPE_FETCH_NODES)
    NO_ERROR = "no error"

    def __init__(self, continue_event: Event, listener):
        super().__init__()  # Call parent constructor first
        self.continue_event = continue_event
        self.node = None
        self.upload_node = None
        self.listener = listener
        self.is_cancelled = False
        self.error = None
        self.__bytes_transferred = 0
        self.__speed = 0
        self.__name = ""
        self.__start_time = time()
        self.__upload_folder = None

    @property
    def downloaded_bytes(self):
        return self.__bytes_transferred

    @property
    def speed(self):
        return self.__speed

    async def cancel_download(self):
        self.is_cancelled = True
        await self.listener.on_upload_error("Upload cancelled by user")

    def onRequestFinish(self, api, request, error):
        """Called when a request finishes - with exception handling to prevent SWIG errors"""
        try:
            # More robust error checking
            error_str = str(error).lower() if error else "unknown error"
            if error_str != "no error":
                self.error = error.copy() if hasattr(error, "copy") else str(error)

                # Classify error severity based on error content
                if "error code: -1" in error_str:
                    # Error code -1 is typically a temporary network/connection issue
                    # Log as INFO since these are usually automatically retried and succeed
                    LOGGER.info(
                        f"MEGA temporary connection issue (will retry): {self.error}"
                    )
                elif any(
                    temp_error in error_str
                    for temp_error in [
                        "error code: -2",
                        "error code: -3",
                        "error code: -4",
                        "error code: -5",
                    ]
                ):
                    # These are also typically temporary errors
                    LOGGER.warning(
                        f"MEGA temporary error (will retry): {self.error}"
                    )
                else:
                    # Other error codes are more serious
                    LOGGER.error(f"MEGA Upload Request Error: {self.error}")
                self.continue_event.set()
                return

            # Safer request type checking
            try:
                request_type = request.getType()
            except Exception as e:
                LOGGER.error(f"Failed to get request type: {e}")
                self.error = f"Request type error: {e}"
                self.continue_event.set()
                return

            if request_type == MegaRequest.TYPE_LOGIN:
                try:
                    api.fetchNodes()
                except Exception as e:
                    LOGGER.error(f"Failed to fetch nodes: {e}")
                    self.error = f"Fetch nodes error: {e}"
                    self.continue_event.set()

            elif request_type == MegaRequest.TYPE_FETCH_NODES:
                try:
                    self.node = api.getRootNode()
                    if self.node:
                        self.__name = self.node.getName()
                    else:
                        self.error = "Failed to get root node"
                        LOGGER.error("MEGA upload: Failed to get root node")
                except Exception as e:
                    LOGGER.error(f"Failed to get root node: {e}")
                    self.error = f"Root node error: {e}"

            elif request_type == MegaRequest.TYPE_CREATE_FOLDER:
                try:
                    self.__upload_folder = request.getNodeHandle()
                    LOGGER.info(
                        f"MEGA upload folder created: {self.__upload_folder}"
                    )
                except Exception as e:
                    LOGGER.error(f"Failed to get folder handle: {e}")
                    self.error = f"Folder handle error: {e}"

            elif request_type == MegaRequest.TYPE_EXPORT:
                try:
                    public_link = request.getLink()
                    # Determine if it's a file or folder
                    is_file = (
                        hasattr(self.listener, "is_file") and self.listener.is_file
                    )
                    files_count = 1 if is_file else 0
                    folders_count = 0 if is_file else 1
                    mime_type = "File" if is_file else "Folder"
                    async_to_sync(
                        self.listener.on_upload_complete,
                        public_link,
                        files_count,
                        folders_count,
                        mime_type,
                    )
                except Exception as e:
                    LOGGER.error(f"Failed to get public link: {e}")
                    self.error = f"Public link error: {e}"

            # Safer event setting
            try:
                if request_type not in self._NO_EVENT_ON or (
                    self.node
                    and self.__name
                    and "cloud drive" not in self.__name.lower()
                ):
                    self.continue_event.set()
            except Exception as e:
                LOGGER.error(f"Error setting continue event: {e}")
                self.continue_event.set()

        except Exception as e:
            # Critical: Prevent any exceptions from propagating back to C++
            # This prevents SWIG DirectorMethodException
            try:
                LOGGER.error(
                    f"Critical exception in MEGA upload onRequestFinish: {e}"
                )
                self.error = f"Critical error: {e}"
                self.continue_event.set()
            except Exception:
                # Last resort: even logging failed, just set the event
                pass

    def onRequestTemporaryError(self, _api, _request, error: MegaError):
        error_msg = error.toString()
        LOGGER.error(f"MEGA Upload Request temporary error: {error_msg}")

        # Check for authentication-related errors that are actually permanent
        if any(
            auth_error in error_msg.lower()
            for auth_error in [
                "access denied",
                "login required",
                "invalid credentials",
                "authentication failed",
                "unauthorized",
                "forbidden",
            ]
        ):
            # This is actually a permanent authentication error, not temporary
            if not self.is_cancelled:
                self.is_cancelled = True
                if "access denied" in error_msg.lower():
                    friendly_msg = (
                        "❌ MEGA Authentication Failed: Access denied.\n\n"
                        "This usually means:\n"
                        "• Invalid MEGA email or password\n"
                        "• Account suspended or restricted\n"
                        "• Two-factor authentication enabled (not supported)\n\n"
                        "Please check your MEGA credentials in bot settings."
                    )
                else:
                    friendly_msg = f"❌ MEGA Authentication Error: {error_msg}"

                async_to_sync(self.listener.on_upload_error, friendly_msg)
        # Handle other temporary errors normally
        elif not self.is_cancelled:
            self.is_cancelled = True
            async_to_sync(
                self.listener.on_upload_error,
                f"MEGA Upload Request Error: {error_msg}",
            )

        self.error = error_msg
        self.continue_event.set()

    def onTransferUpdate(self, api: MegaApi, transfer: MegaTransfer):
        if self.is_cancelled:
            LOGGER.info("MEGA upload cancelled, stopping transfer...")
            api.cancelTransfer(transfer, None)
            self.continue_event.set()
            return

        self.__speed = transfer.getSpeed()
        self.__bytes_transferred = transfer.getTransferredBytes()

    def onTransferFinish(self, api: MegaApi, transfer: MegaTransfer, error):
        try:
            if self.is_cancelled:
                LOGGER.info("MEGA upload transfer was cancelled")
                self.continue_event.set()
                return

            if str(error).lower() != "no error":
                error_msg = str(error)
                LOGGER.error(
                    f"MEGA upload transfer finished with error: {error_msg}"
                )
                self.error = error_msg
                async_to_sync(
                    self.listener.on_upload_error,
                    f"MEGA Upload Transfer Error: {error_msg}",
                )
            else:
                LOGGER.info(
                    f"MEGA upload completed successfully: {transfer.getFileName()}"
                )
                self.upload_node = transfer.getNodeHandle()

                # Generate public link if configured
                if Config.MEGA_UPLOAD_PUBLIC:
                    node = api.getNodeByHandle(self.upload_node)
                    if node:
                        api.exportNode(node)
                        return  # Wait for export to complete

                # If no public link needed, complete upload
                # Determine if it's a file or folder
                is_file = hasattr(self.listener, "is_file") and self.listener.is_file
                files_count = 1 if is_file else 0
                folders_count = 0 if is_file else 1
                mime_type = "File" if is_file else "Folder"
                async_to_sync(
                    self.listener.on_upload_complete,
                    None,
                    files_count,
                    folders_count,
                    mime_type,
                )

            self.continue_event.set()
        except Exception as e:
            LOGGER.error(f"Exception in MEGA upload onTransferFinish: {e}")
            self.continue_event.set()

    def onTransferTemporaryError(self, _api, transfer, error):
        filename = transfer.getFileName()
        state = transfer.getState()
        error_str = error.toString()

        LOGGER.error(
            f"MEGA upload transfer temporary error for {filename}: {error_str} (state: {state})"
        )

        # States 1 and 4 are recoverable, don't cancel for these
        if state in [1, 4]:
            LOGGER.info(
                f"MEGA upload transfer error is recoverable (state {state}), continuing..."
            )
            return

        self.error = error_str
        if not self.is_cancelled:
            self.is_cancelled = True
            async_to_sync(
                self.listener.on_upload_error,
                f"MEGA Upload Transfer Error: {error_str} ({filename})",
            )
            self.continue_event.set()


class AsyncMegaExecutor:
    def __init__(self):
        self.continue_event = Event()

    async def do(self, function, args, timeout=None):
        """Execute MEGA function with improved timeout handling and retry logic"""
        function_name = getattr(function, "__name__", str(function))

        # Try multiple attempts with increasing timeouts for login operations only
        max_attempts = 3 if function_name == "login" else 1
        base_timeout = timeout

        for attempt in range(max_attempts):
            if timeout is not None:
                current_timeout = base_timeout + (
                    attempt * 60
                )  # Increase timeout each attempt
            else:
                current_timeout = None  # No timeout for main operations

            if attempt > 0:
                await asyncio.sleep(5)  # Brief delay between attempts

            self.continue_event.clear()

            try:
                # Execute the MEGA function
                await sync_to_async(function, *args)

                # Wait for completion with or without timeout
                if current_timeout is not None:
                    await asyncio.wait_for(
                        self.continue_event.wait(), timeout=current_timeout
                    )
                else:
                    await (
                        self.continue_event.wait()
                    )  # No timeout - wait indefinitely

                return  # Success, exit retry loop

            except TimeoutError:
                if (
                    attempt == max_attempts - 1
                ):  # Last attempt - this is a real failure
                    LOGGER.error(
                        f"MEGA {function_name} operation timed out after {current_timeout} seconds (attempt {attempt + 1}) - FINAL FAILURE"
                    )
                    raise Exception(
                        f"MEGA {function_name} operation failed after {max_attempts} attempts. This may be due to network issues or MEGA server problems."
                    )
                # Not the last attempt - this is just a retry, log as INFO
                LOGGER.info(
                    f"MEGA {function_name} operation timed out after {current_timeout} seconds (attempt {attempt + 1}) - retrying with longer timeout"
                )
                continue  # Try again

            except Exception as e:
                # Re-raise other exceptions immediately (don't retry)
                LOGGER.error(f"MEGA {function_name} operation failed: {e!s}")
                raise Exception(f"MEGA {function_name} operation failed: {e!s}")


def _get_premium_settings(is_premium):
    """Get optimized settings based on account type"""
    if is_premium:
        return {
            "chunk_size": 10485760,  # 10MB chunks for premium
            "parallel_uploads": 6,  # More parallel uploads
            "bandwidth_limit": 0,  # No bandwidth limit
        }
    return {
        "chunk_size": 1048576,  # 1MB chunks for free
        "parallel_uploads": 1,  # Single upload for free
        "bandwidth_limit": 1,  # Bandwidth limited
    }


async def _detect_mega_account_type(api):
    """Detect MEGA account type (free/premium) and return settings"""
    try:
        # Add a small delay to ensure account details are available
        await asyncio.sleep(0.5)

        # Get account details with retry mechanism
        account_details = None
        for attempt in range(3):
            try:
                account_details = api.getAccountDetails()
                if account_details:
                    break
                await asyncio.sleep(0.5)
            except Exception as e:
                LOGGER.debug(f"Account details attempt {attempt + 1} failed: {e}")
                if attempt < 2:
                    await asyncio.sleep(1.0)

        if account_details:
            try:
                pro_level = account_details.getProLevel()
                storage_used = account_details.getStorageUsed()
                storage_max = account_details.getStorageMax()
                transfer_used = account_details.getTransferOwnUsed()
                transfer_max = account_details.getTransferMax()

                is_premium = pro_level > 0

                if is_premium:
                    LOGGER.info(
                        f"🎉 MEGA Premium account detected (Level {pro_level})"
                    )
                    LOGGER.info(f"📊 Storage: {storage_used}/{storage_max} bytes")
                    LOGGER.info(f"📊 Transfer: {transfer_used}/{transfer_max} bytes")
                    LOGGER.info(
                        "✅ Premium features enabled: larger chunks, parallel uploads, no bandwidth limits"
                    )
                else:
                    LOGGER.info("📱 MEGA Free account detected")
                    LOGGER.info(f"📊 Storage: {storage_used}/{storage_max} bytes")
                    LOGGER.info(f"📊 Transfer: {transfer_used}/{transfer_max} bytes")
                    LOGGER.info(
                        "⚠️ Free account limitations: smaller chunks, single uploads, bandwidth limited"
                    )

                return is_premium, _get_premium_settings(is_premium)
            except Exception as e:
                LOGGER.debug(f"Error parsing account details: {e}")
                LOGGER.info(
                    "📱 MEGA account detected, using free account settings as fallback"
                )
                return False, _get_premium_settings(False)
        else:
            LOGGER.info("📱 MEGA account detected, using free account settings")
            return False, _get_premium_settings(False)

    except Exception as e:
        LOGGER.debug(f"Error detecting MEGA account type: {e}")
        LOGGER.info(
            "📱 MEGA account detected, using free account settings as fallback"
        )
        return False, _get_premium_settings(False)


async def _navigate_to_folder(api, root_node, folder_path):
    """Navigate to a specific folder path in MEGA drive"""
    try:
        if not folder_path or folder_path in {"", "/"}:
            LOGGER.info("Using root folder (empty path)")
            return root_node

        # Remove leading/trailing slashes and split path
        path_parts = folder_path.strip("/").split("/")
        current_node = root_node

        for part in path_parts:
            if not part:  # Skip empty parts
                continue

            # Get children of current node
            children = await sync_to_async(api.getChildren, current_node)
            if not children:
                LOGGER.error("No children found in current folder")
                return None

            # Find the folder with matching name
            found_folder = None
            for i in range(children.size()):
                child = children.get(i)
                if child and child.isFolder() and not child.isRemoved():
                    child_name = child.getName()
                    if child_name == part:
                        found_folder = child
                        break

            if found_folder is None:
                LOGGER.error(f"Folder '{part}' not found in path '{folder_path}'")
                return None

            current_node = found_folder

        return current_node

    except Exception as e:
        LOGGER.error(f"Error navigating to folder '{folder_path}': {e}")
        return None


async def _cleanup_mega_upload_api(api, executor, listener=None):
    """Helper function to cleanup MEGA API instances"""
    try:
        if listener and api:
            try:
                api.removeListener(listener)
            except Exception as e:
                LOGGER.error(f"Error removing MEGA upload listener: {e}")

        if api and executor:
            try:
                # Use a reasonable timeout for logout to prevent hanging
                # Logout should be quick, but give it more time to avoid timeout errors
                # Use direct asyncio.wait_for instead of executor.do to avoid retry logic for cleanup
                await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(None, api.logout),
                    timeout=120,
                )
                LOGGER.info("MEGA upload API logged out")
            except TimeoutError:
                LOGGER.warning(
                    "MEGA upload logout timed out after 120 seconds, but upload was successful"
                )
            except Exception as e:
                LOGGER.warning(
                    f"MEGA upload logout failed: {e}, but upload was successful"
                )
    except Exception as e:
        LOGGER.error(f"Error during MEGA upload API cleanup: {e}")


async def add_mega_upload(listener, path):
    """
    Upload files/folders to MEGA.nz using the MEGA SDK v4.8.0 with FFmpeg support.

    Args:
        listener: Upload listener object
        path: Local path to upload
    """
    # Check if MEGA operations are enabled
    if not Config.MEGA_ENABLED:
        await listener.on_upload_error(
            "❌ MEGA.nz operations are disabled by the administrator."
        )
        return

    # Check if MEGA upload operations are enabled
    if not Config.MEGA_UPLOAD_ENABLED:
        await listener.on_upload_error(
            "❌ MEGA.nz upload operations are disabled by the administrator."
        )
        return

    # Check for user MEGA credentials first, then fall back to owner credentials
    user_mega_email = listener.user_dict.get("MEGA_EMAIL")
    user_mega_password = listener.user_dict.get("MEGA_PASSWORD")

    if user_mega_email and user_mega_password:
        MEGA_EMAIL = user_mega_email
        MEGA_PASSWORD = user_mega_password
    else:
        MEGA_EMAIL = Config.MEGA_EMAIL
        MEGA_PASSWORD = Config.MEGA_PASSWORD

    if not MEGA_EMAIL or not MEGA_PASSWORD:
        await listener.on_upload_error(
            "❌ MEGA.nz credentials not configured. Please set MEGA_EMAIL and MEGA_PASSWORD."
        )
        return

    # Check if MEGA SDK v4.8.0 is available and working
    if not MEGA_SDK_AVAILABLE:
        error_msg = (
            "❌ MEGA SDK v4.8.0 not available. Please install megasdk v4.8.0."
        )
        if MEGA_IMPORT_ERROR:
            error_msg += f"\nImport error: {MEGA_IMPORT_ERROR}"
        await listener.on_upload_error(error_msg)
        return

    LOGGER.info(f"Starting MEGA upload: {path}")

    executor = AsyncMegaExecutor()
    api = None
    mega_listener = None

    try:
        # Initialize MEGA API with error checking and safer patterns
        api_attempts = 3
        api = None

        for attempt in range(api_attempts):
            try:
                # Use a unique app key for each instance to avoid conflicts
                app_key = f"aimleechbot_upload_{int(time())}_{attempt}"

                api = MegaApi(None, None, None, app_key)
                if not api:
                    raise Exception("Failed to create MEGA API instance")

                # Add a small delay to allow API initialization
                await asyncio.sleep(0.2)
                break

            except Exception as e:
                LOGGER.warning(
                    f"MEGA API creation attempt {attempt + 1} failed: {e}"
                )
                if attempt == api_attempts - 1:
                    error_msg = f"Failed to initialize MEGA API after {api_attempts} attempts: {e!s}"
                    LOGGER.error(error_msg)
                    await listener.on_upload_error(error_msg)
                    return
                # Wait before retry
                await asyncio.sleep(1.0)
                continue

        try:
            mega_listener = MegaUploadListener(executor.continue_event, listener)
            api.addListener(mega_listener)
        except Exception as e:
            error_msg = f"Failed to attach MEGA listener: {e!s}"
            LOGGER.error(error_msg)
            await listener.on_upload_error(error_msg)
            return

        # Login with credentials
        try:
            await executor.do(api.login, (MEGA_EMAIL, MEGA_PASSWORD), timeout=60)
        except Exception as e:
            error_msg = f"MEGA login failed: {e!s}"
            LOGGER.error(error_msg)
            await listener.on_upload_error(error_msg)
            return

        if mega_listener.error is not None:
            error_msg = mega_listener.error
            LOGGER.error(f"Failed to login to MEGA: {error_msg}")

            # Provide user-friendly error messages for common authentication issues
            if any(
                auth_error in error_msg.lower()
                for auth_error in [
                    "access denied",
                    "login required",
                    "invalid credentials",
                    "authentication failed",
                    "unauthorized",
                    "forbidden",
                ]
            ):
                if "access denied" in error_msg.lower():
                    friendly_msg = (
                        "❌ MEGA Authentication Failed: Access denied.\n\n"
                        "This usually means:\n"
                        "• Invalid MEGA email or password\n"
                        "• Account suspended or restricted\n"
                        "• Two-factor authentication enabled (not supported)\n\n"
                        "Please check your MEGA credentials in bot settings."
                    )
                else:
                    friendly_msg = f"❌ MEGA Authentication Error: {error_msg}"
                await listener.on_upload_error(friendly_msg)
            else:
                await listener.on_upload_error(
                    f"Failed to login to MEGA: {error_msg}"
                )
            return

        # Verify we have a valid node
        if not mega_listener.node:
            error_msg = "Failed to get MEGA root node for upload"
            LOGGER.error(error_msg)
            await listener.on_upload_error(error_msg)
            return

        # Detect account type and get optimized settings
        try:
            is_premium, premium_settings = await _detect_mega_account_type(api)
        except Exception as e:
            LOGGER.warning(
                f"Could not detect account type: {e}, using free account settings"
            )

        # Get upload destination folder (use node handles for memory safety)
        upload_folder_node = mega_listener.node  # Root by default

        # Check if user selected a specific folder through folder selector
        selected_folder_path = getattr(listener, "mega_upload_path", None)
        if selected_folder_path:
            upload_folder_node = await _navigate_to_folder(
                api, mega_listener.node, selected_folder_path
            )
            if upload_folder_node is None:
                error_msg = (
                    f"Failed to navigate to selected folder: {selected_folder_path}"
                )
                LOGGER.error(error_msg)
                await listener.on_upload_error(error_msg)
                return
        elif Config.MEGA_UPLOAD_FOLDER:
            # Use configured upload folder
            LOGGER.info(
                f"Using configured upload folder: {Config.MEGA_UPLOAD_FOLDER}"
            )
            upload_folder_node = await _navigate_to_folder(
                api, mega_listener.node, Config.MEGA_UPLOAD_FOLDER
            )
            if upload_folder_node is None:
                error_msg = f"Failed to navigate to configured folder: {Config.MEGA_UPLOAD_FOLDER}"
                LOGGER.error(error_msg)
                await listener.on_upload_error(error_msg)
                return
        else:
            LOGGER.info("Using MEGA root folder for upload")

        # Store node handle for memory safety (prevent segmentation faults)
        upload_folder_handle = upload_folder_node.getHandle()

    except Exception as e:
        error_msg = f"Error accessing MEGA for upload: {e!s}"
        LOGGER.error(error_msg)
        await listener.on_upload_error(error_msg)
        await _cleanup_mega_upload_api(api, executor, mega_listener)
        return

    # Set name and size based on the path
    if ospath.isfile(path):
        listener.name = listener.name or ospath.basename(path)
        listener.size = await aiopath.getsize(path)
        listener.is_file = True
    else:
        listener.name = listener.name or ospath.basename(path)
        listener.is_file = False
        # Calculate folder size
        total_size = 0
        for dirpath, _, filenames in walk(path):
            for filename in filenames:
                filepath = ospath.join(dirpath, filename)
                if ospath.exists(filepath):
                    total_size += ospath.getsize(filepath)
        listener.size = total_size

    gid = token_hex(4)

    # Check if upload should be queued
    added_to_queue, event = await check_running_tasks(listener)
    if added_to_queue:
        async with task_dict_lock:
            task_dict[listener.mid] = QueueStatus(listener, gid, "up")
        await send_status_message(listener.message)
        await event.wait()
        async with task_dict_lock:
            if listener.mid not in task_dict:
                LOGGER.info("MEGA upload was cancelled while in queue")
                await _cleanup_mega_upload_api(api, executor)
                return
        from_queue = True
    else:
        from_queue = False

    # Create upload status tracker
    async with task_dict_lock:
        task_dict[listener.mid] = MegaUploadStatus(
            listener.name,
            listener.size,
            gid,
            mega_listener,
            listener.message,
            listener,
        )

    # Start the upload
    if from_queue:
        pass
    else:
        await send_status_message(listener.message)

    try:
        # Generate thumbnail if it's a video file and thumbnail generation is enabled
        thumbnail_path = None
        if ospath.isfile(path) and Config.MEGA_UPLOAD_THUMBNAIL:
            thumbnail_path = await generate_video_thumbnail(path)
            if thumbnail_path:
                LOGGER.info(f"Generated thumbnail for MEGA upload: {thumbnail_path}")

        # Start the actual upload
        try:
            # Get the actual node from handle for upload (safer approach)
            upload_node = api.getNodeByHandle(upload_folder_handle)
            if not upload_node:
                error_msg = "Failed to get upload folder node from handle"
                LOGGER.error(error_msg)
                await listener.on_upload_error(error_msg)
                return

            if ospath.isfile(path):
                # Upload single file with MEGA SDK v4.8.0 API signature
                # startUpload(localPath, parent, fileName, mtime, appData, isSourceTemporary, startFirst, cancelToken)
                ospath.getsize(path)

                await executor.do(
                    api.startUpload,
                    (path, upload_node, listener.name, -1, None, False, False, None),
                )
            else:
                # Upload folder with MEGA SDK v4.8.0 API signature
                # startUpload(localPath, parent, fileName, mtime, appData, isSourceTemporary, startFirst, cancelToken)
                await executor.do(
                    api.startUpload,
                    (path, upload_node, None, -1, None, False, False, None),
                )

        except Exception as e:
            error_msg = f"MEGA upload operation failed: {e!s}"
            LOGGER.error(error_msg)
            await listener.on_upload_error(error_msg)
            return

        # Clean up thumbnail if it was generated
        if thumbnail_path and ospath.exists(thumbnail_path):
            try:
                await aioremove(thumbnail_path)
                LOGGER.info(f"Cleaned up thumbnail: {thumbnail_path}")
            except Exception as e:
                LOGGER.error(f"Failed to clean up thumbnail: {e}")

    except Exception as e:
        error_msg = f"Error during MEGA upload: {e!s}"
        LOGGER.error(error_msg)
        await listener.on_upload_error(error_msg)
    finally:
        # Always cleanup API connections
        await _cleanup_mega_upload_api(api, executor, mega_listener)
