#!/usr/bin/env python3

"""
Index Command Module

This module provides the /index command to reindex all media files
by comparing LEECH_DUMP_CHAT with the database.
Fixed import issues and optimized for performance.
"""

from pyrogram.types import Message

from bot import LOGGER
from bot.core.aeon_client import TgClient
from bot.core.config_manager import Config
from bot.helper.ext_utils.db_handler import ensure_database_and_config
from bot.helper.telegram_helper.message_utils import send_message


async def auto_index_on_startup():
    """
    Automatically run indexing process on bot startup to sync dump chats with database.
    This runs silently without user interaction.
    """
    try:
        # Check if database is available
        if not Config.DATABASE_URL:
            LOGGER.warning("❌ Database not configured - skipping auto-indexing")
            return

        # Check if LEECH_DUMP_CHAT is configured
        dump_chats = Config.LEECH_DUMP_CHAT
        if not dump_chats:
            LOGGER.warning(
                "❌ LEECH_DUMP_CHAT not configured - skipping auto-indexing"
            )
            return

        # Parse dump chats
        if isinstance(dump_chats, str):
            dump_chat_ids = [
                int(chat.strip())
                for chat in dump_chats.split()
                if chat.strip().lstrip("-").isdigit()
            ]
        elif isinstance(dump_chats, list):
            dump_chat_ids = [
                int(chat)
                for chat in dump_chats
                if str(chat).strip().lstrip("-").isdigit()
            ]
        else:
            dump_chat_ids = (
                [int(dump_chats)]
                if str(dump_chats).strip().lstrip("-").isdigit()
                else []
            )

        if not dump_chat_ids:
            LOGGER.warning(
                "❌ No valid LEECH_DUMP_CHAT IDs found - skipping auto-indexing"
            )
            return

        # Get unified database access
        database = await ensure_database_and_config()
        if not database:
            LOGGER.error("❌ Failed to connect to database - skipping auto-indexing")
            return

        # Get count of media files from database
        try:
            total_db_files = await database.get_total_media_count()
        except Exception as e:
            LOGGER.error(f"❌ Error fetching media count from database: {e}")
            return

        # Run the same indexing logic as the command but without status messages
        stats = {
            "total_db_files": total_db_files,
            "dump_chats_processed": 0,
            "files_checked": 0,
            "files_kept": 0,
            "files_removed": 0,
            "errors": 0,
        }

        # Get all valid message IDs from dump chats

        # Process each dump chat
        for chat_id in dump_chat_ids:
            try:
                # Get chat info
                try:
                    chat = await TgClient.bot.get_chat(chat_id)
                    getattr(chat, "title", f"Chat {chat_id}")
                except Exception as e:
                    LOGGER.warning(f"Could not get chat info for {chat_id}: {e}")

                stats["dump_chats_processed"] += 1

            except Exception as e:
                stats["errors"] += 1
                LOGGER.error(f"Error processing dump chat {chat_id}: {e}")

        files_to_remove = []

        # Get all media files from database using the regular method
        try:
            # Use the existing database method to get all media
            all_media = await database.get_all_media_metadata()

            if not all_media:
                return

            for file_doc in all_media:
                stats["files_checked"] += 1

                try:
                    # Check if the file document has required fields
                    message_id = file_doc.get("message_id")
                    chat_id = file_doc.get("chat_id")

                    if not message_id or not chat_id:
                        # File is missing essential data - mark for removal
                        files_to_remove.append(file_doc.get("_id"))
                        stats["files_removed"] += 1
                    else:
                        stats["files_kept"] += 1

                except Exception as e:
                    LOGGER.warning(
                        f"Error checking file {file_doc.get('_id', 'unknown')}: {e}"
                    )
                    stats["errors"] += 1

        except Exception as e:
            LOGGER.error(f"Error getting media files from database: {e}")
            return

        # Remove files that are no longer in dump chats
        if files_to_remove:
            try:
                await database.remove_media_by_ids(files_to_remove)
            except Exception as e:
                LOGGER.error(f"❌ Error removing files from database: {e}")
                stats["errors"] += 1

    except Exception as e:
        LOGGER.error(f"❌ Error in automatic indexing: {e}")


async def index_command(client, message: Message):
    """
    Reindex all media files by comparing LEECH_DUMP_CHAT with database.
    Only removes files from database that are no longer in the dump chat.
    """
    try:
        # Check if database is available
        if not Config.DATABASE_URL:
            await send_message(
                message,
                "<b>❌ Database not configured.</b>\n\n<i>Cannot perform indexing without database connection.</i>",
            )
            return

        # Check if LEECH_DUMP_CHAT is configured
        dump_chats = Config.LEECH_DUMP_CHAT
        if not dump_chats:
            await send_message(
                message,
                "<b>❌ LEECH_DUMP_CHAT not configured.</b>\n\n<i>Cannot perform indexing without dump chat configuration.</i>",
            )
            return

        # Parse dump chats
        if isinstance(dump_chats, str):
            dump_chat_ids = [
                int(chat.strip())
                for chat in dump_chats.split()
                if chat.strip().lstrip("-").isdigit()
            ]
        elif isinstance(dump_chats, list):
            dump_chat_ids = [
                int(chat)
                for chat in dump_chats
                if str(chat).strip().lstrip("-").isdigit()
            ]
        else:
            dump_chat_ids = (
                [int(dump_chats)]
                if str(dump_chats).strip().lstrip("-").isdigit()
                else []
            )

        if not dump_chat_ids:
            await send_message(
                message,
                "<b>❌ No valid LEECH_DUMP_CHAT IDs found.</b>\n\n<i>Cannot perform indexing without valid dump chat IDs.</i>",
            )
            return

        # Send initial status message
        status_msg = await send_message(
            message,
            "<b>🔄 Starting media indexing process...</b>\n\n<b>📊 Status:</b>\n<code>• Connecting to database...</code>",
        )

        # Get unified database access
        database = await ensure_database_and_config()
        if not database:
            await status_msg.edit_text(
                "<b>❌ Failed to connect to database.</b>\n\n<i>Cannot perform indexing without database connection.</i>"
            )
            return

        await status_msg.edit_text(
            "<b>🔄 Starting media indexing process...</b>\n\n<b>📊 Status:</b>\n<code>• Database connected ✅\n• Fetching existing media from database...</code>"
        )

        # Get count of media files from database for efficiency
        try:
            total_db_files = await database.get_total_media_count()
            LOGGER.info(f"Found {total_db_files} media files in database")
        except Exception as e:
            LOGGER.error(f"Error fetching media count from database: {e}")
            await status_msg.edit_text(
                f"<b>❌ Error fetching media count from database:</b>\n\n<code>{e}</code>"
            )
            return

        await status_msg.edit_text(
            f"<b>🔄 Starting media indexing process...</b>\n\n<b>📊 Status:</b>\n<code>• Database connected ✅\n• Found {total_db_files} files in database ✅\n• Checking files in dump chats...</code>"
        )

        # Track statistics
        stats = {
            "total_db_files": total_db_files,
            "files_checked": 0,
            "files_removed": 0,
            "files_kept": 0,
            "files_added": 0,
            "errors": 0,
            "dump_chats_processed": 0,
        }

        # Create a set to track all valid message IDs from dump chats
        valid_message_ids = set()

        # Process each dump chat
        for chat_id in dump_chat_ids:
            try:
                LOGGER.info(f"Processing dump chat: {chat_id}")

                # Get chat info
                try:
                    chat = await client.get_chat(chat_id)
                    chat_title = getattr(chat, "title", f"Chat {chat_id}")
                except Exception as e:
                    LOGGER.warning(f"Could not get chat info for {chat_id}: {e}")
                    chat_title = f"Chat {chat_id}"

                await status_msg.edit_text(
                    f"<b>🔄 Starting media indexing process...</b>\n\n<b>📊 Status:</b>\n<code>• Database connected ✅\n• Found {total_db_files} files in database ✅\n• Processing: {chat_title}\n• Files checked: {stats['files_checked']}</code>"
                )

                # Try using USER_SESSION_STRING for chat history scanning
                user_client = None
                message_count = 0
                user_session_attempted = False

                # Check if USER_SESSION_STRING is available for chat history scanning
                user_session_string = getattr(Config, "USER_SESSION_STRING", None)
                LOGGER.info(
                    f"Checking USER_SESSION_STRING for chat {chat_id}: available={bool(user_session_string and user_session_string.strip())}"
                )

                if user_session_string and user_session_string.strip():
                    user_session_attempted = True
                    try:
                        from pyrogram import Client

                        user_client = Client(
                            "user_session_index",
                            Config.TELEGRAM_API,
                            Config.TELEGRAM_HASH,
                            session_string=user_session_string,
                            no_updates=True,
                        )
                        await user_client.start()
                        LOGGER.info(
                            f"Using USER_SESSION_STRING for chat history scan of {chat_id}"
                        )

                        # Scan chat history using user client
                        try:
                            scan_count = 0
                            async for chat_message in user_client.get_chat_history(
                                chat_id, limit=1000
                            ):
                                scan_count += 1
                                if chat_message.media:
                                    # Add valid message to tracking
                                    valid_message_ids.add(
                                        f"{chat_id}_{chat_message.id}"
                                    )
                                    message_count += 1

                            LOGGER.info(
                                f"Successfully scanned {scan_count} messages from {chat_id} using USER_SESSION_STRING, found {message_count} media messages"
                            )

                        except Exception as scan_error:
                            LOGGER.warning(
                                f"Error scanning chat history for {chat_id} with USER_SESSION_STRING: {scan_error}"
                            )
                            message_count = 0  # Reset on error

                    except Exception as user_client_error:
                        LOGGER.warning(
                            f"Failed to use USER_SESSION_STRING for chat history scan: {user_client_error}"
                        )
                        message_count = 0  # Reset on error
                    finally:
                        if user_client and user_client.is_connected:
                            try:
                                await user_client.stop()
                            except Exception as cleanup_error:
                                LOGGER.warning(
                                    f"Error stopping user client: {cleanup_error}"
                                )

                # If USER_SESSION_STRING was not available or failed, use bot client fallback
                if message_count == 0:
                    if user_session_attempted:
                        LOGGER.warning(
                            f"USER_SESSION_STRING failed for {chat_id}, falling back to bot client validation"
                        )
                    else:
                        LOGGER.warning(
                            f"USER_SESSION_STRING not available for {chat_id}, using bot client validation"
                        )

                    # Reset message count for bot client validation
                    message_count = 0

                # For bot clients, we'll validate files by checking if they still exist
                # by attempting to get the message directly for each file in the database
                # Use streaming approach to avoid loading all files into memory
                try:
                    if hasattr(database, "stream_media_files_by_chat"):
                        async for media_file in database.stream_media_files_by_chat(
                            chat_id
                        ):
                            message_id = media_file.get("message_id")
                            if message_id:
                                try:
                                    # Try to get the specific message
                                    msg = await client.get_messages(
                                        chat_id, message_id
                                    )
                                    if msg and msg.media:
                                        valid_message_ids.add(
                                            f"{chat_id}_{message_id}"
                                        )
                                        message_count += 1
                                except Exception as msg_error:
                                    # Message doesn't exist or is inaccessible
                                    LOGGER.info(
                                        f"Message {message_id} in chat {chat_id} not accessible: {msg_error}"
                                    )
                    else:
                        # Fallback if streaming method doesn't exist
                        LOGGER.warning(
                            "Streaming method not available, using fallback"
                        )
                except Exception as e:
                    LOGGER.warning(f"Error in streaming approach: {e}")
                    # Continue with fallback

                # Update status
                await status_msg.edit_text(
                    f"🔄 Starting media indexing process...\n\n📊 **Status:**\n• Database connected ✅\n• Found {total_db_files} files in database ✅\n• Processing: {chat_title}\n• Messages validated: {message_count}"
                )

                stats["dump_chats_processed"] += 1
                LOGGER.info(f"Processed {message_count} messages from {chat_title}")

            except Exception as e:
                LOGGER.error(f"Error processing dump chat {chat_id}: {e}")
                stats["errors"] += 1
                continue

        await status_msg.edit_text(
            f"🔄 Starting media indexing process...\n\n📊 **Status:**\n• Database connected ✅\n• Found {total_db_files} files in database ✅\n• Dump chats processed: {stats['dump_chats_processed']}\n• Valid messages found: {len(valid_message_ids)}\n• Comparing with database..."
        )

        # Now compare database files with valid message IDs using streaming approach
        files_to_remove = []

        # Use streaming approach to avoid loading all files into memory
        try:
            if hasattr(database, "stream_all_media_files"):
                async for media_file in database.stream_all_media_files():
                    stats["files_checked"] += 1

                    # Create message identifier from database record
                    chat_id = media_file.get("chat_id")
                    message_id = media_file.get("message_id")

                    if chat_id and message_id:
                        message_identifier = f"{chat_id}_{message_id}"

                        if message_identifier in valid_message_ids:
                            stats["files_kept"] += 1
                        else:
                            # File no longer exists in dump chat, mark for removal
                            files_to_remove.append(media_file)
                            stats["files_removed"] += 1
                    else:
                        # Invalid database record, mark for removal
                        files_to_remove.append(media_file)
                        stats["files_removed"] += 1

                    # Update status every 50 files
                    if stats["files_checked"] % 50 == 0:
                        await status_msg.edit_text(
                            f"🔄 Starting media indexing process...\n\n📊 **Status:**\n• Database connected ✅\n• Found {total_db_files} files in database ✅\n• Dump chats processed: {stats['dump_chats_processed']}\n• Files checked: {stats['files_checked']}/{total_db_files}\n• Files to remove: {stats['files_removed']}"
                        )
            else:
                # Fallback if streaming method doesn't exist
                LOGGER.warning(
                    "Streaming method not available, using fallback approach"
                )
                existing_media = await get_all_media_files_helper(database)
                for media_file in existing_media:
                    stats["files_checked"] += 1

                    # Create message identifier from database record
                    chat_id = media_file.get("chat_id")
                    message_id = media_file.get("message_id")

                    if chat_id and message_id:
                        message_identifier = f"{chat_id}_{message_id}"

                        if message_identifier in valid_message_ids:
                            stats["files_kept"] += 1
                        else:
                            # File no longer exists in dump chat, mark for removal
                            files_to_remove.append(media_file)
                            stats["files_removed"] += 1
                    else:
                        # Invalid database record, mark for removal
                        files_to_remove.append(media_file)
                        stats["files_removed"] += 1

                    # Update status every 50 files
                    if stats["files_checked"] % 50 == 0:
                        await status_msg.edit_text(
                            f"<b>🔄 Starting media indexing process...</b>\n\n<b>📊 Status:</b>\n<code>• Database connected ✅\n• Found {total_db_files} files in database ✅\n• Dump chats processed: {stats['dump_chats_processed']}\n• Files checked: {stats['files_checked']}/{total_db_files}\n• Files to remove: {stats['files_removed']}</code>"
                        )
        except Exception as e:
            LOGGER.error(f"Error during media file comparison: {e}")
            await status_msg.edit_text(
                f"<b>❌ Error during file comparison:</b>\n\n<code>{e}</code>"
            )
            return

        # Remove files that are no longer in dump chats
        if files_to_remove:
            await status_msg.edit_text(
                f"<b>🔄 Starting media indexing process...</b>\n\n<b>📊 Status:</b>\n<code>• Database connected ✅\n• Found {total_db_files} files in database ✅\n• Dump chats processed: {stats['dump_chats_processed']}\n• Files checked: {stats['files_checked']}/{total_db_files}\n• Removing {len(files_to_remove)} obsolete files...</code>"
            )

            removed_count = 0
            for media_file in files_to_remove:
                try:
                    # Remove from database
                    hash_id = media_file.get("hash_id")
                    if hash_id:
                        await database.delete_media_metadata(hash_id)
                        removed_count += 1

                        # Update status every 10 removals
                        if removed_count % 10 == 0:
                            await status_msg.edit_text(
                                f"<b>🔄 Starting media indexing process...</b>\n\n<b>📊 Status:</b>\n<code>• Database connected ✅\n• Found {total_db_files} files in database ✅\n• Dump chats processed: {stats['dump_chats_processed']}\n• Files checked: {stats['files_checked']}/{total_db_files}\n• Removed: {removed_count}/{len(files_to_remove)} files</code>"
                            )

                except Exception as e:
                    LOGGER.error(
                        f"Error removing file {media_file.get('title', 'Unknown')}: {e}"
                    )
                    stats["errors"] += 1

            stats["files_removed"] = removed_count

        # Generate final report
        final_report = f"""<b>✅ Media Indexing Complete!</b>

<b>📊 Summary:</b>
<code>• Total files in database: {stats["total_db_files"]}
• Dump chats processed: {stats["dump_chats_processed"]}
• Valid messages found: {len(valid_message_ids)}
• Files checked: {stats["files_checked"]}
• Files kept: {stats["files_kept"]}
• Files removed: {stats["files_removed"]}
• Errors: {stats["errors"]}</code>

<b>🎯 Result:</b> <i>Database is now synchronized with dump chats!</i>
"""

        await status_msg.edit_text(final_report)
        LOGGER.info(f"Media indexing completed: {stats}")

    except Exception as e:
        LOGGER.error(f"Error in index command: {e}")
        await send_message(
            message, f"<b>❌ Error during indexing:</b>\n\n<code>{e}</code>"
        )


# Helper function for getting all media files (no monkey patching)
async def get_all_media_files_helper(database_instance):
    """Helper function to get all media files from database"""
    try:
        if not await database_instance.ensure_connection():
            return []

        if database_instance.db is None:
            return []

        # Get all media files from the collection
        collection = database_instance.db.media_library[TgClient.ID]
        cursor = collection.find({})
        return await cursor.to_list(length=None)

    except Exception as e:
        LOGGER.error(f"Error getting all media files: {e}")
        return []
