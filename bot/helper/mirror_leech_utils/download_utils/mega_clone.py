import asyncio
from asyncio import Event
from secrets import token_hex
from time import time

from bot import LOGGER, task_dict, task_dict_lock
from bot.core.config_manager import Config
from bot.helper.ext_utils.bot_utils import async_to_sync, sync_to_async
from bot.helper.ext_utils.links_utils import get_mega_link_type
from bot.helper.ext_utils.task_manager import check_running_tasks
from bot.helper.mirror_leech_utils.status_utils.mega_status import MegaCloneStatus
from bot.helper.mirror_leech_utils.status_utils.queue_status import QueueStatus
from bot.helper.telegram_helper.message_utils import send_status_message

# Try to import MEGA SDK with system-wide detection
MEGA_SDK_AVAILABLE = False
MEGA_IMPORT_ERROR = None


def _detect_and_import_mega():
    """Detect MEGA SDK installation system-wide and import"""
    import sys
    from pathlib import Path

    # System-wide search paths for MEGA SDK
    search_paths = [
        "/usr/local/lib/python3.13/dist-packages",
        "/usr/lib/python3/dist-packages",
        "/usr/lib/python3.13/dist-packages",
        "/usr/local/lib/python3.12/dist-packages",
        "/usr/lib/python3.12/dist-packages",
        f"{sys.prefix}/lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages",
        f"{sys.prefix}/lib/python{sys.version_info.major}.{sys.version_info.minor}/dist-packages",
        "/usr/src/app/.venv/lib/python3.13/site-packages",
        "/opt/megasdk/lib/python3.13/site-packages",
    ]

    # Try standard import first
    try:
        from mega import MegaApi, MegaError, MegaListener, MegaRequest, MegaTransfer

        # Test basic functionality
        api = MegaApi("test")
        api.getVersion()
        return (
            True,
            None,
            (MegaApi, MegaError, MegaListener, MegaRequest, MegaTransfer),
        )
    except ImportError:
        pass
    except Exception as e:
        return False, f"MEGA SDK validation failed: {e}", None

    # Search system-wide paths
    for path in search_paths:
        mega_path = Path(path) / "mega"
        if mega_path.exists():
            try:
                if str(Path(path)) not in sys.path:
                    sys.path.insert(0, str(Path(path)))

                from mega import (
                    MegaApi,
                    MegaError,
                    MegaListener,
                    MegaRequest,
                    MegaTransfer,
                )

                # Test basic functionality
                api = MegaApi("test")
                api.getVersion()
                return (
                    True,
                    None,
                    (MegaApi, MegaError, MegaListener, MegaRequest, MegaTransfer),
                )
            except Exception:
                continue

    return False, "MEGA SDK not found in system-wide search", None


# Perform detection and define classes
try:
    success, error, classes = _detect_and_import_mega()
    if success:
        MegaApi, MegaError, MegaListener, MegaRequest, MegaTransfer = classes
        MEGA_SDK_AVAILABLE = True
        MEGA_IMPORT_ERROR = None

    # Define the real MegaCloneListener class when MEGA SDK is available
    class MegaCloneListener(MegaListener):
        """MEGA Clone Listener - will be dynamically updated with proper inheritance"""

        _NO_EVENT_ON = (MegaRequest.TYPE_LOGIN, MegaRequest.TYPE_FETCH_NODES)

        def __init__(self, continue_event: Event, listener):
            super().__init__()  # Call parent constructor first
            self.continue_event = continue_event
            self.node = None
            self.public_node = None
            self.cloned_node = None
            self.listener = listener
            self.is_cancelled = False
            self.error = None
            self.__bytes_transferred = 0
            self.__speed = 0
            self.__name = ""
            self.__start_time = time()

        @property
        def downloaded_bytes(self):
            return self.__bytes_transferred

        @property
        def speed(self):
            return self.__speed

        async def cancel_download(self):
            self.is_cancelled = True
            await self.listener.on_download_error("Clone cancelled by user")

        async def cancel_task(self):
            """Cancel task method for compatibility with cancel functionality"""
            self.is_cancelled = True
            await self.listener.on_download_error("Clone cancelled by user")

        def onRequestFinish(self, api, request, error):
            try:
                # More robust error checking
                error_str = str(error).lower() if error else "unknown error"
                if error_str != "no error":
                    self.error = (
                        error.copy() if hasattr(error, "copy") else str(error)
                    )
                    LOGGER.error(f"MEGA Clone Request Error: {self.error}")
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
                    LOGGER.info("MEGA login successful for clone, fetching nodes...")
                    try:
                        api.fetchNodes()
                    except Exception as e:
                        LOGGER.error(f"Failed to fetch nodes: {e}")
                        self.error = f"Fetch nodes error: {e}"
                        self.continue_event.set()

                elif request_type == MegaRequest.TYPE_GET_PUBLIC_NODE:
                    try:
                        self.public_node = request.getPublicMegaNode()
                        if self.public_node:
                            self.__name = self.public_node.getName()
                        else:
                            self.error = "Failed to get public node"
                            LOGGER.error("MEGA clone: Failed to get public node")
                    except Exception as e:
                        LOGGER.error(f"Failed to get public node: {e}")
                        self.error = f"Public node error: {e}"

                elif request_type == MegaRequest.TYPE_FETCH_NODES:
                    try:
                        self.node = api.getRootNode()
                        if self.node:
                            self.__name = self.node.getName()
                            # Always set continue event for FETCH_NODES to prevent timeout
                            self.continue_event.set()
                        else:
                            self.error = "Failed to get root node"
                            LOGGER.error("MEGA clone: Failed to get root node")
                            self.continue_event.set()
                    except Exception as e:
                        LOGGER.error(f"Failed to get root node: {e}")
                        self.error = f"Root node error: {e}"
                        self.continue_event.set()

                elif request_type == MegaRequest.TYPE_COPY:
                    try:
                        self.cloned_node = request.getNodeHandle()
                        LOGGER.info(
                            f"MEGA node cloned successfully: {self.cloned_node}"
                        )
                        # Don't call completion here - wait for export if public link is needed
                        # The completion will be called after export or timeout
                    except Exception as e:
                        LOGGER.error(f"Failed to get cloned node handle: {e}")
                        self.error = f"Clone handle error: {e}"

                elif request_type == MegaRequest.TYPE_EXPORT:
                    try:
                        public_link = request.getLink()
                        LOGGER.info(
                            f"MEGA clone public link generated: {public_link}"
                        )
                        # Store the public link for completion message
                        self.public_link = public_link
                        # Don't call completion here - let the main function handle it
                        # This prevents duplicate completion calls
                    except Exception as e:
                        LOGGER.error(f"Failed to get clone public link: {e}")
                        self.error = f"Clone public link error: {e}"

                # Safer event setting - only set for specific request types that haven't already set it
                try:
                    if (
                        request_type not in self._NO_EVENT_ON
                        and request_type != MegaRequest.TYPE_FETCH_NODES
                    ):
                        # FETCH_NODES already sets the event above, don't set it again
                        self.continue_event.set()
                except Exception as e:
                    LOGGER.error(f"Error setting continue event: {e}")
                    self.continue_event.set()

            except Exception as e:
                LOGGER.error(
                    f"Critical exception in MEGA clone onRequestFinish: {e}"
                )
                self.error = f"Critical error: {e}"
                self.continue_event.set()

    def onRequestTemporaryError(self, _api, _request, error: MegaError):
        error_msg = error.toString()
        LOGGER.error(f"MEGA Clone Request temporary error: {error_msg}")
        if not self.is_cancelled:
            self.is_cancelled = True
            async_to_sync(
                self.listener.on_download_error,
                f"MEGA Clone Request Error: {error_msg}",
            )
        self.error = error_msg
        self.continue_event.set()

    def onTransferUpdate(self, api: MegaApi, transfer: MegaTransfer):
        if self.is_cancelled:
            LOGGER.info("MEGA clone cancelled, stopping transfer...")
            api.cancelTransfer(transfer, None)
            self.continue_event.set()
            return

        self.__speed = transfer.getSpeed()
        self.__bytes_transferred = transfer.getTransferredBytes()

        # Log progress every 10% intervals
        if self.__bytes_transferred > 0:
            total_bytes = transfer.getTotalBytes()
            if total_bytes > 0:
                (self.__bytes_transferred / total_bytes) * 100

    def onTransferFinish(self, _api: MegaApi, transfer: MegaTransfer, error):
        try:
            if self.is_cancelled:
                LOGGER.info("MEGA clone transfer was cancelled")
                self.continue_event.set()
                return

            if str(error).lower() != "no error":
                error_msg = str(error)
                # Check if this is an access denied error and log as warning instead of error
                if "access denied" in error_msg.lower():
                    LOGGER.warning(
                        f"MEGA clone transfer finished with access denied: {error_msg}"
                    )
                else:
                    LOGGER.error(
                        f"MEGA clone transfer finished with error: {error_msg}"
                    )
                self.error = error_msg
                async_to_sync(
                    self.listener.on_download_error,
                    f"MEGA Clone Transfer Error: {error_msg}",
                )
            else:
                LOGGER.info(
                    f"MEGA clone completed successfully: {transfer.getFileName()}"
                )
                async_to_sync(self.listener.on_download_complete)

            self.continue_event.set()
        except Exception as e:
            LOGGER.error(f"Exception in MEGA clone onTransferFinish: {e}")
            self.continue_event.set()

    def onTransferTemporaryError(self, _api, transfer, error):
        filename = transfer.getFileName()
        state = transfer.getState()
        error_str = error.toString()

        LOGGER.error(
            f"MEGA clone transfer temporary error for {filename}: {error_str} (state: {state})"
        )

        # States 1 and 4 are recoverable, don't cancel for these
        if state in [1, 4]:
            LOGGER.warning(
                f"MEGA clone transfer error is recoverable (state {state}), continuing..."
            )
            return

        self.error = error_str
        if not self.is_cancelled:
            self.is_cancelled = True
            async_to_sync(
                self.listener.on_download_error,
                f"MEGA Clone Transfer Error: {error_str} ({filename})",
            )
            self.continue_event.set()

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

    # Define dummy MegaCloneListener class when MEGA SDK is not available
    class MegaCloneListener:
        def __init__(self, continue_event, listener):
            self.continue_event = continue_event
            self.listener = listener
            self.error = "MEGA SDK not available"

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

    # Define dummy MegaCloneListener class when MEGA SDK is not available
    class MegaCloneListener:
        def __init__(self, continue_event, listener):
            self.continue_event = continue_event
            self.listener = listener
            self.error = "MEGA SDK not available"


class AsyncMegaCloneExecutor:
    def __init__(self):
        self.continue_event = Event()

    async def do(self, function, args, timeout=None):
        """Execute MEGA function with optional timeout"""
        function_name = getattr(function, "__name__", str(function))

        self.continue_event.clear()
        await sync_to_async(function, *args)

        if timeout is not None:
            try:
                await asyncio.wait_for(self.continue_event.wait(), timeout=timeout)
            except TimeoutError:
                LOGGER.error(
                    f"MEGA {function_name} operation timed out after {timeout} seconds - OPERATION FAILED"
                )
                raise Exception(
                    f"MEGA {function_name} operation timed out after {timeout} seconds"
                ) from None
        else:
            await self.continue_event.wait()  # No timeout - wait indefinitely


def _get_clone_premium_settings(is_premium):
    """Get optimized clone settings based on account type"""
    if is_premium:
        return {
            "parallel_downloads": 6,  # More parallel downloads
            "bandwidth_limit": 0,  # No bandwidth limit
        }
    return {
        "parallel_downloads": 1,  # Single download for free
        "bandwidth_limit": 1,  # Bandwidth limited
    }


async def _detect_mega_clone_account_type(api):
    """Detect MEGA account type for clone operations"""
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
                LOGGER.debug(
                    f"Clone account details attempt {attempt + 1} failed: {e}"
                )
                if attempt < 2:
                    await asyncio.sleep(1.0)

        if account_details:
            try:
                pro_level = account_details.getProLevel()
                account_details.getStorageUsed()
                account_details.getStorageMax()
                account_details.getTransferOwnUsed()
                account_details.getTransferMax()

                is_premium = pro_level > 0

                if is_premium:
                    LOGGER.info(
                        f"🎉 MEGA Premium account detected for clone (Level {pro_level})"
                    )
                else:
                    LOGGER.info("📱 MEGA Free account detected for clone")

                return is_premium, _get_clone_premium_settings(is_premium)
            except Exception:
                LOGGER.info(
                    "📱 MEGA account detected for clone, using free account settings as fallback"
                )
                return False, _get_clone_premium_settings(False)
        else:
            LOGGER.info(
                "📱 MEGA account detected for clone, using free account settings"
            )
            return False, _get_clone_premium_settings(False)

    except Exception as e:
        LOGGER.debug(f"Error detecting MEGA account type for clone: {e}")
        LOGGER.info(
            "📱 MEGA account detected for clone, using free account settings as fallback"
        )
        return False, _get_clone_premium_settings(False)


async def send_clone_completion_message(listener, mega_listener):
    """Send clone completion message to user - same style as upload completion"""
    try:
        # Import required functions (correct import path)
        from html import escape

        from bot.helper.ext_utils.status_utils import get_readable_file_size
        from bot.helper.telegram_helper.message_utils import send_message

        # Get clone details
        name = listener.name or "MEGA_File"
        size = get_readable_file_size(listener.size) if listener.size else "Unknown"

        # Build completion message in same style as upload completion
        msg = f"<b>Name: </b><code>{escape(name)}</code>\n\n<blockquote><b>Size: </b>{size}"

        # Add public link if available (same style as upload - just "MEGA" as clickable link)
        if hasattr(mega_listener, "public_link") and mega_listener.public_link:
            msg += f"\n<b>Link: </b><a href='{mega_listener.public_link}'>MEGA</a>"

        msg += f"</blockquote>\n<b>cc: </b>{listener.tag or '@' + listener.message.from_user.username or 'User'}"

        # Send completion message to user
        await send_message(listener.message, msg)

        # Send completion message to LOG_CHAT_ID if configured
        from bot.core.config_manager import Config

        if Config.LOG_CHAT_ID:
            try:
                await listener.client.send_message(
                    chat_id=int(Config.LOG_CHAT_ID),
                    text=msg,
                    disable_web_page_preview=True,
                    disable_notification=True,
                )

            except Exception as e:
                LOGGER.error(
                    f"Failed to send clone completion message to log chat: {e}"
                )

        # Clean up task from status
        from bot.helper.ext_utils.status_utils import task_dict, task_dict_lock

        async with task_dict_lock:
            if listener.mid in task_dict:
                del task_dict[listener.mid]

    except Exception as e:
        LOGGER.error(f"Error sending clone completion message: {e}")
        # Fallback to simple message with just the link
        try:
            from bot.core.config_manager import Config
            from bot.helper.telegram_helper.message_utils import send_message

            user_tag = (
                listener.tag or "@" + listener.message.from_user.username or "User"
            )
            if hasattr(mega_listener, "public_link") and mega_listener.public_link:
                msg = f"🎉 MEGA Clone completed!\n\n<b>Link:</b> <a href='{mega_listener.public_link}'>MEGA</a>\n<b>cc:</b> {user_tag}"
            else:
                msg = f"🎉 MEGA Clone completed: {listener.name}\n<b>cc:</b> {user_tag}"

            # Send to user
            await send_message(listener.message, msg)

            # Send to LOG_CHAT_ID if configured
            if Config.LOG_CHAT_ID:
                try:
                    await listener.client.send_message(
                        chat_id=int(Config.LOG_CHAT_ID),
                        text=msg,
                        disable_web_page_preview=True,
                        disable_notification=True,
                    )
                except Exception as log_e:
                    LOGGER.error(
                        f"Failed to send fallback clone message to log chat: {log_e}"
                    )
        except Exception as e2:
            LOGGER.error(f"Error sending fallback clone message: {e2}")


async def _fallback_to_download_upload(listener, mega_link, clone_path=None):
    """
    Fallback method: Download from MEGA and then upload to MEGA when direct cloning fails
    """
    try:
        # Import the necessary modules for download
        from bot.helper.mirror_leech_utils.download_utils.mega_download import (
            add_mega_download,
        )

        # Update listener to indicate this is a clone operation with upload
        listener.is_clone = True
        listener.mega_upload_path = clone_path  # Set the upload path for MEGA upload

        # Start MEGA download with correct filesystem path
        download_path = listener.dir  # Use the listener's download directory
        await add_mega_download(listener, download_path)

    except Exception as e:
        error_msg = f"MEGA clone fallback failed: {e}"
        LOGGER.error(error_msg)
        await listener.on_download_error(error_msg)


async def _navigate_to_folder(api, root_node, folder_path):
    """Navigate to a specific folder path in MEGA"""
    if not folder_path or folder_path in {"", "/"}:
        return root_node

    try:
        current_node = root_node
        path_parts = [part for part in folder_path.split("/") if part.strip()]

        for part in path_parts:
            children = api.getChildren(current_node)
            found = False

            if children:
                for i in range(children.size()):
                    child = children.get(i)
                    if child and child.isFolder() and not child.isRemoved():
                        child_name = child.getName()
                        if child_name == part:
                            current_node = child
                            found = True
                            break

            if not found:
                LOGGER.warning(f"Folder '{part}' not found in path '{folder_path}'")
                return None

        return current_node

    except Exception as e:
        LOGGER.error(f"Error navigating to folder '{folder_path}': {e}")
        return None


async def _cleanup_mega_clone_api(api, executor, listener=None):
    """Helper function to cleanup MEGA API instances with enhanced memory safety"""
    try:
        # Remove listener first to prevent callbacks during cleanup
        if listener and api:
            try:
                api.removeListener(listener)
                # Add small delay to ensure listener removal is processed
                await asyncio.sleep(0.2)
            except Exception as e:
                LOGGER.error(f"Error removing MEGA clone listener: {e}")

        # Set the executor event to prevent any lingering timeouts
        if executor and hasattr(executor, "continue_event"):
            try:
                executor.continue_event.set()
            except Exception as e:
                LOGGER.debug(f"Error setting executor event: {e}")

        # Enhanced logout with better error handling and memory safety
        if api:
            try:
                # Add a small delay before logout to ensure all operations are complete
                await asyncio.sleep(0.5)

                # Use direct asyncio.wait_for with shorter timeout to prevent hanging
                await asyncio.wait_for(
                    asyncio.get_event_loop().run_in_executor(None, api.logout),
                    timeout=30,  # Reduced timeout to prevent hanging
                )

                # Add delay after logout to ensure cleanup is complete
                await asyncio.sleep(0.2)

            except TimeoutError:
                LOGGER.warning(
                    "MEGA clone logout timed out after 30 seconds - forcing cleanup"
                )
                # Force cleanup by setting api to None
                api = None
            except Exception as e:
                LOGGER.warning(f"MEGA clone logout failed: {e} - forcing cleanup")
                # Force cleanup by setting api to None
                api = None

    except Exception as e:
        LOGGER.error(f"Error during MEGA clone API cleanup: {e}")
        # Force cleanup in case of any errors
        try:
            if api:
                api = None
        except:
            pass


async def add_mega_clone(listener, mega_link, clone_path=None):
    """
    Clone files/folders from MEGA.nz to MEGA account using the MEGA SDK v4.8.0.
    Performs direct MEGA-to-MEGA cloning without local downloading.

    Args:
        listener: Clone listener object
        mega_link: MEGA link to clone
        clone_path: Optional destination folder path for cloning
    """
    # Check if MEGA operations are enabled
    if not Config.MEGA_ENABLED:
        await listener.on_download_error(
            "❌ MEGA.nz operations are disabled by the administrator."
        )
        return

    # Check if MEGA clone operations are enabled
    if not Config.MEGA_CLONE_ENABLED:
        await listener.on_download_error(
            "❌ MEGA.nz clone operations are disabled by the administrator."
        )
        return

    # Check for user MEGA credentials first, then fall back to owner credentials
    user_mega_email = listener.user_dict.get("MEGA_EMAIL")
    user_mega_password = listener.user_dict.get("MEGA_PASSWORD")

    if user_mega_email and user_mega_password:
        MEGA_EMAIL = user_mega_email
        MEGA_PASSWORD = user_mega_password
        LOGGER.info("Using user MEGA credentials for clone operation")
    else:
        MEGA_EMAIL = Config.MEGA_EMAIL
        MEGA_PASSWORD = Config.MEGA_PASSWORD
        LOGGER.info("Using owner MEGA credentials for clone operation")

    if not MEGA_EMAIL or not MEGA_PASSWORD:
        await listener.on_download_error(
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
        await listener.on_download_error(error_msg)
        return

    executor = AsyncMegaCloneExecutor()
    api = None
    mega_listener = None

    try:
        # Initialize MEGA API with error checking and safer patterns
        try:
            # Use a unique app key for each instance to avoid conflicts
            app_key = f"aimleechbot_clone_{int(time())}"
            api = MegaApi(None, None, None, app_key)
            if not api:
                raise Exception("Failed to create MEGA API instance")

            # Add a small delay to allow API initialization
            await asyncio.sleep(0.1)

        except Exception as e:
            error_msg = f"Failed to initialize MEGA API: {e!s}"
            LOGGER.error(error_msg)
            await listener.on_download_error(error_msg)
            return

        try:
            mega_listener = MegaCloneListener(executor.continue_event, listener)
            api.addListener(mega_listener)
        except Exception as e:
            error_msg = f"Failed to attach MEGA listener: {e!s}"
            LOGGER.error(error_msg)
            await listener.on_download_error(error_msg)
            return

        # Login with credentials
        try:
            # Increase timeout for clone login to 120 seconds
            await executor.do(api.login, (MEGA_EMAIL, MEGA_PASSWORD), timeout=120)
        except Exception as e:
            error_msg = f"MEGA login failed: {e!s}"
            LOGGER.error(error_msg)
            # Check if it's a timeout error and provide helpful message
            if "timed out" in str(e).lower():
                error_msg = "❌ MEGA login timed out. This may be due to network issues or MEGA server load. Please try again later."
            await listener.on_download_error(error_msg)
            return

        if mega_listener.error is not None:
            error_msg = f"Failed to login to MEGA: {mega_listener.error}"
            LOGGER.error(error_msg)
            await listener.on_download_error(error_msg)
            return

        # Detect account type and get optimized settings
        try:
            await _detect_mega_clone_account_type(api)
        except Exception as e:
            LOGGER.warning(
                f"Could not detect account type for clone: {e}, using free account settings"
            )

        # Get public node to clone
        link_type = get_mega_link_type(mega_link)

        if link_type == "file":
            try:
                await executor.do(api.getPublicNode, (mega_link,), timeout=30)
            except Exception as e:
                error_msg = f"Failed to get public node: {e!s}"
                LOGGER.error(error_msg)
                await listener.on_download_error(error_msg)
                return

            # Add a small delay to allow the public node callback to complete
            await asyncio.sleep(0.2)

            if mega_listener.error is not None:
                error_msg = (
                    f"Failed to get MEGA node for clone: {mega_listener.error}"
                )
                LOGGER.error(error_msg)
                await listener.on_download_error(error_msg)
                return

            if mega_listener.public_node is None:
                error_msg = "Failed to retrieve MEGA node for clone"
                LOGGER.error(error_msg)
                await listener.on_download_error(error_msg)
                return

            node = mega_listener.public_node
        else:
            # Handle folder links using loginToFolder (like MEGA download does)
            folder_api = MegaApi(None, None, None, "aimleechbot_clone_folder")
            folder_listener = MegaCloneListener(executor.continue_event, listener)
            folder_api.addListener(folder_listener)

            try:
                await executor.do(
                    folder_api.loginToFolder, (mega_link,), timeout=120
                )
            except Exception as e:
                error_msg = f"Failed to login to folder: {e!s}"
                LOGGER.error(error_msg)
                await listener.on_download_error(error_msg)
                return

            # Add a small delay to allow the folder login callback to complete
            await asyncio.sleep(0.2)

            if folder_listener.error is not None:
                error_msg = (
                    f"Failed to get MEGA folder for clone: {folder_listener.error}"
                )
                LOGGER.error(error_msg)
                await listener.on_download_error(error_msg)
                return

            if folder_listener.node is None:
                error_msg = "Failed to retrieve MEGA folder node for clone"
                LOGGER.error(error_msg)
                await listener.on_download_error(error_msg)
                return

            # Get the folder node directly
            node = folder_listener.node

            # Calculate actual folder size (MEGA often reports wrong size for folders)
            folder_size = node.getSize()
            if folder_size == 4294967295:  # MEGA's "unknown size" value
                # Try to calculate actual size by iterating through children
                try:
                    children = folder_api.getChildren(node)
                    if children:
                        calculated_size = 0
                        child_count = children.size()
                        for i in range(child_count):
                            child = children.get(i)
                            if child:
                                calculated_size += child.getSize()
                        folder_size = calculated_size
                except Exception as e:
                    LOGGER.warning(
                        f"Could not calculate folder size: {e}, using reported size"
                    )

    except Exception as e:
        error_msg = f"Error accessing MEGA for clone: {e!s}"
        LOGGER.error(error_msg)
        await listener.on_download_error(error_msg)
        await _cleanup_mega_clone_api(api, executor, mega_listener)
        return

    # Set name and size based on the node
    # Preserve the original folder name from the MEGA link, not the SDK default
    original_folder_name = node.getName()
    listener.name = listener.name or original_folder_name
    listener.size = folder_size if "folder_size" in locals() else node.getSize()

    # Store the original name for later use in upload
    listener.original_mega_name = original_folder_name

    gid = token_hex(4)

    # Check if clone should be queued
    added_to_queue, event = await check_running_tasks(listener)
    if added_to_queue:
        LOGGER.info(f"MEGA clone added to queue: {listener.name}")
        async with task_dict_lock:
            task_dict[listener.mid] = QueueStatus(listener, gid, "cl")
        await listener.on_download_start()
        await send_status_message(listener.message)
        await event.wait()
        async with task_dict_lock:
            if listener.mid not in task_dict:
                LOGGER.info("MEGA clone was cancelled while in queue")
                await _cleanup_mega_clone_api(api, executor)
                return
        from_queue = True
        LOGGER.info(f"Starting queued MEGA clone: {listener.name}")
    else:
        from_queue = False

    # Create clone status tracker
    async with task_dict_lock:
        task_dict[listener.mid] = MegaCloneStatus(
            listener.name,
            listener.size,
            gid,
            mega_listener,
            listener.message,
            listener,
        )

    # Start the clone
    if from_queue:
        LOGGER.info(f"Resuming MEGA clone from queue: {listener.name}")
    else:
        await listener.on_download_start()
        await send_status_message(listener.message)
        LOGGER.info(f"Starting MEGA clone: {listener.name}")

    try:
        # MEGA SDK v4.8.0 has segmentation fault issues with copyNode and folder navigation
        # Fall back to download + upload immediately to prevent segfaults
        LOGGER.warning(
            "MEGA clone: Direct cloning disabled due to MEGA SDK segmentation fault issues"
        )
        LOGGER.info("MEGA clone: Falling back to download + upload method...")

        # Get the selected destination path for the fallback
        selected_clone_path = clone_path or (
            getattr(listener, "mega_clone_path", None)
            if hasattr(listener, "mega_clone_path")
            else None
        )

        # Cleanup current API instances before fallback to prevent segfaults
        await _cleanup_mega_clone_api(api, executor, mega_listener)

        # Fall back to download + upload with the selected destination path
        await _fallback_to_download_upload(listener, mega_link, selected_clone_path)
        return

    except Exception as e:
        error_msg = f"Error during MEGA clone: {e!s}"
        LOGGER.error(error_msg)

        # Check if this is a critical error that might cause segfault
        error_str = str(e).lower()
        if any(
            keyword in error_str
            for keyword in ["segmentation", "memory", "core", "signal", "abort"]
        ):
            LOGGER.critical(f"MEGA clone: Critical error detected - {error_msg}")
            error_msg = "❌ MEGA clone failed due to a critical system error. This may be due to MEGA SDK limitations or memory issues."

        await listener.on_download_error(error_msg)
    except:
        # Catch any other critical errors including segfaults
        critical_error = "❌ MEGA clone failed due to an unexpected critical error. This may be due to MEGA SDK limitations."
        LOGGER.critical("MEGA clone: Unexpected critical error occurred")
        try:
            await listener.on_download_error(critical_error)
        except:
            # If even error reporting fails, just log it
            LOGGER.critical("MEGA clone: Failed to report error to user")
    finally:
        # Always cleanup API connections with enhanced safety
        try:
            await _cleanup_mega_clone_api(api, executor, mega_listener)
            LOGGER.info("MEGA clone: Final cleanup completed")
        except Exception as cleanup_error:
            LOGGER.error(f"MEGA clone: Error during final cleanup: {cleanup_error}")
            # Force cleanup even if normal cleanup fails
            try:
                if api:
                    api = None
                if executor:
                    executor = None
                if mega_listener:
                    mega_listener = None
            except:
                pass
