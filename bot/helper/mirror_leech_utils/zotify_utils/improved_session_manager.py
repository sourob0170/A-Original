"""
Optimized Zotify Session Manager
Lightweight session management with minimal memory footprint
"""

import asyncio
import contextlib
import time
import weakref
from typing import Any

from zotify import Session

from bot import LOGGER
from bot.helper.mirror_leech_utils.zotify_utils.zotify_config import zotify_config

# Reduced memory footprint - smaller caches
_active_sessions: set[weakref.ref] = set()
_api_call_cache = {}
_cache_timestamps = {}
MAX_CACHE_SIZE = 50  # Reduced from 100
CACHE_TTL = 180  # Reduced from 300 to 3 minutes


class ImprovedZotifySessionManager:
    """Optimized session manager with minimal resource usage"""

    def __init__(self):
        self._session: Session | None = None
        self._session_created_at = 0
        self._session_max_age = 7200  # Increased to 2 hours to prevent session timeout during long downloads
        self._last_api_call = 0
        self._last_activity = 0
        self._inactivity_timeout = (
            1800  # Increased to 30 minutes for active downloads
        )
        self._api_call_interval = 0.5  # Reduced interval for better performance
        self._consecutive_failures = 0
        self._max_consecutive_failures = 8  # Increased for better resilience
        # Simplified memory management
        self._memory_cleanup_interval = 600  # Increased to 10 minutes
        self._last_memory_cleanup = 0
        # Thread safety
        self._session_lock = asyncio.Lock()
        # Download state tracking
        self._is_downloading = False
        self._download_start_time = 0
        # Connection health tracking
        self._last_connection_check = 0
        self._connection_check_interval = (
            300  # Check connection every 5 minutes during downloads
        )
        self._packet_failures = 0
        self._max_packet_failures = 3  # Allow more packet failures before recreation
        # Register for cleanup tracking
        _active_sessions.add(weakref.ref(self, self._cleanup_callback))

    async def get_session(self) -> Session | None:
        """Get a healthy session with optimized refresh logic"""
        current_time = time.time()

        # Enhanced session health check - don't recreate during active downloads
        session_age = current_time - self._session_created_at
        should_recreate = (
            not self._session
            or (not self._is_downloading and session_age > self._session_max_age)
            or (
                self._is_downloading and session_age > self._session_max_age * 3
            )  # Triple timeout during downloads for better stability
            or self._consecutive_failures >= self._max_consecutive_failures
        )

        if should_recreate:
            await self._create_new_session()

        # Update activity timestamp
        self._last_activity = current_time

        # Check connection health during downloads
        if self._is_downloading:
            health_ok = await self.check_connection_health()
            if not health_ok:
                LOGGER.warning("Connection health check failed, recreating session")
                await self._create_new_session()

        # Less frequent memory cleanup, skip during downloads
        if (
            not self._is_downloading
            and current_time - self._last_memory_cleanup
            > self._memory_cleanup_interval
        ):
            self._cleanup_memory_sync()
            self._last_memory_cleanup = current_time

        return self._session

    def mark_inline_search_activity(self):
        """Mark inline search activity"""
        self._last_activity = time.time()

    def keep_session_alive(self):
        """Keep session alive during long downloads by updating activity timestamp"""
        if self._is_downloading:
            self._last_activity = time.time()
            LOGGER.debug("Session keep-alive ping during download")

    def mark_download_start(self):
        """Mark the start of a download to prevent session timeout"""
        self._is_downloading = True
        self._download_start_time = time.time()
        self._last_activity = time.time()
        # Reset packet failure counter at start of new download
        self._packet_failures = 0
        LOGGER.info("Download started - session timeout protection enabled")

    def mark_download_end(self):
        """Mark the end of a download"""
        self._is_downloading = False
        self._download_start_time = 0
        self._last_activity = time.time()
        # Reset packet failure counter on successful download completion
        self._packet_failures = 0
        LOGGER.info("Download ended - normal session timeout restored")

    def should_cleanup_for_inactivity(self) -> bool:
        """Check if session should be cleaned up due to inactivity"""
        if self._last_activity > 0:
            return time.time() - self._last_activity > self._inactivity_timeout
        return False

    def handle_packet_failure(self) -> bool:
        """Handle packet reading failures and determine if session should be recreated"""
        self._packet_failures += 1
        LOGGER.warning(
            f"Packet failure #{self._packet_failures}/{self._max_packet_failures}"
        )

        if self._packet_failures >= self._max_packet_failures:
            LOGGER.error("Too many packet failures, marking session for recreation")
            self._consecutive_failures = self._max_consecutive_failures
            self._packet_failures = 0  # Reset counter
            return True  # Should recreate session
        return False  # Continue with current session

    async def check_connection_health(self) -> bool:
        """Check connection health during downloads"""
        current_time = time.time()

        # Only check during downloads and at intervals
        if not self._is_downloading:
            return True

        if (
            current_time - self._last_connection_check
            < self._connection_check_interval
        ):
            return True

        self._last_connection_check = current_time

        # Simple health check - try to access session attributes
        if not self._session:
            return False

        try:
            # Check if session is still responsive
            if hasattr(self._session, "api") and self._session.api:
                LOGGER.info("Connection health check passed")
                return True
        except Exception as e:
            LOGGER.warning(f"Connection health check failed: {e}")
            return False

        return True

    @staticmethod
    def _cleanup_callback(weak_ref):
        """Cleanup callback for garbage collected sessions"""
        _active_sessions.discard(weak_ref)

    async def clear_session_cache(self):
        """Clear session and API cache to force credential reload"""
        try:
            if self._session:
                with contextlib.suppress(Exception):
                    self._session.close()
                self._session = None

            # Reset session state
            self._session_created_at = 0
            self._last_activity = 0
            self._consecutive_failures = 0

            # Clear API cache
            _api_call_cache.clear()
            _cache_timestamps.clear()

        except Exception as e:
            LOGGER.warning(f"Error clearing session cache: {e}")

    def _cleanup_memory_sync(self):
        """Synchronous memory cleanup - more efficient"""
        current_time = time.time()

        # Clean expired entries
        expired_keys = [
            key
            for key, timestamp in _cache_timestamps.items()
            if current_time - timestamp > CACHE_TTL
        ]
        for key in expired_keys:
            _api_call_cache.pop(key, None)
            _cache_timestamps.pop(key, None)

        # Limit cache size
        if len(_api_call_cache) > MAX_CACHE_SIZE:
            # Remove oldest entries
            sorted_items = sorted(_cache_timestamps.items(), key=lambda x: x[1])
            to_remove = len(_api_call_cache) - MAX_CACHE_SIZE
            for key, _ in sorted_items[:to_remove]:
                _api_call_cache.pop(key, None)
                _cache_timestamps.pop(key, None)

    async def _create_new_session(self) -> bool:
        """Create a new session with thread-safe optimized stability"""
        async with self._session_lock:  # Prevent concurrent session creation
            try:
                LOGGER.info("Creating Zotify session...")

                # Close existing session if any
                if self._session:
                    with contextlib.suppress(Exception):
                        self._session.close()
                    self._session = None

                # Create new session with fresh credentials from database
                auth_method = zotify_config.get_auth_method()

                if auth_method != "file":
                    LOGGER.error("Only file-based authentication is supported")
                    return False

                # Get owner ID for credential loading
                from bot.core.config_manager import Config

                owner_id = getattr(Config, "OWNER_ID", None)

                # Load credentials from database (this will also update the file)
                fresh_credentials = await zotify_config.load_credentials(owner_id)

                if not fresh_credentials:
                    raise Exception("No credentials available for session creation")

                credentials_path = zotify_config.get_credentials_path()
                language = zotify_config.get_language()

                # Suppress librespot core logs for cleaner output
                import logging

                librespot_logger = logging.getLogger("librespot.core")
                original_level = librespot_logger.level
                librespot_logger.setLevel(logging.ERROR)  # Suppress more logs

                try:
                    # Add delay to prevent rapid session creation and thread exhaustion
                    await asyncio.sleep(1.0)  # Increased delay

                    # Retry session creation with exponential backoff
                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            # Wrap blocking Session.from_file in thread
                            self._session = await asyncio.to_thread(
                                Session.from_file, credentials_path, language
                            )
                            break
                        except Exception as e:
                            if attempt < max_retries - 1:
                                wait_time = 2**attempt
                                LOGGER.warning(
                                    f"Session creation attempt {attempt + 1} failed: {e}. Retrying in {wait_time}s..."
                                )
                                await asyncio.sleep(wait_time)
                            else:
                                raise

                    # Add another delay after session creation
                    await asyncio.sleep(0.5)
                finally:
                    # Restore original logging level
                    librespot_logger.setLevel(original_level)

                if self._session:
                    current_time = time.time()
                    self._session_created_at = current_time
                    self._last_activity = current_time
                    self._consecutive_failures = 0
                    return True

                raise Exception("Session creation failed")

            except Exception as e:
                error_msg = str(e)
                # Handle thread exhaustion specifically
                if "can't start new thread" in error_msg:
                    LOGGER.error(
                        "Thread exhaustion detected - delaying session creation"
                    )
                    await asyncio.sleep(5.0)  # Wait longer for thread cleanup
                else:
                    LOGGER.error(f"Session creation failed: {error_msg}")

                self._consecutive_failures += 1
                return False

    async def _test_session(self):
        """Test session with a simple API call and enhanced error handling"""
        if not self._session:
            raise Exception("No session available")

        try:
            # Apply rate limiting before test - wrap in thread
            await asyncio.to_thread(self._session.rate_limiter.apply_limit)

            # Wrap API operations in threads
            api = await asyncio.to_thread(self._session.api)
            # Simple test call - get current user profile
            result = await asyncio.to_thread(api.invoke_url, "me")
            if not result:
                raise Exception("Session test failed - no response")

            # Verify we got valid user data
            if not isinstance(result, dict) or "id" not in result:
                raise Exception("Session test failed - invalid response format")

        except Exception as e:
            error_msg = str(e)
            # Provide more specific error messages for common issues
            if (
                "Failed reading packet" in error_msg
                or "Failed to receive packet" in error_msg
            ):
                raise Exception(
                    "Connection unstable - packet reading failed (librespot connection issue)"
                )
            if (
                "Connection reset by peer" in error_msg
                or "ConnectionResetError" in error_msg
            ):
                raise Exception(
                    "Connection reset by Spotify servers during session test"
                )
            if (
                "ConnectionRefusedError" in error_msg
                or "Connection refused" in error_msg
            ):
                raise Exception(
                    "Connection refused by Spotify servers during session test"
                )
            if "session-packet-receiver" in error_msg:
                raise Exception("Session packet receiver thread failed during test")
            if "RuntimeError" in error_msg and "packet" in error_msg.lower():
                raise Exception("Runtime packet error during session test")
            if "Bad file descriptor" in error_msg:
                raise Exception("Connection error - file descriptor issue")
            if "timeout" in error_msg.lower():
                raise Exception("Session test timed out - connection too slow")
            raise Exception(f"Session test failed: {error_msg}")

    async def robust_api_call(
        self, endpoint: str, max_retries: int = 3, cache_result: bool = True
    ) -> dict[Any, Any] | None:
        """Make API call with retry logic, rate limiting, and intelligent caching"""
        current_time = time.time()

        # Check cache first for cacheable endpoints
        cache_key = None
        if cache_result and not any(
            param in endpoint for param in ["me", "player", "currently-playing"]
        ):
            cache_key = f"api_{endpoint}"
            if cache_key in _api_call_cache and cache_key in _cache_timestamps:
                if current_time - _cache_timestamps[cache_key] < CACHE_TTL:
                    return _api_call_cache[cache_key]

        # Enforce rate limiting
        time_since_last_call = current_time - self._last_api_call
        if time_since_last_call < self._api_call_interval:
            await asyncio.sleep(self._api_call_interval - time_since_last_call)

        for attempt in range(max_retries):
            try:
                session = await self.get_session()
                if not session:
                    raise Exception("No healthy session available")

                # Wrap API operations in threads
                api = await asyncio.to_thread(session.api)
                result = await asyncio.to_thread(api.invoke_url, endpoint)

                # Update success tracking and activity
                current_time = time.time()
                self._last_api_call = current_time
                self._last_activity = (
                    current_time  # Update activity on successful API calls
                )
                self._consecutive_failures = 0

                # Cache the result if applicable
                if cache_key and result:
                    _api_call_cache[cache_key] = result
                    _cache_timestamps[cache_key] = current_time

                return result

            except Exception as e:
                self._consecutive_failures += 1
                error_msg = str(e)
                LOGGER.warning(f"API call attempt {attempt + 1} failed: {error_msg}")

                # Check for connection errors that indicate session needs recreation
                if any(
                    keyword in error_msg
                    for keyword in [
                        "Failed reading packet",
                        "Failed to receive packet",
                        "Connection reset by peer",
                        "ConnectionResetError",
                        "ConnectionRefusedError",
                        "Connection refused",
                        "session-packet-receiver",
                        "RuntimeError",
                    ]
                ):
                    # Handle packet failures more gracefully
                    if (
                        "Failed reading packet" in error_msg
                        or "Failed to receive packet" in error_msg
                    ):
                        should_recreate = self.handle_packet_failure()
                        if should_recreate:
                            LOGGER.warning(
                                "Too many packet failures - forcing session recreation"
                            )
                        else:
                            LOGGER.info(
                                "Packet failure handled, continuing with current session"
                            )
                            continue  # Retry with current session
                    else:
                        LOGGER.warning(
                            "Connection error detected in API call - marking session for recreation"
                        )
                        self._consecutive_failures = (
                            self._max_consecutive_failures
                        )  # Force session recreation

                if attempt < max_retries - 1:
                    # Adaptive backoff based on error type
                    if (
                        "Connection reset by peer" in error_msg
                        or "ConnectionResetError" in error_msg
                    ):
                        backoff = min(
                            (attempt + 1) * 2, 6
                        )  # Longer delay for connection resets
                    elif (
                        "ConnectionRefusedError" in error_msg
                        or "Connection refused" in error_msg
                    ):
                        backoff = min(
                            (attempt + 1) * 3, 9
                        )  # Even longer delay for refused connections
                    elif (
                        "session-packet-receiver" in error_msg
                        or "RuntimeError" in error_msg
                    ):
                        backoff = min(
                            (attempt + 1) * 2, 6
                        )  # Longer delay for thread/runtime errors
                    else:
                        backoff = min(
                            attempt + 1, 2
                        )  # Standard delay for other errors

                    await asyncio.sleep(backoff)
                else:
                    LOGGER.error(
                        f"API call failed after {max_retries} attempts: {endpoint}"
                    )

        return None

    async def search_with_fallback(
        self, query: str, content_types: list | None = None
    ) -> dict[str, list]:
        """Search with fallback for free account limitations"""
        if not content_types:
            content_types = ["track", "album", "playlist", "artist"]

        results = {}

        for content_type in content_types:
            try:
                # Use conservative limits for free accounts
                limit = 10 if content_type in ["track", "album"] else 5
                endpoint = f"search?q={query}&type={content_type}&limit={limit}"

                search_result = await self.robust_api_call(endpoint)

                if search_result and f"{content_type}s" in search_result:
                    items = search_result[f"{content_type}s"]["items"]
                    results[content_type] = items
                else:
                    results[content_type] = []

                # Add delay between different content type searches
                await asyncio.sleep(0.5)

            except Exception as e:
                LOGGER.error(f"Search failed for {content_type}: {e}")
                results[content_type] = []

        return results

    async def get_track_safe(self, track_id: str) -> Any | None:
        """Get track with error handling for free account limitations"""
        try:
            session = await self.get_session()
            if not session:
                return None

            # Apply rate limiting - wrap in thread
            await asyncio.to_thread(session.rate_limiter.apply_limit)

            # Get track - wrap in thread
            return await asyncio.to_thread(session.get_track, track_id)

        except Exception as e:
            LOGGER.error(f"Failed to get track {track_id}: {e}")
            return None

    async def get_episode_safe(self, episode_id: str) -> Any | None:
        """Get episode with error handling"""
        try:
            session = await self.get_session()
            if not session:
                return None

            # Apply rate limiting - wrap in thread
            await asyncio.to_thread(session.rate_limiter.apply_limit)

            # Get episode - wrap in thread
            return await asyncio.to_thread(session.get_episode, episode_id)

        except Exception as e:
            LOGGER.error(f"Failed to get episode {episode_id}: {e}")
            return None

    def get_session_health(self) -> dict[str, Any]:
        """Get session health information including inactivity tracking"""
        current_time = time.time()
        session_age = current_time - self._session_created_at if self._session else 0
        time_since_activity = (
            current_time - self._last_activity if self._last_activity else 0
        )

        return {
            "has_session": self._session is not None,
            "session_age_seconds": session_age,
            "consecutive_failures": self._consecutive_failures,
            "time_since_last_api_call": current_time - self._last_api_call,
            "time_since_last_activity": time_since_activity,
            "inactivity_timeout": self._inactivity_timeout,
            "is_healthy": (
                self._session is not None
                and self._consecutive_failures < self._max_consecutive_failures
                and session_age < self._session_max_age
                and time_since_activity < self._inactivity_timeout
            ),
        }

    async def force_session_recreation(self):
        """Force recreation of the session due to connection issues"""
        LOGGER.info("Forcing session recreation due to connection issues")
        self._consecutive_failures = self._max_consecutive_failures
        if self._session:
            try:
                self._session.close()
            except Exception as e:
                LOGGER.warning(
                    f"Error closing session during forced recreation: {e}"
                )
            finally:
                self._session = None
        await self._create_new_session()

    async def close(self):
        """Clean up session"""
        if self._session:
            try:
                self._session.close()
            except Exception as e:
                LOGGER.warning(f"Error closing session: {e}")
            finally:
                self._session = None


# Global instance
improved_session_manager = ImprovedZotifySessionManager()

# Global cleanup task to prevent thread buildup
_cleanup_task = None


async def _periodic_cleanup():
    """Periodic cleanup to prevent thread and memory buildup"""
    while True:
        try:
            await asyncio.sleep(300)  # Run every 5 minutes

            # Clean up expired cache entries
            current_time = time.time()
            expired_keys = [
                key
                for key, timestamp in _cache_timestamps.items()
                if current_time - timestamp > CACHE_TTL
            ]
            for key in expired_keys:
                _api_call_cache.pop(key, None)
                _cache_timestamps.pop(key, None)

            # Force session cleanup if too old, but respect download state
            if improved_session_manager._session:
                session_age = (
                    current_time - improved_session_manager._session_created_at
                )
                max_age = improved_session_manager._session_max_age

                # Don't cleanup during active downloads - use more generous timeouts
                if improved_session_manager._is_downloading:
                    max_age *= 4  # Quadruple the timeout during downloads for better stability
                    download_duration = (
                        current_time - improved_session_manager._download_start_time
                    )

                    # For very long downloads, extend timeout even further
                    if download_duration > 3600:  # More than 1 hour
                        max_age *= 2  # Additional extension for long downloads

                if session_age > max_age:
                    if improved_session_manager._is_downloading:
                        LOGGER.info(
                            f"Session aged {session_age:.1f}s but download is active (duration: {download_duration:.1f}s), extending timeout to {max_age:.1f}s"
                        )
                    else:
                        LOGGER.info("Forcing session cleanup due to age")
                        with contextlib.suppress(Exception):
                            improved_session_manager._session.close()
                        improved_session_manager._session = None
                        improved_session_manager._session_created_at = 0

        except Exception as e:
            LOGGER.warning(f"Cleanup task error: {e}")


def start_cleanup_task():
    """Start the periodic cleanup task"""
    global _cleanup_task
    if _cleanup_task is None or _cleanup_task.done():
        _cleanup_task = asyncio.create_task(_periodic_cleanup())


# Start cleanup task when module is imported
try:
    start_cleanup_task()
except Exception:
    pass  # Ignore if event loop not running


# Convenience functions
async def get_improved_session() -> Session | None:
    """Get improved session instance"""
    return await improved_session_manager.get_session()


async def robust_search(
    query: str, content_types: list | None = None
) -> dict[str, list]:
    """Perform robust search with fallback"""
    return await improved_session_manager.search_with_fallback(query, content_types)


async def safe_api_call(
    endpoint: str, max_retries: int = 3
) -> dict[Any, Any] | None:
    """Make safe API call with retry logic"""
    return await improved_session_manager.robust_api_call(endpoint, max_retries)
