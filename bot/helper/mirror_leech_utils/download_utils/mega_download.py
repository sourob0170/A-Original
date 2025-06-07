import asyncio
from asyncio import Event
from secrets import token_hex
from time import time

from aiofiles.os import makedirs

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

    class MegaTransfer:
        pass

    class MegaError:
        pass

    MEGA_SDK_AVAILABLE = False
    MEGA_IMPORT_ERROR = f"Unexpected error: {e!s}"

from bot import LOGGER, task_dict, task_dict_lock
from bot.core.config_manager import Config
from bot.helper.ext_utils.bot_utils import async_to_sync, sync_to_async
from bot.helper.ext_utils.limit_checker import limit_checker
from bot.helper.ext_utils.links_utils import get_mega_link_type
from bot.helper.ext_utils.task_manager import (
    check_running_tasks,
    stop_duplicate_check,
)
from bot.helper.mirror_leech_utils.status_utils.mega_status import MegaDownloadStatus
from bot.helper.mirror_leech_utils.status_utils.queue_status import QueueStatus
from bot.helper.telegram_helper.message_utils import send_status_message


class MegaAppListener(MegaListener):
    _NO_EVENT_ON = (MegaRequest.TYPE_LOGIN, MegaRequest.TYPE_FETCH_NODES)
    NO_ERROR = "no error"

    def __init__(self, continue_event: Event, listener):
        self.continue_event = continue_event
        self.node = None
        self.public_node = None
        self.listener = listener
        self.is_cancelled = False
        self.error = None
        self.__bytes_transferred = 0
        self.__speed = 0
        self.__name = ""
        self.__start_time = time()
        super().__init__()

    @property
    def speed(self):
        return self.__speed

    @property
    def downloaded_bytes(self):
        return self.__bytes_transferred

    def onRequestFinish(self, api, request, error):
        # More robust error checking - ignore errors after cancellation or logout
        if self.is_cancelled:
            return

        error_str = str(error).lower() if error else "unknown error"
        if error_str != "no error":
            # Ignore access denied errors that happen during cleanup/logout
            if "access denied" in error_str.lower():
                return
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
                LOGGER.warning(f"MEGA temporary error (will retry): {self.error}")
            else:
                # Other error codes are more serious
                LOGGER.error(f"MEGA Request Error: {self.error}")
            self.continue_event.set()
            return

        request_type = request.getType()
        if request_type == MegaRequest.TYPE_LOGIN:
            api.fetchNodes()
        elif request_type == MegaRequest.TYPE_GET_PUBLIC_NODE:
            self.public_node = request.getPublicMegaNode()
            self.__name = self.public_node.getName()
        elif request_type == MegaRequest.TYPE_FETCH_NODES:
            self.node = api.getRootNode()
            self.__name = self.node.getName()

        if request_type not in self._NO_EVENT_ON or (
            self.node and "cloud drive" not in self.__name.lower()
        ):
            self.continue_event.set()

    def onRequestTemporaryError(self, _api, _request, error: MegaError):
        error_msg = error.toString()
        LOGGER.error(f"MEGA Request temporary error: {error_msg}")
        if not self.is_cancelled:
            self.is_cancelled = True
            async_to_sync(
                self.listener.on_download_error, f"MEGA Request Error: {error_msg}"
            )
        self.error = error_msg
        self.continue_event.set()

    def onTransferUpdate(self, api: MegaApi, transfer: MegaTransfer):
        if self.is_cancelled:
            LOGGER.info("MEGA transfer cancelled, stopping transfer...")
            api.cancelTransfer(transfer, None)
            self.continue_event.set()
            return

        self.__speed = transfer.getSpeed()
        self.__bytes_transferred = transfer.getTransferredBytes()

    def onTransferFinish(self, _api: MegaApi, transfer: MegaTransfer, error):
        try:
            if self.is_cancelled:
                LOGGER.info("MEGA transfer was cancelled")
                self.continue_event.set()
                return

            if str(error).lower() != "no error":
                error_msg = str(error)
                LOGGER.error(f"MEGA transfer finished with error: {error_msg}")
                self.error = error_msg
                async_to_sync(
                    self.listener.on_download_error,
                    f"MEGA Transfer Error: {error_msg}",
                )
            elif transfer.isFinished() and (
                transfer.isFolderTransfer() or transfer.getFileName() == self.__name
            ):
                async_to_sync(self.listener.on_download_complete)

            self.continue_event.set()
        except Exception as e:
            LOGGER.error(f"Exception in onTransferFinish: {e}")
            self.continue_event.set()

    def onTransferTemporaryError(self, _api, transfer, error):
        filename = transfer.getFileName()
        state = transfer.getState()
        error_str = error.toString()

        LOGGER.error(
            f"MEGA transfer temporary error for {filename}: {error_str} (state: {state})"
        )

        # States 1 and 4 are recoverable, don't cancel for these
        if state in [1, 4]:
            LOGGER.info(
                f"MEGA transfer error is recoverable (state {state}), continuing..."
            )
            return

        self.error = error_str
        if not self.is_cancelled:
            self.is_cancelled = True
            async_to_sync(
                self.listener.on_download_error,
                f"MEGA Transfer Error: {error_str} ({filename})",
            )
            self.continue_event.set()

    async def cancel_download(self):
        self.is_cancelled = True
        await self.listener.on_download_error("Download Canceled by user")


class AsyncExecutor:
    def __init__(self):
        self.continue_event = Event()

    async def do(self, function, args, timeout=None):
        """Execute MEGA function with optional timeout"""
        getattr(function, "__name__", str(function))

        self.continue_event.clear()
        await sync_to_async(function, *args)

        if timeout is not None:
            await asyncio.wait_for(self.continue_event.wait(), timeout=timeout)
        else:
            await self.continue_event.wait()  # No timeout - wait indefinitely


async def _cleanup_mega_apis(api, folder_api, executor):
    """Helper function to cleanup MEGA API instances"""
    try:
        # Set the executor event to prevent any lingering timeouts
        if executor and hasattr(executor, "continue_event"):
            try:
                executor.continue_event.set()
            except Exception as e:
                LOGGER.debug(f"Error setting executor event: {e}")

        # Logout directly without using executor to avoid timeout issues
        if api:
            try:
                # Use direct asyncio.wait_for instead of sync_to_async to avoid timeout issues
                await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(None, api.logout),
                    timeout=120,
                )
            except TimeoutError:
                LOGGER.warning(
                    "MEGA download logout timed out after 120 seconds, but download was successful"
                )
            except Exception as e:
                LOGGER.warning(
                    f"MEGA download logout failed: {e}, but download was successful"
                )

        if folder_api:
            try:
                # Use direct asyncio.wait_for for folder API logout too
                await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(
                        None, folder_api.logout
                    ),
                    timeout=120,
                )
                LOGGER.info("MEGA folder API logged out")
            except TimeoutError:
                LOGGER.warning(
                    "MEGA folder API logout timed out after 120 seconds, but download was successful"
                )
            except Exception as e:
                LOGGER.warning(
                    f"MEGA folder API logout failed: {e}, but download was successful"
                )
    except Exception as e:
        LOGGER.error(f"Error during MEGA API cleanup: {e}")


async def add_mega_download(listener, path):
    """
    Download files/folders from MEGA.nz using the MEGA SDK v4.8.0 with FFmpeg support.

    Args:
        listener: Download listener object
        path: Download destination path
    """
    # Check if MEGA operations are enabled
    if not Config.MEGA_ENABLED:
        await listener.on_download_error(
            "❌ MEGA.nz operations are disabled by the administrator."
        )
        return

    # Check if MEGA SDK v4.8.0 is available and working
    if not MEGA_SDK_AVAILABLE:
        error_msg = (
            "❌ MEGA SDK v4.8.0 not available. Please install megasdk v4.8.0."
        )
        if MEGA_IMPORT_ERROR:
            error_msg += f"\nImport error: {MEGA_IMPORT_ERROR}"
        await listener.on_download_error(error_msg)
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

    executor = AsyncExecutor()
    api = MegaApi(None, None, None, "aimleechbot")
    folder_api = None

    mega_listener = MegaAppListener(executor.continue_event, listener)
    api.addListener(mega_listener)

    try:
        # Login if credentials are provided
        if MEGA_EMAIL and MEGA_PASSWORD:
            await executor.do(api.login, (MEGA_EMAIL, MEGA_PASSWORD), timeout=60)
        else:
            pass  # Anonymous access

        # Handle file vs folder links
        link_type = get_mega_link_type(listener.link)

        if link_type == "file":
            await executor.do(api.getPublicNode, (listener.link,), timeout=30)
            node = mega_listener.public_node
        else:
            folder_api = MegaApi(None, None, None, "aimleechbot")
            folder_api.addListener(mega_listener)
            await executor.do(folder_api.loginToFolder, (listener.link,), timeout=30)
            node = await sync_to_async(folder_api.authorizeNode, mega_listener.node)

        if mega_listener.error is not None:
            error_msg = f"Failed to get MEGA node: {mega_listener.error}"
            LOGGER.error(error_msg)
            await listener.on_download_error(error_msg)
            return

        if node is None:
            error_msg = "Failed to retrieve MEGA node"
            LOGGER.error(error_msg)
            await listener.on_download_error(error_msg)
            return

    except Exception as e:
        error_msg = f"Error accessing MEGA link: {e!s}"
        LOGGER.error(error_msg)
        await listener.on_download_error(error_msg)
        return
    finally:
        pass  # Cleanup will be done later after download completes

    # Set name and size based on the node type
    link_type = get_mega_link_type(listener.link)
    if link_type == "file":
        listener.name = listener.name or node.getName()
        listener.size = node.getSize()
    else:
        listener.name = listener.name or node.getName()
        listener.size = node.getSize()

    gid = token_hex(4)

    # Check size limits
    if listener.size > 0:
        limit_msg = await limit_checker(
            listener.size,
            listener,
            isTorrent=False,
            isMega=True,
            isDriveLink=False,
            isYtdlp=False,
        )
        if limit_msg:
            LOGGER.warning(f"MEGA download size limit exceeded: {limit_msg}")
            await listener.on_download_error(limit_msg)
            await _cleanup_mega_apis(api, folder_api, executor)
            return

    # Check for duplicate downloads
    msg, button = await stop_duplicate_check(listener)
    if msg:
        LOGGER.info(f"MEGA download duplicate detected: {msg}")
        await listener.on_download_error(msg, button)
        await _cleanup_mega_apis(api, folder_api, executor)
        return

    # Check if download should be queued
    added_to_queue, event = await check_running_tasks(listener)
    if added_to_queue:
        async with task_dict_lock:
            task_dict[listener.mid] = QueueStatus(listener, gid, "dl")
        await listener.on_download_start()
        await send_status_message(listener.message)
        await event.wait()
        async with task_dict_lock:
            if listener.mid not in task_dict:
                await _cleanup_mega_apis(api, folder_api, executor)
                return
        from_queue = True
    else:
        from_queue = False

    # Create download status tracker
    async with task_dict_lock:
        task_dict[listener.mid] = MegaDownloadStatus(
            listener.name, listener.size, gid, mega_listener, listener.message
        )

    # Start the download
    if from_queue:
        pass
    else:
        await listener.on_download_start()
        await send_status_message(listener.message)

    try:
        # Create download directory
        await makedirs(path, exist_ok=True)

        # Start the actual download with MEGA SDK v4.8.0 API signature
        # startDownload(node, localPath, customName, appData, startFirst, cancelToken)
        # localPath should be the full file path, not just the directory

        # Construct the full file path for the download
        file_path = f"{path}/{listener.name}"

        await executor.do(
            api.startDownload, (node, file_path, None, None, False, None)
        )

    except Exception as e:
        error_msg = f"Error during MEGA download: {e!s}"
        LOGGER.error(error_msg)
        await listener.on_download_error(error_msg)
    finally:
        # Always cleanup API connections
        await _cleanup_mega_apis(api, folder_api, executor)
