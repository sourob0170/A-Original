from asyncio import sleep as asyncio_sleep
from logging import getLogger

from pyrogram import filters
from pyrogram.errors import FloodWait, InputUserDeactivated, UserIsBlocked
from pyrogram.handlers import MessageHandler

from bot.core.aeon_client import TgClient
from bot.core.config_manager import Config
from bot.helper.ext_utils.bot_utils import new_task
from bot.helper.ext_utils.db_handler import database
from bot.helper.telegram_helper.message_utils import send_message

LOGGER = getLogger(__name__)

# Default keywords to detect in messages
DEFAULT_AD_KEYWORDS = [
    "#ad",
    "#AD",
    "InsideAds",
    "AD",
    "ad",
    "Advertise",
    "advertise",
    "Advertisement",
    "ADVERTISE",
]


# Function to get ad keywords (from config or default)
def get_ad_keywords():
    """Get ad keywords from config or use defaults"""
    if Config.AD_KEYWORDS:
        # Split by comma and strip whitespace, preserving spaces within phrases
        custom_keywords = [
            keyword.strip()
            for keyword in Config.AD_KEYWORDS.split(",")
            if keyword.strip()
        ]
        LOGGER.info(f"Using custom ad keywords (phrases): {custom_keywords}")
        return custom_keywords

    LOGGER.info(f"Using default ad keywords: {DEFAULT_AD_KEYWORDS}")
    return DEFAULT_AD_KEYWORDS


@new_task
async def handle_ad_message(_, message):
    """
    Handler for messages from FSUB_IDS channels that contain ad keywords
    """
    # Check if ad broadcaster is enabled at runtime
    if not Config.AD_BROADCASTER_ENABLED:
        return

    # Get the current ad keywords (from config or default)
    ad_keywords = get_ad_keywords()

    # Skip if message doesn't contain any of the ad keywords
    message_text = message.text or message.caption or ""

    # Check if any of the keywords/phrases are in the message
    found_keyword = None
    for keyword in ad_keywords:
        if keyword in message_text:
            found_keyword = keyword
            break

    if not found_keyword:
        return

    LOGGER.info(
        f"Ad detected with keyword/phrase: '{found_keyword}' in message: {message.id}"
    )

    # Get the message link
    chat_id = message.chat.id
    message_id = message.id

    # Create message link
    message_link = f"https://t.me/c/{str(chat_id).replace('-100', '')}/{message_id}"

    # Get channel name
    try:
        channel_name = message.chat.title or "our channel"
    except Exception:
        channel_name = "our channel"

    # Create broadcast message with better formatting
    broadcast_text = (
        f"<pre>╭──────────────────────╮\n"
        f"│    📢 <b>AD BROADCAST</b> 📢    │\n"
        f"╰──────────────────────╯</pre>\n\n"
        f"<blockquote>Please click the ad to support {channel_name}! This will help us grow and buy Telegram premium for 4GB uploads.</blockquote>\n\n"
        f"<a href='{message_link}'><b>➡️ View Original Message</b></a>"
    )

    # Get all users
    pm_users = await database.get_pm_uids()
    if not pm_users:
        LOGGER.info("No users found in database for ad broadcast")
        return

    # Start broadcasting
    LOGGER.info(f"Starting ad broadcast to {len(pm_users)} users")

    successful, blocked, unsuccessful = 0, 0, 0

    for uid in pm_users:
        try:
            await send_message(uid, broadcast_text)
            successful += 1
        except FloodWait as e:
            LOGGER.warning(f"FloodWait: Sleeping for {e.value} seconds")
            await asyncio_sleep(e.value)
            try:
                await send_message(uid, broadcast_text)
                successful += 1
            except Exception as retry_err:
                LOGGER.error(
                    f"Failed to send ad broadcast to {uid} after FloodWait: {retry_err}"
                )
                unsuccessful += 1
        except (UserIsBlocked, InputUserDeactivated) as user_err:
            LOGGER.info(f"Removing user {uid} from database: {user_err}")
            await database.rm_pm_user(uid)
            blocked += 1
        except Exception as e:
            LOGGER.error(f"Error sending ad broadcast to {uid}: {e}")
            unsuccessful += 1

    LOGGER.info(
        f"Ad Broadcast completed: {successful} successful, {blocked} blocked, {unsuccessful} unsuccessful"
    )


def init_ad_broadcaster():
    """Initialize the ad broadcaster module"""
    if not Config.AD_BROADCASTER_ENABLED:
        LOGGER.info("Ad broadcaster is disabled, not initializing")
        return

    if not Config.FSUB_IDS:
        LOGGER.info("FSUB_IDS not configured, ad broadcaster not initialized")
        return

    # Log the keywords that will be used
    ad_keywords = get_ad_keywords()
    LOGGER.info(f"Ad broadcaster will detect the following keywords: {ad_keywords}")

    # Create a filter for messages from FSUB_IDS channels
    async def fsub_filter(_, __, message):
        # Check if ad broadcaster is enabled at runtime
        if not Config.AD_BROADCASTER_ENABLED:
            return False

        if not Config.FSUB_IDS:
            return False

        # Check if message is from one of the FSUB_IDS channels
        chat_id = message.chat.id
        fsub_ids = [int(channel_id) for channel_id in Config.FSUB_IDS.split()]
        return chat_id in fsub_ids

    # Register the message handler for text messages
    TgClient.bot.add_handler(
        MessageHandler(
            handle_ad_message,
            filters=filters.create(fsub_filter) & (filters.text | filters.caption),
        ),
        group=10,  # Use a high group number to ensure it's processed after other handlers
    )

    LOGGER.info("Ad broadcaster initialized")
