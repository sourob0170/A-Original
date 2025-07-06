import hashlib
import secrets
import time
from typing import Any, ClassVar

from bot import LOGGER
from bot.core.config_manager import Config


class SecurityHandler:
    """Handles security operations for file-to-link functionality"""

    _hash_cache: ClassVar[dict[str, dict[str, Any]]] = {}
    _rate_limit_cache: ClassVar[dict[str, list]] = {}
    _max_cache_size = 1000  # Limit cache size to prevent memory leaks
    _cache_cleanup_interval = 3600  # 1 hour
    _last_cleanup = 0

    @staticmethod
    def _cleanup_expired_caches():
        """Clean up expired cache entries to prevent memory leaks"""
        try:
            current_time = time.time()

            # Only cleanup if interval has passed
            if (
                current_time - SecurityHandler._last_cleanup
                < SecurityHandler._cache_cleanup_interval
            ):
                return

            # Cleanup hash cache (remove entries older than 24 hours)
            expired_hashes = []
            for hash_key, data in SecurityHandler._hash_cache.items():
                if current_time - data.get("created_at", 0) > 86400:  # 24 hours
                    expired_hashes.append(hash_key)

            for hash_key in expired_hashes:
                del SecurityHandler._hash_cache[hash_key]

            # Cleanup rate limit cache (remove entries older than 1 hour)
            expired_rates = []
            for user_id, request_times in SecurityHandler._rate_limit_cache.items():
                # Handle both list format (current) and dict format (legacy)
                if isinstance(request_times, list):
                    # Filter out old requests
                    SecurityHandler._rate_limit_cache[user_id] = [
                        req_time
                        for req_time in request_times
                        if current_time - req_time < 3600
                    ]
                    # Mark for deletion if empty
                    if not SecurityHandler._rate_limit_cache[user_id]:
                        expired_rates.append(user_id)
                elif isinstance(request_times, dict):
                    # Legacy dict format
                    if current_time - request_times.get("last_request", 0) > 3600:
                        expired_rates.append(user_id)

            for user_id in expired_rates:
                del SecurityHandler._rate_limit_cache[user_id]

            SecurityHandler._last_cleanup = current_time

            if expired_hashes or expired_rates:
                LOGGER.debug(
                    f"Security cache cleanup: removed {len(expired_hashes)} hashes, {len(expired_rates)} rate limits"
                )

        except Exception as e:
            LOGGER.error(f"Error during cache cleanup: {e}")

    @staticmethod
    def generate_secure_hash(file_unique_id: str, additional_data: str = "") -> str:
        """Generate a 6-character secure hash for file access with memory optimization"""
        try:
            # Cleanup expired caches periodically
            SecurityHandler._cleanup_expired_caches()

            # Limit cache size to prevent memory leaks
            if len(SecurityHandler._hash_cache) >= SecurityHandler._max_cache_size:
                # Remove oldest 20% of entries
                sorted_items = sorted(
                    SecurityHandler._hash_cache.items(),
                    key=lambda x: x[1].get("created_at", 0),
                )
                items_to_remove = int(SecurityHandler._max_cache_size * 0.2)
                for i in range(items_to_remove):
                    if i < len(sorted_items):
                        del SecurityHandler._hash_cache[sorted_items[i][0]]

            # Use file unique ID + timestamp + additional data for uniqueness
            timestamp = str(int(time.time()))
            data = (
                f"{file_unique_id}{timestamp}{additional_data}{secrets.token_hex(8)}"
            )

            # Create SHA-256 hash and take first 6 characters
            hash_object = hashlib.sha256(data.encode())
            secure_hash = hash_object.hexdigest()[:6]

            # Ensure no collision by checking cache (with limit to prevent infinite loop)
            collision_attempts = 0
            while (
                secure_hash in SecurityHandler._hash_cache
                and collision_attempts < 10
            ):
                data = f"{data}{secrets.token_hex(4)}"
                hash_object = hashlib.sha256(data.encode())
                secure_hash = hash_object.hexdigest()[:6]
                collision_attempts += 1

            # Cache the hash with metadata
            SecurityHandler._hash_cache[secure_hash] = {
                "file_unique_id": file_unique_id,
                "created_at": time.time(),
                "access_count": 0,
            }

            return secure_hash

        except Exception as e:
            LOGGER.error(f"Error generating secure hash: {e}")
            # Fallback to simple hash
            return (
                file_unique_id[:6]
                if len(file_unique_id) >= 6
                else file_unique_id.ljust(6, "0")
            )

    @staticmethod
    def validate_hash(secure_hash: str, file_unique_id: str) -> bool:
        """Validate if hash matches file unique ID"""
        try:
            if not Config.STREAM_SECURITY_HASH:
                return True

            # Check if hash exists in cache
            if secure_hash in SecurityHandler._hash_cache:
                cached_data = SecurityHandler._hash_cache[secure_hash]
                if cached_data["file_unique_id"] == file_unique_id:
                    # Update access count
                    cached_data["access_count"] += 1
                    return True

            # Fallback validation for backward compatibility
            return (
                file_unique_id.startswith(secure_hash)
                or file_unique_id[:6] == secure_hash
            )

        except Exception as e:
            LOGGER.error(f"Error validating hash: {e}")
            return False

    @staticmethod
    def check_rate_limit(
        user_id: int, max_requests: int = 10, time_window: int = 60
    ) -> bool:
        """Check if user is within rate limits"""
        try:
            current_time = time.time()
            user_key = str(user_id)

            # Initialize user's request history if not exists
            if user_key not in SecurityHandler._rate_limit_cache:
                SecurityHandler._rate_limit_cache[user_key] = []

            # Clean old requests outside time window
            user_requests = SecurityHandler._rate_limit_cache[user_key]
            user_requests[:] = [
                req_time
                for req_time in user_requests
                if current_time - req_time < time_window
            ]

            # Check if user exceeded rate limit
            if len(user_requests) >= max_requests:
                return False

            # Add current request
            user_requests.append(current_time)
            return True

        except Exception as e:
            LOGGER.error(f"Error checking rate limit: {e}")
            return True  # Allow on error

    @staticmethod
    def generate_password_hash(password: str) -> str:
        """Generate secure hash for password"""
        try:
            salt = secrets.token_hex(16)
            password_hash = hashlib.pbkdf2_hmac(
                "sha256", password.encode(), salt.encode(), 100000
            )
            return f"{salt}:{password_hash.hex()}"
        except Exception as e:
            LOGGER.error(f"Error generating password hash: {e}")
            return ""

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """Verify password against hash"""
        try:
            if not password_hash:
                return not password  # No password required

            salt, stored_hash = password_hash.split(":")
            password_hash_check = hashlib.pbkdf2_hmac(
                "sha256", password.encode(), salt.encode(), 100000
            )
            return password_hash_check.hex() == stored_hash

        except Exception as e:
            LOGGER.error(f"Error verifying password: {e}")
            return False

    @staticmethod
    def is_safe_filename(filename: str) -> bool:
        """Check if filename is safe for serving"""
        try:
            # Check for path traversal attempts
            if ".." in filename or "/" in filename or "\\" in filename:
                return False

            # Check for null bytes
            if "\x00" in filename:
                return False

            # Check for control characters
            return not any(ord(char) < 32 for char in filename)

        except Exception as e:
            LOGGER.error(f"Error checking filename safety: {e}")
            return False

    @staticmethod
    def clean_cache(max_age: int = 3600):
        """Clean old entries from cache"""
        try:
            current_time = time.time()

            # Clean hash cache
            expired_hashes = [
                hash_key
                for hash_key, data in SecurityHandler._hash_cache.items()
                if current_time - data["created_at"] > max_age
            ]

            for hash_key in expired_hashes:
                del SecurityHandler._hash_cache[hash_key]

            # Clean rate limit cache
            for user_key in list(SecurityHandler._rate_limit_cache.keys()):
                user_requests = SecurityHandler._rate_limit_cache[user_key]
                user_requests[:] = [
                    req_time
                    for req_time in user_requests
                    if current_time - req_time < 300
                ]  # Keep last 5 minutes

                if not user_requests:
                    del SecurityHandler._rate_limit_cache[user_key]

        except Exception as e:
            LOGGER.error(f"Error cleaning cache: {e}")

    @staticmethod
    def get_cache_stats() -> dict[str, int]:
        """Get cache statistics"""
        return {
            "hash_cache_size": len(SecurityHandler._hash_cache),
            "rate_limit_cache_size": len(SecurityHandler._rate_limit_cache),
        }
