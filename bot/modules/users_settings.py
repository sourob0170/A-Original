from asyncio import create_subprocess_exec, create_task, sleep
from functools import partial
from html import escape
from io import BytesIO
from os import getcwd
from re import findall
from time import time

from pyrogram.filters import create
from pyrogram.handlers import MessageHandler

from bot import LOGGER, auth_chats, excluded_extensions, sudo_users, user_data
from bot.core.aeon_client import TgClient
from bot.core.config_manager import Config
from bot.helper.ext_utils.aiofiles_compat import aiopath, makedirs, remove
from bot.helper.ext_utils.bot_utils import (
    get_size_bytes,
    new_task,
    update_user_ldata,
)
from bot.helper.ext_utils.db_handler import database
from bot.helper.ext_utils.help_messages import user_settings_text
from bot.helper.ext_utils.media_utils import create_thumb
from bot.helper.ext_utils.status_utils import get_readable_file_size
from bot.helper.telegram_helper.button_build import ButtonMaker
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    delete_message,
    edit_message,
    send_file,
    send_message,
)

handler_dict = {}
no_thumb = Config.OWNER_THUMB

leech_options = [
    "THUMBNAIL",
    "LEECH_SPLIT_SIZE",
    "EQUAL_SPLITS",
    "LEECH_FILENAME_PREFIX",
    "LEECH_SUFFIX",
    "LEECH_FONT",
    "LEECH_FILENAME",
    "LEECH_FILENAME_CAPTION",
    "THUMBNAIL_LAYOUT",
    "USER_DUMP",
    "USER_SESSION",
    "MEDIA_STORE",
]

ai_options = [
    "DEFAULT_AI_PROVIDER",
    "MISTRAL_API_URL",
    "DEEPSEEK_API_URL",
]
metadata_options = [
    "METADATA_ALL",
    "METADATA_TITLE",
    "METADATA_AUTHOR",
    "METADATA_COMMENT",
    "METADATA_VIDEO_TITLE",
    "METADATA_VIDEO_AUTHOR",
    "METADATA_VIDEO_COMMENT",
    "METADATA_AUDIO_TITLE",
    "METADATA_AUDIO_AUTHOR",
    "METADATA_AUDIO_COMMENT",
    "METADATA_SUBTITLE_TITLE",
    "METADATA_SUBTITLE_AUTHOR",
    "METADATA_SUBTITLE_COMMENT",
    "METADATA_KEY",
]
convert_options = []


rclone_options = ["RCLONE_CONFIG", "RCLONE_PATH", "RCLONE_FLAGS"]
gdrive_options = ["TOKEN_PICKLE", "GDRIVE_ID", "INDEX_URL"]
youtube_options = [
    "YOUTUBE_TOKEN_PICKLE",
    "YOUTUBE_UPLOAD_DEFAULT_PRIVACY",
    "YOUTUBE_UPLOAD_DEFAULT_CATEGORY",
    "YOUTUBE_UPLOAD_DEFAULT_TAGS",
    "YOUTUBE_UPLOAD_DEFAULT_DESCRIPTION",
    "YOUTUBE_UPLOAD_DEFAULT_TITLE",
    "YOUTUBE_UPLOAD_DEFAULT_LANGUAGE",
    "YOUTUBE_UPLOAD_DEFAULT_LICENSE",
    "YOUTUBE_UPLOAD_EMBEDDABLE",
    "YOUTUBE_UPLOAD_PUBLIC_STATS_VIEWABLE",
    "YOUTUBE_UPLOAD_MADE_FOR_KIDS",
    "YOUTUBE_UPLOAD_NOTIFY_SUBSCRIBERS",
    "YOUTUBE_UPLOAD_LOCATION_DESCRIPTION",
    "YOUTUBE_UPLOAD_RECORDING_DATE",
    "YOUTUBE_UPLOAD_AUTO_LEVELS",
    "YOUTUBE_UPLOAD_STABILIZE",
]
mega_options = [
    "MEGA_EMAIL",
    "MEGA_PASSWORD",
    "MEGA_UPLOAD_FOLDER",
    "MEGA_UPLOAD_PUBLIC",
    "MEGA_UPLOAD_PRIVATE",
    "MEGA_UPLOAD_UNLISTED",
    "MEGA_UPLOAD_EXPIRY_DAYS",
    "MEGA_UPLOAD_PASSWORD",
    "MEGA_UPLOAD_ENCRYPTION_KEY",
    "MEGA_UPLOAD_THUMBNAIL",
    "MEGA_UPLOAD_DELETE_AFTER",
    "MEGA_CLONE_TO_FOLDER",
    "MEGA_CLONE_PRESERVE_STRUCTURE",
    "MEGA_CLONE_OVERWRITE",
]
yt_dlp_options = ["YT_DLP_OPTIONS", "USER_COOKIES", "FFMPEG_CMDS"]


async def get_user_settings(from_user, stype="main"):
    from bot.helper.ext_utils.bot_utils import is_media_tool_enabled

    user_id = from_user.id
    name = from_user.mention
    buttons = ButtonMaker()
    rclone_conf = f"rclone/{user_id}.conf"
    token_pickle = f"tokens/{user_id}.pickle"
    thumbpath = f"thumbnails/{user_id}.jpg"
    user_dict = user_data.get(user_id, {})
    thumbnail = thumbpath if await aiopath.exists(thumbpath) else no_thumb

    # Helper function to get MEGA settings with user priority
    def get_mega_setting(setting_name, default_value=None, is_bool=False):
        user_value = user_dict.get(setting_name, None)
        if user_value is not None:
            return user_value, "User"
        owner_value = getattr(Config, setting_name, default_value)
        return owner_value, "Owner"

    if stype == "leech":
        buttons.data_button("Thumbnail", f"userset {user_id} menu THUMBNAIL")
        buttons.data_button(
            "Leech Prefix",
            f"userset {user_id} menu LEECH_FILENAME_PREFIX",
        )
        if user_dict.get("LEECH_FILENAME_PREFIX", False):
            lprefix = user_dict["LEECH_FILENAME_PREFIX"]
        elif (
            "LEECH_FILENAME_PREFIX" not in user_dict and Config.LEECH_FILENAME_PREFIX
        ):
            lprefix = Config.LEECH_FILENAME_PREFIX
        else:
            lprefix = "None"
        buttons.data_button(
            "Leech Suffix",
            f"userset {user_id} menu LEECH_SUFFIX",
        )
        if user_dict.get("LEECH_SUFFIX", False):
            lsuffix = user_dict["LEECH_SUFFIX"]
        elif "LEECH_SUFFIX" not in user_dict and Config.LEECH_SUFFIX:
            lsuffix = Config.LEECH_SUFFIX
        else:
            lsuffix = "None"

        buttons.data_button(
            "Leech Font",
            f"userset {user_id} menu LEECH_FONT",
        )
        if user_dict.get("LEECH_FONT", False):
            lfont = user_dict["LEECH_FONT"]
        elif "LEECH_FONT" not in user_dict and Config.LEECH_FONT:
            lfont = Config.LEECH_FONT
        else:
            lfont = "None"

        buttons.data_button(
            "Leech Filename",
            f"userset {user_id} menu LEECH_FILENAME",
        )
        if user_dict.get("LEECH_FILENAME", False):
            lfilename = user_dict["LEECH_FILENAME"]
        elif "LEECH_FILENAME" not in user_dict and Config.LEECH_FILENAME:
            lfilename = Config.LEECH_FILENAME
        else:
            lfilename = "None"

        buttons.data_button(
            "Leech Caption",
            f"userset {user_id} menu LEECH_FILENAME_CAPTION",
        )
        if user_dict.get("LEECH_FILENAME_CAPTION", False):
            lcap = user_dict["LEECH_FILENAME_CAPTION"]
        elif (
            "LEECH_FILENAME_CAPTION" not in user_dict
            and Config.LEECH_FILENAME_CAPTION
        ):
            lcap = Config.LEECH_FILENAME_CAPTION
        else:
            lcap = "None"
        buttons.data_button(
            "User Dump",
            f"userset {user_id} menu USER_DUMP",
        )
        if user_dict.get("USER_DUMP", False):
            udump = user_dict["USER_DUMP"]
        else:
            udump = "None"
        buttons.data_button(
            "User Session",
            f"userset {user_id} menu USER_SESSION",
        )
        usess = "added" if user_dict.get("USER_SESSION", False) else "None"
        buttons.data_button(
            "Leech Split Size",
            f"userset {user_id} menu LEECH_SPLIT_SIZE",
        )
        # Handle LEECH_SPLIT_SIZE, ensuring it's an integer
        if user_dict.get("LEECH_SPLIT_SIZE"):
            lsplit = user_dict["LEECH_SPLIT_SIZE"]
            # Convert to int if it's not already
            if not isinstance(lsplit, int):
                try:
                    lsplit = int(lsplit)
                except (ValueError, TypeError):
                    lsplit = 0
        elif "LEECH_SPLIT_SIZE" not in user_dict and Config.LEECH_SPLIT_SIZE:
            lsplit = Config.LEECH_SPLIT_SIZE
        else:
            lsplit = "None"
        buttons.data_button(
            "Equal Splits",
            f"userset {user_id} tog EQUAL_SPLITS {'f' if user_dict.get('EQUAL_SPLITS', False) or ('EQUAL_SPLITS' not in user_dict and Config.EQUAL_SPLITS) else 't'}",
        )
        if user_dict.get("AS_DOCUMENT", False) or (
            "AS_DOCUMENT" not in user_dict and Config.AS_DOCUMENT
        ):
            ltype = "DOCUMENT"
            buttons.data_button(
                "Send As Media",
                f"userset {user_id} tog AS_DOCUMENT f",
            )
        else:
            ltype = "MEDIA"
            buttons.data_button(
                "Send As Document",
                f"userset {user_id} tog AS_DOCUMENT t",
            )
        if user_dict.get("MEDIA_GROUP", False) or (
            "MEDIA_GROUP" not in user_dict and Config.MEDIA_GROUP
        ):
            buttons.data_button(
                "Disable Media Group",
                f"userset {user_id} tog MEDIA_GROUP f",
            )
            media_group = "Enabled"
        else:
            buttons.data_button(
                "Enable Media Group",
                f"userset {user_id} tog MEDIA_GROUP t",
            )
            media_group = "Disabled"

        # Add Media Store toggle
        if user_dict.get("MEDIA_STORE", False) or (
            "MEDIA_STORE" not in user_dict and Config.MEDIA_STORE
        ):
            buttons.data_button(
                "Disable Media Store",
                f"userset {user_id} tog MEDIA_STORE f",
            )
            media_store = "Enabled"
        else:
            buttons.data_button(
                "Enable Media Store",
                f"userset {user_id} tog MEDIA_STORE t",
            )
            media_store = "Disabled"
        buttons.data_button(
            "Thumbnail Layout",
            f"userset {user_id} menu THUMBNAIL_LAYOUT",
        )
        if user_dict.get("THUMBNAIL_LAYOUT", False):
            thumb_layout = user_dict["THUMBNAIL_LAYOUT"]
        elif "THUMBNAIL_LAYOUT" not in user_dict and Config.THUMBNAIL_LAYOUT:
            thumb_layout = Config.THUMBNAIL_LAYOUT
        else:
            thumb_layout = "None"

        buttons.data_button("Back", f"userset {user_id} back")
        buttons.data_button("Close", f"userset {user_id} close")

        # Determine Equal Splits status
        equal_splits_status = (
            "Enabled"
            if user_dict.get("EQUAL_SPLITS", False)
            or ("EQUAL_SPLITS" not in user_dict and Config.EQUAL_SPLITS)
            else "Disabled"
        )

        # Determine Media Store status
        media_store = (
            "Enabled"
            if user_dict.get("MEDIA_STORE", False)
            or ("MEDIA_STORE" not in user_dict and Config.MEDIA_STORE)
            else "Disabled"
        )

        # Format split size for display
        if isinstance(lsplit, int) and lsplit > 0:
            lsplit_display = get_readable_file_size(lsplit)
        elif lsplit == "None":
            lsplit_display = "None"
        else:
            try:
                # Try to convert to int and display as readable size
                lsplit_int = int(lsplit)
                if lsplit_int > 0:
                    lsplit_display = get_readable_file_size(lsplit_int)
                else:
                    lsplit_display = "None"
            except (ValueError, TypeError):
                lsplit_display = "None"

        text = f"""<u><b>Leech Settings for {name}</b></u>
-> Leech Type: <b>{ltype}</b>
-> Media Group: <b>{media_group}</b>
-> Media Store: <b>{media_store}</b>
-> Leech Prefix: <code>{escape(lprefix)}</code>
-> Leech Suffix: <code>{escape(lsuffix)}</code>
-> Leech Font: <code>{escape(lfont)}</code>
-> Leech Filename: <code>{escape(lfilename)}</code>
-> Leech Caption: <code>{escape(lcap)}</code>
-> User Session id: {usess}
-> User Dump: <code>{udump}</code>
-> Thumbnail Layout: <b>{thumb_layout}</b>
-> Leech Split Size: <b>{lsplit_display}</b>
-> Equal Splits: <b>{equal_splits_status}</b>
"""
    elif stype == "rclone":
        buttons.data_button("Rclone Config", f"userset {user_id} menu RCLONE_CONFIG")
        buttons.data_button(
            "Default Rclone Path",
            f"userset {user_id} menu RCLONE_PATH",
        )
        buttons.data_button("Rclone Flags", f"userset {user_id} menu RCLONE_FLAGS")
        buttons.data_button("Back", f"userset {user_id} back")
        buttons.data_button("Close", f"userset {user_id} close")
        rccmsg = "Exists" if await aiopath.exists(rclone_conf) else "Not Exists"
        if "RCLONE_PATH" in user_dict:
            rccpath = user_dict["RCLONE_PATH"]
            path_source = "Your"
        elif Config.RCLONE_PATH:
            rccpath = Config.RCLONE_PATH
            path_source = "Owner's"
        else:
            rccpath = "None"
            path_source = ""
        if user_dict.get("RCLONE_FLAGS", False):
            rcflags = user_dict["RCLONE_FLAGS"]
        elif "RCLONE_FLAGS" not in user_dict and Config.RCLONE_FLAGS:
            rcflags = Config.RCLONE_FLAGS
        else:
            rcflags = "None"
        path_display = (
            f"{path_source} Path: <code>{rccpath}</code>"
            if path_source
            else f"Path: <code>{rccpath}</code>"
        )
        text = f"""<u><b>Rclone Settings for {name}</b></u>
-> Rclone Config : <b>{rccmsg}</b>
-> Rclone {path_display}
-> Rclone Flags   : <code>{rcflags}</code>

<blockquote>Dont understand? Then follow this <a href='https://t.me/aimupdate/215'>quide</a></blockquote>

"""
    elif stype == "gdrive":
        buttons.data_button("token.pickle", f"userset {user_id} menu TOKEN_PICKLE")
        buttons.data_button("Default Gdrive ID", f"userset {user_id} menu GDRIVE_ID")
        buttons.data_button("Index URL", f"userset {user_id} menu INDEX_URL")
        if user_dict.get("STOP_DUPLICATE", False) or (
            "STOP_DUPLICATE" not in user_dict and Config.STOP_DUPLICATE
        ):
            buttons.data_button(
                "Disable Stop Duplicate",
                f"userset {user_id} tog STOP_DUPLICATE f",
            )
            sd_msg = "Enabled"
        else:
            buttons.data_button(
                "Enable Stop Duplicate",
                f"userset {user_id} tog STOP_DUPLICATE t",
            )
            sd_msg = "Disabled"
        buttons.data_button("Back", f"userset {user_id} back")
        buttons.data_button("Close", f"userset {user_id} close")
        tokenmsg = "Exists" if await aiopath.exists(token_pickle) else "Not Exists"
        if user_dict.get("GDRIVE_ID", False):
            gdrive_id = user_dict["GDRIVE_ID"]
        elif GDID := Config.GDRIVE_ID:
            gdrive_id = GDID
        else:
            gdrive_id = "None"
        index = (
            user_dict["INDEX_URL"] if user_dict.get("INDEX_URL", False) else "None"
        )
        text = f"""<u><b>Gdrive API Settings for {name}</b></u>
-> Gdrive Token: <b>{tokenmsg}</b>
-> Gdrive ID: <code>{gdrive_id}</code>
-> Index URL: <code>{index}</code>
-> Stop Duplicate: <b>{sd_msg}</b>"""
    elif stype == "youtube":
        # Create organized menu with categories
        buttons.data_button(
            "🔑 YouTube Token", f"userset {user_id} menu YOUTUBE_TOKEN_PICKLE"
        )
        buttons.data_button("📹 Basic Settings", f"userset {user_id} youtube_basic")
        buttons.data_button(
            "⚙️ Advanced Settings", f"userset {user_id} youtube_advanced"
        )

        buttons.data_button("Back", f"userset {user_id} back")
        buttons.data_button("Close", f"userset {user_id} close")

        # Check if YouTube token exists
        youtube_token_path = f"tokens/{user_id}_youtube.pickle"
        youtube_tokenmsg = (
            "Exists" if await aiopath.exists(youtube_token_path) else "Not Exists"
        )

        # Get basic YouTube settings with user priority over owner settings
        youtube_privacy = user_dict.get(
            "YOUTUBE_UPLOAD_DEFAULT_PRIVACY", Config.YOUTUBE_UPLOAD_DEFAULT_PRIVACY
        )
        youtube_category = user_dict.get(
            "YOUTUBE_UPLOAD_DEFAULT_CATEGORY", Config.YOUTUBE_UPLOAD_DEFAULT_CATEGORY
        )
        youtube_tags = (
            user_dict.get(
                "YOUTUBE_UPLOAD_DEFAULT_TAGS", Config.YOUTUBE_UPLOAD_DEFAULT_TAGS
            )
            or "None"
        )
        youtube_description = user_dict.get(
            "YOUTUBE_UPLOAD_DEFAULT_DESCRIPTION",
            Config.YOUTUBE_UPLOAD_DEFAULT_DESCRIPTION,
        )

        text = f"""<u><b>YouTube API Settings for {name}</b></u>
-> YouTube Token: <b>{youtube_tokenmsg}</b>
-> Default Privacy: <code>{youtube_privacy}</code>
-> Default Category: <code>{youtube_category}</code>
-> Default Tags: <code>{youtube_tags}</code>
-> Default Description: <code>{youtube_description}</code>

<i>Note: Your settings will take priority over the bot owner's settings.</i>
<i>Upload videos to YouTube using: -up yt or -up yt:privacy:category:tags</i>
<i>Use the menu buttons below to configure different aspects of YouTube uploads.</i>"""
    elif stype == "youtube_basic":
        # Basic YouTube settings
        buttons.data_button(
            "Default Privacy",
            f"userset {user_id} menu YOUTUBE_UPLOAD_DEFAULT_PRIVACY",
        )
        buttons.data_button(
            "Default Category",
            f"userset {user_id} menu YOUTUBE_UPLOAD_DEFAULT_CATEGORY",
        )
        buttons.data_button(
            "Default Tags", f"userset {user_id} menu YOUTUBE_UPLOAD_DEFAULT_TAGS"
        )
        buttons.data_button(
            "Default Description",
            f"userset {user_id} menu YOUTUBE_UPLOAD_DEFAULT_DESCRIPTION",
        )
        buttons.data_button(
            "Default Title", f"userset {user_id} menu YOUTUBE_UPLOAD_DEFAULT_TITLE"
        )
        buttons.data_button(
            "Default Language",
            f"userset {user_id} menu YOUTUBE_UPLOAD_DEFAULT_LANGUAGE",
        )
        buttons.data_button("Back", f"userset {user_id} youtube")
        buttons.data_button("Close", f"userset {user_id} close")

        # Get basic settings
        youtube_privacy = user_dict.get(
            "YOUTUBE_UPLOAD_DEFAULT_PRIVACY", Config.YOUTUBE_UPLOAD_DEFAULT_PRIVACY
        )
        youtube_category = user_dict.get(
            "YOUTUBE_UPLOAD_DEFAULT_CATEGORY", Config.YOUTUBE_UPLOAD_DEFAULT_CATEGORY
        )
        youtube_tags = (
            user_dict.get(
                "YOUTUBE_UPLOAD_DEFAULT_TAGS", Config.YOUTUBE_UPLOAD_DEFAULT_TAGS
            )
            or "None"
        )
        youtube_description = user_dict.get(
            "YOUTUBE_UPLOAD_DEFAULT_DESCRIPTION",
            Config.YOUTUBE_UPLOAD_DEFAULT_DESCRIPTION,
        )
        youtube_title = (
            user_dict.get(
                "YOUTUBE_UPLOAD_DEFAULT_TITLE", Config.YOUTUBE_UPLOAD_DEFAULT_TITLE
            )
            or "Auto (from filename)"
        )
        youtube_language = user_dict.get(
            "YOUTUBE_UPLOAD_DEFAULT_LANGUAGE", Config.YOUTUBE_UPLOAD_DEFAULT_LANGUAGE
        )

        text = f"""<u><b>YouTube Basic Settings for {name}</b></u>
-> Default Privacy: <code>{youtube_privacy}</code>
-> Default Category: <code>{youtube_category}</code>
-> Default Tags: <code>{youtube_tags}</code>
-> Default Description: <code>{youtube_description}</code>
-> Default Title: <code>{youtube_title}</code>
-> Default Language: <code>{youtube_language}</code>

<i>These are the basic settings for YouTube uploads.</i>"""
    elif stype == "youtube_advanced":
        # Advanced YouTube settings
        buttons.data_button(
            "Default License",
            f"userset {user_id} menu YOUTUBE_UPLOAD_DEFAULT_LICENSE",
        )
        buttons.data_button(
            "Embeddable", f"userset {user_id} tog YOUTUBE_UPLOAD_EMBEDDABLE"
        )
        buttons.data_button(
            "Public Stats Viewable",
            f"userset {user_id} tog YOUTUBE_UPLOAD_PUBLIC_STATS_VIEWABLE",
        )
        buttons.data_button(
            "Made for Kids", f"userset {user_id} tog YOUTUBE_UPLOAD_MADE_FOR_KIDS"
        )
        buttons.data_button(
            "Notify Subscribers",
            f"userset {user_id} tog YOUTUBE_UPLOAD_NOTIFY_SUBSCRIBERS",
        )
        buttons.data_button(
            "Location Description",
            f"userset {user_id} menu YOUTUBE_UPLOAD_LOCATION_DESCRIPTION",
        )
        buttons.data_button(
            "Recording Date", f"userset {user_id} menu YOUTUBE_UPLOAD_RECORDING_DATE"
        )
        buttons.data_button(
            "Auto Levels", f"userset {user_id} tog YOUTUBE_UPLOAD_AUTO_LEVELS"
        )
        buttons.data_button(
            "Stabilize", f"userset {user_id} tog YOUTUBE_UPLOAD_STABILIZE"
        )
        buttons.data_button("Back", f"userset {user_id} youtube")
        buttons.data_button("Close", f"userset {user_id} close")

        # Get advanced settings
        youtube_license = user_dict.get(
            "YOUTUBE_UPLOAD_DEFAULT_LICENSE", Config.YOUTUBE_UPLOAD_DEFAULT_LICENSE
        )
        youtube_embeddable = user_dict.get(
            "YOUTUBE_UPLOAD_EMBEDDABLE", Config.YOUTUBE_UPLOAD_EMBEDDABLE
        )
        youtube_public_stats = user_dict.get(
            "YOUTUBE_UPLOAD_PUBLIC_STATS_VIEWABLE",
            Config.YOUTUBE_UPLOAD_PUBLIC_STATS_VIEWABLE,
        )
        youtube_made_for_kids = user_dict.get(
            "YOUTUBE_UPLOAD_MADE_FOR_KIDS", Config.YOUTUBE_UPLOAD_MADE_FOR_KIDS
        )
        youtube_notify_subs = user_dict.get(
            "YOUTUBE_UPLOAD_NOTIFY_SUBSCRIBERS",
            Config.YOUTUBE_UPLOAD_NOTIFY_SUBSCRIBERS,
        )
        youtube_location = (
            user_dict.get(
                "YOUTUBE_UPLOAD_LOCATION_DESCRIPTION",
                Config.YOUTUBE_UPLOAD_LOCATION_DESCRIPTION,
            )
            or "None"
        )
        youtube_recording_date = (
            user_dict.get(
                "YOUTUBE_UPLOAD_RECORDING_DATE", Config.YOUTUBE_UPLOAD_RECORDING_DATE
            )
            or "None"
        )
        youtube_auto_levels = user_dict.get(
            "YOUTUBE_UPLOAD_AUTO_LEVELS", Config.YOUTUBE_UPLOAD_AUTO_LEVELS
        )
        youtube_stabilize = user_dict.get(
            "YOUTUBE_UPLOAD_STABILIZE", Config.YOUTUBE_UPLOAD_STABILIZE
        )

        text = f"""<u><b>YouTube Advanced Settings for {name}</b></u>
-> Default License: <code>{youtube_license}</code>
-> Embeddable: <b>{"✅ Yes" if youtube_embeddable else "❌ No"}</b>
-> Public Stats Viewable: <b>{"✅ Yes" if youtube_public_stats else "❌ No"}</b>
-> Made for Kids: <b>{"✅ Yes" if youtube_made_for_kids else "❌ No"}</b>
-> Notify Subscribers: <b>{"✅ Yes" if youtube_notify_subs else "❌ No"}</b>
-> Location Description: <code>{youtube_location}</code>
-> Recording Date: <code>{youtube_recording_date}</code>
-> Auto Levels: <b>{"✅ Yes" if youtube_auto_levels else "❌ No"}</b>
-> Stabilize: <b>{"✅ Yes" if youtube_stabilize else "❌ No"}</b>

<i>These are advanced settings for YouTube uploads.</i>"""

    elif stype == "ai":
        # Add buttons for each AI setting
        for option in ai_options:
            buttons.data_button(
                option.replace("_", " ").title(),
                f"userset {user_id} menu {option}",
            )

        buttons.data_button("Reset AI Settings", f"userset {user_id} reset ai")
        buttons.data_button("Back", f"userset {user_id} back")
        buttons.data_button("Close", f"userset {user_id} close")

        # Get current AI settings
        default_ai = user_dict.get(
            "DEFAULT_AI_PROVIDER", Config.DEFAULT_AI_PROVIDER
        ).capitalize()
        mistral_api_url = user_dict.get("MISTRAL_API_URL", "Not Set")
        deepseek_api_url = user_dict.get("DEEPSEEK_API_URL", "Not Set")

        text = f"""<u><b>AI Settings for {name}</b></u>
<b>Default AI Provider:</b> <code>{default_ai}</code>

<b>Mistral AI:</b>
-> API URL: <code>{mistral_api_url}</code>

<b>DeepSeek AI:</b>
-> API URL: <code>{deepseek_api_url}</code>

<i>Note: For each AI provider, configure either API Key or API URL. If both are set, API Key will be used first with fallback to API URL.</i>
<i>Your settings will take priority over the bot owner's settings.</i>
<i>Use /ask command to chat with the default AI provider.</i>
"""

    elif stype == "mega":
        # Check if user has their own token/config enabled
        user_tokens = user_dict.get("USER_TOKENS", False)

        # Get MEGA settings with priority: User > Owner
        mega_email = user_dict.get("MEGA_EMAIL", None)
        mega_password = user_dict.get("MEGA_PASSWORD", None)

        # Determine source and values for credentials
        if mega_email is not None:
            email_source = "User"
            email_value = mega_email or "Not configured"
        else:
            email_source = "Owner"
            email_value = Config.MEGA_EMAIL or "Not configured"

        if mega_password is not None:
            password_source = "User"
            password_value = "✅ Set" if mega_password else "❌ Not set"
        else:
            password_source = "Owner"
            password_value = "✅ Set" if Config.MEGA_PASSWORD else "❌ Not set"

        # User credential settings - always available for MEGA
        buttons.data_button("📧 Email", f"userset {user_id} var MEGA_EMAIL")
        buttons.data_button("🔑 Password", f"userset {user_id} var MEGA_PASSWORD")

        # Reset and Remove buttons for MEGA credentials - show if user has set any credentials
        user_has_mega_credentials = (
            mega_email is not None or mega_password is not None
        )
        if user_has_mega_credentials:
            buttons.data_button(
                "🔄 Reset Credentials", f"userset {user_id} reset mega_credentials"
            )

        # Individual remove buttons - show only if that specific credential is set by user
        if mega_email is not None:
            buttons.data_button(
                "🗑️ Remove Email", f"userset {user_id} remove MEGA_EMAIL"
            )
        if mega_password is not None:
            buttons.data_button(
                "🗑️ Remove Password", f"userset {user_id} remove MEGA_PASSWORD"
            )

        # Upload Settings
        buttons.data_button(
            "📤 Upload Folder", f"userset {user_id} menu MEGA_UPLOAD_FOLDER"
        )
        buttons.data_button(
            "⏰ Link Expiry Days", f"userset {user_id} menu MEGA_UPLOAD_EXPIRY_DAYS"
        )
        buttons.data_button(
            "🔐 Upload Password", f"userset {user_id} menu MEGA_UPLOAD_PASSWORD"
        )
        buttons.data_button(
            "🔑 Encryption Key", f"userset {user_id} menu MEGA_UPLOAD_ENCRYPTION_KEY"
        )

        # Toggle buttons for boolean settings
        public_links, public_links_source = get_mega_setting(
            "MEGA_UPLOAD_PUBLIC", False, True
        )
        private_links, private_links_source = get_mega_setting(
            "MEGA_UPLOAD_PRIVATE", False, True
        )
        unlisted_links, unlisted_links_source = get_mega_setting(
            "MEGA_UPLOAD_UNLISTED", False, True
        )
        thumbnails, thumbnails_source = get_mega_setting(
            "MEGA_UPLOAD_THUMBNAIL", False, True
        )
        delete_after, delete_after_source = get_mega_setting(
            "MEGA_UPLOAD_DELETE_AFTER", False, True
        )

        buttons.data_button(
            f"🔗 Public Links: {'✅ ON' if public_links else '❌ OFF'}",
            f"userset {user_id} tog MEGA_UPLOAD_PUBLIC {'f' if public_links else 't'}",
        )
        buttons.data_button(
            f"🔒 Private Links: {'✅ ON' if private_links else '❌ OFF'}",
            f"userset {user_id} tog MEGA_UPLOAD_PRIVATE {'f' if private_links else 't'}",
        )
        buttons.data_button(
            f"🔓 Unlisted Links: {'✅ ON' if unlisted_links else '❌ OFF'}",
            f"userset {user_id} tog MEGA_UPLOAD_UNLISTED {'f' if unlisted_links else 't'}",
        )
        buttons.data_button(
            f"🖼️ Thumbnails: {'✅ ON' if thumbnails else '❌ OFF'}",
            f"userset {user_id} tog MEGA_UPLOAD_THUMBNAIL {'f' if thumbnails else 't'}",
        )
        buttons.data_button(
            f"🗑️ Delete After: {'✅ ON' if delete_after else '❌ OFF'}",
            f"userset {user_id} tog MEGA_UPLOAD_DELETE_AFTER {'f' if delete_after else 't'}",
        )

        # Clone Settings
        buttons.data_button(
            "📁 Clone To Folder", f"userset {user_id} menu MEGA_CLONE_TO_FOLDER"
        )

        preserve_structure, preserve_structure_source = get_mega_setting(
            "MEGA_CLONE_PRESERVE_STRUCTURE", True, True
        )
        overwrite_files, overwrite_files_source = get_mega_setting(
            "MEGA_CLONE_OVERWRITE", False, True
        )

        buttons.data_button(
            f"🏗️ Preserve Structure: {'✅ ON' if preserve_structure else '❌ OFF'}",
            f"userset {user_id} tog MEGA_CLONE_PRESERVE_STRUCTURE {'f' if preserve_structure else 't'}",
        )
        buttons.data_button(
            f"♻️ Overwrite Files: {'✅ ON' if overwrite_files else '❌ OFF'}",
            f"userset {user_id} tog MEGA_CLONE_OVERWRITE {'f' if overwrite_files else 't'}",
        )

        buttons.data_button("Back", f"userset {user_id} back")
        buttons.data_button("Close", f"userset {user_id} close")

        # Upload settings
        upload_folder, upload_folder_source = get_mega_setting(
            "MEGA_UPLOAD_FOLDER", "Root folder"
        )
        public_links, public_links_source = get_mega_setting(
            "MEGA_UPLOAD_PUBLIC", False, True
        )
        private_links, private_links_source = get_mega_setting(
            "MEGA_UPLOAD_PRIVATE", False, True
        )
        unlisted_links, unlisted_links_source = get_mega_setting(
            "MEGA_UPLOAD_UNLISTED", False, True
        )
        expiry_days, expiry_days_source = get_mega_setting(
            "MEGA_UPLOAD_EXPIRY_DAYS", 0
        )
        upload_password, upload_password_source = get_mega_setting(
            "MEGA_UPLOAD_PASSWORD", ""
        )
        encryption_key, encryption_key_source = get_mega_setting(
            "MEGA_UPLOAD_ENCRYPTION_KEY", ""
        )
        thumbnails, thumbnails_source = get_mega_setting(
            "MEGA_UPLOAD_THUMBNAIL", False, True
        )
        delete_after, delete_after_source = get_mega_setting(
            "MEGA_UPLOAD_DELETE_AFTER", False, True
        )

        # Clone settings
        clone_folder, clone_folder_source = get_mega_setting(
            "MEGA_CLONE_TO_FOLDER", "Root folder"
        )
        preserve_structure, preserve_structure_source = get_mega_setting(
            "MEGA_CLONE_PRESERVE_STRUCTURE", True, True
        )
        overwrite_files, overwrite_files_source = get_mega_setting(
            "MEGA_CLONE_OVERWRITE", False, True
        )

        # Format display values
        upload_folder_display = upload_folder or "Root folder"
        expiry_display = f"{expiry_days} days" if expiry_days > 0 else "No expiry"
        password_display = "Set" if upload_password else "Not set"
        encryption_display = "Set" if encryption_key else "Not set"
        clone_folder_display = clone_folder or "Root folder"

        # Hide email for privacy - only show if it's set or not
        email_display = (
            "✅ Set"
            if email_value not in ["Not configured", "Not set"]
            else "❌ Not set"
        )

        text = f"""<u><b>☁️ MEGA Settings for {name}</b></u>

<b>🔐 Credentials:</b>
Email: <code>{email_display}</code> ({email_source})
Password: <code>{password_value}</code> ({password_source})

<b>📤 Upload:</b>
Folder: <code>{upload_folder_display}</code> ({upload_folder_source})
Public: <b>{"✅" if public_links else "❌"}</b> | Private: <b>{"✅" if private_links else "❌"}</b> | Unlisted: <b>{"✅" if unlisted_links else "❌"}</b>
Expiry: <code>{expiry_display}</code> ({expiry_days_source})
Password: <code>{password_display}</code> ({upload_password_source})
Encryption: <code>{encryption_display}</code> ({encryption_key_source})
Thumbnails: <b>{"✅" if thumbnails else "❌"}</b> | Delete After: <b>{"✅" if delete_after else "❌"}</b>

<b>🔄 Clone:</b>
Folder: <code>{clone_folder_display}</code> ({clone_folder_source})
Preserve Structure: <b>{"✅" if preserve_structure else "❌"}</b> | Overwrite: <b>{"✅" if overwrite_files else "❌"}</b>

<i>Your settings override owner settings. Set your own MEGA credentials to use your account.</i>
"""

    elif stype == "convert":
        buttons.data_button("Back", f"userset {user_id} back")
        buttons.data_button("Close", f"userset {user_id} close")

        text = f"""<u><b>Convert Settings for {name}</b></u>
Convert settings have been moved to Media Tools settings.
Please use /mediatools command to configure convert settings.
"""

    elif stype == "metadata":
        # Global metadata settings
        buttons.data_button("Metadata All", f"userset {user_id} menu METADATA_ALL")
        buttons.data_button("Global Title", f"userset {user_id} menu METADATA_TITLE")
        buttons.data_button(
            "Global Author", f"userset {user_id} menu METADATA_AUTHOR"
        )
        buttons.data_button(
            "Global Comment", f"userset {user_id} menu METADATA_COMMENT"
        )

        # Video metadata settings
        buttons.data_button(
            "Video Title", f"userset {user_id} menu METADATA_VIDEO_TITLE"
        )
        buttons.data_button(
            "Video Author", f"userset {user_id} menu METADATA_VIDEO_AUTHOR"
        )
        buttons.data_button(
            "Video Comment", f"userset {user_id} menu METADATA_VIDEO_COMMENT"
        )

        # Audio metadata settings
        buttons.data_button(
            "Audio Title", f"userset {user_id} menu METADATA_AUDIO_TITLE"
        )
        buttons.data_button(
            "Audio Author", f"userset {user_id} menu METADATA_AUDIO_AUTHOR"
        )
        buttons.data_button(
            "Audio Comment", f"userset {user_id} menu METADATA_AUDIO_COMMENT"
        )

        # Subtitle metadata settings
        buttons.data_button(
            "Subtitle Title", f"userset {user_id} menu METADATA_SUBTITLE_TITLE"
        )
        buttons.data_button(
            "Subtitle Author", f"userset {user_id} menu METADATA_SUBTITLE_AUTHOR"
        )
        buttons.data_button(
            "Subtitle Comment", f"userset {user_id} menu METADATA_SUBTITLE_COMMENT"
        )

        buttons.data_button(
            "Reset All Metadata", f"userset {user_id} reset metadata_all"
        )
        buttons.data_button("Back", f"userset {user_id} back")
        buttons.data_button("Close", f"userset {user_id} close")

        # Get metadata values
        metadata_all = user_dict.get("METADATA_ALL", "None")
        metadata_title = user_dict.get("METADATA_TITLE", "None")
        metadata_author = user_dict.get("METADATA_AUTHOR", "None")
        metadata_comment = user_dict.get("METADATA_COMMENT", "None")

        # Get video metadata values
        metadata_video_title = user_dict.get("METADATA_VIDEO_TITLE", "None")
        metadata_video_author = user_dict.get("METADATA_VIDEO_AUTHOR", "None")
        metadata_video_comment = user_dict.get("METADATA_VIDEO_COMMENT", "None")

        # Get audio metadata values
        metadata_audio_title = user_dict.get("METADATA_AUDIO_TITLE", "None")
        metadata_audio_author = user_dict.get("METADATA_AUDIO_AUTHOR", "None")
        metadata_audio_comment = user_dict.get("METADATA_AUDIO_COMMENT", "None")

        # Get subtitle metadata values
        metadata_subtitle_title = user_dict.get("METADATA_SUBTITLE_TITLE", "None")
        metadata_subtitle_author = user_dict.get("METADATA_SUBTITLE_AUTHOR", "None")
        metadata_subtitle_comment = user_dict.get(
            "METADATA_SUBTITLE_COMMENT", "None"
        )

        # Legacy metadata key - not used directly in the display but kept for reference
        # metadata_key = user_dict.get("METADATA_KEY", "None")

        text = f"""<u><b>Metadata Settings for {name}</b></u>
<b>Global Settings:</b>
-> Metadata All: <code>{metadata_all}</code>
-> Global Title: <code>{metadata_title}</code>
-> Global Author: <code>{metadata_author}</code>
-> Global Comment: <code>{metadata_comment}</code>

<b>Video Track Settings:</b>
-> Video Title: <code>{metadata_video_title}</code>
-> Video Author: <code>{metadata_video_author}</code>
-> Video Comment: <code>{metadata_video_comment}</code>

<b>Audio Track Settings:</b>
-> Audio Title: <code>{metadata_audio_title}</code>
-> Audio Author: <code>{metadata_audio_author}</code>
-> Audio Comment: <code>{metadata_audio_comment}</code>

<b>Subtitle Track Settings:</b>
-> Subtitle Title: <code>{metadata_subtitle_title}</code>
-> Subtitle Author: <code>{metadata_subtitle_author}</code>
-> Subtitle Comment: <code>{metadata_subtitle_comment}</code>

<b>Note:</b> 'Metadata All' takes priority over all other settings when set."""

    else:
        # Only show Leech button if Leech operations are enabled
        if Config.LEECH_ENABLED:
            buttons.data_button("Leech", f"userset {user_id} leech")
        # Only show Rclone button if Rclone operations are enabled
        if Config.RCLONE_ENABLED:
            buttons.data_button("Rclone", f"userset {user_id} rclone")
        # Only show Gdrive API button if Mirror operations are enabled
        if Config.MIRROR_ENABLED:
            buttons.data_button("Gdrive API", f"userset {user_id} gdrive")
        # Only show YouTube API button if YouTube upload is enabled
        if Config.YOUTUBE_UPLOAD_ENABLED:
            buttons.data_button("YouTube API", f"userset {user_id} youtube")
        # Only show MEGA Settings button if MEGA is enabled
        if Config.MEGA_ENABLED:
            buttons.data_button("☁️ MEGA", f"userset {user_id} mega")
        # Only show AI Settings button if Extra Modules are enabled
        if Config.ENABLE_EXTRA_MODULES:
            buttons.data_button("AI Settings", f"userset {user_id} ai")

        upload_paths = user_dict.get("UPLOAD_PATHS", {})
        if (
            not upload_paths
            and "UPLOAD_PATHS" not in user_dict
            and Config.UPLOAD_PATHS
        ):
            upload_paths = Config.UPLOAD_PATHS
        else:
            upload_paths = "None"

        buttons.data_button("Upload Paths", f"userset {user_id} menu UPLOAD_PATHS")

        if user_dict.get("DEFAULT_UPLOAD", ""):
            default_upload = user_dict["DEFAULT_UPLOAD"]
        elif "DEFAULT_UPLOAD" not in user_dict:
            default_upload = Config.DEFAULT_UPLOAD

        # If Rclone is disabled or Mirror is disabled and default upload is set to Rclone, change it to Gdrive
        if (
            not Config.RCLONE_ENABLED or not Config.MIRROR_ENABLED
        ) and default_upload not in ["gd", "yt"]:
            default_upload = "gd"
            # Update the user's settings
            update_user_ldata(user_id, "DEFAULT_UPLOAD", "gd")

        # If YouTube upload is disabled and default upload is set to YouTube, change it to Gdrive
        if not Config.YOUTUBE_UPLOAD_ENABLED and default_upload == "yt":
            default_upload = "gd"
            # Update the user's settings
            update_user_ldata(user_id, "DEFAULT_UPLOAD", "gd")

        # If MEGA is disabled and default upload is set to MEGA, change it to Gdrive
        if not Config.MEGA_ENABLED and default_upload == "mg":
            default_upload = "gd"
            # Update the user's settings
            update_user_ldata(user_id, "DEFAULT_UPLOAD", "gd")

        if default_upload == "gd":
            du = "Gdrive API"
        elif default_upload == "yt":
            du = "YouTube"
        elif default_upload == "mg":
            du = "MEGA"
        else:
            du = "Rclone"

        # Show upload toggle buttons based on enabled services
        available_uploads = []
        if Config.MIRROR_ENABLED:
            available_uploads.append(("gd", "Gdrive API"))
        if Config.RCLONE_ENABLED and Config.MIRROR_ENABLED:
            available_uploads.append(("rc", "Rclone"))
        if Config.YOUTUBE_UPLOAD_ENABLED:
            available_uploads.append(("yt", "YouTube"))
        if Config.MEGA_ENABLED:
            available_uploads.append(("mg", "MEGA"))

        # Only show toggle if there are multiple upload options
        if len(available_uploads) > 1:
            # Find next upload option
            current_index = next(
                (
                    i
                    for i, (code, _) in enumerate(available_uploads)
                    if code == default_upload
                ),
                0,
            )
            next_index = (current_index + 1) % len(available_uploads)
            next_code, next_name = available_uploads[next_index]

            buttons.data_button(
                f"Upload using {next_name}",
                f"userset {user_id} {default_upload}",
            )

        user_tokens = user_dict.get("USER_TOKENS", False)
        tr = "MY" if user_tokens else "OWNER"
        trr = "OWNER" if user_tokens else "MY"

        # Only show the token/config toggle if Mirror is enabled
        if Config.MIRROR_ENABLED:
            buttons.data_button(
                f"{trr} Token/Config",
                f"userset {user_id} tog USER_TOKENS {'f' if user_tokens else 't'}",
            )

        buttons.data_button(
            "Excluded Extensions",
            f"userset {user_id} menu EXCLUDED_EXTENSIONS",
        )
        if user_dict.get("EXCLUDED_EXTENSIONS", False):
            ex_ex = user_dict["EXCLUDED_EXTENSIONS"]
        elif "EXCLUDED_EXTENSIONS" not in user_dict:
            ex_ex = excluded_extensions
        else:
            ex_ex = "None"

        ns_msg = "Added" if user_dict.get("NAME_SUBSTITUTE", False) else "None"
        buttons.data_button(
            "Name Subtitute",
            f"userset {user_id} menu NAME_SUBSTITUTE",
        )

        # Only show YT-DLP Options button if YT-DLP operations are enabled
        if Config.YTDLP_ENABLED:
            buttons.data_button(
                "YT-DLP Options",
                f"userset {user_id} menu YT_DLP_OPTIONS",
            )
        if user_dict.get("YT_DLP_OPTIONS", False):
            ytopt = "Added by User"
        elif "YT_DLP_OPTIONS" not in user_dict and Config.YT_DLP_OPTIONS:
            ytopt = "Added by Owner"
        else:
            ytopt = "None"

        # Only show User Cookies button if YT-DLP operations are enabled
        if Config.YTDLP_ENABLED:
            buttons.data_button(
                "User Cookies",
                f"userset {user_id} menu USER_COOKIES",
            )
        cookies_path = f"cookies/{user_id}.txt"
        cookies_status = "Added" if await aiopath.exists(cookies_path) else "None"

        # Only show Metadata button if metadata tool is enabled

        # Force refresh Config.MEDIA_TOOLS_ENABLED from database to ensure accurate status
        try:
            # Check if database is connected and db attribute exists
            if (
                database.db is not None
                and hasattr(database, "db")
                and hasattr(database.db, "settings")
            ):
                db_config = await database.db.settings.config.find_one(
                    {"_id": TgClient.ID},
                    {"MEDIA_TOOLS_ENABLED": 1, "_id": 0},
                )
                if db_config and "MEDIA_TOOLS_ENABLED" in db_config:
                    # Update Config with the latest value from database
                    Config.MEDIA_TOOLS_ENABLED = db_config["MEDIA_TOOLS_ENABLED"]
        except Exception:
            pass

        if is_media_tool_enabled("metadata"):
            buttons.data_button("Metadata", f"userset {user_id} metadata")

        # Only show FFmpeg Cmds button if ffmpeg tool is enabled
        if is_media_tool_enabled("xtra"):
            buttons.data_button("FFmpeg Cmds", f"userset {user_id} menu FFMPEG_CMDS")
            if user_dict.get("FFMPEG_CMDS", False):
                ffc = "Added by User"
            elif "FFMPEG_CMDS" not in user_dict and Config.FFMPEG_CMDS:
                ffc = "Added by Owner"
            else:
                ffc = "None"
        else:
            ffc = "Disabled"

        # Add MediaInfo toggle
        mediainfo_enabled = user_dict.get("MEDIAINFO_ENABLED", None)
        if mediainfo_enabled is None:
            mediainfo_enabled = Config.MEDIAINFO_ENABLED
            mediainfo_source = "Owner"
        else:
            mediainfo_source = "User"

        buttons.data_button(
            f"MediaInfo: {'✅ ON' if mediainfo_enabled else '❌ OFF'}",
            f"userset {user_id} tog MEDIAINFO_ENABLED {'f' if mediainfo_enabled else 't'}",
        )

        # Watermark moved to Media Tools

        # Get metadata value for display - prioritize METADATA_ALL over METADATA_KEY
        if user_dict.get("METADATA_ALL", False):
            mdt = user_dict["METADATA_ALL"]
            mdt_source = "Metadata All"
        elif user_dict.get("METADATA_KEY", False):
            mdt = user_dict["METADATA_KEY"]
            mdt_source = "Legacy Metadata"
        elif "METADATA_ALL" not in user_dict and Config.METADATA_ALL:
            mdt = Config.METADATA_ALL
            mdt_source = "Owner's Metadata All"
        elif "METADATA_KEY" not in user_dict and Config.METADATA_KEY:
            mdt = Config.METADATA_KEY
            mdt_source = "Owner's Legacy Metadata"
        else:
            mdt = "None"
            mdt_source = ""
        if user_dict:
            buttons.data_button("Reset All", f"userset {user_id} reset all")

        buttons.data_button("Close", f"userset {user_id} close")

        # Get MediaInfo status for display
        mediainfo_enabled = user_dict.get("MEDIAINFO_ENABLED", None)
        if mediainfo_enabled is None:
            mediainfo_enabled = Config.MEDIAINFO_ENABLED
            mediainfo_source = "Owner"
        else:
            mediainfo_source = "User"
        mediainfo_status = f"{'Enabled' if mediainfo_enabled else 'Disabled'} (Set by {mediainfo_source})"

        # Adjust display text based on mirror and leech status
        if Config.MIRROR_ENABLED and Config.LEECH_ENABLED:
            text = f"""<u><b>Settings for {name}</B></u>
-> Default Package: <b>{du}</b>
-> Upload Paths: <code><b>{upload_paths}</b></code>
-> Using <b>{tr}</b> Token/Config
-> Name Substitution: <code>{ns_msg}</code>
-> Excluded Extensions: <code>{ex_ex}</code>
-> YT-DLP Options: <code>{ytopt}</code>
-> User Cookies: <b>{cookies_status}</b>
-> FFMPEG Commands: <code>{ffc}</code>
-> MediaInfo: <b>{mediainfo_status}</b>
-> Metadata Text: <code>{mdt}</code>{f" ({mdt_source})" if mdt != "None" and mdt_source else ""}"""
        elif not Config.MIRROR_ENABLED and Config.LEECH_ENABLED:
            text = f"""<u><b>Settings for {name}</B></u>
-> Upload Paths: <code><b>{upload_paths}</b></code>
-> Mirror operations are disabled by admin
-> Name Substitution: <code>{ns_msg}</code>
-> Excluded Extensions: <code>{ex_ex}</code>
-> YT-DLP Options: <code>{ytopt}</code>
-> User Cookies: <b>{cookies_status}</b>
-> FFMPEG Commands: <code>{ffc}</code>
-> MediaInfo: <b>{mediainfo_status}</b>
-> Metadata Text: <code>{mdt}</code>{f" ({mdt_source})" if mdt != "None" and mdt_source else ""}"""
        elif Config.MIRROR_ENABLED and not Config.LEECH_ENABLED:
            text = f"""<u><b>Settings for {name}</B></u>
-> Default Package: <b>{du}</b>
-> Upload Paths: <code><b>{upload_paths}</b></code>
-> Using <b>{tr}</b> Token/Config
-> Leech operations are disabled by admin
-> Name Substitution: <code>{ns_msg}</code>
-> Excluded Extensions: <code>{ex_ex}</code>
-> YT-DLP Options: <code>{ytopt}</code>
-> User Cookies: <b>{cookies_status}</b>
-> FFMPEG Commands: <code>{ffc}</code>
-> MediaInfo: <b>{mediainfo_status}</b>
-> Metadata Text: <code>{mdt}</code>{f" ({mdt_source})" if mdt != "None" and mdt_source else ""}"""
        else:
            text = f"""<u><b>Settings for {name}</B></u>
-> Upload Paths: <code><b>{upload_paths}</b></code>
-> Mirror operations are disabled by admin
-> Leech operations are disabled by admin
-> Name Substitution: <code>{ns_msg}</code>
-> Excluded Extensions: <code>{ex_ex}</code>
-> YT-DLP Options: <code>{ytopt}</code>
-> User Cookies: <b>{cookies_status}</b>
-> FFMPEG Commands: <code>{ffc}</code>
-> MediaInfo: <b>{mediainfo_status}</b>
-> Metadata Text: <code>{mdt}</code>{f" ({mdt_source})" if mdt != "None" and mdt_source else ""}"""

    return text, buttons.build_menu(2), thumbnail


async def update_user_settings(query, stype="main"):
    handler_dict[query.from_user.id] = False
    msg, button, t = await get_user_settings(query.from_user, stype)
    await edit_message(query.message, msg, button, t)


@new_task
async def send_user_settings(_, message):
    from_user = message.from_user
    handler_dict[from_user.id] = False
    msg, button, t = await get_user_settings(from_user)
    await delete_message(message)  # Delete the command message instantly
    settings_msg = await send_message(message, msg, button, t)
    # Auto delete settings after 5 minutes
    create_task(auto_delete_message(settings_msg, time=300))  # noqa: RUF006


@new_task
async def add_file(_, message, ftype):
    user_id = message.from_user.id
    handler_dict[user_id] = False

    # Get file size for logging purposes (no limits enforced)
    if hasattr(message, "document") and message.document:
        file_size = message.document.file_size
    elif hasattr(message, "photo") and message.photo:
        file_size = message.photo.file_size
    else:
        file_size = 0

    if file_size > 0:
        LOGGER.info(
            f"Processing {ftype} file of size: {get_readable_file_size(file_size)} for user {user_id}"
        )

    try:
        if ftype == "THUMBNAIL":
            des_dir = await create_thumb(message, user_id)
        elif ftype == "RCLONE_CONFIG":
            rpath = f"{getcwd()}/rclone/"
            await makedirs(rpath, exist_ok=True)
            des_dir = f"{rpath}{user_id}.conf"
            await message.download(file_name=des_dir)
        elif ftype == "TOKEN_PICKLE":
            tpath = f"{getcwd()}/tokens/"
            await makedirs(tpath, exist_ok=True)
            des_dir = f"{tpath}{user_id}.pickle"
            await message.download(file_name=des_dir)  # TODO user font
        elif ftype == "YOUTUBE_TOKEN_PICKLE":
            tpath = f"{getcwd()}/tokens/"
            await makedirs(tpath, exist_ok=True)
            des_dir = f"{tpath}{user_id}_youtube.pickle"
            await message.download(file_name=des_dir)
        elif ftype == "USER_COOKIES":
            cpath = f"{getcwd()}/cookies/"
            await makedirs(cpath, exist_ok=True)
            des_dir = f"{cpath}{user_id}.txt"
            await message.download(file_name=des_dir)
    except Exception as e:
        error_msg = await send_message(message, f"❌ Error downloading file: {e!s}")
        create_task(
            auto_delete_message(error_msg, time=300)
        )  # Auto-delete after 5 minutes
        await delete_message(message)
        return

    # Handle special processing for USER_COOKIES
    if ftype == "USER_COOKIES":
        try:
            # Set secure permissions for the cookies file
            await (await create_subprocess_exec("chmod", "600", des_dir)).wait()
            LOGGER.info(
                f"Set secure permissions for cookies file of user ID: {user_id}"
            )

            # Check if the cookies file contains YouTube authentication cookies
            has_youtube_auth = False
            try:
                from http.cookiejar import MozillaCookieJar

                cookie_jar = MozillaCookieJar()
                cookie_jar.load(des_dir)

                # Check for YouTube authentication cookies
                yt_cookies = [
                    c for c in cookie_jar if c.domain.endswith("youtube.com")
                ]
                auth_cookies = [
                    c
                    for c in yt_cookies
                    if c.name
                    in ("SID", "HSID", "SSID", "APISID", "SAPISID", "LOGIN_INFO")
                ]

                if auth_cookies:
                    has_youtube_auth = True
                    LOGGER.info(
                        f"YouTube authentication cookies found for user ID: {user_id}"
                    )
            except Exception as e:
                LOGGER.error(f"Error checking cookies file: {e}")
                error_msg = await send_message(
                    message.chat.id,
                    f"⚠️ Warning: Error checking cookies file: {e}. Your cookies will still be used, but may not work correctly.",
                )
                create_task(
                    auto_delete_message(error_msg, time=300)
                )  # Auto-delete after 5 minutes

            if has_youtube_auth:
                success_msg = await send_message(
                    message.chat.id,
                    "✅ Cookies file uploaded successfully! YouTube authentication cookies detected. Your cookies will be used for YouTube and other yt-dlp downloads.",
                )
            else:
                success_msg = await send_message(
                    message.chat.id,
                    "✅ Cookies file uploaded successfully! Your cookies will be used for YouTube and other yt-dlp downloads. Note: No YouTube authentication cookies detected, which might limit access to restricted content.",
                )
            create_task(
                auto_delete_message(success_msg, time=60)
            )  # Auto-delete after 1 minute
        except Exception as e:
            LOGGER.error(f"Error processing cookies file: {e}")
            error_msg = await send_message(
                message, f"❌ Error processing cookies file: {e!s}"
            )
            create_task(auto_delete_message(error_msg, time=300))
            await delete_message(message)
            return

    # Update user data and database
    try:
        update_user_ldata(user_id, ftype, des_dir)
        await delete_message(message)

        # Show processing message for large files
        if file_size > 50 * 1024 * 1024:  # 50MB
            processing_msg = await send_message(
                message,
                f"🔄 Processing large {ftype.replace('_', ' ').lower()} file ({get_readable_file_size(file_size)}). This may take a moment...",
            )
        else:
            processing_msg = None

        await database.update_user_doc(user_id, ftype, des_dir)

        # Delete processing message if it was shown
        if processing_msg:
            await delete_message(processing_msg)

    except MemoryError as e:
        LOGGER.error(
            f"Memory error updating database for user {user_id}, ftype {ftype}: {e}"
        )
        error_msg = await send_message(
            message,
            f"❌ Memory Error: The {ftype.replace('_', ' ').lower()} file is too large for the current system memory. "
            f"Please try uploading a smaller file or contact the bot administrator.",
        )
        create_task(auto_delete_message(error_msg, time=300))
        # Clean up the file if database update fails
        if await aiopath.exists(des_dir):
            await remove(des_dir)
    except Exception as e:
        LOGGER.error(
            f"Error updating database for user {user_id}, ftype {ftype}: {e}"
        )
        error_msg = await send_message(
            message,
            f"❌ Error saving file to database: {e!s}. The file was uploaded but may not be saved properly.",
        )
        create_task(auto_delete_message(error_msg, time=300))
        # Clean up the file if database update fails
        if await aiopath.exists(des_dir):
            await remove(des_dir)


@new_task
async def add_one(_, message, option):
    user_id = message.from_user.id
    handler_dict[user_id] = False
    user_dict = user_data.get(user_id, {})
    value = message.text
    if value.startswith("{") and value.endswith("}"):
        try:
            value = eval(value)
            if user_dict[option]:
                user_dict[option].update(value)
            else:
                update_user_ldata(user_id, option, value)
        except Exception as e:
            error_msg = await send_message(message, str(e))
            create_task(
                auto_delete_message(error_msg, time=300)
            )  # Auto-delete after 5 minutes
            return
    else:
        error_msg = await send_message(message, "It must be dict!")
        create_task(
            auto_delete_message(error_msg, time=300)
        )  # Auto-delete after 5 minutes
        return
    await delete_message(message)
    await database.update_user_data(user_id)


@new_task
async def remove_one(_, message, option):
    user_id = message.from_user.id
    handler_dict[user_id] = False
    user_dict = user_data.get(user_id, {})
    names = message.text.split("/")
    for name in names:
        if name in user_dict[option]:
            del user_dict[option][name]
    await delete_message(message)
    await database.update_user_data(user_id)


@new_task
async def set_option(_, message, option):
    user_id = message.from_user.id
    handler_dict[user_id] = False
    value = message.text
    if option == "LEECH_SPLIT_SIZE":
        try:
            # Try to convert the value to an integer
            value = int(value) if value.isdigit() else get_size_bytes(value)

            # Always use owner's session for max split size calculation, not user's own session
            max_split_size = (
                TgClient.MAX_SPLIT_SIZE
                if hasattr(Config, "USER_SESSION_STRING")
                and Config.USER_SESSION_STRING
                else 2097152000
            )

            # Ensure split size never exceeds Telegram's limit (based on premium status)
            # Add a safety margin to ensure we never exceed Telegram's limit
            safety_margin = 50 * 1024 * 1024  # 50 MiB

            # For non-premium accounts, use a more conservative limit
            if not TgClient.IS_PREMIUM_USER:
                # Use 2000 MiB (slightly less than 2 GiB) for non-premium accounts
                telegram_limit = 2000 * 1024 * 1024
            else:
                # Use 4000 MiB (slightly less than 4 GiB) for premium accounts
                telegram_limit = 4000 * 1024 * 1024

            safe_telegram_limit = telegram_limit - safety_margin

            # Ensure the value doesn't exceed the safe telegram limit
            value = min(value, safe_telegram_limit)

            # Also ensure it doesn't exceed the maximum allowed split size
            value = min(int(value), max_split_size)
        except (ValueError, TypeError):
            # If conversion fails, set to default max split size
            max_split_size = (
                TgClient.MAX_SPLIT_SIZE
                if hasattr(Config, "USER_SESSION_STRING")
                and Config.USER_SESSION_STRING
                else 2097152000
            )
            value = max_split_size
    elif option == "EXCLUDED_EXTENSIONS":
        fx = value.split()
        value = ["aria2", "!qB"]
        for x in fx:
            x = x.lstrip(".")
            value.append(x.strip().lower())
    elif option == "LEECH_FILENAME_CAPTION":
        # Check if caption exceeds Telegram's limit (1024 characters)
        if len(value) > 1024:
            error_msg = await send_message(
                message,
                "❌ Error: Caption exceeds Telegram's limit of 1024 characters. Please use a shorter caption.",
            )
            # Auto-delete error message after 5 minutes
            create_task(auto_delete_message(error_msg, time=300))  # noqa: RUF006
            return
    elif option in ["UPLOAD_PATHS", "FFMPEG_CMDS", "YT_DLP_OPTIONS"]:
        if value.startswith("{") and value.endswith("}"):
            try:
                value = eval(value)
            except Exception as e:
                error_msg = await send_message(message, str(e))
                create_task(
                    auto_delete_message(error_msg, time=300)
                )  # Auto-delete after 5 minutes
                return
        else:
            error_msg = await send_message(message, "It must be dict!")
            create_task(
                auto_delete_message(error_msg, time=300)
            )  # Auto-delete after 5 minutes
            return
    update_user_ldata(user_id, option, value)
    await delete_message(message)
    await database.update_user_data(user_id)


async def get_menu(option, message, user_id):
    handler_dict[user_id] = False
    user_dict = user_data.get(user_id, {})
    buttons = ButtonMaker()
    if option in [
        "THUMBNAIL",
        "RCLONE_CONFIG",
        "TOKEN_PICKLE",
        "YOUTUBE_TOKEN_PICKLE",
        "USER_COOKIES",
    ]:
        key = "file"
    else:
        key = "set"
    buttons.data_button("Set", f"userset {user_id} {key} {option}")
    if option in user_dict and key != "file":
        buttons.data_button("Reset", f"userset {user_id} reset {option}")
    buttons.data_button("Remove", f"userset {user_id} remove {option}")
    if option == "FFMPEG_CMDS":
        ffc = None
        if user_dict.get("FFMPEG_CMDS", False):
            ffc = user_dict["FFMPEG_CMDS"]
            buttons.data_button("Add one", f"userset {user_id} addone {option}")
            buttons.data_button("Remove one", f"userset {user_id} rmone {option}")
        elif "FFMPEG_CMDS" not in user_dict and Config.FFMPEG_CMDS:
            ffc = Config.FFMPEG_CMDS
        if ffc:
            buttons.data_button("Variables", f"userset {user_id} ffvar")
            buttons.data_button("View", f"userset {user_id} view {option}")
    elif user_dict.get(option):
        if option == "THUMBNAIL":
            buttons.data_button("View", f"userset {user_id} view {option}")
        elif option in ["YT_DLP_OPTIONS", "UPLOAD_PATHS"]:
            buttons.data_button("Add one", f"userset {user_id} addone {option}")
            buttons.data_button("Remove one", f"userset {user_id} rmone {option}")
    if option == "USER_COOKIES":
        buttons.data_button("Help", f"userset {user_id} help {option}")
    # Check if option is in leech_options and if leech is enabled
    if option in leech_options:
        # If leech is disabled, go back to main menu
        back_to = "leech" if Config.LEECH_ENABLED else "back"
    elif option in rclone_options:
        # If mirror is disabled, go back to main menu
        back_to = "rclone" if Config.MIRROR_ENABLED else "back"
    elif option in gdrive_options:
        # If mirror is disabled, go back to main menu
        back_to = "gdrive" if Config.MIRROR_ENABLED else "back"
    elif option in youtube_options:
        # If YouTube upload is disabled, go back to main menu
        back_to = "youtube" if Config.YOUTUBE_UPLOAD_ENABLED else "back"
    elif option in mega_options:
        # If MEGA is disabled, go back to main menu
        back_to = "mega" if Config.MEGA_ENABLED else "back"
    elif option in metadata_options:
        back_to = "metadata"
    # Convert options have been moved to Media Tools settings
    elif option in ai_options:
        back_to = "ai"
    elif option in yt_dlp_options:
        back_to = "back"  # Go back to main menu
    else:
        back_to = "back"
    buttons.data_button("Back", f"userset {user_id} {back_to}")
    buttons.data_button("Close", f"userset {user_id} close")
    text = (
        f"Edit menu for: {option}\n\nUse /help1, /help2, /help3... for more details."
    )
    await edit_message(message, text, buttons.build_menu(2))


async def set_ffmpeg_variable(_, message, key, value, index):
    user_id = message.from_user.id
    handler_dict[user_id] = False
    txt = message.text
    user_dict = user_data.setdefault(user_id, {})
    ffvar_data = user_dict.setdefault("FFMPEG_VARIABLES", {})
    ffvar_data = ffvar_data.setdefault(key, {})
    ffvar_data = ffvar_data.setdefault(index, {})
    ffvar_data[value] = txt
    await delete_message(message)
    await database.update_user_data(user_id)


async def ffmpeg_variables(
    client, query, message, user_id, key=None, value=None, index=None
):
    user_dict = user_data.get(user_id, {})
    ffc = None
    if user_dict.get("FFMPEG_CMDS", False):
        ffc = user_dict["FFMPEG_CMDS"]
    elif "FFMPEG_CMDS" not in user_dict and Config.FFMPEG_CMDS:
        ffc = Config.FFMPEG_CMDS
    if ffc:
        buttons = ButtonMaker()
        if key is None:
            msg = "Choose which key you want to fill/edit varibales in it:"
            for k, v in list(ffc.items()):
                add = False
                for i in v:
                    if variables := findall(r"\{(.*?)\}", i):
                        add = True
                if add:
                    buttons.data_button(k, f"userset {user_id} ffvar {k}")
            buttons.data_button("Back", f"userset {user_id} menu FFMPEG_CMDS")
            buttons.data_button("Close", f"userset {user_id} close")
        elif key in ffc and value is None:
            msg = f"Choose which variable you want to fill/edit: <u>{key}</u>\n\nCMDS:\n{ffc[key]}"
            for ind, vl in enumerate(ffc[key]):
                if variables := set(findall(r"\{(.*?)\}", vl)):
                    for var in variables:
                        buttons.data_button(
                            var, f"userset {user_id} ffvar {key} {var} {ind}"
                        )
            buttons.data_button(
                "Reset", f"userset {user_id} ffvar {key} ffmpegvarreset"
            )
            buttons.data_button("Back", f"userset {user_id} ffvar")
            buttons.data_button("Close", f"userset {user_id} close")
        elif key in ffc and value:
            old_value = (
                user_dict.get("FFMPEG_VARIABLES", {})
                .get(key, {})
                .get(index, {})
                .get(value, "")
            )
            msg = f"Edit/Fill this FFmpeg Variable: <u>{key}</u>\n\nItem: {ffc[key][int(index)]}\n\nVariable: {value}"
            if old_value:
                msg += f"\n\nCurrent Value: {old_value}"
            buttons.data_button("Back", f"userset {user_id} setevent")
            buttons.data_button("Close", f"userset {user_id} close")
        else:
            return
        await edit_message(message, msg, buttons.build_menu(2))
        if key in ffc and value:
            pfunc = partial(set_ffmpeg_variable, key=key, value=value, index=index)
            await event_handler(client, query, pfunc)
            await ffmpeg_variables(client, query, message, user_id, key)


async def event_handler(client, query, pfunc, photo=False, document=False):
    user_id = query.from_user.id
    handler_dict[user_id] = True
    start_time = time()

    async def event_filter(_, __, event):
        if photo:
            mtype = event.photo
        elif document:
            mtype = event.document
        else:
            mtype = event.text
        user = event.from_user or event.sender_chat

        # Check if user is None before accessing id
        if user is None:
            return False

        return bool(
            user.id == user_id and event.chat.id == query.message.chat.id and mtype,
        )

    handler = client.add_handler(
        MessageHandler(pfunc, filters=create(event_filter)),
        group=-1,
    )

    while handler_dict[user_id]:
        await sleep(0.5)
        if time() - start_time > 60:
            handler_dict[user_id] = False
    client.remove_handler(*handler)


@new_task
async def edit_user_settings(client, query):
    from_user = query.from_user
    user_id = from_user.id
    name = from_user.mention
    message = query.message
    data = query.data.split()
    handler_dict[user_id] = False
    thumb_path = f"thumbnails/{user_id}.jpg"
    rclone_conf = f"rclone/{user_id}.conf"
    token_pickle = f"tokens/{user_id}.pickle"
    user_dict = user_data.get(user_id, {})
    if user_id != int(data[1]):
        await query.answer("Not Yours!", show_alert=True)
        return
    if data[2] == "setevent":
        await query.answer()
    elif data[2] in [
        "leech",
        "gdrive",
        "rclone",
        "youtube",
        "mega",
        "metadata",
        "convert",
        "ai",
        "youtube_basic",
        "youtube_advanced",
    ]:
        await query.answer()
        # Redirect to main menu if trying to access disabled features
        if (
            (data[2] == "leech" and not Config.LEECH_ENABLED)
            or (data[2] in ["gdrive", "rclone"] and not Config.MIRROR_ENABLED)
            or (data[2] == "mega" and not Config.MEGA_ENABLED)
            or (
                data[2] in ["youtube", "youtube_basic", "youtube_advanced"]
                and not Config.YOUTUBE_UPLOAD_ENABLED
            )
        ):
            await update_user_settings(query, "main")
        else:
            await update_user_settings(query, data[2])
    elif data[2] == "menu":
        await query.answer()
        await get_menu(data[3], message, user_id)
    elif data[2] == "tog":
        await query.answer()
        update_user_ldata(user_id, data[3], data[4] == "t")
        if data[3] == "STOP_DUPLICATE":
            back_to = "gdrive"
        elif data[3] == "USER_TOKENS" or data[3] == "MEDIAINFO_ENABLED":
            back_to = "main"
        elif data[3] in [
            "MEGA_UPLOAD_PUBLIC",
            "MEGA_UPLOAD_PRIVATE",
            "MEGA_UPLOAD_UNLISTED",
            "MEGA_UPLOAD_THUMBNAIL",
            "MEGA_UPLOAD_DELETE_AFTER",
            "MEGA_CLONE_PRESERVE_STRUCTURE",
            "MEGA_CLONE_OVERWRITE",
        ]:
            back_to = "mega"
        elif data[3] in [
            "YOUTUBE_UPLOAD_EMBEDDABLE",
            "YOUTUBE_UPLOAD_PUBLIC_STATS_VIEWABLE",
            "YOUTUBE_UPLOAD_MADE_FOR_KIDS",
            "YOUTUBE_UPLOAD_NOTIFY_SUBSCRIBERS",
            "YOUTUBE_UPLOAD_AUTO_LEVELS",
            "YOUTUBE_UPLOAD_STABILIZE",
        ]:
            back_to = "youtube_advanced"
        # Convert settings have been moved to Media Tools settings
        else:
            back_to = "leech"
        await update_user_settings(query, stype=back_to)
        await database.update_user_data(user_id)
    elif data[2] == "help":
        await query.answer()
        buttons = ButtonMaker()
        if data[3] == "USER_COOKIES":
            text = """<b>User Cookies Help</b>

You can provide your own cookies for YouTube and other yt-dlp downloads to access restricted content.

<b>How to create a cookies.txt file:</b>
1. Install a browser extension like 'Get cookies.txt' or 'EditThisCookie'
2. Log in to the website (YouTube, etc.) where you want to use your cookies
3. Use the extension to export cookies as a cookies.txt file
4. Upload that file here

<b>Benefits:</b>
- Access age-restricted content
- Fix 'Sign in to confirm you're not a bot' errors
- Access subscriber-only content
- Download private videos (if you have access)

<b>Note:</b> Your cookies are stored securely and only used for your downloads. The bot owner cannot access your account."""
        buttons.data_button("Back", f"userset {user_id} menu {data[3]}")
        buttons.data_button("Close", f"userset {user_id} close")
        await edit_message(message, text, buttons.build_menu(2))
    elif data[2] == "file":
        await query.answer()
        buttons = ButtonMaker()
        if data[3] == "THUMBNAIL":
            text = "Send a photo to save it as custom thumbnail. Timeout: 60 sec"
        elif data[3] == "RCLONE_CONFIG":
            text = "Send rclone.conf. Timeout: 60 sec"
        elif data[3] == "USER_COOKIES":
            text = "Send your cookies.txt file for YouTube and other yt-dlp downloads. Create it using browser extensions like 'Get cookies.txt' or 'EditThisCookie'. Timeout: 60 sec"
        else:
            text = "Send token.pickle. Timeout: 60 sec"
        buttons.data_button("Back", f"userset {user_id} setevent")
        buttons.data_button("Close", f"userset {user_id} close")
        await edit_message(message, text, buttons.build_menu(1))
        pfunc = partial(add_file, ftype=data[3])
        await event_handler(
            client,
            query,
            pfunc,
            photo=data[3] == "THUMBNAIL",
            document=data[3] != "THUMBNAIL",
        )
        await get_menu(data[3], message, user_id)
    elif data[2] == "setprovider":
        await query.answer(f"Setting default AI provider to {data[3].capitalize()}")
        # Update the default AI provider in user settings
        user_dict["DEFAULT_AI_PROVIDER"] = data[3]
        # Update the database
        await database.update_user_data(user_id)
        # Update the UI
        await update_user_settings(query, "ai")
    elif data[2] == "var":
        await query.answer()
        buttons = ButtonMaker()
        if data[3] in user_settings_text:
            text = user_settings_text[data[3]]
            func = set_option

            # Determine the correct back destination based on the option
            if data[3] in mega_options:
                back_to = "mega" if Config.MEGA_ENABLED else "back"
            elif data[3] in youtube_options:
                back_to = "youtube" if Config.YOUTUBE_UPLOAD_ENABLED else "back"
            elif data[3] in leech_options:
                back_to = "leech" if Config.LEECH_ENABLED else "back"
            elif data[3] in gdrive_options:
                back_to = "gdrive" if Config.MIRROR_ENABLED else "back"
            elif data[3] in rclone_options:
                back_to = "rclone" if Config.MIRROR_ENABLED else "back"
            elif data[3] in metadata_options:
                back_to = "metadata"
            elif data[3] in ai_options:
                back_to = "ai"
            else:
                back_to = "back"

            buttons.data_button("Back", f"userset {user_id} {back_to}")
            buttons.data_button("Close", f"userset {user_id} close")
            edit_msg = await edit_message(message, text, buttons.build_menu(1))
            create_task(  # noqa: RUF006
                auto_delete_message(edit_msg, time=300),
            )  # Auto delete edit stage after 5 minutes
            pfunc = partial(func, option=data[3])
            await event_handler(client, query, pfunc)
            await update_user_settings(query, back_to)
        else:
            await update_user_settings(query, "back")
    elif data[2] in ["set", "addone", "rmone"]:
        # Special handling for DEFAULT_AI_PROVIDER
        if data[2] == "set" and data[3] == "DEFAULT_AI_PROVIDER":
            await query.answer()
            buttons = ButtonMaker()
            buttons.data_button("Mistral", f"userset {user_id} setprovider mistral")
            buttons.data_button(
                "DeepSeek", f"userset {user_id} setprovider deepseek"
            )
            buttons.data_button("Back", f"userset {user_id} setevent")
            buttons.data_button("Close", f"userset {user_id} close")

            edit_msg = await edit_message(
                message,
                "<b>Select Default AI Provider</b>\n\nChoose which AI provider to use with the /ask command:",
                buttons.build_menu(2),
            )
            create_task(  # noqa: RUF006
                auto_delete_message(edit_msg, time=300),
            )  # Auto delete edit stage after 5 minutes
            return

        # Normal handling for other settings
        await query.answer()
        buttons = ButtonMaker()
        if data[2] == "set":
            text = user_settings_text[data[3]]
            func = set_option
        elif data[2] == "addone":
            text = f"Add one or more string key and value to {data[3]}. Example: {{'key 1': 62625261, 'key 2': 'value 2'}}. Timeout: 60 sec"
            func = add_one
        elif data[2] == "rmone":
            text = f"Remove one or more key from {data[3]}. Example: key 1/key2/key 3. Timeout: 60 sec"
            func = remove_one
        buttons.data_button("Back", f"userset {user_id} setevent")
        buttons.data_button("Close", f"userset {user_id} close")
        edit_msg = await edit_message(message, text, buttons.build_menu(1))
        create_task(  # noqa: RUF006
            auto_delete_message(edit_msg, time=300),
        )  # Auto delete edit stage after 5 minutes
        pfunc = partial(func, option=data[3])
        await event_handler(client, query, pfunc)
        await get_menu(data[3], message, user_id)
    elif data[2] == "remove":
        await query.answer("Removed!", show_alert=True)
        if data[3] in [
            "THUMBNAIL",
            "RCLONE_CONFIG",
            "TOKEN_PICKLE",
            "YOUTUBE_TOKEN_PICKLE",
            "USER_COOKIES",
        ]:
            if data[3] == "THUMBNAIL":
                fpath = thumb_path
            elif data[3] == "RCLONE_CONFIG":
                fpath = rclone_conf
            elif data[3] == "USER_COOKIES":
                fpath = f"cookies/{user_id}.txt"
            elif data[3] == "YOUTUBE_TOKEN_PICKLE":
                fpath = f"tokens/{user_id}_youtube.pickle"
            else:
                fpath = token_pickle
            if await aiopath.exists(fpath):
                await remove(fpath)
            user_dict.pop(data[3], None)
            await database.update_user_doc(user_id, data[3])
        else:
            update_user_ldata(user_id, data[3], "")
            await database.update_user_data(user_id)
    elif data[2] == "reset":
        await query.answer("Reseted!", show_alert=True)
        if data[3] == "ai":
            # Reset all AI settings
            for key in ai_options:
                if key in user_dict:
                    user_dict.pop(key, None)
            await update_user_settings(query, "ai")
        elif data[3] == "metadata_all":
            # Reset all metadata settings
            for key in metadata_options:
                if key in user_dict:
                    user_dict.pop(key, None)
            await update_user_settings(query, "metadata")
        elif data[3] == "mega_credentials":
            # Reset MEGA credentials
            mega_keys = ["MEGA_EMAIL", "MEGA_PASSWORD"]
            for key in mega_keys:
                if key in user_dict:
                    user_dict.pop(key, None)
            await update_user_settings(query, "mega")

        # Convert settings have been moved to Media Tools settings
        elif data[3] == "MEDIAINFO_ENABLED":
            # Reset MediaInfo setting
            if "MEDIAINFO_ENABLED" in user_dict:
                user_dict.pop("MEDIAINFO_ENABLED", None)
            await update_user_settings(query, "main")
        elif data[3] in user_dict:
            user_dict.pop(data[3], None)
        else:
            for k in list(user_dict.keys()):
                if k not in [
                    "SUDO",
                    "AUTH",
                    "THUMBNAIL",
                    "RCLONE_CONFIG",
                    "TOKEN_PICKLE",
                ]:
                    del user_dict[k]
            await update_user_settings(query)
        await database.update_user_data(user_id)
    elif data[2] == "remove":
        await query.answer("Removed!", show_alert=True)
        if data[3] in user_dict:
            user_dict.pop(data[3], None)
            # Update the appropriate settings page based on the removed setting
            if data[3].startswith("MEGA_"):
                await update_user_settings(query, "mega")
            else:
                await update_user_settings(query)
        await database.update_user_data(user_id)
    elif data[2] == "view":
        await query.answer()
        if data[3] == "THUMBNAIL":
            if await aiopath.exists(thumb_path):
                msg = await send_file(message, thumb_path, name)
                # Auto delete thumbnail after viewing
                create_task(  # noqa: RUF006
                    auto_delete_message(msg, time=30),
                )  # Delete after 30 seconds
            else:
                msg = await send_message(message, "No thumbnail found!")
                create_task(  # noqa: RUF006
                    auto_delete_message(msg, time=10),
                )  # Delete after 10 seconds
        elif data[3] == "FFMPEG_CMDS":
            ffc = None
            if user_dict.get("FFMPEG_CMDS", False):
                ffc = user_dict["FFMPEG_CMDS"]
                source = "User"
            elif "FFMPEG_CMDS" not in user_dict and Config.FFMPEG_CMDS:
                ffc = Config.FFMPEG_CMDS
                source = "Owner"
            else:
                ffc = None
                source = None

            if ffc:
                # Format the FFmpeg commands for better readability
                formatted_cmds = f"FFmpeg Commands ({source}):\n\n"
                if isinstance(ffc, dict):
                    for key, value in ffc.items():
                        formatted_cmds += f"Key: {key}\n"
                        if isinstance(value, list):
                            for i, cmd in enumerate(value):
                                formatted_cmds += f"  Command {i + 1}: {cmd}\n"
                        else:
                            formatted_cmds += f"  Command: {value}\n"
                        formatted_cmds += "\n"
                else:
                    formatted_cmds += str(ffc)

                msg_ecd = formatted_cmds.encode()
                with BytesIO(msg_ecd) as ofile:
                    ofile.name = "ffmpeg_commands.txt"
                    msg = await send_file(message, ofile)
                    # Auto delete file after viewing
                    create_task(  # noqa: RUF006
                        auto_delete_message(msg, time=60),
                    )  # Delete after 60 seconds
            else:
                msg = await send_message(message, "No FFmpeg commands found!")
                create_task(  # noqa: RUF006
                    auto_delete_message(msg, time=10),
                )  # Delete after 10 seconds
    elif data[2] in ["gd", "rc", "yt", "mg"]:
        await query.answer()
        # Cycle through available upload options
        available_uploads = []
        if Config.MIRROR_ENABLED:
            available_uploads.append("gd")
        if Config.RCLONE_ENABLED and Config.MIRROR_ENABLED:
            available_uploads.append("rc")
        if Config.YOUTUBE_UPLOAD_ENABLED:
            available_uploads.append("yt")
        if Config.MEGA_ENABLED:
            available_uploads.append("mg")

        # Find current index and get next option
        current_index = (
            available_uploads.index(data[2]) if data[2] in available_uploads else 0
        )
        next_index = (current_index + 1) % len(available_uploads)
        du = available_uploads[next_index]

        update_user_ldata(user_id, "DEFAULT_UPLOAD", du)
        await update_user_settings(query)
        await database.update_user_data(user_id)
    elif data[2] == "ffvar":
        await query.answer()
        if len(data) > 3:
            key = data[3]
            value = data[4] if len(data) > 4 else None
            index = data[5] if len(data) > 5 else None
            await ffmpeg_variables(
                client, query, message, user_id, key, value, index
            )
        else:
            await ffmpeg_variables(client, query, message, user_id)
    elif data[2] == "back":
        await query.answer()
        await update_user_settings(query)
    else:
        await query.answer()
        await delete_message(message.reply_to_message)
        await delete_message(message)
    # Add auto-delete for all edited messages
    if message and not message.empty:
        create_task(  # noqa: RUF006
            auto_delete_message(message, time=300),
        )  # 5 minutes


@new_task
async def get_users_settings(_, message):
    msg = ""
    if auth_chats:
        msg += f"AUTHORIZED_CHATS: {auth_chats}\n"
    if sudo_users:
        msg += f"SUDO_USERS: {sudo_users}\n\n"
    if user_data:
        for u, d in user_data.items():
            kmsg = f"\n<b>{u}:</b>\n"
            if vmsg := "".join(
                f"{k}: <code>{v or None}</code>\n" for k, v in d.items()
            ):
                msg += kmsg + vmsg
        if not msg:
            error_msg = await send_message(message, "No users data!")
            create_task(
                auto_delete_message(error_msg, time=300)
            )  # Auto-delete after 5 minutes
            return
        msg_ecd = msg.encode()
        if len(msg_ecd) > 4000:
            with BytesIO(msg_ecd) as ofile:
                ofile.name = "users_settings.txt"
                file_msg = await send_file(message, ofile)
                create_task(
                    auto_delete_message(file_msg, time=300)
                )  # Auto-delete after 5 minutes
        else:
            success_msg = await send_message(message, msg)
            create_task(
                auto_delete_message(success_msg, time=300)
            )  # Auto-delete after 5 minutes
    else:
        error_msg = await send_message(message, "No users data!")
        create_task(
            auto_delete_message(error_msg, time=300)
        )  # Auto-delete after 5 minutes
