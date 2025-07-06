"""
Stream utilities package for File-to-Link functionality
Optimized for minimal memory usage and maximum performance
"""

# Core utilities - essential imports only
from .admin_config import admin_config
from .cache_manager import CacheManager
from .file_processor import FileProcessor
from .link_generator import LinkGenerator
from .load_balancer import LoadBalancer
from .security_handler import SecurityHandler


# Optional utilities - lazy loading for better performance
def get_dc_checker():
    """Lazy load DCChecker to reduce startup time"""
    try:
        from .dc_checker import DCChecker

        return DCChecker
    except ImportError:
        return None


def get_config_validator():
    """Lazy load ConfigValidator to reduce startup time"""
    try:
        from .config_validator import ConfigValidator

        return ConfigValidator
    except ImportError:
        return None


def get_system_monitor():
    """Lazy load SystemMonitor to reduce startup time"""
    try:
        from .system_monitor import SystemMonitor

        return SystemMonitor
    except ImportError:
        return None


def get_password_manager():
    """Lazy load PasswordManager to reduce startup time"""
    try:
        from .password_manager import PasswordManager

        return PasswordManager
    except ImportError:
        return None


# Backward compatibility - lazy loaded
DCChecker = get_dc_checker()
ConfigValidator = get_config_validator()
SystemMonitor = get_system_monitor()
PasswordManager = get_password_manager()

# Export only essential classes for external use
__all__ = [
    "CacheManager",
    "ConfigValidator",
    # Lazy-loaded utilities
    "DCChecker",
    "FileProcessor",
    "LinkGenerator",
    "LoadBalancer",
    "PasswordManager",
    "SecurityHandler",
    "SystemMonitor",
    "admin_config",
]
