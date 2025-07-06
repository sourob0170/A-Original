from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    KeyboardButtonRequestChat,
    KeyboardButtonRequestUsers,
    ReplyKeyboardMarkup,
)


def get_quickinfo_menu_buttons():
    """Get the main QuickInfo menu keyboard buttons"""
    return ReplyKeyboardMarkup(
        [
            [
                KeyboardButton(
                    "👤 Users",
                    request_users=KeyboardButtonRequestUsers(
                        button_id=1,
                        user_is_bot=False,
                        max_quantity=1,
                    ),
                ),
                KeyboardButton(
                    "🤖 Bots",
                    request_users=KeyboardButtonRequestUsers(
                        button_id=2,
                        user_is_bot=True,
                        max_quantity=1,
                    ),
                ),
                KeyboardButton(
                    "⭐ Premium",
                    request_users=KeyboardButtonRequestUsers(
                        button_id=3,
                        user_is_bot=False,
                        user_is_premium=True,
                        max_quantity=1,
                    ),
                ),
            ],
            [
                KeyboardButton(
                    "🌐 Public Channel",
                    request_chat=KeyboardButtonRequestChat(
                        button_id=5,
                        chat_is_channel=True,
                        chat_has_username=True,
                    ),
                ),
                KeyboardButton(
                    "🌐 Public Group",
                    request_chat=KeyboardButtonRequestChat(
                        button_id=7,
                        chat_is_channel=False,
                        chat_has_username=True,
                    ),
                ),
            ],
            [
                KeyboardButton(
                    "🔒 Private Channel",
                    request_chat=KeyboardButtonRequestChat(
                        button_id=4,
                        chat_is_channel=True,
                        chat_has_username=False,
                    ),
                ),
                KeyboardButton(
                    "🔒 Private Group",
                    request_chat=KeyboardButtonRequestChat(
                        button_id=6,
                        chat_is_channel=False,
                        chat_has_username=False,
                    ),
                ),
            ],
            [
                KeyboardButton(
                    "👥 Your Groups",
                    request_chat=KeyboardButtonRequestChat(
                        button_id=8,
                        chat_is_channel=False,
                        chat_is_created=True,
                    ),
                ),
                KeyboardButton(
                    "🌟 Your Channels",
                    request_chat=KeyboardButtonRequestChat(
                        button_id=9,
                        chat_is_channel=True,
                        chat_is_created=True,
                    ),
                ),
            ],
        ],
        resize_keyboard=True,
    )


def get_quickinfo_inline_buttons():
    """Get inline keyboard buttons for QuickInfo"""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📋 Help", callback_data="quickinfo_help"),
                InlineKeyboardButton(
                    "🔄 Refresh", callback_data="quickinfo_refresh"
                ),
            ],
            [InlineKeyboardButton("❌ Close", callback_data="quickinfo_close")],
        ]
    )


def get_quickinfo_group_buttons():
    """Get inline keyboard buttons for QuickInfo in groups (no RequestPeerType buttons)"""
    from bot.core.aeon_client import TgClient

    # Get bot username for private chat link
    bot_username = getattr(TgClient.bot, "username", None) if TgClient.bot else None

    buttons = [
        [
            InlineKeyboardButton("📋 Help", callback_data="quickinfo_help"),
            InlineKeyboardButton("🔄 Refresh", callback_data="quickinfo_refresh"),
        ],
    ]

    # Add private chat button only if we have bot username
    if bot_username:
        buttons.append(
            [
                InlineKeyboardButton(
                    "💬 Start Private Chat",
                    url=f"https://t.me/{bot_username}?start=quickinfo",
                ),
            ]
        )

    buttons.append(
        [InlineKeyboardButton("❌ Close", callback_data="quickinfo_close")]
    )

    return InlineKeyboardMarkup(buttons)


def get_appropriate_quickinfo_buttons(chat_type):
    """Get appropriate buttons based on chat type"""
    from pyrogram.enums import ChatType

    if chat_type == ChatType.PRIVATE:
        # Private chats can use RequestPeerType buttons
        return get_quickinfo_menu_buttons()
    # Groups/Supergroups/Channels can only use inline buttons
    return get_quickinfo_group_buttons()
