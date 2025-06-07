#!/usr/bin/env python3
"""
MEGA Folder Selector
Similar to rclone folder selection but for MEGA drive
"""

import asyncio
from time import time

from bot.core.config_manager import Config
from bot.helper.ext_utils.bot_utils import sync_to_async
from bot.helper.ext_utils.db_handler import database
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.message_utils import (
    delete_message,
    edit_message,
    send_message,
)

# Try to import MEGA SDK at module level, but don't fail if not available
try:
    from mega import MegaApi, MegaError, MegaListener, MegaRequest

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

    class MegaError:
        pass

    MEGA_SDK_AVAILABLE = False
    MEGA_IMPORT_ERROR = str(e)

from bot import LOGGER

LIST_LIMIT = 10


class MegaFolderListener(MegaListener):
    """MEGA SDK listener for folder operations"""

    def __init__(self, continue_event):
        super().__init__()
        self.continue_event = continue_event
        self.error = None
        self.nodes_fetched = False

    def onRequestFinish(self, api, request, error):
        """Called when a request finishes - with exception handling to prevent SWIG errors"""
        try:
            if error.getErrorCode() != 0:
                self.error = error.getErrorString()
                LOGGER.error(f"MEGA request error: {self.error}")
            elif request.getType() == MegaRequest.TYPE_LOGIN:
                LOGGER.info("MEGA login successful")
            elif request.getType() == MegaRequest.TYPE_FETCH_NODES:
                self.nodes_fetched = True

            self.continue_event.set()
        except Exception as e:
            # Critical: Prevent any exceptions from propagating back to C++
            # This prevents SWIG DirectorMethodException
            try:
                LOGGER.error(f"Exception in MEGA folder listener callback: {e}")
                self.error = f"Listener callback error: {e!s}"
                self.continue_event.set()
            except Exception:
                # Last resort: even logging failed, just set the event
                pass


class AsyncMegaExecutor:
    """Async executor for MEGA operations"""

    def __init__(self):
        self.continue_event = asyncio.Event()

    async def do(self, function, args=(), timeout=None):
        """Execute MEGA function asynchronously with improved error handling and retry logic"""
        function_name = getattr(function, "__name__", str(function))

        # Try multiple attempts with increasing timeouts for login operations only
        max_attempts = 3 if function_name == "login" else 1
        base_timeout = timeout

        for attempt in range(max_attempts):
            if timeout is not None:
                current_timeout = base_timeout + (
                    attempt * 30
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


class MegaFolderSelector:
    """MEGA folder selector similar to rclone's interface"""

    def __init__(self, listener):
        self.listener = listener
        self.user_id = listener.user_id
        self.api = None
        self.mega_listener = None
        self.executor = AsyncMegaExecutor()
        self.current_node_handle = None
        self.folder_list = []
        self.iter_start = 0
        self.path = ""
        self.path_node_handles = []  # Stack of node handles for navigation
        self.event = asyncio.Event()
        self.reply_to = None
        self.query_proc = False
        self._timeout = 240
        self._time = time()

    async def get_mega_path(self):
        """Get MEGA folder path for upload"""
        # Check if MEGA operations are enabled
        if not Config.MEGA_ENABLED:
            return "❌ MEGA.nz operations are disabled by the administrator."

        # Check if MEGA SDK is available
        if not MEGA_SDK_AVAILABLE:
            error_msg = (
                "❌ MEGA SDK v4.8.0 not available. Please install megasdk v4.8.0."
            )
            if MEGA_IMPORT_ERROR:
                error_msg += f"\nImport error: {MEGA_IMPORT_ERROR}"
            return error_msg

        # Get MEGA credentials
        user_dict = await database.get_user_doc(self.user_id)

        user_mega_email = user_dict.get("MEGA_EMAIL")
        user_mega_password = user_dict.get("MEGA_PASSWORD")

        if user_mega_email and user_mega_password:
            MEGA_EMAIL = user_mega_email
            MEGA_PASSWORD = user_mega_password
            LOGGER.info("Using user MEGA credentials for folder selection")
        else:
            MEGA_EMAIL = Config.MEGA_EMAIL
            MEGA_PASSWORD = Config.MEGA_PASSWORD
            LOGGER.info("Using owner MEGA credentials for folder selection")

        if not MEGA_EMAIL or not MEGA_PASSWORD:
            return "❌ MEGA.nz credentials not configured. Please set MEGA_EMAIL and MEGA_PASSWORD in user settings or contact the administrator."

        # Show initial progress message
        progress_msg = await send_message(
            self.listener.message,
            "🔄 <b>Initializing MEGA folder selection...</b>\n\n"
            "⏳ Connecting to MEGA.nz...\n"
            "📡 This may take up to 3 minutes for large accounts.\n"
            "🔄 Using enhanced retry logic for better reliability.",
        )

        try:
            # Register this selector globally
            global active_mega_selectors
            active_mega_selectors[self.user_id] = self

            # Initialize MEGA API with custom timeout settings
            self.api = MegaApi(None, None, None, "aimleechbot")

            # Try to set MEGA SDK timeouts if available
            try:
                # Set connection timeout to 180 seconds if method exists
                if hasattr(self.api, "setConnectTimeout"):
                    self.api.setConnectTimeout(180)
                if hasattr(self.api, "setRequestTimeout"):
                    self.api.setRequestTimeout(180)
                # Try additional timeout methods
                if hasattr(self.api, "setTimeout"):
                    self.api.setTimeout(180)
                if hasattr(self.api, "setMaxConnections"):
                    self.api.setMaxConnections(6)  # Reduce concurrent connections
            except Exception as timeout_error:
                LOGGER.warning(f"Could not set MEGA SDK timeouts: {timeout_error}")

            self.mega_listener = MegaFolderListener(self.executor.continue_event)
            self.api.addListener(self.mega_listener)

            # Update progress - Login
            await edit_message(
                progress_msg,
                "🔄 <b>Initializing MEGA folder selection...</b>\n\n"
                "🔐 Logging into MEGA account...\n"
                "📡 This may take up to 2 minutes for large accounts.",
            )

            # Login to MEGA with increased timeout
            try:
                await self.executor.do(
                    self.api.login, (MEGA_EMAIL, MEGA_PASSWORD), timeout=60
                )
            except Exception as login_error:
                LOGGER.error(f"MEGA login failed: {login_error}")
                await delete_message(progress_msg)
                if "timed out" in str(login_error).lower():
                    return "❌ MEGA login timed out. Please check your internet connection and try again."
                return f"❌ MEGA login failed: {login_error!s}"

            if self.mega_listener.error:
                await delete_message(progress_msg)
                return f"❌ MEGA login failed: {self.mega_listener.error}"

            # Update progress - Fetch nodes
            await edit_message(
                progress_msg,
                "🔄 <b>Initializing MEGA folder selection...</b>\n\n"
                "✅ Login successful!\n"
                "📁 Fetching folder structure...\n"
                "📡 This may take longer for accounts with many files.",
            )

            # Fetch nodes with increased timeout
            try:
                await self.executor.do(self.api.fetchNodes, timeout=90)
            except Exception as fetch_error:
                LOGGER.error(f"MEGA node fetching failed: {fetch_error}")
                await delete_message(progress_msg)
                if "timed out" in str(fetch_error).lower():
                    return "❌ MEGA node fetching timed out. Your MEGA account may have many files. Please try again."
                return f"❌ Failed to fetch MEGA nodes: {fetch_error!s}"

            if self.mega_listener.error:
                await delete_message(progress_msg)
                return f"❌ Failed to fetch MEGA nodes: {self.mega_listener.error}"

            if not self.mega_listener.nodes_fetched:
                await delete_message(progress_msg)
                return "❌ Failed to fetch MEGA nodes"

            # Start from root
            root_node = self.api.getRootNode()
            if not root_node:
                await delete_message(progress_msg)
                return "❌ Could not access MEGA root folder"

            # Store root node handle instead of the node object
            self.current_node_handle = root_node.getHandle()

            # Delete progress message and show folder selection interface
            await delete_message(progress_msg)
            await self.list_folders()
            await self._event_handler()

            if self.listener.is_cancelled:
                return None

            # Return selected path
            return self.path

        except Exception as e:
            LOGGER.error(f"MEGA folder selection error: {e}")
            # Clean up progress message if it exists
            try:
                if "progress_msg" in locals():
                    await delete_message(progress_msg)
            except:
                pass
            return f"❌ Folder selection failed: {e!s}"
        finally:
            # Clean up
            if self.user_id in active_mega_selectors:
                del active_mega_selectors[self.user_id]
            if self.api and self.mega_listener:
                try:
                    self.api.removeListener(self.mega_listener)
                except Exception as cleanup_error:
                    LOGGER.warning(
                        f"Error during MEGA listener cleanup: {cleanup_error}"
                    )
            # Clear references to prevent memory leaks
            self.current_node_handle = None
            self.path_node_handles = []
            self.folder_list = []

    async def list_folders(self):
        """List folders in current directory"""
        try:
            # Get current node from handle
            current_node = self.api.getNodeByHandle(self.current_node_handle)
            if not current_node:
                await self._send_list_message(
                    "❌ Error: Could not access current folder"
                )
                return

            # Get children of current node
            children = await sync_to_async(self.api.getChildren, current_node)
            self.folder_list = []

            if children:
                for i in range(children.size()):
                    child = children.get(i)
                    if child and child.isFolder() and not child.isRemoved():
                        folder_info = {
                            "Name": child.getName() or f"Folder_{i}",
                            "Handle": child.getHandle(),  # Store handle instead of node
                            "IsDir": True,
                            "Size": 0,  # Folders don't have size
                        }
                        self.folder_list.append(folder_info)

            # Sort folders by name
            self.folder_list.sort(key=lambda x: x["Name"].lower())
            await self.get_path_buttons()

        except Exception as e:
            LOGGER.error(f"Error listing MEGA folders: {e}")
            await self._send_list_message(f"❌ Error listing folders: {e!s}")

    async def get_path_buttons(self):
        """Generate folder selection buttons"""
        items_no = len(self.folder_list)
        pages = (items_no + LIST_LIMIT - 1) // LIST_LIMIT
        if items_no <= self.iter_start:
            self.iter_start = 0
        elif self.iter_start < 0 or self.iter_start > items_no:
            self.iter_start = LIST_LIMIT * (pages - 1)
        page = (self.iter_start / LIST_LIMIT) + 1 if self.iter_start != 0 else 1

        buttons = ButtonMaker()

        # Add folder buttons
        for index, folder in enumerate(
            self.folder_list[self.iter_start : LIST_LIMIT + self.iter_start]
        ):
            orig_index = index + self.iter_start
            name = folder["Name"]
            buttons.data_button(f"📁 {name}", f"mgq fo {orig_index}")

        # Navigation buttons
        if items_no > LIST_LIMIT:
            if self.iter_start != 0:
                buttons.data_button("⬅️", "mgq pre", position="footer")
            buttons.data_button(f"{page}/{pages}", "mgq ref", position="footer")
            if self.iter_start + LIST_LIMIT < items_no:
                buttons.data_button("➡️", "mgq nex", position="footer")

        # Action buttons
        buttons.data_button("✅ Choose Current Folder", "mgq cur", position="footer")

        if self.path_node_handles:  # If not at root
            buttons.data_button("⬆️ Back", "mgq back", position="footer")

        buttons.data_button("🏠 Root", "mgq root", position="footer")
        buttons.data_button("❌ Cancel", "mgq cancel", position="footer")

        button = buttons.build_menu(f_cols=1)

        # Create message text
        msg = "📁 <b>Choose MEGA Upload Folder:</b>\n\n"
        msg += f"📍 Current Path: <code>/{self.path}</code>\n"
        msg += f"📊 Folders: {items_no}\n"
        if pages > 1:
            msg += f"📄 Page: {page}/{pages}\n"
        msg += f"⏰ Timeout: {self._timeout - (time() - self._time):.0f}s\n\n"

        if items_no == 0:
            msg += "📂 This folder is empty or contains no subfolders.\n"
            msg += "You can choose this folder for upload or go back."
        else:
            msg += "Select a folder to navigate into, or choose current folder for upload."

        await self._send_list_message(msg, button)

    async def _send_list_message(self, msg, button=None):
        """Send or edit the folder selection message"""
        if self.reply_to is None:
            self.reply_to = await send_message(self.listener.message, msg, button)
        else:
            await edit_message(self.reply_to, msg, button)

    async def _event_handler(self):
        """Handle folder selection events"""
        while not self.event.is_set():
            if time() - self._time > self._timeout:
                self.event.set()
                if self.reply_to:
                    await delete_message(self.reply_to)
                await send_message(
                    self.listener.message, "⏰ Folder selection timed out!"
                )
                self.path = None  # Indicate timeout/cancellation
                break
            await asyncio.sleep(0.5)


# Global dictionary to store active selectors
active_mega_selectors = {}


async def mega_folder_callback(_, query):
    """Handle MEGA folder selection callbacks"""
    user_id = query.from_user.id
    message = query.message
    data = query.data.split()

    # Find the active selector for this user
    if user_id not in active_mega_selectors:
        await query.answer("❌ No active folder selection session found!")
        return

    selector = active_mega_selectors[user_id]

    if selector.query_proc:
        await query.answer("⏳ Processing previous request...")
        return

    selector.query_proc = True

    # Add timeout protection for callback operations
    callback_timeout = 30  # 30 seconds timeout for callback operations

    try:
        # Wrap all operations in a timeout to prevent hanging
        await asyncio.wait_for(
            _handle_callback_operation(selector, data, query, message),
            timeout=callback_timeout,
        )
    except TimeoutError:
        LOGGER.error(
            f"MEGA folder callback timed out after {callback_timeout} seconds - OPERATION FAILED"
        )
        await query.answer("❌ Operation timed out!")
    except Exception as e:
        LOGGER.error(f"Error in MEGA folder callback: {e}")
        await query.answer(f"❌ Error: {e!s}")
    finally:
        selector.query_proc = False


async def _handle_callback_operation(selector, data, query, message):
    """Handle the actual callback operation with proper error handling"""
    try:
        if data[1] == "fo":  # Folder navigation
            index = int(data[2])
            if index < len(selector.folder_list):
                folder = selector.folder_list[index]
                # Validate the node handle before using it
                node_handle = folder.get("Handle")
                if node_handle is None:
                    await query.answer("❌ Invalid folder selection!")
                    return

                # Verify the node still exists
                test_node = selector.api.getNodeByHandle(node_handle)
                if not test_node:
                    await query.answer("❌ Folder no longer exists!")
                    await selector.list_folders()  # Refresh the list
                    return

                # Store current node handle before navigating
                selector.path_node_handles.append(selector.current_node_handle)
                selector.current_node_handle = node_handle
                selector.path += (
                    f"/{folder['Name']}" if selector.path else folder["Name"]
                )
                selector.iter_start = 0
                await selector.list_folders()
            await query.answer("📁 Navigated to folder")
        elif data[1] == "back":  # Go back
            if selector.path_node_handles:
                selector.path_node_handles.pop()
                if selector.path_node_handles:
                    # Validate the parent node handle
                    parent_handle = selector.path_node_handles[-1]
                    parent_node = selector.api.getNodeByHandle(parent_handle)
                    if parent_node:
                        selector.current_node_handle = parent_handle
                    else:
                        # Parent node is invalid, go to root
                        root_node = selector.api.getRootNode()
                        if root_node:
                            selector.current_node_handle = root_node.getHandle()
                            selector.path_node_handles = []
                else:
                    # Go back to root
                    root_node = selector.api.getRootNode()
                    if root_node:
                        selector.current_node_handle = root_node.getHandle()
                # Update path
                if selector.path_node_handles:
                    path_parts = selector.path.split("/")
                    selector.path = "/".join(path_parts[:-1])
                else:
                    selector.path = ""
                selector.iter_start = 0
                await selector.list_folders()
        elif data[1] == "root":  # Go to root
            root_node = selector.api.getRootNode()
            if root_node:
                selector.current_node_handle = root_node.getHandle()
            selector.path_node_handles = []
            selector.path = ""
            selector.iter_start = 0
            await selector.list_folders()
        elif data[1] == "cur":  # Choose current folder
            await query.answer("✅ Folder selected!")
            await delete_message(message)
            selector.event.set()
        elif data[1] == "cancel":  # Cancel selection
            await query.answer("❌ Selection cancelled!")
            await delete_message(message)
            selector.path = None
            selector.event.set()
        elif data[1] == "pre":  # Previous page
            selector.iter_start -= LIST_LIMIT
            await selector.get_path_buttons()
        elif data[1] == "nex":  # Next page
            selector.iter_start += LIST_LIMIT
            await selector.get_path_buttons()
        elif data[1] == "ref":  # Refresh
            await selector.get_path_buttons()
        else:
            await query.answer("❌ Unknown action!")
    except Exception as e:
        LOGGER.error(f"Error in callback operation: {e}")
        await query.answer(f"❌ Error: {e!s}")
