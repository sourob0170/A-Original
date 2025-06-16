from pyrogram.types import CallbackQuery, Message

from bot import LOGGER
from bot.core.aeon_client import TgClient
from bot.core.config_manager import Config
from bot.helper.telegram_helper.message_utils import (
    delete_message,
    edit_message,
    send_message,
)
from bot.helper.telegram_helper.quickinfo_buttons import (
    get_quickinfo_inline_buttons,
    get_quickinfo_menu_buttons,
)
from bot.helper.telegram_helper.quickinfo_utils import (
    formatter,
    get_quickinfo_help_text,
    is_quickinfo_enabled,
)


async def get_full_chat_info(chat_id):
    """Get full chat information using chat ID"""
    try:
        return await TgClient.bot.get_chat(chat_id)
    except Exception as e:
        # Don't log as error for common permission issues
        error_msg = str(e).lower()
        if any(
            keyword in error_msg
            for keyword in [
                "channel_invalid",
                "channel_private",
                "chat_admin_required",
                "peer_id_invalid",
                "forbidden",
                "access_denied",
            ]
        ):
            # These are expected for private/inaccessible chats
            return None
        # Log unexpected errors
        LOGGER.error(f"Unexpected error getting chat info for {chat_id}: {e}")
        return None


async def get_full_user_info(user_id):
    """Get full user information using user ID"""
    try:
        return await TgClient.bot.get_users(user_id)
    except Exception as e:
        # Don't log as error for common permission issues
        error_msg = str(e).lower()
        if any(
            keyword in error_msg
            for keyword in [
                "user_id_invalid",
                "peer_id_invalid",
                "user_not_found",
                "forbidden",
                "access_denied",
                "user_privacy_restricted",
            ]
        ):
            # These are expected for private/inaccessible users
            return None
        # Log unexpected errors
        LOGGER.error(f"Unexpected error getting user info for {user_id}: {e}")
        return None


async def quickinfo_command(client, message: Message):
    """Handle /quickinfo command - includes both menu and current chat info"""
    if not is_quickinfo_enabled():
        await send_message(
            message,
            "❌ <b>QuickInfo feature is currently disabled by the administrator.</b>",
        )
        return

    # Check if command has arguments to show current chat info
    if len(message.command) > 1 and message.command[1].lower() in [
        "chat",
        "current",
        "here",
    ]:
        # Show current chat information
        try:
            chat = message.chat
            chat_info = formatter.format_chat_info(chat, "detailed")

            reply_markup = get_quickinfo_inline_buttons()
            await send_message(
                message,
                f"<b>📋 Current Chat Information</b>\n\n{chat_info}",
                reply_markup,
            )

        except Exception as e:
            LOGGER.error(f"Error getting current chat info: {e}")
            await send_message(message, "❌ <b>Failed to get chat information.</b>")
        return

    # Show QuickInfo menu
    welcome_text = (
        "🆔 <b>Welcome to QuickInfo!</b> 👋\n\n"
        "✅ <b>Fetch Any Chat ID Instantly!</b>\n\n"
        "🔧 <b>How to Use:</b>\n"
        "1️⃣ Click the buttons below to share a chat or user\n"
        "2️⃣ Receive the unique ID instantly\n"
        "3️⃣ Use <code>/quickinfo chat</code> to get current chat info\n\n"
        "💎 <b>Features:</b>\n"
        "• Supports users, bots, private/public groups & channels\n"
        "• Fast and reliable\n"
        "• Get current chat information\n\n"
        f"🛠 <i>{Config.CREDIT}</i>"
    )

    reply_markup = get_quickinfo_menu_buttons()
    await send_message(message, welcome_text, reply_markup)


async def handle_forwarded_message(client, message: Message):
    """Handle forwarded messages to extract source info"""
    if not is_quickinfo_enabled():
        return

    format_style = "detailed"

    try:
        if hasattr(message, "forward_origin") and message.forward_origin:
            origin = message.forward_origin

            if hasattr(origin, "sender_user") and origin.sender_user:
                user = origin.sender_user
                user_info = formatter.format_user_info(user, format_style)

                reply_markup = get_quickinfo_inline_buttons()
                await send_message(
                    message,
                    f"📤 <b>Forwarded Message Info</b>\n\n{user_info}",
                    reply_markup,
                )

            elif hasattr(origin, "chat") and origin.chat:
                chat = origin.chat
                chat_info = formatter.format_chat_info(chat, format_style)

                reply_markup = get_quickinfo_inline_buttons()
                await send_message(
                    message,
                    f"📤 <b>Forwarded Message Info</b>\n\n{chat_info}",
                    reply_markup,
                )

            elif hasattr(origin, "sender_user_name") and origin.sender_user_name:
                await send_message(
                    message,
                    f"📤 <b>Forwarded Message Info</b>\n\n"
                    f"🔒 <b>Looks Like I Don't Have Control Over The User</b>\n"
                    f"📝 Forwarded from: <code>{origin.sender_user_name}</code>",
                )
            else:
                await send_message(
                    message,
                    "📤 <b>Forwarded Message Info</b>\n\n"
                    "🔒 <b>Looks Like I Don't Have Control Over The User</b>",
                )

        else:
            await send_message(
                message,
                "📤 <b>Forwarded Message Info</b>\n\n"
                "🔒 <b>Looks Like I Don't Have Control Over The User</b>",
            )
    except Exception as e:
        LOGGER.error(f"Error handling forwarded message: {e}")
        await send_message(
            message,
            "📤 <b>Forwarded Message Info</b>\n\n"
            "🔒 <b>Looks Like I Don't Have Control Over The User</b>",
        )


async def handle_shared_entities(client, message: Message):
    """Handle shared users and chats"""
    if not is_quickinfo_enabled():
        return

    format_style = "detailed"

    try:
        # Check for shared users (electrogram structure)
        if hasattr(message, "users_shared") and message.users_shared:
            users_shared = message.users_shared
            # Handle both direct list and object with users attribute
            users_list = (
                users_shared
                if isinstance(users_shared, list)
                else getattr(users_shared, "users", [])
            )

            if users_list:  # Only iterate if list is not empty
                for user_data in users_list:
                    if user_data is None:  # Skip None entries
                        continue

                    # Extract user information from shared data
                    user_id_val = getattr(
                        user_data, "user_id", getattr(user_data, "id", None)
                    )
                    if user_id_val is None:  # Skip if no valid ID
                        continue

                    # Try to get full user information
                    full_user = await get_full_user_info(user_id_val)
                    if full_user:
                        # Use full user information
                        user_info = formatter.format_user_info(
                            full_user, format_style
                        )
                    else:
                        # Fallback to shared data
                        first_name = getattr(user_data, "first_name", "Unknown")
                        last_name = getattr(user_data, "last_name", "")
                        username = getattr(user_data, "username", None)

                        # Create a user object from shared data
                        user_obj = type(
                            "User",
                            (),
                            {
                                "id": user_id_val,
                                "first_name": first_name,
                                "last_name": last_name,
                                "username": username,
                                "is_bot": False,  # Will be determined by username pattern
                                "is_premium": False,  # Not available in shared data
                            },
                        )()

                        # Determine if it's a bot based on username
                        if username and username.lower().endswith("bot"):
                            user_obj.is_bot = True

                        user_info = formatter.format_user_info(
                            user_obj, format_style
                        )
                    reply_markup = get_quickinfo_inline_buttons()
                    await send_message(
                        message,
                        f"👥 <b>Shared Entity Info</b>\n\n{user_info}",
                        reply_markup,
                    )

        # Check for shared chats (electrogram structure)
        elif hasattr(message, "chats_shared") and message.chats_shared:
            chats_shared = message.chats_shared
            # Handle both direct list and object with chats attribute
            chats_list = (
                chats_shared
                if isinstance(chats_shared, list)
                else getattr(chats_shared, "chats", [])
            )

            if chats_list:  # Only iterate if list is not empty
                for chat_data in chats_list:
                    if chat_data is None:  # Skip None entries
                        continue

                    # Extract chat information from shared data
                    chat_id_val = getattr(
                        chat_data, "chat_id", getattr(chat_data, "id", None)
                    )
                    if chat_id_val is None:  # Skip if no valid ID
                        continue

                    # Try to get full chat information
                    full_chat = await get_full_chat_info(chat_id_val)
                    if full_chat:
                        # Use full chat information
                        chat_info = formatter.format_chat_info(
                            full_chat, format_style
                        )
                    else:
                        # Fallback to shared data with limited access note
                        chat_title = getattr(
                            chat_data,
                            "title",
                            getattr(chat_data, "name", "Unknown Chat"),
                        )
                        chat_type = getattr(
                            chat_data,
                            "type",
                            getattr(chat_data, "chat_type", "Unknown"),
                        )

                        # Create a chat object from shared data
                        chat_obj = type(
                            "Chat",
                            (),
                            {
                                "id": chat_id_val,
                                "title": chat_title,
                                "username": None,  # Not available in shared data
                                "type": chat_type,
                                "members_count": "Unknown",
                            },
                        )()

                        chat_info = formatter.format_chat_info(
                            chat_obj, format_style, limited_access=True
                        )
                    reply_markup = get_quickinfo_inline_buttons()
                    await send_message(
                        message,
                        f"👥 <b>Shared Entity Info</b>\n\n{chat_info}",
                        reply_markup,
                    )

        # Check for user_shared (single user) - alternative electrogram structure
        elif hasattr(message, "user_shared") and message.user_shared:
            user_data = message.user_shared
            if user_data is not None:
                user_id_val = getattr(
                    user_data, "user_id", getattr(user_data, "id", None)
                )
                if user_id_val is not None:
                    # Try to get full user information
                    full_user = await get_full_user_info(user_id_val)
                    if full_user:
                        # Use full user information
                        user_info = formatter.format_user_info(
                            full_user, format_style
                        )
                    else:
                        # Fallback to shared data
                        first_name = getattr(user_data, "first_name", "Unknown")
                        last_name = getattr(user_data, "last_name", "")
                        username = getattr(user_data, "username", None)

                        user_obj = type(
                            "User",
                            (),
                            {
                                "id": user_id_val,
                                "first_name": first_name,
                                "last_name": last_name,
                                "username": username,
                                "is_bot": False,
                                "is_premium": False,
                            },
                        )()

                        if username and username.lower().endswith("bot"):
                            user_obj.is_bot = True

                        user_info = formatter.format_user_info(
                            user_obj, format_style
                        )
                    reply_markup = get_quickinfo_inline_buttons()
                    await send_message(
                        message,
                        f"👥 <b>Shared Entity Info</b>\n\n{user_info}",
                        reply_markup,
                    )

        # Check for chat_shared (single chat) - alternative electrogram structure
        elif hasattr(message, "chat_shared") and message.chat_shared:
            chat_data = message.chat_shared
            if chat_data is not None:
                chat_id_val = getattr(
                    chat_data, "chat_id", getattr(chat_data, "id", None)
                )
                if chat_id_val is not None:
                    # Try to get full chat information
                    full_chat = await get_full_chat_info(chat_id_val)
                    if full_chat:
                        # Use full chat information
                        chat_info = formatter.format_chat_info(
                            full_chat, format_style
                        )
                    else:
                        # Fallback to shared data with limited access note
                        chat_title = getattr(
                            chat_data,
                            "title",
                            getattr(chat_data, "name", "Unknown Chat"),
                        )
                        chat_type = getattr(
                            chat_data,
                            "type",
                            getattr(chat_data, "chat_type", "Unknown"),
                        )

                        chat_obj = type(
                            "Chat",
                            (),
                            {
                                "id": chat_id_val,
                                "title": chat_title,
                                "username": None,
                                "type": chat_type,
                                "members_count": "Unknown",
                            },
                        )()

                        chat_info = formatter.format_chat_info(
                            chat_obj, format_style, limited_access=True
                        )
                    reply_markup = get_quickinfo_inline_buttons()
                    await send_message(
                        message,
                        f"👥 <b>Shared Entity Info</b>\n\n{chat_info}",
                        reply_markup,
                    )

        else:
            # No shared entities found, show instruction message
            await send_message(
                message,
                "💡 <b>Please use the provided buttons to share a group, bot, channel, or user.</b>",
            )

    except Exception as e:
        LOGGER.error(f"Error handling shared entities: {e}")
        await send_message(
            message, "❌ <b>Failed to process shared entity information.</b>"
        )


async def quickinfo_callback(client, callback_query: CallbackQuery):
    """Handle QuickInfo callback queries"""
    data = callback_query.data
    message = callback_query.message

    try:
        if data == "quickinfo_help":
            help_text = get_quickinfo_help_text()
            await edit_message(message, help_text, get_quickinfo_inline_buttons())

        elif data == "quickinfo_refresh":
            welcome_text = (
                "🆔 <b>Welcome to QuickInfo!</b> 👋\n\n"
                "✅ <b>Fetch Any Chat ID Instantly!</b>\n\n"
                "🔧 <b>How to Use:</b>\n"
                "1️⃣ Click the buttons below to share a chat or user\n"
                "2️⃣ Receive the unique ID instantly\n"
                "3️⃣ Use <code>/quickinfo chat</code> to get current chat info\n\n"
                "💎 <b>Features:</b>\n"
                "• Supports users, bots, private/public groups & channels\n"
                "• Fast and reliable\n"
                "• Get current chat information\n\n"
                f"🛠 <i>{Config.CREDIT}</i>"
            )
            await edit_message(message, welcome_text, get_quickinfo_inline_buttons())

        elif data == "quickinfo_close":
            await delete_message(message)

        elif data == "quickinfo_back":
            welcome_text = (
                "🆔 <b>Welcome to QuickInfo!</b> 👋\n\n"
                "✅ <b>Fetch Any Chat ID Instantly!</b>\n\n"
                "🔧 <b>How to Use:</b>\n"
                "1️⃣ Click the buttons below to share a chat or user\n"
                "2️⃣ Receive the unique ID instantly\n"
                "3️⃣ Use <code>/quickinfo chat</code> to get current chat info\n\n"
                "💎 <b>Features:</b>\n"
                "• Supports users, bots, private/public groups & channels\n"
                "• Fast and reliable\n"
                "• Get current chat information\n\n"
                f"🛠 <i>{Config.CREDIT}</i>"
            )
            await edit_message(message, welcome_text, get_quickinfo_inline_buttons())

        else:
            await callback_query.answer("❌ Unknown action")

    except Exception as e:
        LOGGER.error(f"Error in quickinfo callback: {e}")
        await callback_query.answer("❌ An error occurred")
