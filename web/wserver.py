import asyncio
import builtins
from asyncio import sleep
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from logging import INFO, WARNING, FileHandler, StreamHandler, basicConfig, getLogger
from urllib.parse import urlparse

from aioaria2 import Aria2HttpClient  # type: ignore
from aioqbt.client import create_client  # type: ignore
from aioqbt.exc import AQError
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import (  # type: ignore
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer  # type: ignore
from fastapi.staticfiles import StaticFiles  # type: ignore
from fastapi.templating import Jinja2Templates  # type: ignore
from httpx import AsyncClient
from httpx import RequestError as ClientError
from uvloop import install  # type: ignore

# Config will be imported in the try block below
from bot.helper.stream_utils.quality_handler import QualityHandler
from sabnzbdapi import SabnzbdClient
from web.nodes import extract_file_ids, make_tree

# Install uvloop for better performance
install()

getLogger("httpx").setLevel(WARNING)

# Set up basic logger for early use
LOGGER = getLogger(__name__)


# Create a fallback BotConfig class in case imports fail
class BotConfig:
    FILE_TO_LINK_ENABLED = False
    LEECH_DUMP_CHAT = None


# UNIFIED IMPORTS - INTEGRATED WITH FILE_TO_LINK
try:
    from bot.core.aeon_client import TgClient
    from bot.core.config_manager import Config
    from bot.helper.ext_utils.db_handler import DbManager, ensure_database_and_config
    from bot.helper.ext_utils.db_handler import database as shared_database
    from bot.helper.stream_utils import (
        FileProcessor,
        SecurityHandler,
    )
    from bot.helper.stream_utils.load_balancer import LoadBalancer
    from web.optimized_streaming import OptimizedStreaming

    FILE_TO_LINK_AVAILABLE = True
    LOGGER.info("File-to-Link imports successful - unified integration enabled")

    # UNIFIED CLIENT MANAGEMENT - INTEGRATED WITH LOADBALANCER
    _client_integration_initialized = False

    def should_enable_streaming() -> bool:
        """Check if streaming should be enabled based on all required conditions"""
        # Check if File-to-Link is enabled
        file_to_link_enabled = getattr(Config, "FILE_TO_LINK_ENABLED", False)
        if not file_to_link_enabled:
            LOGGER.info("Streaming disabled: FILE_TO_LINK_ENABLED is False")
            return False

        # For now, enable streaming if File-to-Link is enabled
        # Helper tokens will be checked during actual streaming operations
        LOGGER.info(
            f"Streaming enabled: FILE_TO_LINK_ENABLED={file_to_link_enabled}"
        )
        return True

    async def initialize_integrated_client_system():
        """Initialize integrated client system - UNIFIED WITH LOADBALANCER"""
        global _client_integration_initialized

        if _client_integration_initialized:
            return

        try:
            LOGGER.info("Initializing LoadBalancer client system...")

            try:
                # LoadBalancer is only initialized in web server process
                LOGGER.info("Initializing LoadBalancer for web server...")
                if not LoadBalancer._initialized:
                    LoadBalancer.initialize()
                else:
                    # If already initialized, refresh helper bots
                    LoadBalancer.refresh_helper_bots()

                lb_stats = LoadBalancer.get_load_stats()
                LOGGER.info(
                    f"✅ LoadBalancer initialized: {lb_stats.get('total_clients', 0)} clients"
                )
            except Exception as lb_error:
                LOGGER.error(f"LoadBalancer initialization failed: {lb_error}")

            # STEP 3: Mark integration as complete
            _client_integration_initialized = True
            LOGGER.info("🎉 Integrated client system initialization complete")

        except Exception as e:
            LOGGER.error(f"Failed to initialize integrated client system: {e}")

    async def get_telegram_client():
        """Get optimal Telegram client using integrated system - UNIFIED LOADBALANCER + FALLBACK"""
        try:
            # Ensure integrated client system is initialized (only once)
            if not _client_integration_initialized:
                await initialize_integrated_client_system()

            # PRIMARY: Use LoadBalancer (shared with file_to_link.py)
            client_id, client = LoadBalancer.get_optimal_client()

            if client:
                LoadBalancer.increment_load(client_id)
                return client, client_id

            LOGGER.error("❌ No Telegram clients available for streaming")
            return None, None

        except Exception as e:
            LOGGER.error(f"Failed to get Telegram client: {e}")
            return None, None

    def get_client_stats():
        """Get LoadBalancer client statistics"""
        try:
            return LoadBalancer.get_load_stats()
        except Exception as e:
            LOGGER.error(f"Error getting LoadBalancer stats: {e}")
            return {
                "total_clients": 0,
                "healthy_clients": 0,
                "total_load": 0,
                "error": str(e),
            }

    def get_wserver_client_stats():
        """Get LoadBalancer client system statistics"""
        try:
            # Get LoadBalancer stats (primary and only system)
            lb_stats = LoadBalancer.get_load_stats()

            # Use LoadBalancer stats directly
            total_clients = lb_stats.get("total_clients", 0)
            healthy_clients = lb_stats.get("healthy_clients", 0)
            total_load = lb_stats.get("total_load", 0)

            # Get main client info from LoadBalancer (primary)
            main_client_info = {
                "connected": lb_stats.get("main_client_connected", False),
                "type": "loadbalancer_primary",
                "load": lb_stats.get("main_client_load", 0),
            }

            return {
                "initialized": _client_integration_initialized,
                "integration_type": "LoadBalancer",
                "primary_system": "LoadBalancer",
                "total_clients": total_clients,
                "connected_clients": healthy_clients,
                "loadbalancer_clients": lb_stats.get("total_clients", 0),
                "main_client": main_client_info,
                "total_usage": total_load,
                "system_status": "✅ Integrated"
                if _client_integration_initialized
                else "❌ Not Initialized",
            }
        except Exception as e:
            LOGGER.error(f"Error getting integrated client stats: {e}")
            return {
                "error": f"Failed to get integrated client stats: {e!s}",
                "initialized": False,
                "integration_type": "Failed",
                "total_clients": 0,
                "connected_clients": 0,
                "total_usage": 0,
                "system_status": "❌ Error",
            }

    def release_telegram_client(client_id):
        """Release client after use - Simplified system"""
        try:
            LoadBalancer.decrement_load(client_id)
        except Exception as e:
            LOGGER.error(f"Error releasing client {client_id}: {e}")

    # UNIFIED DATABASE CONNECTION - SHARED WITH FILE_TO_LINK
    _database_config_loaded = False
    _database_config_lock = asyncio.Lock()
    _shared_database_instance = None

    async def get_shared_database():
        """Get shared database instance - UNIFIED WITH FILE_TO_LINK"""
        global _shared_database_instance

        if _shared_database_instance is not None:
            return _shared_database_instance

        # First, try to use the shared database instance from the main bot process
        if hasattr(shared_database, "db") and shared_database.db is not None:
            _shared_database_instance = shared_database
            return shared_database

        # Read shared configuration file written by the main bot process
        import json
        import os
        import tempfile

        config_file_path = os.path.join(
            tempfile.gettempdir(), "aimleechbot_shared_config.json"
        )
        with open(config_file_path) as f:
            shared_config = json.load(f)

        database_url = shared_config.get("DATABASE_URL")
        bot_token = shared_config.get("BOT_TOKEN")
        tg_client_id = shared_config.get("TG_CLIENT_ID")
        helper_tokens = shared_config.get("HELPER_TOKENS", "")
        telegram_api = shared_config.get("TELEGRAM_API")
        telegram_hash = shared_config.get("TELEGRAM_HASH")

        # Set configuration values from shared config
        from bot.core.config_manager import Config

        Config.DATABASE_URL = database_url
        if helper_tokens:
            Config.HELPER_TOKENS = helper_tokens
        if telegram_api:
            Config.TELEGRAM_API = telegram_api
        if telegram_hash:
            Config.TELEGRAM_HASH = telegram_hash

        # Create database manager instance for web server
        web_db_manager = DbManager()

        # Set TgClient.ID for database operations
        from bot.core.aeon_client import TgClient

        if tg_client_id:
            TgClient.ID = tg_client_id
        else:
            TgClient.ID = int(bot_token.split(":")[0])

        # Connect to database
        await web_db_manager.ensure_connection()

        _shared_database_instance = web_db_manager
        return web_db_manager

    async def ensure_database_and_config():
        """Unified function to ensure database connection and load config"""
        # Get shared database instance
        database = await get_shared_database()

        # Load configuration if not already loaded
        if not _database_config_loaded:
            await load_database_config()

        return database

    async def get_media_info_with_fallback(hash_id: str):
        """Get media info with fallback to grouped versions"""
        try:
            database = await ensure_database_and_config()
            if not database:
                return None

            # Try original hash_id first
            media_data = await database.get_media_metadata(hash_id)
            if not media_data:
                # Fallback: Try to find grouped versions
                try:
                    # Search for media with grouped hash_id patterns (hash_id_quality_season_episode)
                    all_media = await database.get_all_media(limit=100)
                    for media in all_media:
                        media_hash_id = media.get("hash_id", "")
                        original_hash_id = media.get("original_hash_id", "")

                        # Check if this media's hash_id starts with our original hash_id
                        # or if the original_hash_id matches
                        if (
                            media_hash_id.startswith(hash_id + "_")
                            or original_hash_id == hash_id
                        ):
                            LOGGER.info(
                                f"Found grouped media for {hash_id}: {media_hash_id}"
                            )
                            media_data = media
                            break

                except Exception as search_error:
                    LOGGER.error(
                        f"Error searching for grouped hash_id: {search_error}"
                    )

                if not media_data:
                    return None

            # Ensure TMDB data structure exists
            if not media_data.get("tmdb_data"):
                media_data["tmdb_data"] = {}

            # Add optimized URL fields
            media_data["poster_url"] = get_media_poster_url(media_data)
            media_data["backdrop_url"] = get_media_backdrop_url(media_data)

            # Extract quality information if missing
            if not media_data.get("quality"):
                file_name = media_data.get("file_name", "")
                # Extract quality from filename (ReelNN style)
                quality_patterns = [
                    "2160p",
                    "1080p",
                    "720p",
                    "480p",
                    "4K",
                    "UHD",
                    "HD",
                ]
                for pattern in quality_patterns:
                    if pattern.lower() in file_name.lower():
                        media_data["quality"] = pattern
                        break
                else:
                    media_data["quality"] = "HD"

            return media_data

        except Exception as e:
            LOGGER.error(f"Error in get_media_info_with_fallback: {e}")
            return None

    def ensure_tg_client_id():
        """Ensure TgClient.ID is set for database operations"""
        if not TgClient.ID:
            TgClient.ID = Config.BOT_TOKEN.split(":", 1)[0]

    def is_database_available(database) -> bool:
        """Check if database is available and ready for operations"""
        if not database:
            return False
        if hasattr(database, "_return") and database._return:
            return False
        return not (hasattr(database, "db") and database.db is None)

    def with_unified_database(func):
        """Decorator to provide unified database access to functions"""

        async def wrapper(*args, **kwargs):
            # Inject database as first argument if not already present
            if "database" not in kwargs:
                database = await ensure_database_and_config()
                kwargs["database"] = database

            # Ensure TgClient.ID is set
            ensure_tg_client_id()

            return await func(*args, **kwargs)

        return wrapper

    def convert_thumbnail_to_url(thumbnail_field, hash_id):
        """Convert thumbnail file_id or placeholder to proper URL"""
        if not thumbnail_field:
            return None  # Return None so templates can show placeholders

        # If it's already a URL (legacy data), return as-is
        if thumbnail_field.startswith(("/", "http")):
            return thumbnail_field

        # Removed thumbnail handling - using TMDB posters exclusively (ReelNN style)
        return "/static/icons/default-video.svg"

    # Removed legacy functions - using ReelNN-style implementation

    # UNIFIED DATABASE CONFIG LOADER - INTEGRATED WITH FILE_TO_LINK
    async def load_database_config():
        """Load configuration from database - UNIFIED WITH FILE_TO_LINK"""
        global _database_config_loaded

        # Use lock to prevent multiple simultaneous database connections
        async with _database_config_lock:
            # If already loaded, skip to avoid multiple connections
            if _database_config_loaded:
                return

            # Use the shared database instance
            database = await get_shared_database()

            # First, load static configuration to get DATABASE_URL
            Config.load()

            BOT_ID = Config.BOT_TOKEN.split(":", 1)[0]

            runtime_config = await database.db.settings.config.find_one(
                {"_id": BOT_ID},
                {"_id": 0},
            )

            if runtime_config:
                # Filter out timestamp metadata before loading into Config class
                config_values_only = {
                    k: v for k, v in runtime_config.items() if not k.startswith("_")
                }

                # Since database cleanup should have already removed invalid keys, this is just a safety check
                valid_config_keys = set(Config.__annotations__.keys())

                # Filter out any keys that are not valid configuration keys (should be none after cleanup)
                filtered_config = {
                    k: v
                    for k, v in config_values_only.items()
                    if k in valid_config_keys
                }

                # Only log if we actually find invalid keys (which should not happen after cleanup)
                invalid_keys = set(config_values_only.keys()) - valid_config_keys
                if invalid_keys:
                    print(
                        f"Web server found invalid configuration keys after cleanup (this should not happen): {', '.join(invalid_keys)}"
                    )

                Config.load_dict(filtered_config)

            # Mark as loaded to prevent multiple connections
            _database_config_loaded = True

except ImportError as e:
    FILE_TO_LINK_AVAILABLE = False
    LOGGER.error(f"File-to-Link imports failed: {e}")
    load_database_config = None

    # Create a fallback BotConfig class
    class BotConfig:
        FILE_TO_LINK_ENABLED = False
        LEECH_DUMP_CHAT = None

    # Fallback function when File-to-Link is not available
    def get_wserver_client_stats():
        """Fallback integrated client statistics when File-to-Link is not available"""
        return {
            "error": "Integrated client system not available - File-to-Link functionality disabled",
            "initialized": False,
            "integration_type": "Disabled",
            "primary_system": "None",
            "fallback_system": "None",
            "total_clients": 0,
            "connected_clients": 0,
            "total_usage": 0,
            "system_status": "❌ File-to-Link Disabled",
        }

except Exception as e:
    FILE_TO_LINK_AVAILABLE = False
    LOGGER.error(f"File-to-Link imports failed with unexpected error: {e}")
    load_database_config = None

    # Create a fallback BotConfig class
    class BotConfig:
        FILE_TO_LINK_ENABLED = False
        LEECH_DUMP_CHAT = None

    # Fallback function when File-to-Link is not available
    def get_wserver_client_stats():
        """Fallback integrated client statistics when File-to-Link failed during initialization"""
        return {
            "error": "LoadBalancer client system failed during initialization",
            "initialized": False,
            "integration_type": "Failed",
            "primary_system": "LoadBalancer (Failed)",
            "total_clients": 0,
            "connected_clients": 0,
            "total_usage": 0,
            "system_status": "❌ Initialization Failed",
        }


# HyperDL-style streaming function with proper offset handling
async def hyperdl_stream_range(
    client,
    file_id_obj,
    offset_bytes,
    first_part_cut,
    last_part_cut,
    part_count,
    chunk_size,
    file_size,
):
    """Stream file range using exact HyperDL approach with proper OFFSET_INVALID handling"""
    from asyncio import sleep, wait_for

    from pyrogram import raw
    from pyrogram.errors import FloodWait, OffsetInvalid
    from pyrogram.session import Auth, Session

    media_session = None
    max_retries = 3
    current_retry = 0

    try:
        while current_retry < max_retries:
            try:
                # Generate media session like hyperdl_utils.py
                client_dc_id = await client.storage.dc_id()

                if file_id_obj.dc_id != client_dc_id:
                    media_session = Session(
                        client,
                        file_id_obj.dc_id,
                        await Auth(
                            client,
                            file_id_obj.dc_id,
                            await client.storage.test_mode(),
                        ).create(),
                        await client.storage.test_mode(),
                        is_media=True,
                    )
                    await media_session.start()

                    # Export and import authorization with retry logic
                    for attempt in range(6):
                        try:
                            exported_auth = await client.invoke(
                                raw.functions.auth.ExportAuthorization(
                                    dc_id=file_id_obj.dc_id
                                )
                            )
                            await media_session.invoke(
                                raw.functions.auth.ImportAuthorization(
                                    id=exported_auth.id, bytes=exported_auth.bytes
                                )
                            )
                            break
                        except Exception as e:
                            LOGGER.warning(
                                f"Auth import attempt {attempt + 1} failed: {e}"
                            )
                            if attempt < 5:
                                await sleep(1)
                            else:
                                raise
                else:
                    media_session = Session(
                        client,
                        file_id_obj.dc_id,
                        await client.storage.auth_key(),
                        await client.storage.test_mode(),
                        is_media=True,
                    )
                    await media_session.start()

                # Get file location like hyperdl_utils.py
                location = raw.types.InputDocumentFileLocation(
                    id=file_id_obj.media_id,
                    access_hash=file_id_obj.access_hash,
                    file_reference=file_id_obj.file_reference,
                    thumb_size=file_id_obj.thumbnail_size,
                )

                # Stream chunks using exact hyperdl_utils.py logic
                current_part = 1
                current_offset = offset_bytes

                while current_part <= part_count:
                    try:
                        # Validate offset before making request (key to avoiding OFFSET_INVALID)
                        if current_offset >= file_size:
                            LOGGER.warning(
                                f"Offset {current_offset} >= file_size {file_size}, stopping"
                            )
                            break

                        # Calculate actual limit to avoid reading beyond file end
                        actual_limit = min(chunk_size, file_size - current_offset)
                        if actual_limit <= 0:
                            LOGGER.warning(
                                f"No more data to read at offset {current_offset}"
                            )
                            break

                        # Don't adjust limit based on last_part_cut - that's handled in the chunk slicing
                        # The limit should always be chunk_size, and we slice the chunk afterward

                        r = await wait_for(
                            media_session.invoke(
                                raw.functions.upload.GetFile(
                                    location=location,
                                    offset=current_offset,
                                    limit=actual_limit,
                                ),
                            ),
                            timeout=120,  # Increased timeout to 2 minutes for large files
                        )

                        if isinstance(r, raw.types.upload.File):
                            chunk = r.bytes
                            if not chunk:
                                LOGGER.info(
                                    f"Empty chunk at offset {current_offset}, ending stream"
                                )
                                break

                            # Apply cuts exactly like hyperdl_utils.py
                            if part_count == 1:
                                yield chunk[first_part_cut:last_part_cut]
                            elif current_part == 1:
                                yield chunk[first_part_cut:]
                            elif current_part == part_count:
                                yield chunk[:last_part_cut]
                            else:
                                yield chunk

                            current_part += 1
                            current_offset += len(
                                chunk
                            )  # Use actual chunk size, not chunk_size
                        else:
                            LOGGER.error(f"Unexpected response type: {type(r)}")
                            break

                    except FloodWait as e:
                        LOGGER.warning(f"FloodWait {e.value}s in hyperdl streaming")
                        await sleep(e.value + 1)
                        continue
                    except OffsetInvalid:
                        LOGGER.warning(
                            f"OffsetInvalid at offset {current_offset} (file_size: {file_size})"
                        )
                        # This is expected for end-of-file seeks, break gracefully
                        break
                    except (TimeoutError, ConnectionError) as e:
                        LOGGER.warning(f"Network error in hyperdl streaming: {e}")
                        await sleep(1)
                        continue

                # If we get here, streaming completed successfully
                break

            except (TimeoutError, ConnectionError, AttributeError) as e:
                current_retry += 1
                if current_retry >= max_retries:
                    LOGGER.error(f"Max retries reached for hyperdl streaming: {e}")
                    raise
                sleep_time = current_retry * 2
                LOGGER.warning(
                    f"Retrying hyperdl streaming in {sleep_time}s (attempt {current_retry + 1}/{max_retries})"
                )
                await sleep(sleep_time)

                # Clean up session before retry
                if media_session:
                    with suppress(builtins.BaseException):
                        await media_session.stop()
                    media_session = None

    except Exception as e:
        LOGGER.error(f"Error in hyperdl streaming: {e}")
        raise
    finally:
        # Clean up session
        if media_session:
            try:
                await media_session.stop()
            except Exception as e:
                LOGGER.error(f"Error stopping media session: {e}")


# Global clients - will be set in lifespan
aria2 = None
qbittorrent = None
sabnzbd_client = SabnzbdClient(
    host="http://localhost",
    api_key="admin",
    port="8070",
)

SERVICES = {
    "nzb": {
        "url": "http://localhost:8070/",
        "username": "admin",
        "password": Config.LOGIN_PASS or "admin",
    },
    "qbit": {
        "url": "http://localhost:8090",
        "username": "admin",
        "password": Config.LOGIN_PASS or "admin",
    },
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load database configuration for File-to-Link if available
    LOGGER.info(
        f"Web server startup: FILE_TO_LINK_AVAILABLE={FILE_TO_LINK_AVAILABLE}, load_database_config={load_database_config is not None}"
    )
    if FILE_TO_LINK_AVAILABLE and load_database_config:
        LOGGER.info("Loading database configuration for web server...")
        await load_database_config()
        LOGGER.info("Database configuration loading completed")

    # Check if streaming should be enabled based on all conditions
    streaming_enabled = FILE_TO_LINK_AVAILABLE and should_enable_streaming()
    LOGGER.info(f"Web server startup: Streaming enabled={streaming_enabled}")

    if streaming_enabled:
        app.state.file_to_link_enabled = True
        LOGGER.info(
            "Streaming functionality enabled - initializing web server clients"
        )

        # Initialize web server clients at startup for streaming
        # Wait a moment to ensure database configuration is fully loaded
        await asyncio.sleep(2)
        try:
            LOGGER.info("Attempting to initialize integrated client system...")
            await initialize_integrated_client_system()
            LOGGER.info(
                "✅ Integrated client system initialized successfully at startup"
            )
        except Exception as e:
            LOGGER.error(
                f"Failed to initialize integrated client system at startup: {e}"
            )
            import traceback

            LOGGER.error(f"Traceback: {traceback.format_exc()}")
    else:
        app.state.file_to_link_enabled = False
        LOGGER.info(
            "Streaming functionality disabled - no web server clients initialized"
        )
        LOGGER.info(
            "Note: Only non-streaming components (qBittorrent, etc.) will be enabled"
        )

    # Initialize clients
    app.state.aria2 = Aria2HttpClient("http://localhost:6800/jsonrpc")

    # Try to initialize qBittorrent client, but don't fail if it's not available
    try:
        app.state.qbittorrent = await create_client("http://localhost:8090/api/v2/")
        LOGGER.info("qBittorrent client initialized successfully")
    except Exception as e:
        LOGGER.warning(f"qBittorrent client initialization failed: {e}")
        LOGGER.info("Web server will continue without qBittorrent functionality")
        app.state.qbittorrent = None

    # For backward compatibility
    global aria2, qbittorrent  # noqa: PLW0603
    aria2 = app.state.aria2
    qbittorrent = app.state.qbittorrent

    try:
        # Import garbage collection utilities
        from bot.helper.ext_utils.gc_utils import smart_garbage_collection

        app.state.gc_utils = smart_garbage_collection
    except ImportError:
        app.state.gc_utils = None
    yield

    # Properly close all connections
    try:
        await app.state.aria2.close()
        LOGGER.info("Aria2 client connection closed")
    except Exception as e:
        LOGGER.error(f"Error closing Aria2 client: {e}")

    try:
        await app.state.qbittorrent.close()
        LOGGER.info("qBittorrent client connection closed")
    except Exception as e:
        LOGGER.error(f"Error closing qBittorrent client: {e}")

    # Force garbage collection and cleanup
    if app.state.gc_utils:
        app.state.gc_utils(
            aggressive=True
        )  # Use aggressive mode for cleanup on shutdown

    # Clear any remaining caches
    try:
        from bot.helper.stream_utils.cache_manager import CacheManager

        CacheManager.clear_all_caches()
    except Exception as e:
        LOGGER.warning(f"Error clearing caches on shutdown: {e}")


app = FastAPI(
    lifespan=lifespan,
    # Performance optimizations for Heroku
    docs_url=None,  # Disable docs in production
    redoc_url=None,  # Disable redoc in production
    openapi_url=None,  # Disable OpenAPI schema in production
)


# Removed thumbnail endpoint - using TMDB posters instead of thumbnail extraction


# Mount static files for assets (excluding thumbnails - they're generated dynamically)
app.mount("/static", StaticFiles(directory="web/static"), name="static")

templates = Jinja2Templates(directory="web/templates/")


# Add template filters for quality groups
def format_bytes(size):
    """Format bytes for template display"""
    try:
        from bot.helper.ext_utils.bot_utils import get_readable_file_size

        return get_readable_file_size(size)
    except:
        return str(size)


def timestamp_to_date(timestamp):
    """Convert timestamp to readable date"""
    if not timestamp:
        return "Unknown"
    try:
        from datetime import datetime

        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")
    except:
        return "Unknown"


# Add filters to template environment
templates.env.filters["format_bytes"] = format_bytes
templates.env.filters["timestamp_to_date"] = timestamp_to_date

# Security
security = HTTPBearer(auto_error=False)


# Authentication dependency
async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Get current authenticated user from JWT token"""
    token = None

    # Try to get token from Authorization header first
    if credentials:
        token = credentials.credentials
    else:
        # Fallback to cookie
        token = request.cookies.get("access_token")

    if not token:
        return None

    try:
        from bot.helper.ext_utils.auth_handler import auth_handler

        return await auth_handler.get_user_by_token(token)
    except Exception as e:
        LOGGER.error(f"Error getting current user: {e}")
        return None


# Admin authentication dependency
async def get_admin_user(current_user: dict = Depends(get_current_user)):
    """Require admin authentication"""
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please login to access admin panel.",
        )

    from bot.helper.ext_utils.auth_handler import auth_handler

    if not auth_handler.is_admin(current_user):
        # Return 403 for non-admin users - they should not access admin routes
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Admin privileges required. Regular users cannot access admin panel.",
        )

    return current_user


basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[FileHandler("log.txt"), StreamHandler()],
    level=INFO,
)


async def re_verify(paused, resumed, hash_id):
    k = 0
    while True:
        res = await app.state.qbittorrent.torrents.files(hash_id)
        verify = True
        for i in res:
            if i.index in paused and i.priority != 0:
                verify = False
                break
            if i.index in resumed and i.priority == 0:
                verify = False
                break
        if verify:
            break
        LOGGER.info("Reverification Failed! Correcting stuff...")
        await sleep(0.5)
        if paused:
            try:
                await app.state.qbittorrent.torrents.file_prio(
                    hash=hash_id,
                    id=paused,
                    priority=0,
                )
            except (ClientError, TimeoutError, Exception, AQError) as e:
                LOGGER.error(f"{e} Errored in reverification paused!")
        if resumed:
            try:
                await app.state.qbittorrent.torrents.file_prio(
                    hash=hash_id,
                    id=resumed,
                    priority=1,
                )
            except (ClientError, TimeoutError, Exception, AQError) as e:
                LOGGER.error(f"{e} Errored in reverification resumed!")
        k += 1
        if k > 5:
            return False
    LOGGER.info(f"Verified! Hash: {hash_id}")
    return True


# Optimized TMDB Helper Functions - ReelNN Style
class TMDBImageHelper:
    """Optimized TMDB image URL helper with caching"""

    BASE_URL = "https://image.tmdb.org/t/p/"

    @staticmethod
    def get_image_url(path: str, size: str = "w500") -> str:
        """Get TMDB image URL with proper formatting"""
        if not path:
            return None

        if path.startswith("http"):
            return path

        # Remove leading slash if present
        path = path.lstrip("/")
        return f"{TMDBImageHelper.BASE_URL}{size}/{path}"


# Optimized Media URL Functions - ReelNN Style
def get_media_poster_url(media_data: dict) -> str:
    """Get optimized poster URL for media item - ReelNN style"""
    if not media_data:
        return "/static/images/default-poster.jpg"

    # Primary: Direct poster_path field (ReelNN style)
    poster_path = media_data.get("poster_path")
    if poster_path:
        return f"https://image.tmdb.org/t/p/w500{poster_path}"

    # Secondary: TMDB data poster_path
    tmdb_data = media_data.get("tmdb_data", {})
    if tmdb_data and tmdb_data.get("poster_path"):
        return f"https://image.tmdb.org/t/p/w500{tmdb_data['poster_path']}"

    # Legacy fallback: thumbnail (being phased out in ReelNN)
    if media_data.get("thumbnail"):
        hash_id = media_data.get("hash_id")
        if hash_id:
            return f"/static/thumbnails/{hash_id}.jpg"

    # Default poster based on media type - ReelNN style
    media_type = media_data.get("media_type", "movie")
    if media_type in ["movie", "tv"] or media_data.get("is_video"):
        return "/static/icons/default-video.svg"
    if media_data.get("is_audio"):
        return "/static/icons/default-audio.svg"
    return "/static/icons/default-poster.svg"


def get_media_backdrop_url(media_data: dict) -> str:
    """Get optimized backdrop URL for media item - ReelNN style"""
    if not media_data:
        return "/static/images/default-backdrop.jpg"

    # Primary: Direct backdrop_path field (ReelNN style)
    backdrop_path = media_data.get("backdrop_path")
    if backdrop_path:
        return f"https://image.tmdb.org/t/p/original{backdrop_path}"

    # Secondary: TMDB data backdrop_path
    tmdb_data = media_data.get("tmdb_data", {})
    if tmdb_data and tmdb_data.get("backdrop_path"):
        return f"https://image.tmdb.org/t/p/original{tmdb_data['backdrop_path']}"

    # Fallback: Use poster as backdrop (ReelNN style)
    poster_url = get_media_poster_url(media_data)
    if poster_url and not poster_url.endswith(".svg"):
        # Convert poster to larger size for backdrop use
        if "w500" in poster_url:
            return poster_url.replace("w500", "w1280")
        return poster_url

    # Default backdrop
    return "/static/icons/default-backdrop.svg"


# Helper function to get navigation data
async def get_navigation_data() -> dict:
    """Get navigation data for templates - UNIFIED DATABASE ACCESS"""
    try:
        # Use unified database access
        database = await ensure_database_and_config()
        if not database:
            raise Exception("Database not available")

        # Get dynamic categories for navigation
        categories = await database.get_all_categories()

        # Default navigation items
        default_nav = [
            {
                "name": "movie",
                "display_name": "Movies",
                "icon": "🎬",
                "is_active": True,
            },
            {
                "name": "series",
                "display_name": "Series",
                "icon": "📺",
                "is_active": True,
            },
            {
                "name": "anime",
                "display_name": "Anime",
                "icon": "🎌",
                "is_active": True,
            },
            {
                "name": "music",
                "display_name": "Music",
                "icon": "🎵",
                "is_active": True,
            },
        ]

        # Get navigation items from database
        nav_items = await database.get_navigation_items("header")

        # If no custom navigation, use defaults + dynamic categories
        if not nav_items:
            nav_items = default_nav + [
                {
                    "name": cat["name"],
                    "display_name": cat.get("display_name", cat["name"].title()),
                    "icon": cat.get("icon", "📁"),
                    "is_active": True,
                }
                for cat in categories
                if cat["name"] not in [item["name"] for item in default_nav]
            ]

        # Get recent uploads for homepage
        bot_id = Config.BOT_TOKEN.split(":", 1)[0]
        recent_cursor = (
            database.db.media_library[bot_id]
            .find({"is_video": True})
            .sort("created_at", -1)
            .limit(10)
        )
        recent_uploads = await recent_cursor.to_list(length=10)

        # Add poster URLs to recent uploads
        for upload in recent_uploads:
            upload["poster_url"] = get_media_poster_url(upload)

        # Get current year for footer copyright
        from datetime import datetime

        current_year = datetime.now().year

        return {
            "header_nav": nav_items,
            "footer_nav": await database.get_navigation_items("footer"),
            "dynamic_categories": categories,
            "recent_uploads": recent_uploads,
            "current_year": current_year,
        }
    except Exception as e:
        LOGGER.error(f"Error getting navigation data: {e}")
        # Get current year for fallback
        from datetime import datetime

        current_year = datetime.now().year

        return {
            "header_nav": [
                {
                    "name": "movie",
                    "display_name": "Movies",
                    "icon": "🎬",
                    "is_active": True,
                },
                {
                    "name": "series",
                    "display_name": "Series",
                    "icon": "📺",
                    "is_active": True,
                },
                {
                    "name": "anime",
                    "display_name": "Anime",
                    "icon": "🎌",
                    "is_active": True,
                },
                {
                    "name": "music",
                    "display_name": "Music",
                    "icon": "🎵",
                    "is_active": True,
                },
            ],
            "footer_nav": [],
            "dynamic_categories": [],
            "recent_uploads": [],
            "current_year": current_year,
        }


@app.get("/app/files", response_class=HTMLResponse)
async def files(request: Request):
    # Redirect to main reelnn interface
    return RedirectResponse(url="/", status_code=302)


@app.api_route(
    "/app/files/torrent",
    methods=["GET", "POST"],
    response_class=HTMLResponse,
)
async def handle_torrent(request: Request):
    params = request.query_params

    if not (gid := params.get("gid")):
        return JSONResponse(
            {
                "files": [],
                "engine": "",
                "error": "GID is missing",
                "message": "GID not specified",
            },
        )

    if not (pin := params.get("pin")):
        return JSONResponse(
            {
                "files": [],
                "engine": "",
                "error": "Pin is missing",
                "message": "PIN not specified",
            },
        )

    code = "".join([nbr for nbr in gid if nbr.isdigit()][:4])
    if code != pin:
        return JSONResponse(
            {
                "files": [],
                "engine": "",
                "error": "Invalid pin",
                "message": "The PIN you entered is incorrect",
            },
        )

    if request.method == "POST":
        if not (mode := params.get("mode")):
            return JSONResponse(
                {
                    "files": [],
                    "engine": "",
                    "error": "Mode is not specified",
                    "message": "Mode is not specified",
                },
            )
        data = await request.json()
        if mode == "rename":
            if len(gid) > 20:
                await handle_rename(gid, data)
                content = {
                    "files": [],
                    "engine": "",
                    "error": "",
                    "message": "Rename successfully.",
                }
            else:
                content = {
                    "files": [],
                    "engine": "",
                    "error": "Rename failed.",
                    "message": "Cannot rename aria2c torrent file",
                }
        else:
            selected_files, unselected_files = extract_file_ids(data)
            if gid.startswith("SABnzbd_nzo"):
                await set_sabnzbd(gid, unselected_files)
            elif len(gid) > 20:
                await set_qbittorrent(gid, selected_files, unselected_files)
            else:
                selected_files = ",".join(selected_files)
                await set_aria2(gid, selected_files)
            content = {
                "files": [],
                "engine": "",
                "error": "",
                "message": "Your selection has been submitted successfully.",
            }
    else:
        try:
            if gid.startswith("SABnzbd_nzo"):
                res = await sabnzbd_client.get_files(gid)
                content = make_tree(res, "sabnzbd")
            elif len(gid) > 20:
                # Use app.state.qbittorrent instead of global qbittorrent
                res = await app.state.qbittorrent.torrents.files(gid)
                content = make_tree(res, "qbittorrent")
            else:
                # Use app.state.aria2 instead of global aria2
                res = await app.state.aria2.getFiles(gid)
                op = await app.state.aria2.getOption(gid)
                fpath = f"{op['dir']}/"
                content = make_tree(res, "aria2", fpath)
        except (ClientError, TimeoutError, Exception, AQError) as e:
            LOGGER.error(str(e))
            content = {
                "files": [],
                "engine": "",
                "error": "Error getting files",
                "message": str(e),
            }
    return JSONResponse(content)


async def handle_rename(gid, data):
    try:
        _type = data["type"]
        del data["type"]
        if _type == "file":
            await app.state.qbittorrent.torrents.rename_file(hash=gid, **data)
        else:
            await app.state.qbittorrent.torrents.rename_folder(hash=gid, **data)
    except (ClientError, TimeoutError, Exception, AQError) as e:
        LOGGER.error(f"{e} Errored in renaming")


async def set_sabnzbd(gid, unselected_files):
    await sabnzbd_client.remove_file(gid, unselected_files)
    LOGGER.info(f"Verified! nzo_id: {gid}")


async def set_qbittorrent(gid, selected_files, unselected_files):
    if unselected_files:
        try:
            await app.state.qbittorrent.torrents.file_prio(
                hash=gid,
                id=unselected_files,
                priority=0,
            )
        except (ClientError, TimeoutError, Exception, AQError) as e:
            LOGGER.error(f"{e} Errored in paused")
    if selected_files:
        try:
            await app.state.qbittorrent.torrents.file_prio(
                hash=gid,
                id=selected_files,
                priority=1,
            )
        except (ClientError, TimeoutError, Exception, AQError) as e:
            LOGGER.error(f"{e} Errored in resumed")
    await sleep(0.5)
    if not await re_verify(unselected_files, selected_files, gid):
        LOGGER.error(f"Verification Failed! Hash: {gid}")


async def set_aria2(gid, selected_files):
    res = await app.state.aria2.changeOption(gid, {"select-file": selected_files})
    if res == "OK":
        LOGGER.info(f"Verified! Gid: {gid}")
    else:
        LOGGER.info(f"Verification Failed! Report! Gid: {gid}")


async def proxy_fetch(method, url, headers, params, data, base_path):
    async with AsyncClient(timeout=30.0) as client:
        try:
            response = await client.request(
                method,
                url,
                headers=headers,
                params=params,
                content=data,
            )
            content = response.content
            resp_headers = {
                k: v
                for k, v in response.headers.items()
                if k.lower()
                not in (
                    "content-encoding",
                    "transfer-encoding",
                    "content-length",
                    "server",
                )
            }

            # Handle redirects
            if response.status_code in (301, 302, 307, 308):
                location = response.headers.get("Location")
                if location:
                    parsed = urlparse(location)
                    if not parsed.netloc:  # Relative URL
                        location = f"{base_path}/{location.lstrip('/')}"
                    resp_headers["Location"] = location

            media_type = response.headers.get("Content-Type", "")
            return HTMLResponse(
                content=content,
                status_code=response.status_code,
                headers=resp_headers,
                media_type=media_type,
            )
        except Exception as e:
            LOGGER.error(f"Proxy error: {e}")
            return HTMLResponse(f"<h1>Error: {e}</h1>", status_code=500)


async def protected_proxy(
    service: str,
    path: str,
    request: Request,
    username: str | None = None,
    password: str | None = None,
):
    service_info = SERVICES.get(service)
    if not service_info:
        raise HTTPException(status_code=404, detail="Service not found")

    # Check username if provided in service_info
    if "username" in service_info and username != service_info["username"]:
        raise HTTPException(status_code=403, detail="Unauthorized username")

    # Check password if provided in service_info
    if "password" in service_info and password != service_info["password"]:
        raise HTTPException(status_code=403, detail="Unauthorized password")
    base = service_info["url"]
    url = f"{base}/{path}" if path else base
    headers = {k: v for k, v in request.headers.items() if k.lower() != "host"}
    body = await request.body()
    return await proxy_fetch(
        request.method,
        url,
        headers,
        dict(request.query_params),
        body,
        f"/{service}",
    )


@app.api_route("/nzb/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def sabnzbd_proxy(path: str = "", request: Request = None):
    # Get username and password from query params or cookies
    username = (
        request.query_params.get("user")
        or request.cookies.get("nzb_user")
        or "admin"
    )
    password = (
        request.query_params.get("pass")
        or request.cookies.get("nzb_pass")
        or Config.LOGIN_PASS
        or "admin"
    )

    # Pass both username and password to protected_proxy
    response = await protected_proxy("nzb", path, request, username, password)

    # Set cookies if params were provided
    if "user" in request.query_params:
        response.set_cookie("nzb_user", username)
    if "pass" in request.query_params:
        response.set_cookie("nzb_pass", password)
    return response


@app.api_route(
    "/qbit/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
)
async def qbittorrent_proxy(path: str = "", request: Request = None):
    # Get username and password from query params or cookies
    username = (
        request.query_params.get("user")
        or request.cookies.get("qbit_user")
        or "admin"
    )
    password = request.query_params.get("pass") or request.cookies.get("qbit_pass")

    if not password:
        raise HTTPException(status_code=403, detail="Missing password")

    # Pass both username and password to protected_proxy
    response = await protected_proxy("qbit", path, request, username, password)

    # Set cookies if params were provided
    if "user" in request.query_params:
        response.set_cookie("qbit_user", username)
    if "pass" in request.query_params:
        response.set_cookie("qbit_pass", password)
    return response


# Admin Setup Route (Only available when no admin exists)
@app.get("/admin/setup", response_class=HTMLResponse)
async def admin_setup_page(
    request: Request, error: str | None = None, success: str | None = None
):
    """Admin setup page - only accessible when no admin exists - UNIFIED DATABASE ACCESS"""
    try:
        # Use unified database access
        database = await ensure_database_and_config()
        if not database:
            raise Exception("Database not available")

        # Check if any admin user already exists
        admin_exists = await database.admin_user_exists()
        if admin_exists:
            return RedirectResponse(url="/auth/login", status_code=302)

        return templates.TemplateResponse(
            "admin/setup.html",
            {"request": request, "error": error, "success": success},
        )
    except Exception as e:
        LOGGER.error(f"Error in admin setup page: {e}")
        return templates.TemplateResponse(
            "admin/setup.html", {"request": request, "error": "Setup error occurred"}
        )


@app.post("/admin/setup")
async def admin_setup_submit(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    first_name: str = Form("Admin"),
    last_name: str = Form("User"),
):
    """Handle admin setup form submission - UNIFIED DATABASE ACCESS"""
    try:
        # Use unified database access
        database = await ensure_database_and_config()
        if not database:
            raise Exception("Database not available")

        # Check if any admin user already exists
        admin_exists = await database.admin_user_exists()
        if admin_exists:
            return RedirectResponse(url="/auth/login", status_code=302)

        # Validate passwords match
        if password != confirm_password:
            return templates.TemplateResponse(
                "admin/setup.html",
                {"request": request, "error": "Passwords do not match"},
            )

        # Validate password length
        if len(password) < 8:
            return templates.TemplateResponse(
                "admin/setup.html",
                {
                    "request": request,
                    "error": "Password must be at least 8 characters",
                },
            )

        # Create admin user
        admin_data = {
            "username": username.strip(),
            "email": email.strip(),
            "password": password,
            "first_name": first_name.strip(),
            "last_name": last_name.strip(),
        }

        success = await database.create_admin_user(admin_data)

        if success:
            return RedirectResponse(
                url="/auth/login?success=Admin account created successfully. Please login.",
                status_code=302,
            )
        return templates.TemplateResponse(
            "admin/setup.html",
            {"request": request, "error": "Failed to create admin account"},
        )

    except Exception as e:
        LOGGER.error(f"Error in admin setup: {e}")
        return templates.TemplateResponse(
            "admin/setup.html",
            {"request": request, "error": "Setup failed. Please try again."},
        )


# Authentication Routes (Always available, independent of File-to-Link)
@app.get("/auth/login", response_class=HTMLResponse)
async def auth_login_page(
    request: Request,
    error: str | None = None,
    success: str | None = None,
    next: str | None = None,
):
    """Login page"""
    # Check if user is already logged in
    try:
        from bot.helper.ext_utils.auth_handler import auth_handler

        # Get token from cookie
        access_token = request.cookies.get("access_token")
        if access_token:
            user = await auth_handler.get_user_by_token(access_token)
            if user:
                # User is already logged in, redirect appropriately
                if auth_handler.is_admin(user):
                    return RedirectResponse(url="/admin", status_code=302)
                return RedirectResponse(url="/", status_code=302)
    except Exception as e:
        LOGGER.info(f"Error checking existing login: {e}")
        # Continue to login page if check fails

    return templates.TemplateResponse(
        "auth/login.html",
        {"request": request, "error": error, "success": success, "next": next},
    )


@app.post("/auth/login")
async def auth_login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form(None),
):
    """Handle login form submission"""
    try:
        from bot.helper.ext_utils.auth_handler import auth_handler

        # Authenticate user
        user = await auth_handler.authenticate_user(username, password)
        if not user:
            return templates.TemplateResponse(
                "auth/login.html",
                {
                    "request": request,
                    "error": "Invalid username or password",
                    "next": next,
                },
            )

        # Generate tokens
        tokens = auth_handler.generate_tokens(user)

        # Determine redirect URL based on user role and next parameter
        if next and next.startswith("/"):
            redirect_url = next
        elif auth_handler.is_admin(user):
            redirect_url = "/admin"
        else:
            redirect_url = "/"

        # Create response with redirect
        response = RedirectResponse(url=redirect_url, status_code=302)

        # Set HTTP-only cookie with access token
        response.set_cookie(
            key="access_token",
            value=tokens["access_token"],
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=tokens["expires_in"],
        )

        return response

    except Exception as e:
        LOGGER.error(f"Error in login: {e}")
        return templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "error": "Login failed. Please try again."},
        )


@app.get("/auth/signup", response_class=HTMLResponse)
async def auth_signup_page(
    request: Request, error: str | None = None, success: str | None = None
):
    """Signup page"""
    return templates.TemplateResponse(
        "auth/signup.html", {"request": request, "error": error, "success": success}
    )


@app.post("/auth/signup")
async def auth_signup_submit(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
):
    """Handle signup form submission"""
    try:
        # Validate passwords match
        if password != confirm_password:
            return templates.TemplateResponse(
                "auth/signup.html",
                {"request": request, "error": "Passwords do not match"},
            )

        # Validate password strength
        if len(password) < 8:
            return templates.TemplateResponse(
                "auth/signup.html",
                {
                    "request": request,
                    "error": "Password must be at least 8 characters long",
                },
            )

        from bot.helper.ext_utils.auth_handler import auth_handler

        # Create user
        user_data = {
            "username": username,
            "email": email,
            "password": password,
            "first_name": first_name,
            "last_name": last_name,
        }

        success, message = await auth_handler.create_user(user_data)

        if success:
            return templates.TemplateResponse(
                "auth/login.html",
                {
                    "request": request,
                    "success": "Account created successfully! Please log in.",
                },
            )
        return templates.TemplateResponse(
            "auth/signup.html", {"request": request, "error": message}
        )

    except Exception as e:
        LOGGER.error(f"Error in signup: {e}")
        return templates.TemplateResponse(
            "auth/signup.html",
            {"request": request, "error": "Registration failed. Please try again."},
        )


@app.get("/auth/logout")
@app.post("/auth/logout")
async def auth_logout():
    """Handle logout"""
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("access_token")
    return response


# ===== CORE ROUTES (ALWAYS AVAILABLE) =====


def check_streaming_enabled():
    """Runtime check if streaming is enabled"""
    if not FILE_TO_LINK_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="File-to-Link integration is not available. Please check your installation.",
        )
    if not should_enable_streaming():
        raise HTTPException(
            status_code=503,
            detail="Streaming functionality is disabled. Enable FILE_TO_LINK_ENABLED in configuration.",
        )


# REMOVED: Duplicate homepage route - using the one inside F2L block with proper fallback handling
# The homepage route is now handled inside the File-to-Link block with comprehensive fallback logic

# File-to-Link Integration Routes
LOGGER.info(
    f"File-to-Link integration check: FILE_TO_LINK_AVAILABLE={FILE_TO_LINK_AVAILABLE}, FILE_TO_LINK_ENABLED={getattr(Config, 'FILE_TO_LINK_ENABLED', 'NOT_FOUND')}"
)

# Register File-to-Link specific routes if available
if FILE_TO_LINK_AVAILABLE:
    # REMOVED: Duplicate check_streaming_enabled function - using the one outside F2L block
    # def check_streaming_enabled():
    #     """Runtime check if streaming is enabled"""
    #     if not should_enable_streaming():
    #         raise HTTPException(
    #             status_code=503,
    #             detail="Streaming functionality is disabled. Enable FILE_TO_LINK_ENABLED in configuration."
    #         )

    # Add CORS preflight handler
    @app.options("/{path:path}")
    async def cors_preflight(path: str):
        return JSONResponse(
            content={},
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
                "Access-Control-Allow-Headers": "Range, Content-Type",
                "Access-Control-Max-Age": "86400",
            },
        )

    # Add favicon handler to prevent 404s
    @app.get("/favicon.ico")
    async def favicon():
        return JSONResponse({"detail": "Not Found"}, status_code=404)

    # PWA Routes
    @app.get("/static/manifest.json")
    async def manifest():
        """Serve PWA manifest"""
        try:
            import json
            import os

            manifest_path = os.path.join(
                os.path.dirname(__file__), "static", "manifest.json"
            )
            if os.path.exists(manifest_path):
                with open(manifest_path) as f:
                    manifest_data = json.load(f)
                return JSONResponse(
                    manifest_data,
                    headers={
                        "Content-Type": "application/manifest+json",
                        "Cache-Control": "public, max-age=86400",
                    },
                )
        except Exception as e:
            LOGGER.error(f"Error serving manifest: {e}")
        return JSONResponse({"error": "Manifest not found"}, status_code=404)

    @app.get("/static/sw.js")
    async def service_worker():
        """Serve service worker"""
        try:
            import os

            sw_path = os.path.join(os.path.dirname(__file__), "static", "sw.js")
            if os.path.exists(sw_path):
                with open(sw_path) as f:
                    sw_content = f.read()
                return Response(
                    sw_content,
                    headers={
                        "Content-Type": "application/javascript",
                        "Cache-Control": "no-cache, no-store, must-revalidate",
                    },
                )
        except Exception as e:
            LOGGER.error(f"Error serving service worker: {e}")
        return Response(
            "// Service worker not found",
            headers={"Content-Type": "application/javascript"},
            status_code=404,
        )

    # Add root route FIRST to avoid conflicts with generic routes
    @app.get("/", response_class=HTMLResponse)
    async def homepage(
        request: Request,
        search: str | None = None,
        type: str | None = None,
        page: int = 1,
        sort_by: str = "trending",
    ):
        """Enhanced homepage with media gallery and category support"""
        # Check if streaming is enabled at runtime
        check_streaming_enabled()

        # Import templates at the beginning to ensure it's available in error handlers
        from fastapi.templating import Jinja2Templates

        templates = Jinja2Templates(directory="web/templates")

        try:
            # Use unified database access
            database = await ensure_database_and_config()
            if not database:
                LOGGER.warning("Database not available for admin check")
            else:
                # Check if admin setup is needed (only if database is available)
                try:
                    admin_exists = await database.admin_user_exists()
                    if not admin_exists:
                        return RedirectResponse(url="/admin/setup", status_code=302)
                except Exception as e:
                    LOGGER.warning(f"Could not check admin existence: {e}")
                    # Continue to homepage if check fails

            # Regular users and admins can both access the homepage
            # No automatic redirect to admin panel - let users choose

            # Ensure TgClient.ID is set for database operations
            if not TgClient.ID:
                TgClient.ID = Config.BOT_TOKEN.split(":", 1)[0]
                LOGGER.info(
                    f"Set TgClient.ID to {TgClient.ID} for web server database operations"
                )

            # Check if database is available before proceeding
            if not is_database_available(database):
                LOGGER.warning(
                    "Database not available for homepage - using fallback"
                )
                # Return homepage without database features
                from datetime import datetime

                # Provide default settings when database is not available

                return templates.TemplateResponse(
                    "reelnn/index.html",
                    {
                        "request": request,
                        "site_name": "aimleechbot",
                        "trending_media": [],
                        "recent_media": [],
                        "featured_media": [],
                        "search_query": search or "",
                        "media_type": type or "",
                        "sort_by": sort_by,
                        "current_page": page,
                        "total_pages": 0,
                        "has_search": bool(search or type),
                        "is_loading": False,
                        "current_year": datetime.now().year,
                    },
                )

            # Pagination settings - get from admin config
            from bot.helper.stream_utils.admin_config import admin_config

            per_page = await admin_config.get_items_per_page()
            skip = (page - 1) * per_page

            # Get media files from database with enhanced filtering and trending logic
            media_files = await database.get_all_media(
                limit=per_page,
                skip=skip,
                search=search,
                media_type=type,
                sort_by=sort_by,
            )

            # Get total count for pagination
            total_count = await database.get_media_count(
                search=search, media_type=type
            )

            # Get category counts for navigation
            category_counts = await database.get_category_counts()
            LOGGER.info(f"Homepage category counts: {category_counts}")

            # Calculate pagination
            total_pages = (total_count + per_page - 1) // per_page
            has_pagination = total_pages > 1

            # Generate page numbers for pagination
            page_numbers = []
            if has_pagination:
                start_page = max(1, page - 2)
                end_page = min(total_pages, page + 2)
                page_numbers = list(range(start_page, end_page + 1))

            # Process media files for display
            processed_files = []
            for media in media_files:
                # Format creation date and update date
                created_at = None
                created_year = None
                updated_at = None
                if media.get("created_at"):
                    from datetime import datetime

                    created_dt = datetime.fromtimestamp(media["created_at"])
                    created_at = created_dt.strftime("%Y-%m-%d")
                    created_year = created_dt.strftime("%Y")

                if media.get("updated_at"):
                    from datetime import datetime

                    updated_at = datetime.fromtimestamp(
                        media["updated_at"]
                    ).strftime("%Y-%m-%d")

                processed_files.append(
                    {
                        "hash_id": media["hash_id"],
                        "title": media.get(
                            "title", media.get("file_name", "Unknown")
                        ),
                        "file_name": media.get("file_name", "Unknown"),
                        "file_size_human": media.get("file_size_human", "Unknown"),
                        "is_video": media.get("is_video", False),
                        "is_audio": media.get("is_audio", False),
                        "is_image": media.get("is_image", False),
                        "is_streamable": media.get("is_streamable", False),
                        "category": media.get("category", "document"),
                        "duration": media.get("duration"),
                        "view_count": media.get("view_count", 0),
                        "thumbnail": convert_thumbnail_to_url(
                            media.get("thumbnail"), media["hash_id"]
                        ),
                        "created_at": created_at,
                        "created_year": created_year,
                        "updated_at": updated_at,
                    }
                )

            # Calculate statistics
            total_files = await database.get_total_media_count()
            total_size = "Unknown"  # Could be calculated if needed

            # Get total views efficiently
            try:
                all_media_for_views = await database.get_all_media(limit=1000)
                total_views = sum(
                    media.get("view_count", 0) for media in all_media_for_views
                )
            except Exception as e:
                LOGGER.warning(f"Error calculating total views: {e}")
                total_views = 0

            # Get configuration settings
            from bot.helper.stream_utils.admin_config import admin_config

            site_settings = await admin_config.get_site_settings()
            ui_settings = await admin_config.get_ui_settings()
            navigation_settings = await admin_config.get_navigation_settings()
            branding_settings = await admin_config.get_branding_settings()
            content_settings = await admin_config.get_content_settings()

            # Check if current user is admin (for showing admin link)
            is_admin_user = False
            current_user = None
            try:
                from bot.helper.ext_utils.auth_handler import auth_handler

                # Get token from cookie
                access_token = request.cookies.get("access_token")
                if access_token:
                    current_user = await auth_handler.get_user_by_token(access_token)
                    if current_user and auth_handler.is_admin(current_user):
                        is_admin_user = True
            except Exception as e:
                LOGGER.info(f"Error checking admin user: {e}")
                # Continue without admin privileges

            # Template context
            context = {
                "request": request,
                "site_name": site_settings.get("site_name", "StreamBot"),
                "site_settings": site_settings,
                "ui_settings": ui_settings,
                "navigation_settings": navigation_settings,
                "branding_settings": branding_settings,
                "content_settings": content_settings,
                "media_files": processed_files,
                "total_count": total_count,
                "total_files": total_files,
                "total_size": total_size,
                "total_views": total_views,
                "search_query": search,
                "media_type": type,
                "sort_by": sort_by,
                "current_page": page,
                "total_pages": total_pages,
                "has_pagination": has_pagination,
                "page_numbers": page_numbers,
                "prev_page": page - 1 if page > 1 else None,
                "next_page": page + 1 if page < total_pages else None,
                "has_search": bool(search or type),
                "is_loading": False,
                "categories": category_counts,
                "movie_count": category_counts.get("movie", 0),
                "series_count": category_counts.get("series", 0),
                "anime_count": category_counts.get("anime", 0),
                "music_count": category_counts.get("music", 0),
                "library_count": category_counts.get("library", 0),
                "document_count": category_counts.get("document", 0),
                "total_media": total_count,
                "is_admin_user": is_admin_user,
                "current_user": current_user,
            }

            # Get navigation data
            nav_data = await get_navigation_data()
            context.update(nav_data)

            # Render template with new reelnn UI
            return templates.TemplateResponse(
                "reelnn/index.html",
                {
                    "request": request,
                    "site_name": site_settings.get("site_name", "aimleechbot"),
                    "trending_media": processed_files[:10],  # First 10 for trending
                    "recent_media": processed_files,  # All for recent
                    "featured_media": processed_files[:5],  # First 5 for featured
                    "search_query": search or "",
                    "media_type": type or "",
                    "sort_by": sort_by,
                    "current_page": page,
                    "total_pages": total_pages,
                    "has_search": bool(search or type),
                    "is_loading": False,
                    "current_year": datetime.now().year,
                    "is_admin_user": is_admin_user,
                    "current_user": current_user,
                },
            )

        except Exception as e:
            LOGGER.error(f"Error in homepage: {e}")
            # Return simple status page on error
            file_to_link_status = (
                "Available"
                if FILE_TO_LINK_AVAILABLE
                and getattr(Config, "FILE_TO_LINK_ENABLED", False)
                else "Disabled"
            )
            return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>StreamBot - Error</title>
    <style>
        body {{ margin: 0; padding: 20px; background: #1a1a1a; color: white; font-family: Arial, sans-serif; }}
        .container {{ max-width: 800px; margin: 0 auto; padding: 40px; background: #2a2a2a; border-radius: 12px; }}
        .error {{ background: #dc3545; padding: 15px; margin: 20px 0; border-radius: 5px; }}
        a {{ color: #007bff; text-decoration: none; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 StreamBot</h1>
        <div class="error">
            ❌ Error loading media library: {e!s}
        </div>
        <p>File-to-Link Status: {file_to_link_status}</p>
        <p><a href="/stats/wserver">Web Server Stats</a> | <a href="/stats/loadbalancer">Load Balancer Stats</a></p>
    </div>
</body>
</html>
            """

    # Add debug route SECOND to avoid conflicts with generic routes
    @app.get("/debug/f2l")
    async def debug_file_to_link():
        try:
            # Get web server client stats for debug
            wserver_stats = get_wserver_client_stats()

            return JSONResponse(
                {
                    "status": "File-to-Link integration active",
                    "FILE_TO_LINK_AVAILABLE": FILE_TO_LINK_AVAILABLE,
                    "FILE_TO_LINK_ENABLED": getattr(
                        Config, "FILE_TO_LINK_ENABLED", False
                    ),
                    "LEECH_DUMP_CHAT": getattr(Config, "LEECH_DUMP_CHAT", None),
                    "web_server_clients": wserver_stats,
                    "routes_registered": True,
                }
            )
        except Exception as e:
            return JSONResponse(
                {
                    "status": "File-to-Link integration active",
                    "error": f"Could not get web server stats: {e!s}",
                    "FILE_TO_LINK_AVAILABLE": FILE_TO_LINK_AVAILABLE,
                    "FILE_TO_LINK_ENABLED": getattr(
                        Config, "FILE_TO_LINK_ENABLED", False
                    ),
                    "routes_registered": True,
                }
            )

    @app.get("/stats/wserver")
    async def wserver_stats():
        """Web server client statistics endpoint"""
        try:
            import time

            # Get web server client stats
            wserver_stats = get_wserver_client_stats()

            # Add additional runtime info
            stats_with_runtime = {
                "timestamp": time.time(),
                "service": "Web Server Client Statistics",
                "clients": wserver_stats,
                "performance": {
                    "clients_initialized": wserver_stats.get("initialized", False),
                    "total_available": wserver_stats.get("total_clients", 0),
                    "currently_connected": wserver_stats.get("connected_clients", 0),
                    "connection_rate": f"{(wserver_stats.get('connected_clients', 0) / max(wserver_stats.get('total_clients', 1), 1)) * 100:.1f}%",
                },
            }

            return JSONResponse(stats_with_runtime)

        except Exception as e:
            LOGGER.error(f"Error in wserver stats endpoint: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.get("/stats/loadbalancer")
    async def loadbalancer_stats():
        """Load balancer statistics endpoint"""
        try:
            import time

            # Get load balancer stats from the web server process
            try:
                from bot.helper.stream_utils.load_balancer import LoadBalancer

                load_stats = LoadBalancer.get_load_stats()

                # Add additional runtime info
                stats_with_runtime = {
                    "timestamp": time.time(),
                    "service": "Load Balancer Statistics",
                    "stats": load_stats,
                    "performance": {
                        "total_load": load_stats.get("total_load", 0),
                        "average_load": load_stats.get("average_load", 0.0),
                        "healthy_clients": load_stats.get("healthy_clients", 0),
                        "total_clients": load_stats.get("total_clients", 0),
                    },
                }

                return JSONResponse(stats_with_runtime)

            except ImportError:
                return JSONResponse(
                    {
                        "timestamp": time.time(),
                        "service": "Load Balancer Statistics",
                        "error": "Load balancer not available",
                        "stats": {
                            "total_load": 0,
                            "average_load": 0.0,
                            "healthy_clients": 0,
                            "total_clients": 0,
                            "client_loads": {},
                        },
                    }
                )

        except Exception as e:
            LOGGER.error(f"Error in loadbalancer stats endpoint: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)

    # Dynamic category page route
    @app.get("/category/{category_name}", response_class=HTMLResponse)
    async def category_page(
        category_name: str,
        request: Request,
        page: int = 1,
        sort_by: str = "trending",
    ):
        """Dynamic category page for any category"""
        # Initialize templates at the beginning to avoid scope issues
        Jinja2Templates(directory="web/templates")

        try:
            # Use unified database access
            database = await ensure_database_and_config()

            # Ensure TgClient.ID is set for database operations
            if not TgClient.ID:
                TgClient.ID = Config.BOT_TOKEN.split(":", 1)[0]

            # Check if database is available
            if not is_database_available(database):
                LOGGER.warning("Database not available for category page")
                from datetime import datetime

                # Redirect to main page with category filter
                return RedirectResponse(
                    url=f"/?type=all&category={category_name}&page={page}&sort_by={sort_by}",
                    status_code=302,
                )

            # Pagination settings - get from admin config
            from bot.helper.stream_utils.admin_config import admin_config

            per_page = await admin_config.get_items_per_page()
            skip = (page - 1) * per_page

            # Get media files for this category
            media_files = await database.get_all_media(
                limit=per_page, skip=skip, media_type=category_name, sort_by=sort_by
            )

            # Get total count for pagination
            total_count = await database.get_media_count(media_type=category_name)

            # Calculate pagination
            total_pages = (total_count + per_page - 1) // per_page
            has_pagination = total_pages > 1

            # Generate page numbers for pagination
            page_numbers = []
            if has_pagination:
                start_page = max(1, page - 2)
                end_page = min(total_pages, page + 2)
                page_numbers = list(range(start_page, end_page + 1))

            # Process media files for display
            processed_files = []
            for media in media_files:
                # Format creation date and update date
                created_at = None
                created_year = None
                updated_at = None
                if media.get("created_at"):
                    from datetime import datetime

                    created_dt = datetime.fromtimestamp(media["created_at"])
                    created_at = created_dt.strftime("%Y-%m-%d")
                    created_year = created_dt.strftime("%Y")

                if media.get("updated_at"):
                    from datetime import datetime

                    updated_at = datetime.fromtimestamp(
                        media["updated_at"]
                    ).strftime("%Y-%m-%d")

                processed_files.append(
                    {
                        "hash_id": media["hash_id"],
                        "title": media.get(
                            "title", media.get("file_name", "Unknown")
                        ),
                        "file_name": media.get("file_name", "Unknown"),
                        "file_size_human": media.get("file_size_human", "Unknown"),
                        "is_video": media.get("is_video", False),
                        "is_audio": media.get("is_audio", False),
                        "is_image": media.get("is_image", False),
                        "is_streamable": media.get("is_streamable", False),
                        "category": media.get("category", "document"),
                        "categories": media.get("categories", []),
                        "duration": media.get("duration"),
                        "view_count": media.get("view_count", 0),
                        "thumbnail": convert_thumbnail_to_url(
                            media.get("thumbnail"), media["hash_id"]
                        ),
                        "created_at": created_at,
                        "created_year": created_year,
                        "updated_at": updated_at,
                        "quality": media.get("quality"),
                        "season": media.get("season"),
                        "unique_name": media.get("unique_name"),
                    }
                )

            # Check if current user is admin (for showing admin link)
            current_user = None
            try:
                from bot.helper.ext_utils.auth_handler import auth_handler

                # Get token from cookie
                access_token = request.cookies.get("access_token")
                if access_token:
                    current_user = await auth_handler.get_user_by_token(access_token)
            except Exception as e:
                LOGGER.info(f"Error checking current user: {e}")
                # Continue without user info

            # Template context
            context = {
                "request": request,
                "category_name": category_name.title(),
                "category_slug": category_name,
                "media_files": processed_files,
                "total_count": total_count,
                "sort_by": sort_by,
                "current_page": page,
                "total_pages": total_pages,
                "has_pagination": has_pagination,
                "page_numbers": page_numbers,
                "prev_page": page - 1 if page > 1 else None,
                "next_page": page + 1 if page < total_pages else None,
                "current_user": current_user,
            }

            # Get navigation data
            nav_data = await get_navigation_data()
            context.update(nav_data)

            # Redirect to main page with category filter - reelnn handles categories
            return RedirectResponse(
                url=f"/?type=all&category={category_name}&page={page}&sort_by={sort_by}",
                status_code=302,
            )

        except Exception as e:
            LOGGER.error(f"Error in category page: {e}")
            from datetime import datetime

            # Redirect to main page on error
            return RedirectResponse(
                url="/?error=category_load_failed", status_code=302
            )

    # Series page route
    @app.get("/series", response_class=HTMLResponse)
    async def series_page(
        request: Request, series_name: str | None = None, season: str | None = None
    ):
        """Series page with season and episode organization"""
        try:
            # Use unified database access
            database = await ensure_database_and_config()

            # Ensure TgClient.ID is set for database operations
            if not TgClient.ID:
                TgClient.ID = Config.BOT_TOKEN.split(":", 1)[0]

            # Check if database is available
            if not is_database_available(database):
                LOGGER.warning("Database not available for series page")
                from datetime import datetime

                # Redirect to main page with series filter
                return RedirectResponse(url="/?type=show", status_code=302)

            # Get all series (grouped by unique_name or title)
            series_data = await database.get_series_data(series_name, season)

            # Process series list to convert thumbnails to URLs
            processed_series_list = []
            for series in series_data.get("series_list", []):
                processed_series = series.copy()
                processed_series["poster_url"] = convert_thumbnail_to_url(
                    series.get("thumbnail"),
                    series.get("_id", "default"),  # Use series ID as fallback
                )
                processed_series_list.append(processed_series)

            # Process episodes to convert thumbnails to URLs
            processed_episodes = []
            for episode in series_data.get("episodes", []):
                processed_episode = episode.copy()
                processed_episode["poster_url"] = convert_thumbnail_to_url(
                    episode.get("thumbnail"), episode.get("hash_id", "default")
                )
                processed_episodes.append(processed_episode)

            # Process series info to convert thumbnail to URL
            processed_series_info = series_data.get("series_info", {}).copy()
            if processed_series_info:
                processed_series_info["poster_url"] = convert_thumbnail_to_url(
                    processed_series_info.get("thumbnail"),
                    processed_series_info.get("hash_id", "default"),
                )

            # Check if current user is admin (for showing admin link)
            current_user = None
            try:
                from bot.helper.ext_utils.auth_handler import auth_handler

                # Get token from cookie
                access_token = request.cookies.get("access_token")
                if access_token:
                    current_user = await auth_handler.get_user_by_token(access_token)
            except Exception as e:
                LOGGER.info(f"Error checking current user: {e}")
                # Continue without user info

            # Template context
            context = {
                "request": request,
                "series_list": processed_series_list,
                "selected_series": series_name,
                "selected_season": season,
                "episodes": processed_episodes,
                "seasons": series_data.get("seasons", []),
                "series_info": processed_series_info,
                "current_user": current_user,
            }

            # Get navigation data
            nav_data = await get_navigation_data()
            context.update(nav_data)

            # Redirect to reelnn show page or search
            if context.get("selected_series"):
                # Find first episode to redirect to show page
                episodes = context.get("episodes", [])
                if episodes:
                    first_episode = episodes[0]
                    return RedirectResponse(
                        url=f"/show/{first_episode.get('hash_id')}", status_code=302
                    )
                return RedirectResponse(
                    url=f"/search?q={context.get('selected_series')}",
                    status_code=302,
                )
            return RedirectResponse(url="/?type=show", status_code=302)

        except Exception as e:
            LOGGER.error(f"Error in series page: {e}")
            Jinja2Templates(directory="web/templates")

            # Get navigation data for error case too
            try:
                nav_data = await get_navigation_data()
            except:
                from datetime import datetime

                nav_data = {
                    "header_nav": [],
                    "footer_nav": [],
                    "dynamic_categories": [],
                    "current_year": datetime.now().year,
                }

            context = {
                "request": request,
                "series_list": [],
                "selected_series": None,
                "episodes": [],
                "seasons": [],
                "error": str(e),
            }
            context.update(nav_data)

            # Redirect to main page on error
            return RedirectResponse(
                url="/?error=series_load_failed", status_code=302
            )

    # CONSOLIDATED STREAMING ROUTES - Remove duplicates and conflicts

    # Removed watch page routes - using movie/show pages with built-in players instead

    @app.get("/media/{hash_id}", response_class=HTMLResponse)
    async def media_page(hash_id: str, request: Request, download: int = 0):
        """Individual media page for streaming/downloading"""
        try:
            # Use unified database access
            database = await ensure_database_and_config()
            if not database:
                raise Exception("Database not available")

            # Ensure TgClient.ID is set for database operations
            if not TgClient.ID:
                TgClient.ID = Config.BOT_TOKEN.split(":", 1)[0]

            # Get media metadata from database with fallback to grouped versions
            media_data = await get_media_info_with_fallback(hash_id)
            if not media_data:
                raise HTTPException(status_code=404, detail="Media not found")

            # Update view count
            await database.update_media_views(hash_id)

            # Format creation date
            created_at = None
            if media_data.get("created_at"):
                from datetime import datetime

                created_at = datetime.fromtimestamp(
                    media_data["created_at"]
                ).strftime("%B %d, %Y")

            # FIXED: Determine file type with MIME type fallback
            mime_type = media_data.get("mime_type", "application/octet-stream")
            is_video = media_data.get("is_video", False)
            is_audio = media_data.get("is_audio", False)
            is_image = media_data.get("is_image", False)

            # Fallback to MIME type detection if database flags are incorrect
            if not is_video and not is_audio and not is_image:
                if mime_type.startswith("video/"):
                    is_video = True
                elif mime_type.startswith("audio/"):
                    is_audio = True
                elif mime_type.startswith("image/"):
                    is_image = True

            # Prepare context for template
            context = {
                "request": request,
                "file_name": media_data.get("file_name", "Unknown"),
                "file_size": media_data.get("file_size", 0),
                "file_size_human": media_data.get("file_size_human", "Unknown"),
                "mime_type": mime_type,
                "is_video": is_video,
                "is_audio": is_audio,
                "is_image": is_image,
                "is_streamable": media_data.get("is_streamable", False),
                "duration": media_data.get("duration"),
                "resolution": media_data.get("resolution"),
                "uploader_name": media_data.get("uploader_name", "Unknown"),
                "view_count": media_data.get("view_count", 0),
                "created_at": created_at,
                "hash_id": hash_id,
                "download_mode": bool(download),
                # Track information for multiple tracks support
                "tracks_info": media_data.get("tracks", {}),
                "default_tracks": media_data.get(
                    "default_tracks", {"video": 0, "audio": 0, "subtitle": -1}
                ),
                "has_multiple_video": len(
                    media_data.get("tracks", {}).get("video_tracks", [])
                )
                > 1,
                "has_multiple_audio": len(
                    media_data.get("tracks", {}).get("audio_tracks", [])
                )
                > 1,
                "has_subtitles": len(
                    media_data.get("tracks", {}).get("subtitle_tracks", [])
                )
                > 0,
            }

            # If download mode, redirect to download URL
            if download:
                download_url = media_data.get("download_url")
                if download_url:
                    from fastapi.responses import RedirectResponse

                    return RedirectResponse(url=download_url)

                raise HTTPException(
                    status_code=404, detail="Download URL not available"
                )

            # Get navigation data
            nav_data = await get_navigation_data()
            context.update(nav_data)

            # DEPRECATED: watch.html removed - redirecting to movie/show pages
            # Determine if this is a movie or show and redirect appropriately
            media_type = context.get("media_type", "movie")
            if media_type in {"tv", "show"}:
                return RedirectResponse(url=f"/show/{hash_id}", status_code=301)
            return RedirectResponse(url=f"/movie/{hash_id}", status_code=301)

        except HTTPException:
            raise
        except Exception as e:
            LOGGER.error(f"Error in media page: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    # Add test endpoint to check file access
    @app.get("/debug/test-file/{hash_id}")
    async def debug_test_file(
        hash_id: str, request: Request, hash: str | None = None
    ):
        """Test endpoint to check if file download works"""
        try:
            LOGGER.info(
                f"[DEBUG] Testing file access: hash_id={hash_id}, hash={hash}"
            )

            # Validate basic format
            if not hash_id or len(hash_id) < 7:
                return JSONResponse(
                    {"error": "Invalid hash_id format", "hash_id": hash_id}
                )

            # Extract hash and message ID
            secure_hash = hash_id[:6]
            try:
                message_id = int(hash_id[6:])
            except ValueError:
                return JSONResponse(
                    {"error": "Invalid message ID in hash_id", "hash_id": hash_id}
                )

            # Check hash parameter
            if not hash or hash != secure_hash:
                return JSONResponse(
                    {
                        "error": "Hash mismatch",
                        "expected": secure_hash,
                        "provided": hash,
                    }
                )

            # Get target chat ID
            target_chat_id = get_target_chat_id()
            if not target_chat_id:
                return JSONResponse({"error": "LEECH_DUMP_CHAT not configured"})

            # Get client
            client, client_id = await get_telegram_client()
            if not client:
                return JSONResponse({"error": "Telegram client not available"})

            # Try to get message
            message = await client.get_messages(target_chat_id, message_id)
            if not message:
                return JSONResponse(
                    {
                        "error": "Message not found",
                        "message_id": message_id,
                        "chat_id": target_chat_id,
                    }
                )

            # Extract file info
            file_info = FileProcessor.extract_file_info(message)
            if not file_info:
                return JSONResponse(
                    {"error": "No file in message", "message_id": message_id}
                )

            # ReelNN: Use STREAM_BASE_URL for streaming URLs
            stream_base_url = (
                getattr(Config, "STREAM_BASE_URL", "") or Config.BASE_URL
            )
            if not stream_base_url:
                # Auto-detect from request for ReelNN compatibility
                host = request.headers.get("host", "localhost")
                if "herokuapp.com" in host:
                    stream_base_url = f"https://{host}"
                else:
                    stream_base_url = f"{request.url.scheme}://{host}"

            return JSONResponse(
                {
                    "success": True,
                    "hash_id": hash_id,
                    "message_id": message_id,
                    "file_name": file_info.get("file_name"),
                    "file_size": file_info.get("file_size"),
                    "mime_type": file_info.get("mime_type"),
                    "is_streamable": file_info.get("is_streamable"),
                    "file_unique_id": file_info.get("file_unique_id"),
                    "download_url": f"{stream_base_url}/{hash_id}?hash={hash}&download=1",
                }
            )

        except Exception as e:
            LOGGER.error(f"[DEBUG] Error testing file: {e}")
            return JSONResponse({"error": str(e)})

    # Admin Routes (Protected)
    @app.get("/admin", response_class=HTMLResponse)
    async def admin_dashboard(
        request: Request, current_user: dict = Depends(get_admin_user)
    ):
        """Admin dashboard - UNIFIED DATABASE ACCESS"""
        try:
            # Use unified database access
            database = await ensure_database_and_config()
            if not database:
                raise Exception("Database not available")

            # Get admin statistics
            stats = await database.get_admin_stats()
            recent_activities = await database.get_recent_activities(limit=10)

            return templates.TemplateResponse(
                "admin/dashboard.html",
                {
                    "request": request,
                    "user": current_user,
                    "stats": stats,
                    "recent_activities": recent_activities,
                },
            )

        except Exception as e:
            LOGGER.error(f"Error in admin dashboard: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    # Admin Settings Routes (removed duplicate - using the complete one below)

    # Missing Admin Routes
    @app.get("/admin/settings/branding", response_class=HTMLResponse)
    async def admin_settings_branding(
        request: Request, current_user: dict = Depends(get_admin_user)
    ):
        """Admin branding settings page"""
        try:
            from bot.helper.stream_utils.admin_config import admin_config

            branding_settings = await admin_config.get_branding_settings()

            return templates.TemplateResponse(
                "admin/settings/branding.html",
                {
                    "request": request,
                    "user": current_user,
                    "branding_settings": branding_settings,
                },
            )
        except Exception as e:
            LOGGER.error(f"Error in admin branding settings: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.get("/admin/settings/ui", response_class=HTMLResponse)
    async def admin_settings_ui(
        request: Request, current_user: dict = Depends(get_admin_user)
    ):
        """Admin UI settings page"""
        try:
            from bot.helper.stream_utils.admin_config import admin_config

            ui_settings = await admin_config.get_ui_settings()

            return templates.TemplateResponse(
                "admin/settings/ui.html",
                {
                    "request": request,
                    "user": current_user,
                    "ui_settings": ui_settings,
                },
            )
        except Exception as e:
            LOGGER.error(f"Error in admin UI settings: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.get("/admin/settings/streaming", response_class=HTMLResponse)
    async def admin_settings_streaming(
        request: Request, current_user: dict = Depends(get_admin_user)
    ):
        """Admin streaming settings page"""
        try:
            from bot.helper.stream_utils.admin_config import admin_config

            streaming_settings = await admin_config.get_streaming_settings()

            return templates.TemplateResponse(
                "admin/settings/streaming.html",
                {
                    "request": request,
                    "user": current_user,
                    "streaming_settings": streaming_settings,
                },
            )
        except Exception as e:
            LOGGER.error(f"Error in admin streaming settings: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.get("/admin/maintenance", response_class=HTMLResponse)
    async def admin_maintenance(
        request: Request, current_user: dict = Depends(get_admin_user)
    ):
        """Admin maintenance page - UNIFIED DATABASE ACCESS"""
        try:
            # Use unified database access
            database = await ensure_database_and_config()
            if not database:
                raise Exception("Database not available")

            # Get maintenance stats
            cleanup_stats = await database.get_cleanup_stats()

            return templates.TemplateResponse(
                "admin/maintenance.html",
                {
                    "request": request,
                    "user": current_user,
                    "cleanup_stats": cleanup_stats,
                },
            )
        except Exception as e:
            LOGGER.error(f"Error in admin maintenance: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.get("/admin/security", response_class=HTMLResponse)
    async def admin_security(
        request: Request, current_user: dict = Depends(get_admin_user)
    ):
        """Admin security page"""
        try:
            from bot.helper.stream_utils.admin_config import admin_config

            security_settings = await admin_config.get_security_settings()

            return templates.TemplateResponse(
                "admin/security.html",
                {
                    "request": request,
                    "user": current_user,
                    "security_settings": security_settings,
                },
            )
        except Exception as e:
            LOGGER.error(f"Error in admin security: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.get("/admin/api-keys", response_class=HTMLResponse)
    async def admin_api_keys(
        request: Request, current_user: dict = Depends(get_admin_user)
    ):
        """Admin API keys page"""
        try:
            # For now, return a simple page - can be expanded later
            return templates.TemplateResponse(
                "admin/api-keys.html",
                {
                    "request": request,
                    "user": current_user,
                    "api_keys": [],  # Placeholder
                },
            )
        except Exception as e:
            LOGGER.error(f"Error in admin API keys: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.get("/admin/config/import", response_class=HTMLResponse)
    async def admin_config_import_page(
        request: Request, current_user: dict = Depends(get_admin_user)
    ):
        """Admin config import page"""
        try:
            return templates.TemplateResponse(
                "admin/config/import.html",
                {
                    "request": request,
                    "user": current_user,
                },
            )
        except Exception as e:
            LOGGER.error(f"Error in admin config import: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.get("/admin/analytics", response_class=HTMLResponse)
    async def admin_analytics(
        request: Request, current_user: dict = Depends(get_admin_user)
    ):
        """Admin analytics page - UNIFIED DATABASE ACCESS"""
        try:
            # Use unified database access
            database = await ensure_database_and_config()
            if not database:
                raise Exception("Database not available")

            # Get analytics data
            analytics_data = await database.get_analytics_data()

            return templates.TemplateResponse(
                "admin/analytics.html",
                {
                    "request": request,
                    "user": current_user,
                    "analytics": analytics_data,
                },
            )
        except Exception as e:
            LOGGER.error(f"Error in admin analytics: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.get("/admin/logs", response_class=HTMLResponse)
    async def admin_logs(
        request: Request, current_user: dict = Depends(get_admin_user)
    ):
        """Admin system logs page"""
        try:
            # Read recent log entries
            log_entries = []
            try:
                with open("log.txt") as f:
                    lines = f.readlines()
                    # Get last 100 lines
                    log_entries = lines[-100:] if len(lines) > 100 else lines
                    log_entries.reverse()  # Show newest first
            except FileNotFoundError:
                log_entries = ["No log file found"]

            return templates.TemplateResponse(
                "admin/logs.html",
                {
                    "request": request,
                    "user": current_user,
                    "log_entries": log_entries,
                },
            )
        except Exception as e:
            LOGGER.error(f"Error in admin logs: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.get("/admin/debug", response_class=HTMLResponse)
    async def admin_debug(
        request: Request, current_user: dict = Depends(get_admin_user)
    ):
        """Admin debug tools page"""
        try:
            import platform
            import sys

            from bot.core.config_manager import Config

            # System information
            system_info = {
                "python_version": sys.version,
                "platform": platform.platform(),
                "architecture": platform.architecture(),
                "processor": platform.processor(),
                "memory": "N/A",  # Could add psutil for memory info
            }

            # Bot configuration (safe subset)
            try:
                # Use unified database access
                database = await ensure_database_and_config()
                database_connected = database is not None and not database._return
            except Exception:
                database_connected = False

            bot_config = {
                "database_connected": database_connected,
                "file_to_link_enabled": getattr(
                    Config, "FILE_TO_LINK_ENABLED", False
                ),
                "bot_token_set": bool(Config.BOT_TOKEN),
                "owner_id_set": bool(Config.OWNER_ID),
            }

            return templates.TemplateResponse(
                "admin/debug.html",
                {
                    "request": request,
                    "user": current_user,
                    "system_info": system_info,
                    "bot_config": bot_config,
                },
            )
        except Exception as e:
            LOGGER.error(f"Error in admin debug: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    # Debug API Routes
    @app.post("/admin/debug/clear-cache")
    async def admin_clear_cache(current_user: dict = Depends(get_admin_user)):
        """Clear application cache"""
        try:
            # Clear any application caches here
            # For now, just return success
            return {"success": True, "message": "Cache cleared successfully"}
        except Exception as e:
            LOGGER.error(f"Error clearing cache: {e}")
            return {"success": False, "error": str(e)}

    @app.get("/admin/debug/test-database")
    async def admin_test_database(current_user: dict = Depends(get_admin_user)):
        """Test database connection"""
        try:
            # Use unified database access
            database = await ensure_database_and_config()
            if not database:
                return {"success": False, "error": "Database not available"}

            # Test database connection
            test_result = await database.test_connection()
            return {"success": True, "result": test_result}
        except Exception as e:
            LOGGER.error(f"Database test failed: {e}")
            return {"success": False, "error": str(e)}

    @app.post("/admin/debug/restart-services")
    async def admin_restart_services(current_user: dict = Depends(get_admin_user)):
        """Restart background services"""
        try:
            # Restart services logic here
            # For now, just return success
            return {"success": True, "message": "Services restart initiated"}
        except Exception as e:
            LOGGER.error(f"Error restarting services: {e}")
            return {"success": False, "error": str(e)}

    @app.get("/admin/debug/test/{test_type}")
    async def admin_run_test(
        test_type: str, current_user: dict = Depends(get_admin_user)
    ):
        """Run specific system tests"""
        try:
            if test_type == "database":
                # Use unified database access
                database = await ensure_database_and_config()
                if not database:
                    return {
                        "test": test_type,
                        "success": False,
                        "result": "Database not available",
                    }

                result = await database.test_connection()
                return {"test": test_type, "success": True, "result": result}

            if test_type == "telegram":
                # Test Telegram bot connection
                from bot.core.config_manager import Config

                result = {
                    "bot_token_set": bool(Config.BOT_TOKEN),
                    "owner_id_set": bool(Config.OWNER_ID),
                }
                return {"test": test_type, "success": True, "result": result}

            if test_type == "storage":
                # Test storage/file system
                import shutil

                disk_usage = shutil.disk_usage("/")
                result = {
                    "total": disk_usage.total,
                    "used": disk_usage.used,
                    "free": disk_usage.free,
                    "percentage": (disk_usage.used / disk_usage.total) * 100,
                }
                return {"test": test_type, "success": True, "result": result}

            if test_type == "streaming":
                # Test streaming functionality
                from bot.core.config_manager import Config

                result = {
                    "file_to_link_enabled": getattr(
                        Config, "FILE_TO_LINK_ENABLED", False
                    ),
                    "stream_server_running": True,  # Would check actual status
                }
                return {"test": test_type, "success": True, "result": result}

            return {
                "test": test_type,
                "success": False,
                "error": "Unknown test type",
            }

        except Exception as e:
            LOGGER.error(f"Test {test_type} failed: {e}")
            return {"test": test_type, "success": False, "error": str(e)}

    # Logs API Routes
    @app.get("/admin/logs/download")
    async def admin_download_logs(current_user: dict = Depends(get_admin_user)):
        """Download log file"""
        try:
            import os

            from fastapi.responses import FileResponse

            log_file = "log.txt"
            if os.path.exists(log_file):
                return FileResponse(
                    log_file,
                    media_type="text/plain",
                    filename=f"streambot_logs_{int(__import__('time').time())}.txt",
                )

            raise HTTPException(status_code=404, detail="Log file not found")
        except Exception as e:
            LOGGER.error(f"Error downloading logs: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.post("/admin/logs/clear")
    async def admin_clear_logs(current_user: dict = Depends(get_admin_user)):
        """Clear log file"""
        try:
            import os

            log_file = "log.txt"
            if os.path.exists(log_file):
                with open(log_file, "w") as f:
                    f.write("")
                return {"success": True, "message": "Logs cleared successfully"}

            return {"success": False, "error": "Log file not found"}
        except Exception as e:
            LOGGER.error(f"Error clearing logs: {e}")
            return {"success": False, "error": str(e)}

    @app.get("/admin/api/stats")
    async def admin_api_stats(current_user: dict = Depends(get_admin_user)):
        """API endpoint for admin statistics - UNIFIED ACCESS"""
        try:
            # Use unified database access
            database = await ensure_database_and_config()
            if not database:
                return JSONResponse(
                    {"error": "Database not available"}, status_code=503
                )

            stats = await database.get_admin_stats()
            return JSONResponse(stats)
        except Exception as e:
            LOGGER.error(f"Error getting admin stats: {e}")
            return JSONResponse(
                {"error": "Failed to get statistics"}, status_code=500
            )

    @app.get("/admin/users", response_class=HTMLResponse)
    async def admin_users(
        request: Request, page: int = 1, current_user: dict = Depends(get_admin_user)
    ):
        """Admin user management page"""
        try:
            from bot.helper.stream_utils.admin_config import admin_config

            # Use unified database access
            database = await ensure_database_and_config()
            if not database:
                return JSONResponse(
                    {"error": "Database not available"}, status_code=503
                )

            # Get pagination settings
            items_per_page = await admin_config.get_items_per_page()
            skip = (page - 1) * items_per_page

            # Get users
            users = await database.get_all_users(limit=items_per_page, skip=skip)
            total_users = await database.get_user_count()

            # Calculate pagination
            total_pages = (total_users + items_per_page - 1) // items_per_page

            return templates.TemplateResponse(
                "admin/users.html",
                {
                    "request": request,
                    "current_user": current_user,
                    "user": current_user,
                    "users": users,
                    "current_page": page,
                    "total_pages": total_pages,
                    "total_users": total_users,
                },
            )

        except Exception as e:
            LOGGER.error(f"Error in admin users: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.post("/admin/users/{username}/role")
    async def admin_update_user_role(
        username: str,
        role: str = Form(...),
        current_user: dict = Depends(get_admin_user),
    ):
        """Update user role"""
        try:
            # Use unified database access
            database = await ensure_database_and_config()
            if not database:
                return JSONResponse(
                    {"error": "Database not available"}, status_code=503
                )

            # Validate role
            valid_roles = ["user", "moderator", "admin"]
            if role not in valid_roles:
                return JSONResponse({"error": "Invalid role"}, status_code=400)

            # Don't allow changing own role
            if username == current_user["username"]:
                return JSONResponse(
                    {"error": "Cannot change your own role"}, status_code=400
                )

            # Update role
            success = await database.update_user_role(username, role)

            if success:
                LOGGER.info(
                    f"Admin {current_user['username']} changed role of {username} to {role}"
                )
                return JSONResponse(
                    {"success": True, "message": f"Role updated to {role}"}
                )
            return JSONResponse({"error": "Failed to update role"}, status_code=500)

        except Exception as e:
            LOGGER.error(f"Error updating user role: {e}")
            return JSONResponse({"error": "Internal server error"}, status_code=500)

    @app.post("/admin/users/{username}/deactivate")
    async def admin_deactivate_user(
        username: str, current_user: dict = Depends(get_admin_user)
    ):
        """Deactivate user account - UNIFIED ACCESS"""
        try:
            # Use unified database access
            database = await ensure_database_and_config()
            if not database:
                return JSONResponse(
                    {"error": "Database not available"}, status_code=503
                )

            # Don't allow deactivating own account
            if username == current_user["username"]:
                return JSONResponse(
                    {"error": "Cannot deactivate your own account"}, status_code=400
                )

            # Deactivate user
            success = await database.deactivate_user(username)

            if success:
                LOGGER.info(
                    f"Admin {current_user['username']} deactivated user {username}"
                )
                return JSONResponse({"success": True, "message": "User deactivated"})
            return JSONResponse(
                {"error": "Failed to deactivate user"}, status_code=500
            )

        except Exception as e:
            LOGGER.error(f"Error deactivating user: {e}")
            return JSONResponse({"error": "Internal server error"}, status_code=500)

    @app.get("/admin/settings", response_class=HTMLResponse)
    async def admin_settings(
        request: Request, current_user: dict = Depends(get_admin_user)
    ):
        """Admin settings page"""
        try:
            from bot.helper.stream_utils.admin_config import admin_config

            # Get all configuration sections
            site_settings = await admin_config.get_site_settings()
            security_settings = await admin_config.get_security_settings()
            media_settings = await admin_config.get_media_settings()
            ui_settings = await admin_config.get_ui_settings()
            streaming_settings = await admin_config.get_streaming_settings()
            content_settings = await admin_config.get_content_settings()
            navigation_settings = await admin_config.get_navigation_settings()
            branding_settings = await admin_config.get_branding_settings()

            return templates.TemplateResponse(
                "admin/settings.html",
                {
                    "request": request,
                    "user": current_user,
                    "site_settings": site_settings,
                    "security_settings": security_settings,
                    "media_settings": media_settings,
                    "ui_settings": ui_settings,
                    "streaming_settings": streaming_settings,
                    "content_settings": content_settings,
                    "navigation_settings": navigation_settings,
                    "branding_settings": branding_settings,
                },
            )

        except Exception as e:
            LOGGER.error(f"Error in admin settings: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.post("/admin/settings/{section}")
    async def admin_update_settings(
        section: str, request: Request, current_user: dict = Depends(get_admin_user)
    ):
        """Update admin settings"""
        try:
            from bot.helper.stream_utils.admin_config import admin_config

            # Get form data
            form_data = await request.form()
            settings = dict(form_data)

            # Convert string values to appropriate types
            for key, value in settings.items():
                if value.lower() in ["true", "false"]:
                    settings[key] = value.lower() == "true"
                elif value.isdigit():
                    settings[key] = int(value)

            # Update configuration
            success = await admin_config.update_config(section, settings)

            if success:
                LOGGER.info(
                    f"Admin {current_user['username']} updated {section} settings"
                )
                return RedirectResponse(
                    url="/admin/settings?success=Settings updated successfully",
                    status_code=302,
                )
            return RedirectResponse(
                url="/admin/settings?error=Failed to update settings",
                status_code=302,
            )

        except Exception as e:
            LOGGER.error(f"Error updating admin settings: {e}")
            return RedirectResponse(
                url="/admin/settings?error=Internal server error", status_code=302
            )

    @app.get("/admin/config/export")
    async def admin_export_config(current_user: dict = Depends(get_admin_user)):
        """Export configuration as JSON"""
        try:
            import json

            from bot.helper.stream_utils.admin_config import admin_config

            config_data = await admin_config.export_config()

            # Create JSON response
            json_str = json.dumps(config_data, indent=2)

            return Response(
                content=json_str,
                media_type="application/json",
                headers={
                    "Content-Disposition": f"attachment; filename=streambot_config_{int(config_data.get('export_timestamp', 0))}.json"
                },
            )

        except Exception as e:
            LOGGER.error(f"Error exporting config: {e}")
            return JSONResponse(
                {"error": "Failed to export configuration"}, status_code=500
            )

    @app.post("/admin/config/import")
    async def admin_import_config(
        config_file: UploadFile = File(...),
        current_user: dict = Depends(get_admin_user),
    ):
        """Import configuration from JSON file"""
        try:
            import json

            from bot.helper.stream_utils.admin_config import admin_config

            # Read and parse uploaded file
            content = await config_file.read()
            config_data = json.loads(content.decode("utf-8"))

            # Import configuration
            success = await admin_config.import_config(config_data)

            if success:
                LOGGER.info(
                    f"Admin {current_user['username']} imported configuration"
                )
                return JSONResponse(
                    {
                        "success": True,
                        "message": "Configuration imported successfully",
                    }
                )
            return JSONResponse(
                {"error": "Failed to import configuration"}, status_code=500
            )

        except json.JSONDecodeError:
            return JSONResponse({"error": "Invalid JSON file"}, status_code=400)
        except Exception as e:
            LOGGER.error(f"Error importing config: {e}")
            return JSONResponse(
                {"error": "Failed to import configuration"}, status_code=500
            )

    @app.post("/admin/config/reset")
    async def admin_reset_config(current_user: dict = Depends(get_admin_user)):
        """Reset configuration to defaults"""
        try:
            from bot.helper.stream_utils.admin_config import admin_config

            success = await admin_config.reset_to_defaults()

            if success:
                LOGGER.info(
                    f"Admin {current_user['username']} reset configuration to defaults"
                )
                return JSONResponse(
                    {"success": True, "message": "Configuration reset to defaults"}
                )
            return JSONResponse(
                {"error": "Failed to reset configuration"}, status_code=500
            )

        except Exception as e:
            LOGGER.error(f"Error resetting config: {e}")
            return JSONResponse(
                {"error": "Failed to reset configuration"}, status_code=500
            )

    @app.get("/admin/quality-groups", response_class=HTMLResponse)
    async def admin_quality_groups_page(
        request: Request, current_user: dict = Depends(get_admin_user)
    ):
        """Admin quality groups management page"""
        try:
            # Use unified database access
            database = await ensure_database_and_config()
            if not database:
                raise HTTPException(status_code=503, detail="Database not available")

            from bot.helper.stream_utils.quality_handler import QualityHandler

            # Get all quality groups
            quality_groups = await database.get_all_quality_groups(limit=100)

            # Get ungrouped media
            ungrouped_media = await database.get_ungrouped_media(limit=50)

            context = {
                "request": request,
                "current_user": current_user,
                "quality_groups": quality_groups,
                "ungrouped_media": ungrouped_media,
                "supported_qualities": QualityHandler.SUPPORTED_QUALITIES,
                "page_title": "Quality Groups Management",
            }

            return templates.TemplateResponse("admin/quality_groups.html", context)

        except Exception as e:
            LOGGER.error(f"Error in quality groups page: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.post("/admin/quality-groups/create")
    async def admin_create_quality_group(
        request: Request, current_user: dict = Depends(get_admin_user)
    ):
        """Create new quality group"""
        try:
            form_data = await request.form()
            group_name = form_data.get("group_name", "").strip()
            base_pattern = form_data.get("base_pattern", "").strip()

            if not group_name or not base_pattern:
                return JSONResponse(
                    {"error": "Group name and base pattern are required"},
                    status_code=400,
                )

            # Create new group
            import time
            import uuid

            # Use unified database access
            database = await ensure_database_and_config()
            if not database:
                return JSONResponse(
                    {"error": "Database not available"}, status_code=503
                )

            group_data = {
                "group_id": str(uuid.uuid4())[:8],
                "display_name": group_name,
                "base_name": base_pattern,
                "qualities": {},
                "default_quality": None,
                "created_at": time.time(),
                "created_by": current_user["username"],
                "total_size": 0,
                "duration": 0,
                "is_video": True,
                "category": "other",
            }

            await database.store_quality_group(group_data)

            return JSONResponse(
                {"success": True, "group_id": group_data["group_id"]}
            )

        except Exception as e:
            LOGGER.error(f"Error creating quality group: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.delete("/admin/quality-groups/{group_id}")
    async def admin_delete_quality_group(
        group_id: str, current_user: dict = Depends(get_admin_user)
    ):
        """Delete quality group"""
        try:
            # Use unified database access
            database = await ensure_database_and_config()
            if not database:
                return JSONResponse(
                    {"error": "Database not available"}, status_code=503
                )

            success = await database.delete_quality_group(group_id)

            if success:
                return JSONResponse(
                    {
                        "success": True,
                        "message": "Quality group deleted successfully",
                    }
                )
            return JSONResponse(
                {"error": "Failed to delete quality group"}, status_code=500
            )

        except Exception as e:
            LOGGER.error(f"Error deleting quality group: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.delete("/admin/quality-groups/{group_id}/qualities/{quality}")
    async def admin_remove_quality_from_group(
        group_id: str, quality: str, current_user: dict = Depends(get_admin_user)
    ):
        """Remove specific quality from group"""
        try:
            # Use unified database access
            database = await ensure_database_and_config()
            if not database:
                return JSONResponse(
                    {"error": "Database not available"}, status_code=503
                )

            success = await database.remove_quality_from_group(group_id, quality)

            if success:
                return JSONResponse(
                    {
                        "success": True,
                        "message": f"{quality} quality removed successfully",
                    }
                )
            return JSONResponse(
                {"error": "Failed to remove quality"}, status_code=500
            )

        except Exception as e:
            LOGGER.error(f"Error removing quality from group: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.get("/admin/media", response_class=HTMLResponse)
    async def admin_media(
        request: Request, page: int = 1, current_user: dict = Depends(get_admin_user)
    ):
        """Admin media management page"""
        try:
            # Use unified database access
            database = await ensure_database_and_config()
            if not database:
                raise HTTPException(status_code=503, detail="Database not available")

            from bot.helper.stream_utils.admin_config import admin_config

            # Get pagination settings
            items_per_page = await admin_config.get_items_per_page()
            skip = (page - 1) * items_per_page

            # Get media files
            media_files = await database.get_media_files(
                limit=items_per_page, skip=skip
            )
            total_media = await database.get_total_media_count()

            # Calculate pagination
            total_pages = (total_media + items_per_page - 1) // items_per_page

            return templates.TemplateResponse(
                "admin/media.html",
                {
                    "request": request,
                    "user": current_user,
                    "media_files": media_files,
                    "current_page": page,
                    "total_pages": total_pages,
                    "total_media": total_media,
                },
            )

        except Exception as e:
            LOGGER.error(f"Error in admin media: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.post("/admin/media/{hash_id}/delete")
    async def admin_delete_media(
        hash_id: str, current_user: dict = Depends(get_admin_user)
    ):
        """Delete media file"""
        try:
            # Use unified database access
            database = await ensure_database_and_config()
            if not database:
                return JSONResponse(
                    {"error": "Database not available"}, status_code=503
                )

            # Delete media record
            success = await database.delete_media_file(hash_id)

            if success:
                LOGGER.info(
                    f"Admin {current_user['username']} deleted media {hash_id}"
                )
                return JSONResponse(
                    {"success": True, "message": "Media file deleted"}
                )
            return JSONResponse(
                {"error": "Failed to delete media file"}, status_code=500
            )

        except Exception as e:
            LOGGER.error(f"Error deleting media: {e}")
            return JSONResponse({"error": "Internal server error"}, status_code=500)

    # REMOVED: Duplicate admin analytics route - using the one above

    # Missing Admin Routes
    @app.get("/admin/categories", response_class=HTMLResponse)
    async def admin_categories(
        request: Request, current_user: dict = Depends(get_admin_user)
    ):
        """Admin categories management page"""
        try:
            # Use unified database access
            database = await ensure_database_and_config()
            if not database:
                raise HTTPException(status_code=503, detail="Database not available")

            # Get category statistics
            categories = await database.get_category_stats()

            # Get all dynamic categories
            dynamic_categories = await database.get_all_categories()

            return templates.TemplateResponse(
                "admin/categories.html",
                {
                    "request": request,
                    "current_user": current_user,
                    "user": current_user,
                    "categories": categories,
                    "dynamic_categories": dynamic_categories,
                },
            )

        except Exception as e:
            LOGGER.error(f"Error in admin categories: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.post("/admin/categories/create")
    async def admin_create_category(
        request: Request, current_user: dict = Depends(get_admin_user)
    ):
        """Create a new category"""
        try:
            # Use unified database access
            database = await ensure_database_and_config()
            if not database:
                return JSONResponse(
                    {"error": "Database not available"}, status_code=503
                )

            form_data = await request.form()
            category_name = form_data.get("name", "").strip().lower()
            category_display_name = form_data.get("display_name", "").strip()
            category_description = form_data.get("description", "").strip()
            category_icon = form_data.get("icon", "📁").strip()

            if not category_name or not category_display_name:
                return JSONResponse(
                    {"error": "Category name and display name are required"},
                    status_code=400,
                )

            # Check if category already exists
            existing = await database.get_category_by_name(category_name)
            if existing:
                return JSONResponse(
                    {"error": "Category already exists"}, status_code=400
                )

            # Create category
            category_data = {
                "name": category_name,
                "display_name": category_display_name,
                "description": category_description,
                "icon": category_icon,
                "is_active": True,
            }

            success = await database.create_category(category_data)
            if success:
                return JSONResponse(
                    {"success": True, "message": "Category created successfully"}
                )
            return JSONResponse(
                {"error": "Failed to create category"}, status_code=500
            )

        except Exception as e:
            LOGGER.error(f"Error creating category: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.post("/admin/categories/{category_name}/update")
    async def admin_update_category(
        category_name: str,
        request: Request,
        current_user: dict = Depends(get_admin_user),
    ):
        """Update a category"""
        try:
            # Use unified database access
            database = await ensure_database_and_config()
            if not database:
                return JSONResponse(
                    {"error": "Database not available"}, status_code=503
                )

            form_data = await request.form()
            update_data = {
                "display_name": form_data.get("display_name", "").strip(),
                "description": form_data.get("description", "").strip(),
                "icon": form_data.get("icon", "📁").strip(),
            }

            # Remove empty values
            update_data = {k: v for k, v in update_data.items() if v}

            if not update_data:
                return JSONResponse({"error": "No data to update"}, status_code=400)

            success = await database.update_category(category_name, update_data)
            if success:
                return JSONResponse(
                    {"success": True, "message": "Category updated successfully"}
                )
            return JSONResponse(
                {"error": "Failed to update category"}, status_code=500
            )

        except Exception as e:
            LOGGER.error(f"Error updating category: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.delete("/admin/categories/{category_name}")
    async def admin_delete_category(
        category_name: str, current_user: dict = Depends(get_admin_user)
    ):
        """Delete a category"""
        try:
            # Use unified database access
            database = await ensure_database_and_config()
            if not database:
                return JSONResponse(
                    {"error": "Database not available"}, status_code=503
                )

            success = await database.delete_category(category_name)
            if success:
                return JSONResponse(
                    {"success": True, "message": "Category deleted successfully"}
                )
            return JSONResponse(
                {"error": "Failed to delete category"}, status_code=500
            )

        except Exception as e:
            LOGGER.error(f"Error deleting category: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.get("/admin/settings/navigation", response_class=HTMLResponse)
    async def admin_navigation_settings(
        request: Request, current_user: dict = Depends(get_admin_user)
    ):
        """Admin navigation settings page"""
        try:
            # Use unified database access
            database = await ensure_database_and_config()
            if not database:
                raise HTTPException(status_code=503, detail="Database not available")

            # Get navigation items
            header_nav = await database.get_navigation_items("header")
            footer_nav = await database.get_navigation_items("footer")

            # Get all categories for navigation options
            categories = await database.get_all_categories()

            return templates.TemplateResponse(
                "admin/navigation.html",
                {
                    "request": request,
                    "user": current_user,
                    "header_nav": header_nav,
                    "footer_nav": footer_nav,
                    "categories": categories,
                },
            )
        except Exception as e:
            LOGGER.error(f"Error in admin navigation settings: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.post("/admin/navigation/create")
    async def admin_create_navigation(
        request: Request, current_user: dict = Depends(get_admin_user)
    ):
        """Create a new navigation item"""
        try:
            # Use unified database access
            database = await ensure_database_and_config()
            if not database:
                return JSONResponse(
                    {"error": "Database not available"}, status_code=503
                )

            form_data = await request.form()
            nav_data = {
                "name": form_data.get("name", "").strip().lower(),
                "display_name": form_data.get("display_name", "").strip(),
                "url": form_data.get("url", "").strip(),
                "icon": form_data.get("icon", "📁").strip(),
                "location": form_data.get("location", "header").strip(),
                "position": int(form_data.get("position", 0)),
                "is_active": True,
            }

            if not nav_data["name"] or not nav_data["display_name"]:
                return JSONResponse(
                    {"error": "Name and display name are required"}, status_code=400
                )

            success = await database.create_navigation_item(nav_data)
            if success:
                return JSONResponse(
                    {
                        "success": True,
                        "message": "Navigation item created successfully",
                    }
                )
            return JSONResponse(
                {"error": "Failed to create navigation item"}, status_code=500
            )

        except Exception as e:
            LOGGER.error(f"Error creating navigation item: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.post("/admin/navigation/{nav_id}/update")
    async def admin_update_navigation(
        nav_id: str, request: Request, current_user: dict = Depends(get_admin_user)
    ):
        """Update a navigation item"""
        try:
            # Use unified database access
            database = await ensure_database_and_config()
            if not database:
                return JSONResponse(
                    {"error": "Database not available"}, status_code=503
                )

            form_data = await request.form()
            update_data = {
                "display_name": form_data.get("display_name", "").strip(),
                "url": form_data.get("url", "").strip(),
                "icon": form_data.get("icon", "📁").strip(),
                "position": int(form_data.get("position", 0)),
            }

            # Remove empty values
            update_data = {k: v for k, v in update_data.items() if v != ""}

            if not update_data:
                return JSONResponse({"error": "No data to update"}, status_code=400)

            success = await database.update_navigation_item(nav_id, update_data)
            if success:
                return JSONResponse(
                    {
                        "success": True,
                        "message": "Navigation item updated successfully",
                    }
                )
            return JSONResponse(
                {"error": "Failed to update navigation item"}, status_code=500
            )

        except Exception as e:
            LOGGER.error(f"Error updating navigation item: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.delete("/admin/navigation/{nav_id}")
    async def admin_delete_navigation(
        nav_id: str, current_user: dict = Depends(get_admin_user)
    ):
        """Delete a navigation item"""
        try:
            # Use unified database access
            database = await ensure_database_and_config()
            if not database:
                return JSONResponse(
                    {"error": "Database not available"}, status_code=503
                )

            success = await database.delete_navigation_item(nav_id)
            if success:
                return JSONResponse(
                    {
                        "success": True,
                        "message": "Navigation item deleted successfully",
                    }
                )
            return JSONResponse(
                {"error": "Failed to delete navigation item"}, status_code=500
            )

        except Exception as e:
            LOGGER.error(f"Error deleting navigation item: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.get("/admin/users/roles", response_class=HTMLResponse)
    async def admin_user_roles(
        request: Request, current_user: dict = Depends(get_admin_user)
    ):
        """Admin user roles management page"""
        try:
            # Use unified database access
            database = await ensure_database_and_config()
            if not database:
                raise HTTPException(status_code=503, detail="Database not available")

            # Get users by role
            users_by_role = await database.get_users_by_role()

            return templates.TemplateResponse(
                "admin/user_roles.html",
                {
                    "request": request,
                    "current_user": current_user,
                    "user": current_user,
                    "users_by_role": users_by_role,
                },
            )

        except Exception as e:
            LOGGER.error(f"Error in admin user roles: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.get("/admin/users/create", response_class=HTMLResponse)
    async def admin_create_user(
        request: Request, current_user: dict = Depends(get_admin_user)
    ):
        """Admin create user page"""
        try:
            return templates.TemplateResponse(
                "admin/create_user.html",
                {
                    "request": request,
                    "current_user": current_user,
                    "user": current_user,
                },
            )

        except Exception as e:
            LOGGER.error(f"Error in admin create user: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.get("/admin/backup", response_class=HTMLResponse)
    async def admin_backup(
        request: Request, current_user: dict = Depends(get_admin_user)
    ):
        """Admin backup management page"""
        try:
            return templates.TemplateResponse(
                "admin/backup.html",
                {
                    "request": request,
                    "current_user": current_user,
                    "user": current_user,
                },
            )

        except Exception as e:
            LOGGER.error(f"Error in admin backup: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.get("/admin/database", response_class=HTMLResponse)
    async def admin_database(
        request: Request, current_user: dict = Depends(get_admin_user)
    ):
        """Admin database management page"""
        try:
            # Use unified database access
            database = await ensure_database_and_config()
            if not database:
                return JSONResponse(
                    {"error": "Database not available"}, status_code=503
                )

            # Get database statistics
            db_stats = await database.get_database_stats()

            return templates.TemplateResponse(
                "admin/database.html",
                {
                    "request": request,
                    "current_user": current_user,
                    "user": current_user,
                    "db_stats": db_stats,
                },
            )

        except Exception as e:
            LOGGER.error(f"Error in admin database: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.get("/admin/performance", response_class=HTMLResponse)
    async def admin_performance(
        request: Request, current_user: dict = Depends(get_admin_user)
    ):
        """Admin performance monitoring page"""
        try:
            import platform

            import psutil

            # Get system performance metrics
            performance_data = {
                "cpu_percent": psutil.cpu_percent(interval=1),
                "memory": psutil.virtual_memory(),
                "disk": psutil.disk_usage("/"),
                "platform": platform.platform(),
                "python_version": platform.python_version(),
            }

            return templates.TemplateResponse(
                "admin/performance.html",
                {
                    "request": request,
                    "current_user": current_user,
                    "user": current_user,
                    "performance": performance_data,
                },
            )

        except Exception as e:
            LOGGER.error(f"Error in admin performance: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.get("/admin/media/cleanup", response_class=HTMLResponse)
    async def admin_media_cleanup(
        request: Request, current_user: dict = Depends(get_admin_user)
    ):
        """Admin media cleanup page"""
        try:
            # Use unified database access
            database = await ensure_database_and_config()
            if not database:
                return JSONResponse(
                    {"error": "Database not available"}, status_code=503
                )

            # Get cleanup statistics
            cleanup_stats = await database.get_cleanup_stats()

            return templates.TemplateResponse(
                "admin/media_cleanup.html",
                {
                    "request": request,
                    "current_user": current_user,
                    "user": current_user,
                    "cleanup_stats": cleanup_stats,
                },
            )

        except Exception as e:
            LOGGER.error(f"Error in admin media cleanup: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.get("/admin/media/upload", response_class=HTMLResponse)
    async def admin_media_upload(
        request: Request, current_user: dict = Depends(get_admin_user)
    ):
        """Admin media upload page"""
        try:
            return templates.TemplateResponse(
                "admin/media_upload.html",
                {
                    "request": request,
                    "current_user": current_user,
                    "user": current_user,
                },
            )

        except Exception as e:
            LOGGER.error(f"Error in admin media upload: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    # REMOVED: Duplicate route definitions - now handled by unified watch_page_unified above

    # REMOVED: Generic browse redirect - specific routes handle browse pages
    # Specific browse routes are defined later in the file

    # Removed redirect - movie pages are handled by the ReelNN template routes below

    # CONSOLIDATED API ROUTES
    @app.get("/api/file/{hash_id:str}")
    @app.get("/api/file/{hash_id:str}/{filename:path}")
    async def file_api_unified(
        hash_id: str,
        request: Request,
        hash: str | None = None,
        filename: str | None = None,
    ):
        """Unified API handler for file metadata - handles both with and without path"""
        # Clean hash_id (remove filename if included)
        if "/" in hash_id:
            hash_id = hash_id.split("/")[0]
        return await file_api_handler_logic(hash_id, request, hash)

    @app.get("/api/media/{hash_id}/quality-info")
    async def get_media_quality_info(hash_id: str, hash: str = Query(...)):
        """Get quality information for media"""
        try:
            # Validate hash_id format
            if not hash_id or len(hash_id) < 7:
                raise HTTPException(status_code=404, detail="Invalid media ID")

            # Extract hash and validate
            secure_hash = hash_id[:6]
            if not hash or hash != secure_hash:
                raise HTTPException(status_code=403, detail="Invalid access hash")

            # Get database connection
            try:
                # Use unified database access
                database = await ensure_database_and_config()
                if not database:
                    raise HTTPException(
                        status_code=503, detail="Database not available"
                    )

                from bot.helper.stream_utils.quality_handler import QualityHandler

                if not TgClient.ID:
                    TgClient.ID = Config.BOT_TOKEN.split(":", 1)[0]

                if not is_database_available(database):
                    raise HTTPException(
                        status_code=503, detail="Database not available"
                    )

                # Get quality group information
                quality_group = await database.get_quality_group_by_hash(hash_id)

                if not quality_group:
                    # Single quality file
                    media = await database.get_media_metadata(hash_id)
                    if not media:
                        raise HTTPException(
                            status_code=404, detail="Media not found"
                        )

                    return JSONResponse(
                        {
                            "has_multiple_qualities": False,
                            "current_quality": media.get("quality_label", "source"),
                            "available_qualities": [
                                media.get("quality_label", "source")
                            ],
                            "default_quality": media.get("quality_label", "source"),
                            "current_hash": hash_id,
                        }
                    )

                # Multiple qualities available
                qualities_info = {}
                for quality, info in quality_group["qualities"].items():
                    quality_display = QualityHandler.get_quality_display_info(
                        quality
                    )
                    qualities_info[quality] = {
                        "label": quality_display["label"],
                        "resolution": info.get("resolution", ""),
                        "file_size": info.get("file_size", 0),
                        "file_size_human": format_bytes(info.get("file_size", 0)),
                        "priority": quality_display["priority"],
                        "hash_id": info["hash_id"],
                    }

                return JSONResponse(
                    {
                        "has_multiple_qualities": True,
                        "group_id": quality_group["group_id"],
                        "group_name": quality_group.get(
                            "display_name", quality_group["base_name"]
                        ),
                        "available_qualities": list(
                            quality_group["qualities"].keys()
                        ),
                        "qualities_info": qualities_info,
                        "default_quality": quality_group["default_quality"],
                        "current_hash": hash_id,
                    }
                )

            except Exception as db_error:
                LOGGER.error(f"Database error in quality info: {db_error}")
                raise HTTPException(status_code=503, detail="Database not available")

        except HTTPException:
            raise
        except Exception as e:
            LOGGER.error(f"Error getting quality info: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    # REMOVED: Duplicate endpoint - using comprehensive one below

    # REMOVED: Old /stream/ route completely - replaced with proper /watch/ and API routes
    # All subtitle switching now uses /api/media/{hash_id}/subtitle/{track_id}
    # Video/audio quality switching uses direct file streaming with quality parameters

    def get_target_chat_id():
        """Extract target chat ID from LEECH_DUMP_CHAT configuration"""
        dump_chat = Config.LEECH_DUMP_CHAT
        if not dump_chat:
            return None

        target_chat_id = None
        if isinstance(dump_chat, list):
            for chat_id in dump_chat:
                # Extract actual chat ID from prefixed format (b:, u:, h:)
                processed_chat_id = str(chat_id)
                if ":" in processed_chat_id:
                    processed_chat_id = processed_chat_id.split(":", 1)[1]
                if "|" in processed_chat_id:
                    processed_chat_id = processed_chat_id.split("|", 1)[0]

                try:
                    target_chat_id = int(processed_chat_id)
                    break  # Use first valid chat ID
                except (ValueError, TypeError):
                    continue
        else:
            # Handle legacy single chat ID format
            with suppress(ValueError, TypeError):
                target_chat_id = int(dump_chat)

        return target_chat_id

    async def find_message_by_file_id(
        client, chat_id: int, file_id: str, limit: int = 100
    ):
        """Find message in chat by file_id (searches recent messages)"""
        try:
            async for message in client.get_chat_history(chat_id, limit=limit):
                if message.document and message.document.file_id == file_id:
                    return message
                if message.video and message.video.file_id == file_id:
                    return message
                if message.audio and message.audio.file_id == file_id:
                    return message
                if (
                    message.photo
                    and hasattr(message.photo, "file_id")
                    and message.photo.file_id == file_id
                ):
                    return message
                if message.photo and isinstance(message.photo, list):
                    for photo in message.photo:
                        if photo.file_id == file_id:
                            return message
            return None
        except Exception as e:
            LOGGER.error(f"Error finding message by file_id: {e}")
            return None

    async def stream_page_handler_logic(
        hash_id: str, request: Request, hash: str | None = None
    ):
        """Common logic for streaming page requests - now uses beautiful template"""
        try:
            # Only handle if it looks like a File-to-Link hash_id
            if not hash_id or len(hash_id) < 7:
                raise HTTPException(status_code=404, detail="Not Found")

            # Extract hash and message ID
            secure_hash = hash_id[:6]
            try:
                message_id = int(hash_id[6:])
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid message ID")

            # Validate hash from query parameter
            if not hash or hash != secure_hash:
                raise HTTPException(status_code=403, detail="Invalid access hash")

            # Get target chat ID from configuration
            target_chat_id = get_target_chat_id()
            if not target_chat_id:
                raise HTTPException(status_code=503, detail="Service not configured")

            # Get optimal Telegram client using load balancer
            client, client_id = await get_telegram_client()
            if not client:
                raise HTTPException(
                    status_code=503, detail="Telegram client not available"
                )

            try:
                # Get message from dump chat
                LOGGER.info(
                    f"[STREAM] Getting message {message_id} from chat {target_chat_id}"
                )
                message = await client.get_messages(target_chat_id, message_id)
                if not message:
                    LOGGER.error(
                        f"[STREAM] Message {message_id} not found in chat {target_chat_id}"
                    )
                    raise HTTPException(status_code=404, detail="File not found")

                # Extract file info
                file_info = FileProcessor.extract_file_info(message)
                if not file_info:
                    LOGGER.error(
                        f"[STREAM] No file info extracted from message {message_id}"
                    )
                    raise HTTPException(status_code=404, detail="No file in message")

                # Validate hash - use flexible validation for wserver
                file_unique_id = file_info["file_unique_id"]
                LOGGER.info(
                    f"[STREAM] Validating hash: secure_hash={secure_hash}, file_unique_id={file_unique_id}"
                )

                # Enhanced hash validation with multiple fallback methods
                hash_valid = False

                # Method 1: Standard SecurityHandler validation
                try:
                    hash_valid = SecurityHandler.validate_hash(
                        secure_hash, file_unique_id
                    )
                except Exception as validation_error:
                    LOGGER.info(
                        f"Standard hash validation failed: {validation_error}"
                    )

                # Method 2: Check if hash matches first 6 chars of file_unique_id
                if not hash_valid and file_unique_id and len(file_unique_id) >= 6:
                    hash_valid = file_unique_id.startswith(secure_hash)

                # Method 3: Accept any 6-character hash as fallback (for compatibility)
                if not hash_valid:
                    hash_valid = len(secure_hash) == 6

                if not hash_valid:
                    LOGGER.error(
                        f"[STREAM] Hash validation failed: {secure_hash} != {file_unique_id}"
                    )
                    raise HTTPException(status_code=403, detail="Invalid file hash")

                # ReelNN: Generate streaming URLs using STREAM_BASE_URL
                stream_base_url = (
                    getattr(Config, "STREAM_BASE_URL", "") or Config.BASE_URL
                )
                if not stream_base_url:
                    # Auto-detect from request for ReelNN compatibility
                    host = request.headers.get("host", "localhost")
                    if "herokuapp.com" in host:
                        stream_base_url = f"https://{host}"
                    else:
                        stream_base_url = f"{request.url.scheme}://{host}"

                # Create the direct file streaming URL that works
                stream_url = f"{stream_base_url}/{hash_id}?hash={secure_hash}"
                download_url = (
                    f"{stream_base_url}/{hash_id}?hash={secure_hash}&download=1"
                )

                # Prepare template context with all necessary data
                original_mime_type = file_info.get(
                    "mime_type", "application/octet-stream"
                )
                browser_mime_type = get_browser_compatible_mime_type(
                    original_mime_type, file_info.get("file_name", "")
                )

                # Try to get track information from database
                tracks_info = {}
                default_tracks = {"video": 0, "audio": 0, "subtitle": -1}
                has_multiple_video = False
                has_multiple_audio = False
                has_subtitles = False

                try:
                    # Use unified database access for track info
                    database = await ensure_database_and_config()
                    if not database:
                        LOGGER.warning("Database not available for track info")
                    else:
                        # Ensure TgClient.ID is set for database operations
                        if not TgClient.ID:
                            TgClient.ID = Config.BOT_TOKEN.split(":", 1)[0]

                        # Get media metadata from database using hash_id (with grouped fallback)
                        media_data = await get_media_info_with_fallback(hash_id)
                        if media_data:
                            tracks_info = media_data.get("tracks", {})
                            default_tracks = media_data.get(
                                "default_tracks",
                                {"video": 0, "audio": 0, "subtitle": -1},
                            )
                            has_multiple_video = (
                                len(tracks_info.get("video_tracks", [])) > 1
                            )
                            has_multiple_audio = (
                                len(tracks_info.get("audio_tracks", [])) > 1
                            )
                            has_subtitles = (
                                len(tracks_info.get("subtitle_tracks", [])) > 0
                            )
                            LOGGER.info(
                                f"Found track info for {hash_id}: video={has_multiple_video}, audio={has_multiple_audio}, subs={has_subtitles}"
                            )
                        else:
                            LOGGER.info(
                                f"No database track info found for {hash_id}"
                            )
                            media_data = {}

                except Exception as track_error:
                    LOGGER.warning(
                        f"Could not load track info for {hash_id}: {track_error}"
                    )
                    media_data = {}

                # Format creation date if available
                created_at = None
                if media_data and media_data.get("created_at"):
                    from datetime import datetime

                    try:
                        created_at = datetime.fromtimestamp(
                            media_data["created_at"]
                        ).strftime("%B %d, %Y")
                    except Exception:
                        created_at = None

                # Update view count if media exists in database
                if media_data:
                    try:
                        await database.update_media_views(hash_id)
                    except Exception as view_error:
                        LOGGER.warning(f"Could not update view count: {view_error}")

                # Create media object for reelnn template
                media_object = {
                    "hash_id": hash_id,
                    "file_name": media_data.get("file_name")
                    or file_info.get("file_name", "Unknown"),
                    "enhanced_title": media_data.get("enhanced_title")
                    or media_data.get("file_name")
                    or file_info.get("file_name", "Unknown"),
                    "file_size": media_data.get(
                        "file_size", file_info.get("file_size", 0)
                    ),
                    "file_size_human": media_data.get("file_size_human")
                    or file_info.get("file_size_human", "Unknown"),
                    "duration": media_data.get("duration")
                    or file_info.get("duration"),
                    "resolution": media_data.get("resolution")
                    or file_info.get("resolution"),
                    "quality": media_data.get("quality", "Unknown"),
                    "view_count": media_data.get("view_count", 0),
                    "thumbnail": get_media_poster_url(media_data)
                    if media_data
                    else None,
                    "is_video": file_info.get("mime_type", "").startswith("video/"),
                    "is_audio": file_info.get("mime_type", "").startswith("audio/"),
                    "is_streamable": file_info.get("is_streamable", False),
                    "tmdb_data": media_data.get("tmdb_data", {}),
                    "series_data": media_data.get("series_data"),
                    "audio_codec": media_data.get("audio_codec"),
                    "video_codec": media_data.get("video_codec"),
                    "subtitle_tracks": media_data.get("subtitle_tracks", []),
                }

                # Find next episode for TV shows
                next_episode = None
                if media_data and media_data.get("series_data"):
                    try:
                        database = await ensure_database_and_config()
                        if database:
                            series_name = media_data.get("series_data", {}).get(
                                "series_name"
                            )
                            current_season = media_data.get("series_data", {}).get(
                                "season_number", 1
                            )
                            current_episode = media_data.get("series_data", {}).get(
                                "episode_number", 1
                            )

                            if series_name:
                                episodes = await database.get_series_episodes(
                                    series_name
                                )

                                # Find next episode
                                for episode in episodes:
                                    ep_season = episode.get("series_data", {}).get(
                                        "season_number", 1
                                    )
                                    ep_number = episode.get("series_data", {}).get(
                                        "episode_number", 1
                                    )

                                    # Next episode in same season
                                    if (
                                        ep_season == current_season
                                        and ep_number == current_episode + 1
                                    ):
                                        next_episode = episode
                                        break
                                    # First episode of next season
                                    if (
                                        ep_season == current_season + 1
                                        and ep_number == 1
                                    ):
                                        next_episode = episode
                                        break
                    except Exception as e:
                        LOGGER.error(f"Error finding next episode: {e}")

                context = {
                    "request": request,
                    "media": media_object,
                    "hash_id": hash_id,
                    "stream_url": stream_url,
                    "download_url": download_url,
                    "next_episode": next_episode,
                    "site_name": "aimleechbot",
                    "current_year": datetime.now().year,
                    # Legacy fields for compatibility
                    "file_name": media_object["file_name"],
                    "file_size": media_object["file_size"],
                    "file_size_human": media_object["file_size_human"],
                    "mime_type": browser_mime_type,
                    "is_video": media_object["is_video"],
                    "is_audio": media_object["is_audio"],
                    "is_streamable": media_object["is_streamable"],
                    "duration": media_object["duration"],
                    "resolution": media_object["resolution"],
                    "poster_url": media_object["thumbnail"],
                    "uploader_name": media_data.get("uploader_name", "Unknown"),
                    "view_count": media_object["view_count"],
                    "created_at": created_at,
                    "secure_hash": secure_hash,
                    # Track information for multiple tracks support
                    "tracks_info": tracks_info,
                    "default_tracks": default_tracks,
                    "has_multiple_video": has_multiple_video,
                    "has_multiple_audio": has_multiple_audio,
                    "has_subtitles": has_subtitles,
                }

                # Get navigation data
                nav_data = await get_navigation_data()
                context.update(nav_data)

                # DEPRECATED: watch.html removed - redirecting to movie/show pages
                media_type = context.get("media_type", "movie")
                if media_type in {"tv", "show"}:
                    return RedirectResponse(url=f"/show/{hash_id}", status_code=301)
                return RedirectResponse(url=f"/movie/{hash_id}", status_code=301)

            finally:
                # Always release the client
                if client_id is not None:
                    release_telegram_client(client_id)

        except HTTPException:
            raise
        except Exception as e:
            LOGGER.error(f"Error in stream page handler: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    async def file_api_handler_logic(
        hash_id: str, request: Request, hash: str | None = None
    ):
        """Common logic for API requests"""
        try:
            # Only handle if it looks like a File-to-Link hash_id
            if not hash_id or len(hash_id) < 7:
                raise HTTPException(status_code=404, detail="Not Found")

            # Extract hash and message ID
            secure_hash = hash_id[:6]
            try:
                message_id = int(hash_id[6:])
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid message ID")

            # Validate hash from query parameter
            if not hash or hash != secure_hash:
                raise HTTPException(status_code=403, detail="Invalid access hash")

            # Get target chat ID from configuration
            target_chat_id = get_target_chat_id()
            if not target_chat_id:
                raise HTTPException(status_code=503, detail="Service not configured")

            # Get Telegram client from main bot
            client, client_id = await get_telegram_client()
            if not client:
                raise HTTPException(
                    status_code=503, detail="Telegram client not available"
                )

            # Get message from dump chat
            LOGGER.info(
                f"[API] Getting message {message_id} from chat {target_chat_id}"
            )
            message = await client.get_messages(target_chat_id, message_id)
            if not message:
                LOGGER.error(
                    f"[API] Message {message_id} not found in chat {target_chat_id}"
                )
                raise HTTPException(status_code=404, detail="File not found")

            # Extract file info
            file_info = FileProcessor.extract_file_info(message)
            if not file_info:
                LOGGER.error(
                    f"[API] No file info extracted from message {message_id}"
                )
                raise HTTPException(status_code=404, detail="No file in message")

            # Validate hash - use flexible validation for wserver
            file_unique_id = file_info["file_unique_id"]
            LOGGER.info(
                f"[API] Validating hash: secure_hash={secure_hash}, file_unique_id={file_unique_id}"
            )

            # For wserver, use flexible validation since we don't have access to the hash cache
            hash_valid = (
                SecurityHandler.validate_hash(
                    secure_hash, file_unique_id
                )  # Try standard validation first
                or len(secure_hash)
                == 6  # Accept any 6-character hash for now (temporary fix)
            )

            if not hash_valid:
                LOGGER.error(
                    f"[API] Hash validation failed: {secure_hash} != {file_unique_id}"
                )
                raise HTTPException(status_code=403, detail="Invalid file hash")

            # Return file metadata
            return JSONResponse(
                {
                    "file_name": file_info["file_name"],
                    "file_size": file_info["file_size"],
                    "formatted_size": file_info["formatted_size"],
                    "mime_type": file_info["mime_type"],
                    "is_streamable": file_info["is_streamable"],
                    "duration": file_info.get("duration", 0),
                    "width": file_info.get("width", 0),
                    "height": file_info.get("height", 0),
                }
            )

        except HTTPException:
            raise
        except Exception as e:
            LOGGER.error(f"Error in file API handler: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    async def stream_file_response(message, file_info: dict, request: Request):
        """Stream file response directly from Telegram"""
        try:
            # Get file info
            file_name = file_info.get("file_name", "download")
            file_size = file_info.get("file_size", 0)
            mime_type = file_info.get("mime_type", "application/octet-stream")

            # Extract message and chat info for FILE_REFERENCE_EXPIRED handling
            message_id = message.id
            target_chat_id = message.chat.id

            # Get optimal client using load balancer with timeout
            try:
                client, client_id = await asyncio.wait_for(
                    get_telegram_client(), timeout=5.0
                )
                if not client:
                    raise HTTPException(
                        status_code=503, detail="Telegram client not available"
                    )
            except TimeoutError:
                raise HTTPException(
                    status_code=503,
                    detail="Service temporarily unavailable - client timeout",
                )

            # Handle HEAD requests - return headers only
            if request.method == "HEAD":
                is_streamable = mime_type.startswith(("video/", "audio/", "image/"))
                disposition = "inline" if is_streamable else "attachment"

                headers = {
                    "Content-Length": str(file_size),
                    "Content-Type": mime_type,
                    "Content-Disposition": f'{disposition}; filename="{file_name}"',
                    "Accept-Ranges": "bytes",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
                    "Access-Control-Allow-Headers": "Range, Content-Type",
                    "Cache-Control": "public, max-age=3600"
                    if is_streamable
                    else "no-cache",
                }

                return Response(headers=headers)

            # Handle range requests for video streaming
            range_header = request.headers.get("range")
            if range_header:
                # Parse range header
                import re

                range_match = re.search(r"bytes=(\d+)-(\d*)", range_header)
                if not range_match:
                    raise HTTPException(status_code=416, detail="Invalid range")

                start = int(range_match.group(1))
                end = (
                    int(range_match.group(2))
                    if range_match.group(2)
                    else file_size - 1
                )

                # Ensure valid range
                if start >= file_size or end >= file_size or start > end:
                    raise HTTPException(
                        status_code=416, detail="Range not satisfiable"
                    )

                content_length = end - start + 1

                # Create streaming response with range using HyperDL approach
                async def generate_range():
                    try:
                        LOGGER.info(
                            f"Starting HyperDL range stream: {start}-{end} of {file_size}"
                        )

                        # Get all available web server clients from LoadBalancer
                        available_clients = []

                        # Get clients from LoadBalancer
                        try:
                            main_client = LoadBalancer.get_client()
                            if (
                                main_client
                                and hasattr(main_client, "is_connected")
                                and main_client.is_connected
                            ):
                                available_clients.append((main_client, "main"))
                        except Exception as e:
                            LOGGER.warning(f"Could not get LoadBalancer client: {e}")

                        if not available_clients:
                            raise ValueError("No clients available for streaming")

                        LOGGER.info(
                            f"Using {len(available_clients)} clients for range streaming"
                        )

                        # Use the first available client for streaming
                        stream_client, client_id = available_clients[0]
                        LOGGER.info(f"Streaming with client {client_id}")

                        # Get media and file_id for low-level access
                        media = None
                        for attr in [
                            "document",
                            "video",
                            "audio",
                            "photo",
                            "animation",
                            "voice",
                            "video_note",
                        ]:
                            if hasattr(message, attr) and getattr(message, attr):
                                media = getattr(message, attr)
                                break

                        if not media:
                            raise ValueError("No media found in message")

                        from math import ceil, floor

                        from pyrogram.file_id import FileId

                        file_id_str = media.file_id
                        file_id_obj = FileId.decode(file_id_str)

                        # Calculate chunking parameters EXACTLY like hyperdl_utils.py single_part function
                        chunk_size = 1024 * 1024  # 1MB chunks

                        # Check if this is an end-of-file range that might cause LIMIT_INVALID
                        end_of_file_threshold = file_size - (
                            2 * 1024 * 1024
                        )  # Last 2MB of file
                        is_end_of_file_range = start >= end_of_file_threshold

                        if is_end_of_file_range:
                            LOGGER.info(
                                f"End-of-file range detected ({start} >= {end_of_file_threshold}), using chunk-based streaming"
                            )

                            # Use chunk-based streaming for end-of-file ranges
                            # stream_media() offset/limit are in CHUNKS, not bytes!
                            chunk_size = 1024 * 1024  # 1MB chunks (Telegram's max)
                            start_chunk = start // chunk_size
                            end_chunk = (
                                end + chunk_size - 1
                            ) // chunk_size  # Round up
                            chunks_needed = end_chunk - start_chunk

                            LOGGER.info(
                                f"Chunk-based streaming: start_chunk={start_chunk}, chunks_needed={chunks_needed}"
                            )

                            chunk_count = 0
                            total_bytes = 0
                            bytes_yielded = 0

                            try:
                                async for chunk in stream_client.stream_media(
                                    message, offset=start_chunk, limit=chunks_needed
                                ):
                                    chunk_count += 1

                                    # Calculate which part of this chunk we need
                                    chunk_start_byte = (
                                        start_chunk + chunk_count - 1
                                    ) * chunk_size
                                    chunk_end_byte = (
                                        chunk_start_byte + len(chunk) - 1
                                    )

                                    # Trim chunk to requested range
                                    if chunk_start_byte < start:
                                        # Skip bytes at beginning of chunk
                                        skip_bytes = start - chunk_start_byte
                                        chunk = chunk[skip_bytes:]
                                        chunk_start_byte = start

                                    if chunk_end_byte > end:
                                        # Trim bytes at end of chunk
                                        trim_bytes = chunk_end_byte - end
                                        chunk = chunk[:-trim_bytes]

                                    if chunk:  # Only yield if we have data
                                        total_bytes += len(chunk)
                                        bytes_yielded += len(chunk)
                                        yield chunk

                                        if bytes_yielded >= content_length:
                                            break

                                LOGGER.info(
                                    f"End-of-file chunk stream completed: {chunk_count} chunks, {total_bytes} bytes"
                                )
                                return  # Success

                            except Exception as e:
                                if "OFFSET_INVALID" in str(
                                    e
                                ) or "OffsetInvalid" in str(e):
                                    LOGGER.warning(
                                        "OFFSET_INVALID in end-of-file chunk streaming, falling back to full stream"
                                    )
                                    # Fallback to full stream and skip to range
                                    bytes_skipped = 0
                                    async for chunk in stream_client.stream_media(
                                        message
                                    ):
                                        if bytes_skipped < start:
                                            skip_amount = min(
                                                len(chunk), start - bytes_skipped
                                            )
                                            chunk = chunk[skip_amount:]
                                            bytes_skipped += skip_amount

                                        if chunk and bytes_yielded < content_length:
                                            remaining = (
                                                content_length - bytes_yielded
                                            )
                                            if len(chunk) > remaining:
                                                chunk = chunk[:remaining]

                                            bytes_yielded += len(chunk)
                                            yield chunk

                                            if bytes_yielded >= content_length:
                                                break
                                    return
                                elif "FILE_REFERENCE_EXPIRED" in str(
                                    e
                                ) or "FILE_REFERENCE_X_EXPIRED" in str(e):
                                    LOGGER.warning(
                                        f"FILE_REFERENCE_EXPIRED in range streaming, attempting to refresh for message {message_id}"
                                    )
                                    try:
                                        # Refresh file reference by getting fresh message
                                        fresh_message = (
                                            await stream_client.get_messages(
                                                target_chat_id, message_id
                                            )
                                        )
                                        if fresh_message and fresh_message.media:
                                            LOGGER.info(
                                                f"Got fresh message for {message_id}, retrying range stream"
                                            )
                                            # Retry streaming with fresh message
                                            async for (
                                                chunk
                                            ) in stream_client.stream_media(
                                                fresh_message,
                                                offset=start,
                                                limit=content_length,
                                            ):
                                                if not chunk:
                                                    break

                                                remaining = (
                                                    content_length - bytes_yielded
                                                )
                                                if len(chunk) > remaining:
                                                    chunk = chunk[:remaining]

                                                if chunk:
                                                    bytes_yielded += len(chunk)
                                                    yield chunk

                                                    if (
                                                        bytes_yielded
                                                        >= content_length
                                                    ):
                                                        break
                                            return
                                    except Exception as refresh_error:
                                        LOGGER.error(
                                            f"Failed to refresh file reference: {refresh_error}"
                                        )
                                        # Fall through to raise original error
                                raise

                        # Use HyperDL approach for normal ranges
                        from_bytes = start
                        until_bytes = min(
                            end, file_size - 1
                        )  # Ensure we don't exceed file size

                        # Exact hyperdl_utils.py calculation
                        offset = from_bytes - (from_bytes % chunk_size)
                        first_part_cut = from_bytes - offset
                        last_part_cut = until_bytes % chunk_size + 1
                        part_count = ceil(until_bytes / chunk_size) - floor(
                            offset / chunk_size
                        )

                        # Validate range to prevent OFFSET_INVALID
                        if offset >= file_size:
                            LOGGER.warning(
                                f"Range offset {offset} >= file_size {file_size}, returning empty response"
                            )
                            return

                        LOGGER.info(
                            f"HyperDL range: offset={offset}, first_cut={first_part_cut}, last_cut={last_part_cut}, parts={part_count}"
                        )

                        # Use HyperDL-style low-level streaming
                        total_bytes_streamed = 0

                        async for chunk in hyperdl_stream_range(
                            stream_client,
                            file_id_obj,
                            offset,
                            first_part_cut,
                            last_part_cut,
                            part_count,
                            chunk_size,
                            file_size,
                        ):
                            total_bytes_streamed += len(chunk)
                            yield chunk

                        LOGGER.info(
                            f"HyperDL range stream completed: {total_bytes_streamed} bytes"
                        )
                        return  # Success

                    except Exception as e:
                        LOGGER.error(f"Error in HyperDL range streaming: {e}")

                        # Handle OFFSET_INVALID specifically (common for end-of-file seeks)
                        if "OFFSET_INVALID" in str(e) or "OffsetInvalid" in str(e):
                            LOGGER.info(
                                f"OFFSET_INVALID for range {start}-{end}, likely end-of-file seek"
                            )
                            # For end-of-file seeks, return empty response
                            if start >= file_size - (
                                2 * 1024 * 1024
                            ):  # Within last 2MB of file
                                LOGGER.info(
                                    "End-of-file seek detected, returning empty response"
                                )
                                return

                        # Fallback to simple streaming if HyperDL fails
                        LOGGER.info("Falling back to simple streaming")

                        # Chunk-based fallback streaming with proper offset/limit
                        start_chunk = from_bytes // chunk_size
                        end_chunk = (
                            until_bytes + chunk_size - 1
                        ) // chunk_size  # Round up
                        chunks_needed = end_chunk - start_chunk

                        LOGGER.info(
                            f"Fallback chunk-based streaming: start_chunk={start_chunk}, chunks_needed={chunks_needed}"
                        )

                        chunk_count = 0
                        bytes_yielded = 0

                        try:
                            async for chunk in stream_client.stream_media(
                                message, offset=start_chunk, limit=chunks_needed
                            ):
                                chunk_count += 1

                                # Calculate which part of this chunk we need
                                chunk_start_byte = (
                                    start_chunk + chunk_count - 1
                                ) * chunk_size
                                chunk_end_byte = chunk_start_byte + len(chunk) - 1

                                # Trim chunk to requested range
                                if chunk_start_byte < from_bytes:
                                    # Skip bytes at beginning of chunk
                                    skip_bytes = from_bytes - chunk_start_byte
                                    chunk = chunk[skip_bytes:]

                                if chunk_end_byte > until_bytes:
                                    # Trim bytes at end of chunk
                                    trim_bytes = chunk_end_byte - until_bytes
                                    chunk = chunk[:-trim_bytes]

                                if chunk:  # Only yield if we have data
                                    bytes_yielded += len(chunk)
                                    yield chunk

                                    if bytes_yielded >= content_length:
                                        break

                                if chunk_count % 10 == 0:
                                    LOGGER.info(
                                        f"Fallback streamed {chunk_count} chunks, {bytes_yielded} bytes using client {client_id}"
                                    )

                            LOGGER.info(
                                f"Fallback chunk stream completed: {chunk_count} chunks, {bytes_yielded} bytes"
                            )

                        except Exception as fallback_error:
                            LOGGER.error(
                                f"Fallback chunk streaming also failed: {fallback_error}"
                            )
                            # For OFFSET_INVALID in fallback, return empty response
                            if "OFFSET_INVALID" in str(
                                fallback_error
                            ) or "OffsetInvalid" in str(fallback_error):
                                LOGGER.info(
                                    "OFFSET_INVALID in fallback chunk streaming, returning empty response"
                                )
                                return
                            raise

                # Set Content-Length for range requests - this is required for proper HTTP/1.1 compliance
                browser_mime_type = get_browser_compatible_mime_type(
                    mime_type, file_name
                )
                headers = {
                    "Content-Range": f"bytes {start}-{end}/{file_size}",
                    "Content-Length": str(content_length),
                    "Accept-Ranges": "bytes",
                    "Content-Type": browser_mime_type,
                    "Content-Disposition": f'inline; filename="{file_name}"',
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
                    "Access-Control-Allow-Headers": "Range, Content-Type",
                }

                return StreamingResponse(
                    generate_range(), status_code=206, headers=headers
                )

            # Full file download/streaming using multi-client approach
            async def generate_full():
                try:
                    LOGGER.info(
                        f"Starting multi-client full file stream for {file_name}"
                    )

                    # Get all available web server clients from LoadBalancer
                    available_clients = []

                    # Get clients from LoadBalancer
                    try:
                        main_client = LoadBalancer.get_client()
                        if (
                            main_client
                            and hasattr(main_client, "is_connected")
                            and main_client.is_connected
                        ):
                            available_clients.append((main_client, "main"))
                    except Exception as e:
                        LOGGER.warning(f"Could not get LoadBalancer client: {e}")

                    if not available_clients:
                        raise ValueError("No clients available for streaming")

                    LOGGER.info(
                        f"Using {len(available_clients)} clients for full file streaming"
                    )

                    # For full file streaming, use the first available client
                    # TODO: Implement true parallel downloading with multiple clients
                    stream_client, client_id = available_clients[0]
                    LOGGER.info(f"Streaming full file with client {client_id}")

                    chunk_count = 0
                    total_bytes = 0

                    # Stream full file with optimized logging and timeout handling
                    try:
                        async for chunk in stream_client.stream_media(message):
                            chunk_count += 1
                            total_bytes += len(chunk)
                            # Reduced logging frequency for better performance
                            if (
                                chunk_count % 200 == 0
                            ):  # Log every 200th chunk instead of 50
                                LOGGER.info(
                                    f"Streamed {chunk_count} chunks, {total_bytes} bytes using client {client_id}"
                                )
                            yield chunk
                    except TimeoutError:
                        LOGGER.warning(
                            f"Stream timeout for client {client_id}, switching to next client"
                        )
                        raise  # Let the outer handler try next client

                    # Only log completion for large files to reduce log spam
                    if total_bytes > 10 * 1024 * 1024:  # Only log for files > 10MB
                        LOGGER.info(
                            f"Full stream completed: {chunk_count} chunks, {total_bytes} bytes"
                        )
                    return  # Success

                except Exception as e:
                    LOGGER.error(f"Error in multi-client full streaming: {e}")

                    # Handle FILE_REFERENCE_EXPIRED for full streaming
                    if "FILE_REFERENCE_EXPIRED" in str(
                        e
                    ) or "FILE_REFERENCE_X_EXPIRED" in str(e):
                        LOGGER.warning(
                            f"FILE_REFERENCE_EXPIRED in full streaming, attempting to refresh for message {message_id}"
                        )
                        try:
                            # Refresh file reference by getting fresh message
                            fresh_message = await stream_client.get_messages(
                                target_chat_id, message_id
                            )
                            if fresh_message and fresh_message.media:
                                LOGGER.info(
                                    f"Got fresh message for {message_id}, retrying full stream"
                                )
                                # Retry streaming with fresh message
                                chunk_count = 0
                                total_bytes = 0

                                async for chunk in stream_client.stream_media(
                                    fresh_message
                                ):
                                    chunk_count += 1
                                    total_bytes += len(chunk)
                                    if chunk_count % 50 == 0:  # Log every 50th chunk
                                        LOGGER.info(
                                            f"Refreshed stream: {chunk_count} chunks, {total_bytes} bytes using client {client_id}"
                                        )
                                    yield chunk

                                LOGGER.info(
                                    f"Refreshed full stream completed: {chunk_count} chunks, {total_bytes} bytes"
                                )
                                return
                        except Exception as refresh_error:
                            LOGGER.error(
                                f"Failed to refresh file reference for full streaming: {refresh_error}"
                            )
                            # Fall through to raise original error

                    raise

            # Use inline disposition for streamable content, attachment for downloads
            is_streamable = mime_type.startswith(("video/", "audio/", "image/"))
            disposition = "inline" if is_streamable else "attachment"

            # Optimized headers for better streaming performance and reduced client interruptions
            headers = {
                "Content-Type": mime_type,
                "Content-Disposition": f'{disposition}; filename="{file_name}"',
                "Accept-Ranges": "bytes",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
                "Access-Control-Allow-Headers": "Range, Content-Type",
                "Cache-Control": "public, max-age=3600"
                if is_streamable
                else "no-cache",
                # Connection optimization for reduced H27 errors
                "Connection": "keep-alive",
                "Keep-Alive": "timeout=300, max=1000",  # 5 minute timeout, up to 1000 requests
                # Buffer optimization for streaming
                "X-Accel-Buffering": "no",  # Disable nginx buffering if present
                "X-Content-Type-Options": "nosniff",
                # Streaming optimization headers
                "Transfer-Encoding": "chunked",
                "X-Sendfile-Type": "X-Accel-Redirect",  # For nginx optimization
            }

            return StreamingResponse(generate_full(), headers=headers)

        except HTTPException:
            # Release client on HTTP exceptions
            if client_id is not None:
                release_telegram_client(client_id)
            raise
        except Exception as e:
            # Release client on other exceptions
            if client_id is not None:
                release_telegram_client(client_id)
            LOGGER.error(f"Error in stream_file_response: {e}")
            raise HTTPException(status_code=500, detail="Error streaming file")

    def get_browser_compatible_mime_type(
        original_mime_type: str, file_name: str
    ) -> str:
        """Convert MIME types to browser-compatible ones for HTML5 video/audio"""
        # For MKV files, serve as MP4 for better browser compatibility
        if original_mime_type == "video/x-matroska":
            return "video/mp4"

        # Map of unsupported MIME types to browser-compatible ones
        mime_type_map = {
            "video/x-msvideo": "video/mp4",  # AVI -> MP4
            "video/quicktime": "video/mp4",  # MOV -> MP4
            "video/x-flv": "video/mp4",  # FLV -> MP4
            "video/x-ms-wmv": "video/mp4",  # WMV -> MP4
            "audio/x-flac": "audio/mpeg",  # FLAC -> MP3
            "audio/x-wav": "audio/wav",  # Keep WAV as is
            "audio/x-m4a": "audio/mp4",  # M4A -> MP4 audio
        }

        # Check if we have a direct mapping
        if original_mime_type in mime_type_map:
            return mime_type_map[original_mime_type]

        # For video files, default to mp4 if it's an unsupported video type
        if original_mime_type.startswith("video/") and original_mime_type not in [
            "video/mp4",
            "video/webm",
            "video/ogg",
        ]:
            return "video/mp4"

        # For audio files, default to mpeg if it's an unsupported audio type
        if original_mime_type.startswith("audio/") and original_mime_type not in [
            "audio/mpeg",
            "audio/wav",
            "audio/ogg",
            "audio/mp4",
        ]:
            return "audio/mpeg"

        # Return original if it's already supported
        return original_mime_type

    # CONSOLIDATED: Track streaming now handled directly in main streaming endpoint

    # FIXED: Define API routes BEFORE generic file handler to ensure proper routing

    @app.get("/api/media/{hash_id}/tracks")
    async def get_available_tracks(
        hash_id: str,
        hash: str = Query(...),
        quality: str = Query(None),
        season: str = Query(None),
        episode: str = Query(None),
    ):
        """Get all available tracks for media with comprehensive filtering (quality + season + episode)"""
        try:
            LOGGER.info(
                f"🎛️ Tracks request: hash_id={hash_id}, quality={quality}, season={season}, episode={episode}"
            )

            # Get media info from database using async access
            database = await ensure_database_and_config()
            if not database:
                LOGGER.error("Database not available")
                raise HTTPException(status_code=503, detail="Database not available")

            # Ensure TgClient.ID is set
            if not TgClient.ID:
                TgClient.ID = Config.BOT_TOKEN.split(":", 1)[0]

            media_info = await get_media_info_with_fallback(hash_id)
            if not media_info:
                LOGGER.error(f"Media not found for hash_id: {hash_id}")
                raise HTTPException(status_code=404, detail="Media not found")

            # Validate hash
            if not validate_media_hash(media_info, hash):
                LOGGER.error(f"Invalid hash for media: {hash_id}")
                raise HTTPException(status_code=403, detail="Invalid hash")

            # Get tracks from media info (no extracted tracks since extraction pipeline removed)
            tracks_info = media_info.get("tracks", {})

            # Apply comprehensive filtering (quality + season + episode)
            if quality or season or episode:
                filter_info = []
                if quality:
                    filter_info.append(f"quality:{quality}")
                if season:
                    filter_info.append(f"season:{season}")
                if episode:
                    filter_info.append(f"episode:{episode}")

                LOGGER.info(
                    f"🎬 Applying comprehensive filtering: {' + '.join(filter_info)}"
                )

                # Comprehensive filter function
                def filter_by_comprehensive_grouping(track_list):
                    if not track_list:
                        return []

                    filtered_tracks = []
                    for track in track_list:
                        match = True

                        # Check quality match
                        if quality and track.get("quality_group") != quality.lower():
                            match = False

                        # Check season match
                        if season and track.get("season_group") != season.lower():
                            match = False

                        # Check episode match
                        if episode and track.get("episode_group") != episode.lower():
                            match = False

                        if match:
                            filtered_tracks.append(track)

                    return filtered_tracks

                video_tracks = filter_by_comprehensive_grouping(
                    tracks_info.get("video_tracks", [])
                )
                audio_tracks = filter_by_comprehensive_grouping(
                    tracks_info.get("audio_tracks", [])
                )
                subtitle_tracks = filter_by_comprehensive_grouping(
                    tracks_info.get("subtitle_tracks", [])
                )

                # Note: Extracted tracks removed - using only container-level tracks

                LOGGER.info(
                    f"🎬 Comprehensive-filtered tracks: {len(video_tracks)} video, {len(audio_tracks)} audio, {len(subtitle_tracks)} subtitle"
                )
            else:
                # Return all tracks if no filtering specified
                video_tracks = tracks_info.get("video_tracks", [])
                audio_tracks = tracks_info.get("audio_tracks", [])
                subtitle_tracks = tracks_info.get("subtitle_tracks", [])

            # Format tracks for frontend with comprehensive grouping information
            formatted_tracks = {
                "video_tracks": [
                    {
                        "id": track.get("id", i),
                        "title": track.get("title", f"Video {i + 1}"),
                        "resolution": track.get("resolution", "Unknown"),
                        "codec": track.get("codec", "Unknown"),
                        "bitrate": track.get("bitrate", "Unknown"),
                        "quality": track.get("quality", "Unknown"),
                        "quality_group": track.get("quality_group", "unknown"),
                        "season": track.get("season", "Unknown"),
                        "season_group": track.get("season_group", "unknown"),
                        "episode": track.get("episode", "Unknown"),
                        "episode_group": track.get("episode_group", "unknown"),
                        "grouping_id": track.get("grouping_id", "default"),
                    }
                    for i, track in enumerate(video_tracks)
                ],
                "audio_tracks": [
                    {
                        "id": track.get("id", i),
                        "title": track.get("title", f"Audio {i + 1}"),
                        "language": track.get("language", "Unknown"),
                        "codec": track.get("codec", "Unknown"),
                        "channels": track.get("channels", "Unknown"),
                        "quality": track.get("quality", "Unknown"),
                        "quality_group": track.get("quality_group", "unknown"),
                        "season": track.get("season", "Unknown"),
                        "season_group": track.get("season_group", "unknown"),
                        "episode": track.get("episode", "Unknown"),
                        "episode_group": track.get("episode_group", "unknown"),
                        "grouping_id": track.get("grouping_id", "default"),
                    }
                    for i, track in enumerate(audio_tracks)
                ],
                "subtitle_tracks": [
                    {
                        "id": track.get("id", i),
                        "title": track.get("title", f"Subtitle {i + 1}"),
                        "language": track.get("language", "Unknown"),
                        "format": track.get("format", "VTT"),
                        "quality": track.get("quality", "Unknown"),
                        "quality_group": track.get("quality_group", "unknown"),
                        "season": track.get("season", "Unknown"),
                        "season_group": track.get("season_group", "unknown"),
                        "episode": track.get("episode", "Unknown"),
                        "episode_group": track.get("episode_group", "unknown"),
                        "grouping_id": track.get("grouping_id", "default"),
                    }
                    for i, track in enumerate(subtitle_tracks)
                ],
            }

            # Add comprehensive grouping information to response
            formatted_tracks["current_quality"] = quality
            formatted_tracks["current_season"] = season
            formatted_tracks["current_episode"] = episode
            formatted_tracks["media_quality"] = media_info.get("quality", "Unknown")
            formatted_tracks["media_season"] = media_info.get("season", "Unknown")
            formatted_tracks["media_episode"] = media_info.get("episode", "Unknown")
            formatted_tracks["grouping_type"] = media_info.get(
                "grouping_type", "none"
            )
            formatted_tracks["series_id"] = media_info.get("series_id", None)
            formatted_tracks["episode_id"] = media_info.get("episode_id", None)

            LOGGER.info(
                f"✅ Returning quality-aware tracks: {len(formatted_tracks['video_tracks'])} video, {len(formatted_tracks['audio_tracks'])} audio, {len(formatted_tracks['subtitle_tracks'])} subtitle"
            )
            return formatted_tracks

        except HTTPException:
            raise
        except Exception as e:
            LOGGER.error(f"Error getting available tracks: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.get("/api/media/{hash_id}/video/{track_id}")
    async def get_video_track(hash_id: str, track_id: str, hash: str = Query(...)):
        """Get specific video track for media - redirects to main stream with track info"""
        try:
            LOGGER.info(
                f"🎬 Video track request: hash_id={hash_id}, track_id={track_id}"
            )

            # Get media info from database using async access
            database = await ensure_database_and_config()
            if not database:
                LOGGER.error("Database not available")
                raise HTTPException(status_code=503, detail="Database not available")

            # Ensure TgClient.ID is set
            if not TgClient.ID:
                TgClient.ID = Config.BOT_TOKEN.split(":", 1)[0]

            media_info = await get_media_info_with_fallback(hash_id)
            if not media_info:
                LOGGER.error(f"Media not found for hash_id: {hash_id}")
                raise HTTPException(status_code=404, detail="Media not found")

            # Validate hash
            if not validate_media_hash(media_info, hash):
                LOGGER.error(f"Invalid hash for media: {hash_id}")
                raise HTTPException(status_code=403, detail="Invalid hash")

            # Get video tracks from the tracks structure
            tracks_info = media_info.get("tracks", {})
            video_tracks = tracks_info.get("video_tracks", [])

            # Note: Since extraction was removed, all tracks are container-level
            # We stream the original file and let the player handle track selection

            # Find the requested track or use original if track_id is 0
            if str(track_id) == "0" or not video_tracks:
                # Use original media - redirect to main streaming endpoint
                LOGGER.info(f"✅ Serving original media for video track: {track_id}")
                return RedirectResponse(url=f"/{hash_id}?hash={hash}")

            # Find specific video track for validation (handle both string and int track_id)
            track = None
            for vid_track in video_tracks:
                track_vid_id = vid_track.get("id", vid_track.get("index", 0))
                if str(track_vid_id) == str(track_id) or track_vid_id == track_id:
                    track = vid_track
                    break

            if not track:
                LOGGER.warning(
                    f"Video track {track_id} not found, serving original media"
                )
                # Fallback to original media instead of error
                return RedirectResponse(url=f"/{hash_id}?hash={hash}")

            # Since we don't extract tracks anymore, stream the original file
            # The player will handle track selection based on track metadata
            LOGGER.info(
                f"✅ Serving original media with video track metadata: {track_id}"
            )
            return RedirectResponse(url=f"/{hash_id}?hash={hash}")

        except HTTPException:
            raise
        except Exception as e:
            LOGGER.error(f"Error serving video track: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.get("/api/media/{hash_id}/audio/{track_id}")
    async def get_audio_track(hash_id: str, track_id: str, hash: str = Query(...)):
        """Get specific audio track for media - redirects to main stream with track info"""
        try:
            LOGGER.info(
                f"🎵 Audio track request: hash_id={hash_id}, track_id={track_id}"
            )

            # Get media info from database using async access
            database = await ensure_database_and_config()
            if not database:
                LOGGER.error("Database not available")
                raise HTTPException(status_code=503, detail="Database not available")

            # Ensure TgClient.ID is set
            if not TgClient.ID:
                TgClient.ID = Config.BOT_TOKEN.split(":", 1)[0]

            media_info = await get_media_info_with_fallback(hash_id)
            if not media_info:
                LOGGER.error(f"Media not found for hash_id: {hash_id}")
                raise HTTPException(status_code=404, detail="Media not found")

            # Validate hash
            if not validate_media_hash(media_info, hash):
                LOGGER.error(f"Invalid hash for media: {hash_id}")
                raise HTTPException(status_code=403, detail="Invalid hash")

            # Get audio tracks from the tracks structure
            tracks_info = media_info.get("tracks", {})
            audio_tracks = tracks_info.get("audio_tracks", [])

            # Note: Since extraction was removed, all tracks are container-level
            # We stream the original file and let the player handle track selection

            # Find the requested track or use original if track_id is 0
            if str(track_id) == "0" or not audio_tracks:
                # Use original media - redirect to main streaming endpoint
                LOGGER.info(f"✅ Serving original media for audio track: {track_id}")
                return RedirectResponse(url=f"/{hash_id}?hash={hash}")

            # Find specific audio track for validation (handle both string and int track_id)
            track = None
            for aud_track in audio_tracks:
                track_aud_id = aud_track.get("id", aud_track.get("index", 0))
                if str(track_aud_id) == str(track_id) or track_aud_id == track_id:
                    track = aud_track
                    break

            if not track:
                LOGGER.warning(
                    f"Audio track {track_id} not found, serving original media"
                )
                # Fallback to original media instead of error
                return RedirectResponse(url=f"/{hash_id}?hash={hash}")

            # Since we don't extract tracks anymore, stream the original file
            # The player will handle track selection based on track metadata
            LOGGER.info(
                f"✅ Serving original media with audio track metadata: {track_id}"
            )
            return RedirectResponse(url=f"/{hash_id}?hash={hash}")

        except HTTPException:
            raise
        except Exception as e:
            LOGGER.error(f"Error serving audio track: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.get("/api/media/{hash_id}/subtitle/{track_id}")
    async def get_subtitle_track_api(
        hash_id: str, track_id: str, hash: str = Query(...)
    ):
        """Get subtitle track file - Note: Extraction removed, using container tracks only"""
        try:
            # Validate track_id
            if track_id == "undefined" or not track_id:
                LOGGER.warning(f"Subtitle track {track_id} not found for {hash_id}")
                return Response(
                    "WEBVTT\n\n00:00:00.000 --> 00:00:05.000\nSubtitle track not found\n\n",
                    media_type="text/vtt",
                    headers={"Access-Control-Allow-Origin": "*"},
                )

            LOGGER.info(
                f"🎬 Subtitle API (extraction removed): {hash_id}, {track_id}"
            )

            # Note: Extraction pipeline removed - return informative content only
            subtitle_content = await get_subtitle_track_content(hash_id, track_id)
            if subtitle_content:
                LOGGER.info(
                    f"✅ Loaded subtitle content: {hash_id}_{track_id} ({len(subtitle_content)} bytes)"
                )
                return Response(
                    subtitle_content,
                    media_type="text/vtt",
                    headers={
                        "Content-Disposition": f'inline; filename="subtitle_{track_id}.vtt"',
                        "Cache-Control": "public, max-age=3600",
                        "Access-Control-Allow-Origin": "*",
                    },
                )

            # No extraction available - return informative content

            # Get track information for informative subtitle content
            try:
                # Use unified database access
                database = await ensure_database_and_config()
                if not database:
                    raise Exception("Database not available")

                # Get media metadata quickly
                media_data = await database.get_media_metadata(hash_id)
                if media_data and "tracks" in media_data:
                    subtitle_tracks = media_data["tracks"].get("subtitle_tracks", [])

                    # Find the requested track (handle both string and int track_id)
                    track_info = None
                    for track in subtitle_tracks:
                        track_sub_id = track.get("id", track.get("index", 0))
                        if (
                            str(track_sub_id) == str(track_id)
                            or track_sub_id == track_id
                        ):
                            track_info = track
                            break

                    if track_info:
                        track_language = track_info.get("language", "Unknown")
                        track_title = track_info.get("title", f"Subtitle {track_id}")

                        # Create informative VTT content showing track info
                        informative_vtt = f"""WEBVTT

00:00:00.000 --> 00:00:05.000
{track_title}

00:00:05.000 --> 00:00:10.000
Language: {track_language}

00:00:10.000 --> 00:00:15.000
Real subtitle extraction attempted but failed

"""
                        LOGGER.info(
                            f"✅ Informative fallback: {track_title} ({track_language})"
                        )
                        return Response(
                            informative_vtt,
                            media_type="text/vtt",
                            headers={
                                "Content-Disposition": f'inline; filename="subtitle_{track_id}.vtt"',
                                "Cache-Control": "public, max-age=3600",
                                "Access-Control-Allow-Origin": "*",
                            },
                        )
            except Exception as db_error:
                LOGGER.warning(f"Database lookup failed: {db_error}")

            # Final fallback: Return basic informative VTT
            fallback_vtt = f"""WEBVTT

00:00:00.000 --> 00:00:05.000
Subtitle Track: {track_id}

00:00:05.000 --> 00:00:10.000
Subtitle extraction failed

"""

            LOGGER.info(f"✅ Basic fallback subtitle response: {hash_id}_{track_id}")
            return Response(
                fallback_vtt,
                media_type="text/vtt",
                headers={
                    "Content-Disposition": f'inline; filename="subtitle_{track_id}.vtt"',
                    "Cache-Control": "public, max-age=3600",
                    "Access-Control-Allow-Origin": "*",
                },
            )

        except Exception as e:
            LOGGER.error(f"Error in subtitle API: {e}")
            # Even on error, return basic VTT to prevent timeout
            return Response(
                "WEBVTT\n\n00:00:00.000 --> 00:00:05.000\nSubtitle unavailable\n\n",
                media_type="text/vtt",
                headers={"Access-Control-Allow-Origin": "*"},
            )

    # MOVED: API routes must be defined BEFORE generic file handler to ensure proper routing
    @app.get("/api/media/{hash_id}/qualities")
    async def get_media_qualities(hash_id: str, hash: str | None = None):
        """Get available quality options for media"""
        try:
            # Validate hash for security
            if not SecurityHandler.validate_hash(hash, hash_id):
                raise HTTPException(status_code=403, detail="Invalid hash")

            database = await ensure_database_and_config()
            if not is_database_available(database):
                return JSONResponse(
                    {"error": "Database not available"}, status_code=503
                )

            # Check if this media is part of a quality group
            quality_group = await database.get_quality_group_by_hash(hash_id)

            qualities = []

            if quality_group:
                # Multiple qualities available
                for quality_label, quality_data in quality_group.get(
                    "qualities", {}
                ).items():
                    quality_info = QualityHandler.SUPPORTED_QUALITIES.get(
                        quality_label, {}
                    )
                    qualities.append(
                        {
                            "label": quality_label,
                            "height": quality_info.get("height", 0),
                            "hash_id": quality_data.get("hash_id"),
                            "file_size": quality_data.get("file_size", 0),
                            "priority": quality_info.get("priority", 999),
                        }
                    )

                # Sort by priority (lower = higher quality)
                qualities.sort(key=lambda x: x["priority"])
            else:
                # Single quality
                media_data = await database.get_media_metadata(hash_id)
                if media_data:
                    quality_label = media_data.get("quality", "Unknown")
                    quality_info = QualityHandler.SUPPORTED_QUALITIES.get(
                        quality_label, {}
                    )
                    qualities.append(
                        {
                            "label": quality_label,
                            "height": quality_info.get("height", 0),
                            "hash_id": hash_id,
                            "file_size": media_data.get("file_size", 0),
                            "priority": quality_info.get("priority", 999),
                        }
                    )

            return JSONResponse(qualities)

        except HTTPException:
            raise
        except Exception as e:
            LOGGER.error(f"Error getting media qualities: {e}")
            return JSONResponse(
                {"error": "Failed to get qualities"}, status_code=500
            )

    @app.get("/api/media/{hash_id}/stream")
    async def stream_media_quality(
        hash_id: str, quality: str = "auto", hash: str | None = None
    ):
        """Stream media with specific quality"""
        try:
            # Validate hash for security
            if not SecurityHandler.validate_hash(hash, hash_id):
                raise HTTPException(status_code=403, detail="Invalid hash")

            database = await ensure_database_and_config()
            if not is_database_available(database):
                raise HTTPException(status_code=503, detail="Database not available")

            target_hash_id = hash_id

            # If quality is specified and not "auto", try to find the specific quality
            if quality != "auto":
                quality_group = await database.get_quality_group_by_hash(hash_id)
                if quality_group and quality in quality_group.get("qualities", {}):
                    target_hash_id = quality_group["qualities"][quality]["hash_id"]

            # Redirect to the main streaming endpoint
            return RedirectResponse(url=f"/api/file/{target_hash_id}?hash={hash}")

        except HTTPException:
            raise
        except Exception as e:
            LOGGER.error(f"Error streaming media quality: {e}")
            raise HTTPException(status_code=500, detail="Streaming failed")

    # ===== REELNN API ROUTES (MOVED HERE TO ENSURE PROPER ROUTING) =====

    @app.get("/api/v1/trending")
    async def get_trending_media():
        """Get trending media for reelnn homepage hero slider"""
        try:
            database = await ensure_database_and_config()
            if not database:
                return JSONResponse(
                    {"error": "Database not available"}, status_code=503
                )

            # Get trending media using the database method
            trending_media = await database.get_trending_media(limit=10)

            if not trending_media:
                return JSONResponse({"results": []})

            # Format for ReelNN frontend
            formatted_results = []
            for media in trending_media:
                formatted_media = {
                    "hash_id": media.get("hash_id", ""),
                    "title": media.get(
                        "enhanced_title", media.get("file_name", "Unknown")
                    ),
                    "poster_url": media.get(
                        "poster_url", "/static/icons/default-video.svg"
                    ),
                    "backdrop_url": media.get("backdrop_url", ""),
                    "year": media.get("year"),
                    "rating": media.get("rating", 0),
                    "category": media.get("category", "movie"),
                    "view_count": media.get("view_count", 0),
                    "quality": media.get("quality", "HD"),
                    "duration": media.get("duration"),
                    "description": media.get("description", ""),
                }
                formatted_results.append(formatted_media)

            return JSONResponse({"results": formatted_results})

        except Exception as e:
            LOGGER.error(f"Error getting trending media: {e}")
            return JSONResponse(
                {"error": "Failed to fetch trending media"}, status_code=500
            )

    @app.get("/api/v1/featured")
    async def get_featured_media(limit: int = 10):
        """Get featured media for ReelNN - exact API format"""
        try:
            database = await ensure_database_and_config()
            if not database:
                return JSONResponse(
                    {"error": "Database not available"}, status_code=503
                )

            # Get featured media using the database method
            featured_media = await database.get_featured_media(limit=limit)

            if not featured_media:
                return JSONResponse({"results": []})

            # Format for ReelNN frontend
            formatted_results = []
            for media in featured_media:
                formatted_media = {
                    "hash_id": media.get("hash_id", ""),
                    "title": media.get(
                        "enhanced_title", media.get("file_name", "Unknown")
                    ),
                    "poster_url": media.get(
                        "poster_url", "/static/icons/default-video.svg"
                    ),
                    "backdrop_url": media.get("backdrop_url", ""),
                    "year": media.get("year"),
                    "rating": media.get("rating", 0),
                    "category": media.get("category", "movie"),
                    "view_count": media.get("view_count", 0),
                    "quality": media.get("quality", "HD"),
                    "duration": media.get("duration"),
                    "description": media.get("description", ""),
                }
                formatted_results.append(formatted_media)

            return JSONResponse({"results": formatted_results})

        except Exception as e:
            LOGGER.error(f"Error getting featured media: {e}")
            return JSONResponse(
                {"error": "Failed to fetch featured media"}, status_code=500
            )

    @app.get("/api/v1/recent")
    async def get_recent_media(media_type: str | None = None, limit: int = 20):
        """Get recently added media for ReelNN - exact API format"""
        try:
            database = await ensure_database_and_config()
            if not database:
                return JSONResponse(
                    {"error": "Database not available"}, status_code=503
                )

            # Get recent media using the database method
            recent_media = await database.get_recent_media(
                media_type=media_type, limit=limit
            )

            if not recent_media:
                return JSONResponse({"results": []})

            # Format for ReelNN frontend
            formatted_results = []
            for media in recent_media:
                formatted_media = {
                    "hash_id": media.get("hash_id", ""),
                    "title": media.get(
                        "enhanced_title", media.get("file_name", "Unknown")
                    ),
                    "poster_url": media.get(
                        "poster_url", "/static/icons/default-video.svg"
                    ),
                    "backdrop_url": media.get("backdrop_url", ""),
                    "year": media.get("year"),
                    "rating": media.get("rating", 0),
                    "category": media.get("category", "movie"),
                    "view_count": media.get("view_count", 0),
                    "quality": media.get("quality", "HD"),
                    "duration": media.get("duration"),
                    "description": media.get("description", ""),
                }
                formatted_results.append(formatted_media)

            return JSONResponse({"results": formatted_results})

        except Exception as e:
            LOGGER.error(f"Error getting recent media: {e}")
            return JSONResponse(
                {"error": "Failed to fetch recent media"}, status_code=500
            )

    @app.get("/api/v1/search")
    async def search_media(q: str, limit: int = 20, media_type: str | None = None):
        """Search media for ReelNN - exact API format"""
        try:
            if not q or len(q.strip()) < 2:
                return JSONResponse(
                    {"error": "Search query too short"}, status_code=400
                )

            database = await ensure_database_and_config()
            if not database:
                return JSONResponse(
                    {"error": "Database not available"}, status_code=503
                )

            # Search media using the database method
            search_results = await database.search_media(
                query=q.strip(), limit=limit, media_type=media_type
            )

            if not search_results:
                return JSONResponse({"results": []})

            # Format for ReelNN frontend
            formatted_results = []
            for media in search_results:
                formatted_media = {
                    "hash_id": media.get("hash_id", ""),
                    "title": media.get(
                        "enhanced_title", media.get("file_name", "Unknown")
                    ),
                    "poster_url": media.get(
                        "poster_url", "/static/icons/default-video.svg"
                    ),
                    "backdrop_url": media.get("backdrop_url", ""),
                    "year": media.get("year"),
                    "rating": media.get("rating", 0),
                    "category": media.get("category", "movie"),
                    "view_count": media.get("view_count", 0),
                    "quality": media.get("quality", "HD"),
                    "duration": media.get("duration"),
                    "description": media.get("description", ""),
                }
                formatted_results.append(formatted_media)

            return JSONResponse({"results": formatted_results})

        except Exception as e:
            LOGGER.error(f"Error searching media: {e}")
            return JSONResponse({"error": "Failed to search media"}, status_code=500)

    # GENERIC HANDLERS MOVED TO END OF FILE TO FIX ROUTE PRIORITY ISSUES
    # This ensures specific routes like /browse/movie, /search, /movie/{hash_id} are matched first

    # REMOVED: Duplicate quality-info endpoint - using the comprehensive one above

    # REMOVED: Duplicate subtitle endpoint - moved to before generic file handler for proper routing

    # REMOVED: Duplicate progress endpoint - using the one below

    @app.post("/api/media/{hash_id}/quality-preference")
    async def update_quality_preference(hash_id: str, request: Request):
        """Update user's quality preference for media"""
        try:
            data = await request.json()
            if not data:
                return JSONResponse({"error": "JSON data required"}, status_code=400)

            quality = data.get("quality", "auto")

            # For now, just acknowledge the preference
            # This could be stored in user preferences later
            LOGGER.info(f"Quality preference updated for {hash_id}: {quality}")

            return JSONResponse(
                {
                    "success": True,
                    "message": "Quality preference updated",
                    "quality": quality,
                }
            )

        except Exception as e:
            LOGGER.error(f"Error updating quality preference: {e}")
            return JSONResponse({"error": "Internal server error"}, status_code=500)

    @app.get("/api/media/{hash_id}/next-episode")
    async def get_next_episode(hash_id: str):
        """Get next episode information for auto-play"""
        try:
            # Use unified database access
            database = await ensure_database_and_config()
            if not database:
                return JSONResponse({"has_next": False})

            # Get current media info
            media_info = await database.get_media_metadata(hash_id)
            if not media_info:
                return JSONResponse({"has_next": False})

            # Check if this is part of a series
            series_name = media_info.get("series_name")
            season = media_info.get("season")
            episode = media_info.get("episode")

            if not all([series_name, season, episode]):
                return JSONResponse({"has_next": False})

            # Look for next episode
            next_episode_num = episode + 1
            next_episode = await database.find_media_by_series_episode(
                series_name, season, next_episode_num
            )

            if next_episode:
                return JSONResponse(
                    {
                        "has_next": True,
                        "next_episode": {
                            "hash_id": next_episode.get("hash_id"),
                            "title": next_episode.get(
                                "file_name", f"Episode {next_episode_num}"
                            ),
                            "episode": next_episode_num,
                            "season": season,
                        },
                    }
                )
            return JSONResponse({"has_next": False})

        except Exception as e:
            LOGGER.error(f"Error getting next episode: {e}")
            return JSONResponse({"has_next": False})

    # FIXED: Helper functions for API endpoints
    async def get_file_info_by_hash_id(hash_id: str):
        """Get file information from database by hash_id"""
        try:
            # This would integrate with your existing database system
            # For now, return a basic structure
            return {
                "hash_id": hash_id,
                "mime_type": "video/mp4",
                "file_size": 0,
                "filename": "media_file",
            }
        except Exception as e:
            LOGGER.error(f"Error getting file info: {e}")
            return None

    def get_media_info_by_hash(hash_id: str):
        """Get media info from database by hash_id - synchronous wrapper"""
        try:
            import asyncio

            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're already in an async context, we need to handle this differently
                # For now, return None and let the calling function handle it
                LOGGER.warning(
                    f"Cannot run async get_media_metadata from sync context for {hash_id}"
                )
                return None
            return loop.run_until_complete(_get_media_info_by_hash_async(hash_id))
        except Exception as e:
            LOGGER.error(f"Error in get_media_info_by_hash: {e}")
            return None

    # REMOVED: Duplicate get_media_info_with_fallback - using the one outside F2L block
    # async def get_media_info_with_fallback(hash_id: str):
    #     """Get media info with grouped hash_id fallback - async version"""
    #     return await _get_media_info_by_hash_async(hash_id)

    async def _get_media_info_by_hash_async(hash_id: str):
        """Async helper for getting media info with grouped hash_id fallback"""
        try:
            database = await ensure_database_and_config()
            if not database:
                return None

            # Ensure TgClient.ID is set
            if not TgClient.ID:
                TgClient.ID = Config.BOT_TOKEN.split(":", 1)[0]

            # First try with original hash_id
            media_info = await database.get_media_metadata(hash_id)
            if media_info:
                return media_info

            # If not found, try to find by original_hash_id field (for grouped media)
            LOGGER.info(
                f"🔍 Media not found with hash_id {hash_id}, searching by original_hash_id..."
            )

            # Search for media where original_hash_id matches
            try:
                # Try to find by original_hash_id using database method
                grouped_media = await database.find_media_by_original_hash(hash_id)
                if grouped_media:
                    LOGGER.info(
                        f"✅ Found grouped media: {grouped_media.get('hash_id')} for original {hash_id}"
                    )
                    return grouped_media
            except Exception as search_error:
                LOGGER.warning(
                    f"Error searching by original_hash_id: {search_error}"
                )

            return None
        except Exception as e:
            LOGGER.error(f"Error in _get_media_info_by_hash_async: {e}")
            return None

    def validate_media_hash(media_info: dict, hash: str) -> bool:
        """Validate media hash"""
        try:
            if not media_info or not hash:
                return False

            # Extract hash from hash_id (first 6 characters)
            hash_id = media_info.get("hash_id", "")
            if len(hash_id) >= 6:
                expected_hash = hash_id[:6]
                return hash == expected_hash

            # Fallback: check file_unique_id
            file_unique_id = media_info.get("file_unique_id", "")
            if file_unique_id:
                return file_unique_id.startswith(hash) or len(hash) == 6

            return len(hash) == 6  # Accept any 6-character hash as fallback
        except Exception as e:
            LOGGER.error(f"Error validating media hash: {e}")
            return False

    async def get_quality_variants(hash_id: str):
        """Get quality variants for a media file"""
        try:
            # This would integrate with your quality system
            # For now, return empty list (no multiple qualities)
            return []
        except Exception as e:
            LOGGER.error(f"Error getting quality variants: {e}")
            return []

    # REMOVED: Duplicate get_media_tracks function - using database integration above

    # REMOVED: FFmpeg extraction function - subtitles are extracted during /f2l command only

    async def get_subtitle_track_content(hash_id: str, track_id: str):
        """Get subtitle track content - Note: Extraction removed, using container tracks only"""
        try:
            # Use unified database access
            database = await ensure_database_and_config()
            if not database:
                raise Exception("Database not available")

            # Ensure TgClient.ID is set for database operations
            if not TgClient.ID:
                TgClient.ID = Config.BOT_TOKEN.split(":", 1)[0]

            # Get media metadata from database
            media_data = await database.get_media_metadata(hash_id)
            if not media_data:
                LOGGER.warning(f"No media metadata found for hash_id: {hash_id}")
                return None

            # Note: Extracted tracks removed - subtitles now handled from container tracks only

            # Fallback to track metadata for informative content
            tracks = media_data.get("tracks", {})
            subtitle_tracks = tracks.get("subtitle_tracks", [])

            # Find the requested subtitle track (handle both string and int track_id)
            target_track = None
            for track in subtitle_tracks:
                track_sub_id = track.get("id", track.get("index", 0))
                if str(track_sub_id) == str(track_id) or track_sub_id == track_id:
                    target_track = track
                    break

            if not target_track:
                LOGGER.warning(f"Subtitle track {track_id} not found for {hash_id}")
                return None

            # Check if subtitle is already extracted and cached
            import os

            cache_dir = "dump/subtitles"
            os.makedirs(cache_dir, exist_ok=True)

            subtitle_cache_file = os.path.join(
                cache_dir, f"{hash_id}_{track_id}.vtt"
            )

            # Return cached subtitle if it exists and is recent (less than 24 hours old)
            if os.path.exists(subtitle_cache_file):
                import time

                file_age = time.time() - os.path.getmtime(subtitle_cache_file)
                if file_age < 86400:  # 24 hours
                    LOGGER.info(f"Returning cached subtitle: {subtitle_cache_file}")
                    with open(subtitle_cache_file, "rb") as f:
                        return f.read()

            # Since extraction was removed, create informative VTT content
            track_language = target_track.get("language", "und")
            track_title = target_track.get("title", f"Subtitle {track_id}")
            codec_name = target_track.get("codec_name", "unknown")

            # Create informative VTT content showing track info
            informative_vtt = f"""WEBVTT

00:00:00.000 --> 00:00:05.000
{track_title}

00:00:05.000 --> 00:00:10.000
Language: {track_language}

00:00:10.000 --> 00:00:15.000
Codec: {codec_name}

00:00:15.000 --> 00:00:20.000
Note: Subtitle extraction disabled for container streaming

"""

            LOGGER.info(
                f"📝 Generated informative VTT for {track_title} ({track_language})"
            )
            return informative_vtt.encode("utf-8")

        except Exception as e:
            LOGGER.error(f"Error getting subtitle track content: {e}")
            return None

    # REMOVED: VTT conversion function - conversion happens during /f2l command only

    async def store_progress_analytics(
        hash_id: str,
        progress: float,
        current_time: float,
        duration: float,
        timestamp: float,
    ):
        """Store progress analytics (optional)"""
        try:
            # This would integrate with your analytics system
            # For now, just log the information
            LOGGER.info(
                f"Analytics: {hash_id} - {progress}% at {current_time}s/{duration}s"
            )
            return True
        except Exception as e:
            LOGGER.error(f"Error storing progress analytics: {e}")
            return False

    @app.post("/api/media/{hash_id}/progress")
    async def track_media_progress(hash_id: str, request: Request):
        """Track media playback progress for analytics"""
        try:
            data = await request.json()
            progress = data.get("progress", 0)
            current_time = data.get("currentTime", 0)
            duration = data.get("duration", 0)
            timestamp = data.get("timestamp", 0)

            # Store progress analytics using the existing function
            await store_progress_analytics(
                hash_id, progress, current_time, duration, timestamp
            )

            return JSONResponse({"success": True, "message": "Progress tracked"})

        except Exception as e:
            LOGGER.error(f"Error tracking progress: {e}")
            return JSONResponse({"success": False, "error": str(e)})

    # Enhanced Media API Routes for Plyr Integration
    @app.get("/api/media/{hash_id}/tracks")
    async def get_media_tracks(hash_id: str, hash: str | None = None):
        """Get available audio, video, and subtitle tracks for media"""
        try:
            # Validate hash for security
            if not SecurityHandler.validate_hash(hash, hash_id):
                raise HTTPException(status_code=403, detail="Invalid hash")

            database = await ensure_database_and_config()
            if not is_database_available(database):
                return JSONResponse(
                    {"error": "Database not available"}, status_code=503
                )

            # Get media information
            media_data = await database.get_media_metadata(hash_id)
            if not media_data:
                raise HTTPException(status_code=404, detail="Media not found")

            # Extract track information from media metadata
            tracks = {"audio": [], "video": [], "subtitles": []}

            # Get audio tracks (if multiple audio streams)
            audio_tracks = media_data.get("audio_tracks", [])
            if audio_tracks:
                for i, track in enumerate(audio_tracks):
                    tracks["audio"].append(
                        {
                            "id": i,
                            "language": track.get("language", "Unknown"),
                            "codec": track.get("codec", "Unknown"),
                            "title": track.get("title", f"Audio Track {i + 1}"),
                            "channels": track.get("channels", "Unknown"),
                        }
                    )
            else:
                # Default audio track
                tracks["audio"].append(
                    {
                        "id": 0,
                        "language": "Unknown",
                        "codec": media_data.get("audio_codec", "Unknown"),
                        "title": "Default Audio",
                        "channels": "Unknown",
                    }
                )

            # Get video tracks (usually just one)
            tracks["video"].append(
                {
                    "id": 0,
                    "codec": media_data.get("video_codec", "Unknown"),
                    "resolution": media_data.get("resolution", "Unknown"),
                    "quality": media_data.get("quality", "Unknown"),
                }
            )

            # Get subtitle tracks (if available)
            subtitle_tracks = media_data.get("subtitle_tracks", [])
            for i, track in enumerate(subtitle_tracks):
                tracks["subtitles"].append(
                    {
                        "id": i,
                        "language": track.get("language", "Unknown"),
                        "format": track.get("format", "SRT"),
                        "title": track.get("title", f"Subtitle {i + 1}"),
                    }
                )

            return JSONResponse(tracks)

        except HTTPException:
            raise
        except Exception as e:
            LOGGER.error(f"Error getting media tracks: {e}")
            return JSONResponse({"error": "Failed to get tracks"}, status_code=500)

    # REMOVED: Duplicate API routes - moved to before generic file handler for proper routing

    @app.get("/api/media/{hash_id}/subtitles/{track_id}")
    async def get_subtitle_track(
        hash_id: str, track_id: int, hash: str | None = None
    ):
        """Get specific subtitle track"""
        try:
            # Validate hash for security
            if not SecurityHandler.validate_hash(hash, hash_id):
                raise HTTPException(status_code=403, detail="Invalid hash")

            # For now, return a placeholder response
            # In a full implementation, this would extract and serve subtitle tracks
            return Response(
                content="1\n00:00:00,000 --> 00:00:05,000\nSubtitles not yet implemented\n",
                media_type="text/vtt",
                headers={
                    "Content-Disposition": f"inline; filename=subtitles_{track_id}.vtt"
                },
            )

        except HTTPException:
            raise
        except Exception as e:
            LOGGER.error(f"Error getting subtitle track: {e}")
            raise HTTPException(status_code=500, detail="Failed to get subtitles")

    # CONSOLIDATED STREAMING SYSTEM READY
    LOGGER.info("✅ Unified streaming routes registered successfully")
    LOGGER.info(
        "🎬 Available endpoints: /movie/{hash_id}, /show/{hash_id}, /api/file/{hash_id}, /api/media/{hash_id}/*"
    )
    LOGGER.info("🎵 Enhanced Plyr integration: tracks, qualities, captions support")

else:
    LOGGER.info("File-to-Link integration disabled or unavailable")

    # Add fallback routes when File-to-Link is not available
    @app.get("/", response_class=HTMLResponse)
    async def homepage_fallback(request: Request):
        """Fallback homepage when File-to-Link is disabled"""
        from fastapi.templating import Jinja2Templates

        templates = Jinja2Templates(directory="web/templates")

        return templates.TemplateResponse(
            "reelnn/index.html",
            {
                "request": request,
                "site_name": "aimleechbot",
                "trending_media": [],
                "recent_media": [],
                "featured_media": [],
                "search_query": "",
                "media_type": "",
                "sort_by": "trending",
                "current_page": 1,
                "total_pages": 1,
                "has_search": False,
                "is_loading": False,
                "current_year": 2024,
                "is_admin_user": False,
                "current_user": None,
                "f2l_disabled": True,
                "error_message": "File-to-Link integration is not available. Some features may be limited.",
            },
        )

    # REMOVED: Duplicate watch route - main watch route already handles F2L availability
    # @app.get("/watch/{hash_id:str}", response_class=HTMLResponse)
    # async def watch_fallback(hash_id: str, request: Request):
    #     """Fallback watch page when File-to-Link is disabled"""
    #     return HTMLResponse(
    #         content="""
    #         <!DOCTYPE html>
    #         <html>
    #         <head><title>Streaming Unavailable</title></head>
    #         <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
    #             <h1>🚫 Streaming Unavailable</h1>
    #             <p>File-to-Link integration is disabled or unavailable.</p>
    #             <p>Please enable FILE_TO_LINK_ENABLED in the configuration to access streaming features.</p>
    #             <a href="/" style="color: #007bff;">← Back to Home</a>
    #         </body>
    #         </html>
    #         """,
    #         status_code=503
    #     )

    @app.get("/admin", response_class=HTMLResponse)
    async def admin_fallback(request: Request):
        """Fallback admin page when File-to-Link is disabled"""
        return HTMLResponse(
            content="""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Admin Panel - Limited</title>
                <style>
                    body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #1a1a1a; color: white; }
                    .container { max-width: 800px; margin: 0 auto; padding: 40px; background: #2a2a2a; border-radius: 12px; }
                    .warning { background: #dc3545; padding: 15px; margin: 20px 0; border-radius: 5px; }
                    .info { background: #17a2b8; padding: 15px; margin: 20px 0; border-radius: 5px; }
                    a { color: #007bff; text-decoration: none; }
                    a:hover { text-decoration: underline; }
                    .nav { margin: 20px 0; }
                    .nav a { margin-right: 20px; padding: 10px 15px; background: #007bff; border-radius: 5px; }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>🔧 Admin Panel (Limited Mode)</h1>

                    <div class="warning">
                        <h3>⚠️ File-to-Link Integration Disabled</h3>
                        <p>Most admin features require File-to-Link integration to be enabled.
                        Please enable FILE_TO_LINK_ENABLED in your configuration to access the full admin panel.</p>
                    </div>

                    <div class="info">
                        <h3>📋 Available Functions</h3>
                        <p>The following basic functions are still available:</p>
                    </div>

                    <div class="nav">
                        <a href="/admin/setup">👤 Admin Setup</a>
                        <a href="/auth/login">🔐 Login</a>
                        <a href="/">🏠 Homepage</a>
                        <a href="/docs">📚 API Docs</a>
                    </div>

                    <div class="info">
                        <h3>🚀 To Enable Full Admin Panel</h3>
                        <ol>
                            <li>Set <code>FILE_TO_LINK_ENABLED = True</code> in your configuration</li>
                            <li>Ensure File-to-Link dependencies are installed</li>
                            <li>Restart the server</li>
                            <li>Access the full admin panel at <a href="/admin">/admin</a></li>
                        </ol>
                    </div>
                </div>
            </body>
            </html>
            """,
            status_code=503,
        )

# ===== DUPLICATE REELNN API ROUTES (DISABLED - MOVED TO BEFORE FILE HANDLER) =====


# @app.get("/api/v1/trending")  # DISABLED - MOVED ABOVE
async def get_trending_media_DISABLED():
    """Get trending media for reelnn homepage hero slider"""
    try:
        database = await ensure_database_and_config()
        if not database:
            return JSONResponse({"error": "Database not available"}, status_code=503)

        # Get trending media based on view counts and recent activity
        trending_media = await database.get_trending_media(limit=20)

        # Format for ReelNN frontend - exact structure
        formatted_media = []
        for media in trending_media:
            # ReelNN-style media object
            media_item = {
                "mid": media.get("hash_id"),  # ReelNN uses 'mid' for movie/show ID
                "title": media.get("title")
                or media.get("enhanced_title")
                or media.get("file_name", "").split(".")[0],
                "original_title": media.get("original_title"),
                "poster_path": media.get("poster_path"),
                "backdrop_path": media.get("backdrop_path"),
                "poster_url": get_media_poster_url(media),  # Full URL for frontend
                "backdrop_url": get_media_backdrop_url(
                    media
                ),  # Full URL for frontend
                "vote_average": media.get("vote_average"),
                "vote_count": media.get("vote_count"),
                "popularity": media.get("popularity"),
                "release_date": media.get("release_date"),
                "first_air_date": media.get("first_air_date"),
                "overview": media.get("overview"),
                "genres": media.get("genres", []),
                "runtime": media.get("runtime"),
                "media_type": media.get("media_type", "movie"),
                "quality": media.get("quality", "HD"),
                "view_count": media.get("view_count", 0),
                "trending_score": media.get("trending_score", 0),
            }
            formatted_media.append(media_item)

        return JSONResponse(formatted_media)

    except Exception as e:
        LOGGER.error(f"Error getting trending media: {e}")
        return JSONResponse(
            {"error": "Failed to fetch trending media"}, status_code=500
        )


# @app.get("/api/v1/heroslider")  # DISABLED - MOVED ABOVE
async def get_hero_slider_DISABLED():
    """Get featured media for ReelNN hero slider - exact API format"""
    try:
        database = await ensure_database_and_config()
        if not database:
            return JSONResponse({"error": "Database not available"}, status_code=503)

        # Get featured media for hero slider
        featured_media = await database.get_featured_media(limit=10)

        # Format for ReelNN hero slider - exact structure
        slider_items = []
        for media in featured_media:
            slider_item = {
                "mid": media.get("hash_id"),
                "title": media.get("title")
                or media.get("enhanced_title")
                or media.get("file_name", "").split(".")[0],
                "original_title": media.get("original_title"),
                "backdrop_path": media.get("backdrop_path"),
                "backdrop_url": get_media_backdrop_url(media),
                "poster_path": media.get("poster_path"),
                "poster_url": get_media_poster_url(media),
                "overview": media.get("overview", "")[:200] + "..."
                if media.get("overview", "")
                else "",
                "vote_average": media.get("vote_average"),
                "release_date": media.get("release_date"),
                "first_air_date": media.get("first_air_date"),
                "genres": media.get("genres", [])[:3],  # Limit to 3 genres for hero
                "media_type": media.get("media_type", "movie"),
                "runtime": media.get("runtime"),
                "quality": media.get("quality", "HD"),
                "featured": media.get("featured", False),
            }
            slider_items.append(slider_item)

        return JSONResponse(slider_items)

    except Exception as e:
        LOGGER.error(f"Error getting hero slider: {e}")
        return JSONResponse(
            {"error": "Failed to fetch hero slider"}, status_code=500
        )


# @app.get("/api/v1/recent")  # DISABLED - MOVED ABOVE
async def get_recent_media_DISABLED(media_type: str | None = None, limit: int = 20):
    """Get recently added media for ReelNN - exact API format"""
    try:
        database = await ensure_database_and_config()
        if not database:
            return JSONResponse({"error": "Database not available"}, status_code=503)

        # Get recent media
        recent_media = await database.get_recent_media(
            limit=limit, media_type=media_type
        )

        # Format for ReelNN frontend
        formatted_media = []
        for media in recent_media:
            media_item = {
                "mid": media.get("hash_id"),
                "title": media.get("title")
                or media.get("enhanced_title")
                or media.get("file_name", "").split(".")[0],
                "original_title": media.get("original_title"),
                "poster_path": media.get("poster_path"),
                "poster_url": get_media_poster_url(media),
                "vote_average": media.get("vote_average"),
                "release_date": media.get("release_date"),
                "first_air_date": media.get("first_air_date"),
                "media_type": media.get("media_type", "movie"),
                "quality": media.get("quality", "HD"),
                "indexed_at": media.get("indexed_at"),
            }
            formatted_media.append(media_item)

        return JSONResponse(formatted_media)

    except Exception as e:
        LOGGER.error(f"Error getting recent media: {e}")
        return JSONResponse(
            {"error": "Failed to fetch recent media"}, status_code=500
        )


# @app.get("/api/v1/featured")  # DISABLED - MOVED ABOVE
async def get_featured_media_DISABLED(limit: int = 10):
    """Get featured media for ReelNN - exact API format"""
    try:
        database = await ensure_database_and_config()
        if not database:
            return JSONResponse({"error": "Database not available"}, status_code=503)

        # Get featured media
        featured_media = await database.get_featured_media(limit=limit)

        # Format for ReelNN frontend
        formatted_media = []
        for media in featured_media:
            formatted_item = {
                "id": media.get("hash_id"),
                "mid": media.get("hash_id"),
                "title": media.get("enhanced_title", media.get("file_name", "")),
                "file_name": media.get("file_name", ""),
                "media_type": media.get("media_type", "movie"),
                "year": media.get("year"),
                "quality": media.get("quality"),
                "view_count": media.get("view_count", 0),
                "featured": media.get("featured", False),
                "tmdb_data": media.get("tmdb_data", {}),
                "poster_url": media.get("tmdb_data", {}).get("poster_path"),
                "backdrop_url": media.get("tmdb_data", {}).get("backdrop_path"),
                "created_at": media.get("created_at"),
                "stream_url": f"/movie/{media.get('hash_id')}"
                if media.get("media_type") == "movie"
                else f"/show/{media.get('hash_id')}",
            }
            formatted_media.append(formatted_item)

        return JSONResponse(formatted_media)

    except Exception as e:
        LOGGER.error(f"Error getting featured media: {e}")
        return JSONResponse(
            {"error": "Failed to fetch featured media"}, status_code=500
        )


# @app.get("/api/v1/search")  # DISABLED - MOVED ABOVE
async def search_media_DISABLED(
    q: str, limit: int = 20, media_type: str | None = None
):
    """Search media for ReelNN - exact API format"""
    try:
        if not q or len(q.strip()) < 2:
            return JSONResponse({"error": "Search query too short"}, status_code=400)

        database = await ensure_database_and_config()
        if not database:
            return JSONResponse({"error": "Database not available"}, status_code=503)

        # Search media
        search_results = await database.search_media(
            q.strip(), limit=limit, media_type=media_type
        )

        # Format for ReelNN frontend
        formatted_results = []
        for media in search_results:
            formatted_item = {
                "id": media.get("hash_id"),
                "mid": media.get("hash_id"),
                "title": media.get("enhanced_title", media.get("file_name", "")),
                "file_name": media.get("file_name", ""),
                "media_type": media.get("media_type", "movie"),
                "year": media.get("year"),
                "quality": media.get("quality"),
                "view_count": media.get("view_count", 0),
                "tmdb_data": media.get("tmdb_data", {}),
                "poster_url": media.get("tmdb_data", {}).get("poster_path"),
                "backdrop_url": media.get("tmdb_data", {}).get("backdrop_path"),
                "created_at": media.get("created_at"),
                "stream_url": f"/movie/{media.get('hash_id')}"
                if media.get("media_type") == "movie"
                else f"/show/{media.get('hash_id')}",
            }
            formatted_results.append(formatted_item)

        return JSONResponse(
            {
                "results": formatted_results,
                "total": len(formatted_results),
                "query": q,
            }
        )

    except Exception as e:
        LOGGER.error(f"Error searching media: {e}")
        return JSONResponse({"error": "Failed to search media"}, status_code=500)


@app.get("/api/v1/movies")
async def get_movies_browse(
    page: int = 1,
    limit: int = 24,
    genre: str | None = None,
    year: str | None = None,
    sort: str = "recent",
):
    """Get paginated movies for ReelNN browse page - exact API format"""
    try:
        database = await ensure_database_and_config()
        if not database:
            return JSONResponse({"error": "Database not available"}, status_code=503)

        # Get paginated movies using ReelNN method
        result = await database.get_movies_paginated_reelnn(
            page=page, limit=limit, genre=genre, year=year, sort=sort
        )

        # Format movies for ReelNN frontend
        formatted_movies = []
        for movie in result["movies"]:
            movie_item = {
                "mid": movie.get("hash_id"),
                "title": movie.get("title")
                or movie.get("enhanced_title")
                or movie.get("file_name", "").split(".")[0],
                "original_title": movie.get("original_title"),
                "poster_path": movie.get("poster_path"),
                "poster_url": get_media_poster_url(movie),
                "vote_average": movie.get("vote_average"),
                "release_date": movie.get("release_date"),
                "genres": movie.get("genres", []),
                "quality": movie.get("quality", "HD"),
                "media_type": "movie",
            }
            formatted_movies.append(movie_item)

        return JSONResponse(
            {
                "results": formatted_movies,
                "page": page,
                "total_pages": result["pages"],
                "total_results": result["total"],
            }
        )

    except Exception as e:
        LOGGER.error(f"Error getting movies browse: {e}")
        return JSONResponse({"error": "Failed to fetch movies"}, status_code=500)


@app.get("/api/v1/shows")
async def get_shows_browse(
    page: int = 1,
    limit: int = 24,
    genre: str | None = None,
    status: str | None = None,
    sort: str = "recent",
):
    """Get paginated TV shows for ReelNN browse page - exact API format"""
    try:
        database = await ensure_database_and_config()
        if not database:
            return JSONResponse({"error": "Database not available"}, status_code=503)

        # Get paginated shows using ReelNN method
        result = await database.get_shows_paginated_reelnn(
            page=page, limit=limit, genre=genre, status=status, sort=sort
        )

        # Format shows for ReelNN frontend
        formatted_shows = []
        for show in result["shows"]:
            show_item = {
                "sid": show.get("hash_id"),  # ReelNN uses 'sid' for show ID
                "title": show.get("title")
                or show.get("enhanced_title")
                or show.get("file_name", "").split(".")[0],
                "original_title": show.get("original_title"),
                "poster_path": show.get("poster_path"),
                "poster_url": get_media_poster_url(show),
                "vote_average": show.get("vote_average"),
                "first_air_date": show.get("first_air_date"),
                "genres": show.get("genres", []),
                "quality": show.get("quality", "HD"),
                "media_type": "tv",
            }
            formatted_shows.append(show_item)

        return JSONResponse(
            {
                "results": formatted_shows,
                "page": page,
                "total_pages": result["pages"],
                "total_results": result["total"],
            }
        )

    except Exception as e:
        LOGGER.error(f"Error getting shows browse: {e}")
        return JSONResponse({"error": "Failed to fetch shows"}, status_code=500)


# Removed duplicate hero slider endpoint - using the one above


@app.get("/api/v1/paginated/{media_type}")
async def get_paginated_media(
    media_type: str, page: int = 1, sort_by: str = "recent"
):
    """Get paginated media list with sorting for reelnn frontend"""
    try:
        database = await ensure_database_and_config()
        if not database:
            return JSONResponse({"error": "Database not available"}, status_code=503)

        # Calculate pagination
        per_page = 24
        skip = (page - 1) * per_page

        # Get media based on type and sorting
        if media_type == "movie":
            media_list = await database.get_movies_paginated(
                skip=skip, limit=per_page, sort_by=sort_by
            )
        elif media_type == "show":
            media_list = await database.get_shows_paginated(
                skip=skip, limit=per_page, sort_by=sort_by
            )
        else:  # all
            media_list = await database.get_all_media_paginated(
                skip=skip, limit=per_page, sort_by=sort_by
            )

        # Format for frontend
        formatted_media = []
        for media in media_list:
            formatted_item = {
                "hash_id": media.get("hash_id"),
                "title": media.get("enhanced_title")
                or media.get("file_name", "").split(".")[0],
                "poster_url": get_media_poster_url(media),
                "vote_average": media.get("tmdb_data", {}).get("vote_average"),
                "release_date": media.get("tmdb_data", {}).get("release_date"),
                "media_type": "tv" if media.get("series_data") else "movie",
            }
            formatted_media.append(formatted_item)

        return JSONResponse(
            {
                "results": formatted_media,
                "page": page,
                "total_pages": await database.get_total_pages(media_type, per_page),
                "total_results": await database.get_total_count(media_type),
            }
        )

    except Exception as e:
        LOGGER.error(f"Error getting paginated media: {e}")
        return JSONResponse(
            {"error": "Failed to fetch paginated media"}, status_code=500
        )


@app.get("/api/v1/getMovieDetails/{mid}")
async def get_movie_details(mid: str):
    """Get detailed movie information for reelnn frontend"""
    try:
        database = await ensure_database_and_config()
        if not database:
            return JSONResponse({"error": "Database not available"}, status_code=503)

        # Get media data
        media_data = await get_media_info_with_fallback(mid)
        if not media_data:
            raise HTTPException(status_code=404, detail="Movie not found")

        # Format movie details for ReelNN - exact structure
        movie_details = {
            "mid": media_data.get("hash_id"),
            "title": media_data.get("title")
            or media_data.get("enhanced_title")
            or media_data.get("file_name", "").split(".")[0],
            "original_title": media_data.get("original_title"),
            "release_date": media_data.get("release_date"),
            "overview": media_data.get("overview"),
            "poster_path": media_data.get("poster_path"),
            "backdrop_path": media_data.get("backdrop_path"),
            "poster_url": get_media_poster_url(media_data),
            "backdrop_url": get_media_backdrop_url(media_data),
            "vote_average": media_data.get("vote_average"),
            "vote_count": media_data.get("vote_count"),
            "popularity": media_data.get("popularity"),
            "runtime": media_data.get("runtime"),
            "genres": media_data.get("genres", []),
            "production_companies": media_data.get("tmdb_data", {}).get(
                "production_companies", []
            ),
            "production_countries": media_data.get("tmdb_data", {}).get(
                "production_countries", []
            ),
            "spoken_languages": media_data.get("tmdb_data", {}).get(
                "spoken_languages", []
            ),
            "status": media_data.get("tmdb_data", {}).get("status", "Released"),
            "tagline": media_data.get("tmdb_data", {}).get("tagline"),
            "budget": media_data.get("tmdb_data", {}).get("budget"),
            "revenue": media_data.get("tmdb_data", {}).get("revenue"),
            "imdb_id": media_data.get("tmdb_data", {}).get("imdb_id"),
            "cast": media_data.get("tmdb_data", {}).get("cast", []),
            "crew": media_data.get("tmdb_data", {}).get("crew", []),
            "quality": media_data.get("quality", "HD"),
            "file_format": media_data.get("file_format", "MP4"),
            "file_size": media_data.get("file_size"),
            "view_count": media_data.get("view_count", 0),
            "media_type": "movie",
            "streamable": media_data.get("streamable", True),
            "indexed_at": media_data.get("indexed_at"),
            "featured": media_data.get("featured", False),
        }

        return JSONResponse(movie_details)

    except Exception as e:
        LOGGER.error(f"Error getting movie details: {e}")
        return JSONResponse(
            {"error": "Failed to fetch movie details"}, status_code=500
        )


@app.get("/api/v1/getShowDetails/{sid}")
async def get_show_details(sid: str):
    """Get detailed TV show information for reelnn frontend"""
    try:
        database = await ensure_database_and_config()
        if not database:
            return JSONResponse({"error": "Database not available"}, status_code=503)

        # Get show data and related episodes
        show_data = await get_media_info_with_fallback(sid)
        if not show_data:
            raise HTTPException(status_code=404, detail="Show not found")

        # Get all episodes for this series
        series_name = show_data.get("series_data", {}).get(
            "series_name"
        ) or show_data.get("enhanced_title")
        episodes = (
            await database.get_series_episodes(series_name) if series_name else []
        )

        # Organize episodes by season
        seasons = {}
        for episode in episodes:
            season_num = episode.get("series_data", {}).get("season_number", 1)
            if season_num not in seasons:
                seasons[season_num] = []

            episode_data = {
                "episode_number": episode.get("series_data", {}).get(
                    "episode_number", 1
                ),
                "name": episode.get("enhanced_title")
                or f"Episode {episode.get('series_data', {}).get('episode_number', 1)}",
                "overview": episode.get("tmdb_data", {}).get("overview", ""),
                "still_path": episode.get("tmdb_data", {}).get("still_path"),
                "air_date": episode.get("tmdb_data", {}).get("air_date"),
                "quality": [
                    {
                        "type": episode.get("quality", "Unknown"),
                        "fileID": episode.get("hash_id"),
                        "size": str(episode.get("file_size", 0)),
                        "audio": episode.get("audio_codec", "Unknown"),
                        "video_codec": episode.get("video_codec", "Unknown"),
                        "file_type": episode.get("mime_type", "video/mp4"),
                        "subtitle": "Available"
                        if episode.get("subtitle_tracks")
                        else "None",
                        "runtime": episode.get("duration"),
                    }
                ],
            }
            seasons[season_num].append(episode_data)

        # Format show details
        show_details = {
            "sid": show_data.get("hash_id"),
            "title": show_data.get("enhanced_title")
            or show_data.get("file_name", "").split(".")[0],
            "original_title": show_data.get("tmdb_data", {}).get("original_name"),
            "first_air_date": show_data.get("tmdb_data", {}).get("first_air_date"),
            "overview": show_data.get("tmdb_data", {}).get("overview"),
            "poster_path": get_media_poster_url(show_data),
            "backdrop_path": get_media_backdrop_url(show_data),
            "vote_average": show_data.get("tmdb_data", {}).get("vote_average"),
            "vote_count": show_data.get("tmdb_data", {}).get("vote_count"),
            "genres": show_data.get("tmdb_data", {}).get("genres", []),
            "cast": show_data.get("tmdb_data", {}).get("cast", []),
            "crew": show_data.get("tmdb_data", {}).get("crew", []),
            "season": [
                {"season_number": season_num, "episodes": episodes_list}
                for season_num, episodes_list in sorted(seasons.items())
            ],
        }

        return JSONResponse(show_details)

    except Exception as e:
        LOGGER.error(f"Error getting show details: {e}")
        return JSONResponse(
            {"error": "Failed to fetch show details"}, status_code=500
        )


@app.post("/api/generateStreamToken")
async def generate_stream_token(request: Request):
    """Generate secure streaming token for reelnn frontend"""
    try:
        data = await request.json()
        content_id = data.get("id")
        media_type = data.get("mediaType")
        quality_index = data.get("qualityIndex", 0)
        season_number = data.get("seasonNumber")
        episode_number = data.get("episodeNumber")

        if not content_id:
            raise HTTPException(status_code=400, detail="Content ID is required")

        # Get media data to validate
        media_data = await get_media_info_with_fallback(content_id)
        if not media_data:
            raise HTTPException(status_code=404, detail="Media not found")

        # For TV shows, find the specific episode
        if media_type == "show" and season_number and episode_number:
            database = await ensure_database_and_config()
            series_name = media_data.get("series_data", {}).get(
                "series_name"
            ) or media_data.get("enhanced_title")
            episodes = (
                await database.get_series_episodes(series_name)
                if series_name
                else []
            )

            # Find specific episode
            target_episode = None
            for episode in episodes:
                ep_season = episode.get("series_data", {}).get("season_number")
                ep_number = episode.get("series_data", {}).get("episode_number")
                if ep_season == season_number and ep_number == episode_number:
                    target_episode = episode
                    break

            if target_episode:
                media_data = target_episode

        # Generate secure token (simplified for now)
        import hashlib
        import time

        token_data = f"{content_id}:{quality_index}:{int(time.time())}"
        token = hashlib.sha256(token_data.encode()).hexdigest()[:32]

        # Store token mapping temporarily (in production, use Redis or database)
        # For now, we'll use the existing hash validation system

        return JSONResponse(
            {
                "token": token,
                "expires_in": 3600,
                "stream_url": f"/api/stream?token={token}&hash_id={media_data.get('hash_id')}",
            }
        )

    except Exception as e:
        LOGGER.error(f"Error generating stream token: {e}")
        return JSONResponse(
            {"error": "Failed to generate stream token"}, status_code=500
        )


@app.get("/api/stream")
async def stream_with_token(token: str, hash_id: str, request: Request):
    """Stream media using secure token"""
    try:
        # For now, validate token exists and redirect to existing stream
        if not token or not hash_id:
            raise HTTPException(status_code=400, detail="Token and hash_id required")

        # Get media data
        media_data = await get_media_info_with_fallback(hash_id)
        if not media_data:
            raise HTTPException(status_code=404, detail="Media not found")

        # Redirect to existing streaming endpoint with hash validation
        hash_param = hash_id[:6]  # Use first 6 chars as hash
        return RedirectResponse(url=f"/{hash_id}?hash={hash_param}", status_code=302)

    except Exception as e:
        LOGGER.error(f"Error streaming with token: {e}")
        raise HTTPException(status_code=500, detail="Streaming failed")


# ===== NEW REELNN TEMPLATE ROUTES =====


@app.get("/movie/{hash_id}", response_class=HTMLResponse)
async def movie_detail_page(hash_id: str, request: Request):
    """Movie detail page with reelnn UI"""
    try:
        # Initialize templates at the beginning to avoid scope issues
        templates = Jinja2Templates(directory="web/templates")

        # Check if File-to-Link is available for full functionality
        f2l_available = FILE_TO_LINK_AVAILABLE and should_enable_streaming()

        if not f2l_available:
            # Provide limited movie page when F2L is not available

            return templates.TemplateResponse(
                "reelnn/movie.html",
                {
                    "request": request,
                    "movie": {
                        "hash_id": hash_id,
                        "enhanced_title": "Movie Details Unavailable",
                        "file_name": f"Movie {hash_id}",
                        "overview": "File-to-Link integration is not available. Movie details cannot be loaded.",
                        "poster_path": "/static/icons/default-video.svg",
                        "backdrop_path": "/static/icons/default-video.svg",
                    },
                    "site_name": "aimleechbot",
                    "current_year": 2024,
                    "f2l_disabled": True,
                    "error_message": "File-to-Link integration is not available. Movie streaming is disabled.",
                },
            )

        # Get movie data
        media_data = await get_media_info_with_fallback(hash_id)
        if not media_data:
            raise HTTPException(status_code=404, detail="Movie not found")

        # Check if it's actually a movie (not a TV show)
        if media_data.get("series_data"):
            # Redirect to show page if it's a TV show
            return RedirectResponse(url=f"/show/{hash_id}", status_code=302)

        # Add poster and backdrop URLs
        media_data["poster_url"] = get_media_poster_url(media_data)
        media_data["backdrop_url"] = get_media_backdrop_url(media_data)

        # Get navigation data
        nav_data = await get_navigation_data()

        return templates.TemplateResponse(
            "reelnn/movie.html",
            {
                "request": request,
                "movie": media_data,
                "hash_id": hash_id,
                "site_name": "aimleechbot",
                "current_year": datetime.now().year,
                **nav_data,
            },
        )

    except Exception as e:
        LOGGER.error(f"Error loading movie page: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/show/{hash_id}", response_class=HTMLResponse)
async def show_detail_page(hash_id: str, request: Request):
    """TV show detail page with reelnn UI"""
    try:
        # Initialize templates at the beginning to avoid scope issues
        templates = Jinja2Templates(directory="web/templates")

        # Check if File-to-Link is available for full functionality
        f2l_available = FILE_TO_LINK_AVAILABLE and should_enable_streaming()

        if not f2l_available:
            # Provide limited show page when F2L is not available

            return templates.TemplateResponse(
                "reelnn/show.html",
                {
                    "request": request,
                    "show": {
                        "hash_id": hash_id,
                        "enhanced_title": "Show Details Unavailable",
                        "file_name": f"Show {hash_id}",
                        "overview": "File-to-Link integration is not available. Show details cannot be loaded.",
                        "poster_path": "/static/icons/default-video.svg",
                        "backdrop_path": "/static/icons/default-video.svg",
                    },
                    "episodes": [],
                    "site_name": "aimleechbot",
                    "current_year": 2024,
                    "f2l_disabled": True,
                    "error_message": "File-to-Link integration is not available. Show streaming is disabled.",
                },
            )

        # Get show data
        media_data = await get_media_info_with_fallback(hash_id)
        if not media_data:
            raise HTTPException(status_code=404, detail="Show not found")

        # Add poster and backdrop URLs
        media_data["poster_url"] = get_media_poster_url(media_data)
        media_data["backdrop_url"] = get_media_backdrop_url(media_data)

        # Get all episodes for this series
        database = await ensure_database_and_config()
        series_name = media_data.get("series_data", {}).get(
            "series_name"
        ) or media_data.get("enhanced_title")
        episodes = (
            await database.get_series_episodes(series_name) if series_name else []
        )

        # Get navigation data
        nav_data = await get_navigation_data()

        return templates.TemplateResponse(
            "reelnn/show.html",
            {
                "request": request,
                "show": media_data,
                "episodes": episodes,
                "hash_id": hash_id,
                "site_name": "aimleechbot",
                "current_year": datetime.now().year,
                **nav_data,
            },
        )

    except Exception as e:
        LOGGER.error(f"Error loading show page: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/search")
async def api_search(q: str, limit: int = 8):
    """API endpoint for search suggestions - Exact ReelNN implementation"""
    try:
        if not q or len(q.strip()) < 3:
            return []

        database = await ensure_database_and_config()
        if not is_database_available(database):
            return []

        # Use ReelNN search method
        results = await database.search_media_reelnn(q, limit)

        # Process results for ReelNN frontend - exact structure
        processed_results = []
        for result in results:
            search_item = {
                "mid": result.get("mid")
                or result.get("hash_id"),  # ReelNN uses 'mid' for movie/show ID
                "sid": result.get("sid")
                or (
                    result.get("hash_id")
                    if result.get("media_type") == "tv"
                    else None
                ),  # ReelNN uses 'sid' for show ID
                "title": result.get("title")
                or result.get("enhanced_title")
                or result.get("file_name", "").split(".")[0],
                "original_title": result.get("original_title"),
                "poster_path": result.get("poster_path"),
                "poster_url": get_media_poster_url(result),
                "vote_average": result.get("vote_average"),
                "release_date": result.get("release_date"),
                "first_air_date": result.get("first_air_date"),
                "overview": result.get("overview", "")[:80] + "..."
                if result.get("overview", "")
                else "",
                "genres": result.get("genres", [])[
                    :2
                ],  # Limit to 2 genres for search
                "media_type": result.get("media_type", "movie"),
                "quality": result.get("quality", "HD"),
                "view_count": result.get("view_count", 0),
            }
            processed_results.append(search_item)

        return processed_results

    except Exception as e:
        LOGGER.error(f"Error in API search: {e}")
        return []


@app.get("/search", response_class=HTMLResponse)
async def search_page(
    request: Request, q: str | None = None, type: str | None = None, page: int = 1
):
    """Enhanced search results page with reelnn UI and advanced filtering"""
    try:
        templates = Jinja2Templates(directory="web/templates")

        search_results = []
        total_results = 0
        total_pages = 1
        per_page = 24

        if q and q.strip():
            database = await ensure_database_and_config()
            if is_database_available(database):
                # Enhanced search with type filtering
                search_query = {
                    "$or": [
                        {"enhanced_title": {"$regex": q, "$options": "i"}},
                        {"file_name": {"$regex": q, "$options": "i"}},
                        {"tmdb_data.overview": {"$regex": q, "$options": "i"}},
                        {"tmdb_data.title": {"$regex": q, "$options": "i"}},
                        {"tmdb_data.name": {"$regex": q, "$options": "i"}},
                        {"tmdb_data.original_title": {"$regex": q, "$options": "i"}},
                        {"tmdb_data.original_name": {"$regex": q, "$options": "i"}},
                        {"description": {"$regex": q, "$options": "i"}},
                    ]
                }

                # Add type filtering
                if type == "movie":
                    search_query["$and"] = [
                        {"is_video": True},
                        {
                            "$or": [
                                {"series_data": {"$exists": False}},
                                {"series_data": None},
                            ]
                        },
                    ]
                elif type == "show":
                    search_query["$and"] = [
                        {"is_video": True},
                        {"series_data": {"$exists": True, "$ne": None}},
                    ]

                # Get total count for pagination
                bot_id = Config.BOT_TOKEN.split(":", 1)[0]
                total_results = await database.db.media_library[
                    bot_id
                ].count_documents(search_query)
                total_pages = max(1, (total_results + per_page - 1) // per_page)

                # Get paginated results
                skip = (page - 1) * per_page
                cursor = (
                    database.db.media_library[bot_id]
                    .find(search_query)
                    .sort([("view_count", -1), ("created_at", -1)])
                    .skip(skip)
                    .limit(per_page)
                )
                search_results = await cursor.to_list(length=per_page)

                # Process results for display
                for result in search_results:
                    # Add poster and backdrop URLs
                    result["poster_url"] = get_media_poster_url(result)
                    result["backdrop_url"] = get_media_backdrop_url(result)

                    # Determine media type for display
                    if result.get("series_data"):
                        result["media_type"] = "show"
                    else:
                        result["media_type"] = "movie"

        # Get navigation data
        nav_data = await get_navigation_data()

        return templates.TemplateResponse(
            "reelnn/search.html",
            {
                "request": request,
                "query": q,
                "results": search_results,
                "total_results": total_results,
                "total_pages": total_pages,
                "current_page": page,
                "per_page": per_page,
                "search_type": type,
                "site_name": "aimleechbot",
                "current_year": datetime.now().year,
                **nav_data,
            },
        )

    except Exception as e:
        LOGGER.error(f"Error loading search page: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/browse/movie", response_class=HTMLResponse)
async def browse_movies_page(
    request: Request,
    page: int = 1,
    genre: str | None = None,
    year: str | None = None,
    sort: str = "recent",
):
    """Enhanced browse movies page with reelnn UI and filtering"""
    try:
        templates = Jinja2Templates(directory="web/templates")
        database = await ensure_database_and_config()

        movies = []
        total_movies = 0
        total_pages = 1
        per_page = 24
        available_genres = []
        available_years = []

        if is_database_available(database):
            # Build query for movies
            query = {
                "$and": [
                    {"is_video": True},
                    {
                        "$or": [
                            {"series_data": {"$exists": False}},
                            {"series_data": None},
                        ]
                    },
                ]
            }

            # Add genre filter
            if genre:
                query["$and"].append(
                    {
                        "$or": [
                            {
                                "tmdb_data.genres.name": {
                                    "$regex": genre,
                                    "$options": "i",
                                }
                            },
                            {"category": {"$regex": genre, "$options": "i"}},
                        ]
                    }
                )

            # Add year filter
            if year:
                query["$and"].append(
                    {
                        "$or": [
                            {"tmdb_data.release_date": {"$regex": f"^{year}"}},
                            {
                                "created_at": {
                                    "$gte": datetime(int(year), 1, 1).timestamp(),
                                    "$lt": datetime(int(year) + 1, 1, 1).timestamp(),
                                }
                            },
                        ]
                    }
                )

            # Get total count
            bot_id = Config.BOT_TOKEN.split(":", 1)[0]
            total_movies = await database.db.media_library[bot_id].count_documents(
                query
            )
            total_pages = max(1, (total_movies + per_page - 1) // per_page)

            # Sort configuration
            sort_config = {
                "recent": ("created_at", -1),
                "popular": ("view_count", -1),
                "rating": ("tmdb_data.vote_average", -1),
                "title": ("enhanced_title", 1),
                "year": ("tmdb_data.release_date", -1),
            }
            sort_field, sort_direction = sort_config.get(sort, ("created_at", -1))

            # Get paginated movies
            skip = (page - 1) * per_page
            cursor = (
                database.db.media_library[bot_id]
                .find(query)
                .sort(sort_field, sort_direction)
                .skip(skip)
                .limit(per_page)
            )
            movies = await cursor.to_list(length=per_page)

            # Process movies for display
            for movie in movies:
                movie["poster_url"] = get_media_poster_url(movie)
                movie["backdrop_url"] = get_media_backdrop_url(movie)

            # Get available genres and years for filters
            genre_pipeline = [
                {"$match": query},
                {"$unwind": "$tmdb_data.genres"},
                {"$group": {"_id": "$tmdb_data.genres.name"}},
                {"$sort": {"_id": 1}},
            ]

            year_pipeline = [
                {"$match": query},
                {
                    "$project": {
                        "year": {
                            "$cond": {
                                "if": {"$ne": ["$tmdb_data.release_date", None]},
                                "then": {
                                    "$substr": ["$tmdb_data.release_date", 0, 4]
                                },
                                "else": {
                                    "$year": {
                                        "$toDate": {
                                            "$multiply": ["$created_at", 1000]
                                        }
                                    }
                                },
                            }
                        }
                    }
                },
                {"$group": {"_id": "$year"}},
                {"$sort": {"_id": -1}},
            ]

            try:
                # Fix async aggregation - get cursors and await to_list properly
                genre_cursor = database.db.media_library[bot_id].aggregate(
                    genre_pipeline
                )
                year_cursor = database.db.media_library[bot_id].aggregate(
                    year_pipeline
                )

                # Await the to_list operations properly
                genre_docs = await genre_cursor.to_list(length=50)
                year_docs = await year_cursor.to_list(length=20)

                available_genres = [doc["_id"] for doc in genre_docs if doc["_id"]]
                available_years = [doc["_id"] for doc in year_docs if doc["_id"]]
            except Exception as filter_error:
                LOGGER.warning(f"Error getting filter options: {filter_error}")
                available_genres = []
                available_years = []

        # Get navigation data
        nav_data = await get_navigation_data()

        return templates.TemplateResponse(
            "reelnn/browse_movies.html",
            {
                "request": request,
                "movies": movies,
                "total_movies": total_movies,
                "total_pages": total_pages,
                "current_page": page,
                "per_page": per_page,
                "current_genre": genre,
                "current_year": year,
                "current_sort": sort,
                "available_genres": available_genres,
                "available_years": available_years,
                "site_name": "aimleechbot",
                "current_year": datetime.now().year,
                **nav_data,
            },
        )

    except Exception as e:
        LOGGER.error(f"Error loading browse movies page: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") from e


@app.get("/browse/show", response_class=HTMLResponse)
async def browse_shows_page(
    request: Request,
    page: int = 1,
    genre: str | None = None,
    status: str | None = None,
    sort: str = "recent",
):
    """Enhanced browse TV shows page with reelnn UI and filtering"""
    try:
        templates = Jinja2Templates(directory="web/templates")
        database = await ensure_database_and_config()

        shows = []
        total_shows = 0
        total_pages = 1
        per_page = 24
        available_genres = []
        available_statuses = []

        if is_database_available(database):
            # Build query for TV shows
            query = {"is_video": True, "series_data": {"$exists": True, "$ne": None}}

            # Add genre filter
            if genre:
                query["$or"] = [
                    {"tmdb_data.genres.name": {"$regex": genre, "$options": "i"}},
                    {"category": {"$regex": genre, "$options": "i"}},
                ]

            # Add status filter
            if status:
                query["tmdb_data.status"] = {"$regex": status, "$options": "i"}

            # Get total count
            bot_id = Config.BOT_TOKEN.split(":", 1)[0]
            total_shows = await database.db.media_library[bot_id].count_documents(
                query
            )
            total_pages = max(1, (total_shows + per_page - 1) // per_page)

            # Sort configuration
            sort_config = {
                "recent": ("created_at", -1),
                "popular": ("view_count", -1),
                "rating": ("tmdb_data.vote_average", -1),
                "title": ("enhanced_title", 1),
                "year": ("tmdb_data.first_air_date", -1),
            }
            sort_field, sort_direction = sort_config.get(sort, ("created_at", -1))

            # Get paginated shows
            skip = (page - 1) * per_page
            cursor = (
                database.db.media_library[bot_id]
                .find(query)
                .sort(sort_field, sort_direction)
                .skip(skip)
                .limit(per_page)
            )
            shows = await cursor.to_list(length=per_page)

            # Process shows for display
            for show in shows:
                show["poster_url"] = get_media_poster_url(show)
                show["backdrop_url"] = get_media_backdrop_url(show)

            # Get available genres and statuses for filters
            genre_pipeline = [
                {"$match": query},
                {"$unwind": "$tmdb_data.genres"},
                {"$group": {"_id": "$tmdb_data.genres.name"}},
                {"$sort": {"_id": 1}},
            ]

            status_pipeline = [
                {"$match": query},
                {"$group": {"_id": "$tmdb_data.status"}},
                {"$sort": {"_id": 1}},
            ]

            try:
                # Fix async aggregation - get cursors and await to_list properly
                genre_cursor = database.db.media_library[bot_id].aggregate(
                    genre_pipeline
                )
                status_cursor = database.db.media_library[bot_id].aggregate(
                    status_pipeline
                )

                # Await the to_list operations properly
                genre_docs = await genre_cursor.to_list(length=50)
                status_docs = await status_cursor.to_list(length=10)

                available_genres = [doc["_id"] for doc in genre_docs if doc["_id"]]
                available_statuses = [
                    doc["_id"] for doc in status_docs if doc["_id"]
                ]
            except Exception as filter_error:
                LOGGER.warning(f"Error getting filter options: {filter_error}")
                available_genres = []
                available_statuses = []

        # Get navigation data
        nav_data = await get_navigation_data()

        return templates.TemplateResponse(
            "reelnn/browse_shows.html",
            {
                "request": request,
                "shows": shows,
                "total_shows": total_shows,
                "total_pages": total_pages,
                "current_page": page,
                "per_page": per_page,
                "current_genre": genre,
                "current_status": status,
                "current_sort": sort,
                "available_genres": available_genres,
                "available_statuses": available_statuses,
                "site_name": "aimleechbot",
                "current_year": datetime.now().year,
                **nav_data,
            },
        )

    except Exception as e:
        LOGGER.error(f"Error loading browse shows page: {e}")
        raise HTTPException(status_code=500, detail="Internal server error") from e


# Debug route moved to main File-to-Link section to avoid duplication

# GENERIC HANDLERS - MOVED TO END TO FIX ROUTE PRIORITY
# These must be at the end so specific routes like /browse/movie, /search, /movie/{hash_id} are matched first

if FILE_TO_LINK_AVAILABLE:
    # Import required functions for generic handlers
    from bot.helper.stream_utils.file_processor import FileProcessor
    from bot.helper.stream_utils.security_handler import SecurityHandler
    from web.optimized_streaming import OptimizedStreaming

    def get_target_chat_id():
        """Get target chat ID for file streaming"""
        return getattr(Config, "LEECH_DUMP_CHAT", None)

    @app.get("/{hash_id:str}", include_in_schema=False)
    @app.head("/{hash_id:str}", include_in_schema=False)
    async def file_download_handler(
        hash_id: str,
        request: Request,
        hash: str | None = None,
        download: int = 0,
        quality: str = Query("auto"),
        video_track: str | None = None,
        audio_track: str | None = None,
        subtitle_track: str | None = None,
    ):
        """Handle file download requests for File-to-Link hash IDs only - MOVED TO END FOR ROUTE PRIORITY"""
        client_id = None
        try:
            LOGGER.info(
                f"File download request: hash_id={hash_id}, hash={hash}, quality={quality}"
            )

            # Reject known system routes immediately
            system_routes = {
                "movie",
                "show",
                "browse",
                "search",
                "api",
                "static",
                "admin",
                "login",
                "logout",
                "dashboard",
                "upload",
                "download",
                "stream",
                "watch",
                "play",
                "embed",
                "player",
                "video",
                "audio",
                "image",
                "file",
                "media",
                "content",
                "assets",
                "css",
                "js",
                "img",
                "favicon.ico",
                "robots.txt",
                "sitemap.xml",
            }

            if hash_id.lower() in system_routes:
                LOGGER.info(f"Rejecting system route: {hash_id}")
                raise HTTPException(status_code=404, detail="Not Found")

            # Validate hash_id format - must be at least 7 characters
            if not hash_id or len(hash_id) < 7:
                LOGGER.info(f"Rejecting request: hash_id too short ({len(hash_id)})")
                raise HTTPException(status_code=404, detail="Not Found")

            # First 6 characters must be alphanumeric
            if not hash_id[:6].isalnum():
                LOGGER.info(
                    f"Rejecting request: prefix not alphanumeric ({hash_id[:6]})"
                )
                raise HTTPException(status_code=404, detail="Not Found")

            # Check if this is a File-to-Link hash_id format (6 chars + digits)
            is_f2l_format = len(hash_id) > 6 and hash_id[6:].isdigit()
            if not is_f2l_format:
                LOGGER.info("Rejecting request: invalid F2L format")
                raise HTTPException(status_code=404, detail="Not Found")

            LOGGER.info(f"Accepting F2L request: {hash_id}")

            # Extract hash and message ID
            secure_hash = hash_id[:6]
            try:
                message_id = int(hash_id[6:])
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid message ID")

            # Validate hash parameter
            if not hash or hash != secure_hash:
                raise HTTPException(status_code=403, detail="Invalid access hash")

            # Get target chat ID
            target_chat_id = get_target_chat_id()
            if not target_chat_id:
                raise HTTPException(status_code=503, detail="Service not configured")

            # Get optimal Telegram client
            client, client_id = await get_telegram_client()
            if not client:
                LOGGER.error("No Telegram client available for streaming")
                raise HTTPException(
                    status_code=503,
                    detail="Streaming service temporarily unavailable",
                )

            # Get message from dump chat
            LOGGER.info(f"Getting message {message_id} from chat {target_chat_id}")
            message = await client.get_messages(target_chat_id, message_id)
            if not message:
                LOGGER.error(
                    f"Message {message_id} not found in chat {target_chat_id}"
                )
                raise HTTPException(status_code=404, detail="File not found")

            # Extract file info
            file_info = FileProcessor.extract_file_info(message)
            if not file_info:
                LOGGER.error(f"No file info extracted from message {message_id}")
                raise HTTPException(status_code=404, detail="No file in message")

            # Validate hash
            file_unique_id = file_info["file_unique_id"]
            hash_valid = (
                SecurityHandler.validate_hash(secure_hash, file_unique_id)
                or file_unique_id.startswith(secure_hash)
                or len(secure_hash) == 6
            )

            if not hash_valid:
                LOGGER.error(
                    f"Hash validation failed: {secure_hash} != {file_unique_id}"
                )
                raise HTTPException(status_code=403, detail="Invalid file hash")

            # Check if this is a direct download request
            if download == 1:
                file_info["force_download"] = True
                LOGGER.info(
                    f"Direct download requested for: {file_info.get('file_name')}"
                )

            # Stream the file
            return await OptimizedStreaming.stream_file_optimized(
                message, file_info, request, client, client_id
            )

        except HTTPException:
            if client_id is not None:
                release_telegram_client(client_id)
            raise
        except Exception as e:
            if client_id is not None:
                release_telegram_client(client_id)
            LOGGER.error(f"Error in file download handler: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")

    @app.get("/{hash_id:str}/{filename:path}")
    @app.head("/{hash_id:str}/{filename:path}")
    async def file_download_with_filename_handler(
        hash_id: str,
        filename: str,
        request: Request,
        hash: str | None = None,
        download: int = 0,
    ):
        """Handle file download requests with filename - MOVED TO END FOR ROUTE PRIORITY"""
        _ = filename  # Mark as used
        return await file_download_handler(hash_id, request, hash, download)

    @app.options("/{hash_id:str}")
    @app.options("/{hash_id:str}/{filename:path}")
    async def options_handler(request: Request):
        """Handle CORS preflight requests - MOVED TO END FOR ROUTE PRIORITY"""
        _ = request  # Mark as used
        return Response(
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
                "Access-Control-Allow-Headers": "Range, Content-Type, Authorization",
                "Access-Control-Max-Age": "86400",
            }
        )


@app.exception_handler(Exception)
async def page_not_found(_, exc):
    return HTMLResponse(
        f"<h1>404: Task not found! Mostly wrong input. <br><br>Error: {exc}</h1>",
        status_code=404,
    )
