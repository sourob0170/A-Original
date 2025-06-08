# ruff: noqa: RUF012
from bot.core.config_manager import Config

i = Config.CMD_SUFFIX


class BotCommands:
    LeechCommand = [f"leech{i}", f"l{i}"]
    MirrorCommand = [f"mirror{i}", f"m{i}"]
    UserSetCommand = [f"settings{i}", f"usettings{i}", f"us{i}"]
    MegaCloneCommand = [f"megaclone{i}", f"mc{i}"]
    MegaSearchCommand = [f"megasearch{i}", f"mgs{i}"]
    
    StartCommand = "start"
    HelpCommand = f"help{i}"
    PingCommand = f"ping{i}"
    StatusCommand = [f"status{i}", f"s{i}", "statusall", "sall"]
    StatsCommand = f"stats{i}"
    LogCommand = f"log{i}"
    SpeedTest = f"speedtest{i}"
    RestartCommand = [f"restart{i}", "restartall"]
    CancelAllCommand = f"cancelall{i}"
    ClearLocalsCommand = f"clearlocals{i}"
    UsersCommand = f"users{i}"
    AuthorizeCommand = f"auth{i}"
    UnAuthorizeCommand = f"unauth{i}"
    AddSudoCommand = f"addsudo{i}"
    RmSudoCommand = f"rmsudo{i}"
    ForceStartCommand = [f"forcestart{i}", f"fs{i}"]
    BroadcastCommand = [f"broadcast{i}", "broadcastall"]
    BotSetCommand = f"botsettings{i}"
    JdMirrorCommand = [f"jdmirror{i}", f"jm{i}"]
    JdLeechCommand = [f"jdleech{i}", f"jl{i}"]
    NzbMirrorCommand = [f"nzbmirror{i}", f"nm{i}"]
    NzbLeechCommand = [f"nzbleech{i}", f"nl{i}"]
    YtdlCommand = [f"ytdl{i}", f"y{i}"]
    YtdlLeechCommand = [f"ytdlleech{i}", f"yl{i}"]
    CloneCommand = f"clone{i}"
    StreamripMirrorCommand = [f"streamripmirror{i}", f"srmirror{i}", f"srm{i}"]
    StreamripLeechCommand = [f"streamripleech{i}", f"srleech{i}", f"srl{i}"]
    StreamripSearchCommand = [f"streamripsearch{i}", f"srsearch{i}", f"srs{i}"]
    ZotifyMirrorCommand = [f"zotifymirror{i}", f"zmirror{i}", f"zm{i}"]
    ZotifyLeechCommand = [f"zotifyleech{i}", f"zleech{i}", f"zl{i}"]
    ZotifySearchCommand = [f"zotifysearch{i}", f"zsearch{i}", f"zs{i}"]
    SearchCommand = f"search{i}"
    HydraSearchCommamd = f"nzbsearch{i}"
    IMDBCommand = f"imdb{i}"
    MediaInfoCommand = [f"mediainfo{i}", f"mi{i}"]
    MediaSearchCommand = [f"mediasearch{i}", f"mds{i}"]
    RssCommand = f"rss{i}"
    CheckDeletionsCommand = [f"check_deletions{i}", f"cd{i}"]
    MediaToolsCommand = [f"mediatools{i}", f"mt{i}"]
    MediaToolsHelpCommand = [f"mthelp{i}", f"mth{i}"]
    FontStylesCommand = [f"fontstyles{i}", f"fonts{i}"]
    SoxCommand = [f"spectrum{i}", f"sox{i}"]
    ExecCommand = f"exec{i}"
    AExecCommand = f"aexec{i}"
    ShellCommand = f"shell{i}"
    DeleteCommand = f"del{i}"
    CountCommand = f"count{i}"
    SelectCommand = f"sel{i}"
    PasteCommand = f"paste{i}"
    VirusTotalCommand = f"virustotal{i}"
    TruecallerCommand = f"truecaller{i}"
    AskCommand = f"ask{i}"
    GenSessionCommand = [f"gensession{i}", f"gs{i}"]
    LoginCommand = f"login{i}"
