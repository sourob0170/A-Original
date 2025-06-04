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

# Optimized imports and caching
from functools import lru_cache
from typing import Final

import psutil

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

# Pre-computed constants for O(1) access
STARTUP_PHASE_DURATION: Final[int] = 300  # 5 minutes
RESOURCE_CACHE_DURATION: Final[float] = 2.0  # 2 seconds
THREAD_CHECK_INTERVAL_MULTIPLIER: Final[int] = 5
MEMORY_CLEANUP_INTERVAL: Final[int] = 300  # 5 minutes
GB_IN_BYTES: Final[int] = 1024 * 1024 * 1024

# Pre-compiled status sets for O(1) membership testing
DOWNLOAD_STATUSES: Final[frozenset] = frozenset(
    [
        MirrorStatus.STATUS_DOWNLOAD,
        MirrorStatus.STATUS_QUEUEDL,
    ]
)

CPU_INTENSIVE_STATUSES: Final[frozenset] = frozenset(
    [
        MirrorStatus.STATUS_FFMPEG,
        MirrorStatus.STATUS_CONVERT,
        MirrorStatus.STATUS_COMPRESS,
        MirrorStatus.STATUS_ARCHIVE,
        MirrorStatus.STATUS_EXTRACT,
    ]
)

MEMORY_INTENSIVE_STATUSES: Final[frozenset] = frozenset(
    [
        MirrorStatus.STATUS_DOWNLOAD,
        MirrorStatus.STATUS_UPLOAD,
    ]
)


# Shared resource management system
class ResourceConstraint:
    """Unified resource constraint levels"""

    NORMAL = "normal"
    MODERATE = "moderate"
    CRITICAL = "critical"


class SystemResourceManager:
    """Optimized centralized system resource monitoring and constraint management"""

    __slots__ = (
        "_cached_constraint",
        "_cached_cpu",
        "_cached_memory",
        "_last_check_time",
        "_last_usage_check",
        "_startup_time",
    )

    def __init__(self):
        self._startup_time = time.time()
        self._last_check_time = 0.0
        self._cached_constraint = ResourceConstraint.NORMAL
        self._cached_cpu = 0.0
        self._cached_memory = 0.0
        self._last_usage_check = 0.0

    def is_startup_phase(self) -> bool:
        """Check if we're in startup phase (first 5 minutes) - O(1)"""
        return (time.time() - self._startup_time) < STARTUP_PHASE_DURATION

    def get_resource_usage(self) -> tuple[float, float]:
        """Get current CPU and memory usage percentages with caching"""
        current_time = time.time()

        # Use cached values if recent enough (1 second cache for usage)
        if (current_time - self._last_usage_check) < 1.0:
            return self._cached_cpu, self._cached_memory

        try:
            # Use non-blocking CPU sampling to reduce overhead
            self._cached_cpu = psutil.cpu_percent(interval=None)
            self._cached_memory = psutil.virtual_memory().percent
            self._last_usage_check = current_time
            return self._cached_cpu, self._cached_memory
        except Exception as e:
            LOGGER.error(f"Error getting system resource usage: {e}")
            return 0.0, 0.0

    def get_resource_constraint(self, force_refresh: bool = False) -> str:
        """Get current resource constraint level with optimized caching"""
        current_time = time.time()

        # Use cached result if recent enough and not forced refresh
        if (
            not force_refresh
            and (current_time - self._last_check_time) < RESOURCE_CACHE_DURATION
        ):
            return self._cached_constraint

        cpu_percent, memory_percent = self.get_resource_usage()

        # Optimized constraint calculation using pre-computed thresholds
        if self.is_startup_phase():
            # Startup phase thresholds (more lenient)
            if memory_percent > 95.0 or cpu_percent > 98.0:
                constraint = ResourceConstraint.CRITICAL
            elif memory_percent > 85.0 or cpu_percent > 90.0:
                constraint = ResourceConstraint.MODERATE
            else:
                constraint = ResourceConstraint.NORMAL
        # Normal operation thresholds
        elif memory_percent > 85.0 or cpu_percent > 90.0:
            constraint = ResourceConstraint.CRITICAL
        elif memory_percent > 75.0 or cpu_percent > 80.0:
            constraint = ResourceConstraint.MODERATE
        else:
            constraint = ResourceConstraint.NORMAL

        # Cache the result
        self._cached_constraint = constraint
        self._last_check_time = current_time

        return constraint

    def get_max_tasks_for_constraint(self, constraint: str) -> int:
        """Get maximum number of tasks allowed for given constraint level"""
        if constraint == ResourceConstraint.CRITICAL:
            return 1
        if constraint == ResourceConstraint.MODERATE:
            return 2
        return float("inf")  # No limit for normal conditions

    def should_force_queue_task(self) -> tuple[bool, str]:
        """Check if new tasks should be forced to queue due to critical resources"""
        self.get_resource_constraint()
        cpu_percent, memory_percent = self.get_resource_usage()
        startup_phase = self.is_startup_phase()

        if startup_phase:
            # More lenient during startup
            should_queue = memory_percent > 95 or cpu_percent > 98
        else:
            # Normal operation thresholds
            should_queue = memory_percent > 90 or cpu_percent > 95

        if should_queue:
            reason = (
                f"System resources critical: Memory {memory_percent:.1f}%, CPU {cpu_percent:.1f}%. "
                f"{'(Startup phase)' if startup_phase else ''}"
            )

            # Detailed analysis will be handled by task manager for consolidated logging
            # This avoids duplicate logs while still providing comprehensive information

            return True, reason

        return False, ""

    def _get_detailed_resource_analysis(self) -> str:
        """Get detailed system resource analysis for debugging high usage"""
        try:
            analysis_parts = []

            # System-wide resource info
            cpu_count = psutil.cpu_count(logical=True)
            cpu_count_physical = psutil.cpu_count(logical=False)
            cpu_freq = psutil.cpu_freq()

            analysis_parts.append(
                f"CPU: {cpu_count} logical cores ({cpu_count_physical} physical)"
            )
            if cpu_freq:
                analysis_parts.append(
                    f"CPU Freq: {cpu_freq.current:.0f}MHz (max: {cpu_freq.max:.0f}MHz)"
                )

            # Memory details
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()
            analysis_parts.append(
                f"Memory: {memory.used / 1024**3:.1f}GB/{memory.total / 1024**3:.1f}GB used ({memory.percent:.1f}%)"
            )
            analysis_parts.append(
                f"Available: {memory.available / 1024**3:.1f}GB, Swap: {swap.used / 1024**3:.1f}GB/{swap.total / 1024**3:.1f}GB ({swap.percent:.1f}%)"
            )

            # Process-specific analysis
            current_process = psutil.Process()
            process_memory = current_process.memory_info()
            process_cpu = current_process.cpu_percent()
            thread_count = current_process.num_threads()

            analysis_parts.append(
                f"Bot Process: {process_memory.rss / 1024**2:.1f}MB RSS, {process_memory.vms / 1024**2:.1f}MB VMS"
            )
            analysis_parts.append(
                f"Bot CPU: {process_cpu:.1f}%, Threads: {thread_count}"
            )

            # Top memory consuming processes - enhanced with better error handling
            try:
                processes = []
                process_count = 0
                analysis_parts.append("Scanning processes...")

                # Try to get process list with more robust error handling
                for proc in psutil.process_iter(
                    ["pid", "name", "memory_percent", "cpu_percent"]
                ):
                    try:
                        process_count += 1
                        proc_info = proc.info

                        # Check if we have valid data
                        if (
                            proc_info
                            and proc_info.get("memory_percent", 0) is not None
                            and proc_info.get("memory_percent", 0) > 0.5
                        ):  # Lower threshold for better visibility
                            processes.append(
                                {
                                    "pid": proc_info.get("pid", "unknown"),
                                    "name": proc_info.get("name", "unknown"),
                                    "memory_percent": proc_info.get(
                                        "memory_percent", 0
                                    ),
                                    "cpu_percent": proc_info.get("cpu_percent", 0),
                                }
                            )

                    except (
                        psutil.NoSuchProcess,
                        psutil.AccessDenied,
                        psutil.ZombieProcess,
                    ):
                        continue
                    except Exception:
                        # Log individual process errors for debugging
                        continue

                analysis_parts.append(
                    f"Scanned {process_count} processes, found {len(processes)} with >0.5% memory"
                )

                if processes:
                    # Sort by CPU usage first (since that's our main concern), then by memory
                    processes.sort(
                        key=lambda x: (x["cpu_percent"], x["memory_percent"]),
                        reverse=True,
                    )
                    top_processes = processes[
                        :8
                    ]  # Show more processes to identify CPU hogs

                    analysis_parts.append("Top Resource Consumers:")
                    for i, proc in enumerate(top_processes, 1):
                        analysis_parts.append(
                            f"  {i}. {proc['name']} (PID {proc['pid']}): {proc['memory_percent']:.1f}% mem, {proc['cpu_percent']:.1f}% cpu"
                        )
                else:
                    analysis_parts.append(
                        "No high-resource processes found (possible permission issue)"
                    )

            except Exception as e:
                analysis_parts.append(f"Process analysis failed: {e!s}")

                # Only try alternative approaches when resources are EXTREMELY high
                # Check current resource usage to decide if we should show detailed analysis
                try:
                    cpu_percent, memory_percent = (
                        resource_manager.get_resource_usage()
                    )
                    if cpu_percent > 95 or memory_percent > 90:
                        analysis_parts.append(
                            "🚨 ATTEMPTING ALTERNATIVE PROCESS ANALYSIS (EXTREMELY HIGH RESOURCES)"
                        )

                        # Method 1: Try ps command with different options
                        try:
                            import subprocess

                            result = subprocess.run(
                                ["ps", "aux", "--sort=-pcpu"],
                                capture_output=True,
                                text=True,
                                timeout=5,
                                check=False,
                            )
                            if result.returncode == 0:
                                lines = result.stdout.split("\n")[
                                    1:8
                                ]  # Skip header, get top 7
                                analysis_parts.append(
                                    "🔍 Top CPU processes (via ps aux):"
                                )
                                for line in lines:
                                    if line.strip():
                                        parts = line.split()
                                        if len(parts) >= 11:
                                            analysis_parts.append(
                                                f"  📊 {parts[10]} (PID {parts[1]}): {parts[2]}% cpu, {parts[3]}% mem"
                                            )
                        except Exception as ps_error:
                            analysis_parts.append(f"ps aux failed: {ps_error!s}")

                        # Method 2: Try simpler ps command
                        try:
                            import subprocess

                            result = subprocess.run(
                                ["ps", "-eo", "pid,pcpu,pmem,comm", "--sort=-pcpu"],
                                capture_output=True,
                                text=True,
                                timeout=5,
                                check=False,
                            )
                            if result.returncode == 0:
                                lines = result.stdout.split("\n")[
                                    1:6
                                ]  # Skip header, get top 5
                                analysis_parts.append(
                                    "🔍 Top processes (via ps -eo):"
                                )
                                for line in lines:
                                    if line.strip():
                                        parts = line.split()
                                        if len(parts) >= 4:
                                            analysis_parts.append(
                                                f"  📊 {parts[3]} (PID {parts[0]}): {parts[1]}% cpu, {parts[2]}% mem"
                                            )
                        except Exception as ps2_error:
                            analysis_parts.append(f"ps -eo failed: {ps2_error!s}")

                        # Method 3: Try to get current process children info
                        try:
                            current_process = psutil.Process()
                            children = current_process.children(recursive=True)
                            if children:
                                analysis_parts.append(
                                    f"🚨 Bot child processes: {len(children)}"
                                )
                                for i, child in enumerate(children[:5], 1):
                                    try:
                                        child_name = child.name()
                                        child_cpu = child.cpu_percent()
                                        child_mem = child.memory_info().rss / 1024**2
                                        child_cmdline = (
                                            " ".join(child.cmdline()[:2])
                                            if child.cmdline()
                                            else "unknown"
                                        )
                                        analysis_parts.append(
                                            f"  🔍 Child {i}: {child_name} (PID {child.pid}) | CMD: {child_cmdline} | {child_cpu:.1f}% cpu, {child_mem:.1f}MB"
                                        )
                                    except Exception:
                                        analysis_parts.append(
                                            f"  ❌ Child {i}: PID {child.pid} (access denied)"
                                        )
                        except Exception as child_error:
                            analysis_parts.append(
                                f"Child process analysis failed: {child_error!s}"
                            )
                    else:
                        analysis_parts.append(
                            "Alternative analysis skipped - resources not extremely high"
                        )
                except Exception:
                    # Fallback if we can't check resource usage
                    analysis_parts.append(
                        "Could not determine resource levels for alternative analysis"
                    )

                # Method 4: Try /proc filesystem if available (always show this as it's lightweight)
                try:
                    import os

                    if os.path.exists("/proc/loadavg"):
                        with open("/proc/loadavg") as f:
                            loadavg = f.read().strip()
                            analysis_parts.append(f"Load from /proc: {loadavg}")
                except Exception:
                    pass

            # System load and additional info
            try:
                if hasattr(psutil, "getloadavg"):
                    load_avg = psutil.getloadavg()
                    if load_avg and len(load_avg) >= 3:
                        analysis_parts.append(
                            f"Load avg: {load_avg[0]:.2f}, {load_avg[1]:.2f}, {load_avg[2]:.2f}"
                        )
                    else:
                        analysis_parts.append("Load avg: unavailable")
                else:
                    analysis_parts.append("Load avg: not supported on this platform")
            except Exception as e:
                analysis_parts.append(f"Load avg error: {str(e)[:30]}")

            # Boot time to understand system uptime
            try:
                boot_time = psutil.boot_time()
                uptime_seconds = time.time() - boot_time
                uptime_hours = uptime_seconds / 3600
                analysis_parts.append(f"System uptime: {uptime_hours:.1f}h")
            except Exception:
                pass

            # Disk I/O if available
            try:
                disk_io = psutil.disk_io_counters()
                if disk_io:
                    analysis_parts.append(
                        f"Disk I/O: {disk_io.read_bytes / 1024**2:.1f}MB read, {disk_io.write_bytes / 1024**2:.1f}MB written"
                    )
            except Exception:
                pass

            # Network I/O if available
            try:
                net_io = psutil.net_io_counters()
                if net_io:
                    analysis_parts.append(
                        f"Network I/O: {net_io.bytes_recv / 1024**2:.1f}MB received, {net_io.bytes_sent / 1024**2:.1f}MB sent"
                    )
            except Exception:
                pass

            return " | ".join(analysis_parts)

        except Exception as e:
            return f"Resource analysis failed: {e}"


# Global resource manager instance
resource_manager = SystemResourceManager()


# Optimized configuration getters with caching
@lru_cache(maxsize=1)
def get_check_interval():
    return Config.TASK_MONITOR_INTERVAL


@lru_cache(maxsize=1)
def get_speed_threshold():
    return Config.TASK_MONITOR_SPEED_THRESHOLD * 1024  # Convert KB/s to bytes


@lru_cache(maxsize=1)
def get_consecutive_checks():
    return Config.TASK_MONITOR_CONSECUTIVE_CHECKS


@lru_cache(maxsize=1)
def get_elapsed_time_threshold():
    return Config.TASK_MONITOR_ELAPSED_THRESHOLD


@lru_cache(maxsize=1)
def get_long_eta_threshold():
    return Config.TASK_MONITOR_ETA_THRESHOLD


@lru_cache(maxsize=1)
def get_wait_time_before_cancel():
    return Config.TASK_MONITOR_WAIT_TIME


@lru_cache(maxsize=1)
def get_long_completion_threshold():
    return Config.TASK_MONITOR_COMPLETION_THRESHOLD


@lru_cache(maxsize=1)
def get_cpu_high_threshold():
    return Config.TASK_MONITOR_CPU_HIGH


@lru_cache(maxsize=1)
def get_cpu_low_threshold():
    return Config.TASK_MONITOR_CPU_LOW


@lru_cache(maxsize=1)
def get_memory_high_threshold():
    return Config.TASK_MONITOR_MEMORY_HIGH


@lru_cache(maxsize=1)
def get_memory_low_threshold():
    return Config.TASK_MONITOR_MEMORY_LOW


# Optimized monitoring data structures with fixed sizes
_consecutive_checks = get_consecutive_checks()  # Cache this value

# Use fixed-size deques for better memory efficiency
task_speeds: dict[str, deque[int]] = defaultdict(
    lambda: deque(maxlen=_consecutive_checks)
)
task_warnings: dict[str, dict] = {}
cpu_usage_history: deque[float] = deque(maxlen=_consecutive_checks)
memory_usage_history: deque[float] = deque(maxlen=_consecutive_checks)
queued_by_monitor: set[int] = set()  # Store tasks queued by the monitor

# Use sets for O(1) lookups instead of lists
cpu_intensive_tasks: set[int] = set()  # Just store mids for O(1) operations
memory_intensive_tasks: set[int] = set()  # Just store mids for O(1) operations


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


# Optimized task type checking with minimal attribute access
def is_ytdlp_task(task) -> bool:
    """Check if a task is a YT-DLP task - optimized."""
    listener = getattr(task, "listener", None)
    return listener is not None and getattr(listener, "is_ytdlp", False)


def is_jd_task(task) -> bool:
    """Check if a task is a JDownloader task - optimized."""
    return getattr(task, "tool", None) == "jd"


def is_nzb_task(task) -> bool:
    """Check if a task is an NZB task - optimized."""
    return getattr(task, "tool", None) == "nzb"


def is_streamrip_task(task) -> bool:
    """Check if a task is a Streamrip task - optimized."""
    return getattr(task, "tool", None) == "streamrip"


def is_zotify_task(task) -> bool:
    """Check if a task is a Zotify task - optimized."""
    return getattr(task, "tool", None) == "zotify"


def is_youtube_task(task) -> bool:
    """Check if a task is a YouTube upload task - optimized."""
    return getattr(task, "tool", None) == "youtube"


# Cache for task type results to avoid repeated checks
_task_type_cache: dict[int, str] = {}


def get_task_type(task) -> str:
    """Get task type with caching for better performance."""
    task_id = id(task)
    if task_id in _task_type_cache:
        return _task_type_cache[task_id]

    # Determine task type once and cache it
    if is_ytdlp_task(task):
        task_type = "ytdlp"
    elif is_jd_task(task):
        task_type = "jd"
    elif is_nzb_task(task):
        task_type = "nzb"
    elif is_streamrip_task(task):
        task_type = "streamrip"
    elif is_zotify_task(task):
        task_type = "zotify"
    elif is_youtube_task(task):
        task_type = "youtube"
    else:
        task_type = "generic"

    _task_type_cache[task_id] = task_type
    return task_type


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
    elif is_streamrip_task(task):
        # Streamrip tasks might have variable speeds due to platform differences
        threshold = threshold * 0.7  # More lenient threshold for music downloads
    elif is_zotify_task(task):
        # Zotify tasks might have variable speeds due to Spotify API limitations
        threshold = threshold * 0.7  # More lenient threshold for Spotify downloads
    elif is_youtube_task(task):
        # YouTube uploads might have variable speeds due to API limitations and processing
        threshold = threshold * 0.6  # More lenient threshold for YouTube uploads

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

        # Monitor both download and upload tasks
        # Check for all relevant download and upload statuses including specific task types
        monitored_statuses = [
            MirrorStatus.STATUS_DOWNLOAD,
            MirrorStatus.STATUS_QUEUEDL,
            MirrorStatus.STATUS_UPLOAD,
            MirrorStatus.STATUS_QUEUEUP,
        ]

        # Skip monitoring for tasks that are not in monitored states
        if status not in monitored_statuses:
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

        # Check if it's a Streamrip task
        if is_streamrip_task(task):
            # Streamrip tasks might have variable speeds due to platform differences
            # Give them more time before considering cancellation
            if task_elapsed_time < get_elapsed_time_threshold() * 0.6:
                return False, ""

        # Check if it's a Zotify task
        if is_zotify_task(task):
            # Zotify tasks might have variable speeds due to Spotify API limitations
            # Give them more time before considering cancellation
            if task_elapsed_time < get_elapsed_time_threshold() * 0.6:
                return False, ""

        # Check if it's a YouTube upload task
        if is_youtube_task(task):
            # YouTube uploads might have variable speeds due to API limitations and processing
            # Give them more time before considering cancellation
            if task_elapsed_time < get_elapsed_time_threshold() * 0.8:
                return False, ""

        # Check if task is queued by global queue system
        # Don't cancel tasks that are queued by the global queue system
        if hasattr(task.listener, "mid"):
            mid = task.listener.mid
            if await is_task_in_global_queue(mid):
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
            f"Slow transfer speed (≤{Config.TASK_MONITOR_SPEED_THRESHOLD}KB/s) with long estimated completion time.",
        )

    # Case 3: Slow download + estimated completion > 4h
    if is_slow:
        estimated_time = await estimate_completion_time(task)
        if estimated_time > get_long_completion_threshold():
            return (
                True,
                f"Slow transfer speed (≤{Config.TASK_MONITOR_SPEED_THRESHOLD}KB/s) with estimated completion time over {get_long_completion_threshold() // 3600} hours.",
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
                    is_ytdlp_task(task)
                    or is_jd_task(task)
                    or is_nzb_task(task)
                    or is_streamrip_task(task)
                    or is_zotify_task(task)
                    or is_youtube_task(task)
                ) and elapsed_time < get_elapsed_time_threshold() * 1.5:
                    # These task types might take longer to start
                    return False, ""

                return (
                    True,
                    f"No progress for {elapsed_time // 60} minutes. Task appears to be stalled.",
                )

    return False, ""


async def should_queue_task(task_type: str) -> tuple[bool, str]:
    """Determine if a task should be queued based on system resource usage."""
    # Check CPU usage
    if (
        task_type == "cpu"
        and cpu_usage_history
        and all(usage >= get_cpu_high_threshold() for usage in cpu_usage_history)
    ):
        try:
            latest_cpu = list(cpu_usage_history)[-1]
            return True, f"High CPU usage ({latest_cpu}%) detected"
        except (IndexError, TypeError):
            return True, "High CPU usage detected"

    # Check memory usage
    if (
        task_type == "memory"
        and memory_usage_history
        and all(
            usage >= get_memory_high_threshold() for usage in memory_usage_history
        )
    ):
        try:
            latest_memory = list(memory_usage_history)[-1]
            return True, f"High memory usage ({latest_memory}%) detected"
        except (IndexError, TypeError):
            return True, "High memory usage detected"

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
    """Optimized identification of CPU and memory intensive tasks."""
    global cpu_intensive_tasks, memory_intensive_tasks

    # Clear sets efficiently
    cpu_intensive_tasks.clear()
    memory_intensive_tasks.clear()

    async with task_dict_lock:
        for mid, task in task_dict.items():
            # Skip already queued tasks - O(1) lookup
            if mid in queued_by_monitor:
                continue

            try:
                # Quick cancellation check with optimized attribute access
                listener = getattr(task, "listener", None)
                if listener and getattr(listener, "is_cancelled", False):
                    continue

                # Quick status method check
                status_method = getattr(task, "status", None)
                if not callable(status_method):
                    continue

                # Get status efficiently
                status = (
                    await status_method()
                    if asyncio.iscoroutinefunction(status_method)
                    else status_method()
                )

                # CPU-intensive task identification using pre-compiled sets - O(1)
                if status in CPU_INTENSIVE_STATUSES:
                    cpu_intensive_tasks.add(mid)
                    continue  # Skip further checks for this task

                # Music download tasks can be CPU-intensive - optimized check
                if status == MirrorStatus.STATUS_DOWNLOAD:
                    task_type = get_task_type(task)  # Use cached task type
                    if task_type in ("streamrip", "zotify"):
                        cpu_intensive_tasks.add(mid)

                # YouTube upload tasks can be CPU-intensive due to video processing
                if status == MirrorStatus.STATUS_UPLOAD:
                    task_type = get_task_type(task)  # Use cached task type
                    if task_type == "youtube":
                        cpu_intensive_tasks.add(mid)

                # Memory-intensive task identification - O(1) status check
                if status in MEMORY_INTENSIVE_STATUSES:
                    size_method = getattr(task, "size", None)
                    if callable(size_method):
                        try:
                            # Optimized size checking
                            size_str = size_method()
                            size = (
                                speed_string_to_bytes(size_str)
                                if isinstance(size_str, str)
                                else size_str
                            )
                            if size > GB_IN_BYTES:  # Use pre-computed constant
                                memory_intensive_tasks.add(mid)
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

        # Update system resource usage history using shared resource manager
        try:
            # Get resource usage from shared resource manager
            cpu_percent, memory_percent = resource_manager.get_resource_usage()
            cpu_usage_history.append(cpu_percent)
            memory_usage_history.append(memory_percent)

            # Log detailed analysis only when resources are EXTREMELY high for sustained periods
            if (
                len(cpu_usage_history) >= 5 and len(memory_usage_history) >= 5
            ):  # Need at least 5 readings for better accuracy
                try:
                    recent_cpu_avg = sum(list(cpu_usage_history)[-5:]) / 5
                    recent_memory_avg = sum(list(memory_usage_history)[-5:]) / 5
                except (TypeError, IndexError) as e:
                    LOGGER.debug(f"Error calculating resource averages: {e}")
                    recent_cpu_avg = cpu_percent
                    recent_memory_avg = memory_percent

                # Only log when resources are EXTREMELY high (95%+ CPU or 90%+ Memory) for sustained period
                if recent_cpu_avg > 95 or recent_memory_avg > 90:
                    if not hasattr(monitor_tasks, "_last_detailed_log"):
                        monitor_tasks._last_detailed_log = 0

                    current_time = time.time()
                    # Log detailed analysis every 10 minutes when resources are EXTREMELY high
                    if current_time - monitor_tasks._last_detailed_log > 600:
                        detailed_analysis = _get_monitor_resource_analysis()
                        LOGGER.warning(
                            "🚨 EXTREMELY HIGH SUSTAINED RESOURCE USAGE - NEEDS INVESTIGATION"
                        )
                        LOGGER.warning(
                            f"📈 5-cycle averages: CPU {recent_cpu_avg:.1f}%, Memory {recent_memory_avg:.1f}%"
                        )
                        LOGGER.warning(
                            f"📊 ROOT CAUSE ANALYSIS: {detailed_analysis}"
                        )
                        monitor_tasks._last_detailed_log = current_time

            # Check thread usage less frequently to reduce overhead
            current_time = time.time()
            if not hasattr(monitor_tasks, "_last_thread_check"):
                monitor_tasks._last_thread_check = 0

            # Only check thread usage every 5 monitoring cycles to reduce overhead
            if current_time - monitor_tasks._last_thread_check > (
                get_check_interval() * 5
            ):
                high_thread_usage = monitor_thread_usage()
                monitor_tasks._last_thread_check = current_time
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

                # Check if task should be queued due to system resource constraints - optimized
                task_mid = task.listener.mid
                if task_mid in cpu_intensive_tasks:
                    should_queue, queue_reason = await should_queue_task("cpu")
                    if should_queue:
                        # Verify task is still in task_dict before queuing
                        async with task_dict_lock:
                            if gid not in task_dict:
                                continue
                        await queue_task(task_mid, queue_reason)
                        continue
                elif task_mid in memory_intensive_tasks:
                    should_queue, queue_reason = await should_queue_task("memory")
                    if should_queue:
                        # Verify task is still in task_dict before queuing
                        async with task_dict_lock:
                            if gid not in task_dict:
                                continue
                        await queue_task(task_mid, queue_reason)
                        continue
            except Exception as e:
                LOGGER.error(f"Error processing task {gid}: {e}")

        # Add periodic memory cleanup - optimized timing
        current_time = time.time()
        if not hasattr(monitor_tasks, "_last_cleanup_time"):
            monitor_tasks._last_cleanup_time = 0

        if (
            current_time - monitor_tasks._last_cleanup_time
        ) >= MEMORY_CLEANUP_INTERVAL:
            # Use our smart garbage collection utility
            # Check if memory usage is high (>75%) using cached value
            try:
                memory_percent = (
                    list(memory_usage_history)[-1] if memory_usage_history else 0
                )
            except (IndexError, TypeError):
                memory_percent = 0
            smart_garbage_collection(aggressive=memory_percent > 75.0)
            log_memory_usage()
            monitor_tasks._last_cleanup_time = current_time
    except Exception as e:
        LOGGER.error(f"Error in task monitoring: {e}")


async def start_monitoring():
    """Start the task monitoring loop."""
    LOGGER.info("Starting task monitoring system")

    # Initial garbage collection and memory usage logging (less aggressive during startup)
    smart_garbage_collection(aggressive=False)
    log_memory_usage()

    # Start monitoring immediately without waiting
    LOGGER.info("Starting task monitoring immediately...")

    # Start with longer intervals and gradually reduce them
    startup_phase = True
    startup_cycles = 0
    max_startup_cycles = 10  # First 10 cycles use longer intervals

    while True:
        if Config.TASK_MONITOR_ENABLED:
            # Use longer intervals during startup phase to reduce resource usage
            if startup_phase:
                interval = get_check_interval() * 3  # 3x longer during startup
                startup_cycles += 1
                if startup_cycles >= max_startup_cycles:
                    startup_phase = False
                    LOGGER.info(
                        "Task monitoring startup phase completed, switching to normal intervals"
                    )
            else:
                # Check system resources and adjust monitoring frequency using shared resource manager
                try:
                    constraint = resource_manager.get_resource_constraint()
                    cpu_percent, memory_percent = (
                        resource_manager.get_resource_usage()
                    )

                    # Adjust monitoring interval based on resource constraint level
                    if constraint == ResourceConstraint.CRITICAL:
                        interval = (
                            get_check_interval() * 3
                        )  # Triple interval under critical stress
                        LOGGER.debug(
                            f"System critically stressed (CPU: {cpu_percent:.1f}%, Memory: {memory_percent:.1f}%), using much longer monitoring interval"
                        )
                    elif constraint == ResourceConstraint.MODERATE:
                        interval = (
                            get_check_interval() * 2
                        )  # Double interval under moderate stress
                        LOGGER.debug(
                            f"System moderately stressed (CPU: {cpu_percent:.1f}%, Memory: {memory_percent:.1f}%), using longer monitoring interval"
                        )
                    else:
                        interval = get_check_interval()  # Normal interval
                except Exception:
                    interval = get_check_interval()

            await monitor_tasks()
            await asyncio.sleep(interval)
        else:
            await asyncio.sleep(get_check_interval())


def _get_monitor_resource_analysis() -> str:
    """Get detailed resource analysis for task monitoring"""
    try:
        analysis_parts = []

        # Task monitoring specific analysis with safe history access
        try:
            cpu_history = list(cpu_usage_history)[-5:] if cpu_usage_history else [0]
            memory_history = (
                list(memory_usage_history)[-5:] if memory_usage_history else [0]
            )
            analysis_parts.append(
                f"CPU history (last 5): {[f'{x:.1f}' for x in cpu_history]}"
            )
            analysis_parts.append(
                f"Memory history (last 5): {[f'{x:.1f}' for x in memory_history]}"
            )
        except Exception as e:
            analysis_parts.append(f"History analysis error: {str(e)[:30]}")

        # Enhanced child process monitoring - ONLY when resources are EXTREMELY high
        try:
            # Only show detailed child analysis when CPU >95% or Memory >90%
            cpu_percent, memory_percent = resource_manager.get_resource_usage()
            if cpu_percent > 95 or memory_percent > 90:
                current_process = psutil.Process()
                children = current_process.children(recursive=True)
                if children:
                    analysis_parts.append(
                        f"🚨 CHILD PROCESS ANALYSIS (HIGH RESOURCES): {len(children)} children found"
                    )

                    # Get detailed info for each child with robust error handling
                    child_cpu_total = 0
                    for i, child in enumerate(children, 1):
                        try:
                            # Initialize defaults
                            child_pid = getattr(child, "pid", "unknown")
                            child_name = "unknown"
                            child_cpu = 0
                            child_mem = 0
                            child_status = "unknown"
                            child_cmdline = "unknown"
                            child_age = 0

                            # Try to get each piece of info individually
                            try:
                                child_name = child.name()
                            except (
                                psutil.NoSuchProcess,
                                psutil.AccessDenied,
                                psutil.ZombieProcess,
                            ):
                                child_name = "access_denied"
                            except Exception:
                                child_name = "error_name"

                            try:
                                child_cpu = child.cpu_percent()
                            except (
                                psutil.NoSuchProcess,
                                psutil.AccessDenied,
                                psutil.ZombieProcess,
                            ):
                                child_cpu = 0
                            except Exception:
                                child_cpu = 0

                            try:
                                child_mem = child.memory_info().rss / 1024**2
                            except (
                                psutil.NoSuchProcess,
                                psutil.AccessDenied,
                                psutil.ZombieProcess,
                            ):
                                child_mem = 0
                            except Exception:
                                child_mem = 0

                            try:
                                child_status = child.status()
                            except (
                                psutil.NoSuchProcess,
                                psutil.AccessDenied,
                                psutil.ZombieProcess,
                            ):
                                child_status = "access_denied"
                            except Exception:
                                child_status = "error_status"

                            try:
                                cmdline_list = child.cmdline()
                                if cmdline_list:
                                    child_cmdline = " ".join(cmdline_list[:3])
                                else:
                                    child_cmdline = "no_cmdline"
                            except (
                                psutil.NoSuchProcess,
                                psutil.AccessDenied,
                                psutil.ZombieProcess,
                            ):
                                child_cmdline = "access_denied"
                            except Exception:
                                child_cmdline = "error_cmdline"

                            try:
                                child_create_time = child.create_time()
                                child_age = time.time() - child_create_time
                            except (
                                psutil.NoSuchProcess,
                                psutil.AccessDenied,
                                psutil.ZombieProcess,
                            ):
                                child_age = 0
                            except Exception:
                                child_age = 0

                            child_cpu_total += child_cpu

                            analysis_parts.append(
                                f"  🔍 CHILD-{i}: {child_name} | PID {child_pid} | "
                                f"CPU {child_cpu:.1f}% | MEM {child_mem:.1f}MB | "
                                f"STATUS {child_status} | AGE {child_age:.0f}s | "
                                f"CMD: {child_cmdline[:40]}"
                            )
                        except (
                            psutil.NoSuchProcess,
                            psutil.AccessDenied,
                            psutil.ZombieProcess,
                        ):
                            analysis_parts.append(
                                f"  ❌ CHILD-{i}: PID {getattr(child, 'pid', 'unknown')} | PROCESS_GONE"
                            )
                        except Exception as child_err:
                            analysis_parts.append(
                                f"  ❌ CHILD-{i}: PID {getattr(child, 'pid', 'unknown')} | ERROR: {str(child_err)[:30]}"
                            )

                    analysis_parts.append(
                        f"🔥 TOTAL CHILD CPU: {child_cpu_total:.1f}%"
                    )
            else:
                # Just show basic child count when resources are not extremely high
                current_process = psutil.Process()
                children = current_process.children(recursive=True)
                if children:
                    analysis_parts.append(
                        f"Child processes: {len(children)} (details hidden - resources not critical)"
                    )
        except Exception as child_analysis_error:
            analysis_parts.append(f"Child analysis failed: {child_analysis_error!s}")

        # Active task analysis
        async def get_active_task_analysis():
            async with task_dict_lock:
                task_analysis = []
                for gid, task in list(task_dict.items())[
                    :5
                ]:  # Analyze first 5 tasks
                    try:
                        listener = getattr(task, "listener", None)
                        if listener:
                            status_method = getattr(task, "status", None)
                            if callable(status_method):
                                status = (
                                    await status_method()
                                    if asyncio.iscoroutinefunction(status_method)
                                    else status_method()
                                )
                                task_analysis.append(f"{gid[:8]}:{status}")
                    except Exception:
                        pass
                return task_analysis

        # Since we're in sync context, get basic task info
        try:
            analysis_parts.append(f"Active tasks: {len(task_dict)}")
            analysis_parts.append(f"CPU intensive: {len(cpu_intensive_tasks)}")
            analysis_parts.append(f"Memory intensive: {len(memory_intensive_tasks)}")
            analysis_parts.append(f"Queued by monitor: {len(queued_by_monitor)}")
        except Exception:
            analysis_parts.append("Task analysis failed")

        # System load analysis
        try:
            if hasattr(psutil, "getloadavg"):
                load_avg = psutil.getloadavg()
                if load_avg and len(load_avg) >= 3:
                    analysis_parts.append(
                        f"Load avg: {load_avg[0]:.2f}, {load_avg[1]:.2f}, {load_avg[2]:.2f}"
                    )
                else:
                    analysis_parts.append("Load avg: unavailable")
            else:
                analysis_parts.append("Load avg: not supported on this platform")
        except Exception as e:
            analysis_parts.append(f"Load avg error: {str(e)[:30]}")

        # Disk usage analysis
        try:
            disk_usage = psutil.disk_usage("/")
            disk_percent = (disk_usage.used / disk_usage.total) * 100
            analysis_parts.append(f"Disk usage: {disk_percent:.1f}%")
        except Exception:
            pass

        # Process count
        try:
            process_count = len(psutil.pids())
            analysis_parts.append(f"Total processes: {process_count}")
        except Exception:
            pass

        # Memory pressure indicators
        try:
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()

            # Calculate memory pressure score
            memory_pressure = 0
            if memory.percent > 90:
                memory_pressure += 3
            elif memory.percent > 80:
                memory_pressure += 2
            elif memory.percent > 70:
                memory_pressure += 1

            if swap.percent > 50:
                memory_pressure += 2
            elif swap.percent > 25:
                memory_pressure += 1

            analysis_parts.append(f"Memory pressure score: {memory_pressure}/5")
        except Exception:
            pass

        return " | ".join(analysis_parts)

    except Exception as e:
        return f"Monitor analysis failed: {e}"
