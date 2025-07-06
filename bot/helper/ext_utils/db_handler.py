import asyncio
import contextlib
import inspect
import math
import time
from datetime import datetime
from time import time as get_time

from aiofiles import open as aiopen
from pymongo import AsyncMongoClient
from pymongo.errors import (
    ConnectionFailure,
    PyMongoError,
    ServerSelectionTimeoutError,
)
from pymongo.server_api import ServerApi

from bot import LOGGER, qbit_options, rss_dict, user_data
from bot.core.aeon_client import TgClient
from bot.core.config_manager import Config
from bot.helper.ext_utils.aiofiles_compat import aiopath

try:
    from bot.helper.ext_utils.gc_utils import smart_garbage_collection
except ImportError:
    smart_garbage_collection = None


class DbManager:
    def __init__(self):
        self._return = True
        self._conn = None
        self.db = None
        self._last_connection_check = 0
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 5

    async def connect(self):
        try:
            # Only close if we have a connection and it's not working
            if self._conn is not None:
                try:
                    # Test if connection is still working before closing
                    await self._conn.admin.command("ping")
                    # If ping succeeds, connection is still good
                    if self.db is not None:
                        LOGGER.info("Reusing existing database connection")
                        return
                except Exception:
                    # Connection is bad, close it
                    try:
                        await self._conn.close()
                    except Exception as e:
                        LOGGER.error(f"Error closing previous DB connection: {e}")

            # Optimized connection parameters for better stability and performance
            self._conn = AsyncMongoClient(
                Config.DATABASE_URL,
                server_api=ServerApi("1"),
                maxPoolSize=10,  # Increased pool size for better concurrency
                minPoolSize=2,  # Keep minimum connections alive
                maxIdleTimeMS=300000,  # 5 minutes idle time
                connectTimeoutMS=20000,  # 20 seconds connection timeout
                socketTimeoutMS=60000,  # 60 seconds socket timeout
                serverSelectionTimeoutMS=30000,  # 30 seconds server selection timeout
                heartbeatFrequencyMS=30000,  # 30 seconds heartbeat frequency
                retryWrites=True,  # Enable retry for write operations
                retryReads=True,  # Enable retry for read operations
                waitQueueTimeoutMS=30000,  # 30 seconds wait queue timeout
                maxConnecting=5,  # Limit concurrent connection attempts
            )

            # Verify connection is working with a ping
            await self._conn.admin.command("ping")

            self.db = self._conn.luna
            self._return = False
            LOGGER.info("Successfully connected to database")

            # Initialize database schema
            await self._initialize_schema()
        except PyMongoError as e:
            LOGGER.error(f"Error in DB connection: {e}")
            self.db = None
            self._return = True
            self._conn = None

    async def ensure_connection(self):
        """Check if the database connection is alive and reconnect if needed."""
        # Skip if no database URL is configured
        if not Config.DATABASE_URL:
            self._return = True
            return False

        # Skip if we've checked recently (within last 30 seconds)
        current_time = int(get_time())
        if (
            current_time - self._last_connection_check < 30
            and self._conn is not None
            and not self._return
        ):
            return True

        self._last_connection_check = current_time

        # If we don't have a connection, try to connect
        if self._conn is None or self._return:
            await self.connect()
            return not self._return

        # Check if the connection is still alive
        try:
            # Simple ping to check connection
            await self._conn.admin.command("ping")
            self._reconnect_attempts = 0  # Reset reconnect attempts on success
            return True
        except (PyMongoError, ConnectionFailure, ServerSelectionTimeoutError) as e:
            LOGGER.warning(f"Database connection check failed: {e}")

            # Increment reconnect attempts
            self._reconnect_attempts += 1

            # If we've tried too many times, log an error and give up
            if self._reconnect_attempts > self._max_reconnect_attempts:
                LOGGER.error("Maximum reconnection attempts reached. Giving up.")
                await self.disconnect()
                return False

            # Exponential backoff for reconnection attempts
            backoff_delay = min(
                2 ** (self._reconnect_attempts - 1), 30
            )  # Max 30 seconds
            LOGGER.info(
                f"Attempting to reconnect to database (attempt {self._reconnect_attempts}/{self._max_reconnect_attempts}) after {backoff_delay}s delay"
            )

            # Wait before reconnecting to avoid overwhelming the database
            await asyncio.sleep(backoff_delay)

            # Reset connection state before reconnecting
            self._conn = None
            self.db = None
            self._return = True

            await self.connect()
            return not self._return

    async def disconnect(self):
        self._return = True
        if self._conn is not None:
            try:
                await self._conn.close()
                LOGGER.info("Database connection closed successfully")
            except Exception as e:
                LOGGER.error(f"Error closing database connection: {e}")
        self._conn = None
        self.db = None
        self._last_connection_check = 0
        self._reconnect_attempts = 0

        # Force garbage collection after database operations
        if smart_garbage_collection is not None:
            smart_garbage_collection(aggressive=True)

    # Removed update_deploy_config method - deploy config is now only updated during startup
    # when actual config.py changes are detected. No more bidirectional sync!

    async def update_config(self, dict_):
        """
        Update runtime config only - never touch deploy config

        Runtime config represents user modifications and should be independent
        of deploy config which represents the source of truth from config.py

        Args:
            dict_: Configuration dictionary to update
        """
        if not await self.ensure_connection():
            return
        try:
            # Update only runtime config - no timestamps, no deploy config sync
            await self.db.settings.config.update_one(
                {"_id": TgClient.ID},
                {"$set": dict_},
                upsert=True,
            )

        except PyMongoError as e:
            LOGGER.error(f"Error updating config: {e}")
            await self.ensure_connection()  # Try to reconnect for next operation

    # Removed obsolete sync methods - no longer needed with new clean architecture

    async def update_aria2(self, key, value):
        if not await self.ensure_connection():
            return
        try:
            await self.db.settings.aria2c.update_one(
                {"_id": TgClient.ID},
                {"$set": {key: value}},
                upsert=True,
            )
        except PyMongoError as e:
            LOGGER.error(f"Error updating aria2 config: {e}")
            await self.ensure_connection()  # Try to reconnect for next operation

    async def update_qbittorrent(self, key, value):
        if not await self.ensure_connection():
            return
        try:
            await self.db.settings.qbittorrent.update_one(
                {"_id": TgClient.ID},
                {"$set": {key: value}},
                upsert=True,
            )
        except PyMongoError as e:
            LOGGER.error(f"Error updating qbittorrent config: {e}")
            await self.ensure_connection()  # Try to reconnect for next operation

    async def save_qbit_settings(self):
        if not await self.ensure_connection():
            return
        try:
            await self.db.settings.qbittorrent.update_one(
                {"_id": TgClient.ID},
                {"$set": qbit_options},
                upsert=True,
            )
        except PyMongoError as e:
            LOGGER.error(f"Error saving qbittorrent settings: {e}")
            await self.ensure_connection()  # Try to reconnect for next operation

    async def update_private_file(self, path):
        if self._return:
            return
        db_path = path.replace(".", "__")
        if await aiopath.exists(path):
            try:
                async with aiopen(path, "rb+") as pf:
                    pf_bin = await pf.read()
                await self.db.settings.files.update_one(
                    {"_id": TgClient.ID},
                    {"$set": {db_path: pf_bin}},
                    upsert=True,
                )
                # Note: config.py changes are now handled during startup, not here

                # Force garbage collection after handling large files
                if (
                    len(pf_bin) > 1024 * 1024
                    and smart_garbage_collection is not None
                ):  # 1MB
                    smart_garbage_collection(aggressive=False)

                # Explicitly delete large binary data
                del pf_bin
            except Exception as e:
                LOGGER.error(f"Error updating private file {path}: {e}")
        else:
            await self.db.settings.files.update_one(
                {"_id": TgClient.ID},
                {"$unset": {db_path: ""}},
                upsert=True,
            )

    async def get_private_files(self):
        """Get list of available private files from database and filesystem"""
        if self._return:
            return {}

        try:
            # Get files from database
            db_files = await self.db.settings.files.find_one({"_id": TgClient.ID})
            if not db_files:
                db_files = {}

            # List of known private files to check
            known_files = [
                "config.py",
                "token.pickle",
                "token_sa.pickle",
                "youtube_token.pickle",
                "rclone.conf",
                "accounts.zip",
                "list_drives.txt",
                "cookies.txt",
                ".netrc",
                "shorteners.txt",
                "streamrip_config.toml",
                "zotify_credentials.json",
            ]

            available_files = {}

            # Check all known files regardless of existence to show complete status
            for file_name in known_files:
                db_key = file_name.replace(".", "__")
                file_exists_db = db_key in db_files and db_files[db_key] is not None
                file_exists_fs = await aiopath.exists(file_name)

                # Special handling for accounts.zip - also check if accounts directory exists
                accounts_dir_exists = False
                if file_name == "accounts.zip":
                    accounts_dir_exists = await aiopath.exists("accounts")

                # Always include the file in the list to show complete status
                available_files[file_name] = {
                    "exists_db": file_exists_db,
                    "exists_fs": file_exists_fs,
                    "accounts_dir_exists": accounts_dir_exists
                    if file_name == "accounts.zip"
                    else False,
                    "size_db": len(db_files.get(db_key, b""))
                    if file_exists_db
                    else 0,
                    "size_fs": await aiopath.getsize(file_name)
                    if file_exists_fs
                    else 0,
                }

            return available_files

        except Exception as e:
            LOGGER.error(f"Error getting private files list: {e}")
            return {}

    async def sync_private_files_to_db(self):
        """Sync all existing private files from filesystem to database"""
        if self._return:
            return {"synced": 0, "errors": []}

        try:
            # List of known private files to sync
            known_files = [
                "config.py",
                "token.pickle",
                "token_sa.pickle",
                "youtube_token.pickle",
                "rclone.conf",
                "accounts.zip",
                "list_drives.txt",
                "cookies.txt",
                ".netrc",
                "shorteners.txt",
                "streamrip_config.toml",
                "zotify_credentials.json",
            ]

            synced_count = 0
            errors = []

            for file_name in known_files:
                try:
                    if await aiopath.exists(file_name):
                        # Check if already in database
                        db_key = file_name.replace(".", "__")
                        db_files = await self.db.settings.files.find_one(
                            {"_id": TgClient.ID}
                        )

                        if (
                            not db_files
                            or db_key not in db_files
                            or not db_files[db_key]
                        ):
                            # File exists in filesystem but not in database, sync it
                            await self.update_private_file(file_name)
                            synced_count += 1
                            LOGGER.info(f"Synced {file_name} to database")

                except Exception as e:
                    error_msg = f"Error syncing {file_name}: {e}"
                    LOGGER.error(error_msg)
                    errors.append(error_msg)

            return {"synced": synced_count, "errors": errors}

        except Exception as e:
            LOGGER.error(f"Error syncing private files to database: {e}")
            return {"synced": 0, "errors": [str(e)]}

    async def sync_private_files_to_fs(self):
        """Sync all existing private files from database to filesystem"""
        if self._return:
            return {"synced": 0, "errors": []}

        try:
            # Get all files from database
            db_files = await self.db.settings.files.find_one({"_id": TgClient.ID})
            if not db_files:
                return {"synced": 0, "errors": ["No files found in database"]}

            # List of known private files to sync
            known_files = [
                "config.py",
                "token.pickle",
                "token_sa.pickle",
                "youtube_token.pickle",
                "rclone.conf",
                "accounts.zip",
                "list_drives.txt",
                "cookies.txt",
                ".netrc",
                "shorteners.txt",
                "streamrip_config.toml",
                "zotify_credentials.json",
            ]

            synced_count = 0
            errors = []

            for file_name in known_files:
                try:
                    db_key = file_name.replace(".", "__")

                    # Check if file exists in database but not in filesystem
                    if db_files.get(db_key):
                        if not await aiopath.exists(file_name):
                            # File exists in database but not in filesystem, sync it
                            async with aiopen(file_name, "wb") as f:
                                await f.write(db_files[db_key])

                            # Handle special post-sync operations
                            if file_name == "accounts.zip":
                                # Extract accounts.zip if it was synced
                                try:
                                    from asyncio import create_subprocess_exec

                                    await (
                                        await create_subprocess_exec(
                                            "7z",
                                            "x",
                                            "-o.",
                                            "-aoa",
                                            "accounts.zip",
                                            "accounts/*.json",
                                        )
                                    ).wait()
                                    await (
                                        await create_subprocess_exec(
                                            "chmod", "-R", "777", "accounts"
                                        )
                                    ).wait()
                                except Exception as e:
                                    LOGGER.warning(
                                        f"Failed to extract accounts.zip after sync: {e}"
                                    )

                            elif file_name in [".netrc", "netrc"]:
                                # Set proper permissions for .netrc
                                try:
                                    await (
                                        await create_subprocess_exec(
                                            "chmod", "600", ".netrc"
                                        )
                                    ).wait()
                                    await (
                                        await create_subprocess_exec(
                                            "cp", ".netrc", "/root/.netrc"
                                        )
                                    ).wait()
                                except Exception as e:
                                    LOGGER.warning(
                                        f"Failed to set .netrc permissions after sync: {e}"
                                    )

                            synced_count += 1
                            LOGGER.info(f"Synced {file_name} to filesystem")

                except Exception as e:
                    error_msg = f"Error syncing {file_name}: {e}"
                    LOGGER.error(error_msg)
                    errors.append(error_msg)

            return {"synced": synced_count, "errors": errors}

        except Exception as e:
            LOGGER.error(f"Error syncing private files to filesystem: {e}")
            return {"synced": 0, "errors": [str(e)]}

    async def update_nzb_config(self):
        if self._return:
            return
        async with aiopen("sabnzbd/SABnzbd.ini", "rb+") as pf:
            nzb_conf = await pf.read()
        await self.db.settings.nzb.replace_one(
            {"_id": TgClient.ID},
            {"SABnzbd__ini": nzb_conf},
            upsert=True,
        )

    async def update_user_data(self, user_id):
        if self._return:
            return
        data = user_data.get(user_id, {})
        data = data.copy()
        for key in (
            "THUMBNAIL",
            "RCLONE_CONFIG",
            "TOKEN_PICKLE",
            "YOUTUBE_TOKEN_PICKLE",
            "USER_COOKIES",
            "TOKEN",
            "TIME",
        ):
            data.pop(key, None)
        pipeline = [
            {
                "$replaceRoot": {
                    "newRoot": {
                        "$mergeObjects": [
                            data,
                            {
                                "$arrayToObject": {
                                    "$filter": {
                                        "input": {"$objectToArray": "$$ROOT"},
                                        "as": "field",
                                        "cond": {
                                            "$in": [
                                                "$$field.k",
                                                [
                                                    "THUMBNAIL",
                                                    "RCLONE_CONFIG",
                                                    "TOKEN_PICKLE",
                                                    "YOUTUBE_TOKEN_PICKLE",
                                                    "USER_COOKIES",
                                                ],
                                            ],
                                        },
                                    },
                                },
                            },
                        ],
                    },
                },
            },
        ]
        await self.db.users.update_one({"_id": user_id}, pipeline, upsert=True)

    async def update_user_doc(self, user_id, key, path="", binary_data=None):
        """Update a user document in the database with memory-efficient handling.

        Args:
            user_id: The user ID
            key: The key to update
            path: The path to the file to read (if binary_data is None)
            binary_data: Binary data to store directly (if provided, path is ignored)
        """
        if self._return:
            return

        if binary_data is not None:
            # Use the provided binary data directly
            doc_bin = binary_data
        elif path:
            try:
                # Get file size for logging
                file_size = await aiopath.getsize(path)
                LOGGER.info(
                    f"Reading file {path} of size {file_size} bytes for user {user_id}"
                )

                # Use chunked reading for memory efficiency
                chunk_size = 8 * 1024 * 1024  # 8MB chunks
                doc_bin = bytearray()

                async with aiopen(path, "rb") as doc:
                    while True:
                        try:
                            chunk = await doc.read(chunk_size)
                            if not chunk:
                                break
                            doc_bin.extend(chunk)

                            # Force garbage collection periodically for large files
                            if len(doc_bin) % (32 * 1024 * 1024) == 0:  # Every 32MB
                                if smart_garbage_collection is not None:
                                    smart_garbage_collection(aggressive=False)

                        except MemoryError:
                            LOGGER.error(
                                f"Memory error while reading chunk from {path}"
                            )
                            # Try to free up memory
                            if smart_garbage_collection is not None:
                                smart_garbage_collection(aggressive=True)
                            raise MemoryError(
                                f"Not enough memory to read file: {path}"
                            )

                # Convert to bytes for database storage
                doc_bin = bytes(doc_bin)

                # Verify the data was read correctly
                if len(doc_bin) != file_size:
                    LOGGER.error(
                        f"File read size mismatch: expected {file_size}, got {len(doc_bin)}"
                    )
                    raise ValueError("File read size mismatch")

                LOGGER.info(f"Successfully read {len(doc_bin)} bytes from {path}")

            except MemoryError as e:
                LOGGER.error(f"Memory error reading file {path}: {e}")
                # Force aggressive garbage collection
                if smart_garbage_collection is not None:
                    smart_garbage_collection(aggressive=True)
                raise MemoryError(f"Not enough memory to read file: {path}")
            except Exception as e:
                LOGGER.error(f"Error reading file {path}: {e}")
                raise
        else:
            # Remove the key if no data is provided
            await self.db.users.update_one(
                {"_id": user_id},
                {"$unset": {key: ""}},
                upsert=True,
            )
            return

        try:
            # Store the binary data in the database
            LOGGER.info(
                f"Storing {len(doc_bin)} bytes in database for user {user_id}, key {key}"
            )
            await self.db.users.update_one(
                {"_id": user_id},
                {"$set": {key: doc_bin}},
                upsert=True,
            )
            LOGGER.info(
                f"Successfully updated user document for user {user_id}, key {key}"
            )

            # Force garbage collection after large database operations
            if (
                len(doc_bin) > 10 * 1024 * 1024
                and smart_garbage_collection is not None
            ):  # 10MB
                smart_garbage_collection(aggressive=False)

        except MemoryError as e:
            LOGGER.error(
                f"Memory error storing data in database for user {user_id}: {e}"
            )
            # Force aggressive garbage collection
            if smart_garbage_collection is not None:
                smart_garbage_collection(aggressive=True)
            raise MemoryError("Not enough memory to store data in database")
        except Exception as e:
            LOGGER.error(
                f"Error updating user document for user {user_id}, key {key}: {e}"
            )
            raise

    async def rss_update_all(self):
        if self._return:
            return
        for user_id in list(rss_dict.keys()):
            await self.db.rss[TgClient.ID].replace_one(
                {"_id": user_id},
                rss_dict[user_id],
                upsert=True,
            )

    async def rss_update(self, user_id):
        if self._return:
            return
        await self.db.rss[TgClient.ID].replace_one(
            {"_id": user_id},
            rss_dict[user_id],
            upsert=True,
        )

    async def rss_delete(self, user_id):
        if self._return:
            return
        await self.db.rss[TgClient.ID].delete_one({"_id": user_id})

    async def add_incomplete_task(self, cid, link, tag):
        if self._return:
            return
        try:
            await self.db.tasks[TgClient.ID].update_one(
                {"_id": link},
                {"$set": {"cid": cid, "tag": tag}},
                upsert=True,
            )
        except Exception as e:
            # Log the error but don't fail the operation
            LOGGER.warning(f"Failed to add incomplete task to database: {e}")
            # Continue with the operation even if database update fails

    async def get_pm_uids(self):
        if self._return:
            return None
        return [doc["_id"] async for doc in self.db.pm_users[TgClient.ID].find({})]

    async def update_pm_users(self, user_id):
        if self._return:
            return
        if not bool(await self.db.pm_users[TgClient.ID].find_one({"_id": user_id})):
            await self.db.pm_users[TgClient.ID].insert_one({"_id": user_id})
            LOGGER.info(f"New PM User Added : {user_id}")

    async def rm_pm_user(self, user_id):
        if self._return:
            return
        await self.db.pm_users[TgClient.ID].delete_one({"_id": user_id})

    async def update_user_tdata(self, user_id, token, expiry_time):
        if self._return:
            return
        await self.db.access_token.update_one(
            {"_id": user_id},
            {"$set": {"TOKEN": token, "TIME": expiry_time}},
            upsert=True,
        )

    async def update_user_token(self, user_id, token):
        if self._return:
            return
        await self.db.access_token.update_one(
            {"_id": user_id},
            {"$set": {"TOKEN": token}},
            upsert=True,
        )

    async def get_token_expiry(self, user_id):
        if self._return:
            return None
        user_data = await self.db.access_token.find_one({"_id": user_id})
        if user_data:
            return user_data.get("TIME")
        return None

    async def delete_user_token(self, user_id):
        if self._return:
            return
        await self.db.access_token.delete_one({"_id": user_id})

    async def get_user_token(self, user_id):
        if self._return:
            return None
        user_data = await self.db.access_token.find_one({"_id": user_id})
        if user_data:
            return user_data.get("TOKEN")
        return None

    async def get_user_doc(self, user_id):
        """Get a user document from the database.

        Args:
            user_id: The user ID to get the document for.

        Returns:
            The user document as a dictionary, or None if not found.
        """
        if self._return:
            return None
        return await self.db.users.find_one({"_id": user_id})

    async def delete_all_access_tokens(self):
        if self._return:
            return
        await self.db.access_token.delete_many({})

    async def rm_complete_task(self, link):
        if self._return:
            return
        try:
            await self.db.tasks[TgClient.ID].delete_one({"_id": link})
        except Exception as e:
            # Log the error but don't fail the operation
            LOGGER.warning(f"Failed to remove completed task from database: {e}")
            # Continue with the operation even if database update fails

    async def get_incomplete_tasks(self):
        notifier_dict = {}
        if not await self.ensure_connection():
            return notifier_dict

        try:
            if await self.db.tasks[TgClient.ID].find_one():
                rows = self.db.tasks[TgClient.ID].find({})
                async for row in rows:
                    if row["cid"] in list(notifier_dict.keys()):
                        if row["tag"] in list(notifier_dict[row["cid"]]):
                            notifier_dict[row["cid"]][row["tag"]].append(row["_id"])
                        else:
                            notifier_dict[row["cid"]][row["tag"]] = [row["_id"]]
                    else:
                        notifier_dict[row["cid"]] = {row["tag"]: [row["_id"]]}

            # Only drop the collection if we successfully retrieved the data
            try:
                await self.db.tasks[TgClient.ID].drop()
            except PyMongoError as e:
                LOGGER.error(f"Error dropping tasks collection: {e}")
        except PyMongoError as e:
            LOGGER.error(f"Error retrieving incomplete tasks: {e}")
            await self.ensure_connection()  # Try to reconnect for next operation

        return notifier_dict

    async def trunc_table(self, name):
        if self._return:
            return
        await self.db[name][TgClient.ID].drop()

    async def store_scheduled_deletion(
        self,
        chat_ids,
        message_ids,
        delete_time,
        bot_id=None,
    ):
        """Store messages for scheduled deletion

        Args:
            chat_ids: List of chat IDs
            message_ids: List of message IDs
            delete_time: Timestamp when the message should be deleted
            bot_id: ID of the bot that created the message (default: main bot ID)
        """
        if not await self.ensure_connection():
            return

        # Default to main bot ID if not specified
        if bot_id is None:
            bot_id = TgClient.ID

        # Storing messages for deletion

        # Check if connection is still valid before operation
        if self._conn is None or self._return:
            LOGGER.warning(
                "Database connection not available for scheduled deletion storage"
            )
            return

        # Store each message individually to avoid bulk write issues
        for chat_id, message_id in zip(chat_ids, message_ids, strict=True):
            try:
                await self.db.scheduled_deletions.update_one(
                    {"chat_id": chat_id, "message_id": message_id},
                    {"$set": {"delete_time": delete_time, "bot_id": bot_id}},
                    upsert=True,
                )
            except (PyMongoError, AttributeError) as e:
                LOGGER.error(f"Error storing scheduled deletion: {e}")
                # Reset connection state and try to reconnect for next operation
                self._conn = None
                self._return = True
                await self.ensure_connection()
                break  # Stop processing if connection fails

        # Messages stored for deletion

    async def remove_scheduled_deletion(self, chat_id, message_id):
        """Remove a message from scheduled deletions"""
        if not await self.ensure_connection():
            return
        try:
            # Check if connection is still valid before operation
            if self._conn is None or self._return:
                LOGGER.warning(
                    "Database connection not available for scheduled deletion removal"
                )
                return
            await self.db.scheduled_deletions.delete_one(
                {"chat_id": chat_id, "message_id": message_id},
            )
        except (PyMongoError, AttributeError) as e:
            LOGGER.error(f"Error removing scheduled deletion: {e}")
            # Reset connection state and try to reconnect for next operation
            self._conn = None
            self._return = True
            await self.ensure_connection()

    async def get_pending_deletions(self):
        """Get messages that are due for deletion"""
        if not await self.ensure_connection():
            return []

        current_time = int(get_time())
        # Get current time for comparison

        try:
            # Check if connection is still valid before operation
            if self._conn is None or self._return:
                LOGGER.warning(
                    "Database connection not available for pending deletions retrieval"
                )
                return []

            # Create index for better performance if it doesn't exist
            await self.db.scheduled_deletions.create_index([("delete_time", 1)])

            # Get all documents for manual processing
            all_docs = []
            try:
                async for doc in self.db.scheduled_deletions.find():
                    all_docs.append(doc)
            except (PyMongoError, AttributeError) as e:
                LOGGER.error(f"Error retrieving scheduled deletions: {e}")
                # Reset connection state and try to reconnect
                self._conn = None
                self._return = True
                await self.ensure_connection()
                return []

            # Process documents manually to ensure we catch all due messages
            # Include a buffer of 30 seconds to catch messages that are almost due
            buffer_time = 30  # 30 seconds buffer

            # Use list comprehension for better performance and return directly
            # Messages found for deletion
            return [
                (doc["chat_id"], doc["message_id"], doc.get("bot_id", TgClient.ID))
                for doc in all_docs
                if doc.get("delete_time", 0) <= current_time + buffer_time
            ]
        except PyMongoError as e:
            LOGGER.error(f"Error in get_pending_deletions: {e}")
            await self.ensure_connection()  # Try to reconnect
            return []

    async def clean_old_scheduled_deletions(self, days=1):
        """Clean up scheduled deletion entries that have been processed but not removed

        Args:
            days: Number of days after which to clean up entries (default: 1)
        """
        if not await self.ensure_connection():
            return 0

        try:
            # Calculate the timestamp for 'days' ago
            one_day_ago = int(get_time() - (days * 86400))  # 86400 seconds = 1 day

            # Cleaning up old scheduled deletion entries

            # Get all entries to check which ones are actually old and processed
            entries_to_check = [
                doc async for doc in self.db.scheduled_deletions.find({})
            ]

            # Count entries by type
            current_time = int(get_time())
            past_due = [
                doc for doc in entries_to_check if doc["delete_time"] < current_time
            ]

            # Only delete entries that are more than 'days' old AND have already been processed
            # (i.e., their delete_time is in the past)
            deleted_count = 0
            for doc in past_due:
                # If the entry is more than 'days' old from its scheduled deletion time
                if doc["delete_time"] < one_day_ago:
                    result = await self.db.scheduled_deletions.delete_one(
                        {"_id": doc["_id"]},
                    )
                    if result.deleted_count > 0:
                        deleted_count += 1

            # No need to log cleanup results

            return deleted_count
        except PyMongoError as e:
            LOGGER.error(f"Error cleaning old scheduled deletions: {e}")
            await self.ensure_connection()  # Try to reconnect for next operation
            return 0

    async def get_all_scheduled_deletions(self):
        """Get all scheduled deletions for debugging purposes"""
        if not await self.ensure_connection():
            return []

        try:
            cursor = self.db.scheduled_deletions.find({})
            current_time = int(get_time())

            # Return all scheduled deletions
            result = [
                {
                    "chat_id": doc["chat_id"],
                    "message_id": doc["message_id"],
                    "delete_time": doc["delete_time"],
                    "bot_id": doc.get("bot_id", TgClient.ID),
                    "time_remaining": doc["delete_time"] - current_time
                    if "delete_time" in doc
                    else "unknown",
                    "is_due": doc["delete_time"]
                    <= current_time + 30  # 30 seconds buffer
                    if "delete_time" in doc
                    else False,
                }
                async for doc in cursor
            ]
        except PyMongoError as e:
            LOGGER.error(f"Error getting all scheduled deletions: {e}")
            await self.ensure_connection()  # Try to reconnect for next operation
            return []

        # Only log detailed information when called from check_deletion.py
        caller_frame = inspect.currentframe().f_back
        caller_name = caller_frame.f_code.co_name if caller_frame else "unknown"

        if "check_deletion" in caller_name:
            LOGGER.info(f"Found {len(result)} total scheduled deletions in database")
            if result:
                pending_count = sum(1 for item in result if item["is_due"])
                future_count = sum(1 for item in result if not item["is_due"])

                LOGGER.info(
                    f"Pending deletions: {pending_count}, Future deletions: {future_count}",
                )

                # Log some sample entries
                if result:
                    sample = result[:5] if len(result) > 5 else result
                    for entry in sample:
                        LOGGER.info(
                            f"Sample entry: {entry} - Due for deletion: {entry['is_due']}",
                        )

        return result

    async def store_user_cookie(self, user_id, cookie_number, cookie_data):
        """Store a user cookie in the database with a specific number"""
        if self._return:
            return False

        try:
            from time import time

            await self.db.user_cookies.update_one(
                {"user_id": user_id, "cookie_number": cookie_number},
                {
                    "$set": {
                        "cookie_data": cookie_data,
                        "created_at": int(time()),
                        "updated_at": int(time()),
                    }
                },
                upsert=True,
            )
            LOGGER.info(
                f"Stored cookie #{cookie_number} for user {user_id} in database"
            )
            return True
        except Exception as e:
            LOGGER.error(
                f"Error storing cookie #{cookie_number} for user {user_id}: {e}"
            )
            return False

    async def get_user_cookies(self, user_id):
        """Get all cookies for a user from the database"""
        if self._return:
            return []

        try:
            cookies = []
            cursor = self.db.user_cookies.find({"user_id": user_id}).sort(
                "cookie_number", 1
            )
            async for doc in cursor:
                cookies.append(
                    {
                        "number": doc["cookie_number"],
                        "data": doc["cookie_data"],
                        "created_at": doc.get("created_at", 0),
                        "updated_at": doc.get("updated_at", 0),
                    }
                )
            return cookies
        except Exception as e:
            LOGGER.error(f"Error getting cookies for user {user_id}: {e}")
            return []

    async def delete_user_cookie(self, user_id, cookie_number):
        """Delete a specific cookie for a user"""
        if self._return:
            return False

        try:
            result = await self.db.user_cookies.delete_one(
                {"user_id": user_id, "cookie_number": cookie_number}
            )
            if result.deleted_count > 0:
                LOGGER.info(f"Deleted cookie #{cookie_number} for user {user_id}")
                return True
            return False
        except Exception as e:
            LOGGER.error(
                f"Error deleting cookie #{cookie_number} for user {user_id}: {e}"
            )
            return False

    async def delete_all_user_cookies(self, user_id):
        """Delete all cookies for a user"""
        if self._return:
            return 0

        try:
            result = await self.db.user_cookies.delete_many({"user_id": user_id})
            LOGGER.info(f"Deleted {result.deleted_count} cookies for user {user_id}")
            return result.deleted_count
        except Exception as e:
            LOGGER.error(f"Error deleting all cookies for user {user_id}: {e}")
            return 0

    async def count_user_cookies_db(self, user_id):
        """Count the number of cookies for a user in the database"""
        if self._return:
            return 0

        try:
            return await self.db.user_cookies.count_documents({"user_id": user_id})
        except Exception as e:
            LOGGER.error(f"Error counting cookies for user {user_id}: {e}")
            return 0

    # Enhanced NSFW Detection Database Methods
    async def store_nsfw_detection(self, detection_data: dict):
        """Store NSFW detection result in database for analysis and improvement"""
        if self._return:
            return False

        try:
            # Add bot ID and ensure required fields
            detection_data.update({"bot_id": TgClient.ID, "stored_at": time.time()})

            await self.db.nsfw_detections.insert_one(detection_data)
            return True
        except Exception as e:
            LOGGER.error(f"Error storing NSFW detection data: {e}")
            return False

    async def get_nsfw_detection_stats(self, days: int = 7) -> dict:
        """Get NSFW detection statistics for the last N days"""
        if self._return:
            return {}

        try:
            cutoff_time = get_time() - (days * 86400)  # N days ago

            pipeline = [
                {
                    "$match": {
                        "bot_id": TgClient.ID,
                        "timestamp": {"$gte": cutoff_time},
                    }
                },
                {
                    "$group": {
                        "_id": None,
                        "total_detections": {"$sum": 1},
                        "nsfw_detected": {
                            "$sum": {"$cond": ["$detection_result.is_nsfw", 1, 0]}
                        },
                        "avg_confidence": {"$avg": "$detection_result.confidence"},
                        "content_types": {"$addToSet": "$content_type"},
                        "detection_methods": {
                            "$addToSet": "$detection_result.detection_methods"
                        },
                    }
                },
            ]

            cursor = self.db.nsfw_detections.aggregate(pipeline)
            result = await cursor.to_list(length=1)
            if result:
                stats = result[0]
                stats.pop("_id", None)
                return stats
            return {"total_detections": 0, "nsfw_detected": 0}

        except Exception as e:
            LOGGER.error(f"Error getting NSFW detection stats: {e}")
            return {}

    async def clean_old_nsfw_detections(self, days: int = 30):
        """Clean up old NSFW detection records"""
        if self._return:
            return 0

        try:
            cutoff_time = get_time() - (days * 86400)

            result = await self.db.nsfw_detections.delete_many(
                {"bot_id": TgClient.ID, "timestamp": {"$lt": cutoff_time}}
            )

            LOGGER.info(f"Cleaned {result.deleted_count} old NSFW detection records")
            return result.deleted_count

        except Exception as e:
            LOGGER.error(f"Error cleaning old NSFW detection records: {e}")
            return 0

    async def update_user_nsfw_behavior(
        self, user_id: int, nsfw_detected: bool, confidence: float
    ):
        """Track user NSFW behavior patterns"""
        if self._return:
            return

        try:
            current_time = get_time()

            # Update user behavior tracking
            update_data = {
                "$inc": {
                    "nsfw_total_checks": 1,
                    "nsfw_detected_count": 1 if nsfw_detected else 0,
                },
                "$set": {
                    "nsfw_last_check": current_time,
                    "nsfw_last_confidence": confidence,
                },
                "$push": {
                    "nsfw_recent_detections": {
                        "$each": [
                            {
                                "timestamp": current_time,
                                "detected": nsfw_detected,
                                "confidence": confidence,
                            }
                        ],
                        "$slice": -50,  # Keep only last 50 detections
                    }
                },
            }

            await self.db.users.update_one(
                {"_id": user_id}, update_data, upsert=True
            )

        except Exception as e:
            LOGGER.error(f"Error updating user NSFW behavior for {user_id}: {e}")

    # Removed get_user_nsfw_behavior method as user behavior commands were removed

    # ReelNN-Style Media Storage - Exact Implementation
    async def store_media_metadata(self, media_data: dict):
        """Store media metadata using exact ReelNN database schema"""
        if self._return:
            return None
        try:
            from time import time

            # Validate required fields - ReelNN style
            required_fields = ["hash_id", "file_name", "file_size"]
            if not all(field in media_data for field in required_fields):
                LOGGER.error(
                    f"Missing required fields in media_data: {required_fields}"
                )
                return None

            # Extract TMDB data if available
            tmdb_data = media_data.get("tmdb_data", {})

            # ReelNN-style metadata structure - exact schema
            current_time = time()

            # Determine media type based on ReelNN logic
            is_tv_show = bool(
                media_data.get("series_data")
                or media_data.get("season")
                or media_data.get("episode")
            )
            media_type = "tv" if is_tv_show else "movie"

            # Create ReelNN document structure
            reelnn_document = {
                # Core identifiers - ReelNN style
                "mid": media_data.get("hash_id"),  # ReelNN uses 'mid' for movie ID
                "sid": media_data.get("hash_id")
                if is_tv_show
                else None,  # ReelNN uses 'sid' for show ID
                "hash_id": media_data.get("hash_id"),  # Keep for compatibility
                "original_hash_id": media_data.get(
                    "original_hash_id", media_data.get("hash_id")
                ),
                # File metadata
                "file_name": media_data.get("file_name"),
                "file_size": media_data.get("file_size"),
                "mime_type": media_data.get("mime_type"),
                "duration": media_data.get("duration"),
                "width": media_data.get("width"),
                "height": media_data.get("height"),
                # ReelNN content fields - exact structure
                "title": tmdb_data.get("title")
                or tmdb_data.get("name")
                or media_data.get("enhanced_title")
                or media_data.get("file_name", "").split(".")[0],
                "original_title": tmdb_data.get("original_title")
                or tmdb_data.get("original_name"),
                "overview": tmdb_data.get("overview"),
                "tagline": tmdb_data.get("tagline"),
                "release_date": tmdb_data.get("release_date"),
                "first_air_date": tmdb_data.get("first_air_date"),
                "last_air_date": tmdb_data.get("last_air_date"),
                # ReelNN rating and popularity
                "vote_average": tmdb_data.get("vote_average"),
                "vote_count": tmdb_data.get("vote_count"),
                "popularity": tmdb_data.get("popularity"),
                # ReelNN media classification
                "media_type": media_type,
                "is_series": is_tv_show,
                "genres": tmdb_data.get("genres", []),
                "production_companies": tmdb_data.get("production_companies", []),
                "production_countries": tmdb_data.get("production_countries", []),
                "spoken_languages": tmdb_data.get("spoken_languages", []),
                # ReelNN image paths
                "poster_path": tmdb_data.get("poster_path"),
                "backdrop_path": tmdb_data.get("backdrop_path"),
                # ReelNN runtime and status
                "runtime": tmdb_data.get("runtime") or media_data.get("duration"),
                "status": tmdb_data.get("status", "Released"),
                # ReelNN quality and technical info
                "quality": self._extract_quality_reelnn(
                    media_data.get("file_name", "")
                ),
                "file_format": media_data.get("file_name", "").split(".")[-1].upper()
                if "." in media_data.get("file_name", "")
                else "MP4",
                "streamable": media_data.get("is_streamable", True),
                # ReelNN series information (for TV shows)
                "number_of_seasons": tmdb_data.get("number_of_seasons")
                if is_tv_show
                else None,
                "number_of_episodes": tmdb_data.get("number_of_episodes")
                if is_tv_show
                else None,
                "season_number": media_data.get("season"),
                "episode_number": media_data.get("episode"),
                "series_name": media_data.get("unique_name") if is_tv_show else None,
                # ReelNN indexing and management
                "indexed_at": current_time,
                "last_updated": current_time,
                "view_count": 0,
                "last_viewed": None,
                "featured": False,
                "trending_score": 0,
                "active": True,  # ReelNN uses 'active' field
                # ReelNN external IDs
                "imdb_id": tmdb_data.get("imdb_id"),
                "tmdb_id": tmdb_data.get("id"),
                # Telegram metadata
                "message_id": media_data.get("message_id"),
                "chat_id": media_data.get("chat_id"),
                "bot_id": TgClient.ID,
                # Full TMDB data for reference
                "tmdb_data": tmdb_data,
                # Legacy compatibility fields
                "enhanced_title": media_data.get("enhanced_title"),
                "category": media_data.get("category"),
                "series_data": media_data.get("series_data"),
                "unique_name": media_data.get("unique_name"),
                "quality_group_id": media_data.get("quality_group_id"),
                "is_video": media_data.get("is_video", False),
                "is_audio": media_data.get("is_audio", False),
                "is_image": media_data.get("is_image", False),
                "indexed": True,
            }

            # Store in ReelNN collection with upsert
            # Use $setOnInsert for created_at to avoid conflicts
            result = await self.db.media_library[TgClient.ID].update_one(
                {"hash_id": media_data["hash_id"]},
                {
                    "$set": reelnn_document,
                    "$setOnInsert": {"created_at": current_time},
                },
                upsert=True,
            )

            # Selective cache invalidation for better performance
            from bot.helper.stream_utils.cache_manager import CacheManager

            # Only invalidate specific file cache
            CacheManager.invalidate_file_cache(media_data["hash_id"])

            # Only invalidate category cache if category changed
            if result.modified_count > 0:  # Only if document was actually modified
                cache_key = f"category_counts_{TgClient.ID}"
                if cache_key in self._category_cache:
                    del self._category_cache[cache_key]
                if cache_key in self._category_cache_time:
                    del self._category_cache_time[cache_key]

                # Only invalidate media list caches for the specific category
                category = media_data.get("category", "document")
                self._invalidate_category_media_caches(category)
                LOGGER.info(f"Invalidated caches for category: {category}")
            else:
                LOGGER.info("No cache invalidation needed - new media entry")

            return result.upserted_id or media_data["hash_id"]
        except Exception as e:
            LOGGER.error(f"Error storing media metadata: {e}")
            return None

    def _extract_quality_reelnn(self, filename: str) -> str:
        """Extract quality information from filename using ReelNN patterns"""
        if not filename:
            return "HD"

        filename_lower = filename.lower()

        # ReelNN quality detection patterns
        quality_patterns = {
            "4K": ["2160p", "4k", "uhd"],
            "1080p": ["1080p", "fhd"],
            "720p": ["720p", "hd"],
            "480p": ["480p", "sd"],
            "360p": ["360p"],
            "CAM": ["cam", "camrip"],
            "TS": ["ts", "telesync"],
            "TC": ["tc", "telecine"],
            "WEB-DL": ["web-dl", "webdl"],
            "WEBRip": ["webrip", "web-rip"],
            "BluRay": ["bluray", "bdrip", "brrip"],
            "DVDRip": ["dvdrip", "dvd-rip"],
            "HDRip": ["hdrip", "hd-rip"],
        }

        # Check for quality patterns
        for quality, patterns in quality_patterns.items():
            if any(pattern in filename_lower for pattern in patterns):
                return quality

        # Default quality based on file size or other indicators
        return "HD"

    # ReelNN-Style API Methods - Exact Implementation
    async def get_trending_media(self, limit: int = 20) -> list:
        """Get trending media using exact ReelNN algorithm"""
        if self._return:
            return []
        try:
            collection = self.db.media_library[TgClient.ID]

            # ReelNN trending algorithm - exact implementation
            pipeline = [
                {
                    "$match": {
                        "active": True,
                        "streamable": True,
                        "$or": [{"media_type": "movie"}, {"media_type": "tv"}],
                    }
                },
                {
                    "$addFields": {
                        "trending_score": {
                            "$add": [
                                {
                                    "$multiply": [{"$ifNull": ["$view_count", 0]}, 3]
                                },  # Views weight
                                {
                                    "$multiply": [{"$ifNull": ["$popularity", 0]}, 2]
                                },  # TMDB popularity
                                {
                                    "$multiply": [
                                        {"$ifNull": ["$vote_average", 0]},
                                        10,
                                    ]
                                },  # Rating weight
                                {
                                    "$cond": {  # Recency bonus
                                        "if": {
                                            "$gte": [
                                                "$indexed_at",
                                                {
                                                    "$subtract": [
                                                        {"$toDouble": "$$NOW"},
                                                        604800,
                                                    ]
                                                },
                                            ]
                                        },  # 7 days
                                        "then": 50,
                                        "else": 0,
                                    }
                                },
                            ]
                        }
                    }
                },
                {
                    "$sort": {
                        "trending_score": -1,
                        "vote_average": -1,
                        "indexed_at": -1,
                    }
                },
                {"$limit": limit},
                {
                    "$project": {
                        "mid": {"$ifNull": ["$mid", "$hash_id"]},
                        "sid": {"$ifNull": ["$sid", "$hash_id"]},
                        "title": 1,
                        "original_title": 1,
                        "overview": 1,
                        "poster_path": 1,
                        "backdrop_path": 1,
                        "vote_average": 1,
                        "release_date": 1,
                        "first_air_date": 1,
                        "genres": 1,
                        "media_type": 1,
                        "quality": 1,
                        "runtime": 1,
                        "trending_score": 1,
                        "view_count": 1,
                        "streamable": 1,
                    }
                },
            ]

            # Use proper async aggregation according to MongoDB docs
            # Handle both Motor and PyMongo async cases
            try:
                cursor = collection.aggregate(pipeline)
                # Check if cursor is a coroutine (newer PyMongo async) or Motor cursor
                if hasattr(cursor, "__await__"):
                    # PyMongo async - cursor is a coroutine
                    cursor = await cursor
                    return await cursor.to_list(length=limit)
                # Motor - cursor is returned immediately
                return await cursor.to_list(length=limit)
            except AttributeError:
                # Fallback: use async for iteration
                results = []
                async for document in collection.aggregate(pipeline):
                    results.append(document)
                    if len(results) >= limit:
                        break
                return results
        except Exception as e:
            LOGGER.error(f"Error getting trending media: {e}")
            return []

    async def get_hero_slider_media(self, limit: int = 5) -> list:
        """Get media for hero slider using ReelNN's selection algorithm"""
        if self._return:
            return []
        try:
            # ReelNN hero slider: featured + high quality + good backdrop
            query = {
                "is_video": True,
                "active": True,
                "tmdb_data.backdrop_path": {"$exists": True, "$ne": None},
                "$or": [
                    {"featured": True},
                    {
                        "$and": [
                            {"tmdb_data.vote_average": {"$gte": 6.5}},
                            {"view_count": {"$gte": 3}},
                            {"quality": {"$in": ["1080p", "4K", "2160p", "720p"]}},
                        ]
                    },
                ],
            }

            cursor = (
                self.db.media_library[TgClient.ID]
                .find(query)
                .sort(
                    [
                        ("featured", -1),
                        ("tmdb_data.popularity", -1),
                        ("view_count", -1),
                    ]
                )
                .limit(limit)
            )
            return await cursor.to_list(length=limit)
        except Exception as e:
            LOGGER.error(f"Error getting hero slider media: {e}")
            return []

    async def increment_view_count(self, hash_id: str) -> bool:
        """Increment view count for media item - ReelNN style"""
        if self._return:
            return False
        try:
            result = await self.db.media_library[TgClient.ID].update_one(
                {"hash_id": hash_id},
                {"$inc": {"view_count": 1}, "$set": {"last_viewed": datetime.now()}},
            )
            return result.modified_count > 0
        except Exception as e:
            LOGGER.error(f"Error incrementing view count: {e}")
            return False

    async def get_recent_media(
        self, limit: int = 20, media_type: str | None = None
    ) -> list:
        """Get recently added media for ReelNN"""
        if self._return:
            return []
        try:
            collection = self.db.media_library[TgClient.ID]

            query = {"status": "active", "streamable": True}
            if media_type:
                query["media_type"] = media_type

            # Use proper async cursor iteration according to MongoDB docs
            cursor = collection.find(query).sort("indexed_at", -1).limit(limit)
            results = []
            async for document in cursor:
                results.append(document)
            return results
        except Exception as e:
            LOGGER.error(f"Error getting recent media: {e}")
            return []

    async def get_featured_media(self, limit: int = 10) -> list:
        """Get featured media for ReelNN hero slider"""
        if self._return:
            return []
        try:
            collection = self.db.media_library[TgClient.ID]

            # ReelNN hero slider algorithm - high quality content with backdrops
            pipeline = [
                {
                    "$match": {
                        "active": True,
                        "streamable": True,
                        "$or": [
                            {"featured": True},  # Manually featured content
                            {
                                "$and": [
                                    {"vote_average": {"$gte": 7.0}},  # High-rated
                                    {
                                        "backdrop_path": {
                                            "$exists": True,
                                            "$ne": None,
                                        }
                                    },  # Has backdrop
                                    {
                                        "$or": [
                                            {
                                                "popularity": {"$gte": 100}
                                            },  # Popular on TMDB
                                            {
                                                "view_count": {"$gte": 10}
                                            },  # Popular locally
                                        ]
                                    },
                                ]
                            },
                        ],
                    }
                },
                {
                    "$addFields": {
                        "hero_score": {
                            "$add": [
                                {
                                    "$multiply": [
                                        {"$ifNull": ["$vote_average", 0]},
                                        15,
                                    ]
                                },  # Rating priority
                                {
                                    "$multiply": [
                                        {"$ifNull": ["$popularity", 0]},
                                        0.1,
                                    ]
                                },  # TMDB popularity
                                {
                                    "$multiply": [{"$ifNull": ["$view_count", 0]}, 5]
                                },  # Local views
                                {
                                    "$cond": {
                                        "if": "$featured",
                                        "then": 100,
                                        "else": 0,
                                    }
                                },  # Featured bonus
                            ]
                        }
                    }
                },
                {"$sort": {"hero_score": -1, "indexed_at": -1}},
                {"$limit": limit},
            ]

            # Use proper async aggregation according to MongoDB docs
            # Handle both Motor and PyMongo async cases
            try:
                cursor = collection.aggregate(pipeline)
                # Check if cursor is a coroutine (newer PyMongo async) or Motor cursor
                if hasattr(cursor, "__await__"):
                    # PyMongo async - cursor is a coroutine
                    cursor = await cursor
                    return await cursor.to_list(length=limit)
                # Motor - cursor is returned immediately
                return await cursor.to_list(length=limit)
            except AttributeError:
                # Fallback: use async for iteration
                results = []
                async for document in collection.aggregate(pipeline):
                    results.append(document)
                    if len(results) >= limit:
                        break
                return results
        except Exception as e:
            LOGGER.error(f"Error getting featured media: {e}")
            return []

    async def search_media_reelnn(self, query: str, limit: int = 20) -> list:
        """ReelNN-style search with TMDB data"""
        if self._return:
            return []
        try:
            collection = self.db.media_library[TgClient.ID]

            search_query = {
                "$and": [
                    {"status": "active", "streamable": True},
                    {
                        "$or": [
                            {"title": {"$regex": query, "$options": "i"}},
                            {"original_title": {"$regex": query, "$options": "i"}},
                            {"file_name": {"$regex": query, "$options": "i"}},
                            {"overview": {"$regex": query, "$options": "i"}},
                            {"genres.name": {"$regex": query, "$options": "i"}},
                        ]
                    },
                ]
            }

            cursor = (
                collection.find(search_query)
                .sort([("vote_average", -1), ("view_count", -1)])
                .limit(limit)
            )
            return await cursor.to_list(length=limit)
        except Exception as e:
            LOGGER.error(f"Error searching media: {e}")
            return []

    async def get_movies_paginated_reelnn(
        self,
        page: int = 1,
        limit: int = 24,
        genre: str | None = None,
        year: str | None = None,
        sort: str = "recent",
    ) -> dict:
        """Get paginated movies for ReelNN browse page"""
        if self._return:
            return {"movies": [], "total": 0, "pages": 0}
        try:
            collection = self.db.media_library[TgClient.ID]
            skip = (page - 1) * limit

            # Build query
            query = {"media_type": "movie", "status": "active", "streamable": True}
            if genre:
                query["genres.name"] = {"$regex": genre, "$options": "i"}
            if year:
                query["release_date"] = {"$regex": f"^{year}"}

            # Sort options
            sort_options = {
                "recent": ("indexed_at", -1),
                "popular": ("view_count", -1),
                "rating": ("vote_average", -1),
                "title": ("title", 1),
                "year": ("release_date", -1),
            }
            sort_field, sort_direction = sort_options.get(sort, ("indexed_at", -1))

            # Get total count
            total = await collection.count_documents(query)
            pages = (total + limit - 1) // limit

            # Get movies
            cursor = (
                collection.find(query)
                .sort(sort_field, sort_direction)
                .skip(skip)
                .limit(limit)
            )
            movies = await cursor.to_list(length=limit)

            return {"movies": movies, "total": total, "pages": pages}
        except Exception as e:
            LOGGER.error(f"Error getting paginated movies: {e}")
            return {"movies": [], "total": 0, "pages": 0}

    async def get_shows_paginated_reelnn(
        self,
        page: int = 1,
        limit: int = 24,
        genre: str | None = None,
        status: str | None = None,
        sort: str = "recent",
    ) -> dict:
        """Get paginated TV shows for ReelNN browse page"""
        if self._return:
            return {"shows": [], "total": 0, "pages": 0}
        try:
            collection = self.db.media_library[TgClient.ID]
            skip = (page - 1) * limit

            # Build query
            query = {"media_type": "tv", "status": "active", "streamable": True}
            if genre:
                query["genres.name"] = {"$regex": genre, "$options": "i"}
            if status:
                query["status"] = status

            # Sort options
            sort_options = {
                "recent": ("indexed_at", -1),
                "popular": ("view_count", -1),
                "rating": ("vote_average", -1),
                "title": ("title", 1),
                "year": ("first_air_date", -1),
            }
            sort_field, sort_direction = sort_options.get(sort, ("indexed_at", -1))

            # Get total count
            total = await collection.count_documents(query)
            pages = (total + limit - 1) // limit

            # Get shows
            cursor = (
                collection.find(query)
                .sort(sort_field, sort_direction)
                .skip(skip)
                .limit(limit)
            )
            shows = await cursor.to_list(length=limit)

            return {"shows": shows, "total": total, "pages": pages}
        except Exception as e:
            LOGGER.error(f"Error getting paginated shows: {e}")
            return {"shows": [], "total": 0, "pages": 0}

    async def get_media_metadata(self, hash_id: str):
        """Get media metadata by hash ID"""
        if self._return:
            return None
        try:
            return await self.db.media_library[TgClient.ID].find_one(
                {"hash_id": hash_id}
            )
        except Exception as e:
            LOGGER.error(f"Error getting media metadata: {e}")
            return None

    async def find_media_by_original_hash(self, original_hash_id: str):
        """Find media by original_hash_id field (for grouped media)"""
        if self._return:
            return None
        try:
            return await self.db.media_library[TgClient.ID].find_one(
                {"original_hash_id": original_hash_id}
            )
        except Exception as e:
            LOGGER.error(f"Error finding media by original hash: {e}")
            return None

    async def find_media_by_series_episode(
        self, series_name: str, season: int, episode: int
    ):
        """Find media by series name, season, and episode"""
        if self._return:
            return None
        try:
            return await self.db.media_library[TgClient.ID].find_one(
                {"series_name": series_name, "season": season, "episode": episode}
            )
        except Exception as e:
            LOGGER.error(f"Error finding media by series episode: {e}")
            return None

    # REMOVED: Duplicate find_media_by_original_hash method - using the one above

    async def get_all_media_metadata(self):
        """Get all media metadata (for fallback search)"""
        if self._return:
            return []
        try:
            cursor = self.db.media_library[TgClient.ID].find({})
            return await cursor.to_list(length=None)
        except Exception as e:
            LOGGER.error(f"Error getting all media metadata: {e}")
            return []

    async def get_all_media(
        self,
        limit: int = 50,
        skip: int = 0,
        search: str | None = None,
        media_type: str | None = None,
        sort_by: str = "recent",
    ):
        """Optimized media retrieval with caching and efficient queries"""
        if self._return:
            return []
        try:
            # Ensure database connection is available
            if not await self.ensure_connection():
                LOGGER.warning("Database connection not available for get_all_media")
                return []

            if self.db is None:
                LOGGER.warning("Database object is None in get_all_media")
                return []

            if not hasattr(TgClient, "ID") or TgClient.ID is None:
                LOGGER.warning("TgClient.ID is not set for get_all_media")
                return []
            # Create cache key for this query
            from bot.helper.stream_utils.cache_manager import CacheManager

            cache_key = f"media_list_{TgClient.ID}_{limit}_{skip}_{search}_{media_type}_{sort_by}"
            cached_result = CacheManager.get_cached_file_info(cache_key)
            if cached_result:
                return cached_result

            query = {}

            # Optimized search filter with text index
            if search:
                # Use text search if available, fallback to regex
                query["$text"] = {"$search": search}

            # Enhanced media type filter with support for multiple categories
            if media_type:
                if media_type in [
                    "movie",
                    "series",
                    "anime",
                    "music",
                    "library",
                    "document",
                ]:
                    # Check both primary category and categories array
                    query["$or"] = [
                        {"category": media_type},
                        {"categories": {"$in": [media_type]}},
                    ]
                elif media_type == "video":
                    query["$or"] = [
                        {"category": {"$in": ["movie", "series", "anime"]}},
                        {"categories": {"$in": ["movie", "series", "anime"]}},
                    ]
                elif media_type == "audio":
                    query["$or"] = [
                        {"category": "music"},
                        {"categories": {"$in": ["music"]}},
                    ]
                elif media_type == "image":
                    query["is_image"] = True
                elif media_type == "document":
                    query["$and"] = [
                        {
                            "category": {
                                "$nin": ["movie", "series", "anime", "music"]
                            }
                        },
                        {
                            "categories": {
                                "$nin": ["movie", "series", "anime", "music"]
                            }
                        },
                    ]

            # Enhanced sort configuration with trending logic
            sort_config = {
                "recent": ("created_at", -1),
                "popular": ("view_count", -1),
                "trending": None,  # Special handling for trending
                "name": ("file_name", 1),
                "size": ("file_size", -1),
            }

            # Use projection to limit returned fields for better performance
            projection = {
                "hash_id": 1,
                "file_name": 1,
                "file_size": 1,
                "file_size_human": 1,
                "mime_type": 1,
                "category": 1,
                "thumbnail": 1,
                "view_count": 1,
                "created_at": 1,
                "is_video": 1,
                "is_audio": 1,
                "is_image": 1,
                "duration": 1,
            }

            # Handle trending sort with simplified logic (avoid complex aggregation)
            if sort_by == "trending":
                try:
                    # Simplified trending: Sort by view_count first, then by created_at for recent files
                    # This avoids complex aggregation while still providing meaningful trending results
                    LOGGER.info(
                        "Using simplified trending sort (view_count + recent)"
                    )

                    # Use a compound sort: view_count descending, then created_at descending
                    sort_field = [("view_count", -1), ("created_at", -1)]

                    cursor = (
                        self.db.media_library[TgClient.ID]
                        .find(query, projection)
                        .sort(sort_field)
                        .skip(skip)
                        .limit(limit)
                    )

                    result = await cursor.to_list(length=limit)

                    # Cache result for 5 minutes (trending changes more frequently)
                    CacheManager.cache_file_info(cache_key, result)
                    return result

                except Exception as trending_error:
                    LOGGER.warning(
                        f"Simplified trending sort failed: {trending_error}, falling back to recent sort"
                    )
                    sort_by = "recent"

            sort_field, sort_direction = sort_config.get(sort_by, ("created_at", -1))

            cursor = (
                self.db.media_library[TgClient.ID]
                .find(query, projection)
                .sort(sort_field, sort_direction)
                .skip(skip)
                .limit(limit)
            )

            result = await cursor.to_list(length=limit)

            # Cache result for 2 minutes
            CacheManager.cache_file_info(cache_key, result)

            return result
        except Exception as e:
            LOGGER.error(f"Error getting media list: {e}")
            return []

    async def get_media_count(
        self, search: str | None = None, media_type: str | None = None
    ):
        """Get total count of media with filters"""
        if self._return:
            return 0
        try:
            query = {}

            # Add search filter
            if search:
                query["$or"] = [
                    {"file_name": {"$regex": search, "$options": "i"}},
                    {"title": {"$regex": search, "$options": "i"}},
                    {"description": {"$regex": search, "$options": "i"}},
                ]

            # Add media type filter
            if media_type:
                if media_type == "video":
                    query["is_video"] = True
                elif media_type == "audio":
                    query["is_audio"] = True
                elif media_type == "image":
                    query["is_image"] = True
                elif media_type == "document":
                    query["$and"] = [
                        {"is_video": {"$ne": True}},
                        {"is_audio": {"$ne": True}},
                        {"is_image": {"$ne": True}},
                    ]

            return await self.db.media_library[TgClient.ID].count_documents(query)
        except Exception as e:
            LOGGER.error(f"Error getting media count: {e}")
            return 0

    def _invalidate_all_media_caches(self):
        """Invalidate all media list caches to ensure immediate website updates"""
        try:
            from bot.helper.stream_utils.cache_manager import CacheManager

            # Clear all media list caches by pattern
            # The cache keys follow pattern: f"media_list_{TgClient.ID}_{limit}_{skip}_{search}_{media_type}_{sort_by}"
            if hasattr(CacheManager, "_file_cache") and CacheManager._file_cache:
                # Get all cache keys that start with media_list pattern
                cache_keys_to_remove = []
                for key in CacheManager._file_cache._cache:
                    if key.startswith(f"media_list_{TgClient.ID}_"):
                        cache_keys_to_remove.append(key)

                # Remove all matching cache entries
                for key in cache_keys_to_remove:
                    if key in CacheManager._file_cache._cache:
                        del CacheManager._file_cache._cache[key]

                LOGGER.info(
                    f"Invalidated {len(cache_keys_to_remove)} media list cache entries"
                )

            # Also clear search results cache
            try:
                from bot.modules.media_search import SEARCH_RESULTS_CACHE

                if hasattr(SEARCH_RESULTS_CACHE, "cache"):
                    SEARCH_RESULTS_CACHE.cache.clear()
                    SEARCH_RESULTS_CACHE.access_order.clear()
                    LOGGER.info("Invalidated search results cache")
            except ImportError:
                pass  # Search module might not be available

        except Exception as e:
            LOGGER.error(f"Error invalidating media list caches: {e}")

    def _invalidate_category_media_caches(self, category: str):
        """Invalidate media list caches for a specific category"""
        try:
            from bot.helper.stream_utils.cache_manager import CacheManager

            if hasattr(CacheManager, "_file_cache") and CacheManager._file_cache:
                cache_keys_to_remove = []
                for key in list(CacheManager._file_cache._cache.keys()):
                    # Invalidate caches that might contain this category
                    if key.startswith(f"media_list_{TgClient.ID}_") and (
                        category in key or "None" in key
                    ):  # None for no filter
                        cache_keys_to_remove.append(key)

                for key in cache_keys_to_remove:
                    if key in CacheManager._file_cache._cache:
                        del CacheManager._file_cache._cache[key]

                LOGGER.info(
                    f"Invalidated {len(cache_keys_to_remove)} category-specific cache entries"
                )

        except Exception as e:
            LOGGER.error(f"Error invalidating category caches: {e}")

    async def delete_media_metadata(self, hash_id: str):
        """Delete media metadata"""
        if self._return:
            return False
        try:
            result = await self.db.media_library[TgClient.ID].delete_one(
                {"hash_id": hash_id}
            )

            if result.deleted_count > 0:
                # Invalidate category cache to ensure immediate website updates
                cache_key = f"category_counts_{TgClient.ID}"
                if cache_key in self._category_cache:
                    del self._category_cache[cache_key]
                if cache_key in self._category_cache_time:
                    del self._category_cache_time[cache_key]
                LOGGER.info(
                    f"Invalidated category cache after deleting media: {hash_id}"
                )

                # Invalidate ALL media list caches to ensure immediate website updates
                self._invalidate_all_media_caches()
                LOGGER.info(
                    f"Invalidated all media list caches after deleting media: {hash_id}"
                )

            return result.deleted_count > 0
        except Exception as e:
            LOGGER.error(f"Error deleting media metadata: {e}")
            return False

    async def update_media_views(self, hash_id: str):
        """Increment view count for media"""
        if self._return:
            return
        try:
            from time import time

            await self.db.media_library[TgClient.ID].update_one(
                {"hash_id": hash_id},
                {"$inc": {"view_count": 1}, "$set": {"last_viewed": time()}},
            )
        except Exception as e:
            LOGGER.error(f"Error updating media views: {e}")

    # Quality Groups Management
    async def store_quality_group(self, group_data: dict):
        """Store quality group information"""
        if self._return:
            return None
        try:
            result = await self.db.quality_groups[TgClient.ID].replace_one(
                {"group_id": group_data["group_id"]}, group_data, upsert=True
            )
            LOGGER.info(
                f"Stored quality group {group_data['group_id']} with {len(group_data['qualities'])} qualities"
            )
            return result.upserted_id or group_data["group_id"]
        except Exception as e:
            LOGGER.error(f"Error storing quality group: {e}")
            return None

    async def get_quality_group(self, group_id: str) -> dict:
        """Get quality group by group_id"""
        if self._return:
            return None
        try:
            return await self.db.quality_groups[TgClient.ID].find_one(
                {"group_id": group_id}
            )
        except Exception as e:
            LOGGER.error(f"Error getting quality group: {e}")
            return None

    async def get_quality_group_by_hash(self, hash_id: str) -> dict:
        """Get quality group by any member hash_id"""
        if self._return:
            return None
        try:
            # First get the media entry to find group_id
            media = await self.db.media_library[TgClient.ID].find_one(
                {"hash_id": hash_id}
            )
            if not media or not media.get("quality_group_id"):
                return None
            # Then get the full group
            return await self.get_quality_group(media["quality_group_id"])
        except Exception as e:
            LOGGER.error(f"Error getting quality group by hash: {e}")
            return None

    async def update_quality_group(self, group_data: dict):
        """Update existing quality group"""
        if self._return:
            return False
        try:
            result = await self.db.quality_groups[TgClient.ID].replace_one(
                {"group_id": group_data["group_id"]}, group_data
            )
            return result.modified_count > 0
        except Exception as e:
            LOGGER.error(f"Error updating quality group: {e}")
            return False

    async def update_media_quality_group(
        self, hash_id: str, group_id: str, quality: str, default_quality: str
    ):
        """Update media entry with quality group information"""
        if self._return:
            return False
        try:
            result = await self.db.media_library[
                TgClient.ID
            ].update_one(
                {"hash_id": hash_id},
                {
                    "$set": {
                        "quality_group_id": group_id,
                        "quality_label": quality,
                        "is_part_of_group": True,
                        "group_default_quality": default_quality,
                        "base_filename": group_id,  # Use group_id as base_filename for grouping
                    }
                },
            )
            return result.modified_count > 0
        except Exception as e:
            LOGGER.error(f"Error updating media quality group: {e}")
            return False

    async def update_media_quality_info(
        self, hash_id: str, quality: str, base_filename: str
    ):
        """Update media entry with quality info (single quality file)"""
        if self._return:
            return False
        try:
            result = await self.db.media_library[TgClient.ID].update_one(
                {"hash_id": hash_id},
                {
                    "$set": {
                        "quality_label": quality,
                        "is_part_of_group": False,
                        "base_filename": base_filename,
                    }
                },
            )
            return result.modified_count > 0
        except Exception as e:
            LOGGER.error(f"Error updating media quality info: {e}")
            return False

    async def get_all_quality_groups(self, limit: int = 50, skip: int = 0) -> list:
        """Get all quality groups for admin panel"""
        if self._return:
            return []
        try:
            cursor = (
                self.db.quality_groups[TgClient.ID]
                .find({})
                .sort("created_at", -1)
                .skip(skip)
                .limit(limit)
            )
            return await cursor.to_list(length=limit)
        except Exception as e:
            LOGGER.error(f"Error getting quality groups: {e}")
            return []

    async def get_ungrouped_media(self, limit: int = 50) -> list:
        """Get media files that are not part of any quality group"""
        if self._return:
            return []
        try:
            cursor = (
                self.db.media_library[TgClient.ID]
                .find({"is_part_of_group": {"$ne": True}})
                .sort("created_at", -1)
                .limit(limit)
            )
            return await cursor.to_list(length=limit)
        except Exception as e:
            LOGGER.error(f"Error getting ungrouped media: {e}")
            return []

    async def remove_quality_from_group(self, group_id: str, quality: str) -> bool:
        """Remove specific quality from group"""
        if self._return:
            return False
        try:
            # Get group data
            group = await self.get_quality_group(group_id)
            if not group or quality not in group.get("qualities", {}):
                return False

            # Get hash_id of quality to remove
            quality_data = group["qualities"][quality]
            hash_id = quality_data["hash_id"]

            # Remove quality from group
            del group["qualities"][quality]
            group["total_size"] -= quality_data.get("file_size", 0)
            group["last_updated"] = time.time()

            # If no qualities left, delete group
            if not group["qualities"]:
                await self.db.quality_groups[TgClient.ID].delete_one(
                    {"group_id": group_id}
                )
                # Update media entry to remove group reference
                await self.db.media_library[TgClient.ID].update_one(
                    {"hash_id": hash_id},
                    {
                        "$unset": {
                            "quality_group_id": "",
                            "is_part_of_group": "",
                            "group_default_quality": "",
                        }
                    },
                )
                return True

            # Recalculate default quality
            from bot.helper.stream_utils.quality_handler import QualityHandler

            available_qualities = list(group["qualities"].keys())
            quality_priorities = {
                q: QualityHandler.SUPPORTED_QUALITIES.get(q, {"priority": 999})[
                    "priority"
                ]
                for q in available_qualities
            }
            group["default_quality"] = min(
                quality_priorities, key=quality_priorities.get
            )

            # Update group
            await self.update_quality_group(group)

            # Update media entry to remove group reference
            await self.db.media_library[TgClient.ID].update_one(
                {"hash_id": hash_id},
                {
                    "$unset": {
                        "quality_group_id": "",
                        "is_part_of_group": "",
                        "group_default_quality": "",
                    }
                },
            )

            return True
        except Exception as e:
            LOGGER.error(f"Error removing quality from group: {e}")
            return False

    async def delete_quality_group(self, group_id: str) -> bool:
        """Delete entire quality group"""
        if self._return:
            return False
        try:
            # Get group data to find all hash_ids
            group = await self.get_quality_group(group_id)
            if not group:
                return False

            # Remove group references from all media entries
            hash_ids = [
                quality_data["hash_id"]
                for quality_data in group["qualities"].values()
            ]
            await self.db.media_library[TgClient.ID].update_many(
                {"hash_id": {"$in": hash_ids}},
                {
                    "$unset": {
                        "quality_group_id": "",
                        "is_part_of_group": "",
                        "group_default_quality": "",
                    }
                },
            )

            # Delete the group
            result = await self.db.quality_groups[TgClient.ID].delete_one(
                {"group_id": group_id}
            )
            return result.deleted_count > 0
        except Exception as e:
            LOGGER.error(f"Error deleting quality group: {e}")
            return False

    async def update_media_thumbnail(
        self, hash_id: str, thumbnail_file_id: str | None = None
    ):
        """Update or remove thumbnail file_id for media"""
        if self._return:
            return
        try:
            from time import time

            update_data = {"last_updated": time()}

            if thumbnail_file_id is None:
                # Remove the thumbnail_file_id field
                await self.db.media_library[TgClient.ID].update_one(
                    {"hash_id": hash_id},
                    {
                        "$unset": {"thumbnail_file_id": "", "thumbnail": ""},
                        "$set": update_data,
                    },
                )
                LOGGER.info(f"Removed thumbnail file_id from database for {hash_id}")
            else:
                # Update the thumbnail_file_id
                update_data.update(
                    {
                        "thumbnail_file_id": thumbnail_file_id,
                        "thumbnail": thumbnail_file_id,  # Keep both for compatibility
                    }
                )
                await self.db.media_library[TgClient.ID].update_one(
                    {"hash_id": hash_id}, {"$set": update_data}
                )
                LOGGER.info(f"Updated thumbnail file_id for {hash_id}")
        except Exception as e:
            LOGGER.error(f"Error updating media thumbnail: {e}")

    # Removed redundant delete_media_file method - use delete_media_metadata instead

    # Removed redundant get_media_files method - use get_all_media instead

    async def get_series_data(
        self, series_name: str | None = None, season: str | None = None
    ):
        """Get series data with episodes grouped by series and seasons"""
        if self._return:
            return {
                "series_list": [],
                "episodes": [],
                "seasons": [],
                "series_info": {},
            }
        try:
            # Get all series (grouped by unique_name)
            series_pipeline = [
                {
                    "$match": {
                        "category": {"$in": ["series", "anime"]},
                        "unique_name": {"$exists": True, "$ne": None},
                    }
                },
                {
                    "$group": {
                        "_id": "$unique_name",
                        "title": {"$first": "$unique_name"},
                        "episode_count": {"$sum": 1},
                        "thumbnail": {"$first": "$thumbnail"},
                        "category": {"$first": "$category"},
                        "total_views": {"$sum": "$view_count"},
                        "latest_episode": {"$max": "$created_at"},
                    }
                },
                {"$sort": {"latest_episode": -1}},
            ]

            collection = self.db.media_library[TgClient.ID]
            series_cursor = collection.aggregate(series_pipeline)
            series_list = await series_cursor.to_list(length=100)

            # If specific series requested, get episodes and seasons
            episodes = []
            seasons = []
            series_info = {}

            if series_name:
                # Get all episodes for this series
                episodes_query = {
                    "unique_name": series_name,
                    "category": {"$in": ["series", "anime"]},
                }

                if season:
                    episodes_query["season"] = season

                episodes_cursor = (
                    self.db.media_library[TgClient.ID]
                    .find(episodes_query)
                    .sort("created_at", 1)
                )
                episodes = await episodes_cursor.to_list(length=1000)

                # Get available seasons for this series
                seasons_pipeline = [
                    {
                        "$match": {
                            "unique_name": series_name,
                            "season": {"$exists": True, "$ne": None},
                        }
                    },
                    {
                        "$group": {
                            "_id": "$season",
                            "season": {"$first": "$season"},
                            "episode_count": {"$sum": 1},
                            "total_views": {"$sum": "$view_count"},
                        }
                    },
                    {"$sort": {"season": 1}},
                ]

                collection = self.db.media_library[TgClient.ID]
                seasons_cursor = collection.aggregate(seasons_pipeline)
                seasons = await seasons_cursor.to_list(length=50)

                # Get series info
                series_info = await self.db.media_library[TgClient.ID].find_one(
                    {
                        "unique_name": series_name,
                        "category": {"$in": ["series", "anime"]},
                    }
                )
                if not series_info:
                    series_info = {}

            return {
                "series_list": series_list,
                "episodes": episodes,
                "seasons": seasons,
                "series_info": series_info,
            }

        except Exception as e:
            LOGGER.error(f"Error getting series data: {e}")
            return {
                "series_list": [],
                "episodes": [],
                "seasons": [],
                "series_info": {},
            }

    # Simple in-memory cache for category counts
    _category_cache = {}
    _category_cache_time = {}

    async def get_category_counts(self) -> dict:
        """Optimized category counts with caching and efficient aggregation"""
        if self._return:
            return {}
        try:
            # Check simple cache first (5 minute TTL)
            cache_key = f"category_counts_{TgClient.ID}"
            current_time = time.time()

            if (
                cache_key in self._category_cache
                and cache_key in self._category_cache_time
                and current_time - self._category_cache_time[cache_key] < 300
            ):  # 5 minutes
                LOGGER.info(
                    f"Homepage category counts (cached): {self._category_cache[cache_key]}"
                )
                return self._category_cache[cache_key]

            # Ensure database connection is available
            if not await self.ensure_connection():
                LOGGER.warning(
                    "Database connection not available for get_category_counts"
                )
                return {}

            if self.db is None:
                LOGGER.warning("Database object is None in get_category_counts")
                return {}

            if not hasattr(TgClient, "ID") or TgClient.ID is None:
                LOGGER.warning("TgClient.ID is not set for get_category_counts")
                return {}

            # Optimized aggregation pipeline with indexing hints

            collection = self.db.media_library[TgClient.ID]

            # Enhanced approach to handle both primary category and categories array
            try:
                # Get all unique primary categories first
                primary_categories = await collection.distinct(
                    "category", {"category": {"$exists": True, "$ne": None}}
                )

                # Get all unique categories from categories array
                try:
                    array_categories = await collection.distinct(
                        "categories", {"categories": {"$exists": True, "$ne": []}}
                    )
                    # Flatten the array categories if they're nested
                    flattened_array_categories = []
                    for cat in array_categories:
                        if isinstance(cat, list):
                            flattened_array_categories.extend(cat)
                        else:
                            flattened_array_categories.append(cat)
                    array_categories = list(set(flattened_array_categories))
                except Exception:
                    array_categories = []

                # Combine all unique categories
                all_categories = list(set(primary_categories + array_categories))

                result = []
                for category in all_categories[:20]:  # Limit to 20 categories
                    # Count documents that have this category in either primary category or categories array
                    count = await collection.count_documents(
                        {
                            "$or": [
                                {"category": category},
                                {"categories": {"$in": [category]}},
                            ]
                        }
                    )
                    if count > 0:  # Only include categories with actual content
                        result.append({"_id": category, "count": count})

                # Sort by count descending
                result.sort(key=lambda x: x["count"], reverse=True)

            except Exception as simple_error:
                LOGGER.warning(
                    f"Simple category count error: {simple_error}, using empty result"
                )
                result = []

            # Convert to dictionary efficiently
            category_counts = {
                item.get("_id", "unknown"): item.get("count", 0) for item in result
            }

            # Cache the result for 5 minutes in simple cache
            self._category_cache[cache_key] = category_counts
            self._category_cache_time[cache_key] = time.time()

            LOGGER.info(f"Homepage category counts: {category_counts}")
            return category_counts
        except Exception as e:
            LOGGER.error(f"Error getting category counts: {e}")
            return {}

    # User Management Methods (Updated for new schema)
    async def create_user(self, user_data: dict) -> bool:
        """Create a new user with separated credentials and profile"""
        if self._return:
            return False
        try:
            from datetime import datetime

            # Separate credentials and profile data
            credentials_data = {
                "_id": user_data["username"].lower(),
                "username": user_data["username"].lower(),
                "email": user_data["email"].lower(),
                "password_hash": user_data["password_hash"],
                "role": user_data.get("role", "user"),
                "is_active": user_data.get("is_active", True),
                "created_at": user_data.get(
                    "created_at", datetime.utcnow().timestamp()
                ),
                "last_login": None,
                "login_attempts": 0,
                "locked_until": None,
                "email_verified": True,
                "two_factor_enabled": False,
            }

            profile_data = {
                "_id": user_data["username"].lower(),
                "username": user_data["username"].lower(),
                "first_name": user_data.get("first_name", ""),
                "last_name": user_data.get("last_name", ""),
                "display_name": f"{user_data.get('first_name', '')} {user_data.get('last_name', '')}".strip(),
                "avatar": user_data.get("profile", {}).get("avatar"),
                "bio": user_data.get("profile", {}).get("bio", ""),
                "preferences": user_data.get("profile", {}).get(
                    "preferences",
                    {"theme": "dark", "language": "en", "notifications": True},
                ),
                "stats": user_data.get(
                    "stats",
                    {"files_uploaded": 0, "total_views": 0, "storage_used": 0},
                ),
                "created_at": user_data.get(
                    "created_at", datetime.utcnow().timestamp()
                ),
                "updated_at": datetime.utcnow().timestamp(),
            }

            # Insert into both collections
            cred_result = await self.db.user_credentials[TgClient.ID].insert_one(
                credentials_data
            )
            profile_result = await self.db.user_profiles[TgClient.ID].insert_one(
                profile_data
            )

            return bool(cred_result.inserted_id and profile_result.inserted_id)

        except Exception as e:
            LOGGER.error(f"Error creating user: {e}")
            return False

    async def get_user_by_username(self, username: str) -> dict:
        """Get user by username (combines credentials and profile)"""
        if self._return:
            return None
        try:
            from bot.core.aeon_client import TgClient
            from bot.core.config_manager import Config

            # Get bot ID from token if TgClient.ID is not set yet
            bot_id = TgClient.ID
            if not bot_id:
                if Config.BOT_TOKEN:
                    bot_id = Config.BOT_TOKEN.split(":", 1)[0]
                else:
                    return None

            # First check admin credentials
            credentials = await self.db.admin_credentials[bot_id].find_one(
                {"username": username.lower()}
            )

            # If not found in admin, check regular user credentials
            if not credentials:
                credentials = await self.db.user_credentials[bot_id].find_one(
                    {"username": username.lower()}
                )

            if not credentials:
                return None

            # Get profile
            profile = await self.db.user_profiles[bot_id].find_one(
                {"username": username.lower()}
            )

            # Combine data
            user_data = credentials.copy()
            if profile:
                user_data.update(
                    {
                        "first_name": profile.get("first_name"),
                        "last_name": profile.get("last_name"),
                        "display_name": profile.get("display_name"),
                        "avatar": profile.get("avatar"),
                        "bio": profile.get("bio"),
                        "preferences": profile.get("preferences", {}),
                        "stats": profile.get("stats", {}),
                    }
                )

            return user_data

        except Exception as e:
            LOGGER.error(f"Error getting user by username: {e}")
            return None

    async def get_user_by_email(self, email: str) -> dict:
        """Get user by email (combines credentials and profile)"""
        if self._return:
            return None
        try:
            from bot.core.aeon_client import TgClient
            from bot.core.config_manager import Config

            # Get bot ID from token if TgClient.ID is not set yet
            bot_id = TgClient.ID
            if not bot_id:
                if Config.BOT_TOKEN:
                    bot_id = Config.BOT_TOKEN.split(":", 1)[0]
                else:
                    return None

            # First check admin credentials
            credentials = await self.db.admin_credentials[bot_id].find_one(
                {"email": email.lower()}
            )

            # If not found in admin, check regular user credentials
            if not credentials:
                credentials = await self.db.user_credentials[bot_id].find_one(
                    {"email": email.lower()}
                )

            if not credentials:
                return None

            # Get profile
            profile = await self.db.user_profiles[bot_id].find_one(
                {"username": credentials["username"]}
            )

            # Combine data
            user_data = credentials.copy()
            if profile:
                user_data.update(
                    {
                        "first_name": profile.get("first_name"),
                        "last_name": profile.get("last_name"),
                        "display_name": profile.get("display_name"),
                        "avatar": profile.get("avatar"),
                        "bio": profile.get("bio"),
                        "preferences": profile.get("preferences", {}),
                        "stats": profile.get("stats", {}),
                    }
                )

            return user_data

        except Exception as e:
            LOGGER.error(f"Error getting user by email: {e}")
            return None

    async def update_user_last_login(self, username: str) -> bool:
        """Update user's last login timestamp"""
        if self._return:
            return False
        try:
            from time import time

            from bot.core.aeon_client import TgClient
            from bot.core.config_manager import Config

            # Get bot ID from token if TgClient.ID is not set yet
            bot_id = TgClient.ID
            if not bot_id:
                if Config.BOT_TOKEN:
                    bot_id = Config.BOT_TOKEN.split(":", 1)[0]
                else:
                    return False

            # Try to update in admin credentials first
            result = await self.db.admin_credentials[bot_id].update_one(
                {"username": username.lower()}, {"$set": {"last_login": time()}}
            )

            # If not found in admin, try regular user credentials
            if result.modified_count == 0:
                result = await self.db.user_credentials[bot_id].update_one(
                    {"username": username.lower()}, {"$set": {"last_login": time()}}
                )

            return result.modified_count > 0
        except Exception as e:
            LOGGER.error(f"Error updating user last login: {e}")
            return False

    async def update_user_password(self, username: str, password_hash: str) -> bool:
        """Update user's password hash"""
        if self._return:
            return False
        try:
            result = await self.db.user_credentials[TgClient.ID].update_one(
                {"username": username.lower()},
                {"$set": {"password_hash": password_hash}},
            )
            return result.modified_count > 0
        except Exception as e:
            LOGGER.error(f"Error updating user password: {e}")
            return False

    async def get_all_users(self, limit: int = 50, skip: int = 0) -> list:
        """Get all users with pagination (combines credentials and profiles)"""
        if self._return:
            return []
        try:
            # Get credentials (excluding password hash)
            credentials_cursor = (
                self.db.user_credentials[TgClient.ID]
                .find({}, {"password_hash": 0})
                .skip(skip)
                .limit(limit)
            )
            credentials_list = await credentials_cursor.to_list(length=limit)

            # Get corresponding profiles
            usernames = [cred["username"] for cred in credentials_list]
            profiles_cursor = self.db.user_profiles[TgClient.ID].find(
                {"username": {"$in": usernames}}
            )
            profiles_list = await profiles_cursor.to_list(length=len(usernames))

            # Create profile lookup
            profiles_dict = {
                profile["username"]: profile for profile in profiles_list
            }

            # Combine data
            combined_users = []
            for cred in credentials_list:
                user_data = cred.copy()
                profile = profiles_dict.get(cred["username"], {})
                user_data.update(
                    {
                        "first_name": profile.get("first_name", ""),
                        "last_name": profile.get("last_name", ""),
                        "display_name": profile.get("display_name", ""),
                        "avatar": profile.get("avatar"),
                        "bio": profile.get("bio", ""),
                        "preferences": profile.get("preferences", {}),
                        "stats": profile.get("stats", {}),
                    }
                )
                combined_users.append(user_data)

            return combined_users

        except Exception as e:
            LOGGER.error(f"Error getting all users: {e}")
            return []

    async def get_user_count(self) -> int:
        """Get total number of users"""
        if self._return:
            return 0
        try:
            return await self.db.user_credentials[TgClient.ID].count_documents({})
        except Exception as e:
            LOGGER.error(f"Error getting user count: {e}")
            return 0

    async def update_user_role(self, username: str, role: str) -> bool:
        """Update user's role"""
        if self._return:
            return False
        try:
            result = await self.db.user_credentials[TgClient.ID].update_one(
                {"username": username.lower()}, {"$set": {"role": role}}
            )
            return result.modified_count > 0
        except Exception as e:
            LOGGER.error(f"Error updating user role: {e}")
            return False

    async def deactivate_user(self, username: str) -> bool:
        """Deactivate a user account"""
        if self._return:
            return False
        try:
            result = await self.db.user_credentials[TgClient.ID].update_one(
                {"username": username.lower()}, {"$set": {"is_active": False}}
            )
            return result.modified_count > 0
        except Exception as e:
            LOGGER.error(f"Error deactivating user: {e}")
            return False

    async def update_user_profile(self, username: str, profile_data: dict) -> bool:
        """Update user profile information"""
        if self._return:
            return False
        try:
            from time import time

            profile_data["updated_at"] = time()

            result = await self.db.user_profiles[TgClient.ID].update_one(
                {"username": username.lower()}, {"$set": profile_data}
            )
            return result.modified_count > 0
        except Exception as e:
            LOGGER.error(f"Error updating user profile: {e}")
            return False

    # Admin Configuration Methods
    async def get_admin_config(self) -> dict:
        """Get admin configuration"""
        if self._return:
            return None
        try:
            return await self.db.admin_config[TgClient.ID].find_one({})
        except Exception as e:
            LOGGER.error(f"Error getting admin config: {e}")
            return None

    async def admin_user_exists(self) -> bool:
        """Check if any admin user exists"""
        if self._return:
            return False
        try:
            from bot.core.aeon_client import TgClient
            from bot.core.config_manager import Config

            # Get bot ID from token if TgClient.ID is not set yet
            bot_id = TgClient.ID
            if not bot_id:
                if Config.BOT_TOKEN:
                    bot_id = Config.BOT_TOKEN.split(":", 1)[0]
                else:
                    return False

            admin_count = await self.db.admin_credentials[bot_id].count_documents(
                {"role": "admin"}
            )
            return admin_count > 0
        except Exception as e:
            LOGGER.error(f"Error checking admin user existence: {e}")
            return False

    async def create_admin_user(self, admin_data: dict) -> bool:
        """Create initial admin user"""
        try:
            from bot.core.aeon_client import TgClient
            from bot.core.config_manager import Config
            from bot.helper.ext_utils.auth_handler import auth_handler

            # Get bot ID from token if TgClient.ID is not set yet
            bot_id = TgClient.ID
            if not bot_id:
                if Config.BOT_TOKEN:
                    bot_id = Config.BOT_TOKEN.split(":", 1)[0]
                    LOGGER.info(
                        f"Using bot ID from token for admin user creation: {bot_id}"
                    )
                else:
                    LOGGER.error(
                        "Neither TgClient.ID nor BOT_TOKEN available for admin user creation"
                    )
                    return False

            # Hash password
            hashed_password = auth_handler.hash_password(admin_data["password"])

            # Create admin credentials
            admin_credentials = {
                "_id": admin_data["username"].lower(),
                "username": admin_data["username"].lower(),
                "email": admin_data["email"].lower(),
                "password_hash": hashed_password,
                "role": "admin",
                "is_active": True,
                "created_at": get_time(),
                "last_login": None,
                "login_attempts": 0,
                "locked_until": None,
                "two_factor_enabled": False,
                "permissions": [
                    "user_management",
                    "content_management",
                    "system_configuration",
                    "analytics_access",
                    "security_management",
                ],
            }

            # Create admin profile
            admin_profile = {
                "_id": admin_data["username"].lower(),
                "username": admin_data["username"].lower(),
                "first_name": admin_data.get("first_name", "Admin"),
                "last_name": admin_data.get("last_name", "User"),
                "display_name": f"{admin_data.get('first_name', 'Admin')} {admin_data.get('last_name', 'User')}",
                "avatar": None,
                "bio": "System Administrator",
                "preferences": {
                    "theme": "dark",
                    "language": "en",
                    "notifications": True,
                    "dashboard_layout": "default",
                },
                "created_at": get_time(),
                "updated_at": get_time(),
            }

            # Insert admin data
            await self.db.admin_credentials[bot_id].replace_one(
                {"username": admin_data["username"].lower()},
                admin_credentials,
                upsert=True,
            )

            await self.db.user_profiles[bot_id].replace_one(
                {"username": admin_data["username"].lower()},
                admin_profile,
                upsert=True,
            )

            LOGGER.info(f"Created admin user: {admin_data['username']}")
            return True

        except Exception as e:
            LOGGER.error(f"Error creating admin user: {e}")
            return False

    async def test_connection(self) -> dict:
        """Test database connection"""
        try:
            from bot.core.aeon_client import TgClient

            if not TgClient.ID:
                return {"status": "error", "message": "TgClient.ID not set"}

            # Test basic database operations
            test_collection = self.db.test[TgClient.ID]
            await test_collection.insert_one({"test": True, "timestamp": get_time()})
            await test_collection.delete_many({"test": True})

            return {"status": "success", "message": "Database connection successful"}
        except Exception as e:
            LOGGER.error(f"Database test failed: {e}")
            return {"status": "error", "message": str(e)}

    async def get_media_stats(self) -> dict:
        """Get media statistics"""
        try:
            from bot.core.aeon_client import TgClient

            if not TgClient.ID:
                return {}

            total_files = await self.db.files[TgClient.ID].count_documents({})
            total_size = 0
            total_views = 0

            # Calculate total size and views
            async for file_doc in self.db.files[TgClient.ID].find({}):
                total_size += file_doc.get("size", 0)
                total_views += file_doc.get("views", 0)

            return {
                "total_files": total_files,
                "total_size": total_size,
                "total_views": total_views,
                "avg_file_size": total_size / total_files if total_files > 0 else 0,
            }
        except Exception as e:
            LOGGER.error(f"Error getting media stats: {e}")
            return {}

    async def get_movies_paginated(
        self, skip: int = 0, limit: int = 24, sort_by: str = "recent"
    ) -> list:
        """Get paginated movies"""
        if self._return:
            return []
        try:
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

            sort_config = {
                "recent": ("created_at", -1),
                "popular": ("view_count", -1),
                "rating": ("tmdb_data.vote_average", -1),
                "name": ("enhanced_title", 1),
            }

            sort_field, sort_direction = sort_config.get(sort_by, ("created_at", -1))

            cursor = (
                self.db.media_library[TgClient.ID]
                .find(query)
                .sort(sort_field, sort_direction)
                .skip(skip)
                .limit(limit)
            )
            return await cursor.to_list(length=limit)
        except Exception as e:
            LOGGER.error(f"Error getting movies paginated: {e}")
            return []

    async def get_shows_paginated(
        self, skip: int = 0, limit: int = 24, sort_by: str = "recent"
    ) -> list:
        """Get paginated TV shows"""
        if self._return:
            return []
        try:
            query = {"is_video": True, "series_data": {"$exists": True, "$ne": None}}

            sort_config = {
                "recent": ("created_at", -1),
                "popular": ("view_count", -1),
                "rating": ("tmdb_data.vote_average", -1),
                "name": ("enhanced_title", 1),
            }

            sort_field, sort_direction = sort_config.get(sort_by, ("created_at", -1))

            cursor = (
                self.db.media_library[TgClient.ID]
                .find(query)
                .sort(sort_field, sort_direction)
                .skip(skip)
                .limit(limit)
            )
            return await cursor.to_list(length=limit)
        except Exception as e:
            LOGGER.error(f"Error getting shows paginated: {e}")
            return []

    async def get_all_media_paginated(
        self, skip: int = 0, limit: int = 24, sort_by: str = "recent"
    ) -> list:
        """Get all media paginated"""
        if self._return:
            return []
        try:
            return await self.get_all_media(limit=limit, skip=skip, sort_by=sort_by)
        except Exception as e:
            LOGGER.error(f"Error getting all media paginated: {e}")
            return []

    async def get_total_pages(self, media_type: str, per_page: int) -> int:
        """Get total pages for pagination"""
        if self._return:
            return 0
        try:
            total_count = await self.get_total_count(media_type)
            return (total_count + per_page - 1) // per_page
        except Exception as e:
            LOGGER.error(f"Error getting total pages: {e}")
            return 0

    async def get_total_count(self, media_type: str) -> int:
        """Get total count for media type"""
        if self._return:
            return 0
        try:
            if media_type == "movie":
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
            elif media_type == "show":
                query = {
                    "is_video": True,
                    "series_data": {"$exists": True, "$ne": None},
                }
            else:  # all
                query = {}

            return await self.db.media_library[TgClient.ID].count_documents(query)
        except Exception as e:
            LOGGER.error(f"Error getting total count: {e}")
            return 0

    async def search_media(self, query: str, limit: int = 50) -> list:
        """Search media by title, filename, or description"""
        if self._return:
            return []
        try:
            search_query = {
                "$or": [
                    {"enhanced_title": {"$regex": query, "$options": "i"}},
                    {"file_name": {"$regex": query, "$options": "i"}},
                    {"tmdb_data.overview": {"$regex": query, "$options": "i"}},
                    {"description": {"$regex": query, "$options": "i"}},
                ]
            }

            cursor = (
                self.db.media_library[TgClient.ID]
                .find(search_query)
                .sort("view_count", -1)
                .limit(limit)
            )
            return await cursor.to_list(length=limit)
        except Exception as e:
            LOGGER.error(f"Error searching media: {e}")
            return []

    async def get_series_episodes(self, series_name: str) -> list:
        """Get all episodes for a series"""
        if self._return:
            return []
        try:
            query = {
                "$or": [
                    {"series_data.series_name": series_name},
                    {"enhanced_title": {"$regex": series_name, "$options": "i"}},
                ]
            }

            cursor = (
                self.db.media_library[TgClient.ID]
                .find(query)
                .sort(
                    [
                        ("series_data.season_number", 1),
                        ("series_data.episode_number", 1),
                    ]
                )
            )
            return await cursor.to_list(length=1000)
        except Exception as e:
            LOGGER.error(f"Error getting series episodes: {e}")
            return []

    async def get_user_stats(self) -> dict:
        """Get user statistics"""
        try:
            from bot.core.aeon_client import TgClient

            if not TgClient.ID:
                return {}

            total_users = await self.db.admin_credentials[
                TgClient.ID
            ].count_documents({})
            admin_users = await self.db.admin_credentials[
                TgClient.ID
            ].count_documents({"role": "admin"})
            active_users = await self.db.admin_credentials[
                TgClient.ID
            ].count_documents({"is_active": True})

            return {
                "total_users": total_users,
                "admin_users": admin_users,
                "regular_users": total_users - admin_users,
                "active_users": active_users,
                "inactive_users": total_users - active_users,
            }
        except Exception as e:
            LOGGER.error(f"Error getting user stats: {e}")
            return {}

    async def get_analytics_data(self) -> dict:
        """Get analytics data"""
        try:
            from bot.core.aeon_client import TgClient

            if not TgClient.ID:
                return {}

            # Basic analytics - would be expanded with real tracking
            media_stats = await self.get_media_stats()
            user_stats = await self.get_user_stats()

            return {
                "total_views": media_stats.get("total_views", 0),
                "unique_visitors": user_stats.get("active_users", 0),
                "total_downloads": 0,  # Would track actual downloads
                "avg_session_duration": "5m",  # Would calculate from real data
                "active_users": user_stats.get("active_users", 0),
                "user_growth": 0,  # Would calculate growth percentage
                "storage_used": f"{media_stats.get('total_size', 0) / (1024**3):.1f} GB",
                "storage_percentage": 25,  # Would calculate actual percentage
                "top_content": [],  # Would get from analytics collection
                "traffic_sources": [],  # Would get from analytics collection
                "popular_categories": [],  # Would get from file categories
            }
        except Exception as e:
            LOGGER.error(f"Error getting analytics data: {e}")
            return {}

    async def update_admin_config(self, config_data: dict) -> bool:
        """Update admin configuration"""
        if self._return:
            return False
        try:
            result = await self.db.admin_config[TgClient.ID].replace_one(
                {}, config_data, upsert=True
            )
            return bool(result.upserted_id or result.modified_count > 0)
        except Exception as e:
            LOGGER.error(f"Error updating admin config: {e}")
            return False

    # Analytics and Statistics Methods
    async def get_admin_stats(self) -> dict:
        """Get admin dashboard statistics"""
        if self._return:
            return {}
        try:
            from time import time

            today_start = time() - (24 * 60 * 60)  # 24 hours ago

            # Ensure TgClient.ID is available
            if not TgClient.ID:
                LOGGER.warning("TgClient.ID not available for admin stats")
                return {}

            # Get user stats (use new collections if available, fallback to old)
            try:
                total_users = await self.db.user_credentials[
                    TgClient.ID
                ].count_documents({})
                new_users_today = await self.db.user_credentials[
                    TgClient.ID
                ].count_documents({"created_at": {"$gte": today_start}})
            except Exception:
                # Fallback to old collection during migration
                try:
                    total_users = await self.db.users[TgClient.ID].count_documents(
                        {}
                    )
                    new_users_today = await self.db.users[
                        TgClient.ID
                    ].count_documents({"created_at": {"$gte": today_start}})
                except Exception:
                    total_users = 0
                    new_users_today = 0

            # Get media stats
            try:
                total_media = await self.db.media_library[
                    TgClient.ID
                ].count_documents({})
                new_media_today = await self.db.media_library[
                    TgClient.ID
                ].count_documents({"created_at": {"$gte": today_start}})
            except Exception:
                total_media = 0
                new_media_today = 0

            # Get view stats with better error handling
            total_views = 0
            try:
                collection = self.db.media_library[TgClient.ID]
                total_views_pipeline = [
                    {"$group": {"_id": None, "total": {"$sum": "$view_count"}}}
                ]
                total_views_cursor = collection.aggregate(total_views_pipeline)
                total_views_result = await total_views_cursor.to_list(length=1)
                total_views = (
                    total_views_result[0]["total"] if total_views_result else 0
                )
            except Exception as e:
                LOGGER.warning(f"Error calculating total views: {e}")
                total_views = 0

            # Calculate storage with better error handling
            total_storage = 0
            try:
                collection = self.db.media_library[TgClient.ID]
                storage_pipeline = [
                    {"$group": {"_id": None, "total": {"$sum": "$file_size"}}}
                ]
                storage_result = await collection.aggregate(
                    storage_pipeline
                ).to_list(length=1)
                total_storage = storage_result[0]["total"] if storage_result else 0
            except Exception as e:
                LOGGER.warning(f"Error calculating total storage: {e}")
                total_storage = 0

            return {
                "total_users": total_users,
                "new_users_today": new_users_today,
                "total_media": total_media,
                "new_media_today": new_media_today,
                "total_views": total_views,
                "views_today": 0,  # Would need view tracking by date
                "storage_used": self._format_file_size(total_storage),
                "storage_bytes": total_storage,
                "storage_percentage": min(
                    100, (total_storage / (100 * 1024 * 1024 * 1024)) * 100
                ),  # Assume 100GB limit
            }
        except Exception as e:
            LOGGER.error(f"Error getting admin stats: {e}")
            return {}

    def _format_file_size(self, size_bytes: int) -> str:
        """Format file size in human readable format"""
        if size_bytes == 0:
            return "0 B"

        size_names = ["B", "KB", "MB", "GB", "TB"]

        i = math.floor(math.log(size_bytes, 1024))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return f"{s} {size_names[i]}"

    async def get_recent_activities(self, limit: int = 10) -> list:
        """Get recent user activities for admin dashboard"""
        if self._return:
            return []
        try:
            activities = []

            # Get recent user registrations (use new collections if available)
            try:
                recent_users = (
                    await self.db.user_credentials[TgClient.ID]
                    .find({}, {"username": 1, "created_at": 1})
                    .sort("created_at", -1)
                    .limit(5)
                    .to_list(length=5)
                )
            except Exception:
                # Fallback to old collection during migration
                recent_users = (
                    await self.db.users[TgClient.ID]
                    .find({}, {"username": 1, "created_at": 1})
                    .sort("created_at", -1)
                    .limit(5)
                    .to_list(length=5)
                )

            for user in recent_users:
                activities.append(
                    {
                        "time": self._format_timestamp(user.get("created_at", 0)),
                        "user": user.get("username", "Unknown"),
                        "action": "User Registration",
                        "details": "New user account created",
                        "status": "success",
                        "status_class": "success",
                    }
                )

            # Get recent media uploads
            recent_media = (
                await self.db.media_library[TgClient.ID]
                .find({}, {"title": 1, "uploader_name": 1, "created_at": 1})
                .sort("created_at", -1)
                .limit(5)
                .to_list(length=5)
            )

            for media in recent_media:
                activities.append(
                    {
                        "time": self._format_timestamp(media.get("created_at", 0)),
                        "user": media.get("uploader_name", "Unknown"),
                        "action": "File Upload",
                        "details": media.get("title", "Unknown file"),
                        "status": "success",
                        "status_class": "success",
                    }
                )

            # Sort by time and limit
            activities.sort(key=lambda x: x["time"], reverse=True)
            return activities[:limit]

        except Exception as e:
            LOGGER.error(f"Error getting recent activities: {e}")
            return []

    def _format_timestamp(self, timestamp: float) -> str:
        """Format timestamp for display"""
        try:
            from datetime import datetime

            dt = datetime.fromtimestamp(timestamp)
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return "Unknown"

    async def _initialize_schema(self):
        """Initialize database schema and perform migration if needed"""
        try:
            # Initialize database schema directly (removed redundant db_schema.py)
            await self._create_indexes_and_collections()
            LOGGER.info("Database schema initialized successfully")
        except Exception as e:
            LOGGER.error(f"Error initializing database schema: {e}")

    async def _create_indexes_and_collections(self):
        """Create ReelNN-style database indexes and collections for optimal performance"""
        try:
            # Create indexes for media_library collection - ReelNN style
            media_collection = self.db.media_library[TgClient.ID]

            # Primary indexes - ReelNN style
            await media_collection.create_index("hash_id", unique=True)
            await media_collection.create_index("mid")  # ReelNN movie/show ID
            await media_collection.create_index(
                "original_hash_id"
            )  # For grouped media

            # ReelNN search and filtering indexes
            await media_collection.create_index("title")
            await media_collection.create_index("original_title")
            await media_collection.create_index("file_name")
            await media_collection.create_index("category")
            # Full text search index - handle conflicts gracefully
            try:
                await media_collection.create_index(
                    [
                        ("title", "text"),
                        ("original_title", "text"),
                        ("overview", "text"),
                    ]
                )
            except Exception as text_index_error:
                if (
                    "IndexOptionsConflict" not in str(text_index_error)
                    or "equivalent index already exists"
                    not in str(text_index_error).lower()
                ):
                    LOGGER.warning(
                        f"Could not create text search index: {text_index_error}"
                    )

            # ReelNN media type indexes
            await media_collection.create_index("media_type")  # movie/tv
            await media_collection.create_index("is_series")
            await media_collection.create_index("is_video")
            await media_collection.create_index("is_audio")
            await media_collection.create_index("is_image")

            # ReelNN sorting and filtering indexes
            await media_collection.create_index("indexed_at")  # ReelNN creation time
            await media_collection.create_index("release_date")
            await media_collection.create_index("first_air_date")
            await media_collection.create_index("vote_average")
            await media_collection.create_index("popularity")
            await media_collection.create_index("view_count")
            await media_collection.create_index("trending_score")
            await media_collection.create_index("status")  # active/inactive
            await media_collection.create_index("featured")  # featured content
            await media_collection.create_index("streamable")

            # ReelNN genre and metadata indexes
            await media_collection.create_index("genres.name")
            await media_collection.create_index("genres.id")
            await media_collection.create_index("runtime")
            await media_collection.create_index("quality")
            await media_collection.create_index("file_format")

            # ReelNN series/episode indexes
            await media_collection.create_index("unique_name")
            await media_collection.create_index("season")
            await media_collection.create_index("episode")
            await media_collection.create_index(
                [("unique_name", 1), ("season", 1), ("episode", 1)]
            )

            # ReelNN compound indexes for common query patterns
            await media_collection.create_index(
                [("media_type", 1), ("status", 1), ("indexed_at", -1)]
            )  # Browse pages
            await media_collection.create_index(
                [("status", 1), ("streamable", 1), ("trending_score", -1)]
            )  # Trending
            await media_collection.create_index(
                [("status", 1), ("featured", -1), ("vote_average", -1)]
            )  # Featured
            await media_collection.create_index(
                [("media_type", 1), ("genres.name", 1), ("vote_average", -1)]
            )  # Genre filtering
            await media_collection.create_index(
                [("view_count", -1), ("indexed_at", -1)]
            )  # Popular content
            await media_collection.create_index(
                [("chat_id", 1), ("message_id", 1)]
            )  # For indexing

            # Create indexes for categories collection
            categories_collection = self.db.categories[TgClient.ID]
            await categories_collection.create_index("name", unique=True)
            await categories_collection.create_index("is_active")

            # Create indexes for navigation collection
            nav_collection = self.db.navigation[TgClient.ID]
            await nav_collection.create_index("name", unique=True)
            await nav_collection.create_index("order")

            # Create indexes for encoded_data collection (password-protected encoding)
            encoded_data_collection = self.db.encoded_data
            # Note: _id index is automatically created and unique, no need to specify
            await encoded_data_collection.create_index("authorized_user_id")
            await encoded_data_collection.create_index("creator_user_id")
            await encoded_data_collection.create_index("created_at")
            await encoded_data_collection.create_index(
                [("created_at", 1)]
            )  # For cleanup operations

            # Create indexes for username_mappings collection
            username_mappings_collection = self.db.username_mappings
            await username_mappings_collection.create_index("username", unique=True)
            await username_mappings_collection.create_index("user_id")
            await username_mappings_collection.create_index("updated_at")

        except Exception as e:
            # Handle index conflicts gracefully
            if (
                "IndexOptionsConflict" in str(e)
                or "equivalent index already exists" in str(e).lower()
            ):
                LOGGER.info(
                    "Some indexes already exist with different options - this is normal"
                )
            else:
                LOGGER.warning(
                    f"Error creating database indexes (may already exist): {e}"
                )

    async def _cleanup_invalid_config_keys(self):
        """Dynamically remove invalid/deprecated configuration keys from database"""
        try:
            if not await self.ensure_connection():
                return

            # Import Config class to get valid configuration keys
            from bot.core.config_manager import Config

            # Get all valid configuration keys from the Config class
            valid_config_keys = set(Config.__annotations__.keys())

            # Get all keys from runtime config
            runtime_config = await self.db.settings.config.find_one(
                {"_id": TgClient.ID}, {"_id": 0}
            )

            # Get all keys from deploy config
            deploy_config = await self.db.settings.deployConfig.find_one(
                {"_id": TgClient.ID}, {"_id": 0}
            )

            # Find deprecated keys (keys that exist in database but not in Config class)
            deprecated_keys_runtime = []
            deprecated_keys_deploy = []

            if runtime_config:
                for key in runtime_config:
                    # Skip internal keys (starting with _) and only check config keys
                    if not key.startswith("_") and key not in valid_config_keys:
                        deprecated_keys_runtime.append(key)

            if deploy_config:
                for key in deploy_config:
                    # Skip internal keys (starting with _) and only check config keys
                    if not key.startswith("_") and key not in valid_config_keys:
                        deprecated_keys_deploy.append(key)

            # Combine all deprecated keys for logging
            all_deprecated_keys = []
            if deprecated_keys_runtime:
                all_deprecated_keys.extend(
                    [f"{key} (runtime config)" for key in deprecated_keys_runtime]
                )
            if deprecated_keys_deploy:
                all_deprecated_keys.extend(
                    [f"{key} (deploy config)" for key in deprecated_keys_deploy]
                )

            # Show warning only when deprecated keys are found
            if all_deprecated_keys:
                LOGGER.warning(
                    f"Found deprecated configuration keys: {', '.join(all_deprecated_keys)}. "
                    f"These keys are no longer valid and will be removed from database."
                )

            # Track if any keys were actually cleaned up
            keys_actually_removed = False

            # Remove deprecated keys from runtime config
            if deprecated_keys_runtime:
                result = await self.db.settings.config.update_one(
                    {"_id": TgClient.ID},
                    {"$unset": dict.fromkeys(deprecated_keys_runtime, "")},
                )
                if result.modified_count > 0:
                    keys_actually_removed = True
                    LOGGER.info(
                        f"✅ Cleaned up {len(deprecated_keys_runtime)} deprecated configuration keys from runtime config"
                    )

            # Remove deprecated keys from deploy config
            if deprecated_keys_deploy:
                result = await self.db.settings.deployConfig.update_one(
                    {"_id": TgClient.ID},
                    {"$unset": dict.fromkeys(deprecated_keys_deploy, "")},
                )
                if result.modified_count > 0:
                    keys_actually_removed = True
                    LOGGER.info(
                        f"✅ Cleaned up {len(deprecated_keys_deploy)} deprecated configuration keys from deploy config"
                    )

            # If we found and cleaned up deprecated keys, log completion
            if all_deprecated_keys and keys_actually_removed:
                LOGGER.info(
                    "🧹 Database cleanup completed. All deprecated configuration keys have been permanently removed."
                )

        except Exception as e:
            LOGGER.error(f"Error cleaning up invalid configuration keys: {e}")

    async def get_category_stats(self):
        """Get category statistics for admin panel"""
        try:
            if not TgClient.ID:
                return []

            # Get category statistics
            collection = self.db.media_library[TgClient.ID]
            category_pipeline = [
                {
                    "$group": {
                        "_id": "$category",
                        "count": {"$sum": 1},
                        "total_size": {"$sum": "$file_size"},
                        "total_views": {"$sum": "$view_count"},
                    }
                },
                {"$sort": {"count": -1}},
            ]
            cursor = collection.aggregate(category_pipeline)
            categories = await cursor.to_list(length=None)

            # Format the results
            formatted_categories = []
            for cat in categories:
                formatted_categories.append(
                    {
                        "name": cat["_id"] or "Uncategorized",
                        "count": cat["count"],
                        "total_size": cat["total_size"],
                        "total_views": cat["total_views"] or 0,
                        "size_human": self._format_file_size(cat["total_size"]),
                    }
                )

            return formatted_categories

        except Exception as e:
            LOGGER.error(f"Error getting category stats: {e}")
            return []

    # Dynamic Categories Management
    async def create_category(self, category_data: dict) -> bool:
        """Create a new category"""
        if self._return:
            return False
        try:
            from datetime import datetime

            category_data.update(
                {
                    "created_at": datetime.utcnow().timestamp(),
                    "updated_at": datetime.utcnow().timestamp(),
                    "is_active": True,
                }
            )

            result = await self.db.categories[TgClient.ID].insert_one(category_data)
            return bool(result.inserted_id)
        except Exception as e:
            LOGGER.error(f"Error creating category: {e}")
            return False

    async def get_all_categories(self) -> list:
        """Get all categories"""
        if self._return:
            return []
        try:
            cursor = (
                self.db.categories[TgClient.ID]
                .find({"is_active": True})
                .sort("name", 1)
            )
            return await cursor.to_list(length=None)
        except Exception as e:
            LOGGER.error(f"Error getting categories: {e}")
            return []

    async def get_category_by_name(self, category_name: str) -> dict | None:
        """Get a category by name"""
        if self._return:
            return None
        try:
            return await self.db.categories[TgClient.ID].find_one(
                {"name": category_name}
            )
        except Exception as e:
            LOGGER.error(f"Error getting category by name: {e}")
            return None

    async def update_category(self, category_name: str, update_data: dict) -> bool:
        """Update a category"""
        if self._return:
            return False
        try:
            from datetime import datetime

            update_data["updated_at"] = datetime.utcnow().timestamp()

            result = await self.db.categories[TgClient.ID].update_one(
                {"name": category_name}, {"$set": update_data}
            )
            return result.modified_count > 0
        except Exception as e:
            LOGGER.error(f"Error updating category: {e}")
            return False

    async def delete_category(self, category_name: str) -> bool:
        """Delete a category (soft delete)"""
        if self._return:
            return False
        try:
            from datetime import datetime

            result = await self.db.categories[TgClient.ID].update_one(
                {"name": category_name},
                {
                    "$set": {
                        "is_active": False,
                        "updated_at": datetime.utcnow().timestamp(),
                    }
                },
            )
            return result.modified_count > 0
        except Exception as e:
            LOGGER.error(f"Error deleting category: {e}")
            return False

    # Navigation Management
    async def create_navigation_item(self, nav_data: dict) -> bool:
        """Create a new navigation item"""
        if self._return:
            return False
        try:
            from datetime import datetime

            nav_data.update(
                {
                    "created_at": datetime.utcnow().timestamp(),
                    "updated_at": datetime.utcnow().timestamp(),
                    "is_active": True,
                }
            )

            result = await self.db.navigation[TgClient.ID].insert_one(nav_data)
            return bool(result.inserted_id)
        except Exception as e:
            LOGGER.error(f"Error creating navigation item: {e}")
            return False

    async def get_navigation_items(self, location: str | None = None) -> list:
        """Get navigation items by location"""
        if self._return:
            return []
        try:
            query = {"is_active": True}
            if location:
                query["location"] = location

            cursor = self.db.navigation[TgClient.ID].find(query).sort("position", 1)
            return await cursor.to_list(length=None)
        except Exception as e:
            LOGGER.error(f"Error getting navigation items: {e}")
            return []

    async def update_navigation_item(self, nav_id: str, update_data: dict) -> bool:
        """Update a navigation item"""
        if self._return:
            return False
        try:
            from datetime import datetime

            from bson import ObjectId

            update_data["updated_at"] = datetime.utcnow().timestamp()

            result = await self.db.navigation[TgClient.ID].update_one(
                {"_id": ObjectId(nav_id)}, {"$set": update_data}
            )
            return result.modified_count > 0
        except Exception as e:
            LOGGER.error(f"Error updating navigation item: {e}")
            return False

    async def delete_navigation_item(self, nav_id: str) -> bool:
        """Delete a navigation item (soft delete)"""
        if self._return:
            return False
        try:
            from datetime import datetime

            from bson import ObjectId

            result = await self.db.navigation[TgClient.ID].update_one(
                {"_id": ObjectId(nav_id)},
                {
                    "$set": {
                        "is_active": False,
                        "updated_at": datetime.utcnow().timestamp(),
                    }
                },
            )
            return result.modified_count > 0
        except Exception as e:
            LOGGER.error(f"Error deleting navigation item: {e}")
            return False

    async def delete_media_by_category_and_user(
        self, category: str, uploader_username: str
    ) -> int:
        """Delete all media files by category and uploader username"""
        if self._return:
            return 0
        try:
            result = await self.db.media_library[TgClient.ID].delete_many(
                {"category": category, "uploader_username": uploader_username}
            )

            if result.deleted_count > 0:
                # Invalidate caches
                self._invalidate_all_media_caches()
                cache_key = f"category_counts_{TgClient.ID}"
                if cache_key in self._category_cache:
                    del self._category_cache[cache_key]
                if cache_key in self._category_cache_time:
                    del self._category_cache_time[cache_key]

            return result.deleted_count
        except Exception as e:
            LOGGER.error(f"Error deleting media by category and user: {e}")
            return 0

    async def update_media_category(
        self, old_category: str, new_category: str, uploader_username: str
    ) -> int:
        """Update category for all media files by uploader username"""
        if self._return:
            return 0
        try:
            from datetime import datetime

            result = await self.db.media_library[TgClient.ID].update_many(
                {"category": old_category, "uploader_username": uploader_username},
                {
                    "$set": {
                        "category": new_category,
                        "updated_at": datetime.utcnow().timestamp(),
                    }
                },
            )

            if result.modified_count > 0:
                # Invalidate caches
                self._invalidate_all_media_caches()
                cache_key = f"category_counts_{TgClient.ID}"
                if cache_key in self._category_cache:
                    del self._category_cache[cache_key]
                if cache_key in self._category_cache_time:
                    del self._category_cache_time[cache_key]

            return result.modified_count
        except Exception as e:
            LOGGER.error(f"Error updating media category: {e}")
            return 0

    async def get_users_by_role(self):
        """Get users grouped by role for admin panel"""
        try:
            # Get users by role
            collection = self.db.users
            users_pipeline = [
                {
                    "$group": {
                        "_id": "$role",
                        "users": {
                            "$push": {
                                "user_id": "$user_id",
                                "username": "$username",
                                "first_name": "$first_name",
                                "last_name": "$last_name",
                                "created_at": "$created_at",
                            }
                        },
                        "count": {"$sum": 1},
                    }
                },
                {"$sort": {"count": -1}},
            ]
            users_cursor = collection.aggregate(users_pipeline)
            return await users_cursor.to_list(length=None)

        except Exception as e:
            LOGGER.error(f"Error getting users by role: {e}")
            return []

    async def get_database_stats(self):
        """Get database statistics for admin panel"""
        try:
            stats = {}

            # Get collection stats
            if TgClient.ID:
                media_count = await self.db.media_library[
                    TgClient.ID
                ].count_documents({})
                stats["media_files"] = media_count
            else:
                stats["media_files"] = 0

            users_count = await self.db.users.count_documents({})
            stats["users"] = users_count

            # Get database size (approximate)
            try:
                db_stats = await self.db.command("dbStats")
                stats["database_size"] = db_stats.get("dataSize", 0)
                stats["index_size"] = db_stats.get("indexSize", 0)
                stats["storage_size"] = db_stats.get("storageSize", 0)
            except Exception:
                stats["database_size"] = 0
                stats["index_size"] = 0
                stats["storage_size"] = 0

            return stats

        except Exception as e:
            LOGGER.error(f"Error getting database stats: {e}")
            return {}

    async def get_cleanup_stats(self):
        """Get cleanup statistics for admin panel"""
        try:
            if not TgClient.ID:
                return {}

            # Get files without thumbnails
            no_thumbnail_count = await self.db.media_library[
                TgClient.ID
            ].count_documents(
                {
                    "$or": [
                        {"thumbnail": {"$exists": False}},
                        {"thumbnail": None},
                        {"thumbnail": ""},
                    ]
                }
            )

            # Get duplicate files (same file_name and file_size)
            collection = self.db.media_library[TgClient.ID]
            duplicate_pipeline = [
                {
                    "$group": {
                        "_id": {
                            "file_name": "$file_name",
                            "file_size": "$file_size",
                        },
                        "count": {"$sum": 1},
                        "ids": {"$push": "$_id"},
                    }
                },
                {"$match": {"count": {"$gt": 1}}},
            ]
            duplicates_cursor = collection.aggregate(duplicate_pipeline)
            duplicates = await duplicates_cursor.to_list(length=None)
            duplicate_count = len(duplicates)

            # Get old files (older than 30 days with 0 views)
            import time

            thirty_days_ago = time.time() - (30 * 24 * 60 * 60)
            old_files_count = await self.db.media_library[
                TgClient.ID
            ].count_documents(
                {
                    "created_at": {"$lt": thirty_days_ago},
                    "$or": [{"view_count": {"$exists": False}}, {"view_count": 0}],
                }
            )

            return {
                "no_thumbnail": no_thumbnail_count,
                "duplicates": duplicate_count,
                "old_files": old_files_count,
                "total_cleanup_candidates": no_thumbnail_count
                + duplicate_count
                + old_files_count,
            }

        except Exception as e:
            LOGGER.error(f"Error getting cleanup stats: {e}")
            return {}

    # Optimized database methods for streaming operations
    async def get_total_media_count(self) -> int:
        """Get total count of media files efficiently (without filters)"""
        if not await self.ensure_connection():
            return 0
        try:
            return await self.db.media_library[TgClient.ID].count_documents({})
        except Exception as e:
            LOGGER.error(f"Error getting total media count: {e}")
            return 0

    async def stream_media_files_by_chat(self, chat_id: int):
        """Stream media files by chat ID to avoid loading all into memory"""
        if not await self.ensure_connection():
            return
        try:
            cursor = self.db.media_library[TgClient.ID].find(
                {"chat_id": chat_id},
                {
                    "hash_id": 1,
                    "message_id": 1,
                    "chat_id": 1,
                },  # Only fetch needed fields
            )
            async for document in cursor:
                yield document
        except Exception as e:
            LOGGER.error(f"Error streaming media files by chat {chat_id}: {e}")

    async def stream_all_media_files(self):
        """Stream all media files to avoid loading all into memory"""
        if not await self.ensure_connection():
            return
        try:
            cursor = self.db.media_library[TgClient.ID].find(
                {},
                {
                    "hash_id": 1,
                    "message_id": 1,
                    "chat_id": 1,
                    "file_name": 1,
                },  # Only fetch needed fields
            )
            async for document in cursor:
                yield document
        except Exception as e:
            LOGGER.error(f"Error streaming all media files: {e}")

    async def batch_update_media_metadata(self, updates: list) -> int:
        """Batch update media metadata for efficiency"""
        if not await self.ensure_connection() or not updates:
            return 0
        try:
            from pymongo import UpdateOne

            operations = []
            for update in updates:
                hash_id = update.get("hash_id")
                metadata = update.get("metadata", {})
                if hash_id and metadata:
                    operations.append(
                        UpdateOne({"hash_id": hash_id}, {"$set": metadata})
                    )

            if operations:
                result = await self.db.media_library[TgClient.ID].bulk_write(
                    operations
                )
                return result.modified_count
            return 0
        except Exception as e:
            LOGGER.error(f"Error in batch update media metadata: {e}")
            return 0


class DatabaseManager(DbManager):
    def __init__(self):
        super().__init__()
        self._heartbeat_task = None

    async def start_heartbeat(self):
        """Start a background task to periodically check the database connection."""
        if self._heartbeat_task is not None:
            return

        # Define the heartbeat coroutine
        async def heartbeat():
            while True:
                try:
                    if Config.DATABASE_URL:
                        await self.ensure_connection()
                    await asyncio.sleep(60)  # Check every minute
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    LOGGER.error(f"Error in database heartbeat: {e}")
                    await asyncio.sleep(30)  # Shorter interval on error

        # Start the heartbeat task
        self._heartbeat_task = asyncio.create_task(heartbeat())
        LOGGER.info("Database heartbeat task started")

    async def stop_heartbeat(self):
        """Stop the heartbeat task."""
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat_task
            self._heartbeat_task = None
            LOGGER.info("Database heartbeat task stopped")


database = DatabaseManager()


# UNIFIED DATABASE ACCESS FUNCTION
async def ensure_database_and_config():
    """
    Unified database access function for all modules
    Returns the shared database instance after ensuring connection
    """
    try:
        if not Config.DATABASE_URL:
            LOGGER.warning("Database URL not configured")
            return None

        # Ensure database connection
        if not await database.ensure_connection():
            LOGGER.error("Failed to establish database connection")
            return None

        return database

    except Exception as e:
        LOGGER.error(f"Error in unified database access: {e}")
        return None
