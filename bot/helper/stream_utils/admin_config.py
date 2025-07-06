"""
Admin Configuration Management System
Handles website configuration, settings, and admin-specific functionality
"""

from datetime import datetime
from typing import Any

from bot import LOGGER
from bot.helper.ext_utils.db_handler import database


class AdminConfig:
    """Manages admin configuration and website settings"""

    def __init__(self):
        self._config_cache = {}
        self._cache_timestamp = 0
        self._cache_ttl = 600  # 10 minutes cache TTL for efficiency
        self._full_config_cache = None  # Cache for full config
        self._default_config = {
            "site_settings": {
                "site_name": "StreamBot",
                "site_description": "Your personal media streaming platform",
                "site_logo": None,
                "site_favicon": None,
                "site_footer_text": "Powered by StreamBot",
                "site_copyright": "© 2024 StreamBot. All rights reserved.",
                "maintenance_mode": False,
                "registration_enabled": True,
                "public_registration": True,
                "max_file_size": 2147483648,  # 2GB
                "allowed_file_types": ["video", "audio", "image", "document"],
                "default_theme": "dark",
                "custom_css": "",
                "custom_js": "",
                "google_analytics_id": "",
                "meta_keywords": "streaming, media, movies, series, anime",
                "meta_author": "StreamBot",
                "contact_email": "",
                "social_links": {
                    "telegram": "",
                    "discord": "",
                    "twitter": "",
                    "github": "",
                },
            },
            "security_settings": {
                "require_email_verification": False,
                "password_min_length": 8,
                "session_timeout": 30,  # minutes
                "max_login_attempts": 5,
                "lockout_duration": 15,  # minutes
                "two_factor_auth": False,
                "admin_approval_required": False,
            },
            "media_settings": {
                "auto_generate_thumbnails": True,
                "thumbnail_quality": 85,
                "video_preview_duration": 10,  # seconds
                "max_concurrent_streams": 10,
                "enable_transcoding": False,
                "storage_quota_per_user": 10737418240,  # 10GB
                "auto_cleanup_old_files": False,
                "cleanup_after_days": 30,
            },
            "ui_settings": {
                "items_per_page": 10,
                "enable_dark_mode": True,
                "enable_light_mode": True,
                "default_view": "grid",
                "show_file_sizes": True,
                "show_upload_dates": True,
                "show_view_counts": True,
                "enable_search": True,
                "enable_filtering": True,
                "homepage_title": "Ultimate Media Streaming Platform",
                "homepage_subtitle": "Stream your favorite movies, series, anime, and music",
                "hero_background_image": "",
                "primary_color": "#6366f1",
                "secondary_color": "#8b5cf6",
                "accent_color": "#f59e0b",
                "navigation_style": "horizontal",
                "show_trending_section": True,
                "show_categories_section": True,
                "show_recent_section": True,
                "footer_enabled": True,
                "breadcrumbs_enabled": True,
            },
            "notification_settings": {
                "email_notifications": False,
                "smtp_server": "",
                "smtp_port": 587,
                "smtp_username": "",
                "smtp_password": "",
                "admin_email": "",
                "notify_new_users": True,
                "notify_new_uploads": False,
                "notify_errors": True,
            },
            "analytics_settings": {
                "enable_analytics": True,
                "track_user_activity": True,
                "track_file_views": True,
                "track_downloads": True,
                "retention_days": 90,
                "enable_public_stats": False,
            },
            "streaming_settings": {
                "enable_streaming": True,
                "max_concurrent_streams": 10,
                "stream_quality": "auto",
                "enable_download": True,
                "enable_direct_links": True,
                "stream_timeout": 300,  # seconds
                "buffer_size": 8192,
                "enable_subtitles": True,
                "auto_play": False,
                "show_player_controls": True,
                "enable_fullscreen": True,
                "enable_picture_in_picture": True,
                "default_volume": 80,
                "enable_speed_control": True,
                "enable_quality_selector": True,
            },
            "content_settings": {
                "enable_categories": True,
                "enable_series_grouping": True,
                "enable_trending": True,
                "trending_algorithm": "views_and_time",
                "enable_ratings": False,
                "enable_comments": False,
                "enable_favorites": True,
                "enable_watchlist": True,
                "enable_continue_watching": True,
                "auto_generate_descriptions": True,
                "enable_metadata_extraction": True,
                "enable_imdb_integration": False,
            },
            "navigation_settings": {
                "show_home_link": True,
                "show_movies_link": True,
                "show_series_link": True,
                "show_anime_link": True,
                "show_music_link": True,
                "show_library_link": True,
                "show_search": True,
                "show_user_menu": True,
                "show_admin_link": True,
                "custom_nav_links": [],
                "nav_position": "top",
                "nav_style": "horizontal",
            },
            "branding_settings": {
                "logo_url": "",
                "logo_text": "StreamBot",
                "favicon_url": "",
                "brand_colors": {
                    "primary": "#6366f1",
                    "secondary": "#8b5cf6",
                    "accent": "#f59e0b",
                    "success": "#10b981",
                    "warning": "#f59e0b",
                    "error": "#ef4444",
                },
                "custom_fonts": {"primary": "Inter", "secondary": "Inter"},
                "show_powered_by": True,
                "powered_by_text": "Powered by StreamBot",
                "powered_by_link": "",
            },
        }

    async def get_config(self, section: str | None = None) -> dict[str, Any]:
        """Get configuration settings with optimized caching"""
        try:
            current_time = datetime.utcnow().timestamp()

            # Check if full config cache is valid
            if (
                self._full_config_cache
                and current_time - self._cache_timestamp < self._cache_ttl
            ):
                if section:
                    return self._full_config_cache.get(
                        section, self._default_config.get(section, {})
                    )
                return self._full_config_cache.copy()

            # Get from database and update cache
            config_doc = await database.get_admin_config()
            if not config_doc:
                # Initialize with default config
                await self.reset_to_defaults()
                config_doc = self._default_config

            # Update full config cache
            self._full_config_cache = config_doc
            self._cache_timestamp = current_time

            if section:
                return config_doc.get(section, self._default_config.get(section, {}))

            return config_doc.copy()

        except Exception as e:
            LOGGER.error(f"Error getting admin config: {e}")
            return (
                self._default_config.get(section, {})
                if section
                else self._default_config.copy()
            )

    async def update_config(self, section: str, settings: dict[str, Any]) -> bool:
        """Update configuration settings with cache invalidation"""
        try:
            # Validate section exists
            if section not in self._default_config:
                LOGGER.error(f"Invalid config section: {section}")
                return False

            # Get current config
            current_config = await self.get_config()

            # Update the specific section
            if section not in current_config:
                current_config[section] = {}

            current_config[section].update(settings)
            current_config["last_updated"] = datetime.utcnow().timestamp()
            current_config["updated_by"] = "admin"  # Could be passed as parameter

            # Save to database
            result = await database.update_admin_config(current_config)

            if result:
                # Invalidate cache to force reload
                self._full_config_cache = None
                self._cache_timestamp = 0
                LOGGER.info(f"Updated admin config section: {section}")
                return True

            return False

        except Exception as e:
            LOGGER.error(f"Error updating admin config: {e}")
            return False

    async def reset_to_defaults(self) -> bool:
        """Reset configuration to default values"""
        try:
            default_config = self._default_config.copy()
            default_config["created_at"] = datetime.utcnow().timestamp()
            default_config["last_updated"] = datetime.utcnow().timestamp()

            result = await database.update_admin_config(default_config)

            if result:
                # Clear cache
                self._config_cache.clear()
                LOGGER.info("Reset admin config to defaults")
                return True

            return False

        except Exception as e:
            LOGGER.error(f"Error resetting admin config: {e}")
            return False

    async def get_site_settings(self) -> dict[str, Any]:
        """Get site-specific settings"""
        return await self.get_config("site_settings")

    async def get_security_settings(self) -> dict[str, Any]:
        """Get security-specific settings"""
        return await self.get_config("security_settings")

    async def get_media_settings(self) -> dict[str, Any]:
        """Get media-specific settings"""
        return await self.get_config("media_settings")

    async def get_ui_settings(self) -> dict[str, Any]:
        """Get UI-specific settings"""
        return await self.get_config("ui_settings")

    async def get_streaming_settings(self) -> dict[str, Any]:
        """Get streaming-specific settings"""
        return await self.get_config("streaming_settings")

    async def get_content_settings(self) -> dict[str, Any]:
        """Get content-specific settings"""
        return await self.get_config("content_settings")

    async def get_navigation_settings(self) -> dict[str, Any]:
        """Get navigation-specific settings"""
        return await self.get_config("navigation_settings")

    async def get_branding_settings(self) -> dict[str, Any]:
        """Get branding-specific settings"""
        return await self.get_config("branding_settings")

    async def is_maintenance_mode(self) -> bool:
        """Check if site is in maintenance mode"""
        try:
            site_settings = await self.get_site_settings()
            return site_settings.get("maintenance_mode", False)
        except Exception:
            return False

    async def is_registration_enabled(self) -> bool:
        """Check if user registration is enabled"""
        try:
            site_settings = await self.get_site_settings()
            return site_settings.get("registration_enabled", True)
        except Exception:
            return True

    async def get_max_file_size(self) -> int:
        """Get maximum allowed file size"""
        try:
            site_settings = await self.get_site_settings()
            return site_settings.get("max_file_size", 2147483648)  # 2GB default
        except Exception:
            return 2147483648

    async def get_allowed_file_types(self) -> list[str]:
        """Get allowed file types"""
        try:
            site_settings = await self.get_site_settings()
            return site_settings.get(
                "allowed_file_types", ["video", "audio", "image", "document"]
            )
        except Exception:
            return ["video", "audio", "image", "document"]

    async def get_items_per_page(self) -> int:
        """Get items per page for pagination"""
        try:
            ui_settings = await self.get_ui_settings()
            return ui_settings.get("items_per_page", 10)
        except Exception:
            return 10

    async def export_config(self) -> dict[str, Any]:
        """Export current configuration for backup"""
        try:
            config = await self.get_config()
            config["export_timestamp"] = datetime.utcnow().timestamp()

            # Convert ObjectId to string for JSON serialization
            def convert_objectid(obj):
                if hasattr(obj, "__dict__"):
                    for key, value in obj.__dict__.items():
                        obj.__dict__[key] = convert_objectid(value)
                elif isinstance(obj, dict):
                    for key, value in obj.items():
                        obj[key] = convert_objectid(value)
                elif isinstance(obj, list):
                    for i, item in enumerate(obj):
                        obj[i] = convert_objectid(item)
                elif (
                    hasattr(obj, "__class__")
                    and obj.__class__.__name__ == "ObjectId"
                ):
                    return str(obj)
                return obj

            return convert_objectid(config)
        except Exception as e:
            LOGGER.error(f"Error exporting config: {e}")
            return {}

    async def import_config(self, config_data: dict[str, Any]) -> bool:
        """Import configuration from backup"""
        try:
            # Validate config structure
            for section in self._default_config:
                if section not in config_data:
                    LOGGER.warning(f"Missing config section in import: {section}")
                    config_data[section] = self._default_config[section]

            config_data["last_updated"] = datetime.utcnow().timestamp()
            config_data["imported_at"] = datetime.utcnow().timestamp()

            result = await database.update_admin_config(config_data)

            if result:
                # Clear cache to force reload
                self._config_cache.clear()
                LOGGER.info("Imported admin configuration")
                return True

            return False

        except Exception as e:
            LOGGER.error(f"Error importing config: {e}")
            return False


# Global admin config instance
admin_config = AdminConfig()
