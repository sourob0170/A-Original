#!/usr/bin/env python3
"""
MEGA Clone Command Handler
Dedicated command for MEGA-to-MEGA cloning operations
"""

from asyncio import create_task

from bot.core.config_manager import Config
from bot.helper.ext_utils.bot_utils import (
    arg_parser,
    new_task,
)
from bot.helper.ext_utils.links_utils import is_mega_link
from bot.helper.listeners.task_listener import TaskListener
from bot.helper.mirror_leech_utils.download_utils.mega_clone import add_mega_clone
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    delete_links,
    send_message,
)


class MegaClone(TaskListener):
    """MEGA Clone Task Listener"""

    def __init__(self, client, message, bulk=None, multi_tag=None, options=""):
        if bulk is None:
            bulk = []
        self.message = message
        self.client = client
        self.multi_tag = multi_tag
        self.options = options
        self.bulk = bulk
        super().__init__()

    @new_task
    async def new_event(self):
        """Handle new MEGA clone event"""
        text = self.message.text.split("\n")
        input_list = text[0].split(" ")

        # Parse arguments
        args = {
            "link": "",
            "-i": 0,
            "-b": False,
            "-n": "",
        }

        arg_parser(input_list[1:], args)

        try:
            self.multi = int(args["-i"])
        except Exception:
            self.multi = 0

        self.link = args["link"]
        self.name = args["-n"]

        # Validate MEGA link
        if not self.link:
            msg = await send_message(
                self.message,
                "❌ No MEGA link provided!\n\n"
                "<b>Usage:</b> <code>/megaclone MEGA_LINK</code>\n"
                "<b>Example:</b> <code>/megaclone https://mega.nz/file/ABC123</code>",
            )
            await delete_links(self.message)
            return await auto_delete_message(msg, time=300)

        if not is_mega_link(self.link):
            msg = await send_message(
                self.message,
                "❌ Invalid MEGA link!\n\n"
                "Please provide a valid MEGA.nz link.\n"
                "<b>Example:</b> <code>https://mega.nz/file/ABC123</code>",
            )
            await delete_links(self.message)
            return await auto_delete_message(msg, time=300)

        # Check if MEGA operations are enabled
        if not Config.MEGA_ENABLED:
            msg = await send_message(
                self.message,
                "❌ MEGA.nz operations are disabled by the administrator.",
            )
            await delete_links(self.message)
            return await auto_delete_message(msg, time=300)

        # Check if MEGA clone is enabled
        if not Config.MEGA_CLONE_ENABLED:
            msg = await send_message(
                self.message,
                "❌ MEGA clone operations are disabled by the administrator.",
            )
            await delete_links(self.message)
            return await auto_delete_message(msg, time=300)

        # Check if MEGA credentials are configured
        if not Config.MEGA_EMAIL or not Config.MEGA_PASSWORD:
            msg = await send_message(
                self.message,
                "❌ MEGA credentials not configured. Please contact the administrator.",
            )
            await delete_links(self.message)
            return await auto_delete_message(msg, time=300)

        # Set default name if not provided
        if not self.name:
            try:
                # Extract filename from MEGA link if possible
                if "/file/" in self.link:
                    self.name = "MEGA_File"
                elif "/folder/" in self.link:
                    self.name = "MEGA_Folder"
                else:
                    self.name = "MEGA_Clone"
            except Exception:
                self.name = "MEGA_Clone"

        # Check which MEGA account will be used and show folder selection if needed
        from bot.helper.ext_utils.db_handler import database

        user_dict = await database.get_user_doc(self.user_id)

        # Check for user MEGA credentials first, then fall back to owner credentials
        user_mega_email = user_dict.get("MEGA_EMAIL")
        user_mega_password = user_dict.get("MEGA_PASSWORD")

        has_user_credentials = user_mega_email and user_mega_password
        has_owner_credentials = Config.MEGA_EMAIL and Config.MEGA_PASSWORD

        # Determine which account will be used and check if folder selection is needed
        will_use_user_account = has_user_credentials
        will_use_owner_account = not has_user_credentials and has_owner_credentials

        show_folder_selection = False
        if will_use_user_account and not user_dict.get("MEGA_CLONE_TO_FOLDER"):
            # User account will be used but user hasn't set clone folder
            show_folder_selection = True
        elif will_use_owner_account and not Config.MEGA_CLONE_TO_FOLDER:
            # Owner account will be used but owner hasn't set clone folder
            show_folder_selection = True

        # Show MEGA folder selection if needed for the account that will be used
        if show_folder_selection:
            from bot.helper.mega_utils.folder_selector import MegaFolderSelector

            folder_selector = MegaFolderSelector(self)
            selected_path = await folder_selector.get_mega_path()

            if selected_path is None:
                # User cancelled
                return None
            if isinstance(selected_path, str) and selected_path.startswith("❌"):
                # Error occurred
                await send_message(self.message, selected_path)
                return None
            # Store selected path for this clone operation
            self.mega_clone_path = selected_path

        # Start MEGA clone operation
        await self.on_download_start()
        create_task(add_mega_clone(self, self.link))
        await delete_links(self.message)
        return None


async def mega_clone(client, message):
    """
    MEGA Clone command handler

    Clones files/folders directly from MEGA to MEGA account without downloading locally.
    This is faster and more efficient than downloading and re-uploading.
    """
    # Check if MEGA operations are enabled
    if not Config.MEGA_ENABLED:
        await send_message(
            message, "❌ MEGA.nz operations are disabled by the administrator."
        )
        return

    # Check if MEGA clone operations are enabled
    if not Config.MEGA_CLONE_ENABLED:
        await send_message(
            message, "❌ MEGA clone operations are disabled by the administrator."
        )
        return

    # Check if MEGA credentials are configured (user or owner)
    from bot.helper.ext_utils.db_handler import database

    user_id = message.from_user.id
    user_dict = await database.get_user_doc(user_id)

    user_mega_email = user_dict.get("MEGA_EMAIL")
    user_mega_password = user_dict.get("MEGA_PASSWORD")

    has_user_credentials = user_mega_email and user_mega_password
    has_owner_credentials = Config.MEGA_EMAIL and Config.MEGA_PASSWORD

    if not has_user_credentials and not has_owner_credentials:
        await send_message(
            message,
            "❌ MEGA credentials not configured. Please set your MEGA credentials in user settings or contact the administrator.",
        )
        return

    # Create MEGA clone task
    create_task(MegaClone(client, message).new_event())


# Handler registration is done in bot/core/handlers.py to avoid circular imports
