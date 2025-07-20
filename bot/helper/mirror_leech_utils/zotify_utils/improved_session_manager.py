"""
Improved Zotify Session Manager
Handles connection stability, rate limiting, and free account optimizations
"""

import asyncio
import contextlib
import gc
import time
import weakref
from typing import Any

from zotify import Session

from bot import LOGGER
from bot.helper.mirror_leech_utils.zotify_utils.zotify_config import zotify_config

# Memory optimization: Track active objects for cleanup
_active_sessions: set[weakref.ref] = set()
_api_call_cache = {}
_cache_timestamps = {}
MAX_CACHE_SIZE = 100
CACHE_TTL = 300  # 5 minutes


class ImprovedZotifySessionManager:
    """Enhanced session manager with stability improvements for free accounts"""

    def __init__(self):
        self._session: Session | None = None
        self._session_created_at = 0
        self._session_max_age = (
            3600  # 1 hour max age - but will be cleaned based on inactivity
        )
        self._last_api_call = 0
        self._last_activity = 0  # Track last activity for inactivity cleanup
        self._inactivity_timeout = 60  # 1 minute of inactivity before cleanup
        self._last_inline_search = 0  # Track last inline search activity
        self._inline_search_timeout = (
            60  # 1 minute of inactivity for inline searches
        )
        self._api_call_interval = 1.0  # Minimum 1 second between API calls
        self._consecutive_failures = 0
        self._max_consecutive_failures = 3
        self._backoff_time = 5.0
        # Memory optimization
        self._memory_cleanup_interval = 300  # 5 minutes
        self._last_memory_cleanup = 0
        # Register for cleanup tracking
        _active_sessions.add(weakref.ref(self, self._cleanup_callback))

    async def get_session(self) -> Session | None:
        """Get a healthy session with automatic refresh and inactivity cleanup"""
        current_time = time.time()

        # Check if session needs refresh due to age, failures, inactivity, or connection issues
        if (
            not self._session
            or current_time - self._session_created_at > self._session_max_age
            or current_time - self._last_activity > self._inactivity_timeout
            or self._consecutive_failures >= self._max_consecutive_failures
            or await self._is_session_unhealthy()
        ):
            await self._create_new_session()

        # Update activity timestamp
        self._last_activity = current_time

        # Periodic memory cleanup
        if current_time - self._last_memory_cleanup > self._memory_cleanup_interval:
            await self._cleanup_memory()
            self._last_memory_cleanup = current_time

        return self._session

    def mark_inline_search_activity(self):
        """Mark inline search activity to prevent connection cleanup"""
        current_time = time.time()
        self._last_inline_search = current_time
        self._last_activity = current_time
        LOGGER.debug("Marked inline search activity")

    def should_cleanup_for_inactivity(self) -> bool:
        """Check if session should be cleaned up due to inactivity"""
        current_time = time.time()

        # Check inline search activity first
        if self._last_inline_search > 0:
            inline_inactive_time = current_time - self._last_inline_search
            if inline_inactive_time < self._inline_search_timeout:
                return False

        # Check general activity
        if self._last_activity > 0:
            inactive_time = current_time - self._last_activity
            return inactive_time > self._inactivity_timeout

        return False

    async def _is_session_unhealthy(self) -> bool:
        """Check if the session has connection issues that require recreation"""
        if not self._session:
            return False

        try:
            # Quick health check - try to access session properties
            # If the session has background thread failures, this might fail
            if hasattr(self._session, "connection") and self._session.connection:
                # Check if connection is still valid
                return False
            LOGGER.debug("Session connection appears to be invalid")
            return True
        except Exception as e:
            error_msg = str(e)
            # Check for specific connection-related errors
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
                LOGGER.warning(
                    f"Session health check detected connection issue: {error_msg}"
                )
                return True
            return False

    @staticmethod
    def _cleanup_callback(weak_ref):
        """Cleanup callback for garbage collected sessions"""
        _active_sessions.discard(weak_ref)

    async def clear_session_cache(self):
        """Clear session and API cache to force credential reload"""
        try:
            # Clear current session
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

            # Force garbage collection
            gc.collect()

        except Exception as e:
            LOGGER.warning(f"Error clearing session cache: {e}")

    async def _cleanup_memory(self):
        """Perform memory cleanup operations"""
        try:
            # Clean API call cache
            current_time = time.time()
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

            # Force garbage collection
            gc.collect()

            LOGGER.debug(
                f"Memory cleanup completed. Cache size: {len(_api_call_cache)}"
            )
        except Exception as e:
            LOGGER.warning(f"Memory cleanup error: {e}")

    async def _create_new_session(self) -> bool:
        """Create a new session with retry logic"""
        max_retries = 3

        for attempt in range(max_retries):
            try:
                LOGGER.info(
                    f"Creating Zotify session (attempt {attempt + 1}/{max_retries})"
                )

                # Close existing session if any
                if self._session:
                    try:
                        self._session.close()
                    except Exception as e:
                        LOGGER.warning(f"Error closing old session: {e}")

                # Create new session with fresh credentials from database
                auth_method = zotify_config.get_auth_method()

                if auth_method == "file":
                    # CRITICAL: Load fresh credentials from database first

                    # Get owner ID for credential loading
                    from bot.core.config_manager import Config

                    owner_id = getattr(Config, "OWNER_ID", None)

                    # Load credentials from database (this will also update the file)
                    fresh_credentials = await zotify_config.load_credentials(
                        owner_id
                    )

                    if not fresh_credentials:
                        raise Exception(
                            "No credentials available for session creation"
                        )

                    fresh_credentials.get("username", "unknown")

                    credentials_path = zotify_config.get_credentials_path()
                    language = zotify_config.get_language()

                    # Suppress librespot core logs for cleaner output
                    import logging

                    librespot_logger = logging.getLogger("librespot.core")
                    original_level = librespot_logger.level
                    librespot_logger.setLevel(
                        logging.WARNING
                    )  # Only show warnings and errors

                    try:
                        self._session = Session.from_file(credentials_path, language)
                    finally:
                        # Restore original logging level
                        librespot_logger.setLevel(original_level)

                    # Test the session with a simple API call
                    await self._test_session()

                    current_time = time.time()
                    self._session_created_at = current_time
                    self._last_activity = (
                        current_time  # Initialize activity tracking
                    )
                    self._consecutive_failures = 0

                    return True
                LOGGER.error("Only file-based authentication is supported")
                return False

            except Exception as e:
                error_msg = str(e)
                LOGGER.error(
                    f"Session creation attempt {attempt + 1} failed: {error_msg}"
                )

                # Handle specific errors with better user feedback
                if (
                    "BadCredentials" in error_msg
                    or "error_code: BadCredentials" in error_msg
                ):
                    LOGGER.error(
                        "❌ Zotify authentication failed - Invalid or missing Spotify credentials"
                    )
                    LOGGER.error(
                        "Please check your Spotify credentials configuration:"
                    )
                    LOGGER.error(
                        "1. Ensure you have valid Spotify Premium account credentials"
                    )
                    LOGGER.error(
                        "2. Check that credentials file exists and is properly formatted"
                    )
                    LOGGER.error(
                        "3. Verify ZOTIFY_CREDENTIALS_PATH is set correctly"
                    )
                    # Don't retry for credential errors - they won't fix themselves
                    break
                if (
                    "Failed reading packet" in error_msg
                    or "Failed to receive packet" in error_msg
                ):
                    LOGGER.info(
                        "Connection packet error - librespot connection issue, retrying..."
                    )
                elif (
                    "Connection reset by peer" in error_msg
                    or "ConnectionResetError" in error_msg
                ):
                    LOGGER.info(
                        "Connection reset by Spotify servers - retrying with longer delay..."
                    )
                elif (
                    "ConnectionRefusedError" in error_msg
                    or "Connection refused" in error_msg
                ):
                    LOGGER.info(
                        "Connection refused by Spotify servers - retrying with backoff..."
                    )
                elif "session-packet-receiver" in error_msg:
                    LOGGER.info(
                        "Session packet receiver thread error - recreating session..."
                    )
                elif "Bad file descriptor" in error_msg:
                    LOGGER.info(
                        "Connection descriptor error - retrying with longer delay..."
                    )
                elif "Connection lost" in error_msg or "SSL" in error_msg:
                    LOGGER.info("Network connection error - retrying...")
                elif "RuntimeError" in error_msg and "packet" in error_msg.lower():
                    LOGGER.info(
                        "Runtime packet error - librespot internal issue, retrying..."
                    )

                if attempt < max_retries - 1:
                    # Don't retry for credential errors
                    if "BadCredentials" in error_msg:
                        break

                    # Adaptive delay based on error type
                    if (
                        "Connection reset by peer" in error_msg
                        or "ConnectionResetError" in error_msg
                    ):
                        delay = min(
                            (attempt + 1) * 2, 8
                        )  # Longer delay for connection resets
                    elif (
                        "ConnectionRefusedError" in error_msg
                        or "Connection refused" in error_msg
                    ):
                        delay = min(
                            (attempt + 1) * 3, 12
                        )  # Even longer delay for refused connections
                    elif (
                        "session-packet-receiver" in error_msg
                        or "RuntimeError" in error_msg
                    ):
                        delay = min(
                            (attempt + 1) * 2, 8
                        )  # Longer delay for thread/runtime errors
                    else:
                        delay = min(
                            attempt + 1, 3
                        )  # Standard delay for other errors

                    LOGGER.info(f"Retrying in {delay} seconds...")
                    await asyncio.sleep(delay)

        self._consecutive_failures = self._max_consecutive_failures
        LOGGER.error("Failed to create Zotify session after all retries")
        return False

    async def _test_session(self):
        """Test session with a simple API call and enhanced error handling"""
        if not self._session:
            raise Exception("No session available")

        try:
            # Apply rate limiting before test
            self._session.rate_limiter.apply_limit()

            api = self._session.api()
            # Simple test call - get current user profile
            result = api.invoke_url("me")
            if not result:
                raise Exception("Session test failed - no response")

            # Verify we got valid user data
            if not isinstance(result, dict) or "id" not in result:
                raise Exception("Session test failed - invalid response format")

            LOGGER.debug(
                f"Session test successful for user: {result.get('display_name', 'Unknown')}"
            )

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
                    LOGGER.debug(f"Using cached API result for: {endpoint}")
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

                api = session.api()
                result = api.invoke_url(endpoint)

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

            # Apply rate limiting
            session.rate_limiter.apply_limit()

            # Get track - use session.get_track() directly (no quality parameter needed)
            return session.get_track(track_id)

        except Exception as e:
            LOGGER.error(f"Failed to get track {track_id}: {e}")
            return None

    async def get_episode_safe(self, episode_id: str) -> Any | None:
        """Get episode with error handling"""
        try:
            session = await self.get_session()
            if not session:
                return None

            # Apply rate limiting
            session.rate_limiter.apply_limit()

            return session.get_episode(episode_id)

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
