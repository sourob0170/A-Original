from asyncio import create_subprocess_exec, create_task, sleep
from functools import partial
from html import escape
from io import BytesIO
from os import getcwd
from re import findall
from time import time

import aiofiles
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
# Only use owner thumbnail if it's actually configured (not empty/None)
no_thumb = (
    Config.OWNER_THUMB if Config.OWNER_THUMB and Config.OWNER_THUMB.strip() else None
)


def get_ddl_setting(user_id, setting_name, default_value=None):
    """
    Helper function to get DDL settings with user priority

    Args:
        user_id: User ID to get settings for
        setting_name: Name of the setting to retrieve
        default_value: Default value if setting not found

    Returns:
        tuple: (value, source) where source is "User" or "Owner"
    """
    try:
        user_dict = user_data.get(user_id, {})

        # Check user settings first
        user_value = user_dict.get(setting_name, None)
        if user_value is not None:
            return user_value, "User"

        # Fall back to owner config with comprehensive error handling
        try:
            owner_value = getattr(Config, setting_name, default_value)
            return owner_value, "Owner"
        except (AttributeError, KeyError, TypeError, ValueError) as e:
            LOGGER.warning(
                f"Config setting {setting_name} access failed: {e}, using default: {default_value}"
            )
            return default_value, "Default"
        except Exception as e:
            LOGGER.error(
                f"Unexpected error accessing Config.{setting_name}: {e}, using default: {default_value}"
            )
            return default_value, "Default"

    except Exception as e:
        LOGGER.error(
            f"Critical error in get_ddl_setting for {setting_name}: {e}, using default: {default_value}"
        )
        return default_value, "Default"


async def count_user_cookies(user_id):
    """Count the number of cookie files for a user (both file system and database)"""
    # Count from database first
    db_count = await database.count_user_cookies_db(user_id)

    # Also count from file system for backward compatibility
    cookies_dir = "cookies/"
    file_count = 0
    if await aiopath.exists(cookies_dir):
        try:
            import os

            for filename in os.listdir(cookies_dir):
                if filename.startswith(f"{user_id}_") and filename.endswith(".txt"):
                    file_count += 1
        except Exception:
            pass

    # Return the maximum count (in case of migration scenarios)
    return max(db_count, file_count)


async def get_user_cookies_list(user_id):
    """Get list of all cookie files for a user with their creation times (from both DB and filesystem)"""
    cookies_list = []

    # Get cookies from database first
    try:
        db_cookies = await database.get_user_cookies(user_id)
        for cookie in db_cookies:
            import time

            created_time = time.strftime(
                "%Y-%m-%d %H:%M", time.localtime(cookie.get("created_at", 0))
            )
            cookies_list.append(
                {
                    "filename": f"{user_id}_{cookie['number']}.txt",
                    "filepath": f"cookies/{user_id}_{cookie['number']}.txt",
                    "number": str(cookie["number"]),
                    "created": created_time,
                    "source": "database",
                }
            )
    except Exception as e:
        LOGGER.error(f"Error getting cookies from database for user {user_id}: {e}")

    # Also get cookies from file system for backward compatibility
    cookies_dir = "cookies/"
    if await aiopath.exists(cookies_dir):
        try:
            import os
            import time

            for filename in os.listdir(cookies_dir):
                if filename.startswith(f"{user_id}_") and filename.endswith(".txt"):
                    filepath = f"{cookies_dir}{filename}"
                    try:
                        # Get file creation/modification time
                        stat = os.stat(filepath)
                        created_time = time.strftime(
                            "%Y-%m-%d %H:%M", time.localtime(stat.st_mtime)
                        )

                        # Extract cookie number from filename
                        cookie_num = filename.replace(f"{user_id}_", "").replace(
                            ".txt", ""
                        )

                        # Check if this cookie is already in the list from database
                        if not any(c["number"] == cookie_num for c in cookies_list):
                            cookies_list.append(
                                {
                                    "filename": filename,
                                    "filepath": filepath,
                                    "number": cookie_num,
                                    "created": created_time,
                                    "source": "filesystem",
                                }
                            )
                    except Exception:
                        continue
        except Exception:
            pass

    # Sort by cookie number
    cookies_list.sort(
        key=lambda x: int(x["number"]) if x["number"].isdigit() else 999
    )

    return cookies_list


async def get_next_cookie_number(user_id):
    """Get the next available cookie number for a user (checking both DB and filesystem)"""
    used_numbers = set()

    # Get used numbers from database
    try:
        db_cookies = await database.get_user_cookies(user_id)
        for cookie in db_cookies:
            used_numbers.add(int(cookie["number"]))
    except Exception as e:
        LOGGER.error(
            f"Error getting cookie numbers from database for user {user_id}: {e}"
        )

    # Also check file system for backward compatibility
    cookies_dir = "cookies/"
    if await aiopath.exists(cookies_dir):
        try:
            import os

            for filename in os.listdir(cookies_dir):
                if filename.startswith(f"{user_id}_") and filename.endswith(".txt"):
                    cookie_num = filename.replace(f"{user_id}_", "").replace(
                        ".txt", ""
                    )
                    if cookie_num.isdigit():
                        used_numbers.add(int(cookie_num))
        except Exception:
            pass

    # Find the next available number
    next_num = 1
    while next_num in used_numbers:
        next_num += 1

    return next_num


async def migrate_user_cookies_to_db(user_id):
    """Migrate existing user cookies from filesystem to database"""
    cookies_dir = "cookies/"
    if not await aiopath.exists(cookies_dir):
        return 0

    migrated_count = 0
    try:
        import os

        for filename in os.listdir(cookies_dir):
            if filename.startswith(f"{user_id}_") and filename.endswith(".txt"):
                filepath = f"{cookies_dir}{filename}"
                try:
                    # Extract cookie number from filename
                    cookie_num = filename.replace(f"{user_id}_", "").replace(
                        ".txt", ""
                    )
                    if not cookie_num.isdigit():
                        continue

                    cookie_num = int(cookie_num)

                    # Check if this cookie is already in database
                    db_cookies = await database.get_user_cookies(user_id)
                    if any(c["number"] == cookie_num for c in db_cookies):
                        continue  # Already migrated

                    # Read cookie file content
                    async with aiofiles.open(filepath, "rb") as f:
                        cookie_data = await f.read()

                    # Store in database
                    if await database.store_user_cookie(
                        user_id, cookie_num, cookie_data
                    ):
                        migrated_count += 1
                        LOGGER.info(
                            f"Migrated cookie #{cookie_num} for user {user_id} to database"
                        )

                except Exception as e:
                    LOGGER.error(
                        f"Error migrating cookie {filename} for user {user_id}: {e}"
                    )
                    continue
    except Exception as e:
        LOGGER.error(f"Error during cookie migration for user {user_id}: {e}")

    return migrated_count


leech_options = [
    "THUMBNAIL",
    "AUTO_THUMBNAIL",
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
    # "MEGA_UPLOAD_FOLDER" removed - using folder selector instead
    "MEGA_UPLOAD_PUBLIC",
    # "MEGA_UPLOAD_PRIVATE" removed - not supported by MEGA SDK v4.8.0
    # "MEGA_UPLOAD_UNLISTED" removed - not supported by MEGA SDK v4.8.0
    # "MEGA_UPLOAD_EXPIRY_DAYS" removed - premium feature not implemented
    # "MEGA_UPLOAD_PASSWORD" removed - premium feature not implemented
    # "MEGA_UPLOAD_ENCRYPTION_KEY" removed - not supported by MEGA SDK v4.8.0
    "MEGA_UPLOAD_THUMBNAIL",
    # "MEGA_UPLOAD_DELETE_AFTER" removed - always delete after upload
]
yt_dlp_options = ["YT_DLP_OPTIONS", "USER_COOKIES", "FFMPEG_CMDS"]
ddl_options = [
    "DDL_SERVER",
    "GOFILE_API_KEY",
    "GOFILE_FOLDER_NAME",
    "GOFILE_PUBLIC_LINKS",
    "GOFILE_PASSWORD_PROTECTION",
    "GOFILE_DEFAULT_PASSWORD",
    "GOFILE_LINK_EXPIRY_DAYS",
    "STREAMTAPE_API_USERNAME",
    "STREAMTAPE_API_PASSWORD",
    "STREAMTAPE_FOLDER_NAME",
    "DEVUPLOADS_API_KEY",
    "DEVUPLOADS_FOLDER_NAME",
    "DEVUPLOADS_PUBLIC_FILES",
    "MEDIAFIRE_EMAIL",
    "MEDIAFIRE_PASSWORD",
    "MEDIAFIRE_APP_ID",
    "MEDIAFIRE_API_KEY",
]


async def get_user_settings(from_user, stype="main"):
    from bot.helper.ext_utils.bot_utils import is_media_tool_enabled

    user_id = from_user.id
    name = from_user.mention
    buttons = ButtonMaker()
    rclone_conf = f"rclone/{user_id}.conf"
    token_pickle = f"tokens/{user_id}.pickle"
    thumbpath = f"thumbnails/{user_id}.jpg"
    user_dict = user_data.get(user_id, {})
    # Only show thumbnail if user has one or if owner thumbnail is configured
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

        # Auto Thumbnail toggle
        auto_thumb = user_dict.get("AUTO_THUMBNAIL")
        if auto_thumb is None:
            auto_thumb = Config.AUTO_THUMBNAIL

        if auto_thumb:
            buttons.data_button(
                "Auto Thumbnail: ✅ ON",
                f"userset {user_id} tog AUTO_THUMBNAIL f",
            )
        else:
            buttons.data_button(
                "Auto Thumbnail: ❌ OFF",
                f"userset {user_id} tog AUTO_THUMBNAIL t",
            )

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

        # Get auto thumbnail status
        auto_thumb = user_dict.get("AUTO_THUMBNAIL")
        if auto_thumb is None:
            auto_thumb = Config.AUTO_THUMBNAIL
        auto_thumb_status = "✅ Enabled" if auto_thumb else "❌ Disabled"

        text = f"""<u><b>Leech Settings for {name}</b></u>
-> Leech Type: <b>{ltype}</b>
-> Media Group: <b>{media_group}</b>
-> Media Store: <b>{media_store}</b>
-> Auto Thumbnail: <b>{auto_thumb_status}</b>
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
        # Check if MEGA operations are enabled
        if not Config.MEGA_ENABLED or not Config.MEGA_UPLOAD_ENABLED:
            buttons.data_button("Back", f"userset {user_id} back")
            buttons.data_button("Close", f"userset {user_id} close")

            disabled_reason = []
            if not Config.MEGA_ENABLED:
                disabled_reason.append("MEGA operations")
            if not Config.MEGA_UPLOAD_ENABLED:
                disabled_reason.append("MEGA upload")

            text = f"""<u><b>☁️ MEGA Settings for {name}</b></u>

❌ <b>MEGA Settings Disabled</b>

{" and ".join(disabled_reason)} {"is" if len(disabled_reason) == 1 else "are"} disabled by the administrator.

Please contact the administrator to enable MEGA functionality.
"""
            return text, buttons.build_menu(2), thumbnail

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

        # User credential settings - use menu action for consistent reset/remove buttons
        buttons.data_button("📧 Email", f"userset {user_id} menu MEGA_EMAIL")
        buttons.data_button("🔑 Password", f"userset {user_id} menu MEGA_PASSWORD")

        # Upload Settings
        # Upload Folder button removed - using folder selector instead
        # Link Expiry, Upload Password, Encryption Key buttons removed - not supported by MEGA SDK v4.8.0

        # Toggle buttons for boolean settings
        public_links, public_links_source = get_mega_setting(
            "MEGA_UPLOAD_PUBLIC", False, True
        )
        # private_links, unlisted_links removed - not supported by MEGA SDK v4.8.0
        thumbnails, thumbnails_source = get_mega_setting(
            "MEGA_UPLOAD_THUMBNAIL", False, True
        )
        # delete_after removed - always delete after upload

        buttons.data_button(
            f"🔗 Public Links: {'✅ ON' if public_links else '❌ OFF'}",
            f"userset {user_id} tog MEGA_UPLOAD_PUBLIC {'f' if public_links else 't'}",
        )
        # Private Links and Unlisted Links buttons removed - not supported by MEGA SDK v4.8.0
        buttons.data_button(
            f"🖼️ Thumbnails: {'✅ ON' if thumbnails else '❌ OFF'}",
            f"userset {user_id} tog MEGA_UPLOAD_THUMBNAIL {'f' if thumbnails else 't'}",
        )
        # Delete After button removed - always delete after upload

        buttons.data_button("Back", f"userset {user_id} back")
        buttons.data_button("Close", f"userset {user_id} close")

        # Upload settings
        # upload_folder removed - using folder selector instead
        public_links, public_links_source = get_mega_setting(
            "MEGA_UPLOAD_PUBLIC", False, True
        )
        # private_links, unlisted_links, expiry_days, upload_password, encryption_key removed - not supported by MEGA SDK v4.8.0
        thumbnails, thumbnails_source = get_mega_setting(
            "MEGA_UPLOAD_THUMBNAIL", False, True
        )
        # delete_after removed - always delete after upload

        # Format display values
        # upload_folder_display, expiry_display, password_display, encryption_display removed - not supported by MEGA SDK v4.8.0

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
Folder: <b>📁 Using Folder Selector</b>
Public Links: <b>{"✅ Enabled" if public_links else "❌ Disabled"}</b>
Thumbnails: <b>{"✅ Enabled" if thumbnails else "❌ Disabled"}</b> | Delete After: <b>🗑️ Always Delete</b>

<b>ℹ️ Note:</b> Private/Unlisted links, Password protection, Link expiry, and Custom encryption are not supported by MEGA SDK v4.8.0


<i>Your settings override owner settings. Set your own MEGA credentials to use your account.</i>
"""

    elif stype == "convert":
        buttons.data_button("Back", f"userset {user_id} back")
        buttons.data_button("Close", f"userset {user_id} close")

        text = f"""<u><b>Convert Settings for {name}</b></u>
Convert settings have been moved to Media Tools settings.
Please use /mediatools command to configure convert settings.
"""

    elif stype == "gallerydl_main":
        # Gallery-dl Settings - only show if Gallery-dl is enabled
        if not Config.GALLERY_DL_ENABLED:
            buttons.data_button("Back", f"userset {user_id} back")
            buttons.data_button("Close", f"userset {user_id} close")
            text = f"""<u><b>🖼️ Gallery-dl Settings for {name}</b></u>

<b>⚠️ Gallery-dl is currently disabled by the bot owner.</b>

Gallery-dl allows downloading media from 200+ platforms including:
• Instagram, Twitter, Reddit
• Pixiv, DeviantArt, ArtStation
• Tumblr, Discord, and many more

Contact the bot owner to enable Gallery-dl functionality."""
        else:
            # Gallery-dl is enabled, show settings menu
            buttons.data_button(
                "⚙️ General Settings", f"userset {user_id} gallerydl_general"
            )
            buttons.data_button(
                "🔐 Authentication", f"userset {user_id} gallerydl_auth"
            )
            buttons.data_button("Back", f"userset {user_id} back")
            buttons.data_button("Close", f"userset {user_id} close")

            # Get user's gallery-dl settings status
            user_general_settings = any(
                key in user_dict
                for key in [
                    "GALLERY_DL_QUALITY_SELECTION",
                    "GALLERY_DL_ARCHIVE_ENABLED",
                    "GALLERY_DL_METADATA_ENABLED",
                ]
            )
            user_auth_settings = any(
                key in user_dict
                for key in [
                    "GALLERY_DL_INSTAGRAM_USERNAME",
                    "GALLERY_DL_TWITTER_USERNAME",
                    "GALLERY_DL_REDDIT_CLIENT_ID",
                    "GALLERY_DL_PIXIV_USERNAME",
                    "GALLERY_DL_DEVIANTART_CLIENT_ID",
                    "GALLERY_DL_TUMBLR_API_KEY",
                    "GALLERY_DL_DISCORD_TOKEN",
                ]
            )

            general_status = (
                "User configured"
                if user_general_settings
                else "Using owner settings"
            )
            auth_status = (
                "User configured" if user_auth_settings else "Using owner settings"
            )

            text = f"""<u><b>🖼️ Gallery-dl Settings for {name}</b></u>

<b>Configuration Status:</b>
• General Settings: <b>{general_status}</b>
• Authentication: <b>{auth_status}</b>

<b>Supported Platforms:</b>
Gallery-dl supports 200+ platforms including Instagram, Twitter, Reddit, Pixiv, DeviantArt, Tumblr, Discord, and many more.

<i>💡 Your settings will override the bot owner's settings.</i>
<i>🔒 All credentials are stored securely and privately.</i>"""

    elif stype == "gallerydl_general":
        # Gallery-dl General Settings
        general_settings = [
            "GALLERY_DL_QUALITY_SELECTION",
            "GALLERY_DL_ARCHIVE_ENABLED",
            "GALLERY_DL_METADATA_ENABLED",
        ]

        for setting in general_settings:
            display_name = (
                setting.replace("GALLERY_DL_", "").replace("_", " ").title()
            )
            buttons.data_button(display_name, f"userset {user_id} menu {setting}")

        buttons.data_button("Back", f"userset {user_id} gallerydl_main")
        buttons.data_button("Close", f"userset {user_id} close")

        # Get current values
        quality_selection = user_dict.get(
            "GALLERY_DL_QUALITY_SELECTION", Config.GALLERY_DL_QUALITY_SELECTION
        )
        archive_enabled = user_dict.get(
            "GALLERY_DL_ARCHIVE_ENABLED", Config.GALLERY_DL_ARCHIVE_ENABLED
        )
        metadata_enabled = user_dict.get(
            "GALLERY_DL_METADATA_ENABLED", Config.GALLERY_DL_METADATA_ENABLED
        )

        quality_status = "✅ Enabled" if quality_selection else "❌ Disabled"
        archive_status = "✅ Enabled" if archive_enabled else "❌ Disabled"
        metadata_status = "✅ Enabled" if metadata_enabled else "❌ Disabled"

        text = f"""<u><b>🖼️ Gallery-dl General Settings for {name}</b></u>

<b>Current Settings:</b>
• Quality Selection: <b>{quality_status}</b>
• Archive: <b>{archive_status}</b>
• Metadata: <b>{metadata_status}</b>

<b>Description:</b>
• <b>Quality Selection:</b> Show quality selection interface for downloads
• <b>Archive:</b> Keep track of downloaded files to avoid duplicates
• <b>Metadata:</b> Save metadata files (JSON, YAML, TXT) with downloads

<i>💡 Your settings will override the bot owner's settings.</i>"""

    elif stype == "gallerydl_auth":
        # Gallery-dl Authentication Settings
        auth_settings = [
            "GALLERY_DL_INSTAGRAM_USERNAME",
            "GALLERY_DL_INSTAGRAM_PASSWORD",
            "GALLERY_DL_TWITTER_USERNAME",
            "GALLERY_DL_TWITTER_PASSWORD",
            "GALLERY_DL_REDDIT_CLIENT_ID",
            "GALLERY_DL_REDDIT_CLIENT_SECRET",
            "GALLERY_DL_REDDIT_USERNAME",
            "GALLERY_DL_REDDIT_PASSWORD",
            "GALLERY_DL_REDDIT_REFRESH_TOKEN",
            "GALLERY_DL_PIXIV_USERNAME",
            "GALLERY_DL_PIXIV_PASSWORD",
            "GALLERY_DL_PIXIV_REFRESH_TOKEN",
            "GALLERY_DL_DEVIANTART_CLIENT_ID",
            "GALLERY_DL_DEVIANTART_CLIENT_SECRET",
            "GALLERY_DL_DEVIANTART_USERNAME",
            "GALLERY_DL_DEVIANTART_PASSWORD",
            "GALLERY_DL_TUMBLR_API_KEY",
            "GALLERY_DL_TUMBLR_API_SECRET",
            "GALLERY_DL_TUMBLR_TOKEN",
            "GALLERY_DL_TUMBLR_TOKEN_SECRET",
            "GALLERY_DL_DISCORD_TOKEN",
        ]

        for setting in auth_settings:
            display_name = (
                setting.replace("GALLERY_DL_", "").replace("_", " ").title()
            )
            buttons.data_button(display_name, f"userset {user_id} menu {setting}")

        buttons.data_button("Back", f"userset {user_id} gallerydl_main")
        buttons.data_button("Close", f"userset {user_id} close")

        text = f"""<u><b>🖼️ Gallery-dl Authentication Settings for {name}</b></u>

<b>Platform Authentication:</b>
Configure credentials for accessing private content and higher quality downloads.

<b>Supported Platforms:</b>
• <b>Instagram:</b> Username/password for private accounts and stories
• <b>Twitter/X:</b> Username/password for private accounts and higher quality
• <b>Reddit:</b> OAuth credentials for NSFW content and private subreddits
• <b>Pixiv:</b> Username/password for R-18 content and following artists
• <b>DeviantArt:</b> OAuth credentials for mature content and Eclipse features
• <b>Tumblr:</b> API credentials for NSFW content
• <b>Discord:</b> Bot token for server content

<i>💡 Your settings will override the bot owner's settings.</i>
<i>🔒 All credentials are stored securely and privately.</i>"""

    elif stype == "cookies_main":
        # User Cookies Management
        # First, migrate any existing cookies to database
        try:
            migrated = await migrate_user_cookies_to_db(user_id)
            if migrated > 0:
                LOGGER.info(
                    f"Migrated {migrated} cookies to database for user {user_id}"
                )
        except Exception as e:
            LOGGER.error(f"Error during cookie migration for user {user_id}: {e}")

        cookies_list = await get_user_cookies_list(user_id)

        buttons.data_button("➕ Add New Cookie", f"userset {user_id} cookies_add")

        if cookies_list:
            buttons.data_button(
                "🗑️ Remove All", f"userset {user_id} cookies_remove_all"
            )

            # Show individual cookies
            for cookie in cookies_list[:10]:  # Limit to 10 cookies for UI
                cookie_name = f"Cookie #{cookie['number']}"
                buttons.data_button(
                    f"🍪 {cookie_name}",
                    f"userset {user_id} cookies_manage {cookie['number']}",
                )

        buttons.data_button("ℹ️ Help", f"userset {user_id} cookies_help")
        buttons.data_button("Back", f"userset {user_id} back")
        buttons.data_button("Close", f"userset {user_id} close")

        cookies_count = len(cookies_list)

        # Build the base text first
        base_text = f"""<u><b>🍪 User Cookies Management for {name}</b></u>

<b>Total Cookies:</b> {cookies_count}

<b>Your Cookies:</b>
"""

        footer_text = """
<i>💡 You can upload unlimited cookies for different sites. When downloading with YT-DLP or Gallery-dl, the bot will try each cookie until one works.</i>
<i>🔒 Only you can access your cookies - they are completely private.</i>"""

        # Calculate available space for cookies list (Telegram limit is 1024 chars)
        available_space = (
            1024 - len(base_text) - len(footer_text) - 50
        )  # 50 chars buffer

        if cookies_count > 0:
            cookies_info = ""
            cookies_shown = 0

            for cookie in cookies_list:
                cookie_line = f"🍪 <b>Cookie #{cookie['number']}</b> - Added: {cookie['created']}\n"

                # Check if adding this line would exceed the limit
                if len(cookies_info + cookie_line) > available_space:
                    break

                cookies_info += cookie_line
                cookies_shown += 1

            # Remove trailing newline
            cookies_info = cookies_info.rstrip("\n")

            # Add "and X more" if we couldn't show all cookies
            if cookies_shown < cookies_count:
                remaining = cookies_count - cookies_shown
                more_text = f"\n... and {remaining} more"

                # Check if we have space for the "more" text
                if len(cookies_info + more_text) <= available_space:
                    cookies_info += more_text
                # If not enough space, remove the last cookie and add "more" text
                elif cookies_shown > 0:
                    lines = cookies_info.split("\n")
                    lines = lines[:-1]  # Remove last line
                    cookies_info = "\n".join(lines)
                    remaining = cookies_count - (cookies_shown - 1)
                    cookies_info += f"\n... and {remaining} more"
        else:
            cookies_info = "No cookies uploaded yet."

        text = base_text + cookies_info + footer_text

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

    elif stype == "ddl":
        # DDL Settings - only show if DDL is enabled
        if not Config.DDL_ENABLED:
            buttons.data_button("Back", f"userset {user_id} back")
            buttons.data_button("Close", f"userset {user_id} close")
            text = f"""<u><b>🔗 DDL Settings for {name}</b></u>

<b>❌ DDL (Direct Download Link) uploads are currently disabled by the bot owner.</b>

<i>Contact the bot owner to enable DDL functionality.</i>"""
        else:
            # DDL General Settings
            buttons.data_button(
                "📤 General Settings", f"userset {user_id} ddl_general"
            )
            buttons.data_button(
                "📁 Gofile Settings", f"userset {user_id} ddl_gofile"
            )
            buttons.data_button(
                "🎬 Streamtape Settings", f"userset {user_id} ddl_streamtape"
            )
            buttons.data_button(
                "🚀 DevUploads Settings", f"userset {user_id} ddl_devuploads"
            )
            buttons.data_button(
                "🔥 MediaFire Settings", f"userset {user_id} ddl_mediafire"
            )

            buttons.data_button("Back", f"userset {user_id} back")
            buttons.data_button("Close", f"userset {user_id} close")

            # Helper function to get DDL settings with user priority (local version)
            def get_ddl_setting_local(setting_name, default_value=None):
                # Check user settings first
                user_value = user_dict.get(setting_name, None)
                if user_value is not None:
                    return user_value, "User"

                # Fall back to owner config
                owner_value = getattr(Config, setting_name, default_value)
                return owner_value, "Owner"

            # Get DDL settings
            ddl_server, ddl_server_source = get_ddl_setting_local(
                "DDL_SERVER", Config.DDL_DEFAULT_SERVER
            )

            # Gofile settings
            gofile_api_key, gofile_api_source = get_ddl_setting_local(
                "GOFILE_API_KEY", ""
            )
            gofile_folder, gofile_folder_source = get_ddl_setting_local(
                "GOFILE_FOLDER_NAME", ""
            )
            gofile_public, gofile_public_source = get_ddl_setting_local(
                "GOFILE_PUBLIC_LINKS", Config.GOFILE_PUBLIC_LINKS
            )
            gofile_password_protection, gofile_password_source = (
                get_ddl_setting_local(
                    "GOFILE_PASSWORD_PROTECTION", Config.GOFILE_PASSWORD_PROTECTION
                )
            )
            gofile_default_password, gofile_default_password_source = (
                get_ddl_setting_local("GOFILE_DEFAULT_PASSWORD", "")
            )
            gofile_expiry, gofile_expiry_source = get_ddl_setting_local(
                "GOFILE_LINK_EXPIRY_DAYS", Config.GOFILE_LINK_EXPIRY_DAYS
            )

            # Streamtape settings
            streamtape_api_username, streamtape_username_source = (
                get_ddl_setting_local("STREAMTAPE_API_USERNAME", "")
            )
            streamtape_api_password, streamtape_password_source = (
                get_ddl_setting_local("STREAMTAPE_API_PASSWORD", "")
            )
            streamtape_folder, streamtape_folder_source = get_ddl_setting_local(
                "STREAMTAPE_FOLDER_NAME", ""
            )

            # DevUploads settings
            devuploads_api_key, devuploads_api_source = get_ddl_setting_local(
                "DEVUPLOADS_API_KEY", ""
            )
            devuploads_folder, devuploads_folder_source = get_ddl_setting_local(
                "DEVUPLOADS_FOLDER_NAME", ""
            )
            devuploads_public, devuploads_public_source = get_ddl_setting_local(
                "DEVUPLOADS_PUBLIC_FILES", True
            )

            # Status indicators
            gofile_status = "✅ Ready" if gofile_api_key else "❌ API Key Required"
            streamtape_status = (
                "✅ Ready"
                if (streamtape_api_username and streamtape_api_password)
                else "❌ Credentials Required"
            )
            devuploads_status = (
                "✅ Ready" if devuploads_api_key else "❌ API Key Required"
            )

            # Display values
            gofile_api_display = "Set" if gofile_api_key else "Not Set"
            gofile_folder_display = gofile_folder or "None (Use filename)"
            gofile_password_display = gofile_default_password or "None"
            gofile_expiry_display = (
                f"{gofile_expiry} days" if gofile_expiry else "No expiry"
            )

            streamtape_username_display = (
                "Set" if streamtape_api_username else "Not Set"
            )
            streamtape_password_display = (
                "Set" if streamtape_api_password else "Not Set"
            )
            streamtape_folder_display = streamtape_folder or "None (Root folder)"

            devuploads_api_display = "Set" if devuploads_api_key else "Not Set"
            devuploads_folder_display = devuploads_folder or "None (Root folder)"
            devuploads_public_display = (
                "✅ Public" if devuploads_public else "🔒 Private"
            )

            # MediaFire settings
            mediafire_email, mediafire_email_source = get_ddl_setting_local(
                "MEDIAFIRE_EMAIL", ""
            )
            mediafire_password, mediafire_password_source = get_ddl_setting_local(
                "MEDIAFIRE_PASSWORD", ""
            )
            mediafire_app_id, mediafire_app_id_source = get_ddl_setting_local(
                "MEDIAFIRE_APP_ID", ""
            )
            mediafire_api_key, mediafire_api_key_source = get_ddl_setting_local(
                "MEDIAFIRE_API_KEY", ""
            )

            mediafire_status = (
                "✅ Enabled"
                if (mediafire_email and mediafire_password and mediafire_app_id)
                else "❌ Disabled"
            )
            mediafire_email_display = "Set" if mediafire_email else "Not Set"
            mediafire_password_display = "Set" if mediafire_password else "Not Set"
            mediafire_app_id_display = "Set" if mediafire_app_id else "Not Set"
            mediafire_api_key_display = "Set" if mediafire_api_key else "Not Set"

            text = f"""<u><b>🔗 DDL Settings for {name}</b></u>

<b>📤 General:</b>
Default Server: <code>{ddl_server}</code> ({ddl_server_source})

<b>📁 Gofile Server:</b>
Status: <b>{gofile_status}</b>
API Key: <code>{gofile_api_display}</code> ({gofile_api_source})
Folder: <code>{gofile_folder_display}</code> ({gofile_folder_source})
Public Links: <b>{"✅" if gofile_public else "❌"}</b> ({gofile_public_source})
Password Protection: <b>{"✅" if gofile_password_protection else "❌"}</b> ({gofile_password_source})
Default Password: <code>{gofile_password_display}</code> ({gofile_default_password_source})
Link Expiry: <code>{gofile_expiry_display}</code> ({gofile_expiry_source})

<b>🎬 Streamtape Server:</b>
Status: <b>{streamtape_status}</b>
API Username: <code>{streamtape_username_display}</code> ({streamtape_username_source})
API Password: <code>{streamtape_password_display}</code> ({streamtape_password_source})
Folder: <code>{streamtape_folder_display}</code> ({streamtape_folder_source})

<b>🚀 DevUploads Server:</b>
Status: <b>{devuploads_status}</b>
API Key: <code>{devuploads_api_display}</code> ({devuploads_api_source})
Folder: <code>{devuploads_folder_display}</code> ({devuploads_folder_source})
Public Files: <b>{devuploads_public_display}</b> ({devuploads_public_source})

<b>🔥 MediaFire Server:</b>
Status: <b>{mediafire_status}</b>
Email: <code>{mediafire_email_display}</code> ({mediafire_email_source})
Password: <code>{mediafire_password_display}</code> ({mediafire_password_source})
App ID: <code>{mediafire_app_id_display}</code> ({mediafire_app_id_source})
API Key: <code>{mediafire_api_key_display}</code> ({mediafire_api_key_source})

<i>💡 Your settings override owner settings. Configure your own API keys for personalized uploads.</i>
<i>🔗 Use -up ddl to upload to default server, or -up ddl:gofile / -up ddl:streamtape / -up ddl:devuploads / -up ddl:mediafire for specific servers.</i>"""

    elif stype == "ddl_general":
        # DDL General Settings
        buttons.data_button("Default Server", f"userset {user_id} menu DDL_SERVER")
        buttons.data_button("Back", f"userset {user_id} ddl")
        buttons.data_button("Close", f"userset {user_id} close")

        # Get DDL server setting
        ddl_server = user_dict.get("DDL_SERVER", Config.DDL_DEFAULT_SERVER)
        ddl_server_source = "User" if "DDL_SERVER" in user_dict else "Owner"

        text = f"""<u><b>📤 DDL General Settings for {name}</b></u>

<b>Server Configuration:</b>
Default Server: <code>{ddl_server}</code> (Set by {ddl_server_source})

<b>Available Servers:</b>
• <b>gofile</b> - Supports all file types, free tier available
• <b>streamtape</b> - Video files only, requires account
• <b>devuploads</b> - Supports all file types, requires API key
• <b>mediafire</b> - Supports all file types, requires account

<i>The default server will be used when you specify -up ddl without a specific server.</i>"""

    elif stype == "ddl_gofile":
        # Gofile Settings
        buttons.data_button("API Key", f"userset {user_id} menu GOFILE_API_KEY")
        buttons.data_button(
            "Folder Name", f"userset {user_id} menu GOFILE_FOLDER_NAME"
        )
        buttons.data_button(
            "Default Password", f"userset {user_id} menu GOFILE_DEFAULT_PASSWORD"
        )
        buttons.data_button(
            "Link Expiry Days", f"userset {user_id} menu GOFILE_LINK_EXPIRY_DAYS"
        )

        # Toggle buttons
        gofile_public = user_dict.get(
            "GOFILE_PUBLIC_LINKS", Config.GOFILE_PUBLIC_LINKS
        )
        buttons.data_button(
            f"Public Links: {'✅ ON' if gofile_public else '❌ OFF'}",
            f"userset {user_id} tog GOFILE_PUBLIC_LINKS {'f' if gofile_public else 't'}",
        )

        gofile_password_protection = user_dict.get(
            "GOFILE_PASSWORD_PROTECTION", Config.GOFILE_PASSWORD_PROTECTION
        )
        buttons.data_button(
            f"Password Protection: {'✅ ON' if gofile_password_protection else '❌ OFF'}",
            f"userset {user_id} tog GOFILE_PASSWORD_PROTECTION {'f' if gofile_password_protection else 't'}",
        )

        buttons.data_button("Back", f"userset {user_id} ddl")
        buttons.data_button("Close", f"userset {user_id} close")

        # Get Gofile settings with user priority
        def get_gofile_setting(setting_name, default_value=None):
            # Check user settings first
            user_value = user_dict.get(setting_name, None)
            if user_value is not None:
                return user_value, "User"

            # Fall back to owner config
            owner_value = getattr(Config, setting_name, default_value)
            return owner_value, "Owner"

        gofile_api_key, gofile_api_source = get_gofile_setting("GOFILE_API_KEY", "")
        gofile_folder, gofile_folder_source = get_gofile_setting(
            "GOFILE_FOLDER_NAME", ""
        )
        gofile_public, gofile_public_source = get_gofile_setting(
            "GOFILE_PUBLIC_LINKS", Config.GOFILE_PUBLIC_LINKS
        )
        gofile_password_protection, gofile_password_source = get_gofile_setting(
            "GOFILE_PASSWORD_PROTECTION", Config.GOFILE_PASSWORD_PROTECTION
        )
        gofile_default_password, gofile_default_password_source = get_gofile_setting(
            "GOFILE_DEFAULT_PASSWORD", ""
        )
        gofile_expiry, gofile_expiry_source = get_gofile_setting(
            "GOFILE_LINK_EXPIRY_DAYS", Config.GOFILE_LINK_EXPIRY_DAYS
        )

        # Display values
        gofile_api_display = "Set" if gofile_api_key else "Not Set"
        gofile_folder_display = gofile_folder or "None (Use filename)"
        gofile_password_display = gofile_default_password or "None"
        gofile_expiry_display = (
            f"{gofile_expiry} days" if gofile_expiry else "No expiry"
        )

        text = f"""<u><b>📁 Gofile Settings for {name}</b></u>

<b>Authentication:</b>
API Key: <code>{gofile_api_display}</code> ({gofile_api_source})

<b>Upload Settings:</b>
Folder Name: <code>{gofile_folder_display}</code> ({gofile_folder_source})
Public Links: <b>{"✅ Enabled" if gofile_public else "❌ Disabled"}</b> ({gofile_public_source})
Password Protection: <b>{"✅ Enabled" if gofile_password_protection else "❌ Disabled"}</b> ({gofile_password_source})
Default Password: <code>{gofile_password_display}</code> ({gofile_default_password_source})
Link Expiry: <code>{gofile_expiry_display}</code> ({gofile_expiry_source})

<b>Features:</b>
• Supports all file types
• Free tier available (with limitations)
• Premium accounts get better speeds and storage
• Password protection available
• Custom expiry dates

<i>Get your API key from <a href="https://gofile.io/myProfile">Gofile Profile</a></i>"""

    elif stype == "ddl_streamtape":
        # Streamtape Settings
        buttons.data_button(
            "API Username", f"userset {user_id} menu STREAMTAPE_API_USERNAME"
        )
        buttons.data_button(
            "API Password", f"userset {user_id} menu STREAMTAPE_API_PASSWORD"
        )
        buttons.data_button(
            "Folder Name", f"userset {user_id} menu STREAMTAPE_FOLDER_NAME"
        )

        buttons.data_button("Back", f"userset {user_id} ddl")
        buttons.data_button("Close", f"userset {user_id} close")

        # Get Streamtape settings with user priority
        def get_streamtape_setting(setting_name, default_value=None):
            # Check user settings first
            user_value = user_dict.get(setting_name, None)
            if user_value is not None:
                return user_value, "User"

            # Fall back to owner config
            owner_value = getattr(Config, setting_name, default_value)
            return owner_value, "Owner"

        streamtape_api_username, streamtape_username_source = get_streamtape_setting(
            "STREAMTAPE_API_USERNAME", ""
        )
        streamtape_api_password, streamtape_password_source = get_streamtape_setting(
            "STREAMTAPE_API_PASSWORD", ""
        )
        streamtape_folder, streamtape_folder_source = get_streamtape_setting(
            "STREAMTAPE_FOLDER_NAME", ""
        )

        # Display values
        streamtape_username_display = "Set" if streamtape_api_username else "Not Set"
        streamtape_password_display = "Set" if streamtape_api_password else "Not Set"
        streamtape_folder_display = streamtape_folder or "None (Root folder)"

        text = f"""<u><b>🎬 Streamtape Settings for {name}</b></u>

<b>Authentication:</b>
API Username: <code>{streamtape_username_display}</code> ({streamtape_username_source})
API Password: <code>{streamtape_password_display}</code> ({streamtape_password_source})

<b>Upload Settings:</b>
Folder Name: <code>{streamtape_folder_display}</code> ({streamtape_folder_source})

<b>Supported Formats:</b>
• Video files only: .mp4, .mkv, .avi, .mov, .wmv, .flv, .webm, .m4v
• Maximum file size depends on account type

<b>Features:</b>
• Fast video streaming
• Direct download links
• Folder organization
• Account required for uploads

<i>Get your API credentials from <a href="https://streamtape.com/accpanel">Streamtape Account Panel</a></i>"""

    elif stype == "ddl_devuploads":
        # DevUploads Settings
        buttons.data_button("API Key", f"userset {user_id} menu DEVUPLOADS_API_KEY")
        buttons.data_button(
            "Folder Name", f"userset {user_id} menu DEVUPLOADS_FOLDER_NAME"
        )
        buttons.data_button(
            "Public Files", f"userset {user_id} menu DEVUPLOADS_PUBLIC_FILES"
        )

        buttons.data_button("Back", f"userset {user_id} ddl")
        buttons.data_button("Close", f"userset {user_id} close")

        # Get DevUploads settings with user priority
        def get_devuploads_setting(setting_name, default_value=None):
            # Check user settings first
            user_value = user_dict.get(setting_name, None)
            if user_value is not None:
                return user_value, "User"

            # Fall back to owner config
            owner_value = getattr(Config, setting_name, default_value)
            return owner_value, "Owner"

        # Get DevUploads settings
        devuploads_api_key, devuploads_api_source = get_devuploads_setting(
            "DEVUPLOADS_API_KEY", ""
        )
        devuploads_folder, devuploads_folder_source = get_devuploads_setting(
            "DEVUPLOADS_FOLDER_NAME", ""
        )
        devuploads_public, devuploads_public_source = get_devuploads_setting(
            "DEVUPLOADS_PUBLIC_FILES", True
        )

        # Display values
        devuploads_api_display = "Set" if devuploads_api_key else "Not Set"
        devuploads_folder_display = devuploads_folder or "None (Root folder)"
        devuploads_public_display = (
            "✅ Public" if devuploads_public else "🔒 Private"
        )

        text = f"""<u><b>🚀 DevUploads Settings for {name}</b></u>

<b>Authentication:</b>
API Key: <code>{devuploads_api_display}</code> ({devuploads_api_source})

<b>Upload Settings:</b>
Folder Name: <code>{devuploads_folder_display}</code> ({devuploads_folder_source})
Public Files: <b>{devuploads_public_display}</b> ({devuploads_public_source})

<b>Supported Formats:</b>
• All file types supported
• Maximum file size: 5 GB
• Files expire after 30 days

<b>Features:</b>
• Fast download speeds
• Direct download links
• Folder organization
• Public/Private file settings
• API key required for uploads

<i>Get your API key from <a href="https://devuploads.com/api">DevUploads API</a></i>"""

    elif stype == "ddl_mediafire":
        # MediaFire Settings
        buttons.data_button("Email", f"userset {user_id} menu MEDIAFIRE_EMAIL")
        buttons.data_button("Password", f"userset {user_id} menu MEDIAFIRE_PASSWORD")
        buttons.data_button("App ID", f"userset {user_id} menu MEDIAFIRE_APP_ID")
        buttons.data_button("API Key", f"userset {user_id} menu MEDIAFIRE_API_KEY")

        buttons.data_button("Back", f"userset {user_id} ddl")
        buttons.data_button("Close", f"userset {user_id} close")

        # Get MediaFire settings with user priority
        def get_mediafire_setting(setting_name, default_value=None):
            # Check user settings first
            user_value = user_dict.get(setting_name, None)
            if user_value is not None:
                return user_value, "User"

            # Fall back to owner config
            owner_value = getattr(Config, setting_name, default_value)
            return owner_value, "Owner"

        # Get MediaFire settings
        mediafire_email, mediafire_email_source = get_mediafire_setting(
            "MEDIAFIRE_EMAIL", ""
        )
        mediafire_password, mediafire_password_source = get_mediafire_setting(
            "MEDIAFIRE_PASSWORD", ""
        )
        mediafire_app_id, mediafire_app_id_source = get_mediafire_setting(
            "MEDIAFIRE_APP_ID", ""
        )
        mediafire_api_key, mediafire_api_key_source = get_mediafire_setting(
            "MEDIAFIRE_API_KEY", ""
        )

        # Display values
        mediafire_email_display = "Set" if mediafire_email else "Not Set"
        mediafire_password_display = "Set" if mediafire_password else "Not Set"
        mediafire_app_id_display = "Set" if mediafire_app_id else "Not Set"
        mediafire_api_key_display = "Set" if mediafire_api_key else "Not Set"
        mediafire_status = (
            "✅ Enabled"
            if (mediafire_email and mediafire_password and mediafire_app_id)
            else "❌ Disabled"
        )

        text = f"""<u><b>🔥 MediaFire Settings for {name}</b></u>

<b>Authentication:</b>
Email: <code>{mediafire_email_display}</code> ({mediafire_email_source})
Password: <code>{mediafire_password_display}</code> ({mediafire_password_source})
App ID: <code>{mediafire_app_id_display}</code> ({mediafire_app_id_source})
API Key: <code>{mediafire_api_key_display}</code> ({mediafire_api_key_source})

<b>Status:</b> {mediafire_status}

<b>Supported Formats:</b>
• All file types supported
• Maximum file size: ~50 GB
• Files stored permanently
• Instant upload for duplicate files

<b>Features:</b>
• Large file support (up to 50GB)
• Official API integration
• Instant upload detection
• Hash verification
• Folder organization
• Account required for uploads

<i>Get your credentials from <a href="https://www.mediafire.com/developers/">MediaFire Developers</a></i>
<i>Email, Password, and App ID are required. API Key is optional for enhanced features.</i>"""

    else:
        # Show service buttons based on individual service availability
        # Only show Leech button if Leech operations are enabled
        if Config.LEECH_ENABLED:
            buttons.data_button("Leech", f"userset {user_id} leech")

        # Show upload service buttons only if mirror operations are enabled
        if Config.MIRROR_ENABLED:
            # Only show Gdrive API button if Gdrive upload is enabled
            if Config.GDRIVE_UPLOAD_ENABLED:
                buttons.data_button("Gdrive API", f"userset {user_id} gdrive")

            # Only show Rclone button if Rclone operations are enabled
            if Config.RCLONE_ENABLED:
                buttons.data_button("Rclone", f"userset {user_id} rclone")

            # Only show YouTube API button if YouTube upload is enabled
            if Config.YOUTUBE_UPLOAD_ENABLED:
                buttons.data_button("YouTube API", f"userset {user_id} youtube")

            # Only show MEGA Settings button if MEGA and MEGA upload are enabled
            if Config.MEGA_ENABLED and Config.MEGA_UPLOAD_ENABLED:
                buttons.data_button("☁️ MEGA", f"userset {user_id} mega")

            # Only show DDL Settings button if DDL is enabled
            if Config.DDL_ENABLED:
                buttons.data_button("🔗 DDL", f"userset {user_id} ddl")
        # Only show AI Settings button if AI is enabled
        if Config.AI_ENABLED:
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

        # Reset default upload if the selected service is disabled
        # Find first available service as fallback (only if mirror operations are enabled)
        fallback_upload = None
        if Config.MIRROR_ENABLED:
            if Config.GDRIVE_UPLOAD_ENABLED:
                fallback_upload = "gd"
            elif Config.RCLONE_ENABLED:
                fallback_upload = "rc"
            elif Config.YOUTUBE_UPLOAD_ENABLED:
                fallback_upload = "yt"
            elif Config.MEGA_ENABLED and Config.MEGA_UPLOAD_ENABLED:
                fallback_upload = "mg"
            elif Config.DDL_ENABLED:
                fallback_upload = "ddl"

        # Check if current default upload is available, if not reset to fallback
        reset_needed = False
        if not Config.MIRROR_ENABLED:
            # If mirror is disabled, reset to None (no upload service available)
            reset_needed = True
            fallback_upload = None
        elif (
            (default_upload == "gd" and not Config.GDRIVE_UPLOAD_ENABLED)
            or (default_upload == "rc" and not Config.RCLONE_ENABLED)
            or (default_upload == "yt" and not Config.YOUTUBE_UPLOAD_ENABLED)
            or (
                default_upload == "mg"
                and (not Config.MEGA_ENABLED or not Config.MEGA_UPLOAD_ENABLED)
            )
            or (default_upload == "ddl" and not Config.DDL_ENABLED)
        ):
            reset_needed = True

        if reset_needed and fallback_upload:
            default_upload = fallback_upload
            # Update the user's settings
            update_user_ldata(user_id, "DEFAULT_UPLOAD", fallback_upload)

        if default_upload == "gd":
            du = "Gdrive API"
        elif default_upload == "yt":
            du = "YouTube"
        elif default_upload == "mg":
            du = "MEGA"
        elif default_upload == "ddl":
            du = "DDL"
        else:
            du = "Rclone"

        # Show upload toggle buttons only if mirror operations are enabled
        available_uploads = []
        if Config.MIRROR_ENABLED:
            if Config.GDRIVE_UPLOAD_ENABLED:
                available_uploads.append(("gd", "Gdrive API"))
            if Config.RCLONE_ENABLED:
                available_uploads.append(("rc", "Rclone"))
            if Config.YOUTUBE_UPLOAD_ENABLED:
                available_uploads.append(("yt", "YouTube"))
            if Config.MEGA_ENABLED and Config.MEGA_UPLOAD_ENABLED:
                available_uploads.append(("mg", "MEGA"))
            if Config.DDL_ENABLED:
                available_uploads.append(("ddl", "DDL"))

        # Only show toggle if there are multiple upload options available
        if len(available_uploads) > 1:
            # Ensure default_upload is valid for current available services
            available_codes = [code for code, _ in available_uploads]
            if default_upload not in available_codes:
                # If current default is not available, reset to first available service
                default_upload = available_codes[0]
                update_user_ldata(user_id, "DEFAULT_UPLOAD", default_upload)

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
                f"userset {user_id} upload_toggle {next_code}",
            )

        user_tokens = user_dict.get("USER_TOKENS", False)
        tr = "MY" if user_tokens else "OWNER"
        trr = "OWNER" if user_tokens else "MY"

        # Show the token/config toggle only if mirror operations are enabled and any upload service is enabled
        if Config.MIRROR_ENABLED and (
            Config.GDRIVE_UPLOAD_ENABLED
            or Config.RCLONE_ENABLED
            or Config.YOUTUBE_UPLOAD_ENABLED
            or Config.DDL_ENABLED
            or (Config.MEGA_ENABLED and Config.MEGA_UPLOAD_ENABLED)
        ):
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

        # Universal Filename button
        universal_filename_msg = (
            "Added" if user_dict.get("UNIVERSAL_FILENAME", False) else "None"
        )
        buttons.data_button(
            "Filename",
            f"userset {user_id} menu UNIVERSAL_FILENAME",
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

        # Only show Gallery-dl button if Gallery-dl operations are enabled
        if Config.GALLERY_DL_ENABLED:
            buttons.data_button(
                "Gallery-dl",
                f"userset {user_id} gallerydl_main",
            )

        # Show User Cookies button if YT-DLP or Gallery-dl operations are enabled
        if Config.YTDLP_ENABLED or Config.GALLERY_DL_ENABLED:
            buttons.data_button(
                "User Cookies",
                f"userset {user_id} cookies_main",
            )
        # Count user cookies
        cookies_count = await count_user_cookies(user_id)
        cookies_status = f"{cookies_count} cookies" if cookies_count > 0 else "None"

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

        # Add BOT_PM toggle
        bot_pm_enabled = user_dict.get("BOT_PM", None)
        if bot_pm_enabled is None:
            bot_pm_enabled = Config.BOT_PM
            bot_pm_source = "Owner"
        else:
            bot_pm_source = "User"

        buttons.data_button(
            f"Bot PM: {'✅ ON' if bot_pm_enabled else '❌ OFF'}",
            f"userset {user_id} tog BOT_PM {'f' if bot_pm_enabled else 't'}",
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

        # Get BOT_PM status for display
        bot_pm_enabled = user_dict.get("BOT_PM", None)
        if bot_pm_enabled is None:
            bot_pm_enabled = Config.BOT_PM
            bot_pm_source = "Owner"
        else:
            bot_pm_source = "User"
        bot_pm_status = (
            f"{'Enabled' if bot_pm_enabled else 'Disabled'} (Set by {bot_pm_source})"
        )

        # Get DDL status for display
        ddl_status = ""
        if Config.DDL_ENABLED:
            # Check if user has DDL settings
            user_ddl_settings = any(
                key.startswith(
                    ("GOFILE_", "STREAMTAPE_", "DEVUPLOADS_", "MEDIAFIRE_", "DDL_")
                )
                for key in user_dict
            )
            if user_ddl_settings:
                ddl_status = "\n-> DDL Settings: <b>User configured</b>"
            else:
                ddl_status = "\n-> DDL Settings: <b>Using owner settings</b>"

        # Generate display text based on available services
        # Show default upload only if mirror operations are enabled and any upload service is available
        upload_services_available = Config.MIRROR_ENABLED and (
            Config.GDRIVE_UPLOAD_ENABLED
            or Config.RCLONE_ENABLED
            or Config.YOUTUBE_UPLOAD_ENABLED
            or Config.DDL_ENABLED
            or (Config.MEGA_ENABLED and Config.MEGA_UPLOAD_ENABLED)
        )

        # Show token/config status if any upload service is enabled
        token_config_line = ""
        if upload_services_available:
            token_config_line = f"\n-> Using <b>{tr}</b> Token/Config{ddl_status}"

        # Build the main text
        text = f"""<u><b>Settings for {name}</B></u>"""

        # Add default upload line only if upload services are available
        if upload_services_available:
            text += f"\n-> Default Upload: <b>{du}</b>"

        # Build dynamic text based on available services
        text_parts = []

        # Always show upload paths if upload services are available
        if upload_services_available:
            text_parts.append(
                f"-> Upload Paths: <code><b>{upload_paths}</b></code>{token_config_line}"
            )

        # Always show these settings regardless of upload services
        text_parts.extend(
            [
                f"-> Name Substitution: <code>{ns_msg}</code>",
                f"-> Universal Filename: <code>{universal_filename_msg}</code>",
                f"-> Excluded Extensions: <code>{ex_ex}</code>",
            ]
        )

        # Only show YT-DLP related settings if YT-DLP is enabled
        if Config.YTDLP_ENABLED:
            text_parts.append(f"-> YT-DLP Options: <code>{ytopt}</code>")

        # Only show Gallery-dl settings if Gallery-dl is enabled
        if Config.GALLERY_DL_ENABLED:
            # Get gallery-dl settings status
            gallery_dl_settings = any(
                key.startswith("GALLERY_DL_") and key != "GALLERY_DL_ENABLED"
                for key in user_dict
            )
            gallery_dl_status = (
                "User configured" if gallery_dl_settings else "Using owner settings"
            )
            text_parts.append(f"-> Gallery-dl Settings: <b>{gallery_dl_status}</b>")

        # Show cookies status if either YT-DLP or Gallery-dl is enabled
        if Config.YTDLP_ENABLED or Config.GALLERY_DL_ENABLED:
            text_parts.append(f"-> User Cookies: <b>{cookies_status}</b>")

        # Only show FFmpeg settings if media tools are enabled
        if is_media_tool_enabled("xtra"):
            text_parts.append(f"-> FFMPEG Commands: <code>{ffc}</code>")

        # Always show MediaInfo, BOT_PM, and Metadata
        text_parts.extend(
            [
                f"-> MediaInfo: <b>{mediainfo_status}</b>",
                f"-> Bot PM: <b>{bot_pm_status}</b>",
                f"-> Metadata Text: <code>{mdt}</code>{f' ({mdt_source})' if mdt != 'None' and mdt_source else ''}",
            ]
        )

        # Join all parts with newlines
        if text_parts:
            text += "\n" + "\n".join(text_parts)

        # Add service status information - only show if any services are disabled
        disabled_services = []
        if not Config.LEECH_ENABLED:
            disabled_services.append("Leech")
        if not Config.GDRIVE_UPLOAD_ENABLED:
            disabled_services.append("Gdrive Upload")
        if not Config.RCLONE_ENABLED:
            disabled_services.append("Rclone")
        if not Config.YOUTUBE_UPLOAD_ENABLED:
            disabled_services.append("YouTube Upload")
        if not Config.MEGA_ENABLED or not Config.MEGA_UPLOAD_ENABLED:
            disabled_services.append("MEGA Upload")
        if not Config.DDL_ENABLED:
            disabled_services.append("DDL Upload")
        if not Config.YTDLP_ENABLED:
            disabled_services.append("YT-DLP")
        if not Config.GALLERY_DL_ENABLED:
            disabled_services.append("Gallery-dl")

        if disabled_services:
            text += f"\n\n<i>Disabled services: {', '.join(disabled_services)}</i>"

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
            # Get next available cookie number
            cookie_num = await get_next_cookie_number(user_id)
            des_dir = f"{cpath}{user_id}_{cookie_num}.txt"
            await message.download(file_name=des_dir)

            # Also store in database
            try:
                # Read the cookie file content
                async with aiofiles.open(des_dir, "rb") as f:
                    cookie_data = await f.read()

                # Store in database
                await database.store_user_cookie(user_id, cookie_num, cookie_data)
                LOGGER.info(
                    f"Stored cookie #{cookie_num} for user {user_id} in database"
                )
            except Exception as e:
                LOGGER.error(
                    f"Error storing cookie #{cookie_num} in database for user {user_id}: {e}"
                )
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
                f"Set secure permissions for cookies file #{cookie_num} of user ID: {user_id}"
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

            # Count total cookies after upload
            total_cookies = await count_user_cookies(user_id)

            if has_youtube_auth:
                success_msg = await send_message(
                    message.chat.id,
                    f"✅ <b>Cookie #{cookie_num} uploaded successfully!</b>\n\n🍪 <b>Total Cookies:</b> {total_cookies}\n\n🔐 YouTube authentication cookies detected! Your cookies will be tried automatically during downloads.\n\n⚠️ <b>Security:</b> Only you can access your cookies.",
                )
            else:
                success_msg = await send_message(
                    message.chat.id,
                    f"✅ <b>Cookie #{cookie_num} uploaded successfully!</b>\n\n🍪 <b>Total Cookies:</b> {total_cookies}\n\n⚠️ No YouTube authentication cookies detected - may limit access to restricted content.\n\n🔒 <b>Security:</b> Only you can access your cookies.",
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

            # Calculate max split size based on owner's USER_TRANSMISSION setting (matches old Aeon-MLTB logic)
            # USER_TRANSMISSION is owner setting only, not user-specific
            # If owner has USER_TRANSMISSION enabled and premium session, use 4GB limit, otherwise 2GB
            max_split_size = (
                TgClient.MAX_SPLIT_SIZE
                if Config.USER_TRANSMISSION and TgClient.IS_PREMIUM_USER
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
            # Calculate max split size based on owner's USER_TRANSMISSION setting (matches old Aeon-MLTB logic)
            # USER_TRANSMISSION is owner setting only, not user-specific
            max_split_size = (
                TgClient.MAX_SPLIT_SIZE
                if Config.USER_TRANSMISSION and TgClient.IS_PREMIUM_USER
                else 2097152000
            )
            value = max_split_size
    elif option == "EXCLUDED_EXTENSIONS":
        fx = value.split()
        value = ["aria2", "!qB"]
        for x in fx:
            x = x.lstrip(".")
            value.append(x.strip().lower())
    elif option == "INDEX_URL":
        value = value.strip("/")
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
    elif option in [
        "GOFILE_API_KEY",
        "STREAMTAPE_API_PASSWORD",
        "STREAMTAPE_API_USERNAME",
        "DEVUPLOADS_API_KEY",
    ]:
        # Special handling for DDL credentials - store in regular user settings
        # This ensures compatibility with the display functions
        update_user_ldata(user_id, option, value)
        await delete_message(message)
        await database.update_user_data(user_id)
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
        # If rclone is disabled, go back to main menu
        back_to = "rclone" if Config.RCLONE_ENABLED else "back"
    elif option in gdrive_options:
        # If gdrive upload is disabled, go back to main menu
        back_to = "gdrive" if Config.GDRIVE_UPLOAD_ENABLED else "back"
    elif option in youtube_options:
        # If YouTube upload is disabled, go back to main menu
        back_to = "youtube" if Config.YOUTUBE_UPLOAD_ENABLED else "back"
    elif option in mega_options:
        # If MEGA or MEGA upload is disabled, go back to main menu
        back_to = (
            "mega"
            if (Config.MEGA_ENABLED and Config.MEGA_UPLOAD_ENABLED)
            else "back"
        )
    elif option in metadata_options:
        back_to = "metadata"
    # Convert options have been moved to Media Tools settings
    elif option in ai_options:
        back_to = "ai"
    elif option in yt_dlp_options:
        back_to = "back"  # Go back to main menu
    elif option in ddl_options:
        # Determine which DDL subsection to return to
        if option == "DDL_SERVER":
            back_to = "ddl_general"
        elif option.startswith("GOFILE_"):
            back_to = "ddl_gofile"
        elif option.startswith("STREAMTAPE_"):
            back_to = "ddl_streamtape"
        elif option.startswith("DEVUPLOADS_"):
            back_to = "ddl_devuploads"
        elif option.startswith("MEDIAFIRE_"):
            back_to = "ddl_mediafire"
        else:
            back_to = "ddl"
    elif option in ["NAME_SUBSTITUTE", "EXCLUDED_EXTENSIONS", "UNIVERSAL_FILENAME"]:
        back_to = "back"  # Go back to main menu for general options
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

    # Safely handle query.data splitting with error checking
    if not query.data:
        LOGGER.error(f"Empty query.data received from user {user_id}")
        await query.answer("Invalid request!", show_alert=True)
        return

    data = query.data.split()
    if len(data) < 2:
        LOGGER.error(f"Insufficient data in query from user {user_id}: {query.data}")
        await query.answer("Invalid request format!", show_alert=True)
        return

    handler_dict[user_id] = False
    thumb_path = f"thumbnails/{user_id}.jpg"
    rclone_conf = f"rclone/{user_id}.conf"
    token_pickle = f"tokens/{user_id}.pickle"
    user_dict = user_data.get(user_id, {})

    try:
        if user_id != int(data[1]):
            await query.answer("Not Yours!", show_alert=True)
            return
    except (ValueError, IndexError) as e:
        LOGGER.error(f"Error parsing user_id from query data {data}: {e}")
        await query.answer("Invalid user data!", show_alert=True)
        return
    # Ensure we have enough data elements for the operations
    if len(data) < 3:
        LOGGER.error(
            f"Insufficient data elements in query from user {user_id}: {query.data}"
        )
        await query.answer("Invalid request format!", show_alert=True)
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
        "cookies_main",
        "ddl",
        "ddl_general",
        "ddl_gofile",
        "ddl_streamtape",
        "ddl_devuploads",
        "ddl_mediafire",
        "gallerydl_main",
        "gallerydl_general",
        "gallerydl_auth",
    ]:
        await query.answer()
        # Redirect to main menu if trying to access disabled features
        if (
            (data[2] == "leech" and not Config.LEECH_ENABLED)
            or (data[2] == "gdrive" and not Config.GDRIVE_UPLOAD_ENABLED)
            or (data[2] == "rclone" and not Config.RCLONE_ENABLED)
            or (
                data[2] == "mega"
                and (not Config.MEGA_ENABLED or not Config.MEGA_UPLOAD_ENABLED)
            )
            or (
                data[2] in ["youtube", "youtube_basic", "youtube_advanced"]
                and not Config.YOUTUBE_UPLOAD_ENABLED
            )
            or (
                data[2]
                in [
                    "ddl",
                    "ddl_general",
                    "ddl_gofile",
                    "ddl_streamtape",
                    "ddl_devuploads",
                    "ddl_mediafire",
                ]
                and not Config.DDL_ENABLED
            )
            or (
                data[2] in ["gallerydl_main", "gallerydl_general", "gallerydl_auth"]
                and not Config.GALLERY_DL_ENABLED
            )
            or (
                data[2] == "cookies_main"
                and not (Config.YTDLP_ENABLED or Config.GALLERY_DL_ENABLED)
            )
        ):
            await update_user_settings(query, "main")
        else:
            await update_user_settings(query, data[2])
    elif data[2] == "cookies_add":
        await query.answer()
        buttons = ButtonMaker()
        text = "Send your cookies.txt file. The bot will automatically assign it a number and store it securely.\n\n⏰ Timeout: 60 seconds"
        buttons.data_button("Back", f"userset {user_id} cookies_main")
        buttons.data_button("Close", f"userset {user_id} close")
        await edit_message(message, text, buttons.build_menu(2))
        pfunc = partial(add_file, ftype="USER_COOKIES")
        await event_handler(client, query, pfunc, document=True)
        await update_user_settings(query, "cookies_main")
    elif data[2] == "cookies_help":
        await query.answer()
        buttons = ButtonMaker()
        text = """<b>🍪 User Cookies Help</b>

<b>What are cookies?</b>
Cookies allow you to access restricted content on YouTube, Instagram, Twitter, and other sites that require authentication.

<b>Supported Downloads:</b>
• YT-DLP downloads (YouTube, etc.)
• Gallery-dl downloads (Instagram, Twitter, DeviantArt, Pixiv, etc.)

<b>How to get cookies:</b>
1. Install browser extension "Get cookies.txt" or "EditThisCookie"
2. Login to the website in your browser (YouTube, Instagram, Twitter, etc.)
3. Use extension to export cookies as .txt file
4. Upload the file here

<b>Multiple Cookies:</b>
• Upload unlimited cookies for different sites
• Bot tries each cookie until one works
• Each cookie gets a unique number
• Only you can access your cookies

<b>Security:</b>
• Cookies are stored with restricted permissions
• Each user's cookies are completely isolated
• Files are automatically secured on upload"""
        buttons.data_button("Back", f"userset {user_id} cookies_main")
        buttons.data_button("Close", f"userset {user_id} close")
        await edit_message(message, text, buttons.build_menu(1))
    elif data[2] == "cookies_remove_all":
        await query.answer()
        buttons = ButtonMaker()
        cookies_count = await count_user_cookies(user_id)
        text = f"⚠️ <b>Remove All Cookies</b>\n\nAre you sure you want to remove all {cookies_count} cookies?\n\n<b>This action cannot be undone!</b>"
        buttons.data_button(
            "✅ Yes, Remove All", f"userset {user_id} cookies_confirm_remove_all"
        )
        buttons.data_button("❌ Cancel", f"userset {user_id} cookies_main")
        await edit_message(message, text, buttons.build_menu(1))
    elif data[2] == "cookies_confirm_remove_all":
        await query.answer()
        # Remove all user cookies from both database and filesystem
        from bot import LOGGER

        cookies_list = await get_user_cookies_list(user_id)
        removed_count = 0

        # Remove from filesystem
        for cookie in cookies_list:
            try:
                if await aiopath.exists(cookie["filepath"]):
                    await remove(cookie["filepath"])
                    removed_count += 1
            except Exception as e:
                LOGGER.error(f"Error removing cookie file {cookie['filename']}: {e}")

        # Remove from database
        try:
            db_removed = await database.delete_all_user_cookies(user_id)
            LOGGER.info(
                f"Removed {db_removed} cookies from database for user {user_id}"
            )
        except Exception as e:
            LOGGER.error(
                f"Error removing cookies from database for user {user_id}: {e}"
            )

        buttons = ButtonMaker()
        text = f"✅ <b>Removed {removed_count} cookies successfully!</b>"
        buttons.data_button("Back", f"userset {user_id} back")
        buttons.data_button("Close", f"userset {user_id} close")
        await edit_message(message, text, buttons.build_menu(2))
    elif data[2] == "cookies_manage":
        await query.answer()
        if len(data) <= 3:
            LOGGER.error(
                f"Missing cookie number in cookies_manage request from user {user_id}"
            )
            await query.answer("Invalid cookie management request!", show_alert=True)
            return

        cookie_num = data[3]
        cookie_path = f"cookies/{user_id}_{cookie_num}.txt"

        if not await aiopath.exists(cookie_path):
            buttons = ButtonMaker()
            text = f"❌ Cookie #{cookie_num} not found!"
            buttons.data_button("Back", f"userset {user_id} cookies_main")
            buttons.data_button("Close", f"userset {user_id} close")
            await edit_message(message, text, buttons.build_menu(2))
            return

        buttons = ButtonMaker()
        text = f"<b>🍪 Cookie #{cookie_num} Management</b>\n\nWhat would you like to do with this cookie?"
        buttons.data_button(
            "🗑️ Remove Cookie", f"userset {user_id} cookies_remove {cookie_num}"
        )
        buttons.data_button("Back", f"userset {user_id} cookies_main")
        buttons.data_button("Close", f"userset {user_id} close")
        await edit_message(message, text, buttons.build_menu(1))
    elif data[2] == "cookies_remove":
        await query.answer()
        if len(data) <= 3:
            LOGGER.error(
                f"Missing cookie number in cookies_remove request from user {user_id}"
            )
            await query.answer("Invalid cookie removal request!", show_alert=True)
            return

        cookie_num = data[3]
        cookie_path = f"cookies/{user_id}_{cookie_num}.txt"

        removed_file = False
        removed_db = False

        # Remove from filesystem
        from bot import LOGGER

        try:
            if await aiopath.exists(cookie_path):
                await remove(cookie_path)
                removed_file = True
                LOGGER.info(f"Removed cookie file #{cookie_num} for user {user_id}")
        except Exception as e:
            LOGGER.error(f"Error removing cookie file {cookie_path}: {e}")

        # Remove from database
        try:
            removed_db = await database.delete_user_cookie(user_id, int(cookie_num))
        except Exception as e:
            LOGGER.error(
                f"Error removing cookie #{cookie_num} from database for user {user_id}: {e}"
            )

        if removed_file or removed_db:
            text = f"✅ <b>Cookie #{cookie_num} removed successfully!</b>"
        else:
            text = f"❌ Cookie #{cookie_num} not found!"

        buttons = ButtonMaker()
        buttons.data_button("Back", f"userset {user_id} cookies_main")
        buttons.data_button("Close", f"userset {user_id} close")
        await edit_message(message, text, buttons.build_menu(2))
    elif data[2] == "menu":
        await query.answer()
        if len(data) <= 3:
            LOGGER.error(f"Missing menu option in request from user {user_id}")
            await query.answer("Invalid menu request!", show_alert=True)
            return
        await get_menu(data[3], message, user_id)
    elif data[2] == "tog":
        await query.answer()
        if len(data) <= 4:
            LOGGER.error(f"Missing toggle parameters in request from user {user_id}")
            await query.answer("Invalid toggle request!", show_alert=True)
            return
        update_user_ldata(user_id, data[3], data[4] == "t")
        if data[3] == "STOP_DUPLICATE":
            back_to = "gdrive"
        elif data[3] in ["USER_TOKENS", "MEDIAINFO_ENABLED", "BOT_PM"]:
            back_to = "main"
        elif data[3] in [
            "MEGA_UPLOAD_PUBLIC",
            # "MEGA_UPLOAD_PRIVATE" removed - not supported by MEGA SDK v4.8.0
            # "MEGA_UPLOAD_UNLISTED" removed - not supported by MEGA SDK v4.8.0
            "MEGA_UPLOAD_THUMBNAIL",
            # "MEGA_UPLOAD_DELETE_AFTER" removed - always delete after upload
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
        elif data[3] in [
            "GOFILE_PUBLIC_LINKS",
            "GOFILE_PASSWORD_PROTECTION",
        ]:
            back_to = "ddl_gofile"
        # Convert settings have been moved to Media Tools settings
        else:
            back_to = "leech"
        await update_user_settings(query, stype=back_to)
        await database.update_user_data(user_id)
    elif data[2] == "help":
        await query.answer()
        if len(data) <= 3:
            LOGGER.error(f"Missing help topic in request from user {user_id}")
            await query.answer("Invalid help request!", show_alert=True)
            return
        buttons = ButtonMaker()
        if data[3] == "USER_COOKIES":
            text = """<b>User Cookies Help</b>

You can provide your own cookies for YT-DLP and Gallery-dl downloads to access restricted content.

<b>Supported Downloads:</b>
• YT-DLP: YouTube, Twitch, and 1000+ sites
• Gallery-dl: Instagram, Twitter, DeviantArt, Pixiv, Reddit, and 200+ platforms

<b>How to create a cookies.txt file:</b>
1. Install a browser extension like 'Get cookies.txt' or 'EditThisCookie'
2. Log in to the website (YouTube, Instagram, Twitter, etc.) where you want to use your cookies
3. Use the extension to export cookies as a cookies.txt file
4. Upload that file here

<b>Benefits:</b>
- Access age-restricted content
- Fix 'Sign in to confirm you're not a bot' errors
- Access subscriber-only content
- Download private videos/posts (if you have access)
- Access platform-specific content (Instagram stories, Twitter media, etc.)

<b>Note:</b> Your cookies are stored securely and only used for your downloads. The bot owner cannot access your account."""
        buttons.data_button("Back", f"userset {user_id} menu {data[3]}")
        buttons.data_button("Close", f"userset {user_id} close")
        await edit_message(message, text, buttons.build_menu(2))
    elif data[2] == "file":
        await query.answer()
        if len(data) <= 3:
            LOGGER.error(f"Missing file type in request from user {user_id}")
            await query.answer("Invalid file request!", show_alert=True)
            return
        buttons = ButtonMaker()
        if data[3] == "THUMBNAIL":
            text = "Send a photo to save it as custom thumbnail. Timeout: 60 sec"
        elif data[3] == "RCLONE_CONFIG":
            text = "Send rclone.conf. Timeout: 60 sec"
        elif data[3] == "USER_COOKIES":
            text = "Send your cookies.txt file for YT-DLP and Gallery-dl downloads (YouTube, Instagram, Twitter, etc.). Create it using browser extensions like 'Get cookies.txt' or 'EditThisCookie'. Timeout: 60 sec"
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
        if len(data) <= 3:
            LOGGER.error(
                f"Missing provider in setprovider request from user {user_id}"
            )
            await query.answer("Invalid provider request!", show_alert=True)
            return
        await query.answer(f"Setting default AI provider to {data[3].capitalize()}")
        # Update the default AI provider in user settings
        user_dict["DEFAULT_AI_PROVIDER"] = data[3]
        # Update the database
        await database.update_user_data(user_id)
        # Update the UI
        await update_user_settings(query, "ai")
    elif data[2] == "var":
        await query.answer()
        if len(data) <= 3:
            LOGGER.error(f"Missing variable name in var request from user {user_id}")
            await query.answer("Invalid variable request!", show_alert=True)
            return
        buttons = ButtonMaker()
        if data[3] in user_settings_text:
            text = user_settings_text[data[3]]
            func = set_option

            # Determine the correct back destination based on the option
            if data[3] in mega_options:
                back_to = (
                    "mega"
                    if (Config.MEGA_ENABLED and Config.MEGA_UPLOAD_ENABLED)
                    else "back"
                )
            elif data[3] in youtube_options:
                back_to = "youtube" if Config.YOUTUBE_UPLOAD_ENABLED else "back"
            elif data[3] in leech_options:
                back_to = "leech" if Config.LEECH_ENABLED else "back"
            elif data[3] in gdrive_options:
                back_to = "gdrive" if Config.GDRIVE_UPLOAD_ENABLED else "back"
            elif data[3] in rclone_options:
                back_to = "rclone" if Config.RCLONE_ENABLED else "back"
            elif data[3] in metadata_options:
                back_to = "metadata"
            elif data[3] in ai_options:
                back_to = "ai"
            elif data[3] in ddl_options:
                # Determine which DDL subsection to return to (only if DDL is enabled)
                if Config.DDL_ENABLED:
                    if data[3] == "DDL_SERVER":
                        back_to = "ddl_general"
                    elif data[3].startswith("GOFILE_"):
                        back_to = "ddl_gofile"
                    elif data[3].startswith("STREAMTAPE_"):
                        back_to = "ddl_streamtape"
                    elif data[3].startswith("DEVUPLOADS_"):
                        back_to = "ddl_devuploads"
                    elif data[3].startswith("MEDIAFIRE_"):
                        back_to = "ddl_mediafire"
                    else:
                        back_to = "ddl"
                else:
                    back_to = "back"
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
        if len(data) <= 3:
            LOGGER.error(
                f"Missing option name in {data[2]} request from user {user_id}"
            )
            await query.answer("Invalid request format!", show_alert=True)
            return
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
        if len(data) <= 3:
            LOGGER.error(
                f"Missing option name in remove request from user {user_id}"
            )
            await query.answer("Invalid remove request!", show_alert=True)
            return
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
                # Remove all user cookies from both database and filesystem
                from bot import LOGGER

                cookies_list = await get_user_cookies_list(user_id)
                for cookie in cookies_list:
                    try:
                        if await aiopath.exists(cookie["filepath"]):
                            await remove(cookie["filepath"])
                    except Exception as e:
                        LOGGER.error(
                            f"Error removing cookie file {cookie['filename']}: {e}"
                        )

                # Also remove from database
                try:
                    await database.delete_all_user_cookies(user_id)
                    LOGGER.info(
                        f"Removed all cookies from database for user {user_id}"
                    )
                except Exception as e:
                    LOGGER.error(
                        f"Error removing cookies from database for user {user_id}: {e}"
                    )

                fpath = None  # Set to None since we handled removal above
            elif data[3] == "YOUTUBE_TOKEN_PICKLE":
                fpath = f"tokens/{user_id}_youtube.pickle"
            else:
                fpath = token_pickle
            if fpath and await aiopath.exists(fpath):
                await remove(fpath)
            user_dict.pop(data[3], None)
            await database.update_user_doc(user_id, data[3])
        else:
            update_user_ldata(user_id, data[3], "")
            await database.update_user_data(user_id)
    elif data[2] == "reset":
        await query.answer("Reseted!", show_alert=True)
        if len(data) <= 3:
            LOGGER.error(f"Missing option name in reset request from user {user_id}")
            await query.answer("Invalid reset request!", show_alert=True)
            return
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
        if len(data) <= 3:
            LOGGER.error(f"Missing option name in view request from user {user_id}")
            await query.answer("Invalid view request!", show_alert=True)
            return
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
    elif data[2] == "upload_toggle" and len(data) > 3:
        await query.answer()
        # Cycle through available upload options only if mirror operations are enabled
        available_uploads = []
        if Config.MIRROR_ENABLED:
            if Config.GDRIVE_UPLOAD_ENABLED:
                available_uploads.append(("gd", "Gdrive API"))
            if Config.RCLONE_ENABLED:
                available_uploads.append(("rc", "Rclone"))
            if Config.YOUTUBE_UPLOAD_ENABLED:
                available_uploads.append(("yt", "YouTube"))
            if Config.MEGA_ENABLED and Config.MEGA_UPLOAD_ENABLED:
                available_uploads.append(("mg", "MEGA"))
            if Config.DDL_ENABLED:
                available_uploads.append(("ddl", "DDL"))

        # Only proceed if there are multiple upload options available
        if len(available_uploads) <= 1:
            # If no services or only one service available, don't allow toggle
            await update_user_settings(query)
            return

        # The clicked service is what the user wants to set as their new default
        clicked_service = data[3]

        # Ensure clicked_service is valid for current available services
        available_codes = [code for code, _ in available_uploads]
        if clicked_service not in available_codes:
            # If clicked service is not available, use first available service
            clicked_service = available_codes[0] if available_codes else "gd"

        update_user_ldata(user_id, "DEFAULT_UPLOAD", clicked_service)

        # Force refresh the user settings to ensure button updates properly
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
