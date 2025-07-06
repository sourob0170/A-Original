import re

from bot import LOGGER
from bot.core.config_manager import Config

from .security_handler import SecurityHandler


class PasswordManager:
    """Manages password protection for files"""

    # Password strength requirements
    MIN_LENGTH = 6
    MAX_LENGTH = 128

    @staticmethod
    def is_password_required(user_id: int, file_info: dict) -> bool:
        """Check if password is required for file access"""
        try:
            # Check global setting
            if not Config.STREAM_PASSWORD_PROTECTION:
                return False

            # Check file-specific settings (could be extended)
            # For now, use global default
            return bool(Config.STREAM_DEFAULT_PASSWORD)

        except Exception as e:
            LOGGER.error(f"Error checking password requirement: {e}")
            return False

    @staticmethod
    def validate_password_strength(password: str) -> tuple[bool, str]:
        """Validate password strength"""
        try:
            if not password:
                return False, "Password cannot be empty"

            if len(password) < PasswordManager.MIN_LENGTH:
                return (
                    False,
                    f"Password must be at least {PasswordManager.MIN_LENGTH} characters",
                )

            if len(password) > PasswordManager.MAX_LENGTH:
                return (
                    False,
                    f"Password must be less than {PasswordManager.MAX_LENGTH} characters",
                )

            # Check for basic complexity
            has_upper = bool(re.search(r"[A-Z]", password))
            has_lower = bool(re.search(r"[a-z]", password))
            has_digit = bool(re.search(r"\d", password))
            has_special = bool(re.search(r'[!@#$%^&*(),.?":{}|<>]', password))

            complexity_score = sum([has_upper, has_lower, has_digit, has_special])

            if complexity_score < 2:
                return (
                    False,
                    "Password must contain at least 2 of: uppercase, lowercase, numbers, special characters",
                )

            # Check for common weak passwords
            weak_patterns = [r"123456", r"password", r"qwerty", r"abc123", r"admin"]

            for pattern in weak_patterns:
                if re.search(pattern, password.lower()):
                    return (
                        False,
                        "Password is too common, please choose a stronger password",
                    )

            return True, "Password is strong"

        except Exception as e:
            LOGGER.error(f"Error validating password strength: {e}")
            return False, "Error validating password"

    @staticmethod
    def set_file_password(file_id: str, password: str) -> tuple[bool, str]:
        """Set password for a file"""
        try:
            if not password:
                return True, "No password set"

            # Validate password strength
            is_valid, message = PasswordManager.validate_password_strength(password)
            if not is_valid:
                return False, message

            # Generate password hash
            password_hash = SecurityHandler.generate_password_hash(password)
            if not password_hash:
                return False, "Failed to generate password hash"

            # Store password hash (in a real implementation, this would go to database)
            # For now, we'll use a simple in-memory storage
            if not hasattr(PasswordManager, "_password_store"):
                PasswordManager._password_store = {}

            PasswordManager._password_store[file_id] = password_hash

            return True, "Password set successfully"

        except Exception as e:
            LOGGER.error(f"Error setting file password: {e}")
            return False, "Error setting password"

    @staticmethod
    def verify_file_password(file_id: str, password: str) -> bool:
        """Verify password for file access"""
        try:
            # Get stored password hash
            if not hasattr(PasswordManager, "_password_store"):
                PasswordManager._password_store = {}

            stored_hash = PasswordManager._password_store.get(file_id)

            # If no password is set, allow access
            if not stored_hash:
                # Check if default password is required
                if Config.STREAM_DEFAULT_PASSWORD:
                    return SecurityHandler.verify_password(
                        password,
                        SecurityHandler.generate_password_hash(
                            Config.STREAM_DEFAULT_PASSWORD
                        ),
                    )
                return True

            # Verify provided password
            return SecurityHandler.verify_password(password, stored_hash)

        except Exception as e:
            LOGGER.error(f"Error verifying file password: {e}")
            return False

    @staticmethod
    def remove_file_password(file_id: str) -> bool:
        """Remove password protection from file"""
        try:
            if not hasattr(PasswordManager, "_password_store"):
                return True

            if file_id in PasswordManager._password_store:
                del PasswordManager._password_store[file_id]

            return True

        except Exception as e:
            LOGGER.error(f"Error removing file password: {e}")
            return False

    @staticmethod
    def get_default_password() -> str:
        """Get default password from config"""
        return Config.STREAM_DEFAULT_PASSWORD or ""

    @staticmethod
    def generate_secure_password(length: int = 12) -> str:
        """Generate a secure random password"""
        try:
            import secrets
            import string

            # Ensure minimum length
            length = max(length, PasswordManager.MIN_LENGTH)
            length = min(length, PasswordManager.MAX_LENGTH)

            # Character sets
            lowercase = string.ascii_lowercase
            uppercase = string.ascii_uppercase
            digits = string.digits
            special = "!@#$%^&*"

            # Ensure at least one character from each set
            password = [
                secrets.choice(lowercase),
                secrets.choice(uppercase),
                secrets.choice(digits),
                secrets.choice(special),
            ]

            # Fill remaining length with random characters
            all_chars = lowercase + uppercase + digits + special
            password.extend(secrets.choice(all_chars) for _ in range(length - 4))

            # Shuffle the password
            secrets.SystemRandom().shuffle(password)

            return "".join(password)

        except Exception as e:
            LOGGER.error(f"Error generating secure password: {e}")
            return "SecurePass123!"

    @staticmethod
    def get_password_hint(file_id: str) -> str | None:
        """Get password hint for file (if any)"""
        try:
            # This could be extended to store hints
            # For now, return generic hint
            if Config.STREAM_DEFAULT_PASSWORD:
                return "Use the default password set by admin"
            return None

        except Exception as e:
            LOGGER.error(f"Error getting password hint: {e}")
            return None

    @staticmethod
    def cleanup_expired_passwords(max_age: int = 86400):
        """Clean up expired password entries"""
        try:
            # This would be implemented with proper database storage
            # For now, just ensure the store exists
            if not hasattr(PasswordManager, "_password_store"):
                PasswordManager._password_store = {}

            # In a real implementation, this would remove passwords
            # for files that no longer exist or are expired

        except Exception as e:
            LOGGER.error(f"Error cleaning up passwords: {e}")

    @staticmethod
    def get_password_stats() -> dict[str, int]:
        """Get password protection statistics"""
        try:
            if not hasattr(PasswordManager, "_password_store"):
                PasswordManager._password_store = {}

            return {
                "protected_files": len(PasswordManager._password_store),
                "default_password_enabled": bool(Config.STREAM_DEFAULT_PASSWORD),
                "protection_enabled": Config.STREAM_PASSWORD_PROTECTION,
            }

        except Exception as e:
            LOGGER.error(f"Error getting password stats: {e}")
            return {}
