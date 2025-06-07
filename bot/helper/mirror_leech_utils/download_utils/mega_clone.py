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

# Try to import MEGA SDK at module level, but don't fail if not available
try:
    from mega import MegaApi, MegaError, MegaListener, MegaRequest, MegaTransfer

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
                            LOGGER.info(
                                f"MEGA public node retrieved for clone: {self.__name} ({self.public_node.getSize()} bytes)"
                            )
                        else:
                            self.error = "Failed to get public node"
                            LOGGER.error("MEGA clone: Failed to get public node")
                    except Exception as e:
                        LOGGER.error(f"Failed to get public node: {e}")
                        self.error = f"Public node error: {e}"

                elif request_type == MegaRequest.TYPE_FETCH_NODES:
                    LOGGER.info("MEGA nodes fetched for clone, getting root node...")
                    try:
                        self.node = api.getRootNode()
                        if self.node:
                            LOGGER.info(
                                f"MEGA root node for clone: {self.node.getName()}"
                            )
                        else:
                            self.error = "Failed to get root node"
                            LOGGER.error("MEGA clone: Failed to get root node")
                    except Exception as e:
                        LOGGER.error(f"Failed to get root node: {e}")
                        self.error = f"Root node error: {e}"

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
                progress = (self.__bytes_transferred / total_bytes) * 100
                if progress % 10 < 0.1:  # Log every 10%
                    LOGGER.info(
                        f"MEGA clone progress: {progress:.1f}% ({self.__bytes_transferred}/{total_bytes} bytes)"
                    )

    def onTransferFinish(self, _api: MegaApi, transfer: MegaTransfer, error):
        try:
            if self.is_cancelled:
                LOGGER.info("MEGA clone transfer was cancelled")
                self.continue_event.set()
                return

            if str(error).lower() != "no error":
                error_msg = str(error)
                LOGGER.error(f"MEGA clone transfer finished with error: {error_msg}")
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
            LOGGER.info(
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
        LOGGER.info("Detecting MEGA account type for clone...")

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
                storage_used = account_details.getStorageUsed()
                storage_max = account_details.getStorageMax()
                transfer_used = account_details.getTransferOwnUsed()
                transfer_max = account_details.getTransferMax()

                is_premium = pro_level > 0

                if is_premium:
                    LOGGER.info(
                        f"🎉 MEGA Premium account detected for clone (Level {pro_level})"
                    )
                    LOGGER.info(f"📊 Storage: {storage_used}/{storage_max} bytes")
                    LOGGER.info(f"📊 Transfer: {transfer_used}/{transfer_max} bytes")
                    LOGGER.info(
                        "✅ Premium features enabled: parallel downloads, no bandwidth limits"
                    )
                else:
                    LOGGER.info("📱 MEGA Free account detected for clone")
                    LOGGER.info(f"📊 Storage: {storage_used}/{storage_max} bytes")
                    LOGGER.info(f"📊 Transfer: {transfer_used}/{transfer_max} bytes")
                    LOGGER.info(
                        "⚠️ Free account limitations: single downloads, bandwidth limited"
                    )

                return is_premium, _get_clone_premium_settings(is_premium)
            except Exception as e:
                LOGGER.debug(f"Error parsing clone account details: {e}")
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
                LOGGER.info(
                    f"Clone completion message sent to log chat: {Config.LOG_CHAT_ID}"
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

        LOGGER.info(f"Clone completion message sent for: {name}")

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


async def _cleanup_mega_clone_api(api, executor, listener=None):
    """Helper function to cleanup MEGA API instances"""
    try:
        if listener and api:
            try:
                api.removeListener(listener)
                LOGGER.info("MEGA clone listener removed")
            except Exception as e:
                LOGGER.error(f"Error removing MEGA clone listener: {e}")

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
                LOGGER.info("MEGA clone API logged out")
            except TimeoutError:
                LOGGER.warning(
                    "MEGA clone logout timed out after 120 seconds, but clone was successful"
                )
            except Exception as e:
                LOGGER.warning(
                    f"MEGA clone logout failed: {e}, but clone was successful"
                )
    except Exception as e:
        LOGGER.error(f"Error during MEGA clone API cleanup: {e}")


async def add_mega_clone(listener, mega_link):
    """
    Clone files/folders from MEGA.nz to MEGA account using the MEGA SDK v4.8.0.
    Performs direct MEGA-to-MEGA cloning without local downloading.

    Args:
        listener: Clone listener object
        mega_link: MEGA link to clone
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

    LOGGER.info("MEGA SDK v4.8.0 is available for clone")

    LOGGER.info(f"Starting MEGA clone: {mega_link}")

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
            LOGGER.info(
                f"MEGA API instance created successfully with key: {app_key}"
            )

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
            LOGGER.info("MEGA clone listener attached")
        except Exception as e:
            error_msg = f"Failed to attach MEGA listener: {e!s}"
            LOGGER.error(error_msg)
            await listener.on_download_error(error_msg)
            return

        # Login with credentials
        LOGGER.info("Logging into MEGA for clone...")
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
            is_premium, premium_settings = await _detect_mega_clone_account_type(api)
            LOGGER.info(
                f"MEGA clone account type detected: {'Premium' if is_premium else 'Free'}"
            )
        except Exception as e:
            LOGGER.warning(
                f"Could not detect account type for clone: {e}, using free account settings"
            )
            is_premium = False

        # Get public node to clone
        link_type = get_mega_link_type(mega_link)
        LOGGER.info(f"MEGA clone link type: {link_type}")

        LOGGER.info("Getting public node for clone...")
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
            error_msg = f"Failed to get MEGA node for clone: {mega_listener.error}"
            LOGGER.error(error_msg)
            await listener.on_download_error(error_msg)
            return

        if mega_listener.public_node is None:
            error_msg = "Failed to retrieve MEGA node for clone"
            LOGGER.error(error_msg)
            await listener.on_download_error(error_msg)
            return

        node = mega_listener.public_node

    except Exception as e:
        error_msg = f"Error accessing MEGA for clone: {e!s}"
        LOGGER.error(error_msg)
        await listener.on_download_error(error_msg)
        await _cleanup_mega_clone_api(api, executor, mega_listener)
        return

    # Set name and size based on the node
    listener.name = listener.name or node.getName()
    listener.size = node.getSize()

    gid = token_hex(4)
    LOGGER.info(
        f"MEGA clone info - Name: {listener.name}, Size: {listener.size} bytes"
    )

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
        # Get destination folder
        dest_folder = mega_listener.node  # Root by default
        if Config.MEGA_CLONE_TO_FOLDER:
            # TODO: Navigate to specific folder
            LOGGER.info(
                f"Using clone destination folder: {Config.MEGA_CLONE_TO_FOLDER}"
            )

        # Start the actual clone operation

        # Use copyNode with new name parameter for MEGA SDK v4.8.0
        await executor.do(api.copyNode, (node, dest_folder, listener.name))

        # Check if clone was successful
        if mega_listener.error:
            error_msg = f"MEGA clone failed: {mega_listener.error}"
            LOGGER.error(error_msg)
            await listener.on_download_error(error_msg)
            return

        # Generate public link if configured
        if Config.MEGA_UPLOAD_PUBLIC and mega_listener.cloned_node:
            cloned_node = api.getNodeByHandle(mega_listener.cloned_node)
            if cloned_node:
                await executor.do(api.exportNode, (cloned_node,))

        LOGGER.info(f"MEGA clone completed: {listener.name}")

        # Set executor event to signal completion and prevent timeout
        if executor and hasattr(executor, "continue_event"):
            executor.continue_event.set()

        # For clone operations, send completion message directly instead of calling on_download_complete
        # This prevents the system from treating it as a download operation
        await send_clone_completion_message(listener, mega_listener)

    except Exception as e:
        error_msg = f"Error during MEGA clone: {e!s}"
        LOGGER.error(error_msg)
        await listener.on_download_error(error_msg)
    finally:
        # Always cleanup API connections
        await _cleanup_mega_clone_api(api, executor, mega_listener)
