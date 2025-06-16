from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    RequestPeerTypeChannel,
    RequestPeerTypeChat,
    RequestPeerTypeUser,
)


def get_quickinfo_menu_buttons():
    """Get the main QuickInfo menu keyboard buttons"""
    return ReplyKeyboardMarkup(
        [
            [
                KeyboardButton(
                    "👤 Users",
                    request_user=RequestPeerTypeUser(
                        button_id=1,
                        is_bot=False,
                        max=1,
                        is_name_requested=True,
                        is_username_requested=True,
                    ),
                ),
                KeyboardButton(
                    "🤖 Bots",
                    request_user=RequestPeerTypeUser(
                        button_id=2,
                        is_bot=True,
                        max=1,
                        is_name_requested=True,
                        is_username_requested=True,
                    ),
                ),
                KeyboardButton(
                    "⭐ Premium",
                    request_user=RequestPeerTypeUser(
                        button_id=3,
                        is_bot=False,
                        is_premium=True,
                        max=1,
                        is_name_requested=True,
                        is_username_requested=True,
                    ),
                ),
            ],
            [
                KeyboardButton(
                    "🌐 Public Channel",
                    request_chat=RequestPeerTypeChannel(
                        button_id=5,
                        is_username=True,
                        max=1,
                        is_name_requested=True,
                        is_username_requested=True,
                    ),
                ),
                KeyboardButton(
                    "🌐 Public Group",
                    request_chat=RequestPeerTypeChat(
                        button_id=7,
                        is_username=True,
                        max=1,
                        is_name_requested=True,
                        is_username_requested=True,
                    ),
                ),
            ],
            [
                KeyboardButton(
                    "🔒 Private Channel",
                    request_chat=RequestPeerTypeChannel(
                        button_id=4,
                        is_username=False,
                        max=1,
                        is_name_requested=True,
                        is_username_requested=True,
                    ),
                ),
                KeyboardButton(
                    "🔒 Private Group",
                    request_chat=RequestPeerTypeChat(
                        button_id=6,
                        is_username=False,
                        max=1,
                        is_name_requested=True,
                        is_username_requested=True,
                    ),
                ),
            ],
            [
                KeyboardButton(
                    "👥 Your Groups",
                    request_chat=RequestPeerTypeChat(
                        button_id=8,
                        is_creator=True,
                        max=1,
                        is_name_requested=True,
                        is_username_requested=True,
                    ),
                ),
                KeyboardButton(
                    "🌟 Your Channels",
                    request_chat=RequestPeerTypeChannel(
                        button_id=9,
                        is_creator=True,
                        max=1,
                        is_name_requested=True,
                        is_username_requested=True,
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
