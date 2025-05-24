import contextlib
import gc
import logging
import os
import threading
import time
import tracemalloc

try:
    import psutil
except ImportError:
    psutil = None

try:
    import resource
except ImportError:
    resource = None

LOGGER = logging.getLogger(__name__)

# Track last garbage collection time to avoid too frequent collections
_last_gc_time = time.time()
_gc_interval = 60  # Default interval in seconds between forced collections

# Flag to enable/disable memory tracking for debugging
_memory_tracking_enabled = False


def force_garbage_collection(threshold_mb=100, log_stats=False, generation=None):
    """
    Force garbage collection if memory usage exceeds threshold or timer expired.

    Args:
        threshold_mb: Memory threshold in MB to trigger collection
        log_stats: Whether to log detailed statistics
        generation: Specific generation to collect (0, 1, 2, or None for all)

    Returns:
        bool: True if garbage collection was performed
    """
    global _last_gc_time

    # Check if enough time has passed since last collection
    current_time = time.time()
    time_since_last_gc = current_time - _last_gc_time

    # Get current memory usage
    try:
        global psutil
        if psutil is None:
            # If psutil is not available, collect based on time only
            if time_since_last_gc > _gc_interval:
                if generation is not None:
                    # Collect specific generation
                    gc.collect(generation)
                else:
                    # Collect all generations
                    gc.collect(0)
                    gc.collect(1)
                    gc.collect(2)
                _last_gc_time = current_time
                return True
            return False

        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        memory_mb = memory_info.rss / (1024 * 1024)

        # Decide whether to collect based on memory usage or time interval
        should_collect = (memory_mb > threshold_mb) or (
            time_since_last_gc > _gc_interval
        )

        if should_collect:
            # Run collection based on specified generation or full cycle
            if log_stats:
                # First run collection and get stats
                if generation is not None:
                    # Collect specific generation
                    collected = gc.collect(generation)
                    collected_gen0 = collected if generation == 0 else 0
                    collected_gen1 = collected if generation == 1 else 0
                    collected_gen2 = collected if generation == 2 else 0
                else:
                    # Collect all generations
                    collected_gen0 = gc.collect(0)  # Collect youngest generation
                    collected_gen1 = gc.collect(1)  # Collect middle generation
                    collected_gen2 = gc.collect(2)  # Collect oldest generation
                    (collected_gen0 + collected_gen1 + collected_gen2)

                # Get memory after collection
                memory_after = process.memory_info().rss / (1024 * 1024)
                max(0, memory_mb - memory_after)  # Avoid negative values

                # Only log if explicitly requested or if there's a significant memory issue
                # Log unreachable objects if there are any
                unreachable = gc.garbage
                if unreachable:
                    # Clear the list to avoid memory leaks
                    gc.garbage.clear()
            # Just collect without stats
            elif generation is not None:
                # Collect specific generation
                gc.collect(generation)
            else:
                # Collect all generations
                gc.collect(0)  # Collect youngest generation
                gc.collect(1)  # Collect middle generation
                gc.collect(2)  # Collect oldest generation

            # Update last collection time
            _last_gc_time = current_time
            return True
    except ImportError:
        # If psutil is not available, collect based on time only
        if time_since_last_gc > _gc_interval:
            if generation is not None:
                # Collect specific generation
                gc.collect(generation)
            else:
                # Collect all generations
                gc.collect(0)
                gc.collect(1)
                gc.collect(2)
            _last_gc_time = current_time
            return True
    except Exception as e:
        LOGGER.error(f"Error during garbage collection: {e}")
        # Try a simple collection even if there was an error
        try:
            if generation is not None:
                gc.collect(generation)
            else:
                gc.collect()
        except Exception as ex:
            LOGGER.error(f"Failed to perform fallback garbage collection: {ex}")

    return False


def start_memory_tracking():
    """Start tracking memory allocations for debugging."""
    global _memory_tracking_enabled

    try:
        tracemalloc.start()
        _memory_tracking_enabled = True
        LOGGER.info("Memory tracking started")
    except Exception as e:
        LOGGER.error(f"Failed to start memory tracking: {e}")


def stop_memory_tracking():
    """Stop tracking memory allocations."""
    global _memory_tracking_enabled

    if _memory_tracking_enabled:
        try:
            tracemalloc.stop()
            _memory_tracking_enabled = False
            LOGGER.info("Memory tracking stopped")
        except Exception as e:
            LOGGER.error(f"Failed to stop memory tracking: {e}")


def get_memory_snapshot():
    """Get current memory snapshot if tracking is enabled."""
    if not _memory_tracking_enabled:
        return None

    try:
        return tracemalloc.take_snapshot()
    except Exception as e:
        LOGGER.error(f"Failed to take memory snapshot: {e}")
        return None


def compare_memory_snapshots(old_snapshot, new_snapshot, limit=10):
    """
    Compare two memory snapshots and return the differences.

    Args:
        old_snapshot: Previous memory snapshot
        new_snapshot: Current memory snapshot
        limit: Number of top differences to return

    Returns:
        List of memory differences
    """
    if not old_snapshot or not new_snapshot:
        return []

    try:
        differences = new_snapshot.compare_to(old_snapshot, "lineno")
        return differences[:limit]
    except Exception as e:
        LOGGER.error(f"Failed to compare memory snapshots: {e}")
        return []


def log_memory_usage():
    """Log current memory usage information."""
    global psutil

    try:
        if psutil is None:
            return None

        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()

        # Calculate memory usage in MB
        rss_mb = memory_info.rss / (1024 * 1024)
        vms_mb = memory_info.vms / (1024 * 1024)

        # Get system memory info
        system_memory = psutil.virtual_memory()
        system_memory_percent = system_memory.percent

        # Only log if memory usage is high
        if system_memory_percent > 85:
            pass

        return {
            "rss_mb": rss_mb,
            "vms_mb": vms_mb,
            "system_percent": system_memory_percent,
        }
    except Exception as e:
        LOGGER.error(f"Error logging memory usage: {e}")
        return None


def set_gc_parameters(threshold=700, interval=60):
    """
    Configure garbage collection parameters.

    Args:
        threshold: Memory threshold in MB to trigger collection
        interval: Minimum time in seconds between collections
    """
    global _gc_interval

    try:
        # Set Python's GC thresholds
        # These control how many allocations trigger automatic collection
        current_thresholds = gc.get_threshold()

        # Only change if significantly different to avoid unnecessary changes
        if abs(current_thresholds[0] - threshold) > 50:
            gc.set_threshold(threshold, current_thresholds[1], current_thresholds[2])
        # Set our custom interval
        _gc_interval = interval
    except Exception as e:
        LOGGER.error(f"Failed to set garbage collection parameters: {e}")


def optimized_garbage_collection(aggressive=False, log_stats=False):
    """
    Perform an optimized garbage collection with minimal impact on performance.

    Args:
        aggressive: Whether to perform a more aggressive collection
        log_stats: Whether to log detailed statistics

    Returns:
        bool: True if collection was performed successfully
    """
    try:
        global psutil

        # Get memory before collection if we're logging stats
        memory_before = None
        if log_stats and psutil is not None:
            try:
                process = psutil.Process(os.getpid())
                memory_info = process.memory_info()
                memory_before = memory_info.rss / (1024 * 1024)
            except Exception:
                pass

        # First collect only generation 0 (youngest objects)
        # This is usually very fast and frees up most temporary objects
        collected_gen0 = gc.collect(0)

        # If we're in aggressive mode or if we collected many objects in gen0,
        # also collect generation 1
        collected_gen1 = 0
        collected_gen2 = 0
        if aggressive or collected_gen0 > 1000:
            collected_gen1 = gc.collect(1)

            # Only collect generation 2 (oldest, most expensive) if in aggressive mode
            # or if we collected many objects in gen1
            if aggressive or collected_gen1 > 100:
                collected_gen2 = gc.collect(2)

        # Clear any unreachable objects
        unreachable_count = 0
        if gc.garbage:
            unreachable_count = len(gc.garbage)
            gc.garbage.clear()

        # Log statistics if requested
        if log_stats and memory_before is not None:
            try:
                # Get memory after collection
                process = psutil.Process(os.getpid())
                memory_after = process.memory_info().rss / (1024 * 1024)
                max(0, memory_before - memory_after)  # Avoid negative values

                collected_gen0 + collected_gen1 + collected_gen2

                # Only log if significant memory was freed or in debug mode
                # Always log unreachable objects as they indicate potential memory leaks
                if unreachable_count > 0:
                    pass
            except Exception:
                pass

        return True
    except Exception as e:
        LOGGER.error(f"Error during optimized garbage collection: {e}")
        return False


def cleanup_large_objects():
    """
    Find and clean up large objects in memory.
    This is a more aggressive approach for when memory usage is critical.
    Optimized to use less memory during the cleanup process.
    """
    try:
        # Get memory before collection if psutil is available
        memory_before = None
        if psutil is not None:
            try:
                process = psutil.Process(os.getpid())
                memory_info = process.memory_info()
                memory_before = memory_info.rss / (1024 * 1024)
            except Exception:
                pass

        # Force a full collection first
        gc.collect()

        # Clear any unreachable objects
        if gc.garbage:
            gc.garbage.clear()

        # Instead of scanning all objects, which is memory intensive,
        # just do a thorough garbage collection of all generations
        gc.collect(0)
        gc.collect(1)
        gc.collect(2)

        # Log memory freed if psutil is available
        if memory_before is not None and psutil is not None:
            try:
                # Get memory after collection
                process = psutil.Process(os.getpid())
                memory_after = process.memory_info().rss / (1024 * 1024)
                memory_freed = max(
                    0, memory_before - memory_after
                )  # Avoid negative values

                # Only log if significant memory was freed (> 10MB)
                if memory_freed > 10:
                    LOGGER.debug(
                        f"Freed {memory_freed:.2f} MB during garbage collection"
                    )
            except Exception:
                pass

        return 1  # Return a simple success indicator
    except Exception as e:
        LOGGER.error(f"Error during garbage collection: {e}")
        # Try a simple collection even if there was an error
        with contextlib.suppress(Exception):
            gc.collect()
        return 0


def monitor_thread_usage():
    """
    Monitor thread usage and log warnings if approaching system limits.
    Returns True if thread usage is high, False otherwise.
    """
    try:
        # Get current thread count
        thread_count = threading.active_count()

        # Get system thread limit (ulimit -u)
        # This is a rough approximation and may not be accurate on all systems
        hard_limit = 1000  # Default fallback value

        try:
            if resource:
                _, hard_limit = resource.getrlimit(resource.RLIMIT_NPROC)
                if hard_limit == resource.RLIM_INFINITY:
                    # If unlimited, use a reasonable default based on system
                    hard_limit = os.cpu_count() * 100
        except (ImportError, AttributeError, OSError):
            # Default to a reasonable value if we can't get the actual limit
            hard_limit = 1000

        # Calculate percentage of thread usage
        usage_percent = (thread_count / hard_limit) * 100

        # Log warning if thread usage is high
        if usage_percent > 80:
            LOGGER.warning(
                f"High thread usage: {thread_count}/{hard_limit} ({usage_percent:.1f}%)"
            )
            return True
        if usage_percent > 60:
            LOGGER.info(
                f"Moderate thread usage: {thread_count}/{hard_limit} ({usage_percent:.1f}%)"
            )

        return usage_percent > 60  # Return True if usage is moderate or high
    except Exception as e:
        LOGGER.error(f"Error monitoring thread usage: {e}")
        return False


def smart_garbage_collection(
    aggressive=False, for_split_file=False, memory_error=False
):
    """
    Perform a smart garbage collection that adapts based on memory usage.
    This function decides whether to use optimized_garbage_collection or
    a more aggressive approach with cleanup_large_objects.

    Optimized to reduce memory overhead during collection.

    Args:
        aggressive: Whether to force aggressive collection regardless of memory usage
        for_split_file: Whether this is being called for a split file upload (more aggressive)

    Returns:
        bool: True if collection was performed successfully
    """
    try:
        # Check current memory usage if psutil is available
        memory_percent = 0
        if psutil is not None:
            try:
                memory = psutil.virtual_memory()
                memory_percent = memory.percent
            except Exception:
                pass

        # Check thread usage
        high_thread_usage = monitor_thread_usage()

        # If thread usage is high, be more aggressive with garbage collection
        if high_thread_usage:
            aggressive = True

        # For split files, always be more aggressive
        if for_split_file:
            aggressive = True

        # Decide which collection method to use based on memory pressure and thread usage

        # If this is a memory error recovery, use the most aggressive approach
        if memory_error:
            LOGGER.warning("Performing emergency memory cleanup after memory error")
            # Clear any unreachable objects first
            if gc.garbage:
                gc.garbage.clear()

            # Do a thorough collection of all generations
            gc.collect(0)
            gc.collect(1)
            gc.collect(2)

            # Try to free as much memory as possible
            cleanup_large_objects()

            # Try to reduce memory fragmentation
            try:
                import ctypes

                ctypes.CDLL("libc.so.6").malloc_trim(0)
                LOGGER.info("Performed malloc_trim to reduce memory fragmentation")
            except Exception as e:
                LOGGER.error(f"Failed to perform malloc_trim: {e}")

            return True

        # For high memory usage, thread issues, or forced aggressive mode
        if aggressive or memory_percent > 85 or high_thread_usage:
            # For very high memory usage, thread issues, or split files, do more thorough cleanup
            if memory_percent > 90 or for_split_file or high_thread_usage:
                # Clear any unreachable objects first
                if gc.garbage:
                    gc.garbage.clear()

                # Do a thorough collection
                cleanup_large_objects()
            else:
                # Just do an optimized collection for moderate high memory
                optimized_garbage_collection(aggressive=True, log_stats=False)

            return True
        if memory_percent > 70:  # Moderate memory usage
            # Use optimized collection without logging for better performance
            return optimized_garbage_collection(aggressive=False, log_stats=False)
        # Low memory usage
        # Just collect generation 0 (youngest objects) which is very fast
        gc.collect(0)
        return True

    except Exception as e:
        LOGGER.error(f"Error during smart garbage collection: {e}")
        # Try a simple collection as fallback
        try:
            gc.collect()
            return True
        except Exception:
            return False
