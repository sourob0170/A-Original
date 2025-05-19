from asyncio import create_subprocess_exec, create_task, sleep
from functools import partial
from html import escape
from http.cookiejar import MozillaCookieJar
from io import BytesIO
from os import getcwd
from re import findall
from time import time

from aiofiles.os import makedirs, remove
from aiofiles.os import path as aiopath
from pyrogram.filters import create
from pyrogram.handlers import MessageHandler

from bot import LOGGER, auth_chats, excluded_extensions, sudo_users, user_data
from bot.core.aeon_client import TgClient
from bot.core.config_manager import Config
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
no_thumb = "https://graph.org/file/80b7fb095063a18f9e232.jpg"

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
    "MISTRAL_API_KEY",
    "MISTRAL_API_URL",
    "DEEPSEEK_API_KEY",
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
        mistral_api_key = (
            "✅ Set" if user_dict.get("MISTRAL_API_KEY", False) else "❌ Not Set"
        )
        mistral_api_url = user_dict.get("MISTRAL_API_URL", "Not Set")
        deepseek_api_key = (
            "✅ Set" if user_dict.get("DEEPSEEK_API_KEY", False) else "❌ Not Set"
        )
        deepseek_api_url = user_dict.get("DEEPSEEK_API_URL", "Not Set")

        text = f"""<u><b>AI Settings for {name}</b></u>
<b>Default AI Provider:</b> <code>{default_ai}</code>

<b>Mistral AI:</b>
-> API Key: <b>{mistral_api_key}</b>
-> API URL: <code>{mistral_api_url}</code>

<b>DeepSeek AI:</b>
-> API Key: <b>{deepseek_api_key}</b>
-> API URL: <code>{deepseek_api_url}</code>

<i>Note: For each AI provider, configure either API Key or API URL. If both are set, API Key will be used first with fallback to API URL.</i>
<i>Your settings will take priority over the bot owner's settings.</i>
<i>Use /ask command to chat with the default AI provider.</i>
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
        ) and default_upload != "gd":
            default_upload = "gd"
            # Update the user's settings
            update_user_ldata(user_id, "DEFAULT_UPLOAD", "gd")

        du = "Gdrive API" if default_upload == "gd" else "Rclone"

        # Only show the toggle button if both Rclone and Mirror are enabled
        if Config.RCLONE_ENABLED and Config.MIRROR_ENABLED:
            dur = "Gdrive API" if default_upload != "gd" else "Rclone"
            buttons.data_button(
                f"Upload using {dur}",
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
    elif ftype == "USER_COOKIES":
        cpath = f"{getcwd()}/cookies/"
        await makedirs(cpath, exist_ok=True)
        des_dir = f"{cpath}{user_id}.txt"
        await message.download(file_name=des_dir)

        # Set secure permissions for the cookies file
        await (await create_subprocess_exec("chmod", "600", des_dir)).wait()
        LOGGER.info(f"Set secure permissions for cookies file of user ID: {user_id}")

        # Check if the cookies file contains YouTube authentication cookies
        has_youtube_auth = False
        try:
            cookie_jar = MozillaCookieJar()
            cookie_jar.load(des_dir)

            # Check for YouTube authentication cookies
            yt_cookies = [c for c in cookie_jar if c.domain.endswith("youtube.com")]
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
    update_user_ldata(user_id, ftype, des_dir)
    await delete_message(message)
    await database.update_user_doc(user_id, ftype, des_dir)


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
    if option in ["THUMBNAIL", "RCLONE_CONFIG", "TOKEN_PICKLE", "USER_COOKIES"]:
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
    elif data[2] in ["leech", "gdrive", "rclone", "metadata", "convert", "ai"]:
        await query.answer()
        # Redirect to main menu if trying to access disabled features
        if (data[2] == "leech" and not Config.LEECH_ENABLED) or (
            data[2] in ["gdrive", "rclone"] and not Config.MIRROR_ENABLED
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
        if data[3] in ["THUMBNAIL", "RCLONE_CONFIG", "TOKEN_PICKLE", "USER_COOKIES"]:
            if data[3] == "THUMBNAIL":
                fpath = thumb_path
            elif data[3] == "RCLONE_CONFIG":
                fpath = rclone_conf
            elif data[3] == "USER_COOKIES":
                fpath = f"cookies/{user_id}.txt"
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
    elif data[2] in ["gd", "rc"]:
        await query.answer()
        du = "rc" if data[2] == "gd" else "gd"
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
