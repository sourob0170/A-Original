from bot import LOGGER
from bot.core.config_manager import Config


class ConfigValidator:
    """Validates File-to-Link configuration settings"""

    @staticmethod
    def validate_all() -> tuple[bool, list[str]]:
        """Validate all File-to-Link configuration settings"""
        errors = []
        warnings = []

        # Check if feature is enabled
        if not Config.FILE_TO_LINK_ENABLED:
            warnings.append("File-to-Link functionality is disabled")
            return True, warnings  # Not an error, just disabled

        # Validate required settings
        required_checks = [
            ConfigValidator._check_dump_chat,
            ConfigValidator._check_server_settings,
            ConfigValidator._check_security_settings,
        ]

        for check in required_checks:
            try:
                is_valid, messages = check()
                if not is_valid:
                    errors.extend(messages)
                else:
                    warnings.extend(messages)
            except Exception as e:
                errors.append(f"Configuration check failed: {e}")

        # Optional settings validation
        optional_checks = [
            ConfigValidator._check_performance_settings,
            ConfigValidator._check_interface_settings,
        ]

        for check in optional_checks:
            try:
                _, messages = check()
                warnings.extend(messages)
            except Exception as e:
                warnings.append(f"Optional configuration check failed: {e}")

        return len(errors) == 0, errors + warnings

    @staticmethod
    def _check_dump_chat() -> tuple[bool, list[str]]:
        """Check dump chat configuration"""
        messages = []

        if not hasattr(Config, "LEECH_DUMP_CHAT") or not Config.LEECH_DUMP_CHAT:
            # Make this a warning instead of error - File-to-Link can work without dump chat
            messages.append(
                "LEECH_DUMP_CHAT is not configured - files will be sent to requesting user only"
            )
            return True, messages

        # Handle LEECH_DUMP_CHAT as a list (new format)
        if isinstance(Config.LEECH_DUMP_CHAT, list):
            if not Config.LEECH_DUMP_CHAT:
                # Make this a warning instead of error
                messages.append(
                    "LEECH_DUMP_CHAT list is empty - files will be sent to requesting user only"
                )
                return True, messages

            # Validate each chat ID in the list
            for i, chat_id in enumerate(Config.LEECH_DUMP_CHAT):
                try:
                    # Extract actual chat ID from prefixed format (b:, u:, h:)
                    processed_chat_id = str(chat_id)
                    if ":" in processed_chat_id:
                        processed_chat_id = processed_chat_id.split(":", 1)[1]
                    if "|" in processed_chat_id:
                        processed_chat_id = processed_chat_id.split("|", 1)[0]

                    # Try to convert to integer to validate
                    chat_id_int = int(processed_chat_id)
                    if chat_id_int == 0:
                        return False, [f"LEECH_DUMP_CHAT[{i}] cannot be 0"]
                    if chat_id_int > 0:
                        messages.append(
                            f"LEECH_DUMP_CHAT[{i}] appears to be a user ID, consider using a channel/group"
                        )
                except (ValueError, TypeError):
                    return False, [
                        f"LEECH_DUMP_CHAT[{i}] must be a valid integer chat ID or prefixed format"
                    ]
        else:
            # Handle legacy single chat ID format
            try:
                chat_id = int(Config.LEECH_DUMP_CHAT)
                if chat_id == 0:
                    return False, ["LEECH_DUMP_CHAT cannot be 0"]
                if chat_id > 0:
                    messages.append(
                        "LEECH_DUMP_CHAT appears to be a user ID, consider using a channel/group"
                    )
            except (ValueError, TypeError):
                return False, ["LEECH_DUMP_CHAT must be a valid integer chat ID"]

        return True, messages

    @staticmethod
    def _check_server_settings() -> tuple[bool, list[str]]:
        """Check streaming server settings"""
        messages = []

        if not Config.FILE_TO_LINK_ENABLED:
            messages.append(
                "Streaming functionality is disabled - only download links will work"
            )
            return True, messages

        # Streaming is now integrated with wserver, no separate port needed
        messages.append("Streaming functionality integrated with main web server")

        # Check base URL if configured
        base_url = getattr(Config, "BASE_URL", "")
        if base_url and not base_url.startswith(("http://", "https://")):
            return False, ["BASE_URL must start with http:// or https://"]

        return True, messages

    @staticmethod
    def _check_security_settings() -> tuple[bool, list[str]]:
        """Check security settings"""
        messages = []

        # Check hash security
        if not getattr(Config, "STREAM_SECURITY_HASH", True):
            messages.append(
                "Hash-based security is disabled - files will be less secure"
            )

        # Check password protection
        password_protection = getattr(Config, "STREAM_PASSWORD_PROTECTION", False)
        default_password = getattr(Config, "STREAM_DEFAULT_PASSWORD", "")

        if password_protection and not default_password:
            messages.append(
                "Password protection is enabled but no default password is set"
            )

        if default_password and len(default_password) < 6:
            messages.append(
                "Default password is too short (minimum 6 characters recommended)"
            )

        # Check banned channels
        banned_channels = getattr(Config, "BANNED_STREAM_CHANNELS", "")
        if banned_channels:
            try:
                # Try to parse as comma-separated integers
                channel_ids = [
                    int(x.strip()) for x in banned_channels.split(",") if x.strip()
                ]
                if len(channel_ids) == 0:
                    messages.append(
                        "BANNED_STREAM_CHANNELS is set but contains no valid channel IDs"
                    )
            except ValueError:
                return False, [
                    "BANNED_STREAM_CHANNELS must contain comma-separated integer channel IDs"
                ]

        return True, messages

    @staticmethod
    def _check_performance_settings() -> tuple[bool, list[str]]:
        """Check performance settings"""
        messages = []

        # Check caching
        if not getattr(Config, "STREAM_CACHE_ENABLED", True):
            messages.append("Caching is disabled - performance may be reduced")

        # Check load balancing
        if not getattr(Config, "STREAM_LOAD_BALANCING", True):
            messages.append(
                "Load balancing is disabled - single client will handle all requests"
            )

        # Check helper bots only if load balancing is enabled
        if getattr(Config, "STREAM_LOAD_BALANCING", True):
            helper_tokens = getattr(Config, "HELPER_TOKENS", "")
            if not helper_tokens or not helper_tokens.strip():
                # This is a warning, not an error - the system can work with just the main bot
                messages.append(
                    "Load balancing is enabled but no helper bots are configured - consider adding HELPER_TOKENS for better performance"
                )

        return True, messages

    @staticmethod
    def _check_interface_settings() -> tuple[bool, list[str]]:
        """Check interface settings"""
        messages = []

        # Check ads setting
        if not getattr(Config, "STREAM_NO_ADS", True):
            messages.append("Ad-free setting is disabled")

        # Check permanent links
        if not getattr(Config, "PERMANENT_LINKS", True):
            messages.append("Permanent links are disabled - links may expire")

        return True, messages

    @staticmethod
    def get_configuration_summary() -> dict[str, any]:
        """Get a summary of current configuration"""
        return {
            "feature_enabled": getattr(Config, "FILE_TO_LINK_ENABLED", False),
            "base_url": getattr(Config, "BASE_URL", ""),
            "security_hash": getattr(Config, "STREAM_SECURITY_HASH", True),
            "password_protection": getattr(
                Config, "STREAM_PASSWORD_PROTECTION", False
            ),
            "cache_enabled": getattr(Config, "STREAM_CACHE_ENABLED", True),
            "load_balancing": getattr(Config, "STREAM_LOAD_BALANCING", True),
            "permanent_links": getattr(Config, "PERMANENT_LINKS", True),
            "no_ads": getattr(Config, "STREAM_NO_ADS", True),
            "dump_chat": getattr(Config, "LEECH_DUMP_CHAT", None),
            "banned_channels": getattr(Config, "BANNED_STREAM_CHANNELS", ""),
        }

    @staticmethod
    def format_validation_report(is_valid: bool, messages: list[str]) -> str:
        """Format validation report for display"""
        if not messages:
            return "✅ All File-to-Link settings are properly configured!"

        report = "🔧 **File-to-Link Configuration Report**\n\n"

        if not is_valid:
            report += "❌ **Configuration Errors Found:**\n"
            errors = [
                msg
                for msg in messages
                if any(
                    keyword in msg.lower()
                    for keyword in ["error", "required", "must", "cannot", "invalid"]
                )
            ]
            for error in errors:
                report += f"• {error}\n"
            report += "\n"

        warnings = [
            msg
            for msg in messages
            if msg
            not in [
                msg
                for msg in messages
                if any(
                    keyword in msg.lower()
                    for keyword in ["error", "required", "must", "cannot", "invalid"]
                )
            ]
        ]

        if warnings:
            report += "⚠️ **Configuration Warnings:**\n"
            for warning in warnings:
                report += f"• {warning}\n"

        return report.strip()

    @staticmethod
    def validate_and_log():
        """Validate configuration and log results"""
        try:
            is_valid, messages = ConfigValidator.validate_all()

            if is_valid and not messages:
                LOGGER.info("File-to-Link configuration validation passed")
            elif is_valid:
                LOGGER.info(
                    "File-to-Link configuration validation passed with warnings"
                )
                for message in messages:
                    LOGGER.info(f"Config info: {message}")
            else:
                LOGGER.error("File-to-Link configuration validation failed")
                for message in messages:
                    if any(
                        keyword in message.lower()
                        for keyword in [
                            "error",
                            "required",
                            "must",
                            "cannot",
                            "invalid",
                        ]
                    ):
                        LOGGER.error(f"Config error: {message}")
                    else:
                        LOGGER.warning(f"Config warning: {message}")

            return is_valid

        except Exception as e:
            LOGGER.error(f"Configuration validation failed: {e}")
            return False
