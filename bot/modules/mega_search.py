#!/usr/bin/env python3
"""
MEGA Search Command Handler
Search through MEGA drive and provide download links
"""

import asyncio
from asyncio import create_task

from bot.core.config_manager import Config
from bot.helper.ext_utils.bot_utils import (
    get_telegraph_list,
    sync_to_async,
)
from bot.helper.ext_utils.status_utils import get_readable_file_size
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    delete_links,
    edit_message,
    send_message,
)

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
        TYPE_SEARCH = 3

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
        TYPE_SEARCH = 3

    class MegaTransfer:
        pass

    class MegaError:
        pass

    MEGA_SDK_AVAILABLE = False
    MEGA_IMPORT_ERROR = str(e)

from bot import LOGGER


class MegaSearchListener(MegaListener):
    """MEGA SDK listener for search operations"""

    def __init__(self, continue_event):
        super().__init__()
        self.continue_event = continue_event
        self.error = None
        self.temp_error = None
        self.search_results = []
        self.nodes_fetched = False

    def onRequestFinish(self, api, request, error):
        """Called when a request finishes - with exception handling to prevent SWIG errors"""
        try:
            if error.getErrorCode() != 0:
                # Handle MEGA error with proper signature
                error_code = error.getErrorCode()
                try:
                    # Try the static method first (most common in MEGA SDK v4.8.0)
                    if hasattr(error, "getErrorString") and callable(
                        error.getErrorString
                    ):
                        # Try instance method first
                        self.error = error.getErrorString()
                    else:
                        # Try static method with error code
                        from mega import MegaError

                        self.error = MegaError.getErrorString(error_code)
                except Exception:
                    # Fallback to error code only
                    self.error = f"MEGA Error Code: {error_code}"

                # Classify error severity based on error code
                if error_code == -1:
                    # Error code -1 is typically a temporary network/connection issue
                    # Log as INFO since these are usually automatically retried and succeed
                    LOGGER.info(
                        f"MEGA temporary connection issue (will retry): {self.error}"
                    )
                    # Don't treat temporary errors as permanent failures
                    self.temp_error = self.error
                elif error_code in [-2, -3, -4, -5]:
                    # These are also typically temporary errors
                    LOGGER.warning(
                        f"MEGA temporary error (will retry): {self.error}"
                    )
                    # Don't treat temporary errors as permanent failures
                    self.temp_error = self.error
                else:
                    # Other error codes are more serious
                    LOGGER.error(f"MEGA request error: {self.error}")
            else:
                request_type = request.getType()

                if request_type == MegaRequest.TYPE_LOGIN:
                    LOGGER.info("MEGA login successful")
                    # Clear any temporary errors after successful login
                    if hasattr(self, "temp_error"):
                        self.error = None
                elif request_type == MegaRequest.TYPE_FETCH_NODES:
                    self.nodes_fetched = True
                    # Clear any temporary errors after successful node fetching
                    if hasattr(self, "temp_error"):
                        self.error = None
                # Note: Search results are handled differently in MEGA SDK
                # The search method returns a MegaNodeList directly, not through request

            self.continue_event.set()
        except Exception as e:
            # Critical: Prevent any exceptions from propagating back to C++
            # This prevents SWIG DirectorMethodException
            try:
                LOGGER.error(f"Exception in MEGA listener callback: {e}")
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


class MegaSearchHandler:
    """Handle MEGA search operations"""

    def __init__(self, message, query):
        self.message = message
        self.query = query
        self.user_id = message.from_user.id
        self.results = []

    async def _manual_search(self, api, root_node, query):
        """Manual search through MEGA drive when API search fails"""
        try:
            results = []
            query_lower = query.lower()

            # Get all children recursively
            await self._search_node_recursive(api, root_node, query_lower, results)

            return results
        except Exception:
            return []

    async def _search_node_recursive(
        self, api, node, query_lower, results, depth=0, max_depth=10
    ):
        """Recursively search through MEGA nodes"""
        try:
            # Prevent infinite recursion
            if depth > max_depth:
                return

            # Check current node name
            node_name = node.getName() if node.getName() else ""
            if query_lower in node_name.lower():
                results.append(node)

            # If it's a folder, search its children
            if node.isFolder():
                try:
                    children = await sync_to_async(api.getChildren, node)
                    if children:
                        for i in range(children.size()):
                            child = children.get(i)
                            if child:
                                await self._search_node_recursive(
                                    api,
                                    child,
                                    query_lower,
                                    results,
                                    depth + 1,
                                    max_depth,
                                )
                except Exception:
                    pass  # Ignore folder access errors

        except Exception:
            pass  # Ignore node processing errors

    async def search(self):
        """Perform MEGA search"""
        # Check if MEGA operations are enabled
        if not Config.MEGA_ENABLED:
            await send_message(
                self.message,
                "❌ MEGA.nz operations are disabled by the administrator.",
            )
            return

        # Check if MEGA SDK is available
        if not MEGA_SDK_AVAILABLE:
            error_msg = (
                "❌ MEGA SDK v4.8.0 not available. Please install megasdk v4.8.0."
            )
            if MEGA_IMPORT_ERROR:
                error_msg += f"\nImport error: {MEGA_IMPORT_ERROR}"
            await send_message(self.message, error_msg)
            return

        # Get MEGA credentials
        from bot.helper.ext_utils.db_handler import database

        user_dict = await database.get_user_doc(self.user_id)

        user_mega_email = user_dict.get("MEGA_EMAIL")
        user_mega_password = user_dict.get("MEGA_PASSWORD")

        if user_mega_email and user_mega_password:
            MEGA_EMAIL = user_mega_email
            MEGA_PASSWORD = user_mega_password
        else:
            MEGA_EMAIL = Config.MEGA_EMAIL
            MEGA_PASSWORD = Config.MEGA_PASSWORD

        if not MEGA_EMAIL or not MEGA_PASSWORD:
            await send_message(
                self.message,
                "❌ MEGA.nz credentials not configured. Please set MEGA_EMAIL and MEGA_PASSWORD in user settings or contact the administrator.",
            )
            return

        # Show searching message
        search_msg = await send_message(
            self.message,
            f"🔍 Searching MEGA drive for: <code>{self.query}</code>\n\n"
            "⏳ Please wait...",
        )

        executor = AsyncMegaExecutor()
        api = None
        mega_listener = None

        try:
            # Initialize MEGA API with custom timeout settings
            api = MegaApi(None, None, None, "aimleechbot")

            # Try to set MEGA SDK timeouts if available
            try:
                # Set connection timeout to 180 seconds if method exists
                if hasattr(api, "setConnectTimeout"):
                    api.setConnectTimeout(180)
                if hasattr(api, "setRequestTimeout"):
                    api.setRequestTimeout(180)
                # Try additional timeout methods
                if hasattr(api, "setTimeout"):
                    api.setTimeout(180)
                if hasattr(api, "setMaxConnections"):
                    api.setMaxConnections(6)  # Reduce concurrent connections
            except Exception as timeout_error:
                LOGGER.warning(f"Could not set MEGA SDK timeouts: {timeout_error}")

            mega_listener = MegaSearchListener(executor.continue_event)
            api.addListener(mega_listener)

            # Login to MEGA with increased timeout
            try:
                await executor.do(api.login, (MEGA_EMAIL, MEGA_PASSWORD), timeout=60)
            except Exception as login_error:
                LOGGER.error(f"MEGA login failed: {login_error}")
                if "timed out" in str(login_error).lower():
                    await edit_message(
                        search_msg,
                        "❌ MEGA login timed out. Please check your internet connection and try again.",
                    )
                else:
                    await edit_message(
                        search_msg, f"❌ MEGA login failed: {login_error!s}"
                    )
                return

            if mega_listener.error:
                await edit_message(
                    search_msg, f"❌ MEGA login failed: {mega_listener.error}"
                )
                return

            # Fetch nodes with increased timeout
            try:
                await executor.do(api.fetchNodes, timeout=90)

                # Additional verification - wait a bit for listener to process
                await asyncio.sleep(0.5)

                # Force check if nodes are available
                try:
                    root_node_check = api.getRootNode()
                    if root_node_check:
                        mega_listener.nodes_fetched = True  # Ensure flag is set
                except Exception:
                    pass  # Ignore verification errors

            except Exception as fetch_error:
                if "timed out" in str(fetch_error).lower():
                    await edit_message(
                        search_msg,
                        "❌ MEGA node fetching timed out. Your MEGA account may have many files. Please try again.",
                    )
                else:
                    await edit_message(
                        search_msg, f"❌ Failed to fetch MEGA nodes: {fetch_error!s}"
                    )
                return

            # Check if node fetching actually succeeded despite temporary errors
            if mega_listener.error and not mega_listener.nodes_fetched:
                # Only treat as error if nodes weren't fetched AND there's a non-temporary error
                error_str = str(mega_listener.error).lower()
                if "error code: -1" not in error_str:
                    # This is a real error, not a temporary connection issue
                    await edit_message(
                        search_msg,
                        f"❌ Failed to fetch MEGA nodes: {mega_listener.error}",
                    )
                    return

            if not mega_listener.nodes_fetched:
                # Try to get root node as a fallback check
                try:
                    root_node_test = api.getRootNode()
                    if root_node_test:
                        mega_listener.nodes_fetched = True  # Manually set the flag
                    else:
                        await edit_message(
                            search_msg, "❌ Failed to fetch MEGA nodes"
                        )
                        return
                except Exception:
                    await edit_message(search_msg, "❌ Failed to fetch MEGA nodes")
                    return

            # Perform search
            root_node = api.getRootNode()
            if not root_node:
                await edit_message(
                    search_msg, "❌ Could not access MEGA root folder"
                )
                return

            # MEGA search returns results directly, not through listener
            try:
                # Update search message to show progress
                await edit_message(
                    search_msg,
                    f"🔍 Searching MEGA drive for: <code>{self.query}</code>\n\n"
                    "🔄 Searching through files and folders...",
                )

                # Try different search methods as MEGA SDK can be inconsistent
                # Method 1: Try the standard search with recursive flag
                try:
                    node_list = await sync_to_async(
                        api.search, root_node, self.query, True
                    )
                except Exception:
                    node_list = None

                # Method 2: If standard search fails, try without recursive flag
                if not node_list or (
                    hasattr(node_list, "size") and node_list.size() == 0
                ):
                    try:
                        node_list = await sync_to_async(
                            api.search, root_node, self.query
                        )
                    except Exception:
                        node_list = None

                # Method 3: If both fail, try manual traversal search
                if not node_list or (
                    hasattr(node_list, "size") and node_list.size() == 0
                ):
                    node_list = await self._manual_search(api, root_node, self.query)

                if node_list and hasattr(node_list, "size") and node_list.size() > 0:
                    for i in range(node_list.size()):
                        node = node_list.get(i)
                        if node:
                            self.results.append(node)
                elif isinstance(node_list, list) and len(node_list) > 0:
                    # Handle case where manual search returns a list
                    for node in node_list:
                        if node:
                            self.results.append(node)

            except Exception as search_error:
                await edit_message(
                    search_msg, f"❌ MEGA search failed: {search_error!s}"
                )
                return

            if not self.results:
                await edit_message(
                    search_msg,
                    f"🔍 Search completed for: <code>{self.query}</code>\n\n"
                    "❌ No results found.",
                )
                return

            # Display all results like Google Drive search
            await self.display_all_results(search_msg, api)

        except Exception as e:
            LOGGER.error(f"MEGA search error: {e}")
            await edit_message(search_msg, f"❌ Search failed: {e!s}")
        finally:
            if api and mega_listener:
                api.removeListener(mega_listener)

    async def display_all_results(self, message, api):
        """Display all search results like Google Drive search using Telegraph"""
        total_results = len(self.results)

        # Build HTML content for Telegraph (similar to Google Drive search)
        telegraph_content = []
        msg = f"<h4>🔍 MEGA Search Results for: {self.query}</h4><br>"
        msg += f"📊 Found <b>{total_results}</b> results<br><br>"

        contents_no = 0

        for i, node in enumerate(self.results):
            try:
                name = node.getName() or f"Unknown_{i}"
                size = node.getSize()
                is_folder = node.isFolder()

                # Get public link
                link = None
                try:
                    if node.isExported():
                        link = node.getPublicLink()
                    else:
                        # Try to export the node for public access
                        await sync_to_async(api.exportNode, node)
                        # Wait a bit for export to complete
                        await asyncio.sleep(0.5)
                        link = node.getPublicLink()
                except Exception as link_error:
                    LOGGER.warning(
                        f"Could not get public link for {name}: {link_error}"
                    )
                    # Try to get a direct download link if possible
                    try:
                        link = await sync_to_async(api.getNodePath, node)
                        if link:
                            link = f"MEGA Path: {link}"
                    except Exception:
                        pass

                if is_folder:
                    msg += f"📁 <code>{name}<br>(folder)</code><br>"
                    if link:
                        msg += f"<b><a href='{link}'>MEGA Link</a></b>"
                    else:
                        msg += "<b>Link not available</b>"
                else:
                    size_str = get_readable_file_size(size)
                    msg += f"📄 <code>{name}<br>({size_str})</code><br>"
                    if link:
                        msg += f"<b><a href='{link}'>MEGA Link</a></b>"
                    else:
                        msg += "<b>Link not available</b>"

                msg += "<br><br>"
                contents_no += 1

                # Split into multiple Telegraph pages if content gets too long (like Google Drive)
                if len(msg.encode("utf-8")) > 39000:
                    telegraph_content.append(msg)
                    msg = ""

            except Exception as e:
                LOGGER.error(f"Error processing MEGA search result {i}: {e}")
                msg += f"❌ Error processing result {i + 1}<br><br>"

        # Add remaining content
        if msg != "":
            telegraph_content.append(msg)

        # Create Telegraph page(s) and display like Google Drive search
        if telegraph_content:
            try:
                button = await get_telegraph_list(telegraph_content)
                result_msg = f"<b>🔍 Found {contents_no} MEGA results for <i>{self.query}</i></b>"
                await edit_message(message, result_msg, button)
            except Exception as e:
                LOGGER.error(f"Error creating Telegraph page: {e}")
                # Fallback to simple text display
                simple_msg = f"🔍 <b>MEGA Search Results for:</b> <code>{self.query}</code>\n\n"
                simple_msg += f"📊 Found <b>{contents_no}</b> results\n\n"
                simple_msg += "❌ Could not create detailed view. Please try again."
                await edit_message(message, simple_msg)
        else:
            await edit_message(
                message, f"❌ No results found for <i>{self.query}</i>"
            )


# Pagination callbacks removed - MEGA search now shows all results like Google Drive


async def mega_search_command(_, message):
    """
    MEGA Search command handler

    Search through the entire MEGA drive and provide download links
    """
    # Check if MEGA operations are enabled
    if not Config.MEGA_ENABLED:
        await send_message(
            message, "❌ MEGA.nz operations are disabled by the administrator."
        )
        return

    # Parse command
    text = message.text.split()

    if len(text) < 2:
        # Show help message
        help_text = (
            "🔍 <b>MEGA Search Help</b>\n\n"
            "<b>Usage:</b> <code>/megasearch query</code>\n\n"
            "<b>Description:</b>\n"
            "Search through your entire MEGA drive for files and folders.\n"
            "Returns direct MEGA download links for found items.\n\n"
            "<b>Examples:</b>\n"
            "• <code>/megasearch movie</code> - Search for files containing 'movie'\n"
            "• <code>/megasearch .mp4</code> - Search for MP4 files\n"
            "• <code>/megasearch folder_name</code> - Search for specific folder\n\n"
            "<b>Note:</b> You need MEGA credentials configured to use this feature."
        )

        msg = await send_message(message, help_text)
        await delete_links(message)
        await auto_delete_message(msg, time=300)  # Auto-delete after 5 minutes
        return

    # Get search query
    query = " ".join(text[1:])

    # Create search handler and start search
    search_handler = MegaSearchHandler(message, query)

    # Delete the command message first
    await delete_links(message)

    # Start the search (no need to store task reference since we're not managing it)
    create_task(search_handler.search())
