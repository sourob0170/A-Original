from pyrogram import filters
from pyrogram.filters import command, regex
from pyrogram.handlers import (
    CallbackQueryHandler,
    EditedMessageHandler,
    MessageHandler,
)

from bot.core.config_manager import Config
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.filters import CustomFilters
from bot.modules import (
    add_sudo,
    aeon_callback,
    aioexecute,
    arg_usage,
    ask_ai,
    authorize,
    bot_help,
    bot_stats,
    cancel,
    cancel_all_buttons,
    cancel_all_update,
    cancel_multi,
    check_scheduled_deletions,
    clear,
    clone_node,
    confirm_restart,
    confirm_selection,
    count_node,
    delete_file,
    delete_pending_messages,
    edit_bot_settings,
    edit_media_tools_settings,
    edit_user_settings,
    execute,
    font_styles_cmd,
    force_delete_all_messages,
    gdrive_search,
    gen_session,
    get_rss_menu,
    get_users_settings,
    handle_broadcast_command,
    handle_broadcast_media,
    handle_cancel_broadcast_command,
    handle_cancel_button,
    handle_cancel_command,
    handle_command,
    handle_group_gensession,
    handle_no_suffix_commands,
    handle_qb_commands,
    handle_session_input,
    hydra_search,
    imdb_callback,
    imdb_search,
    jd_leech,
    jd_mirror,
    leech,
    log,
    login,
    media_cancel_callback,
    media_get_callback,
    media_search,
    media_tools_help_cmd,
    media_tools_settings,
    mediainfo,
    mirror,
    nzb_leech,
    nzb_mirror,
    paste_text,
    ping,
    remove_from_queue,
    remove_sudo,
    restart_bot,
    rss_listener,
    run_shell,
    select,
    select_type,
    send_bot_settings,
    send_user_settings,
    spectrum_handler,
    speedtest,
    start,
    status_pages,
    task_status,
    torrent_search,
    torrent_search_update,
    truecaller_lookup,
    unauthorize,
    virustotal_scan,
    ytdl,
    ytdl_leech,
)
from bot.modules.font_styles import font_styles_callback
from bot.modules.media_tools_help import media_tools_help_callback

from .aeon_client import TgClient


def add_handlers():
    command_filters = {
        "authorize": (
            authorize,
            BotCommands.AuthorizeCommand,
            CustomFilters.sudo,
        ),
        "unauthorize": (
            unauthorize,
            BotCommands.UnAuthorizeCommand,
            CustomFilters.sudo,
        ),
        "add_sudo": (
            add_sudo,
            BotCommands.AddSudoCommand,
            CustomFilters.sudo,
        ),
        "remove_sudo": (
            remove_sudo,
            BotCommands.RmSudoCommand,
            CustomFilters.sudo,
        ),
        "send_bot_settings": (
            send_bot_settings,
            BotCommands.BotSetCommand,
            CustomFilters.sudo,
        ),
        "cancel_all_buttons": (
            cancel_all_buttons,
            BotCommands.CancelAllCommand,
            CustomFilters.authorized,
        ),
        "clone_node": (
            clone_node,
            BotCommands.CloneCommand,
            CustomFilters.authorized,
        ),
        "aioexecute": (
            aioexecute,
            BotCommands.AExecCommand,
            CustomFilters.sudo,
        ),
        "execute": (
            execute,
            BotCommands.ExecCommand,
            CustomFilters.sudo,
        ),
        "clear": (
            clear,
            BotCommands.ClearLocalsCommand,
            CustomFilters.sudo,
        ),
        "select": (
            select,
            BotCommands.SelectCommand,
            CustomFilters.authorized,
        ),
        "remove_from_queue": (
            remove_from_queue,
            BotCommands.ForceStartCommand,
            CustomFilters.authorized,
        ),
        "count_node": (
            count_node,
            BotCommands.CountCommand,
            CustomFilters.authorized,
        ),
        "delete_file": (
            delete_file,
            BotCommands.DeleteCommand,
            CustomFilters.authorized,
        ),
        "gdrive_search": (
            gdrive_search,
            BotCommands.ListCommand,
            CustomFilters.authorized,
        ),
        "mirror": (
            mirror,
            BotCommands.MirrorCommand,
            CustomFilters.authorized,
        ),
        "jd_mirror": (
            jd_mirror,
            BotCommands.JdMirrorCommand,
            CustomFilters.authorized,
        ),
        "leech": (
            leech,
            BotCommands.LeechCommand,
            CustomFilters.authorized,
        ),
        "jd_leech": (
            jd_leech,
            BotCommands.JdLeechCommand,
            CustomFilters.authorized,
        ),
        "get_rss_menu": (
            get_rss_menu,
            BotCommands.RssCommand,
            CustomFilters.owner,
        ),
        "run_shell": (
            run_shell,
            BotCommands.ShellCommand,
            CustomFilters.owner,
        ),
        "start": (
            start,
            BotCommands.StartCommand,
            None,
        ),
        "log": (
            log,
            BotCommands.LogCommand,
            CustomFilters.sudo,
        ),
        "restart_bot": (
            restart_bot,
            BotCommands.RestartCommand,
            CustomFilters.sudo,
        ),
        "ping": (
            ping,
            BotCommands.PingCommand,
            CustomFilters.authorized,
        ),
        "bot_help": (
            bot_help,
            BotCommands.HelpCommand,
            CustomFilters.authorized,
        ),
        "bot_stats": (
            bot_stats,
            BotCommands.StatsCommand,
            CustomFilters.authorized,
        ),
        "check_scheduled_deletions": (
            check_scheduled_deletions,
            BotCommands.CheckDeletionsCommand,
            CustomFilters.sudo,
        ),
        "task_status": (
            task_status,
            BotCommands.StatusCommand,
            CustomFilters.authorized,
        ),
        "s": (
            task_status,
            BotCommands.StatusCommand,
            CustomFilters.authorized,
        ),
        "statusall": (
            task_status,
            BotCommands.StatusCommand,
            CustomFilters.authorized,
        ),
        "sall": (
            task_status,
            BotCommands.StatusCommand,
            CustomFilters.authorized,
        ),
        "torrent_search": (
            torrent_search,
            BotCommands.SearchCommand,
            CustomFilters.authorized,
        ),
        "get_users_settings": (
            get_users_settings,
            BotCommands.UsersCommand,
            CustomFilters.sudo,
        ),
        "ytdl": (
            ytdl,
            BotCommands.YtdlCommand,
            CustomFilters.authorized,
        ),
        "ytdl_leech": (
            ytdl_leech,
            BotCommands.YtdlLeechCommand,
            CustomFilters.authorized,
        ),
        "mediainfo": (
            mediainfo,
            BotCommands.MediaInfoCommand,
            CustomFilters.authorized,
        ),
        "speedtest": (
            speedtest,
            BotCommands.SpeedTest,
            CustomFilters.authorized,
        ),
        "broadcast": (
            handle_broadcast_command,
            BotCommands.BroadcastCommand,
            CustomFilters.owner,
        ),
        "nzb_mirror": (
            nzb_mirror,
            BotCommands.NzbMirrorCommand,
            CustomFilters.authorized,
        ),
        "nzb_leech": (
            nzb_leech,
            BotCommands.NzbLeechCommand,
            CustomFilters.authorized,
        ),
        "hydra_search": (
            hydra_search,
            BotCommands.HydraSearchCommamd,
            CustomFilters.authorized,
        ),
        "spectrum_handler": (
            spectrum_handler,
            BotCommands.SoxCommand,
            CustomFilters.authorized,
        ),
        # font_styles_cmd entry removed - now handled by direct handler registration
        "imdb_search": (
            imdb_search,
            BotCommands.IMDBCommand,
            CustomFilters.authorized,
        ),
        "login": (
            login,
            BotCommands.LoginCommand,
            None,
        ),
        "media_search": (
            media_search,
            BotCommands.MediaSearchCommand,
            CustomFilters.authorized,
        ),
        # media_tools_settings and media_tools_help_cmd entries removed - now handled by direct handler registration
        "gen_session": (
            handle_command,
            BotCommands.GenSessionCommand,
            filters.private,  # Only allow in private chats
        ),
        # user_settings entry removed - now handled by direct handler registration
        "truecaller_lookup": (
            truecaller_lookup,
            BotCommands.TruecallerCommand,
            CustomFilters.authorized,
        ),
        "ask_ai": (
            ask_ai,
            BotCommands.AskCommand,
            CustomFilters.authorized,
        ),
        "paste": (
            paste_text,
            BotCommands.PasteCommand,
            CustomFilters.authorized,
        ),
        "virustotal": (
            virustotal_scan,
            BotCommands.VirusTotalCommand,
            CustomFilters.authorized,
        ),
    }

    # Add streamrip handlers if streamrip is enabled
    if Config.STREAMRIP_ENABLED:
        from bot.modules.streamrip import (
            streamrip_leech,
            streamrip_mirror,
            streamrip_search,
        )

        streamrip_handlers = {
            "streamrip_mirror": (
                streamrip_mirror,
                BotCommands.StreamripMirrorCommand,
                CustomFilters.authorized,
            ),
            "streamrip_leech": (
                streamrip_leech,
                BotCommands.StreamripLeechCommand,
                CustomFilters.authorized,
            ),
            "streamrip_search": (
                streamrip_search,
                BotCommands.StreamripSearchCommand,
                CustomFilters.authorized,
            ),
        }

        # Add streamrip handlers to command_filters
        command_filters.update(streamrip_handlers)

    # Add zotify handlers if zotify is enabled
    if Config.ZOTIFY_ENABLED:
        from bot.modules.zotify import (
            zotify_leech,
            zotify_mirror,
            zotify_search,
        )

        zotify_handlers = {
            "zotify_mirror": (
                zotify_mirror,
                BotCommands.ZotifyMirrorCommand,
                CustomFilters.authorized,
            ),
            "zotify_leech": (
                zotify_leech,
                BotCommands.ZotifyLeechCommand,
                CustomFilters.authorized,
            ),
            "zotify_search": (
                zotify_search,
                BotCommands.ZotifySearchCommand,
                CustomFilters.authorized,
            ),
        }

        # Add zotify handlers to command_filters
        command_filters.update(zotify_handlers)

    # Add MEGA handlers if MEGA is enabled
    if Config.MEGA_ENABLED:
        from bot.modules.mega_search import mega_search_command
        from bot.modules.megaclone import mega_clone

        mega_handlers = {
            "mega_clone": (
                mega_clone,
                BotCommands.MegaCloneCommand,
                CustomFilters.authorized,
            ),
            "mega_search": (
                mega_search_command,
                BotCommands.MegaSearchCommand,
                CustomFilters.authorized,
            ),
        }

        # Add MEGA handlers to command_filters
        command_filters.update(mega_handlers)

    for handler_func, command_name, custom_filter in command_filters.values():
        if custom_filter:
            filters_to_apply = (
                command(command_name, case_sensitive=True) & custom_filter
            )
        else:
            filters_to_apply = command(command_name, case_sensitive=True)

        TgClient.bot.add_handler(
            MessageHandler(
                handler_func,
                filters=filters_to_apply,
            ),
            group=0,
        )

    # Define callback handlers that need authorization
    auth_regex_filters = {
        "^botset": edit_bot_settings,
        "^canall": cancel_all_update,
        "^stopm": cancel_multi,
        "^sel": confirm_selection,
        "^list_types": select_type,
        "^rss": rss_listener,
        "^torser": torrent_search_update,
        "^help": arg_usage,
        "^status": status_pages,
        "^botrestart": confirm_restart,
        "^aeon": aeon_callback,
        "^imdb": imdb_callback,
        "^medget": media_get_callback,
        "^medcancel": media_cancel_callback,
        "^gensession$": gen_session,
        "delete_pending": delete_pending_messages,
        "force_delete_all": force_delete_all_messages,
    }

    # Define callback handlers that don't need authorization (accessible to all users)
    public_regex_filters = {
        "^userset": edit_user_settings,
        "^mediatools": edit_media_tools_settings,
        "^fontstyles": font_styles_callback,
        "^mthelp": media_tools_help_callback,
        "^gensession_cancel$": handle_cancel_button,
    }

    # Add Zotify quality selector callback handler if enabled
    if Config.ZOTIFY_ENABLED:
        from bot.helper.zotify_utils.quality_selector import (
            ZotifyQualitySelector,
            get_active_zotify_quality_selector,
        )

        async def handle_zotify_quality_callback(client, query):
            """Handle Zotify quality selector callbacks"""
            user_id = query.from_user.id
            selector = get_active_zotify_quality_selector(user_id)
            if selector:
                await ZotifyQualitySelector._handle_callback(client, query, selector)

        public_regex_filters["^zq"] = handle_zotify_quality_callback

    # Add MEGA callback handlers if enabled
    if Config.MEGA_ENABLED:
        from bot.helper.mega_utils.folder_selector import mega_folder_callback

        # MEGA search now uses Telegraph (no pagination callbacks needed)
        public_regex_filters["^mgq"] = mega_folder_callback

    # Add handlers for callbacks that don't need authorization (accessible to all users)
    # These have higher priority (group=-1) to ensure they're processed first
    for regex_filter, handler_func in public_regex_filters.items():
        TgClient.bot.add_handler(
            CallbackQueryHandler(handler_func, filters=regex(regex_filter)),
            group=-1,  # Higher priority than authorized callbacks
        )

    # Add handlers for callbacks that need authorization
    # These have normal priority (group=0)
    for regex_filter, handler_func in auth_regex_filters.items():
        TgClient.bot.add_handler(
            CallbackQueryHandler(
                handler_func, filters=regex(regex_filter) & CustomFilters.authorized
            ),
            group=0,
        )

    TgClient.bot.add_handler(
        EditedMessageHandler(
            run_shell,
            filters=command(BotCommands.ShellCommand, case_sensitive=True)
            & CustomFilters.owner,
        ),
        group=0,
    )
    TgClient.bot.add_handler(
        MessageHandler(
            cancel,
            filters=regex(r"^/stop(_\w+)?(?!all)") & CustomFilters.authorized,
        ),
        group=0,
    )

    # Add handler for deprecated commands (qbleech, qbmirror) with any suffix
    TgClient.bot.add_handler(
        MessageHandler(
            handle_qb_commands,
            filters=regex(r"^/qb(leech|mirror)(\d+|[a-zA-Z0-9_]+)?")
            & CustomFilters.authorized,
        ),
        group=0,
    )

    # Add handler for all command variants (with or without suffix)
    TgClient.bot.add_handler(
        MessageHandler(
            handle_no_suffix_commands,
            filters=regex(
                r"^/(mirror|m|leech|l|jdmirror|jm|jdleech|jl|nzbmirror|nm|nzbleech|nl|ytdl|y|ytdlleech|yl|streamripmirror|srmirror|srm|streamripleech|srleech|srl|streamripsearch|srsearch|srs|streamripquality|srquality|zotifymirror|zmirror|zm|zotifyleech|zleech|zl|zotifysearch|zsearch|zs|clone|count|del|cancelall|forcestart|fs|list|search|nzbsearch|status|s|statusall|sall|users|auth|unauth|addsudo|rmsudo|ping|restart|restartall|stats|help|log|shell|aexec|exec|clearlocals|botsettings|speedtest|broadcast|broadcastall|sel|rss|check_deletions|cd|imdb|login|mediasearch|mds|truecaller|ask|mediainfo|mi|spectrum|sox|paste|virustotal)([a-zA-Z0-9_]*)($| )"
            )
            & CustomFilters.pm_or_authorized,
        ),
        group=0,
    )

    # Add a handler for /gensession in groups to guide users to PM
    TgClient.bot.add_handler(
        MessageHandler(
            handle_group_gensession,
            filters=command(BotCommands.GenSessionCommand, case_sensitive=True)
            & filters.group,
        ),
        group=0,
    )

    # Add handlers for special commands that should work in both private chats and groups
    # These handlers will be called before the handle_no_suffix_commands handler
    # Using group=-1 to ensure they are processed before other handlers in group 0

    # User Settings command
    TgClient.bot.add_handler(
        MessageHandler(
            send_user_settings,
            filters=command(BotCommands.UserSetCommand, case_sensitive=True),
        ),
        group=-1,  # Higher priority than regular handlers
    )

    # Media Tools command
    TgClient.bot.add_handler(
        MessageHandler(
            media_tools_settings,
            filters=command(BotCommands.MediaToolsCommand, case_sensitive=True),
        ),
        group=-1,  # Higher priority than regular handlers
    )

    # Media Tools Help command
    TgClient.bot.add_handler(
        MessageHandler(
            media_tools_help_cmd,
            filters=command(BotCommands.MediaToolsHelpCommand, case_sensitive=True),
        ),
        group=-1,  # Higher priority than regular handlers
    )

    # Font Styles command
    TgClient.bot.add_handler(
        MessageHandler(
            font_styles_cmd,
            filters=command(BotCommands.FontStylesCommand, case_sensitive=True),
        ),
        group=-1,  # Higher priority than regular handlers
    )

    # Add a handler for /cancel command in private chats
    TgClient.bot.add_handler(
        MessageHandler(
            handle_cancel_command,
            filters=command("cancel", case_sensitive=False) & filters.private,
        ),
        group=0,
    )

    # Add a handler for /cancelbc command for broadcast cancellation
    TgClient.bot.add_handler(
        MessageHandler(
            # Use our dedicated cancel function
            handle_cancel_broadcast_command,
            filters=command("cancelbc", case_sensitive=False)
            & filters.private
            & filters.create(
                lambda _, __, m: m.from_user and m.from_user.id == Config.OWNER_ID
                # We don't check broadcast_awaiting_message here to allow cancellation
                # even if the state tracking has issues
            ),
        ),
        group=4,  # Use a specific group number for this handler
    )

    # Add handler for broadcast media (second step) - text messages
    TgClient.bot.add_handler(
        MessageHandler(
            # Use our dedicated media handler function (works for text too)
            handle_broadcast_media,
            filters=filters.private
            & filters.text
            & filters.create(
                lambda _, __, m: (
                    # Must be from owner
                    m.from_user
                    and m.from_user.id == Config.OWNER_ID
                    # Exclude commands
                    and not (
                        hasattr(m, "text") and m.text and m.text.startswith("/")
                    )
                )
                # We'll check broadcast_awaiting_message inside the handler
            ),
        ),
        group=5,  # Use a higher group number to ensure it's processed after command handlers
    )

    # Add handler for broadcast media (second step) - media messages
    TgClient.bot.add_handler(
        MessageHandler(
            # Use our dedicated media handler function
            handle_broadcast_media,
            filters=filters.private
            & (
                filters.photo
                | filters.video
                | filters.document
                | filters.audio
                | filters.voice
                | filters.sticker
                | filters.animation
            )
            & filters.create(
                lambda _, __, m: (
                    # Must be from owner
                    m.from_user and m.from_user.id == Config.OWNER_ID
                )
                # We'll check broadcast_awaiting_message inside the handler
            ),
        ),
        group=3,  # Use a lower group number to ensure it's processed before other handlers
    )

    # Define a custom filter for non-command messages
    def session_input_filter(*args):
        # Extract update from args (args[2])
        update = args[2]
        if update.text:
            # Filter out all commands
            for prefix in ["/", "!", "."]:
                if update.text.startswith(prefix):
                    return False
        return True

    # Add a persistent handler for session generation input
    TgClient.bot.add_handler(
        MessageHandler(
            handle_session_input,
            # Use a filter that allows normal messages but filters out commands
            filters=filters.private
            & filters.incoming
            & filters.create(session_input_filter),
        ),
        group=1,  # Higher priority group
    )

    # Import and initialize the media search module
    from bot.modules.media_search import init_media_search

    # Initialize media search module (this will register handlers except inline query)
    init_media_search(TgClient.bot)

    # Initialize unified inline search handler that supports both media and streamrip
    from bot.helper.inline_search_router import init_unified_inline_search

    init_unified_inline_search(TgClient.bot)

    # Initialize ad broadcaster module
    from bot.modules.ad_broadcaster import init_ad_broadcaster

    init_ad_broadcaster()
