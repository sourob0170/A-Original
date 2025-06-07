import asyncio
import contextlib
import inspect
from importlib import import_module
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
            if self._conn is not None:
                try:
                    await self._conn.close()
                except Exception as e:
                    LOGGER.error(f"Error closing previous DB connection: {e}")

            # Improved connection parameters to address stability issues
            self._conn = AsyncMongoClient(
                Config.DATABASE_URL,
                server_api=ServerApi("1"),
                maxPoolSize=5,  # Reduced pool size to prevent resource exhaustion
                minPoolSize=0,  # Allow all connections to close when idle
                maxIdleTimeMS=60000,  # Increased idle time to 60 seconds
                connectTimeoutMS=10000,  # Increased connection timeout to 10 seconds
                socketTimeoutMS=30000,  # Increased socket timeout to 30 seconds
                serverSelectionTimeoutMS=15000,  # Added server selection timeout
                heartbeatFrequencyMS=10000,  # More frequent heartbeats
                retryWrites=True,  # Enable retry for write operations
                retryReads=True,  # Enable retry for read operations
                waitQueueTimeoutMS=10000,  # Wait queue timeout
            )

            # Verify connection is working with a ping
            await self._conn.admin.command("ping")

            self.db = self._conn.luna
            self._return = False
            LOGGER.info("Successfully connected to database")
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

            # Try to reconnect
            LOGGER.info(
                f"Attempting to reconnect to database (attempt {self._reconnect_attempts})"
            )
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

    async def update_deploy_config(self):
        if not await self.ensure_connection():
            return
        settings = import_module("config")
        config_file = {
            key: value.strip() if isinstance(value, str) else value
            for key, value in vars(settings).items()
            if not key.startswith("__")
        }
        try:
            await self.db.settings.deployConfig.replace_one(
                {"_id": TgClient.ID},
                config_file,
                upsert=True,
            )
        except PyMongoError as e:
            LOGGER.error(f"Error updating deploy config: {e}")
            await self.ensure_connection()  # Try to reconnect for next operation

    async def update_config(self, dict_):
        if not await self.ensure_connection():
            return
        try:
            await self.db.settings.config.update_one(
                {"_id": TgClient.ID},
                {"$set": dict_},
                upsert=True,
            )
        except PyMongoError as e:
            LOGGER.error(f"Error updating config: {e}")
            await self.ensure_connection()  # Try to reconnect for next operation

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
                if path == "config.py":
                    await self.update_deploy_config()

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

        # Store each message individually to avoid bulk write issues
        for chat_id, message_id in zip(chat_ids, message_ids, strict=True):
            try:
                await self.db.scheduled_deletions.update_one(
                    {"chat_id": chat_id, "message_id": message_id},
                    {"$set": {"delete_time": delete_time, "bot_id": bot_id}},
                    upsert=True,
                )
            except PyMongoError as e:
                LOGGER.error(f"Error storing scheduled deletion: {e}")
                await self.ensure_connection()  # Try to reconnect for next operation

        # Messages stored for deletion

    async def remove_scheduled_deletion(self, chat_id, message_id):
        """Remove a message from scheduled deletions"""
        if not await self.ensure_connection():
            return
        try:
            await self.db.scheduled_deletions.delete_one(
                {"chat_id": chat_id, "message_id": message_id},
            )
        except PyMongoError as e:
            LOGGER.error(f"Error removing scheduled deletion: {e}")
            await self.ensure_connection()  # Try to reconnect for next operation

    async def get_pending_deletions(self):
        """Get messages that are due for deletion"""
        if not await self.ensure_connection():
            return []

        current_time = int(get_time())
        # Get current time for comparison

        try:
            # Create index for better performance if it doesn't exist
            await self.db.scheduled_deletions.create_index([("delete_time", 1)])

            # Get all documents for manual processing
            all_docs = []
            try:
                async for doc in self.db.scheduled_deletions.find():
                    all_docs.append(doc)
            except PyMongoError as e:
                LOGGER.error(f"Error retrieving scheduled deletions: {e}")
                await self.ensure_connection()  # Try to reconnect
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
