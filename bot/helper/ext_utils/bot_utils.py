import contextlib
import math
import os
from asyncio import (
    create_subprocess_exec,
    create_subprocess_shell,
    run_coroutine_threadsafe,
    sleep,
)
from asyncio.subprocess import PIPE
from base64 import urlsafe_b64decode, urlsafe_b64encode
from functools import partial, wraps

from httpx import AsyncClient

from bot import LOGGER, bot_loop, user_data
from bot.core.config_manager import Config
from bot.helper.telegram_helper.button_build import ButtonMaker

try:
    from bot.helper.ext_utils.gc_utils import smart_garbage_collection
except ImportError:
    smart_garbage_collection = None

from .help_messages import (
    AI_HELP_DICT,
    CLONE_HELP_DICT,
    FORWARD_HELP_DICT,
    GALLERY_DL_HELP_DICT,
    MIRROR_HELP_DICT,
    NSFW_HELP_DICT,
    PHISH_HELP_DICT,
    STREAMRIP_HELP_DICT,
    VT_HELP_DICT,
    YT_HELP_DICT,
    ZOTIFY_HELP_DICT,
)
from .telegraph_helper import telegraph

COMMAND_USAGE = {}


class SetInterval:
    def __init__(self, interval, action, *args, **kwargs):
        self.interval = interval
        self.action = action
        self.args = args
        self.kwargs = kwargs
        self._cancelled = False

        # Validate that action is callable
        if not callable(action):
            raise ValueError(f"Action must be callable, got {type(action)}")

        # Check if action is an async function
        import inspect

        if not inspect.iscoroutinefunction(action):
            raise ValueError(
                f"Action must be an async function, got {type(action).__name__}. Did you forget to add 'async' keyword?"
            )

        self.task = bot_loop.create_task(self._set_interval())

    async def _set_interval(self):
        try:
            while not self._cancelled:
                await sleep(self.interval)
                if self._cancelled:
                    break

                # Ensure action is still valid before calling
                if self.action is None:
                    LOGGER.error("SetInterval action became None, stopping interval")
                    break

                # Additional validation to prevent NoneType errors
                if not callable(self.action):
                    LOGGER.error(
                        f"SetInterval action is not callable: {type(self.action)}, stopping interval"
                    )
                    break

                try:
                    # Validate action is still a coroutine function
                    import inspect

                    if not inspect.iscoroutinefunction(self.action):
                        LOGGER.error(
                            f"SetInterval action is no longer a coroutine function: {type(self.action)}, stopping interval"
                        )
                        break

                    # Call the action with stored args and kwargs
                    result = self.action(*self.args, **self.kwargs)

                    # Ensure we have a coroutine to await
                    if result is None:
                        LOGGER.error(
                            "SetInterval action returned None instead of coroutine, stopping interval"
                        )
                        break

                    await result
                except Exception as e:
                    LOGGER.error(f"Error in SetInterval action: {e}", exc_info=True)
                    # Continue the loop unless it's a critical error
                    if "NoneType" in str(e) or "can't be used in 'await'" in str(e):
                        LOGGER.error(
                            "Critical error: action became None or invalid, stopping interval"
                        )
                        break
        except Exception as e:
            LOGGER.error(f"Critical error in SetInterval: {e}", exc_info=True)
        finally:
            self._cancelled = True

    def cancel(self):
        self._cancelled = True
        if hasattr(self, "task") and self.task:
            self.task.cancel()


def _build_command_usage(help_dict, command_key):
    buttons = ButtonMaker()
    for name in list(help_dict.keys())[1:]:
        buttons.data_button(name, f"help {command_key} {name}")
    buttons.data_button("Close", "help close")
    COMMAND_USAGE[command_key] = [help_dict["main"], buttons.build_menu(3)]
    buttons.reset()


def create_help_buttons():
    _build_command_usage(MIRROR_HELP_DICT, "mirror")
    _build_command_usage(YT_HELP_DICT, "yt")
    _build_command_usage(CLONE_HELP_DICT, "clone")
    _build_command_usage(AI_HELP_DICT, "ai")
    _build_command_usage(VT_HELP_DICT, "virustotal")
    _build_command_usage(PHISH_HELP_DICT, "phishcheck")
    _build_command_usage(NSFW_HELP_DICT, "nsfw")
    _build_command_usage(STREAMRIP_HELP_DICT, "streamrip")
    _build_command_usage(ZOTIFY_HELP_DICT, "zotify")
    _build_command_usage(GALLERY_DL_HELP_DICT, "gdl")
    _build_command_usage(FORWARD_HELP_DICT, "forward")


def bt_selection_buttons(id_):
    # Convert id_ to string before slicing
    id_str = str(id_)
    gid = id_str[:12] if len(id_str) > 25 else id_str
    # Convert id_ to string before extracting digits
    pin = "".join([n for n in id_str if n.isdigit()][:4])
    buttons = ButtonMaker()
    if Config.WEB_PINCODE:
        buttons.url_button("Select Files", f"{Config.BASE_URL}/app/files?gid={id_}")
        buttons.data_button("Pincode", f"sel pin {gid} {pin}")
    else:
        buttons.url_button(
            "Select Files",
            f"{Config.BASE_URL}/app/files?gid={id_}&pin={pin}",
        )
    buttons.data_button("Done Selecting", f"sel done {gid} {id_}")
    buttons.data_button("Cancel", f"sel cancel {gid}")
    return buttons.build_menu(2)


async def get_telegraph_list(telegraph_content):
    path = [
        (
            await telegraph.create_page(
                title="Mirror-Leech-Bot Drive Search",
                content=content,
            )
        )["path"]
        for content in telegraph_content
    ]
    if len(path) > 1:
        await telegraph.edit_telegraph(path, telegraph_content)
    buttons = ButtonMaker()
    buttons.url_button("🔎 VIEW", f"https://telegra.ph/{path[0]}")
    return buttons.build_menu(1)


def arg_parser(items, arg_base):
    if not items:
        return

    # Initialize -m flag if not present
    if "-m" not in arg_base:
        arg_base["-m"] = ""

    arg_start = -1
    i = 0
    total = len(items)

    bool_arg_set = {
        "-b",
        "-e",
        "-z",
        "-s",
        "-j",
        "-d",
        "-sv",
        "-ss",
        "-f",
        "-fd",
        "-fu",
        "-sync",
        "-hl",
        "-doc",
        "-med",
        "-ut",
        "-bt",
        "-es",
        "-compress",
        "-comp-video",
        "-comp-audio",
        "-comp-image",
        "-comp-document",
        "-comp-subtitle",
        "-comp-archive",
        "-video-fast",
        "-video-medium",
        "-video-slow",
        "-audio-fast",
        "-audio-medium",
        "-audio-slow",
        "-image-fast",
        "-image-medium",
        "-image-slow",
        "-document-fast",
        "-document-medium",
        "-document-slow",
        "-subtitle-fast",
        "-subtitle-medium",
        "-subtitle-slow",
        "-archive-fast",
        "-archive-medium",
        "-archive-slow",
        "-extract",
        "-extract-video",
        "-extract-audio",
        "-extract-subtitle",
        "-extract-attachment",
        "-extract-priority",
        "-remove",
        "-remove-video",
        "-remove-audio",
        "-remove-subtitle",
        "-remove-attachment",
        "-remove-metadata",
        "-add",
        "-add-video",
        "-add-audio",
        "-add-subtitle",
        "-add-subtitle-hardsub",
        "-add-attachment",
        "-del",
        "-preserve",
        "-replace",
        "-mt",
        # Gallery-dl flags
        "--archive",
        "--no-archive",
        "--metadata",
        "--no-metadata",
        "--write-info-json",
    }

    while i < total:
        part = items[i]
        if part in arg_base:
            if arg_start == -1:
                arg_start = i
            if (i + 1 == total and part in bool_arg_set) or part in [
                "-s",
                "-j",
                "-f",
                "-fd",
                "-fu",
                "-sync",
                "-hl",
                "-doc",
                "-med",
                "-ut",
                "-bt",
                "-es",
                "-compress",
                "-comp-video",
                "-comp-audio",
                "-comp-image",
                "-comp-document",
                "-comp-subtitle",
                "-comp-archive",
                "-video-fast",
                "-video-medium",
                "-video-slow",
                "-audio-fast",
                "-audio-medium",
                "-audio-slow",
                "-image-fast",
                "-image-medium",
                "-image-slow",
                "-document-fast",
                "-document-medium",
                "-document-slow",
                "-subtitle-fast",
                "-subtitle-medium",
                "-subtitle-slow",
                "-archive-fast",
                "-archive-medium",
                "-archive-slow",
                "-extract",
                "-extract-video",
                "-extract-audio",
                "-extract-subtitle",
                "-extract-attachment",
                "-remove",
                "-remove-video",
                "-remove-audio",
                "-remove-subtitle",
                "-remove-attachment",
                "-remove-metadata",
                "-add",
                "-add-video",
                "-add-audio",
                "-add-subtitle",
                "-add-subtitle-hardsub",
                "-add-attachment",
                "-swap",
                "-swap-audio",
                "-swap-video",
                "-swap-subtitle",
                "-del",
                "-preserve",
                "-replace",
                "-mt",
                "-hl",
                "-bt",
                "-ut",
                "-es",
                # Gallery-dl flags
                "--archive",
                "--no-archive",
                "--metadata",
                "--no-metadata",
                "--write-info-json",
            ]:
                arg_base[part] = True
            else:
                sub_list = []
                for j in range(i + 1, total):
                    if items[j] in arg_base:
                        if part in bool_arg_set and not sub_list:
                            arg_base[part] = True
                            break
                        if not sub_list:
                            break
                        check = " ".join(sub_list).strip()
                        if part == "-ff":
                            if check.startswith("[") and check.endswith("]"):
                                break
                        else:
                            break
                    sub_list.append(items[j])
                if sub_list:
                    value = " ".join(sub_list)
                    if part == "-ff":
                        # For -ff flag, if it's a direct command (not starting with '['),
                        # treat it as a direct command string, not a set
                        if not value.strip().startswith("["):
                            arg_base[part] = value
                        else:
                            # Only add to set if it's a key reference (starts with '[')
                            with contextlib.suppress(Exception):
                                arg_base[part].add(tuple(eval(value)))
                    else:
                        arg_base[part] = value
                    i += len(sub_list)
        i += 1
    if "link" in arg_base:
        link_items = items[:arg_start] if arg_start != -1 else items
        if link_items:
            arg_base["link"] = " ".join(link_items)


def get_size_bytes(size):
    size = size.lower()
    if "k" in size:
        size = int(float(size.split("k")[0]) * 1024)
    elif "m" in size:
        size = int(float(size.split("m")[0]) * 1048576)
    elif "g" in size:
        size = int(float(size.split("g")[0]) * 1073741824)
    elif "t" in size:
        size = int(float(size.split("t")[0]) * 1099511627776)
    else:
        size = 0
    return size


async def get_content_type(url):
    try:
        async with AsyncClient(follow_redirects=True, verify=False) as client:
            response = await client.head(url)
            if "Content-Type" not in response.headers:
                response = await client.get(url)
            return response.headers.get("Content-Type")
    except Exception:
        return None


def get_user_split_size(user_id, args, file_size, equal_splits=False):
    """
    Calculate the split size based on user settings, command arguments, and file size.
    User settings take priority over owner bot settings.
    Equal splits uses the configured leech split size as target but ensures equal parts.

    Args:
        user_id: User ID for retrieving user settings
        args: Command arguments that may override settings
        file_size: Size of the file to be split
        equal_splits: Whether to use equal splits calculation

    Returns:
        int: Calculated split size in bytes
        bool: Whether to skip splitting
    """
    from bot import user_data
    from bot.core.aeon_client import TgClient
    from bot.core.config_manager import Config

    user_dict = user_data.get(user_id, {})

    # Calculate max split size based on owner's USER_TRANSMISSION setting (matches old Aeon-MLTB logic)
    # USER_TRANSMISSION is owner setting only, not user-specific
    # If owner has USER_TRANSMISSION enabled and premium session, use 4GB limit, otherwise 2GB
    max_split_size = (
        TgClient.MAX_SPLIT_SIZE
        if Config.USER_TRANSMISSION and TgClient.IS_PREMIUM_USER
        else 2097152000
    )

    # Get the target split size from settings (respecting priority order)
    target_split_size = 0

    # Command args have highest priority (if args is provided)
    if args is not None and args.get("-sp"):
        split_arg = args.get("-sp")
        if split_arg.isdigit():
            target_split_size = int(split_arg)
        else:
            target_split_size = get_size_bytes(split_arg)
    # User settings have second priority
    elif user_dict.get("LEECH_SPLIT_SIZE"):
        target_split_size = user_dict.get("LEECH_SPLIT_SIZE")
    # Owner settings have third priority
    elif Config.LEECH_SPLIT_SIZE and max_split_size != Config.LEECH_SPLIT_SIZE:
        target_split_size = Config.LEECH_SPLIT_SIZE
    # Default to max split size if no custom size is set
    else:
        target_split_size = max_split_size

    # Ensure target split size doesn't exceed maximum allowed
    target_split_size = min(target_split_size, max_split_size)

    # If equal splits is enabled, calculate equal parts based on target split size
    if equal_splits:
        # For equal splits, always split if file is larger than target split size
        if file_size <= target_split_size:
            # File is smaller than or equal to target split size, no need to split
            return file_size, True

        # Calculate how many parts we need based on target split size
        parts = math.ceil(file_size / target_split_size)

        # Calculate equal split size
        equal_split_size = math.ceil(file_size / parts)

        # Ensure each part doesn't exceed max split size
        while equal_split_size > max_split_size:
            parts += 1
            equal_split_size = math.ceil(file_size / parts)

        # Add extra safety check - if we're close to the limit, add one more part
        safety_margin = 10 * 1024 * 1024  # 10 MiB
        if equal_split_size > (max_split_size - safety_margin):
            parts += 1
            equal_split_size = math.ceil(file_size / parts)

        # Log the equal split calculation
        from bot import LOGGER

        LOGGER.info(
            f"Equal splits: Target size: {target_split_size / (1024 * 1024):.1f} MiB, "
            f"File size: {file_size / (1024 * 1024):.2f} MiB, "
            f"Parts: {parts}, Equal split size: {equal_split_size / (1024 * 1024):.1f} MiB"
        )

        # Ensure the calculated equal split size is never greater than max split size
        equal_split_size = min(equal_split_size, max_split_size)

        # Always split when equal splits is enabled and file > target size
        return equal_split_size, False

    # For regular splitting (not equal splits):
    # Get split size from command args, user settings, or bot config (in that order)
    # This ensures custom split sizes set by user or owner get priority
    split_size = 0

    # Command args have highest priority (if args is provided)
    if args is not None and args.get("-sp"):
        split_arg = args.get("-sp")
        if split_arg.isdigit():
            split_size = int(split_arg)
        else:
            split_size = get_size_bytes(split_arg)
    # User settings have second priority
    elif user_dict.get("LEECH_SPLIT_SIZE"):
        split_size = user_dict.get("LEECH_SPLIT_SIZE")
    # Owner settings have third priority
    elif Config.LEECH_SPLIT_SIZE and max_split_size != Config.LEECH_SPLIT_SIZE:
        split_size = Config.LEECH_SPLIT_SIZE
    # Default to max split size if no custom size is set
    else:
        split_size = max_split_size

    # Ensure split size never exceeds Telegram's limit (based on premium status)
    # TgClient.MAX_SPLIT_SIZE is already set based on premium status
    # This will be 4000 MiB for premium users and 2000 MiB for regular users
    telegram_limit = TgClient.MAX_SPLIT_SIZE

    # Add a larger safety margin to ensure we never exceed Telegram's limit
    # Use a 50 MiB safety margin to account for any overhead or rounding issues
    safety_margin = 50 * 1024 * 1024  # 50 MiB

    # For non-premium accounts, use a more conservative limit
    if not TgClient.IS_PREMIUM_USER:
        # Use 2000 MiB (slightly less than 2 GiB) for non-premium accounts
        telegram_limit = 2000 * 1024 * 1024
    else:
        # Use 4000 MiB (slightly less than 4 GiB) for premium accounts
        telegram_limit = 4000 * 1024 * 1024

    safe_telegram_limit = telegram_limit - safety_margin

    split_size = min(split_size, safe_telegram_limit)

    # Ensure split size doesn't exceed maximum allowed
    split_size = min(split_size, max_split_size)

    # Skip splitting if file size is less than the split size
    if file_size <= split_size:
        return file_size, True
    # Always split the file if it's larger than split_size, regardless of max_split_size
    # This ensures files larger than max_split_size still get split when equal_splits is off
    return split_size, False


def update_user_ldata(id_, key, value):
    user_data.setdefault(id_, {})
    user_data[id_][key] = value


async def ensure_authorized_users():
    """
    Unified function to ensure OWNER_ID and SUDO_USERS are properly authorized.
    This consolidates all authorization logic into one place.
    """
    from bot import sudo_users
    from bot.core.config_manager import Config
    from bot.helper.ext_utils.db_handler import database

    authorized_count = 0

    # Authorize OWNER_ID
    if Config.OWNER_ID:
        owner_id = Config.OWNER_ID
        if owner_id not in user_data:
            user_data[owner_id] = {"AUTH": True}
            authorized_count += 1
        elif not user_data[owner_id].get("AUTH", False):
            user_data[owner_id]["AUTH"] = True
            authorized_count += 1

        # Update in database if available
        if hasattr(database, "db") and database.db is not None:
            await database.update_user_data(owner_id)

    # Authorize SUDO_USERS
    if Config.SUDO_USERS:
        aid = Config.SUDO_USERS.split()
        for id_ in aid:
            user_id = int(id_.strip())
            # Add to sudo_users list if not already there
            if user_id not in sudo_users:
                sudo_users.append(user_id)

            # Authorize the user
            if user_id not in user_data:
                user_data[user_id] = {"AUTH": True, "SUDO": True}
                authorized_count += 1
            else:
                if not user_data[user_id].get("AUTH", False):
                    user_data[user_id]["AUTH"] = True
                    authorized_count += 1
                user_data[user_id]["SUDO"] = True

            # Update in database if available
            if hasattr(database, "db") and database.db is not None:
                await database.update_user_data(user_id)

    if authorized_count > 0:
        from bot import LOGGER

        LOGGER.info(
            f"Ensured authorization for {authorized_count} privileged users (Owner + Sudo)"
        )

    return authorized_count


def is_privileged_user(user_id):
    """
    Check if user is OWNER_ID or SUDO_USER and auto-authorize if needed.
    Returns True if user is privileged, False otherwise.
    """
    from bot import sudo_users
    from bot.core.config_manager import Config

    # Check if user is owner
    if user_id == Config.OWNER_ID:
        # Ensure owner is authorized
        if user_id not in user_data:
            user_data[user_id] = {"AUTH": True}
        elif not user_data[user_id].get("AUTH", False):
            user_data[user_id]["AUTH"] = True
        return True

    # Check if user is sudo user
    if user_id in sudo_users:
        # Ensure sudo user is authorized
        if user_id not in user_data:
            user_data[user_id] = {"AUTH": True, "SUDO": True}
        else:
            if not user_data[user_id].get("AUTH", False):
                user_data[user_id]["AUTH"] = True
            user_data[user_id]["SUDO"] = True
        return True

    return False


async def getdailytasks(
    user_id,
    increase_task=False,
    upmirror=0,
    upleech=0,
    check_mirror=False,
    check_leech=False,
    save_data=True,
):
    """Get or update daily task statistics for a user.

    This function manages daily usage statistics for users, including task count,
    mirror usage, and leech usage. It also handles automatic reset at midnight.

    Args:
        user_id (int): User ID to check or update
        increase_task (bool, optional): Whether to increase the task count. Defaults to False.
        upmirror (int, optional): Size in bytes to add to mirror usage. Defaults to 0.
        upleech (int, optional): Size in bytes to add to leech usage. Defaults to 0.
        check_mirror (bool, optional): Whether to return mirror usage. Defaults to False.
        check_leech (bool, optional): Whether to return leech usage. Defaults to False.
        save_data (bool, optional): Whether to save data to disk. Defaults to True.

    Returns:
        int or float: Task count, mirror usage, or leech usage depending on parameters
    """
    from datetime import datetime

    try:
        # Initialize user data if not exists
        user_data.setdefault(user_id, {})
        user_dict = user_data[user_id]

        # Check if we need to reset daily stats (new day)
        current_date = datetime.now().strftime("%Y-%m-%d")
        last_reset_date = user_dict.get("last_reset_date", "")

        if current_date != last_reset_date:
            # It's a new day, reset the stats
            user_dict["daily_tasks"] = 0
            user_dict["daily_mirror"] = 0
            user_dict["daily_leech"] = 0
            user_dict["last_reset_date"] = current_date
            # Always save when resetting stats for a new day
            if save_data:
                await _save_user_data()
        else:
            # Initialize stats if they don't exist
            user_dict.setdefault("daily_tasks", 0)
            user_dict.setdefault("daily_mirror", 0)
            user_dict.setdefault("daily_leech", 0)
            user_dict.setdefault("last_reset_date", current_date)

        # Track if we made any changes
        made_changes = False

        # Handle task count increase
        if increase_task:
            user_dict["daily_tasks"] += 1
            made_changes = True
            result = user_dict["daily_tasks"]
        # Handle mirror usage update
        elif upmirror > 0:
            user_dict["daily_mirror"] += upmirror
            made_changes = True
            result = None
        # Handle leech usage update
        elif upleech > 0:
            user_dict["daily_leech"] += upleech
            made_changes = True
            result = None
        # Just checking values, no changes
        elif check_mirror:
            result = user_dict["daily_mirror"]
        elif check_leech:
            result = user_dict["daily_leech"]
        else:
            result = user_dict["daily_tasks"]

        # Only save if changes were made and save_data is True
        if made_changes and save_data:
            await _save_user_data()

        return result

    except Exception:
        # Return safe defaults in case of error
        if check_mirror or check_leech:
            return 0
        return 0


async def _save_user_data():
    """Save user data to a persistent file.

    This internal function saves the user_data dictionary to a JSON file
    to ensure data persistence across bot restarts.
    """
    import json

    import aiofiles

    try:
        # Create data directory if it doesn't exist
        os.makedirs("data", exist_ok=True)

        # Save user data to file - use compact JSON to reduce memory usage
        async with aiofiles.open("data/user_data.json", "w") as f:
            # Use separators without extra spaces to reduce file size
            # and disable pretty printing (indent=None) to save memory
            await f.write(json.dumps(user_data, separators=(",", ":"), indent=None))

        # Force garbage collection after saving large data
        try:
            from bot.helper.ext_utils.gc_utils import smart_garbage_collection

            smart_garbage_collection(aggressive=False)
        except ImportError:
            import gc

            gc.collect()

    except Exception:
        pass


async def _load_user_data():
    """Load user data from persistent file.

    This function is called during bot startup to load saved user data.
    """
    import json

    import aiofiles

    global user_data

    try:
        # Check if data file exists
        if os.path.exists("data/user_data.json"):
            async with aiofiles.open("data/user_data.json") as f:
                content = await f.read()
                if content.strip():  # Check if file is not empty
                    # Parse JSON with optimized memory usage
                    loaded_data = json.loads(content)

                    # Process data in chunks to reduce memory usage
                    # Clear existing data first
                    user_data.clear()

                    # Process in batches of 100 users
                    batch_size = 100
                    keys = list(loaded_data.keys())

                    for i in range(0, len(keys), batch_size):
                        batch_keys = keys[i : i + batch_size]
                        for k in batch_keys:
                            # Convert string keys back to integers
                            user_data[int(k)] = loaded_data[k]

                        # Force garbage collection after each batch
                        if (i + batch_size) < len(keys):
                            try:
                                from bot.helper.ext_utils.gc_utils import (
                                    smart_garbage_collection,
                                )

                                smart_garbage_collection(aggressive=False)
                            except ImportError:
                                import gc

                                gc.collect()

                    # Data loaded successfully

                    # Clear the loaded_data variable to free memory
                    del loaded_data

                    # Final garbage collection
                    try:
                        from bot.helper.ext_utils.gc_utils import (
                            smart_garbage_collection,
                        )

                        smart_garbage_collection(aggressive=True)
                    except ImportError:
                        import gc

                        gc.collect()
    except Exception:
        # Keep using the empty user_data dictionary
        pass


async def timeval_check(user_id):
    """Check if user needs to wait before starting a new task.

    This function enforces a minimum time interval between user tasks
    to prevent abuse and rate limit the bot usage.

    Args:
        user_id (int): User ID to check

    Returns:
        float: Time to wait in seconds, or 0 if no wait needed
    """
    from time import time

    from bot.core.config_manager import Config

    # Initialize user data if not exists
    user_data.setdefault(user_id, {})
    user_data[user_id].setdefault("last_task_time", 0)

    # Get time interval setting from config
    interval = Config.USER_TIME_INTERVAL

    # If interval is not set or is zero, no time restriction
    if not interval:
        user_data[user_id]["last_task_time"] = time()
        return 0

    # Check if enough time has passed since last task
    current_time = time()
    last_time = user_data[user_id]["last_task_time"]
    elapsed = current_time - last_time

    # If not enough time has passed, user needs to wait
    if elapsed < interval:
        return interval - elapsed

    # No wait needed, update last task time and save data
    user_data[user_id]["last_task_time"] = current_time
    await _save_user_data()
    return 0


def encode_slink(string):
    return (urlsafe_b64encode(string.encode("ascii")).decode("ascii")).strip("=")


def decode_slink(b64_str):
    return urlsafe_b64decode(
        (b64_str.strip("=") + "=" * (-len(b64_str.strip("=")) % 4)).encode("ascii"),
    ).decode("ascii")


async def cmd_exec(cmd, shell=False, task_type="FFmpeg"):
    """Execute a command and return its output.

    Args:
        cmd: Command to execute (list or string)
        shell: Whether to use shell execution
        task_type: Type of task (e.g., "FFmpeg", "Watermark", "Merge")

    Returns:
        tuple: (stdout, stderr, return_code)
    """
    import asyncio
    import shlex
    import sys

    # Handle shell commands with special characters
    if shell and isinstance(cmd, str):
        # Use shlex.quote to properly escape the command for shell execution
        cmd_parts = shlex.split(cmd)
        cmd = " ".join(shlex.quote(part) for part in cmd_parts)

    try:
        if shell:
            proc = await create_subprocess_shell(cmd, stdout=PIPE, stderr=PIPE)
        else:
            proc = await create_subprocess_exec(*cmd, stdout=PIPE, stderr=PIPE)
    except NotImplementedError:
        # Fallback for environments where child watcher is not implemented
        # This can happen in certain asyncio environments
        if sys.platform != "win32":
            # Set a compatible event loop policy for Unix systems
            try:
                asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
                if shell:
                    proc = await create_subprocess_shell(
                        cmd, stdout=PIPE, stderr=PIPE
                    )
                else:
                    proc = await create_subprocess_exec(
                        *cmd, stdout=PIPE, stderr=PIPE
                    )
            except Exception:
                # Final fallback: use synchronous subprocess
                import subprocess

                if shell:
                    result = subprocess.run(
                        cmd, check=False, shell=True, capture_output=True, text=True
                    )
                else:
                    result = subprocess.run(
                        cmd, check=False, capture_output=True, text=True
                    )
                return (
                    result.stdout.strip(),
                    result.stderr.strip(),
                    result.returncode,
                )
        else:
            # For Windows, use synchronous subprocess as fallback
            import subprocess

            if shell:
                result = subprocess.run(
                    cmd, check=False, shell=True, capture_output=True, text=True
                )
            else:
                result = subprocess.run(
                    cmd, check=False, capture_output=True, text=True
                )
            return result.stdout.strip(), result.stderr.strip(), result.returncode

    stdout, stderr = await proc.communicate()
    try:
        stdout = stdout.decode().strip()
    except Exception:
        stdout = "Unable to decode the response!"
    try:
        stderr = stderr.decode().strip()
    except Exception:
        stderr = "Unable to decode the error!"

    # Force garbage collection after resource-intensive operations
    if (
        task_type in ["FFmpeg", "Watermark", "Merge", "7z", "Split File"]
        and smart_garbage_collection is not None
    ):
        smart_garbage_collection(
            aggressive=True
        )  # Use aggressive mode for resource-intensive operations
    elif proc.returncode != 0 and smart_garbage_collection is not None:
        # Also collect garbage after failed operations to clean up any partial resources
        smart_garbage_collection(aggressive=False)

    return stdout, stderr, proc.returncode


def new_task(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        return bot_loop.create_task(func(*args, **kwargs))

    return wrapper


async def sync_to_async(func, *args, wait=True, **kwargs):
    """
    Run a synchronous function in a thread pool and return its result.

    Args:
        func: The synchronous function to run
        *args: Arguments to pass to the function
        wait: Whether to wait for the result
        **kwargs: Keyword arguments to pass to the function

    Returns:
        The result of the function if wait=True, otherwise the future
    """
    try:
        # Check if we should run garbage collection before creating a new thread
        # This helps prevent resource exhaustion in high-load situations
        if smart_garbage_collection is not None:
            # Monitor thread usage and run garbage collection if needed
            from bot.helper.ext_utils.gc_utils import monitor_thread_usage

            if monitor_thread_usage():
                smart_garbage_collection(aggressive=True)

        # Create partial function with arguments
        pfunc = partial(func, *args, **kwargs)

        # Run in executor using default thread pool
        future = bot_loop.run_in_executor(None, pfunc)
        result = await future if wait else future

        # Force garbage collection after large operations
        if (
            smart_garbage_collection is not None
            and hasattr(func, "__name__")
            and func.__name__
            in ["walk", "get_media_info", "extract", "zip", "get_path_size"]
        ):
            smart_garbage_collection(
                aggressive=False
            )  # Use normal mode for standard operations

        return result
    except RuntimeError as e:
        # Handle thread creation errors
        if "can't start new thread" in str(e):
            LOGGER.error(f"Thread limit reached: {e}")
            # Force aggressive garbage collection
            if smart_garbage_collection is not None:
                smart_garbage_collection(aggressive=True)
            # Wait a bit and retry
            await sleep(1)

            # Retry the operation
            pfunc = partial(func, *args, **kwargs)
            future = bot_loop.run_in_executor(None, pfunc)
            return await future if wait else future
        # Re-raise other runtime errors
        raise


def async_to_sync(func, *args, wait=True, **kwargs):
    future = run_coroutine_threadsafe(func(*args, **kwargs), bot_loop)
    return future.result() if wait else future


def loop_thread(func):
    @wraps(func)
    def wrapper(*args, wait=False, **kwargs):
        future = run_coroutine_threadsafe(func(*args, **kwargs), bot_loop)
        return future.result() if wait else future

    return wrapper


def is_media_tool_enabled(tool_name):
    """Check if a specific media tool is enabled in the global configuration.

    Args:
        tool_name (str): The name of the tool to check (merge, watermark, convert, etc.)
                         Use 'mediatools' to check if all media tools are enabled.

    Returns:
        bool: True if the tool is enabled, False otherwise
    """
    from bot import LOGGER
    from bot.core.config_manager import Config

    # If media tools are completely disabled (boolean False), return False
    if Config.MEDIA_TOOLS_ENABLED is False:
        return False

    # List of all available tools
    all_tools = [
        "watermark",
        "merge",
        "convert",
        "compression",
        "trim",
        "extract",
        "remove",
        "add",
        "swap",
        "metadata",
        "xtra",
        "sample",
        "screenshot",
        "archive",
    ]

    # This is a synchronous function, so we can't directly access the database
    # We'll use the current value from Config and rely on the UI to refresh it

    # Parse enabled tools from the configuration
    enabled_tools = []

    # If MEDIA_TOOLS_ENABLED is a string
    if isinstance(Config.MEDIA_TOOLS_ENABLED, str):
        # Handle both comma-separated and single values
        if "," in Config.MEDIA_TOOLS_ENABLED:
            # Split by comma and strip whitespace
            enabled_tools = [
                t.strip().lower()
                for t in Config.MEDIA_TOOLS_ENABLED.split(",")
                if t.strip()
            ]
        elif Config.MEDIA_TOOLS_ENABLED.strip():  # Single non-empty value
            # Make sure to properly handle a single tool name
            single_tool = Config.MEDIA_TOOLS_ENABLED.strip().lower()
            if single_tool in all_tools:
                enabled_tools = [single_tool]
            # If the single tool is not in all_tools, it might be a comma-separated string without spaces
            elif any(t in single_tool for t in all_tools):
                # Try to split by comma without spaces
                potential_tools = single_tool.split(",")
                enabled_tools = [t for t in potential_tools if t in all_tools]

                # If we couldn't find any valid tools, try the original value again
                if not enabled_tools and single_tool:
                    # Check if it's a valid tool name (might be misspelled or have extra characters)
                    for tool in all_tools:
                        if tool in single_tool:
                            enabled_tools = [tool]
                            break

    # If MEDIA_TOOLS_ENABLED is True (boolean), all tools are enabled
    elif Config.MEDIA_TOOLS_ENABLED is True:
        enabled_tools = all_tools.copy()

    # If MEDIA_TOOLS_ENABLED is some other truthy value
    elif Config.MEDIA_TOOLS_ENABLED:
        if isinstance(Config.MEDIA_TOOLS_ENABLED, list | tuple | set):
            enabled_tools = [
                str(t).strip().lower() for t in Config.MEDIA_TOOLS_ENABLED if t
            ]
        else:
            # Try to convert to string and use as a single value
            try:
                val = str(Config.MEDIA_TOOLS_ENABLED).strip().lower()
                if val:
                    if val in all_tools:
                        enabled_tools = [val]
                    else:
                        # Check if it contains a valid tool name
                        for tool in all_tools:
                            if tool in val:
                                enabled_tools = [tool]
                                break
            except Exception as e:
                LOGGER.error(f"Error parsing MEDIA_TOOLS_ENABLED value: {e}")

    # If checking for 'mediatools' (general media tools status), return True if any tool is enabled
    if tool_name.lower() == "mediatools":
        return len(enabled_tools) > 0

    # Check if the specific tool is in the enabled list
    # If MEDIA_TOOLS_ENABLED is False or empty, no tools are enabled
    if not enabled_tools:
        return False

    # Otherwise, check if the specific tool is in the enabled list
    return tool_name.lower() in enabled_tools


def is_flag_enabled(flag_name):
    """Check if a specific command flag is enabled based on media tools configuration.

    Args:
        flag_name (str): The name of the flag to check (ff, sv, mt, etc.)

    Returns:
        bool: True if the flag is enabled, False otherwise
    """
    from bot.core.config_manager import Config

    # Clean the flag name by removing the leading dash
    clean_flag = flag_name.lstrip("-")

    # Check for leech-related flags
    leech_flags = ["tl", "hl", "ut", "bt", "sp", "es", "doc", "med"]
    if clean_flag in leech_flags:
        # If leech is disabled, these flags should be disabled too
        return Config.LEECH_ENABLED

    # Check for ytdlp-related flags
    ytdlp_flags = ["opt", "range"]
    if clean_flag in ytdlp_flags:
        # If ytdlp is disabled, these flags should be disabled too
        return Config.YTDLP_ENABLED

    # Check for torrent seed flag
    if clean_flag == "d":
        # If torrent operations are disabled, the seed flag should be disabled too
        return Config.TORRENT_ENABLED

    # Check for streamrip-related flags
    streamrip_flags = ["q", "quality", "c", "codec"]
    if clean_flag in streamrip_flags:
        # If streamrip is disabled, these flags should be disabled too
        return Config.STREAMRIP_ENABLED

    # Map flags to their corresponding media tools
    flag_to_tool_map = {
        "ff": "xtra",  # Custom FFmpeg commands flag
        "sv": "sample",  # Sample video flag
        "ss": "screenshot",  # Screenshot flag
        "mt": "mediatools",  # Media tools flag
        "md": "metadata",  # Metadata flag
        "merge-video": "merge",
        "merge-audio": "merge",
        "merge-subtitle": "merge",
        "merge-all": "merge",
        "merge-image": "merge",
        "merge-pdf": "merge",
        "watermark": "watermark",
        "wm": "watermark",  # Short for watermark
        "iwm": "watermark",  # Image watermark flag
        "extract": "extract",
        "extract-video": "extract",
        "extract-audio": "extract",
        "extract-subtitle": "extract",
        "extract-attachment": "extract",
        "extract-video-index": "extract",
        "extract-audio-index": "extract",
        "extract-subtitle-index": "extract",
        "extract-attachment-index": "extract",
        "vi": "extract",  # Short for extract-video-index
        "ai": "extract",  # Short for extract-audio-index
        "si": "extract",  # Short for extract-subtitle-index
        "ati": "extract",  # Short for extract-attachment-index
        "remove": "remove",
        "remove-video": "remove",
        "remove-audio": "remove",
        "remove-subtitle": "remove",
        "remove-attachment": "remove",
        "remove-metadata": "remove",
        "remove-video-index": "remove",
        "remove-audio-index": "remove",
        "remove-subtitle-index": "remove",
        "remove-attachment-index": "remove",
        "rvi": "remove",  # Short for remove-video-index
        "rai": "remove",  # Short for remove-audio-index
        "rsi": "remove",  # Short for remove-subtitle-index
        "rati": "remove",  # Short for remove-attachment-index
        "add": "add",
        "add-video": "add",
        "add-audio": "add",
        "add-subtitle": "add",
        "add-attachment": "add",
        "add-video-index": "add",
        "add-audio-index": "add",
        "add-subtitle-index": "add",
        "add-attachment-index": "add",
        "avi": "add",  # Short for add-video-index
        "aai": "add",  # Short for add-audio-index
        "asi": "add",  # Short for add-subtitle-index
        "aati": "add",  # Short for add-attachment-index
        "preserve": "add",
        "replace": "add",
        "swap": "swap",
        "swap-audio": "swap",
        "swap-video": "swap",
        "swap-subtitle": "swap",
        "trim": "trim",
        "compress": "compression",
        "comp-video": "compression",
        "comp-audio": "compression",
        "comp-image": "compression",
        "comp-document": "compression",
        "comp-subtitle": "compression",
        "comp-archive": "compression",
        "video-fast": "compression",
        "video-medium": "compression",
        "video-slow": "compression",
        "audio-fast": "compression",
        "audio-medium": "compression",
        "audio-slow": "compression",
        "image-fast": "compression",
        "image-medium": "compression",
        "image-slow": "compression",
        "document-fast": "compression",
        "document-medium": "compression",
        "document-slow": "compression",
        "subtitle-fast": "compression",
        "subtitle-medium": "compression",
        "subtitle-slow": "compression",
        "archive-fast": "compression",
        "archive-medium": "compression",
        "archive-slow": "compression",
        "cv": "convert",  # Convert video flag
        "ca": "convert",  # Convert audio flag
        "cs": "convert",  # Convert subtitle flag
        "cd": "convert",  # Convert document flag
        "cr": "convert",  # Convert archive flag
        "del": "convert",  # Delete original after conversion
        "metadata-title": "metadata",
        "metadata-author": "metadata",
        "metadata-artist": "metadata",
        "metadata-album": "metadata",
        "metadata-year": "metadata",
        "metadata-genre": "metadata",
        "metadata-comment": "metadata",
        "metadata-all": "metadata",
        "metadata-video-title": "metadata",
        "metadata-audio-title": "metadata",
        "metadata-subtitle-title": "metadata",
        "metadata-video-author": "metadata",
        "metadata-audio-author": "metadata",
        "metadata-subtitle-author": "metadata",
        "z": "archive",  # Archive compression flag
        "e": "archive",  # Archive extraction flag
        # Gallery-dl flags
        "-archive": "gallery-dl",
        "-no-archive": "gallery-dl",
        "-metadata": "gallery-dl",
        "-no-metadata": "gallery-dl",
        "-write-info-json": "gallery-dl",
        "-limit": "gallery-dl",
        "-username": "gallery-dl",
        "-password": "gallery-dl",
    }

    # Special case for -m flag (same directory operations)
    if clean_flag == "m":
        return Config.SAME_DIR_ENABLED

    # Special case for archive flags (-z and -e)
    if clean_flag in ["z", "e"]:
        return (
            hasattr(Config, "ARCHIVE_FLAGS_ENABLED") and Config.ARCHIVE_FLAGS_ENABLED
        )

    # Special case for gallery-dl flags
    if clean_flag in [
        "-archive",
        "-no-archive",
        "-metadata",
        "-no-metadata",
        "-write-info-json",
        "-limit",
        "-username",
        "-password",
    ]:
        return Config.GALLERY_DL_ENABLED

    # If the flag is not in the map, assume it's enabled
    if clean_flag not in flag_to_tool_map:
        return True

    # Get the tool name for this flag
    tool_name = flag_to_tool_map[clean_flag]

    # Special handling for "archive" tool
    if tool_name == "archive":
        return (
            hasattr(Config, "ARCHIVE_FLAGS_ENABLED") and Config.ARCHIVE_FLAGS_ENABLED
        )

    # Check if the tool is enabled
    return is_media_tool_enabled(tool_name)


def check_storage_threshold(size, threshold, arch=False):
    """Check if there's enough storage space available.

    This function checks if there's enough free space on the disk to download a file
    and optionally extract it, while maintaining a minimum free space threshold.

    Args:
        size (int): Size of the file/folder to be downloaded in bytes
        threshold (int): Minimum free space to maintain in bytes
        arch (bool, optional): Whether the download will be archived/extracted. Defaults to False.

    Returns:
        bool: True if there's enough space, False otherwise

    Note:
        For archives, the function estimates that extraction will require approximately
        the same amount of space as the archive itself, so it checks for 2x the size.
        For very large archives with high compression ratios, this might underestimate
        the required space.
    """
    import shutil

    from bot import DOWNLOAD_DIR, LOGGER
    from bot.helper.ext_utils.status_utils import get_readable_file_size

    # Handle invalid inputs
    if not isinstance(size, int | float) or size < 0:
        LOGGER.warning(f"Invalid size value in check_storage_threshold: {size}")
        return True  # Default to allowing the download if size is invalid

    if not isinstance(threshold, int | float) or threshold < 0:
        LOGGER.warning(
            f"Invalid threshold value in check_storage_threshold: {threshold}"
        )
        threshold = 0  # Default to no threshold if invalid

    # If size is 0, no space is needed
    if size == 0:
        return True

    try:
        # Ensure the download directory exists
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)

        # Get disk usage statistics
        usage = shutil.disk_usage(DOWNLOAD_DIR)
        free = usage.free
        total = usage.total

        # Calculate disk usage (logging will be done in consolidated critical resource logs)
        (usage.used / total) * 100

        # Calculate space needed based on whether it's an archive
        space_needed = size
        if arch:
            # For archives, estimate extraction will need the same space as the archive
            # Use a multiplier between 1.5x and 3x based on common compression ratios
            # 1.5x for basic archives, 2x for typical, 3x for highly compressed
            compression_multiplier = 2.0  # Default to 2x for typical compression

            # Adjust multiplier based on file size (larger files often have higher compression)
            if size > 1024**3:  # > 1GB
                compression_multiplier = 2.5
            elif size > 10 * 1024**3:  # > 10GB
                compression_multiplier = 3.0

            space_needed = int(size * compression_multiplier)
            LOGGER.info(
                f"Archive detected: {get_readable_file_size(size)} → estimating {compression_multiplier}x space needed for extraction ({get_readable_file_size(space_needed)} total)"
            )

        # Check if there's enough space
        has_enough_space = (free - space_needed) >= threshold

        # Log the result (only log failures, success will be in consolidated critical resource logs)
        if has_enough_space:
            pass  # Success logging handled in consolidated critical resource logs
        else:
            LOGGER.warning(
                f"Storage check failed: Need {get_readable_file_size(space_needed)}, "
                f"have {get_readable_file_size(free)}, "
                f"threshold {get_readable_file_size(threshold)}"
            )

        return has_enough_space

    except Exception as e:
        LOGGER.error(f"Error checking storage threshold: {e}")
        # Default to allowing the download if we can't check the space
        return True
