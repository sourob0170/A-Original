#!/usr/bin/env python3
import asyncio
import time
from asyncio import create_task
from collections import defaultdict, deque

try:
    import psutil
except ImportError:
    import pip

    pip.main(["install", "psutil"])
    import psutil

# Resource manager removed
from bot import (
    LOGGER,
    non_queued_dl,
    non_queued_up,
    queue_dict_lock,
    queued_dl,
    queued_up,
    task_dict,
    task_dict_lock,
)
from bot.core.config_manager import Config
from bot.helper.ext_utils.gc_utils import (
    log_memory_usage,
    monitor_thread_usage,
    smart_garbage_collection,
)
from bot.helper.ext_utils.status_utils import (
    MirrorStatus,
    speed_string_to_bytes,
)
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    send_message,
)


# Get monitoring settings from Config
def get_check_interval():
    return Config.TASK_MONITOR_INTERVAL


def get_speed_threshold():
    return Config.TASK_MONITOR_SPEED_THRESHOLD * 1024  # Convert KB/s to bytes


def get_consecutive_checks():
    return Config.TASK_MONITOR_CONSECUTIVE_CHECKS


def get_elapsed_time_threshold():
    return Config.TASK_MONITOR_ELAPSED_THRESHOLD


def get_long_eta_threshold():
    return Config.TASK_MONITOR_ETA_THRESHOLD


def get_wait_time_before_cancel():
    return Config.TASK_MONITOR_WAIT_TIME


def get_long_completion_threshold():
    return Config.TASK_MONITOR_COMPLETION_THRESHOLD


def get_cpu_high_threshold():
    return Config.TASK_MONITOR_CPU_HIGH


def get_cpu_low_threshold():
    return Config.TASK_MONITOR_CPU_LOW


def get_memory_high_threshold():
    return Config.TASK_MONITOR_MEMORY_HIGH


def get_memory_low_threshold():
    return Config.TASK_MONITOR_MEMORY_LOW


# Store monitoring data
task_speeds: dict[str, deque[int]] = defaultdict(
    lambda: deque(maxlen=get_consecutive_checks())
)
task_warnings: dict[str, dict] = {}
cpu_usage_history: deque[float] = deque(maxlen=get_consecutive_checks())
memory_usage_history: deque[float] = deque(maxlen=get_consecutive_checks())
queued_by_monitor: set[int] = set()  # Store tasks queued by the monitor
cpu_intensive_tasks: list[tuple[int, str]] = []  # [(mid, task_type), ...]
memory_intensive_tasks: list[tuple[int, str]] = []  # [(mid, task_type), ...]


async def get_task_speed(task) -> int:
    """Get the current download speed of a task in bytes per second."""
    try:
        if not hasattr(task, "speed") or not callable(task.speed):
            return 0

        speed = task.speed()
        if isinstance(speed, str):
            # Handle common zero speed strings explicitly
            if speed in ["0B/s", "0.00B/s", "-"]:
                return 0
            # Convert string speed (like "1.5 MB/s") to bytes
            return speed_string_to_bytes(speed)
        return speed
    except Exception:
        return 0


async def get_task_eta(task) -> int:
    """Get the estimated time remaining for a task in seconds."""
    try:
        if not hasattr(task, "eta") or not callable(task.eta):
            return float("inf")

        eta = task.eta()
        if isinstance(eta, str):
            # Handle common cases for stalled or unknown ETA
            if eta == "-" or "∞" in eta or not eta:
                # Check if speed is zero - this is a strong indicator of a stalled task
                speed = await get_task_speed(task)
                if speed == 0:
                    # For stalled tasks with zero speed, return a high but finite value
                    # This helps differentiate between truly stalled tasks and those just starting
                    return 86400  # 24 hours - high enough to trigger cancellation
                return float("inf")  # Infinite ETA

            # Try to convert readable time to seconds
            try:
                # Parse time string like "2h 3m 4s" to seconds
                parts = eta.split()
                seconds = 0
                for part in parts:
                    if "h" in part:
                        seconds += int(part.replace("h", "")) * 3600
                    elif "m" in part:
                        seconds += int(part.replace("m", "")) * 60
                    elif "s" in part:
                        seconds += int(part.replace("s", ""))
                return seconds
            except Exception:
                # If parsing fails, return infinite ETA
                return float("inf")
        return eta
    except Exception:
        return float("inf")  # Return infinite ETA on error


async def estimate_completion_time(task) -> int:
    """Estimate completion time based on file size and current speed."""
    try:
        # Get processed bytes and total size
        if hasattr(task, "processed_bytes") and callable(task.processed_bytes):
            processed_str = task.processed_bytes()
            if isinstance(processed_str, str):
                processed = speed_string_to_bytes(processed_str)
            else:
                processed = processed_str
        else:
            processed = 0

        if hasattr(task, "size") and callable(task.size):
            size_str = task.size()
            if isinstance(size_str, str):
                size = speed_string_to_bytes(size_str)
            else:
                size = size_str
        else:
            size = 0

        # Get current speed
        speed = await get_task_speed(task)

        if speed <= 0 or size <= 0 or processed >= size:
            return float("inf")

        # Calculate remaining time
        remaining_bytes = size - processed
        return remaining_bytes / speed if speed > 0 else float("inf")

    except Exception:
        return float("inf")


async def get_task_elapsed_time(task) -> int:
    """Get the elapsed time for a task in seconds."""
    try:
        if not hasattr(task, "listener"):
            return 0
        if not hasattr(task.listener, "message"):
            return 0
        if not hasattr(task.listener.message, "date"):
            return 0

        return int(time.time() - task.listener.message.date.timestamp())
    except Exception:
        return 0


def is_ytdlp_task(task) -> bool:
    """Check if a task is a YT-DLP task."""
    return (
        hasattr(task, "listener")
        and hasattr(task.listener, "is_ytdlp")
        and task.listener.is_ytdlp
    )


def is_jd_task(task) -> bool:
    """Check if a task is a JDownloader task."""
    return hasattr(task, "tool") and task.tool == "jd"


def is_nzb_task(task) -> bool:
    """Check if a task is an NZB task."""
    return hasattr(task, "tool") and task.tool == "nzb"


async def is_task_in_global_queue(mid: int) -> bool:
    """Check if a task is queued by the global queue system."""
    async with queue_dict_lock:
        return mid in queued_dl or mid in queued_up


async def is_task_slow(task, gid: str) -> bool:
    """Check if a task's download speed is consistently below threshold."""
    speed = await get_task_speed(task)
    task_speeds[gid].append(speed)

    # Get the threshold based on task type
    threshold = get_speed_threshold()

    # Adjust threshold for specific task types
    if is_ytdlp_task(task):
        # YT-DLP tasks might have variable speeds due to processing
        threshold = threshold * 0.75  # More lenient threshold
    elif is_jd_task(task):
        # JDownloader tasks might have connection issues
        threshold = threshold * 0.8  # Slightly more lenient threshold
    elif is_nzb_task(task):
        # NZB tasks might be processing or repairing files
        threshold = threshold * 0.8  # Slightly more lenient threshold

    # Check if we have enough data points and all are below threshold
    return bool(
        len(task_speeds[gid]) >= get_consecutive_checks()
        and all(s <= threshold for s in task_speeds[gid])
    )


async def should_cancel_task(task, gid: str) -> tuple[bool, str]:
    """Determine if a task should be cancelled based on monitoring criteria."""
    try:
        if not hasattr(task, "status") or not callable(task.status):
            return False, ""

        # Check if task has listener attribute
        if not hasattr(task, "listener"):
            return False, ""

        # Get task status
        status = (
            await task.status()
            if asyncio.iscoroutinefunction(task.status)
            else task.status()
        )

        # Only monitor download tasks
        # Check for all relevant download statuses including specific task types
        download_statuses = [
            MirrorStatus.STATUS_DOWNLOAD,
            MirrorStatus.STATUS_QUEUEDL,
        ]

        # Skip monitoring for tasks that are not in download state
        if status not in download_statuses:
            return False, ""

        # Special handling for different task types
        # Get elapsed time for task type-specific checks
        task_elapsed_time = await get_task_elapsed_time(task)

        # Check if it's a ytdlp task
        if is_ytdlp_task(task):
            # For ytdlp tasks, we need to be more lenient as they might have variable speeds
            # due to processing different formats or playlist items
            if (
                task_elapsed_time < get_elapsed_time_threshold() * 0.5
            ):  # Give ytdlp tasks more time
                return False, ""

        # Check if it's a JDownloader task
        if is_jd_task(task):
            # JDownloader tasks might have connection issues or be in queue within JD itself
            # Give them more time and be more lenient with speed checks
            if task_elapsed_time < get_elapsed_time_threshold() * 0.75:
                return False, ""

        # Check if it's an NZB task
        if is_nzb_task(task):
            # NZB tasks might be processing or repairing files
            # Give them more time before considering cancellation
            if task_elapsed_time < get_elapsed_time_threshold() * 0.75:
                return False, ""

        # Check if task is queued by global queue system
        # Don't cancel tasks that are queued by the global queue system
        if hasattr(task.listener, "mid"):
            mid = task.listener.mid
            if await is_task_in_global_queue(mid):
                LOGGER.debug(
                    f"Task {mid} is queued by global queue system, skipping cancellation check"
                )
                return False, ""
    except Exception:
        return False, ""

    elapsed_time = await get_task_elapsed_time(task)
    eta = await get_task_eta(task)
    is_slow = await is_task_slow(task, gid)

    # User tag is not needed here, it's only used in notifications
    # which are handled in the cancel_task function

    # Case 1: Task estimation > 24h or no estimation && elapsed > 1h
    if (
        eta == float("inf") or eta > get_long_eta_threshold()
    ) and elapsed_time > get_elapsed_time_threshold():
        if gid not in task_warnings:
            task_warnings[gid] = {
                "warning_sent": False,
                "warning_time": 0,
                "reason": "Long estimated completion time or no progress. Please cancel this task if it's stuck.",
                "case": 1,
            }

        if not task_warnings[gid]["warning_sent"]:
            task_warnings[gid]["warning_sent"] = True
            task_warnings[gid]["warning_time"] = time.time()
            return False, task_warnings[gid]["reason"]

        # Check if wait time has passed since warning
        if (
            time.time() - task_warnings[gid]["warning_time"]
            > get_wait_time_before_cancel()
        ):
            return (
                True,
                f"Task was warned {get_wait_time_before_cancel() // 60} minutes ago but not cancelled manually.",
            )

    # Case 2: Slow download + long ETA + elapsed > 1h
    if (
        is_slow
        and (eta == float("inf") or eta > get_long_eta_threshold())
        and elapsed_time > get_elapsed_time_threshold()
    ):
        return (
            True,
            f"Slow download speed (≤{Config.TASK_MONITOR_SPEED_THRESHOLD}KB/s) with long estimated completion time.",
        )

    # Case 3: Slow download + estimated completion > 4h
    if is_slow:
        estimated_time = await estimate_completion_time(task)
        if estimated_time > get_long_completion_threshold():
            return (
                True,
                f"Slow download speed (≤{Config.TASK_MONITOR_SPEED_THRESHOLD}KB/s) with estimated completion time over {get_long_completion_threshold() // 3600} hours.",
            )

    # Case 4: Zero progress for extended period
    # Check if speed is consistently 0 and elapsed time is significant
    speed = await get_task_speed(task)
    if speed == 0 and elapsed_time > get_elapsed_time_threshold():
        # Check if we have enough data points and all are zero
        if gid in task_speeds and len(task_speeds[gid]) >= get_consecutive_checks():
            if all(s == 0 for s in task_speeds[gid]):
                # Special handling for different task types
                # Give more time to specific task types
                if (
                    is_ytdlp_task(task) or is_jd_task(task) or is_nzb_task(task)
                ) and elapsed_time < get_elapsed_time_threshold() * 1.5:
                    # These task types might take longer to start
                    return False, ""

                return (
                    True,
                    f"No download progress for {elapsed_time // 60} minutes. Task appears to be stalled.",
                )

    return False, ""


async def should_queue_task(task_type: str) -> tuple[bool, str]:
    """Determine if a task should be queued based on system resource usage."""
    # Check CPU usage
    if task_type == "cpu" and all(
        usage >= get_cpu_high_threshold() for usage in cpu_usage_history
    ):
        return True, f"High CPU usage ({cpu_usage_history[-1]}%) detected"

    # Check memory usage
    if task_type == "memory" and all(
        usage >= get_memory_high_threshold() for usage in memory_usage_history
    ):
        return True, f"High memory usage ({memory_usage_history[-1]}%) detected"

    return False, ""


async def can_resume_queued_tasks() -> tuple[bool, str]:
    """Check if queued tasks can be resumed based on system resources."""
    # Check CPU usage for resuming CPU-intensive tasks
    if all(usage <= get_cpu_low_threshold() for usage in cpu_usage_history):
        return True, "cpu"

    # Check memory usage for resuming memory-intensive tasks
    if all(usage <= get_memory_low_threshold() for usage in memory_usage_history):
        return True, "memory"

    return False, ""


async def identify_resource_intensive_tasks():
    """Identify CPU and memory intensive tasks."""
    global cpu_intensive_tasks, memory_intensive_tasks

    # Reset lists
    cpu_intensive_tasks = []
    memory_intensive_tasks = []

    async with task_dict_lock:
        for mid, task in task_dict.items():
            # Skip already queued tasks
            if mid in queued_by_monitor:
                continue

            try:
                # Skip tasks that are already being cancelled
                if (
                    hasattr(task, "listener")
                    and hasattr(task.listener, "is_cancelled")
                    and task.listener.is_cancelled
                ):
                    continue

                # Check if task has status method
                if not hasattr(task, "status") or not callable(task.status):
                    continue

                # Identify CPU-intensive tasks (FFmpeg, archive/extract operations)
                status = (
                    await task.status()
                    if asyncio.iscoroutinefunction(task.status)
                    else task.status()
                )

                if status in [
                    MirrorStatus.STATUS_FFMPEG,
                    MirrorStatus.STATUS_CONVERT,
                    MirrorStatus.STATUS_COMPRESS,
                ] or status in [
                    MirrorStatus.STATUS_ARCHIVE,
                    MirrorStatus.STATUS_EXTRACT,
                ]:
                    cpu_intensive_tasks.append((mid, "cpu"))

                # Identify memory-intensive tasks (large downloads, uploads)
                if status in [
                    MirrorStatus.STATUS_DOWNLOAD,
                    MirrorStatus.STATUS_UPLOAD,
                ]:
                    # Check if task has size method
                    if not hasattr(task, "size") or not callable(task.size):
                        continue

                    try:
                        # Check if task is handling large files (>1GB)
                        size_str = task.size()
                        size = (
                            speed_string_to_bytes(size_str)
                            if isinstance(size_str, str)
                            else size_str
                        )
                        if size > 1024 * 1024 * 1024:  # 1GB
                            memory_intensive_tasks.append((mid, "memory"))
                    except Exception:
                        pass
            except Exception:
                pass


async def queue_task(mid: int, reason: str):
    """Queue a task due to resource constraints."""
    try:
        async with task_dict_lock:
            if mid not in task_dict:
                return

            task = task_dict[mid]

            # Check if task has listener attribute
            if not hasattr(task, "listener"):
                return

            listener = task.listener

            # Check if task is already cancelled
            if hasattr(listener, "is_cancelled") and listener.is_cancelled:
                return

            # Mark as queued by monitor
            queued_by_monitor.add(mid)

            # Check if task is already queued by global queue system
            if await is_task_in_global_queue(mid):
                LOGGER.debug(
                    f"Task {mid} is already queued by global queue system, not queuing again"
                )
                queued_by_monitor.discard(mid)
                return

            # Add to appropriate queue
            async with queue_dict_lock:
                if mid in non_queued_dl:
                    non_queued_dl.remove(mid)
                    queued_dl[mid] = asyncio.Event()
                    LOGGER.info(
                        f"Queued download task {listener.name} due to {reason}"
                    )
                elif mid in non_queued_up:
                    non_queued_up.remove(mid)
                    queued_up[mid] = asyncio.Event()
                    LOGGER.info(
                        f"Queued upload task {listener.name} due to {reason}"
                    )
                else:
                    # Task is not in any queue, can't queue it
                    queued_by_monitor.discard(mid)
                    return

            # Notify user
            if hasattr(listener, "message"):
                # Get user tag for notifications
                user_tag = (
                    f"@{listener.user.username}"
                    if hasattr(listener.user, "username") and listener.user.username
                    else f"<a href='tg://user?id={listener.user_id}'>{listener.user_id}</a>"
                )

                queue_msg = await send_message(
                    listener.message,
                    f"⚠️ <b>Task Queued</b> ⚠️\n\n"
                    f"<b>Name:</b> <code>{listener.name}</code>\n"
                    f"<b>Reason:</b> {reason}\n\n"
                    f"Task will resume automatically when system resources are available.\n\n"
                    f"{user_tag}",
                )

                # Auto-delete queue message after 5 minutes
                if not isinstance(queue_msg, str):
                    create_task(auto_delete_message(queue_msg, time=300))
    except Exception as e:
        LOGGER.error(f"Error queuing task {mid}: {e}")


async def resume_queued_tasks(resource_type: str):
    """Resume tasks that were queued due to resource constraints."""
    try:
        tasks_to_resume = []

        # Identify tasks to resume based on resource type
        if resource_type == "cpu":
            for mid, task_type in cpu_intensive_tasks:
                if mid in queued_by_monitor and task_type == "cpu":
                    tasks_to_resume.append(mid)
        elif resource_type == "memory":
            for mid, task_type in memory_intensive_tasks:
                if mid in queued_by_monitor and task_type == "memory":
                    tasks_to_resume.append(mid)

        if not tasks_to_resume:
            return

        # Check global queue limits before resuming tasks
        dl_count = 0
        up_count = 0
        all_count = 0

        async with queue_dict_lock:
            dl_count = len(non_queued_dl)
            up_count = len(non_queued_up)
            all_count = dl_count + up_count

        # Calculate how many tasks we can resume based on queue limits
        dl_slots_available = (
            0
            if not Config.QUEUE_DOWNLOAD
            else max(0, Config.QUEUE_DOWNLOAD - dl_count)
        )
        up_slots_available = (
            0 if not Config.QUEUE_UPLOAD else max(0, Config.QUEUE_UPLOAD - up_count)
        )
        all_slots_available = (
            0 if not Config.QUEUE_ALL else max(0, Config.QUEUE_ALL - all_count)
        )

        # Prepare lists of tasks to resume by type
        dl_tasks_to_resume = []
        up_tasks_to_resume = []

        # Categorize tasks by type (download or upload)
        async with queue_dict_lock:
            for mid in tasks_to_resume:
                if mid in queued_dl:
                    dl_tasks_to_resume.append(mid)
                elif mid in queued_up:
                    up_tasks_to_resume.append(mid)

        # Limit the number of tasks to resume based on available slots
        if Config.QUEUE_ALL:
            # If we have a global limit, we need to prioritize tasks
            total_to_resume = min(
                len(dl_tasks_to_resume) + len(up_tasks_to_resume),
                all_slots_available,
            )

            # Prioritize downloads over uploads (can be adjusted based on preference)
            dl_to_resume = min(
                len(dl_tasks_to_resume),
                dl_slots_available if Config.QUEUE_DOWNLOAD else float("inf"),
                total_to_resume,
            )

            up_to_resume = min(
                len(up_tasks_to_resume),
                up_slots_available if Config.QUEUE_UPLOAD else float("inf"),
                total_to_resume - dl_to_resume,
            )

            dl_tasks_to_resume = dl_tasks_to_resume[:dl_to_resume]
            up_tasks_to_resume = up_tasks_to_resume[:up_to_resume]
        else:
            # If no global limit, just respect individual limits
            if Config.QUEUE_DOWNLOAD:
                dl_tasks_to_resume = dl_tasks_to_resume[:dl_slots_available]

            if Config.QUEUE_UPLOAD:
                up_tasks_to_resume = up_tasks_to_resume[:up_slots_available]

        # Resume the selected tasks
        async with queue_dict_lock:
            # Resume download tasks
            for mid in dl_tasks_to_resume:
                try:
                    if mid in queued_dl:
                        queued_dl[mid].set()
                        del queued_dl[mid]
                        non_queued_dl.add(mid)
                        LOGGER.info(f"Resuming queued download task {mid}")
                        # Remove from queued_by_monitor
                        queued_by_monitor.discard(mid)
                except Exception as e:
                    LOGGER.error(f"Error resuming download task {mid}: {e}")

            # Resume upload tasks
            for mid in up_tasks_to_resume:
                try:
                    if mid in queued_up:
                        queued_up[mid].set()
                        del queued_up[mid]
                        non_queued_up.add(mid)
                        LOGGER.info(f"Resuming queued upload task {mid}")
                        # Remove from queued_by_monitor
                        queued_by_monitor.discard(mid)
                except Exception as e:
                    LOGGER.error(f"Error resuming upload task {mid}: {e}")
    except Exception as e:
        LOGGER.error(f"Error in resume_queued_tasks: {e}")


async def cancel_task(task, gid: str, reason: str):
    """Cancel a task with the given reason."""
    try:
        LOGGER.info(f"Cancelling task {task.listener.name}: {reason}")

        # Get user tag for notifications
        user_tag = (
            f"@{task.listener.user.username}"
            if hasattr(task.listener.user, "username")
            and task.listener.user.username
            else f"<a href='tg://user?id={task.listener.user_id}'>{task.listener.user_id}</a>"
        )

        # Notify user before cancellation
        cancel_msg = await send_message(
            task.listener.message,
            f"⚠️ <b>Task Cancelled</b> ⚠️\n\n"
            f"<b>Name:</b> <code>{task.listener.name}</code>\n"
            f"<b>Reason:</b> {reason}\n\n"
            f"<b>This task was automatically cancelled by the system.</b>\n\n"
            f"{user_tag}",
        )

        # Auto-delete cancellation message after 5 minutes
        if not isinstance(cancel_msg, str):
            create_task(auto_delete_message(cancel_msg, time=300))

        # Cancel the task
        if hasattr(task, "cancel_task") and callable(task.cancel_task):
            await task.cancel_task()
        else:
            # Fallback: Mark as cancelled and let the task handle it
            task.listener.is_cancelled = True

        # Clean up task_warnings to prevent memory leaks
        task_warnings.pop(gid, None)

    except Exception as e:
        LOGGER.error(f"Error cancelling task: {e}")


async def monitor_tasks():
    try:
        # Log task monitor activity periodically (every 10 minutes)
        if time.time() % 600 < 1:
            LOGGER.info(
                f"Task monitor active. Monitoring {len(task_dict)} tasks. "
                + f"Queue stats: DL={len(non_queued_dl)}/{len(queued_dl)}, "
                + f"UP={len(non_queued_up)}/{len(queued_up)}, "
                + f"Monitor queued={len(queued_by_monitor)}"
            )

        # Update system resource usage history
        try:
            cpu_usage_history.append(psutil.cpu_percent())
            memory_usage_history.append(psutil.virtual_memory().percent)

            # Check thread usage
            high_thread_usage = monitor_thread_usage()
            if high_thread_usage:
                # If thread usage is high, force garbage collection
                LOGGER.warning(
                    "High thread usage detected, forcing garbage collection"
                )
                smart_garbage_collection(aggressive=True)
        except Exception as e:
            LOGGER.error(f"Error getting system resource usage: {e}")
            # Use default values if we can't get actual usage
            cpu_usage_history.append(0)
            memory_usage_history.append(0)

        # Clean up task_warnings for tasks that no longer exist
        async with task_dict_lock:
            active_gids = set(task_dict.keys())
            for gid in list(task_warnings.keys()):
                if gid not in active_gids:
                    del task_warnings[gid]

        # Identify resource-intensive tasks
        await identify_resource_intensive_tasks()

        # Check if we can resume any queued tasks
        can_resume, resource_type = await can_resume_queued_tasks()
        if can_resume and queued_by_monitor:
            await resume_queued_tasks(resource_type)

        # Monitor active tasks
        async with task_dict_lock:
            # Make a copy of the task_dict to avoid modification during iteration
            tasks_to_check = list(task_dict.items())

        # Process tasks outside the lock to minimize lock contention
        for gid, task in tasks_to_check:
            try:
                # Skip tasks without listener attribute
                if not hasattr(task, "listener"):
                    continue

                # Skip tasks that are already queued by the monitor
                if task.listener.mid in queued_by_monitor:
                    continue

                # Skip tasks that are queued by the global queue system
                if await is_task_in_global_queue(task.listener.mid):
                    LOGGER.debug(
                        f"Task {task.listener.mid} is queued by global queue system, skipping monitoring"
                    )
                    continue

                # Skip tasks that are already being cancelled
                if (
                    hasattr(task.listener, "is_cancelled")
                    and task.listener.is_cancelled
                ):
                    continue

                # Check if task should be cancelled
                should_cancel, cancel_reason = await should_cancel_task(task, gid)
                if should_cancel:
                    # Verify task is still in task_dict before cancelling
                    async with task_dict_lock:
                        if gid not in task_dict:
                            continue
                    await cancel_task(task, gid, cancel_reason)
                    continue

                # Send warning if needed but not already sent
                if (
                    gid in task_warnings
                    and task_warnings[gid]["warning_sent"]
                    and not should_cancel
                ):
                    if not task_warnings[gid].get("notification_sent", False):
                        # Verify task has message attribute
                        if not hasattr(task.listener, "message"):
                            continue

                        # Get user tag for notifications
                        user_tag = (
                            f"@{task.listener.user.username}"
                            if hasattr(task.listener.user, "username")
                            and task.listener.user.username
                            else f"<a href='tg://user?id={task.listener.user_id}'>{task.listener.user_id}</a>"
                        )

                        # Send warning notification to user
                        warning_msg = await send_message(
                            task.listener.message,
                            f"⚠️ <b>Task Warning</b> ⚠️\n\n"
                            f"<b>Name:</b> <code>{task.listener.name}</code>\n"
                            f"<b>Issue:</b> {task_warnings[gid]['reason']}\n\n"
                            f"<b>This task will be automatically cancelled in {get_wait_time_before_cancel() // 60} minutes "
                            f"if not manually cancelled.</b>\n\n"
                            f"{user_tag}",
                        )
                        # Auto-delete warning message after 5 minutes
                        if not isinstance(warning_msg, str):
                            create_task(auto_delete_message(warning_msg, time=300))
                        task_warnings[gid]["notification_sent"] = True

                # Check if task should be queued due to system resource constraints
                for task_info in cpu_intensive_tasks + memory_intensive_tasks:
                    mid, task_type = task_info
                    if mid == task.listener.mid:
                        should_queue, queue_reason = await should_queue_task(
                            task_type
                        )
                        if should_queue:
                            # Verify task is still in task_dict before queuing
                            async with task_dict_lock:
                                if gid not in task_dict:
                                    continue
                            await queue_task(mid, queue_reason)
                            break
            except Exception as e:
                LOGGER.error(f"Error processing task {gid}: {e}")

        # Add periodic memory cleanup
        if time.time() % 300 < 1:  # Every ~5 minutes
            # Use our smart garbage collection utility
            # Check if memory usage is high (>75%)
            memory_percent = memory_usage_history[-1] if memory_usage_history else 0
            smart_garbage_collection(aggressive=memory_percent > 75)
            log_memory_usage()
    except Exception as e:
        LOGGER.error(f"Error in task monitoring: {e}")


async def start_monitoring():
    """Start the task monitoring loop."""
    LOGGER.info("Starting task monitoring system")

    # Initial garbage collection and memory usage logging
    smart_garbage_collection(aggressive=False)
    log_memory_usage()

    while True:
        if Config.TASK_MONITOR_ENABLED:
            await monitor_tasks()
        await asyncio.sleep(get_check_interval())
