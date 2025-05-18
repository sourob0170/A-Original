**1. Required Fields**

- `BOT_TOKEN` (`Str`):  The Telegram Bot Token that you got from [@BotFather](https://t.me/BotFather).

- `OWNER_ID` (`Int`):  The Telegram User ID (not username) of the Owner of the bot.

- `TELEGRAM_API` (`Int`): This is to authenticate your Telegram account for downloading Telegram files. You can get this
  from <https://my.telegram.org>.

- `TELEGRAM_HASH` (`Str`):  This is to authenticate your Telegram account for downloading Telegram files. You can get this
  from <https://my.telegram.org>.

**2. Optional Fields**
- `TG_PROXY` (`Dict`): The Proxy settings as dict. Ex: {"scheme": "socks5", "hostname": "11.22.33.44", "port": 1234, "username": "user", "password": "pass"}. The username and password can be omitted if the proxy doesn’t require authorization.

- `USER_SESSION_STRING` (`Str`): To download/upload from your telegram account if user is `PREMIUM` and to send rss. To generate session string use this command `python3 generate_string_session.py` after mounting repo folder for sure. **NOTE**: You can't use bot with private message. Use it with superGroup.

- `DATABASE_URL` (`Str`): Your Mongo Database URL (Connection string). Follow this [Create Database](https://github.com/anasty17/test?tab=readme-ov-file#create-database) to create database. Data will be saved in Database: bot settings, users settings, rss data and incomplete tasks. **NOTE**: You can always edit all settings that saved in database from the official site -> (Browse collections). 

- `CMD_SUFFIX` (`Str`|`Int`): Commands index number. This number will added at the end all commands.

- `AUTHORIZED_CHATS` (`Str`): Fill user_id and chat_id of groups/users you want to authorize. To auth only specific topic(s) write it in this format `chat_id|thread_id` Ex:-100XXXXXXXXXXX or -100XXXXXXXXXXX|10 or -100XXXXXXXXXXX|10|12. Separate them by space.

- `SUDO_USERS` (`Str`):  Fill user_id of users whom you want to give sudo permission. Separate them by space.

- `UPLOAD_PATHS` (`Dict`): Send Dict of keys that have path values. Example: {"path 1": "remote:rclonefolder", "path 2": "gdrive1 id", "path 3": "tg chat id", "path 4": "mrcc:remote:", "path 5": "b: @username"}. 

- `DEFAULT_UPLOAD` (`Str`): Whether `rc` to upload to `RCLONE_PATH` or `gd` to upload to `GDRIVE_ID`. Default is `rc`. Read More [HERE](https://github.com/anasty17/mirror-leech-telegram-bot/tree/master#upload).

- `STATUS_UPDATE_INTERVAL` (`Int`): Time in seconds after which the progress/status message will be updated. Recommended `10` seconds at least.

- `STATUS_LIMIT` (`Int`): Limit the no. of tasks shown in status message with buttons. Default is `4`. **NOTE**: Recommended limit is `4` tasks.

- `EXCLUDED_EXTENSIONS` (`Str`): File extensions that won't upload/clone. Separate them by space.

- `INCOMPLETE_TASK_NOTIFIER` (`Bool`): Get incomplete task messages after restart. Require database and superGroup. Default
is `False`.

- `FILELION_API` (`Str`): Filelion api key to mirror Filelion links. Get it
from [Filelion](https://vidhide.com/?op=my_account).

- `STREAMWISH_API` (`Str`): Streamwish api key to mirror Streamwish links. Get it
from [Streamwish](https://streamwish.com/?op=my_account).

- `YT_DLP_OPTIONS` (`Dict`): Dict of yt-dlp options. Check all possible
options [HERE](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/YoutubeDL.py#L184) or use this [script](https://t.me/mltb_official_channel/177) to convert cli arguments to api options. Format: {key: value, key: value, key: value}.
  - Example: {"format": "bv*+mergeall[vcodec=none]", "nocheckcertificate": True, "playliststart": 10, "fragment_retries": float("inf"), "matchtitle": "S13", "writesubtitles": True, "live_from_start": True, "postprocessor_args": {"ffmpeg": ["-threads", "4"]}, "wait_for_video": (5, 100), "download_ranges": [{"start_time": 0, "end_time": 10}]}

- `USE_SERVICE_ACCOUNTS` (`Bool`): Whether to use Service Accounts or not, with google-api-python-client. For this to work
see [Using Service Accounts](https://github.com/anasty17/mirror-leech-telegram-bot#generate-service-accounts-what-is-service-account) section below. Default is `False`.

- `FFMPEG_CMDS` (`Dict`): Dict of list values of ffmpeg commands. You can set multiple ffmpeg commands for all files before upload. Don't write ffmpeg at beginning, start directly with the arguments. `Dict`
  - Examples: {"subtitle": ["-i mltb.mkv -c copy -c:s srt mltb.mkv", "-i mltb.video -c copy -c:s srt mltb"], "convert": ["-i mltb.m4a -c:a libmp3lame -q:a 2 mltb.mp3", "-i mltb.audio -c:a libmp3lame -q:a 2 mltb.mp3"], extract: ["-i mltb -map 0:a -c copy mltb.mka -map 0:s -c copy mltb.srt"], "metadata": ["-i mltb.mkv -map 0 -map -0:v:1 -map -0:s -map 0:s:0 -map -0:v:m:attachment -c copy -metadata:s:v:0 title={title} -metadata:s:a:0 title={title} -metadata:s:a:1 title={title2} -metadata:s:a:2 title={title2} -c:s srt -metadata:s:s:0 title={title3} mltb -y -del"], "watermark": ["-i mltb -i tg://openmessage?user_id=5272663208&message_id=322801 -filter_complex 'overlay=W-w-10:H-h-10' -c:a copy mltb"]}
  **Notes**:
  - Don't add ffmpeg at the beginning!
  - Add `-del` to the list which you want from the bot to delete the original files after command run complete!
  - To execute one of those lists in bot for example, you must use -ff subtitle (list key) or -ff convert (list key)
  **Example**:
  - Here I will explain how to use mltb.* which is reference to files you want to work on.
  1. First cmd: the input is mltb.mkv so this cmd will work only on mkv videos and the output is mltb.mkv also so all outputs is mkv. `-del` will delete the original media after complete run of the cmd.
  2. Second cmd: the input is mltb.video so this cmd will work on all videos and the output is only mltb so the extenstion is same as input files.
  3. Third cmd: the input in mltb.m4a so this cmd will work only on m4a audios and the output is mltb.mp3 so the output extension is mp3.
  4. Fourth cmd: the input is mltb.audio so this cmd will work on all audios and the output is mltb.mp3 so the output extension is mp3.
  5. FFmpeg Variables in last cmd which is metadata ({title}, {title2}, etc...), you can edit them in usetting
  6. Telegram link for small size inputs like photo to set watermark.

- `NAME_SUBSTITUTE` (`Str`): Add word/letter/character/sentense/pattern to remove or replace with other words with sensitive case or without. 
  **Notes**:
    - Before any character you must add `\BACKSLASH`, those are the characters: `\^$.|?*+()[]{}-`
    * Example: script/code/s | mirror/leech | tea/ /s | clone | cpu/ | \[mltb\]/mltb | \\text\\/text/s
    - script will get replaced by code with sensitive case
    - mirror will get replaced by leech
    - tea will get replaced by space with sensitive case
    - clone will get removed
    - cpu will get replaced by space
    - [mltb] will get replaced by mltb
    - \text\ will get replaced by text with sensitive case

**3. GDrive Tools**

- `GDRIVE_ID` (`Str`): This is the Folder/TeamDrive ID of the Google Drive OR `root` to which you want to upload all the mirrors using google-api-python-client.

- `IS_TEAM_DRIVE` (`Bool`): Set `True` if uploading to TeamDrive using google-api-python-client. Default is `False`.

- `INDEX_URL` (`Str`): Refer to <https://gitlab.com/ParveenBhadooOfficial/Google-Drive-Index>.

- `STOP_DUPLICATE` (`Bool`): Bot will check file/folder name in Drive incase uploading to `GDRIVE_ID`. If it's present in Drive then downloading or cloning will be stopped. (**NOTE**: Item will be checked using name and not hash, so this feature is not perfect). Default is `False`.

**4. Rclone**

- `RCLONE_PATH` (`Str`): Default rclone path to which you want to upload all the files/folders using rclone.

- `RCLONE_FLAGS` (`Str`): --key:value|--key|--key|--key:value . Check here all [RcloneFlags](https://rclone.org/flags/).

- `RCLONE_SERVE_URL` (`Str`): Valid URL where the bot is deployed to use rclone serve. Format of URL should be `http://myip`, where `myip` is the IP/Domain(public) of your bot or if you have chosen port other than `80` so write it in this format `http://myip:port` (`http` and not `https`).

- `RCLONE_SERVE_PORT` (`Int`): Which is the **RCLONE_SERVE_URL** Port. Default is `8080`.

- `RCLONE_SERVE_USER` (`Str`): Username for rclone serve authentication.

- `RCLONE_SERVE_PASS` (`Str`): Password for rclone serve authentication.

**5. Update**

- `UPSTREAM_REPO` (`Str`): Your github repository link, if your repo is private add `https://username:{githubtoken}@github.com/{username}/{reponame}` format. Get token from [Github settings](https://github.com/settings/tokens). So you can update your bot from filled repository on each restart.
  - **NOTE**: Any change in docker or requirements you need to deploy/build again with updated repo to take effect. DON'T delete .gitignore file. For more information read [THIS](https://github.com/anasty17/mirror-leech-telegram-bot/tree/master#upstream-repo-recommended).

- `UPSTREAM_BRANCH` (`Str`): Upstream branch for update. Default is `master`.

**6. Leech**

- `LEECH_SPLIT_SIZE` (`Int`): Size of split in bytes. Default is `2GB`. Default is `4GB` if your account is premium.
- `AS_DOCUMENT` (`Bool`): Default type of Telegram file upload. Default is `False` mean as media.

- `EQUAL_SPLITS` (`Bool`): Split files larger than **LEECH_SPLIT_SIZE** into equal parts size (Not working with zip cmd). Default is `False`.

- `MEDIA_GROUP` (`Bool`): View Uploaded splitted file parts in media group. Default is `False`.

- `USER_TRANSMISSION` (`Bool`): Upload/Download by user session. Only in superChat. Default is `False`.

- `HYBRID_LEECH` (`Bool`): Upload by user and bot session with respect to file size. Only in superChat. Default is `False`.

- `LEECH_FILENAME_PREFIX` (`Str`): Add custom word to leeched file name.

- `LEECH_DUMP_CHAT` (`Int`|`Str`): ID or USERNAME or PM(private message) to where files would be uploaded. Add `-100` before channel/superGroup id. To use only specific topic write it in this format `chat_id|thread_id`. Ex:-100XXXXXXXXXXX or -100XXXXXXXXXXX|10 or pm or @xxxxxxx or @xxxxxxx|10.

- `THUMBNAIL_LAYOUT` (`Str`): Thumbnail layout (widthxheight, 2x2, 3x3, 2x4, 4x4, ...) of how many photo arranged for the thumbnail.

**7. qBittorrent/Aria2c/Sabnzbd**

- `TORRENT_TIMEOUT` (`Int`): Timeout of dead torrents downloading with qBittorrent and Aria2c in seconds.

- `BASE_URL` (`Str`): Valid BASE URL where the bot is deployed to use torrent/nzb web files selection. Format of URL should be `http://myip`, where `myip` is the IP/Domain(public) of your bot or if you have chosen port other than `80` so write it in this format `http://myip:port` (`http` and not `https`).

- `BASE_URL_PORT` (`Int`): Which is the **BASE_URL** Port. Default is `80`.

- `WEB_PINCODE` (`Bool`): Whether to ask for pincode before selecting files from torrent in web or not. Default is `False`.
    - **Qbittorrent NOTE**: If your facing ram issues then set limit for `MaxConnections`, decrease `AsyncIOThreadsCount`, set limit of `DiskWriteCacheSize` to `32` and decrease `MemoryWorkingSetLimit` from qbittorrent.conf or bsetting command.
    - Open port 8090 in your vps to access webui from any device. username: mltb, password: mltbmltb

**8. JDownloader**

- `JD_EMAIL` (`Str`): jdownloader email sign up on [JDownloader](https://my.jdownloader.org/).

- `JD_PASS` (`Str`): jdownloader password.
  - **JDownloader Config**: You can use your config from local machine in bot by *zipping* cfg folder (cfg.zip) and add it in repo folder.

**9. Sabnzbd**

- `USENET_SERVERS` (`List`): list of dictionaries, you can add as much as you want and there is a button for servers in sabnzbd settings to edit current servers and add new servers.

  ***[{'name': 'main', 'host': '', 'port': 563, 'timeout': 60, 'username': '', 'password': '', 'connections': 8, 'ssl': 1, 'ssl_verify': 2, 'ssl_ciphers': '', 'enable': 1, 'required': 0, 'optional': 0, 'retention': 0, 'send_group': 0, 'priority': 0}]***

  - [READ THIS FOR MORE INFORMATION](https://sabnzbd.org/wiki/configuration/4.2/servers)

  - Open port 8070 in your vps to access full web interface from any device. Use it like http://ip:8070/sabnzbd/. username: mltb, password: mltbmltb

**10. RSS**

- `RSS_DELAY` (`Int`): Time in seconds for rss refresh interval. Recommended `600` second at least. Default is `600` in sec.

- `RSS_SIZE_LIMIT` (`INT`): Item size limit in bytes. Default is `0`.

- `RSS_CHAT` (`Int`|`Str`): Chat `ID or USERNAME or ID|TOPIC_ID or USERNAME|TOPIC_ID` where rss links will be sent. If you want message to be sent to the channel then add channel id. Add `-100` before channel id.
    - **RSS NOTES**: `RSS_CHAT` is required, otherwise monitor will not work. You must use `USER_STRING_SESSION` --OR-- *CHANNEL*. If using channel then bot should be added in both channel and group(linked to channel) and `RSS_CHAT` is the channel id, so messages sent by the bot to channel will be forwarded to group. Otherwise with `USER_STRING_SESSION` add group id for `RSS_CHAT`. If `DATABASE_URL` not added you will miss the feeds while bot offline.

**11. Queue System**

- `QUEUE_ALL` (`Int`): Number of parallel tasks of downloads and uploads. For example if 20 task added and `QUEUE_ALL` is `8`, then the summation of uploading and downloading tasks are 8 and the rest in queue. **NOTE**: if you want to fill `QUEUE_DOWNLOAD` or `QUEUE_UPLOAD`, then `QUEUE_ALL` value must be greater than or equal to the greatest one and less than or equal to summation of `QUEUE_UPLOAD` and `QUEUE_DOWNLOAD`.

- `QUEUE_DOWNLOAD` (`Int`): Number of all parallel downloading tasks.

- `QUEUE_UPLOAD` (`Int`): Number of all parallel uploading tasks.

**12. NZB Search**

- `HYDRA_IP` (`Str`): IP address of [nzbhydra2](https://github.com/theotherp/nzbhydra2).

- `HYDRA_API_KEY` (`Str`): API key from [nzbhydra2](https://github.com/theotherp/nzbhydra2).
