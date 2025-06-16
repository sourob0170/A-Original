from pyrogram.types import Chat, User

from bot.core.config_manager import Config


class QuickInfoFormatter:
    """Handles formatting for QuickInfo responses"""

    @staticmethod
    def format_user_info(user: User, style: str = "detailed") -> str:
        """Format user information"""
        user_id = user.id
        first_name = user.first_name or "N/A"
        last_name = user.last_name or ""
        username = f"@{user.username}" if user.username else "No username"
        user_type = "Bot" if user.is_bot else "User"
        is_premium = getattr(user, "is_premium", False)

        premium_info = "\n🌟 <b>Premium:</b> <code>Yes</code>" if is_premium else ""
        return (
            f"👤 <b>{user_type} Information</b>\n\n"
            f"🏷 <b>Type:</b> <code>{user_type}</code>\n"
            f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
            f"📝 <b>Name:</b> <code>{(first_name + ' ' + last_name).strip()}</code>\n"
            f"🔗 <b>Username:</b> <code>{username}</code>" + premium_info
        )

    @staticmethod
    def format_chat_info(
        chat: Chat, style: str = "detailed", limited_access: bool = False
    ) -> str:
        """Format chat information"""
        chat_id = chat.id
        chat_name = chat.title or "Unnamed Chat"
        chat_type = str(chat.type).replace("ChatType.", "").capitalize()
        username = f"@{chat.username}" if chat.username else "Private/No username"
        members_count = getattr(chat, "members_count", "Private/Unknown")

        # Add note for limited access
        access_note = ""
        if limited_access:
            access_note = (
                "\n\n🔒 <i>Limited info - Bot doesn't have access to this chat</i>"
            )

        return (
            f"💬 <b>{chat_type} Information</b>\n\n"
            f"🏷 <b>Type:</b> <code>{chat_type}</code>\n"
            f"🆔 <b>ID:</b> <code>{chat_id}</code>\n"
            f"📝 <b>Name:</b> <code>{chat_name}</code>\n"
            f"🔗 <b>Username:</b> <code>{username}</code>\n"
            f"👥 <b>Members:</b> <code>{members_count}</code>" + access_note
        )


def is_quickinfo_enabled() -> bool:
    """Check if QuickInfo feature is enabled"""
    return getattr(Config, "QUICKINFO_ENABLED", True)


def get_quickinfo_help_text() -> str:
    """Get help text for QuickInfo"""
    return (
        "🚀 <b>QuickInfo Help Center</b> 🌟\n\n"
        "🔍 <b>Need to grab a chat ID? We've got you covered!</b>\n\n"
        "📋 <b>Commands &amp; Features:</b>\n"
        "👉 <code>/quickinfo</code> or <code>/qi</code> - Launch QuickInfo with interactive buttons! 🎮\n"
        "👉 <code>/quickinfo chat</code> - Get current chat information 📖\n"
        "👉 <b>Forward Messages</b> - Send any forwarded message to reveal its source ID! 🔎\n"
        "👉 <b>Buttons</b> - Pick from users, bots, groups, or channels to get IDs instantly ⚡\n\n"
        "💡 <b>Pro Tip:</b> Forward a message from any chat, and I'll dig up the details! 🕵️\n\n"
        "📩 <b>Support:</b> Contact administrators for help! 😎"
    )


# Global instances
formatter = QuickInfoFormatter()
