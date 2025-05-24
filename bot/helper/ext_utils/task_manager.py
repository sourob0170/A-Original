from asyncio import Event

from bot import (
    LOGGER,
    non_queued_dl,
    non_queued_up,
    queue_dict_lock,
    queued_dl,
    queued_up,
)
from bot.core.config_manager import Config
from bot.helper.mirror_leech_utils.gdrive_utils.search import GoogleDriveSearch

from .bot_utils import get_telegraph_list, sync_to_async
from .files_utils import get_base_name
from .links_utils import is_gdrive_id


async def stop_duplicate_check(listener):
    if (
        isinstance(listener.up_dest, int)
        or listener.is_leech
        or listener.select
        or not is_gdrive_id(listener.up_dest)
        or (listener.up_dest.startswith("mtp:") and listener.stop_duplicate)
        or not listener.stop_duplicate
        or listener.same_dir
    ):
        return False, None

    name = listener.name
    LOGGER.info(f"Checking File/Folder if already in Drive: {name}")

    if listener.compress:
        # Check if it's the new compression feature or the old 7z compression
        if hasattr(listener, "compression_enabled") and listener.compression_enabled:
            # For the new compression feature, we keep the original name
            # as the compressed file will maintain its extension
            pass
        else:
            # For the old 7z compression
            name = f"{name}.7z"
    elif listener.extract:
        try:
            name = get_base_name(name)
        except Exception:
            name = None

    if name is not None:
        telegraph_content, contents_no = await sync_to_async(
            GoogleDriveSearch(stop_dup=True, no_multi=listener.is_clone).drive_list,
            name,
            listener.up_dest,
            listener.user_id,
        )
        if telegraph_content:
            msg = f"File/Folder is already available in Drive.\nHere are {contents_no} list results:"
            button = await get_telegraph_list(telegraph_content)
            return msg, button

    return False, None


async def check_running_tasks(listener, state="dl"):
    all_limit = Config.QUEUE_ALL
    state_limit = Config.QUEUE_DOWNLOAD if state == "dl" else Config.QUEUE_UPLOAD
    event = None
    is_over_limit = False

    # Check system resources before allowing new tasks
    try:
        import psutil

        memory_percent = psutil.virtual_memory().percent
        cpu_percent = psutil.cpu_percent(interval=0.1)

        # If system resources are critically low, force queue regardless of limits
        resource_critical = memory_percent > 90 or cpu_percent > 95

        if resource_critical:
            LOGGER.warning(
                f"System resources critical: Memory {memory_percent}%, CPU {cpu_percent}%. "
                f"Forcing task {listener.mid} to queue."
            )
            # Force garbage collection to try to free up resources
            from bot.helper.ext_utils.gc_utils import smart_garbage_collection

            smart_garbage_collection(aggressive=True)

            # Create event for queuing
            event = Event()
            async with queue_dict_lock:
                if state == "dl":
                    queued_dl[listener.mid] = event
                else:
                    queued_up[listener.mid] = event

            return True, event
    except ImportError:
        # If psutil is not available, continue with normal limit checks
        pass

    async with queue_dict_lock:
        if state == "up" and listener.mid in non_queued_dl:
            non_queued_dl.remove(listener.mid)
        if (
            (all_limit or state_limit)
            and not listener.force_run
            and not (listener.force_upload and state == "up")
            and not (listener.force_download and state == "dl")
        ):
            dl_count = len(non_queued_dl)
            up_count = len(non_queued_up)
            t_count = dl_count if state == "dl" else up_count
            is_over_limit = (
                all_limit
                and dl_count + up_count >= all_limit
                and (not state_limit or t_count >= state_limit)
            ) or (state_limit and t_count >= state_limit)
            if is_over_limit:
                event = Event()
                if state == "dl":
                    queued_dl[listener.mid] = event
                else:
                    queued_up[listener.mid] = event
        if not is_over_limit:
            if state == "up":
                non_queued_up.add(listener.mid)
            else:
                non_queued_dl.add(listener.mid)

    return is_over_limit, event


async def start_dl_from_queued(mid: int):
    queued_dl[mid].set()
    del queued_dl[mid]
    non_queued_dl.add(mid)


async def start_up_from_queued(mid: int):
    queued_up[mid].set()
    del queued_up[mid]
    non_queued_up.add(mid)


async def start_from_queued():
    # Check system resources before starting queued tasks
    try:
        import psutil

        memory_percent = psutil.virtual_memory().percent
        cpu_percent = psutil.cpu_percent(interval=0.1)

        # If system resources are critically low, don't start new tasks
        if memory_percent > 85 or cpu_percent > 90:
            LOGGER.warning(
                f"System resources too high to start queued tasks: Memory {memory_percent}%, CPU {cpu_percent}%. "
                f"Will try again later."
            )
            # Force garbage collection to try to free up resources
            from bot.helper.ext_utils.gc_utils import smart_garbage_collection

            smart_garbage_collection(aggressive=True)
            return

        # If resources are moderately high, start fewer tasks
        resource_constraint = memory_percent > 75 or cpu_percent > 80
    except ImportError:
        # If psutil is not available, assume no resource constraints
        resource_constraint = False

    if all_limit := Config.QUEUE_ALL:
        dl_limit = Config.QUEUE_DOWNLOAD
        up_limit = Config.QUEUE_UPLOAD
        async with queue_dict_lock:
            dl = len(non_queued_dl)
            up = len(non_queued_up)
            all_ = dl + up
            if all_ < all_limit:
                f_tasks = all_limit - all_
                if resource_constraint:
                    f_tasks = min(
                        f_tasks, 2
                    )  # Start at most 2 tasks when resources are constrained

                if queued_up and (not up_limit or up < up_limit):
                    for index, mid in enumerate(list(queued_up.keys()), start=1):
                        await start_up_from_queued(mid)
                        f_tasks -= 1
                        if f_tasks == 0 or (up_limit and index >= up_limit - up):
                            break
                if queued_dl and (not dl_limit or dl < dl_limit) and f_tasks != 0:
                    for index, mid in enumerate(list(queued_dl.keys()), start=1):
                        await start_dl_from_queued(mid)
                        if (dl_limit and index >= dl_limit - dl) or index == f_tasks:
                            break
        return

    # If resources are constrained, be more conservative with task starts
    1 if resource_constraint else float("inf")

    if up_limit := Config.QUEUE_UPLOAD:
        async with queue_dict_lock:
            up = len(non_queued_up)
            if queued_up and up < up_limit:
                f_tasks = up_limit - up
                for index, mid in enumerate(list(queued_up.keys()), start=1):
                    await start_up_from_queued(mid)
                    if index == f_tasks:
                        break
    else:
        async with queue_dict_lock:
            if queued_up:
                for mid in list(queued_up.keys()):
                    await start_up_from_queued(mid)

    if dl_limit := Config.QUEUE_DOWNLOAD:
        async with queue_dict_lock:
            dl = len(non_queued_dl)
            if queued_dl and dl < dl_limit:
                f_tasks = dl_limit - dl
                for index, mid in enumerate(list(queued_dl.keys()), start=1):
                    await start_dl_from_queued(mid)
                    if index == f_tasks:
                        break
    else:
        async with queue_dict_lock:
            if queued_dl:
                for mid in list(queued_dl.keys()):
                    await start_dl_from_queued(mid)
