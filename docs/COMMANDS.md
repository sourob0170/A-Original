Bot commands to be set in <a href="https://t.me/BotFather">@BotFather</a>

```
mirror - or /m Mirror
qbmirror - or /qm Mirror using qBittorrent
jdmirror - or /jm Mirror using JDownloader
nzbmirror - or /nm Mirror using Sabnzbd
ytdl - or /y Mirror yt-dlp links
leech - or /l Upload to Telegram
qbleech - or /ql Leech using qBittorrent
jdleech - or /jl Leech using JDownloader
nzbleech - or /nl Leech using Sabnzbd
ytdlleech - or /yl Leech yt-dlp links
clone - Copy file/folder to Drive
count - Count file/folder from GDrive
settings - User settings
botsettings - Bot settings
status - Show mirror status
sel - Select files from torrent
rss - RSS menu
list - Search files in Drive
search - Search for torrents with API
stopall - Cancel all tasks
forcestart - or /fs Force start a task from queue
del - Delete file/folder from GDrive
log - Get the bot log
auth - Authorize user or chat
unauth - Unauthorize user or chat
shell - Run commands in Shell
aexec - Execute async function
exec - Execute sync function
restart - Restart the bot
restartses - Restart Telegram Session(s)
stats - Bot usage stats
ping - Ping the bot
help - List all commands and their descriptions
mediainfo - Check media information
broadcast - Broadcast message
spectrum - Generate spectrum from audio
```

## Command Details

### YouTube Downloader Commands (`/ytdl`, `/y`, `/ytdlleech`, `/yl`)

These commands are used to download videos or playlists using `yt-dlp` and then either mirror them to a cloud service (with `ytdl`) or leech them to Telegram (with `ytdlleech`).

**Common Options:**

*   `-n [new_name]`: Set a new name for the downloaded file/folder.
*   `-z`: Zip the downloaded files.
*   `-opt [yt-dlp_options]`: Specify advanced `yt-dlp` options.
*   `-s`: Select video quality interactively.
*   `-up [destination_details]`: Specify the upload destination.
    *   For standard uploads (Google Drive, Rclone): `gd` (for default GDrive), `rc` (for default Rclone), or a specific path like `remote:path/to/dir`.
    *   **For YouTube specific overrides (when uploading to YouTube):** Use the format `yt:privacy:mode:tags:category:description`.
        *   `privacy`: `public`, `private`, or `unlisted`.
        *   `mode`: `playlist`, `individual`, or `playlist_and_individual`.
        *   `tags`: Comma-separated tags (e.g., `mytag,anothertag`). Use `None` for no tags or leave empty.
        *   `category`: YouTube category ID (e.g., `22`).
        *   `description`: Custom video description.
        *   `playlist_id`: (Optional) YouTube Playlist ID to add the uploaded video(s) to. If provided, videos will be added to this existing playlist. If omitted or empty, new playlists might be created for folder uploads based on mode, or no specific playlist might be used for individual video uploads unless set in user settings.
        *   Parts can be skipped by leaving them empty. For example, `yt::individual:::MyDescription:` overrides only mode and description.
        *   Examples:
            *   `/ytdl [link] -up yt:private:individual:tag1,tag2:22:My custom description:YOUR_PLAYLIST_ID`
            *   `/ytdl [link] -up yt::playlist_and_individual::::YOUR_PLAYLIST_ID` (override mode and add to specific playlist)
            *   `/ytdl [link] -up yt:public` (override only privacy)
            *   If you want to upload to your default YouTube account (as per user settings) and also specify an Rclone path for other uploads (though ytdl usually implies one primary upload), you would typically rely on user settings for YouTube and use `-up rclone_path` for the rclone part if the bot supports such multi-destination logic for a single task. The `yt:` override is primarily for when YouTube is the chosen destination for the ytdl task.
*   `-rcf [rclone_flags]`: Specify Rclone flags if uploading to an Rclone destination.
*   `-t [thumbnail_link]`: Specify a custom thumbnail for the upload.

**Leech Specific Options (for `/ytdlleech`, `/yl`):**

*   `-doc`: Upload as document.
*   `-med`: Upload as media.
*   (Other leech-specific flags like `-sp` for split size, etc.)

Refer to the bot's interactive help (`/help` command followed by navigating to the `yt` section) for a more comprehensive list of all available flags and their detailed descriptions, as many flags are shared with general mirror/leech commands.
