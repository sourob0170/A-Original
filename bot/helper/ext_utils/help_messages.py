# FFmpeg help message with concise and visual format
ffmpeg_help = """<b>Custom FFmpeg Commands</b>: -ff

<blockquote>
<b>Basic Usage:</b>
• <code>/cmd link -ff "-i mltb.video -c:v libx264 mltb.mp4"</code> - Direct command
• <code>/cmd link -ff "preset_name"</code> - Use saved preset
• <code>/cmd link -ff "-i mltb.video -c:v libx264 -del mltb.mp4"</code> - Delete original
</blockquote>

<blockquote expandable="expandable">
<b>Multiple Commands:</b>
Run commands sequentially, using output of one as input for the next.

<b>JSON Array Format:</b> (Recommended)
<code>/cmd link -ff '[
  "-i mltb.video -c:v libx264 output1.mp4",
  "-i mltb -vf scale=640:360 output2.mp4",
  "-i mltb -ss 00:00:01 -vframes 1 thumb.jpg",
  "-i mltb -i tg://openmessage?user_id=5272663208&message_id=322801 -filter_complex 'overlay=W-w-10:H-h-10' -c:a copy mltb"
]'</code>

<b>List Format:</b>
<code>/cmd link -ff [["-i","mltb.video","-c:v","libx264","out.mp4"],["-i","mltb","-vf","scale=640:360","out2.mp4"]]</code>

• <code>mltb</code> in later commands refers to previous output
• For presets: <code>{"process":[["-i","mltb","-c:v","libx264","temp.mp4"],["-i","mltb","-vf","scale=720p","final.mp4"]]}</code>
</blockquote>

<blockquote expandable="expandable">
<b>Input Placeholders:</b>
• <code>mltb</code> or <code>input.mp4</code> - Generic input file
• <code>mltb.video</code> - Video files only
• <code>mltb.audio</code> - Audio files only
• <code>mltb.image</code> - Image files only
• <code>mltb.subtitle</code> - Subtitle files only
• <code>mltb.document</code> - Document files only
• <code>mltb.archive</code> - Archive files only
• <code>mltb.mkv</code> - In multiple commands, refers to previous command's output

These placeholders are automatically replaced with the actual file path.
</blockquote>

<blockquote expandable="expandable">
<b>Multiple Input Support:</b>
• <code>-i mltb.video -i mltb.audio</code> - Use multiple input files
• <code>-i mltb.video -i mltb.audio -map 0:v:0 -map 1:a:0 output.mp4</code> - Video from first, audio from second
• <code>-i mltb.video -i mltb.image -filter_complex "[0:v][1:v]overlay=10:10" output.mp4</code> - Add watermark
• <code>-i mltb.video -i mltb.audio -i mltb.subtitle -map 0:v -map 1:a -map 2:s output.mkv</code> - Combine all
</blockquote>

<blockquote expandable="expandable">
<b>Dynamic Output Naming:</b>
• <code>mltb.mp4</code> - Simple output (adds ffmpeg prefix)
• <code>output.mp4</code> - Custom named output
• <code>mltb-%d.mp4</code> → video-1.mp4, video-2.mp4, etc.
• <code>mltb-%03d.mp4</code> → video-001.mp4, video-002.mp4, etc.

<b>Dynamic Output Examples:</b>
• <code>-i mltb.video -map 0:v -c:v libx264 video-%d.mp4</code> - Extract all video streams
• <code>-i mltb.video -map 0:a -c:a aac audio-%03d.m4a</code> - Extract all audio tracks
• <code>-i mltb.mkv -f segment -segment_time 600 part-%03d.mkv</code> - Split into segments
</blockquote>

<blockquote expandable="expandable">
<b>Common Tasks:</b>

<b>Convert Video Format:</b>
<code>-i mltb.video -c:v libx264 -c:a aac mltb.mp4</code>

<b>Extract Audio:</b>
<code>-i mltb.video -vn -c:a copy mltb.m4a</code>

<b>Extract Subtitles:</b>
<code>-i mltb.video -map 0:s -c:s srt mltb-%d.srt</code>

<b>Compress Video:</b>
<code>-i mltb.video -c:v libx264 -crf 23 -preset medium -c:a aac -b:a 128k mltb.mp4</code>

<b>Trim Video:</b>
<code>-i mltb.video -ss 00:01:00 -to 00:02:00 -c:v copy -c:a copy mltb.mp4</code>

<b>Create GIF:</b>
<code>-i mltb.video -vf "fps=10,scale=320:-1:flags=lanczos" -c:v gif mltb.gif</code>
</blockquote>

<blockquote expandable="expandable">
<b>Advanced Examples:</b>

<b>Extract Streams:</b> <code>-i mltb.mkv -map 0:v -c:v copy video.mp4 -map 0:a -c:a copy audio.m4a</code>

<b>Add Watermark:</b> <code>-i mltb.video -vf "drawtext=text='@YourChannel':fontcolor=white:fontsize=24:x=10:y=10" mltb.mp4</code>

<b>Speed Up:</b> <code>-i mltb.video -filter_complex "[0:v]setpts=0.5*PTS[v];[0:a]atempo=2.0[a]" -map "[v]" -map "[a]" mltb.mp4</code>

<b>Multi-Step Processing:</b>
<code>/cmd link -ff '[
  "-i mltb.video -c:v libx264 temp.mp4",
  "-i mltb -vf scale=720:480 final.mp4",
  "-i mltb -ss 00:00:01 -vframes 1 thumb.jpg"
]'</code>
</blockquote>

<blockquote expandable="expandable">
<b>Preset Management:</b>

<b>Using Presets:</b>
• Use <code>/cmd link -ff "preset_name"</code> to apply a preset
• Configure in User Settings > FFMPEG_CMDS

<b>Creating Presets:</b>
• Single command: <code>{"compress": ["-i mltb.video -c:v libx264 mltb.mp4"]}</code>
• Multiple commands: <code>{"process": [
  ["-i mltb.video -c:v libx264 temp.mp4"],
  ["-i mltb -vf scale=720:480 final.mp4"]
]}</code>
• Variables: Use <code>{variable}</code> for customizable values
</blockquote>

<blockquote expandable="expandable">
<b>Tips & Tricks:</b>

• Use <code>-c:v copy -c:a copy</code> for fastest processing (no re-encoding)
• Add <code>-del</code> to delete original files after processing
• For bulk downloads, commands apply to each file individually
• For complex commands, test on small files first
• In multiple commands, use <code>mltb</code> to reference the previous command's output
• JSON array format is more readable for complex command sequences
• You can add telegram link for small size input like photo to set watermark
</blockquote>"""

nsfw_keywords = [
    "porn",
    "onlyfans",
    "nsfw",
    "Brazzers",
    "adult",
    "xnxx",
    "xvideos",
    "nsfwcherry",
    "hardcore",
    "Pornhub",
    "xvideos2",
    "youporn",
    "pornrip",
    "playboy",
    "hentai",
    "erotica",
    "blowjob",
    "redtube",
    "stripchat",
    "camgirl",
    "nude",
    "fetish",
    "cuckold",
    "orgy",
    "horny",
    "swingers",
    "ullu",
]

mirror = """<b>Send link along with command line or </b>

/cmd link

<b>By replying to link/file</b>:

/cmd -n new name -e -up upload destination

<b>NOTE:</b>"""

yt = """<b>Send link along with command line</b>:

/cmd link
<b>By replying to link</b>:
/cmd -n new name -z password -opt x:y|x1:y1

Check here all supported <a href='https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md'>SITES</a>
Check all yt-dlp api options from this <a href='https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/YoutubeDL.py#L212'>FILE</a> or use this <a href='https://t.me/mltb_official_channel/177'>script</a> to convert cli arguments to api options."""

clone = """Send Gdrive|Gdot|Filepress|Filebee|Appdrive|Gdflix link or rclone path along with command or by replying to the link/rc_path by command.
Use -sync to use sync method in rclone. Example: /cmd rcl/rclone_path -up rcl/rclone_path/rc -sync"""

new_name = """<b>New Name</b>: -n

/cmd link -n new name
Note: Doesn't work with torrents"""

multi_link = """<b>Multi links only by replying to first link/file</b>: -i

/cmd -i 10(number of links/files)"""

same_dir = """<b>Move file(s)/folder(s) to new folder</b>: -m

You can use this arg also to move multiple links contents to the same directory, so all links will be uploaded together as one task

/cmd link -m new folder (only one link inside new folder)
/cmd -i 10(number of links/files) -m folder name (all links contents in one folder)
/cmd -b -m folder name (reply to batch of message/file(each link on new line))

While using bulk you can also use this arg with different folder name along with the links in message or file batch
Example:
link1 -m folder1
link2 -m folder1
link3 -m folder2
link4 -m folder2
link5 -m folder3
link6
so link1 and link2 content will be uploaded from same folder which is folder1
link3 and link4 content will be uploaded from same folder also which is folder2
link5 will uploaded alone inside new folder named folder3
link6 will get uploaded normally alone
"""

thumb = """<b>Thumbnail for current task</b>: -t

/cmd link -t tg-message-link (doc or photo) or none (file without thumb)"""

split_size = """<b>Split size for current task</b>: -sp

/cmd link -sp (500mb or 2gb or 4000000000)
Note: Only mb and gb are supported or write in bytes without unit!

<b>Equal Splits</b>: -es

/cmd link -es
This will split the file into equal parts based on the file size, regardless of the split size setting.
You can also enable Equal Splits in user settings > leech menu.
"""

upload = """<b>Upload Destination</b>: -up

/cmd link -up rcl/gdl (rcl: to select rclone config, remote & path | gdl: To select token.pickle, gdrive id) using buttons
You can directly add the upload path: -up remote:dir/subdir or -up Gdrive_id or -up id/username (telegram) or -up id/username|topic_id (telegram)
If DEFAULT_UPLOAD is `rc` then you can pass up: `gd` to upload using gdrive tools to GDRIVE_ID.
If DEFAULT_UPLOAD is `gd` then you can pass up: `rc` to upload to RCLONE_PATH.

If you want to add path or gdrive manually from your config/token (UPLOADED FROM USETTING) add mrcc: for rclone and mtp: before the path/gdrive_id without space.
/cmd link -up mrcc:main:dump or -up mtp:gdrive_id <strong>or you can simply edit upload using owner/user token/config from usetting without adding mtp: or mrcc: before the upload path/id</strong>

To add leech destination:
-up id/@username/pm
-up b:id/@username/pm (b: means leech by bot) (id or username of the chat or write pm means private message so bot will send the files in private to you)
when you should use b:(leech by bot)? When your default settings is leech by user and you want to leech by bot for specific task.
-up u:id/@username(u: means leech by user) This incase OWNER added USER_SESSION_STRING.
-up h:id/@username(hybrid leech) h: to upload files by bot and user based on file size.
-up id/@username|topic_id(leech in specific chat and topic) add | without space and write topic id after chat id or username.

In case you want to specify whether using token.pickle or service accounts you can add tp:gdrive_id (using token.pickle) or sa:gdrive_id (using service accounts) or mtp:gdrive_id (using token.pickle uploaded from usetting).
DEFAULT_UPLOAD doesn't affect on leech cmds.
"""

user_download = """<b>User Download</b>: link

/cmd tp:link to download using owner token.pickle incase service account enabled.
/cmd sa:link to download using service account incase service account disabled.
/cmd tp:gdrive_id to download using token.pickle and file_id incase service account enabled.
/cmd sa:gdrive_id to download using service account and file_id incase service account disabled.
/cmd mtp:gdrive_id or mtp:link to download using user token.pickle uploaded from usetting
/cmd mrcc:remote:path to download using user rclone config uploaded from usetting
you can simply edit upload using owner/user token/config from usetting without adding mtp: or mrcc: before the path/id"""

rcf = """<b>Rclone Flags</b>: -rcf

/cmd link|path|rcl -up path|rcl -rcf --buffer-size:8M|--drive-starred-only|key|key:value
This will override all other flags except --exclude
Check here all <a href='https://rclone.org/flags/'>RcloneFlags</a>."""

bulk = """<b>Bulk Download</b>: -b

Bulk can be used only by replying to text message or text file contains links separated by new line.
Note: Bulk operations can be enabled/disabled by the administrator in bot settings.

Example:
link1 -n new name -up remote1:path1 -rcf |key:value|key:value
link2 -z -n new name -up remote2:path2
link3 -e -n new name -up remote2:path2
Reply to this example by this cmd -> /cmd -b(bulk)

Note: Any arg along with the cmd will be setted to all links
/cmd -b -up remote: -z -m folder name (all links contents in one zipped folder uploaded to one destination)
so you can't set different upload destinations along with link incase you have added -m along with cmd
You can set start and end of the links from the bulk like seed, with -b start:end or only end by -b :end or only start by -b start.
The default start is from zero(first link) to inf."""

rlone_dl = """<b>Rclone Download</b>:

Treat rclone paths exactly like links
/cmd main:dump/ubuntu.iso or rcl(To select config, remote and path)
Users can add their own rclone from user settings
If you want to add path manually from your config add mrcc: before the path without space
/cmd mrcc:main:dump/ubuntu.iso
You can simply edit using owner/user config from usetting without adding mrcc: before the path"""

extract_zip = """<b>Extract/Zip</b>: -e -z

/cmd link -e password (extract password protected)
/cmd link -z password (zip password protected)
/cmd link -z password -e (extract and zip password protected)
Note: When both extract and zip added with cmd it will extract first and then zip, so always extract first"""

join = """<b>Join Splitted Files</b>: -j

This option will only work before extract and zip, so mostly it will be used with -m argument (samedir)
By Reply:
/cmd -i 3 -j -m folder name
/cmd -b -j -m folder name
if u have link(folder) have splitted files:
/cmd link -j"""

tg_links = """<b>TG Links</b>:

Treat links like any direct link
Some links need user access so you must add USER_SESSION_STRING for it.
Three types of links:
Public: https://t.me/channel_name/message_id
Private: tg://openmessage?user_id=xxxxxx&message_id=xxxxx
Super: https://t.me/c/channel_id/message_id
Range: https://t.me/channel_name/first_message_id-last_message_id
Range Example: tg://openmessage?user_id=xxxxxx&message_id=555-560 or https://t.me/channel_name/100-150
Skip Messages: Add -skip followed by a number to skip messages in a range
Skip Examples:
• https://t.me/channel_name/100-150 -skip 3 (will download messages 100, 103, 106, etc.)
• https://t.me/channel_name/100-150-skip3 (same result, more compact format)
• tg://openmessage?user_id=xxxxxx&message_id=555-560 -skip 2 (will download messages 555, 557, 559)
Note: Range link will work only by replying cmd to it"""

sample_video = """<b>Sample Video</b>: -sv

Create sample video for one video or folder of videos.
/cmd -sv (it will take the default values which 60sec sample duration and part duration is 4sec).
You can control those values. Example: /cmd -sv 70:5(sample-duration:part-duration) or /cmd -sv :5 or /cmd -sv 70."""

screenshot = """<b>ScreenShots</b>: -ss

Create screenshots for one video or folder of videos.
/cmd -ss (it will take the default values which is 10 photos).
You can control this value. Example: /cmd -ss 6."""

zip_arg = """<b>Zip</b>: -z password

/cmd link -z (zip)
/cmd link -z password (zip password protected)"""

qual = """<b>Quality Buttons</b>: -s

In case default quality added from yt-dlp options using format option and you need to select quality for specific link or links with multi links feature.
/cmd link -s"""

yt_opt = """<b>Options</b>: -opt

/cmd link -opt {"format": "bv*+mergeall[vcodec=none]", "nocheckcertificate": True, "playliststart": 10, "fragment_retries": float("inf"), "matchtitle": "S13", "writesubtitles": True, "live_from_start": True, "postprocessor_args": {"xtra": ["-threads", "4"]}, "wait_for_video": (5, 100), "download_ranges": [{"start_time": 0, "end_time": 10}]}
Check all yt-dlp api options from this <a href='https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/YoutubeDL.py#L184'>FILE</a> or use this <a href='https://t.me/mltb_official_channel/177'>script</a> to convert cli arguments to api options."""

convert_media = """<b>Convert Media</b>: -ca -cv -cs -cd -cr

<blockquote>Dont understand? Then follow this <a href='https://t.me/aimupdate/218'>quide</a></blockquote>

Convert media files to different formats with customizable settings for video, audio, subtitles, documents, and archives.

<b>Basic Usage:</b>
- <code>-cv format</code>: Convert videos (e.g., <code>-cv mp4</code>)
- <code>-ca format</code>: Convert audio (e.g., <code>-ca mp3</code>)
- <code>-cs format</code>: Convert subtitles (e.g., <code>-cs srt</code>)
- <code>-cd format</code>: Convert documents (e.g., <code>-cd pdf</code>)
- <code>-cr format</code>: Convert archives (e.g., <code>-cr zip</code>)
- <code>-del</code>: Delete original files after conversion

<b>Supported Formats:</b>
• <b>Videos</b>: MP4, MKV, AVI, MOV, WebM, FLV, WMV, M4V, TS, 3GP
• <b>Audio</b>: MP3, M4A, FLAC, WAV, OGG, OPUS, AAC, WMA, ALAC
• <b>Subtitles</b>: SRT, ASS, SSA, VTT, WebVTT, SUB, SBV
• <b>Documents</b>: PDF, DOCX, TXT, ODT, RTF
• <b>Archives</b>: ZIP, RAR, 7Z, TAR, GZ, BZ2

<b>Advanced Usage:</b>
- <code>-ca mp3 + flac ogg</code>: Convert only FLAC and OGG audios to MP3
- <code>-cv mkv - webm flv</code>: Convert all videos to MKV except WebM and FLV
- <code>-ca mp3 -cv mp4 -cs srt</code>: Convert audios to MP3, videos to MP4, and subtitles to SRT
- <code>-cv mp4 -del</code>: Convert all videos to MP4 and delete original files

<b>Examples:</b>
/cmd link -ca mp3 -cv mp4
/cmd link -ca mp3 + flac ogg
/cmd link -cv mkv - webm flv
/cmd link -cs srt -cd pdf
/cmd link -cr zip -del

<b>Important Notes:</b>
• Enable convert in Media Tools settings before using
• Enable specific media type conversions (video, audio, etc.)
• Configure quality settings for optimal results
• Set priority to control when conversion runs in the pipeline
• Use /mthelp command for detailed guide on convert feature"""

add_media = """<b>Add Media</b>: -add -add-video -add-audio -add-subtitle -add-attachment

<blockquote>Add media tracks to existing files</blockquote>

Add specific tracks (video, audio, subtitle, attachment) to media files.

<b>Basic Usage:</b>
- <code>-add</code>: Add all enabled track types based on settings
- <code>-add-video</code>: Add only video tracks
- <code>-add-audio</code>: Add only audio tracks
- <code>-add-subtitle</code>: Add only subtitle tracks
- <code>-add-attachment</code>: Add only attachment tracks

<b>Track Handling Flags:</b>
- <code>-del</code>: Delete original file after processing
- <code>-preserve</code>: Preserve existing tracks when adding new ones
- <code>-replace</code>: Replace existing tracks with new ones

<b>Advanced Usage (Long Format):</b>
- <code>-add-video-index 0,1,2</code>: Add video tracks at indices 0, 1, and 2
- <code>-add-audio-index 0,1</code>: Add audio tracks at indices 0 and 1
- <code>-add -del</code>: Add tracks and delete original file
- <code>-add -preserve</code>: Add tracks and preserve existing tracks
- <code>-add -replace</code>: Add tracks and replace existing tracks

<b>Track Index Selection:</b>
- <code>-add-video-index 0</code>: Add only the first video track from source
- <code>-add-audio-index 1</code>: Add only the second audio track from source
- <code>-add-subtitle-index 2</code>: Add only the third subtitle track from source
- <code>-add-attachment-index 0</code>: Add only the first attachment from source
- <code>-add-video-index 0,1,2</code>: Add multiple video tracks at specified indices
- <code>-add-audio-index 0,1,2</code>: Add multiple audio tracks at specified indices

<b>Advanced Usage (Short Format):</b>
- <code>-avi 0</code>: Add only the first video track
- <code>-avi 0,1,2</code>: Add video tracks at indices 0, 1, and 2
- <code>-aai 1</code>: Add only the second audio track
- <code>-aai 0,1</code>: Add audio tracks at indices 0 and 1
- <code>-asi 2</code>: Add only the third subtitle track
- <code>-ati 0</code>: Add only the first attachment

<b>Additional Video Settings:</b>
- <code>-add-video-codec h264</code>: Set video codec (h264, h265, vp9, etc.)
- <code>-add-video-quality 18</code>: Set video quality (CRF value, lower is better)
- <code>-add-video-preset medium</code>: Set encoding preset (ultrafast, fast, medium, slow)
- <code>-add-video-bitrate 5M</code>: Set video bitrate
- <code>-add-video-resolution 1920x1080</code>: Set video resolution
- <code>-add-video-fps 30</code>: Set video frame rate

<b>Additional Audio Settings:</b>
- <code>-add-audio-codec aac</code>: Set audio codec (aac, mp3, opus, flac, etc.)
- <code>-add-audio-bitrate 320k</code>: Set audio bitrate
- <code>-add-audio-channels 2</code>: Set number of audio channels
- <code>-add-audio-sampling 48000</code>: Set audio sampling rate
- <code>-add-audio-volume 1.5</code>: Set audio volume (1.0 is normal)

<b>Additional Subtitle Settings:</b>
- <code>-add-subtitle-codec srt</code>: Set subtitle codec (srt, ass, etc.)
- <code>-add-subtitle-language eng</code>: Set subtitle language code
- <code>-add-subtitle-encoding UTF-8</code>: Set subtitle character encoding
- <code>-add-subtitle-font Arial</code>: Set subtitle font (for ASS/SSA)
- <code>-add-subtitle-font-size 24</code>: Set subtitle font size (for ASS/SSA)

<b>Attachment Settings:</b>
- <code>-add-attachment-mimetype font/ttf</code>: Set MIME type for attachment

<b>Examples:</b>
/cmd link -add
/cmd link -add-video -add-audio
/cmd link -add -del
/cmd link -add-video -add-video-codec h264 -add-video-quality 18
/cmd link -add-audio -add-audio-codec aac -add-audio-bitrate 320k
/cmd link -add-subtitle -add-subtitle-codec srt
/cmd link -add-video-index 0,1 -m (with multi-link feature)

<b>Multi-Link and Bulk Integration:</b>
- <code>/cmd link1 link2 link3 -add-video -m</code>: Add video from link2 to link1
- <code>/cmd link1 link2 link3 -add-video-index 0,1 -m</code>: Add videos from link2 at index 0 and link3 at index 1 to link1

<b>Important Notes:</b>
• The Add feature must be enabled in both the bot settings and user settings
• The main Add toggle and the specific track type toggles must be enabled
• Configure add settings in Media Tools settings
• Add priority can be set to control when it runs in the processing pipeline
• When using multi-link feature (-m), tracks are added from the additional files
• When add is enabled through settings, original files are automatically deleted after processing
• Use the -del flag to delete original files after adding tracks (or -del f to keep original files)
• Settings with value 'none' will not be used in command generation
• If a specified index is not available, the system will use the first available index
• When using multiple indices with multi-link, tracks are added in the order of input files
"""

extract_media = """<b>Extract Media</b>: -extract -extract-video -extract-audio -extract-subtitle -extract-attachment

<blockquote>Extract specific tracks from media files</blockquote>

Extract specific tracks (video, audio, subtitle, attachment) from media files.

<b>Basic Usage:</b>
- <code>-extract</code>: Extract all enabled track types based on settings
- <code>-extract-video</code>: Extract only video tracks
- <code>-extract-audio</code>: Extract only audio tracks
- <code>-extract-subtitle</code>: Extract only subtitle tracks
- <code>-extract-attachment</code>: Extract only attachment tracks

<b>Advanced Usage (Long Format):</b>
- <code>-extract-video-index 0</code>: Extract only the first video track
- <code>-extract-audio-index 1</code>: Extract only the second audio track
- <code>-extract-subtitle-index 2</code>: Extract only the third subtitle track
- <code>-extract-attachment-index 0</code>: Extract only the first attachment
- <code>-extract -del</code>: Extract tracks and delete original file

<b>Multiple Track Indices:</b>
- <code>-extract-video-index 0,1</code>: Extract first and second video tracks
- <code>-extract-audio-index 0,2,3</code>: Extract first, third, and fourth audio tracks
- <code>-extract-subtitle-index 1,2</code>: Extract second and third subtitle tracks
- <code>-extract-attachment-index 0,1</code>: Extract first and second attachments

<b>Advanced Usage (Short Format):</b>
- <code>-vi 0</code>: Extract only the first video track
- <code>-ai 1</code>: Extract only the second audio track
- <code>-si 2</code>: Extract only the third subtitle track
- <code>-ati 0</code>: Extract only the first attachment
- <code>-vi 0,1 -ai 2,3</code>: Extract multiple tracks with short format

<b>Additional Video Settings:</b>
- <code>-extract-video-codec h264</code>: Set video codec (h264, h265, vp9, etc.)
- <code>-extract-video-quality 18</code>: Set video quality (CRF value, lower is better)
- <code>-extract-video-preset medium</code>: Set encoding preset (ultrafast, fast, medium, slow)
- <code>-extract-video-bitrate 5M</code>: Set video bitrate
- <code>-extract-video-resolution 1920x1080</code>: Set video resolution
- <code>-extract-video-fps 30</code>: Set video frame rate

<b>Additional Audio Settings:</b>
- <code>-extract-audio-codec aac</code>: Set audio codec (aac, mp3, opus, flac, etc.)
- <code>-extract-audio-bitrate 320k</code>: Set audio bitrate
- <code>-extract-audio-channels 2</code>: Set number of audio channels
- <code>-extract-audio-sampling 48000</code>: Set audio sampling rate
- <code>-extract-audio-volume 1.5</code>: Set audio volume (1.0 is normal)

<b>Additional Subtitle Settings:</b>
- <code>-extract-subtitle-codec srt</code>: Set subtitle codec (srt, ass, etc.)
- <code>-extract-subtitle-language eng</code>: Set subtitle language code
- <code>-extract-subtitle-encoding UTF-8</code>: Set subtitle character encoding
- <code>-extract-subtitle-font Arial</code>: Set subtitle font (for ASS/SSA)
- <code>-extract-subtitle-font-size 24</code>: Set subtitle font size (for ASS/SSA)

<b>Attachment Settings:</b>
- <code>-extract-attachment-filter *.ttf</code>: Filter attachments by pattern

<b>Examples:</b>
/cmd link -extract
/cmd link -extract-video -extract-audio
/cmd link -vi 0 -ai 1
/cmd link -extract-subtitle
/cmd link -extract -del
/cmd link -extract-video -extract-video-codec h264 -extract-video-quality 18
/cmd link -extract-audio -extract-audio-codec aac -extract-audio-bitrate 320k
/cmd link -extract-subtitle -extract-subtitle-codec srt

<b>Important Notes:</b>
• The Extract feature must be enabled in both the bot settings and user settings
• The main Extract toggle and the specific track type toggles must be enabled
• Configure extract settings in Media Tools settings
• Extract priority can be set to control when it runs in the processing pipeline
• Track indices start from 0 (first track is index 0)
• If no index is specified, all tracks of that type will be extracted
• You can use either long format (-extract-video-index) or short format (-vi) flags
• When extract is enabled through settings, original files are automatically deleted after extraction
• Only the specified track indices will be extracted when indices are provided
• Use the -del flag to delete original files after extraction (or -del f to keep original files)
• Settings with value 'none' will not be used in command generation
• For ASS/SSA subtitles, use 'copy' codec to preserve the original format or 'srt' to convert to SRT"""

force_start = """<b>Force Start</b>: -f -fd -fu
/cmd link -f (force download and upload)
/cmd link -fd (force download only)
/cmd link -fu (force upload directly after download finish)"""

media_tools_flag = """<b>Media Tools Flag</b>: -mt

/cmd link -mt (opens media tools settings before starting the task)

<blockquote>
When you use the -mt flag with any command:
1. The bot will show the media tools settings menu
2. You can customize settings as needed
3. Click "Done" to start the task with your settings
4. Click "Cancel" to abort the task
5. If no action is taken within 60 seconds, the task will be cancelled
</blockquote>

<blockquote expandable="expandable"><b>Usage Examples</b>:
• <code>/mirror https://example.com/video.mp4 -mt</code>
  Shows media tools settings before starting the mirror task

• <code>/leech https://example.com/files.zip -z -mt</code>
  Shows media tools settings before starting the leech task with zip extraction

• <code>/ytdl https://youtube.com/watch?v=example -mt</code>
  Shows media tools settings before starting the YouTube download

• <code>/mirror https://example.com/videos.zip -merge-video -mt</code>
  Shows media tools settings before starting a task with video merging

• <code>/leech https://example.com/video.mp4 -watermark "My Channel" -mt</code>
  Configure watermark settings before applying text watermark

• <code>/mirror https://example.com/audio.mp3 -ca mp3 -mt</code>
  Configure conversion settings before converting audio to MP3</blockquote>

<b>Benefits</b>:
• Configure media tools settings on-the-fly for specific tasks
• No need to use separate commands to change settings
• Preview and adjust settings before processing large files
• Easily cancel tasks if settings aren't right
• Works with all download commands and other flags

<b>Note</b>: All messages related to the <code>-mt</code> flag interaction are automatically deleted after 5 minutes for a cleaner chat experience."""

gdrive = """<b>Gdrive</b>: link
If DEFAULT_UPLOAD is `rc` then you can pass up: `gd` to upload using gdrive tools to GDRIVE_ID.
/cmd gdriveLink or gdl or gdriveId -up gdl or gdriveId or gd
/cmd tp:gdriveLink or tp:gdriveId -up tp:gdriveId or gdl or gd (to use token.pickle if service account enabled)
/cmd sa:gdriveLink or sa:gdriveId -p sa:gdriveId or gdl or gd (to use service account if service account disabled)
/cmd mtp:gdriveLink or mtp:gdriveId -up mtp:gdriveId or gdl or gd(if you have added upload gdriveId from usetting) (to use user token.pickle that uploaded by usetting)
You can simply edit using owner/user token from usetting without adding mtp: before the id"""

rclone_cl = """<b>Rclone</b>: path
If DEFAULT_UPLOAD is `gd` then you can pass up: `rc` to upload to RCLONE_PATH.
/cmd rcl/rclone_path -up rcl/rclone_path/rc -rcf flagkey:flagvalue|flagkey|flagkey:flagvalue
/cmd rcl or rclone_path -up rclone_path or rc or rcl
/cmd mrcc:rclone_path -up rcl or rc(if you have add rclone path from usetting) (to use user config)"""

name_sub = r"""<b>Name Substitution</b>: -ns

<blockquote>Dont understand? Then follow this <a href='https://t.me/aimupdate/190'>quide</a></blockquote>

/cmd link -ns script/code/s | mirror/leech | tea/ /s | clone | cpu/ | \[hello\]/hello | \\text\\/text/s
This will affect on all files. Format: wordToReplace/wordToReplaceWith/sensitiveCase
Word Subtitions. You can add pattern instead of normal text. Timeout: 60 sec
NOTE: You must add \ before any character, those are the characters: \^$.|?*+()[]{}-
1. script will get replaced by code with sensitive case
2. mirror will get replaced by leech
4. tea will get replaced by space with sensitive case
5. clone will get removed
6. cpu will get replaced by space
7. [hello] will get replaced by hello
8. \text\ will get replaced by text with sensitive case
"""

thumbnail_layout = """Thumbnail Layout: -tl
/cmd link -tl 3x3 (widthxheight) 3 photos in row and 3 photos in column"""

leech_as = """<b>Leech as</b>: -doc -med
/cmd link -doc (Leech as document)
/cmd link -med (Leech as media)"""

font_styles = """<b>Font Styles</b>:
Use the /fonts or /fontstyles command to see available font styles for leech.

<b>Three Types of Font Styling:</b>
• <b>Unicode Styles</b>: Transform regular ASCII characters into special Unicode variants (serif, sans, script, etc.)
• <b>HTML Formatting</b>: Apply Telegram's supported HTML tags (bold, italic, code, etc.)
• <b>Google Fonts</b>: Use any Google Font name for styling (Roboto, Open Sans, Lato, etc.)

<blockquote expandable="expandable"><b>Google Fonts Support:</b>
You can use Google Fonts in two ways:

1. <b>Leech Font Setting</b>: Set a Google Font name as your leech font to apply it to all captions

2. <b>Leech Caption Templates</b>: Apply Google Fonts to specific parts of your caption using this syntax:
   <code>{{variable}font_name}</code> - Apply font_name to just that variable
   Example: <code>{{filename}Roboto} - Size: {size}</code>

3. <b>Available Google Fonts</b>: You can use any Google Font name, including:
   • Roboto, Open Sans, Lato, Montserrat, Oswald
   • Raleway, Source Sans Pro, Slabo, PT Sans
   • And many more - see fonts.google.com for the full list

4. <b>Font Weight Support</b>: You can specify font weight for leech caption:
   • <code>{{filename}Roboto:700}</code> - Bold Roboto
   • <code>{{filename}Open Sans:300}</code> - Light Open Sans
   • <code>{{filename}Montserrat:900}</code> - Black Montserrat

5. <b>Font Style Support</b>: You can specify font style for leech caption:
   • <code>{{filename}Roboto:italic}</code> - Italic Roboto
   • <code>{{filename}Open Sans:700italic}</code> - Bold Italic Open Sans

6. <b>Multiple Font Properties</b>: You can combine weight and style for leech caption:
   • <code>{{filename}Roboto:700italic}</code> - Bold Italic Roboto</blockquote>

<blockquote expandable="expandable"><b>Unicode Font Styles:</b>
Unicode font styles transform regular ASCII characters into special Unicode variants.

Available Unicode styles:
• <b>serif</b>: 𝐒𝐞𝐫𝐢𝐟 𝐭𝐞𝐱𝐭 (bold)
• <b>serif_i</b>: 𝑆𝑒𝑟𝑖𝑓 𝑖𝑡𝑎𝑙𝑖𝑐 𝑡𝑒𝑥𝑡
• <b>serif_b</b>: 𝑺𝒆𝒓𝒊𝒇 𝒃𝒐𝒍𝒅 𝒊𝒕𝒂𝒍𝒊𝒄 𝒕𝒆𝒙𝒕
• <b>sans</b>: 𝖲𝖺𝗇𝗌 𝗍𝖾𝗑𝗍
• <b>sans_i</b>: 𝘚𝘢𝘯𝘴 𝘪𝘵𝘢𝘭𝘪𝘤 𝘵𝘦𝘹𝘵
• <b>sans_b</b>: 𝗦𝗮𝗻𝘀 𝗯𝗼𝗹𝗱 𝘁𝗲𝘅𝘁
• <b>sans_bi</b>: 𝙎𝙖𝙣𝙨 𝙗𝙤𝙡𝙙 𝙞𝙩𝙖𝙡𝙞𝙘 𝙩𝙚𝙭𝙩
• <b>script</b>: 𝒮𝒸𝓇𝒾𝓅𝓉 𝓉𝑒𝓍𝓉
• <b>script_b</b>: 𝓢𝓬𝓻𝓲𝓹𝓽 𝓫𝓸𝓵𝓭 𝓽𝓮𝔁𝓽
• <b>fraktur</b>: 𝔉𝔯𝔞𝔨𝔱𝔲𝔯 𝔱𝔢𝔵𝔱
• <b>fraktur_b</b>: 𝕱𝖗𝖆𝖐𝖙𝖚𝖗 𝖇𝖔𝖑𝖉 𝖙𝖊𝖝𝖙
• <b>mono</b>: 𝙼𝚘𝚗𝚘𝚜𝚙𝚊𝚌𝚎 𝚝𝚎𝚡𝚝
• <b>double</b>: 𝔻𝕠𝕦𝕓𝕝𝕖-𝕤𝕥𝕣𝕦𝕔𝕜 𝕥𝕖𝕩𝕥
• <b>gothic</b>: 𝖆𝖇𝖈
• <b>small_caps</b>: ᴀʙᴄ
• <b>circled</b>: ⓐⓑⓒ
• <b>bubble</b>: ａｂｃ
• <b>inverted</b>: ɐqɔ
• <b>squared</b>: 🄰🄱🄲
• <b>regional</b>: 🇦🇧🇨
• <b>superscript</b>: ᵃᵇᶜ
• <b>subscript</b>: ₐₑₓ
• <b>wide</b>: ｗｉｄｅ
• <b>cursive</b>: 𝒶𝒷𝒸

<b>For Leech Font:</b>
Enter one of the Unicode style names like "serif", "sans_b", "script", etc.
Example: Enter sans_b to use 𝗦𝗮𝗻𝘀 𝗯𝗼𝗹𝗱 𝘁𝗲𝘅𝘁 for all your leech captions

<b>For Leech Caption:</b>
Use the template variable format: {{variable}unicode_style}
Example: {{filename}serif_b} - Size: {{size}mono}
This applies serif bold to the filename and monospace to the size

Remember that Unicode styling only works with basic Latin characters (A-Z, a-z) and won't affect numbers or special characters.</blockquote>

<blockquote expandable="expandable"><b>HTML Formatting:</b>
HTML formatting applies Telegram's supported HTML tags to your text.

Available HTML formats:
• <b>bold</b>: <b>Bold text</b>
• <b>italic</b>: <i>Italic text</i>
• <b>underline</b>: <u>Underlined text</u>
• <b>strike</b>: <s>Strikethrough text</s>
• <b>code</b>: <code>Monospace text</code>
• <b>pre</b>: Preformatted text
• <b>spoiler</b>: <tg-spoiler>Spoiler text</tg-spoiler>
• <b>quote</b>: Quoted text

You can combine HTML formats:
• <b>bold_italic</b>: <b><i>Bold italic text</i></b>
• <b>bold_underline</b>: <b><u>Bold underlined text</u></b>
• <b>italic_underline</b>: <i><u>Italic underlined text</u></i>
• <b>bold_italic_underline</b>: <b><i><u>Bold italic underlined text</u></i></b>
• <b>quote_expandable</b>: <b><i><u>The text will be in expaned formate</u></i></b>
• <b>bold_quote</b>: <b><i><u>Text will be bold in quote formate</u></i></b>

<b>or Leech Font:</b>
Enter an HTML format name like "bold", "italic", "code", etc.
Example: Enter 'bold' to use <b>Bold text</b> for all your leech captions

<b>For Leech Caption:</b>
Use the template variable format: {{variable}html_format}
Example: {{filename}bold} - Size: {{size}code}
You can also use html tags like this -> <b> <i> <s> <u> <code> <pre> <tg-spoiler> <blockquote> <blockquote expandable="expandable">. You can also nest them together.</blockquote>

<blockquote expandable="expandable"><b>Unicode Emojis and Special Characters:</b>

You can also use any single Unicode character or emoji as a style. Examples:
- 🔥: Will add the fire emoji before and after your text
- ⭐: Will add stars before and after your text
- Any other emoji or special character will be used similarly

<b>For Leech Font:</b>
Any single emoji: 🔥, ⭐, 🚀, etc.
Any single Unicode character
Unicode codepoints in U+XXXX format (e.g., U+1F525 for 🔥)
The emoji will be added before and after your text
Example: If leech font is "🔥" and text is "filename.mp4", it will appear as "🔥filename.mp4🔥"

<b>For Leech Caption:</b>
Use the template variable format: {{variable}unicode_emoji}
Example: {{filename}🔥}</blockquote>

<blockquote expandable="expandable"><b>Template Variables (For Leech Caption and Leech Filename):</b>

<b>Basic Variables:</b>
• <code>{filename}</code> - The name of the file without extension
• <code>{size}</code> - The size of the file (e.g., 1.5GB, 750MB)
• <code>{duration}</code> - The duration of media files (e.g., 01:30:45)
• <code>{quality}</code> - The quality of video files (e.g., 1080p, 720p)
• <code>{audios}</code> - Audio languages in the file (e.g., English, Hindi)
• <code>{subtitles}</code> - Subtitle languages in the file (e.g., English, Spanish)
• <code>{md5_hash}</code> - MD5 hash of the file

<b>TV Show Variables:</b>
• <code>{season}</code> - Season number (with leading zero for single digits)
• <code>{episode}</code> - Episode number (with leading zero for single digits)

<b>Media Information:</b>
• <code>{NumVideos}</code> - Number of video tracks
• <code>{NumAudios}</code> - Number of audio tracks
• <code>{NumSubtitles}</code> - Number of subtitle tracks
• <code>{year}</code> - Release year extracted from filename or metadata
• <code>{formate}</code> - File format/extension
• <code>{id}</code> - Unique ID of the file
• <code>{framerate}</code> - Video framerate
• <code>{codec}</code> - Codec information (Video, Audio, Subtitle)

"<b>Example Usage:</b>
• TV Show: <code>{filename} S{season}E{episode} [{quality}]</code>
• Detailed: <code>{filename} [{formate}] [{codec}] [{framerate}]</code></blockquote>

<blockquote expandable="expandable"><b>Usage Examples:</b>

1. <b>Setting a default font style for all leech captions:</b>
   • Use the /usettings or /settings command and select "LEECH_FONT"
   • Enter a font style name like "serif_b" or "Roboto"

2. <b>Using font styles in caption templates:</b>
   • <code>{{filename}serif_b} - Size: {size}</code>
   • <code>File: {{filename}Montserrat:700} | {size}</code>
   • <code>{{filename}bold} | {{size}italic}</code>

3. <b>Mixing different font styles:</b>
   • <code>{{filename}Roboto:700} | {{size}mono} | {{quality}script}</code>

4. <b>Using HTML formatting with variables:</b>
   • <code>{{filename}bold_italic} | {{size}code}</code>

5. <b>Combining Google Fonts with HTML formatting:</b>
   • <code>{{{filename}Roboto:700}bold}</code> - Bold Roboto with HTML bold</blockquote>

6. <b>Combining with unicode emoji:</b>
   • <code>{{{{filename}Roboto:700}bold}🔥}</code> - Bold Roboto with HTML bold and with unicode emoji</blockquote>

<blockquote expandable="expandable"><b>Unlimited Nesting Support:</b>
You can nest styles to any depth with any combination of styles!

1. <b>Basic Nesting (Two Styles):</b>
   • <code>{{{variable}style1}style2}</code>
   • Example: <code>{{{filename}bold}italic}</code> - Bold then italic

2. <b>Triple Nesting (Three Styles):</b>
   • <code>{{{{variable}style1}style2}style3}</code>
   • Example: <code>{{{{filename}bold}italic}🔥}</code> - Bold, italic, then fire emoji

3. <b>Advanced Nesting (Four or More Styles):</b>
   • <code>{{{{{variable}style1}style2}style3}style4}</code>
   • Example: <code>{{{{{filename}bold}italic}code}underline}</code> - Four nested styles

4. <b>Master Nesting (Any Number of Styles):</b>
   • You can continue nesting to any depth
   • Example: <code>{{{{{{{{filename}bold}italic}code}underline}strike}🔥}Roboto}</code>
   • Styles are applied from innermost to outermost: bold → italic → code → underline → strike → 🔥 → Roboto</blockquote>

<blockquote expandable="expandable"><b>How to Find Google Fonts:</b>
1. Visit <a href='https://fonts.google.com/'>fonts.google.com</a>
2. Find a font you like
3. Use the exact font name in your leech font setting or caption template</blockquote>

<b>Important Notes:</b>
• Unicode font styles only work with basic Latin characters (A-Z, a-z)
• Google Fonts support depends on the rendering capabilities of the device
• HTML formatting is the most compatible across all devices
• Font styles are applied after template variables are processed
• User settings take priority over owner settings
• Unlimited nesting of styles is supported - combine any number of styles in any order
• For complex nested styles, apply them in order from innermost to outermost"""

ffmpeg_cmds = ffmpeg_help


ai_help = """<b>AI Chatbot</b>:

Chat with AI models using the bot commands.

<b>Available AI Models:</b>
Use the /ask command with any of the following AI providers:
- <b>Mistral AI</b>
- <b>DeepSeek AI</b>

<b>Usage:</b>
/ask your question here

<b>Configuration:</b>
1. <b>Bot Owner</b>: Configure API Keys or API URLs and default AI provider in bot settings
2. <b>Users</b>: Configure your own API Keys or API URLs and default AI provider in user settings

<b>Features:</b>
- Uses powerful language models
- Supports both direct API access and custom API endpoints
- User settings take priority over bot owner settings
- Messages auto-delete after 5 minutes
- Automatically selects the configured AI provider

<b>Examples:</b>
/ask What is the capital of France?
/ask Write a short poem about nature
/ask Explain how quantum computing works
/ask Translate this text to Spanish: Hello world
"""

user_cookies_help = """<b>User Cookies</b>:

You can provide your own cookies for YouTube and other yt-dlp downloads to access restricted content.

1. Go to /usettings > Leech Settings > User Cookies
2. Upload your cookies.txt file (create it using browser extensions)
3. Your cookies will be used for all your yt-dlp downloads

When you upload your cookies, they will be used instead of the owner's cookies. This helps with errors like login requirements or subscriber-only content.

To remove your cookies and use the owner's cookies again, click the Remove button."""

YT_HELP_DICT = {
    "main": yt,
    "New-Name": f"{new_name}\nNote: Don't add file extension",
    "Zip": zip_arg,
    "Quality": qual,
    "Options": yt_opt,
    "User-Cookies": user_cookies_help,
    "Multi-Link": multi_link,
    "Same-Directory": same_dir,
    "Thumb": thumb,
    "Split-Size": split_size,
    "Upload-Destination": upload,
    "Rclone-Flags": rcf,
    "Bulk": bulk,
    "Sample-Video": sample_video,
    "Screenshot": screenshot,
    "Convert-Media": convert_media,
    "Force-Start": force_start,
    "Name-Substitute": name_sub,
    "Thumb-Layout": thumbnail_layout,
    "Leech-Type": leech_as,
    "FFmpeg-Cmds": ffmpeg_cmds,
    "Media-Tools-Flag": media_tools_flag,
}

# Merge flags guide has been moved to media_tools_help.py

# Watermark guide has been moved to media_tools_help.py

MIRROR_HELP_DICT = {
    "main": mirror,
    "New-Name": new_name,
    "DL-Auth": "<b>Direct link authorization</b>: -au -ap\n\n/cmd link -au username -ap password",
    "Headers": "<b>Direct link custom headers</b>: -h\n\n/cmd link -h key:value|key1:value1",
    "Extract/Zip": extract_zip,
    "Select-Files": "<b>JDownloader/Sabnzbd File Selection</b>: -s\n\n/cmd link -s or by replying to file/link",
    "Multi-Link": multi_link,
    "Same-Directory": same_dir,
    "Thumb": thumb,
    "Split-Size": split_size,
    "Upload-Destination": upload,
    "Rclone-Flags": rcf,
    "Bulk": bulk,
    "Join": join,
    "Rclone-DL": rlone_dl,
    "Tg-Links": tg_links,
    "Sample-Video": sample_video,
    "Screenshot": screenshot,
    "Convert-Media": convert_media,
    "Force-Start": force_start,
    "User-Download": user_download,
    "Name-Substitute": name_sub,
    "Thumb-Layout": thumbnail_layout,
    "Leech-Type": leech_as,
    "FFmpeg-Cmds": ffmpeg_cmds,
    "Media-Tools-Flag": media_tools_flag,
    "AI-Chatbot": ai_help,
}

CLONE_HELP_DICT = {
    "main": clone,
    "Multi-Link": multi_link,
    "Bulk": bulk,
    "Gdrive": gdrive,
    "Rclone": rclone_cl,
}

AI_HELP_DICT = {
    "main": ai_help,
}

virustotal_help = """<b>VirusTotal Scanner</b>

Scan files and URLs for viruses and malware using VirusTotal.

<b>Usage:</b>
1. Reply to a file with /virustotal to scan it
2. Reply to a message containing a URL with /virustotal
3. Use /virustotal <url> to scan a URL directly

<b>Features:</b>
• Automatic scanning in private chats (when enabled)
• Manual scanning in groups
• Detailed threat analysis
• Link to full VirusTotal report

<b>Note:</b>
• Maximum file size: 32MB
• Requires a VirusTotal API key to be configured
• Files are temporarily downloaded for scanning and then deleted
"""

VT_HELP_DICT = {
    "main": virustotal_help,
}

# Streamrip help content
streamrip_main = """<b>🎵 Streamrip Downloads</b>

Download high-quality music from streaming platforms like Qobuz, Tidal, Deezer, and SoundCloud.

<b>Commands:</b>
• <code>/srm</code>, <code>/srmirror</code> or <code>/streamripmirror</code> - Mirror music to cloud storage
• <code>/srl</code>, <code>/srleech</code> or <code>/streamripleech</code> - Leech music to Telegram
• <code>/srs</code>, <code>/srsearch</code> or <code>/streamripsearch</code> - Search for music across platforms

<b>Supported Platforms:</b>
• <b>Qobuz</b> - Up to Hi-Res+ quality (24-bit/192kHz)
• <b>Tidal</b> - Up to Hi-Res/MQA quality (24-bit/96kHz)
• <b>Deezer</b> - Up to CD quality (16-bit/44.1kHz)
• <b>SoundCloud</b> - Up to 320 kbps

<b>Input Types:</b>
• Direct URLs from supported platforms
• ID format: <code>platform:type:id</code> (e.g., <code>qobuz:album:123456</code>)
• Last.fm playlist URLs (converted to source platforms)
• Batch files (text/JSON with multiple URLs/IDs)

<b>Quality Levels:</b>
• <b>0</b> - 128 kbps (~4MB/track)
• <b>1</b> - 320 kbps (~10MB/track)
• <b>2</b> - CD Quality 16-bit/44.1kHz (~35MB/track)
• <b>3</b> - Hi-Res 24-bit/≤96kHz (~80MB/track)
• <b>4</b> - Hi-Res+ 24-bit/≤192kHz (~150MB/track)

<b>Note:</b> Higher quality levels require premium subscriptions on respective platforms."""

streamrip_quality_flags = """<b>🎯 Quality & Format Flags</b>

Control the quality and format of your music downloads.

<b>Quality Selection:</b>
• <code>-q &lt;0-4&gt;</code> - Set quality level
  - <code>-q 0</code> - 128 kbps (smallest files)
  - <code>-q 1</code> - 320 kbps (good quality)
  - <code>-q 2</code> - CD Quality (lossless)
  - <code>-q 3</code> - Hi-Res (studio quality)
  - <code>-q 4</code> - Hi-Res+ (maximum quality)

<b>Codec Selection:</b>
• <code>-c &lt;codec&gt;</code> - Set audio codec
  - <code>-c flac</code> - Lossless compression (recommended)
  - <code>-c mp3</code> - Lossy compression, smaller files
  - <code>-c m4a</code> - Apple's format, good quality
  - <code>-c ogg</code> - Open source, good compression
  - <code>-c opus</code> - Modern codec, excellent quality

<b>Examples:</b>
• <code>/srm https://qobuz.com/album/... -q 3 -c flac</code>
• <code>/srl qobuz:album:123456 -q 2</code>
• <code>/srm -q 4 -c flac</code> (reply to URL)

<b>Platform Compatibility:</b>
• <b>Qobuz:</b> All quality levels (0-4)
• <b>Tidal:</b> Levels 0-3 (MQA support)
• <b>Deezer:</b> Levels 0-2 (HiFi subscription required for 2)
• <b>SoundCloud:</b> Levels 0-1 (free platform)"""

streamrip_download_flags = """<b>📁 Download Control Flags</b>

Customize how your music downloads are handled.

<b>File Naming:</b>
• <code>-n &lt;name&gt;</code> - Custom filename/folder name
  - <code>/srmirror url -n "My Album Collection"</code>
  - <code>/srleech url -n "Artist - Album (Year)"</code>

<b>Upload Control (Mirror only):</b>
• <code>-up &lt;path&gt;</code> - Custom upload path
• <code>-rcf &lt;flags&gt;</code> - Custom rclone flags
• <code>-sync</code> - Sync with cloud storage

<b>Telegram Upload (Leech only):</b>
• <code>-thumb &lt;url&gt;</code> - Custom thumbnail URL
• <code>-sp &lt;size&gt;</code> - Split size for large files
• <code>-cap &lt;caption&gt;</code> - Custom caption for uploads

<b>File Selection:</b>
• <code>-s</code> - Select specific files from multi-track downloads
• <code>-e &lt;extensions&gt;</code> - Exclude file extensions
• <code>-j</code> - Join files if multiple parts

<b>Upload Type:</b>
• <code>-doc</code> - Upload as document
• <code>-med</code> - Upload as media

<b>Headers & Authentication:</b>
• <code>-h &lt;headers&gt;</code> - Custom headers (key:value|key1:value1)

<b>Examples:</b>
• <code>/srm url -n "Jazz Collection" -up "Music/Jazz"</code>
• <code>/srl url -sp 2GB -doc -cap "High Quality Music"</code>"""

streamrip_media_tools = """<b>🎬 Media Tools Integration</b>

Enhance your music downloads with powerful media processing tools.

<b>Main Media Tools Flag:</b>
• <code>-mt</code> - Enable media tools processing

<b>Core Operations:</b>
• <code>-compress</code> - Enable compression
• <code>-extract</code> - Enable extraction
• <code>-add</code> - Enable adding tracks/metadata

<b>Compression Presets:</b>
• <code>-audio-fast</code> - Fast audio compression
• <code>-audio-medium</code> - Balanced audio compression
• <code>-audio-slow</code> - High-quality audio compression

<b>Specific Compression Types:</b>
• <code>-comp-audio</code> - Compress audio tracks
• <code>-comp-image</code> - Compress album artwork
• <code>-comp-document</code> - Compress metadata files
• <code>-comp-archive</code> - Compress final archive

<b>Extract Operations:</b>
• <code>-extract-audio</code> - Extract audio tracks
• <code>-extract-attachment</code> - Extract embedded files

<b>Add Operations:</b>
• <code>-add-audio</code> - Add audio tracks
• <code>-add-attachment</code> - Add metadata/artwork
• <code>-preserve</code> - Keep existing tracks when adding
• <code>-replace</code> - Replace existing tracks

<b>Examples:</b>
• <code>/srm url -mt -compress -audio-medium</code>
• <code>/srl url -mt -add-attachment -preserve</code>
• <code>/srm url -mt -comp-audio -extract-attachment</code>

<b>Note:</b> Media tools require additional processing time but provide enhanced output quality."""

streamrip_control_flags = """<b>🔧 Advanced Control Flags</b>

Fine-tune your streamrip downloads with advanced options.

<b>Archive & Security:</b>
• <code>-z &lt;password&gt;</code> - Archive password protection
  - <code>/srmirror url -z "mypassword"</code>
  - Works with compressed downloads

<b>Force Operations:</b>
• <code>-f</code> - Force run (bypass some checks)
• <code>-fd</code> - Force download (ignore cache)
• <code>-fu</code> - Force upload (re-upload existing)

<b>Processing Control:</b>
• <code>-s</code> - Select files from multi-track downloads
• <code>-j</code> - Join files if multiple parts
• <code>-e &lt;extensions&gt;</code> - Exclude file extensions
  - <code>-e "log,cue,m3u"</code> - Exclude metadata files

<b>Cloud Integration (Mirror):</b>
• <code>-sync</code> - Sync with cloud storage
• <code>-rcf &lt;flags&gt;</code> - Custom rclone flags
  - <code>-rcf "--buffer-size:8M|--transfers:4"</code>

<b>Upload Options (Leech):</b>
• <code>-doc</code> - Upload as document (preserves quality)
• <code>-med</code> - Upload as media (Telegram compression)

<b>Examples:</b>
• <code>/srm url -z "secure123" -sync -f</code>
• <code>/srl url -s -j -doc -e "log,cue"</code>
• <code>/srm url -rcf "--transfers:8" -fd</code>

<b>Tips:</b>
• Use <code>-doc</code> for lossless audio preservation
• Use <code>-s</code> for large albums to select specific tracks
• Combine flags for complex workflows"""

streamrip_examples = """<b>📋 Usage Examples</b>

Real-world examples of streamrip commands for different scenarios.

<b>🎵 Basic Downloads:</b>
• <code>/srm https://qobuz.com/album/xyz</code>
• <code>/srl https://tidal.com/browse/track/123</code>
• <code>/srs Daft Punk Random Access Memories</code>

<b>🎯 Quality-Focused Downloads:</b>
• <code>/srm qobuz:album:123456 -q 4 -c flac</code>
• <code>/srl tidal:album:789012 -q 3 -doc</code>
• <code>/srm url -q 2 -c flac -n "Lossless Collection"</code>

<b>📁 Organized Downloads:</b>
• <code>/srm url -n "Artist - Album (2023)" -up "Music/2023"</code>
• <code>/srl url -n "Jazz Essentials" -cap "High Quality Jazz"</code>

<b>🎬 Media Tools Enhanced:</b>
• <code>/srm url -mt -compress -audio-medium</code>
• <code>/srl url -mt -add-attachment -preserve</code>
• <code>/srm url -mt -comp-audio -extract-attachment</code>

<b>🔒 Secure Downloads:</b>
• <code>/srm url -z "mypassword" -compress</code>
• <code>/srl url -doc -z "secure123"</code>

<b>📦 Batch Processing:</b>
• Upload a text file with multiple URLs and use:
• <code>/srm -q 3 -c flac -mt</code> (reply to file)
• <code>/srl -doc -sp 2GB</code> (reply to file)

<b>🔍 Advanced Selection:</b>
• <code>/srm url -s -e "log,cue" -j</code>
• <code>/srl url -s -doc -thumb "https://image.url"</code>

<b>☁️ Cloud Integration:</b>
• <code>/srm url -sync -rcf "--transfers:8"</code>
• <code>/srm url -up "Music/Streamrip" -sync</code>

<b>💡 Pro Tips:</b>
• Combine quality and media tools for best results
• Use batch files for downloading entire discographies
• Select specific tracks from large albums with <code>-s</code>
• Use <code>-doc</code> for preserving audio quality in Telegram"""

streamrip_platforms = """<b>🎵 Platform Support & Features</b>

Detailed information about supported streaming platforms and their capabilities.

<b>🎯 Qobuz (Premium Recommended):</b>
• <b>Quality Levels:</b> 0-4 (up to 24-bit/192kHz)
• <b>Formats:</b> FLAC, MP3, M4A
• <b>Features:</b> Hi-Res audio, extensive classical catalog
• <b>Requirements:</b> Premium subscription for Hi-Res
• <b>Best For:</b> Audiophiles, classical music, jazz

<b>🌊 Tidal (HiFi/HiFi Plus):</b>
• <b>Quality Levels:</b> 0-3 (up to MQA 24-bit/96kHz)
• <b>Formats:</b> FLAC, MQA, AAC, MP3
• <b>Features:</b> MQA support, exclusive content
• <b>Requirements:</b> HiFi subscription for lossless
• <b>Best For:</b> Hip-hop, R&B, exclusive releases

<b>🎶 Deezer (HiFi):</b>
• <b>Quality Levels:</b> 0-2 (up to 16-bit/44.1kHz)
• <b>Formats:</b> FLAC, MP3, M4A
• <b>Features:</b> Large catalog, good discovery
• <b>Requirements:</b> HiFi subscription for CD quality
• <b>Best For:</b> Pop music, international content

<b>☁️ SoundCloud (Free/Pro):</b>
• <b>Quality Levels:</b> 0-1 (up to 320 kbps)
• <b>Formats:</b> MP3, AAC
• <b>Features:</b> Independent artists, remixes, podcasts
• <b>Requirements:</b> Free access, Pro for higher quality
• <b>Best For:</b> Independent music, DJ sets, podcasts

<b>🎵 Last.fm Integration:</b>
• <b>Playlist Support:</b> Convert Last.fm playlists to downloads
• <b>Scrobbling Data:</b> Use listening history for downloads
• <b>Discovery:</b> Find similar tracks and artists

<b>📋 Input Format Examples:</b>
• <b>Direct URLs:</b>
  - <code>https://qobuz.com/album/xyz</code>
  - <code>https://tidal.com/browse/track/123</code>
  - <code>https://deezer.com/album/456</code>
  - <code>https://soundcloud.com/artist/track</code>

• <b>ID Format:</b>
  - <code>qobuz:album:123456</code>
  - <code>tidal:track:789012</code>
  - <code>deezer:playlist:345678</code>
  - <code>soundcloud:user:901234</code>

• <b>Last.fm URLs:</b>
  - <code>https://last.fm/user/username/playlists/123</code>

<b>💡 Platform Tips:</b>
• Use Qobuz for highest quality classical and jazz
• Tidal excels for hip-hop and exclusive content
• Deezer offers great international music discovery
• SoundCloud is perfect for independent and remix content"""

STREAMRIP_HELP_DICT = {
    "main": streamrip_main,
    "Quality-Flags": streamrip_quality_flags,
    "Download-Flags": streamrip_download_flags,
    "Media-Tools": streamrip_media_tools,
    "Control-Flags": streamrip_control_flags,
    "Examples": streamrip_examples,
    "Platforms": streamrip_platforms,
}

RSS_HELP_MESSAGE = """
Use this format to add feed url:
Title1 link (required)
Title2 link -c cmd -inf xx -exf xx
Title3 link -c cmd -d ratio:time -z password

-c command -up mrcc:remote:path/subdir -rcf --buffer-size:8M|key|key:value
-inf For included words filter.
-exf For excluded words filter.
-stv true or false (sensitive filter)

<b>RSS Examples:</b>
Example: Title https://www.rss-url.com -inf 1080 or 720 or 144p|mkv or mp4|hevc -exf flv or web|xxx
This filter will parse links that its titles contain `(1080 or 720 or 144p) and (mkv or mp4) and hevc` and doesn't contain (flv or web) and xxx words. You can add whatever you want.

Another example: -inf  1080  or 720p|.web. or .webrip.|hvec or x264. This will parse titles that contain ( 1080  or 720p) and (.web. or .webrip.) and (hvec or x264). I have added space before and after 1080 to avoid wrong matching. If this `10805695` number in title it will match 1080 if added 1080 without spaces after it.

Filter Notes:
1. | means and.
2. Add `or` between similar keys, you can add it between qualities or between extensions, so don't add filter like this f: 1080|mp4 or 720|web because this will parse 1080 and (mp4 or 720) and web ... not (1080 and mp4) or (720 and web).
3. You can add `or` and `|` as much as you want.
4. Take a look at the title if it has a static special character after or before the qualities or extensions or whatever and use them in the filter to avoid wrong match.
Timeout: 60 sec.
"""

PASSWORD_ERROR_MESSAGE = """
<b>This link requires a password!</b>
- Insert <b>::</b> after the link and write the password after the sign.

<b>Example:</b> link::my password
"""


user_settings_text = {
    "DEFAULT_AI_PROVIDER": "Select the default AI provider to use with the /ask command. Options: mistral, deepseek. Timeout: 60 sec",
    "MISTRAL_API_URL": "Send your custom Mistral AI API URL. Leave empty to use the bot owner's API URL. Timeout: 60 sec",
    "DEEPSEEK_API_URL": "Send your custom DeepSeek AI API URL. Leave empty to use the bot owner's API URL. Timeout: 60 sec",
    # Metadata Settings
    "METADATA_KEY": "Set legacy metadata key for backward compatibility.\n\nExample: title=My Video,author=John Doe - set title and author\nExample: none - don't use legacy metadata\n\nThis is a legacy option, consider using the specific metadata options instead.\n\nTimeout: 60 sec",
    "METADATA_ALL": "Set metadata text to be used for all metadata fields (title, author, comment) for all track types.\n\nExample: My Project - apply to all metadata fields\nExample: none - don't set global metadata\n\nThis takes priority over all other metadata settings.\n\nTimeout: 60 sec",
    "METADATA_TITLE": "Set metadata text to be used for the global title field.\n\nExample: My Video - set title to 'My Video'\nExample: none - don't set global title\n\nTimeout: 60 sec",
    "METADATA_AUTHOR": "Set metadata text to be used for the global author field.\n\nExample: John Doe - set author to 'John Doe'\nExample: none - don't set global author\n\nTimeout: 60 sec",
    "METADATA_COMMENT": "Set metadata text to be used for the global comment field.\n\nExample: Created with Telegram Bot - add a comment\nExample: none - don't set global comment\n\nTimeout: 60 sec",
    "METADATA_VIDEO_TITLE": "Set metadata text to be used specifically for video track titles.\n\nExample: Episode 1 - set video track title\nExample: none - don't set video track title\n\nTimeout: 60 sec",
    "METADATA_VIDEO_AUTHOR": "Set metadata text to be used specifically for video track authors.\n\nExample: Director Name - set video track author\nExample: none - don't set video track author\n\nTimeout: 60 sec",
    "METADATA_VIDEO_COMMENT": "Set metadata text to be used specifically for video track comments.\n\nExample: 4K HDR Version - add video track comment\nExample: none - don't set video track comment\n\nTimeout: 60 sec",
    "METADATA_AUDIO_TITLE": "Set metadata text to be used specifically for audio track titles.\n\nExample: Song Name - set audio track title\nExample: none - don't set audio track title\n\nTimeout: 60 sec",
    "METADATA_AUDIO_AUTHOR": "Set metadata text to be used specifically for audio track authors.\n\nExample: Artist Name - set audio track author\nExample: none - don't set audio track author\n\nTimeout: 60 sec",
    "METADATA_AUDIO_COMMENT": "Set metadata text to be used specifically for audio track comments.\n\nExample: 320kbps Stereo - add audio track comment\nExample: none - don't set audio track comment\n\nTimeout: 60 sec",
    "METADATA_SUBTITLE_TITLE": "Set metadata text to be used specifically for subtitle track titles.\n\nExample: English Subtitles - set subtitle track title\nExample: none - don't set subtitle track title\n\nTimeout: 60 sec",
    "METADATA_SUBTITLE_AUTHOR": "Set metadata text to be used specifically for subtitle track authors.\n\nExample: Translator Name - set subtitle track author\nExample: none - don't set subtitle track author\n\nTimeout: 60 sec",
    "METADATA_SUBTITLE_COMMENT": "Set metadata text to be used specifically for subtitle track comments.\n\nExample: Full Translation - add subtitle track comment\nExample: none - don't set subtitle track comment\n\nTimeout: 60 sec",
    "USER_SESSION": "Send your pyrogram user session string for download from private telegram chat. Timeout: 60 sec",
    "USER_DUMP": "Send your channel or group id where you want to store your leeched files. Bot must have permission to send message in your chat. Timeout: 60 sec",
    "USER_COOKIES": "Send your cookies.txt file for YouTube and other yt-dlp downloads. This will be used instead of the owner's cookies file. Create it using browser extensions like 'Get cookies.txt' or 'EditThisCookie'. Timeout: 60 sec",
    "LEECH_FILENAME_CAPTION": """Send caption template for all your leech files.

<b>Basic Variables:</b>
• <code>{filename}</code> - Filename without extension
• <code>{ext}</code> - File extension
• <code>{size}</code> - File size
• <code>{quality}</code> - Video quality
• <code>{duration}</code> - Media duration
• <code>{season}</code>, <code>{episode}</code> - TV show info

<b>Styling:</b>
• HTML: <code>{{filename}bold}</code>
• Google Fonts: <code>{{filename}Roboto}</code>
• Unicode: <code>{{filename}serif_b}</code>
• Emoji: <code>{{filename}🔥}</code>

<b>Examples:</b>
• <code>📁 {{filename}bold} | 💾 {size}</code>
• <code>🎬 {{filename}Roboto:700} [{quality}]</code>

Use /fontstyles for more options.

Timeout: 60 sec""",
    "LEECH_SPLIT_SIZE": "Send Leech split size in bytes or use gb or mb. Example: 40000000 or 2.5gb or 1000mb. IS_PREMIUM_USER: {TgClient.IS_PREMIUM_USER}. Timeout: 60 sec",
    "LEECH_DUMP_CHAT": """"Send leech destination ID/USERNAME/PM. You can specify multiple destinations separated by commas.
* b:id/@username/pm (b: means leech by bot) (id or username of the chat or write pm means private message so bot will send the files in private to you) when you should use b:(leech by bot)? When your default settings is leech by user and you want to leech by bot for specific task.
* u:id/@username(u: means leech by user) This incase OWNER added USER_SESSION_STRING.
* h:id/@username(hybrid leech) h: to upload files by bot and user based on file size.
* For multiple destinations, use comma-separated values: -100123456789,-100987654321
* id/@username|topic_id(leech in specific chat and topic) add | without space and write topic id after chat id or username. Timeout: 60 sec""",
    "LOG_CHAT_ID": "Send log chat ID for mirror tasks. You can specify multiple chat IDs separated by commas (e.g., -100123456789,-100987654321). Timeout: 60 sec",
    "LEECH_FILENAME_PREFIX": r"Send Leech Filename Prefix. You can add HTML tags. Example: <code>@mychannel</code>. Timeout: 60 sec",
    "LEECH_SUFFIX": r"Send Leech Filename Suffix. You can add HTML tags. Example: <code>@mychannel</code>. Timeout: 60 sec",
    "LEECH_FONT": "Send Leech Font Style. Options: HTML formats (bold, italic), Unicode styles (serif, sans_b), Google Fonts (Roboto, Open Sans), or emojis (🔥). Use /fontstyles for full list. Timeout: 60 sec",
    "LEECH_FILENAME": """Send Leech Filename template. This will change the actual filename of all your leech files.

<b>Basic Variables:</b>
• <code>{filename}</code> - Original filename without extension
• <code>{ext}</code> - File extension (e.g., mkv, mp4)
• <code>{size}</code> - File size (e.g., 1.5GB)
• <code>{quality}</code> - Video quality (e.g., 1080p, 720p)

<b>TV Show Variables:</b>
• <code>{season}</code> - Season number extracted from filename
• <code>{episode}</code> - Episode number extracted from filename
• <code>{year}</code> - Release year extracted from filename

<b>Media Information:</b>
• <code>{codec}</code> - Video codec (e.g., HEVC, AVC)
• <code>{framerate}</code> - Video framerate
• <code>{format}</code> - Media container format
• <code>{formate}</code> - File extension in uppercase

<b>Examples:</b>
• <code>{filename} [{quality}]</code>
• <code>{filename} S{season}E{episode} [{quality}]</code>
• <code>{filename} ({year}) [{codec}]</code>
• <code>Series S{season}E{episode} [{quality}] [{codec}]</code>

Use /fontstyles to see all available template variables.

Timeout: 60 sec""",
    "THUMBNAIL_LAYOUT": "Send thumbnail layout (widthxheight, 2x2, 3x3, 2x4, 4x4, ...). Example: 3x3. Timeout: 60 sec",
    "RCLONE_PATH": "Send Rclone Path. If you want to use your rclone config edit using owner/user config from usetting or add mrcc: before rclone path. Example mrcc:remote:folder. Timeout: 60 sec",
    "RCLONE_FLAGS": "key:value|key|key|key:value . Check here all <a href='https://rclone.org/flags/'>RcloneFlags</a>\nEx: --buffer-size:8M|--drive-starred-only",
    "GDRIVE_ID": "Send Gdrive ID. If you want to use your token.pickle edit using owner/user token from usetting or add mtp: before the id. Example: mtp:F435RGGRDXXXXXX . Timeout: 60 sec",
    "INDEX_URL": "Send Index URL. Timeout: 60 sec",
    "UPLOAD_PATHS": "Send Dict of keys that have path values. Example: {'path 1': 'remote:rclonefolder', 'path 2': 'gdrive1 id', 'path 3': 'tg chat id', 'path 4': 'mrcc:remote:', 'path 5': b:@username} . Timeout: 60 sec",
    "EXCLUDED_EXTENSIONS": "Send exluded extenions separated by space without dot at beginning. Timeout: 60 sec",
    "NAME_SUBSTITUTE": r"""Word Subtitions. You can add pattern instead of normal text. Timeout: 60 sec
NOTE: You must add \ before any character, those are the characters: \^$.|?*+()[]{}-
Example: script/code/s | mirror/leech | tea/ /s | clone | cpu/ | \[mltb\]/mltb | \\text\\/text/s
1. script will get replaced by code with sensitive case
2. mirror will get replaced by leech
4. tea will get replaced by space with sensitive case
5. clone will get removed
6. cpu will get replaced by space
7. [mltb] will get replaced by mltb
8. \text\ will get replaced by text with sensitive case
""",
    "YT_DLP_OPTIONS": """Send dict of YT-DLP Options. Timeout: 60 sec
Format: {key: value, key: value, key: value}.
Example: {"format": "bv*+mergeall[vcodec=none]", "nocheckcertificate": True, "playliststart": 10, "fragment_retries": float("inf"), "matchtitle": "S13", "writesubtitles": True, "live_from_start": True, "postprocessor_args": {"xtra": ["-threads", "4"]}, "wait_for_video": (5, 100), "download_ranges": [{"start_time": 0, "end_time": 10}]}
Check all yt-dlp api options from this <a href='https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/YoutubeDL.py#L184'>FILE</a> or use this <a href='https://t.me/mltb_official_channel/177'>script</a> to convert cli arguments to api options.""",
    "FFMPEG_CMDS": """Read this guide. http://telegra.ph/Ffmpeg-guide-01-10""",
    "HELPER_TOKENS": """Send your helper bot tokens separated by space. These bots will be used for hyper download to speed up your downloads.
Example: 1234567890:ABCDEFGHIJKLMNOPQRSTUVWXYZ 0987654321:ZYXWVUTSRQPONMLKJIHGFEDCBA

NOTE: You can add up to 20 helper bots. Make sure the bots are created using @BotFather and are not being used by any other bot.
To use these bots, you need to enable them using the 'Enable Helper Bots' button in the leech settings menu.
Timeout: 60 sec""",
    "ENABLE_HELPER_BOTS": """Enable or disable helper bots for hyper download.
When enabled, both your helper bots and the owner's helper bots will be used for downloads.
When disabled, only the owner's helper bots will be used.
Timeout: 60 sec""",
}

# Media tools help text dictionary with detailed examples and consistent formatting
# This is the MAIN dictionary that should be used for all media tools help text
# All entries follow the same format:
# - Clear description of the setting
# - Examples with explanations
# - Timeout information (where applicable)
media_tools_text = {
    "MEDIA_TOOLS_ENABLED": "Enable or disable media tools features. You can enable specific tools by providing a comma-separated list.\n\nExample: true - enable all media tools\nExample: watermark,merge,convert - enable only these tools\nExample: false - disable all media tools\n\nAvailable tools: watermark, merge, convert, compression, trim, extract, add, metadata, ffmpeg, sample\n\nTimeout: 60 sec",
    "MEDIA_TOOLS_PRIORITY": "Set priority for media tools processing. Lower number means higher priority.\n\nExample: 1 - highest priority\nExample: 10 - lower priority\n\nTimeout: 60 sec",
    # Watermark Settings
    "WATERMARK_ENABLED": "Enable or disable watermark feature. Send 'true' to enable or 'false' to disable.\n\nExample: true - enable watermark\nExample: false - disable watermark\n\nPriority:\n1. Global (enabled) & User (disabled) -> Apply global\n2. User (enabled) & Global (disabled) -> Apply user\n3. Global (enabled) & User (enabled) -> Apply user\n4. Global (disabled) & User (disabled) -> Don't apply\n\nUse the Reset button to reset all watermark settings to default.",
    "WATERMARK_KEY": "Send your text which will be added as watermark in all mkv videos.\n\nExample: My Watermark Text\n\nTimeout: 60 sec",
    "WATERMARK_POSITION": "Send watermark position. Valid options: top_left, top_right, bottom_left, bottom_right, center, top_center, bottom_center, left_center, right_center.\n\nExample: bottom_right - place in bottom right corner\nExample: center - place in center of video\n\nTimeout: 60 sec",
    "WATERMARK_SIZE": "Send watermark font size (integer value).\n\nExample: 20 - medium size\nExample: 36 - larger size\n\nTimeout: 60 sec",
    "WATERMARK_COLOR": "Send watermark text color.\n\nExample: white - white text\nExample: black - black text\nExample: red - red text\nExample: #FF00FF - custom color (magenta)\n\nTimeout: 60 sec",
    "WATERMARK_FONT": "Send font name for watermark text. You can use a Google Font name or a font file name if available in the bot's directory.\n\nExample: Roboto - Google font\nExample: Arial - common font\nExample: default.otf - use default font\n\nTimeout: 60 sec",
    "WATERMARK_OPACITY": "Set the opacity level for watermark text (0.0-1.0). Lower values make the watermark more transparent.\n\nExample: 0.5 - 50% opacity (semi-transparent)\nExample: 1.0 - 100% opacity (fully visible)\nExample: 0.2 - 20% opacity (mostly transparent)\n\nTimeout: 60 sec",
    "WATERMARK_PRIORITY": "Set priority for watermark processing. Lower number means higher priority.\n\nExample: 1 - highest priority\nExample: 10 - lower priority\n\nTimeout: 60 sec",
    "WATERMARK_THREADING": "Enable or disable threading for watermark processing.\n\nExample: true - enable threading (faster processing)\nExample: false - disable threading\n\nTimeout: 60 sec",
    "WATERMARK_THREAD_NUMBER": "Set the number of threads to use for watermark processing.\n\nExample: 2 - use 2 threads\nExample: 4 - use 4 threads\n\nTimeout: 60 sec",
    "WATERMARK_QUALITY": "Set the quality value for watermark processing.\n\nExample: 23 - good quality (lower is better)\nExample: 18 - high quality\nExample: none - use default quality\n\nTimeout: 60 sec",
    "WATERMARK_SPEED": "Set the speed value for watermark processing.\n\nExample: ultrafast - fastest processing\nExample: medium - balanced speed and quality\nExample: veryslow - best quality\nExample: none - use default speed\n\nTimeout: 60 sec",
    "WATERMARK_REMOVE_ORIGINAL": "Enable or disable removing original files after watermarking.\n\nExample: true - delete original files after watermarking\nExample: false - keep original files\n\nYou can also use the -del flag in commands to override this setting.\n\nTimeout: 60 sec",
    "AUDIO_WATERMARK_INTERVAL": "Set the interval in seconds for audio watermarks.\n\nExample: 30 - add watermark every 30 seconds\nExample: 60 - add watermark every minute\nExample: 0 - disable interval (default)\n\nTimeout: 60 sec",
    "AUDIO_WATERMARK_VOLUME": "Set the volume of the audio watermark relative to the original audio.\n\nExample: 0.5 - half the volume of the original\nExample: 0.2 - subtle watermark\nExample: 1.0 - same volume as the original\n\nTimeout: 60 sec",
    "SUBTITLE_WATERMARK_INTERVAL": "Set the interval in seconds for subtitle watermarks.\n\nExample: 30 - add watermark every 30 seconds\nExample: 60 - add watermark every minute\nExample: 0 - disable interval (default)\n\nTimeout: 60 sec",
    "SUBTITLE_WATERMARK_STYLE": "Set the style of the subtitle watermark.\n\nExample: normal - standard subtitle style\nExample: bold - bold text\nExample: italic - italic text\nExample: bold_italic - bold and italic text\n\nTimeout: 60 sec",
    "IMAGE_WATERMARK_ENABLED": "Enable or disable image watermark feature.\n\nExample: true - enable image watermark\nExample: false - disable image watermark\n\nTimeout: 60 sec",
    "IMAGE_WATERMARK_PATH": "Set the path to the watermark image file.\n\nExample: /path/to/watermark.png\n\nThe image should preferably be a PNG with transparency for best results.\n\nTimeout: 60 sec",
    "IMAGE_WATERMARK_SCALE": "Set the scale of the watermark image as a percentage of the video width.\n\nExample: 10 - watermark will be 10% of the video width\nExample: 20 - watermark will be 20% of the video width\n\nTimeout: 60 sec",
    "IMAGE_WATERMARK_OPACITY": "Set the opacity of the watermark image.\n\nExample: 0.7 - 70% opacity\nExample: 0.5 - 50% opacity\nExample: 1.0 - 100% opacity (fully visible)\n\nTimeout: 60 sec",
    "IMAGE_WATERMARK_POSITION": "Set the position of the watermark image on the media.\n\nExample: bottom_right - place in bottom right corner\nExample: center - place in the center of the video\n\nTimeout: 60 sec",
    # Merge Settings
    "MERGE_ENABLED": "Enable or disable merge feature. Send 'true' to enable or 'false' to disable.\n\nExample: true - enable merge\nExample: false - disable merge\n\nPriority:\n1. Global (enabled) & User (disabled) -> Apply global\n2. User (enabled) & Global (disabled) -> Apply user\n3. Global (enabled) & User (enabled) -> Apply user\n4. Global (disabled) & User (disabled) -> Don't apply\n\nUse the Reset button to reset all merge settings to default.",
    "CONCAT_DEMUXER_ENABLED": "Enable or disable concat demuxer for merging.\n\nExample: true - enable concat demuxer\nExample: false - disable concat demuxer\n\nTimeout: 60 sec",
    "FILTER_COMPLEX_ENABLED": "Enable or disable filter complex for merging.\n\nExample: true - enable filter complex\nExample: false - disable filter complex\n\nTimeout: 60 sec",
    # Output formats
    "MERGE_OUTPUT_FORMAT_VIDEO": "Set output format for merged videos. Common formats: mkv, mp4, avi, webm.\n\nExample: mkv - container that supports almost all codecs\nExample: mp4 - widely compatible format\n\nTimeout: 60 sec",
    "MERGE_OUTPUT_FORMAT_AUDIO": "Set output format for merged audios. Common formats: mp3, m4a, flac, wav.\n\nExample: mp3 - widely compatible format\nExample: flac - lossless audio format\n\nTimeout: 60 sec",
    "MERGE_OUTPUT_FORMAT_IMAGE": "Set output format for merged images. Common formats: jpg, png, webp, tiff.\n\nExample: jpg - good compression, smaller files\nExample: png - lossless format with transparency support\n\nTimeout: 60 sec",
    "MERGE_OUTPUT_FORMAT_DOCUMENT": "Set output format for merged documents. Currently only pdf is supported.\n\nExample: pdf - standard document format\n\nTimeout: 60 sec",
    "MERGE_OUTPUT_FORMAT_SUBTITLE": "Set output format for merged subtitles. Common formats: srt, vtt, ass.\n\nExample: srt - simple subtitle format\nExample: ass - advanced subtitle format with styling\n\nTimeout: 60 sec",
    # Video settings
    "MERGE_VIDEO_CODEC": "Set the video codec for merged videos. Options: copy, h264, h265, vp9, av1.\n\nExample: copy - preserves original codec (fastest)\nExample: h264 - widely compatible codec\n\nTimeout: 60 sec",
    "MERGE_VIDEO_QUALITY": "Set the quality preset for video encoding. Options: low, medium, high, veryhigh.\n\nExample: medium - balanced quality and file size\nExample: high - better quality but larger file size\n\nTimeout: 60 sec",
    "MERGE_VIDEO_PRESET": "Set the encoding preset for video. Options: ultrafast to veryslow.\n\nExample: medium - balanced encoding speed and compression\nExample: slow - better compression but slower encoding\n\nTimeout: 60 sec",
    "MERGE_VIDEO_CRF": "Set the Constant Rate Factor for video quality (0-51, lower is better).\n\nExample: 23 - default value, good balance\nExample: 18 - visually lossless quality\n\nTimeout: 60 sec",
    "MERGE_VIDEO_PIXEL_FORMAT": "Set the pixel format for video. Common formats: yuv420p, yuv444p.\n\nExample: yuv420p - most compatible format\nExample: yuv444p - highest quality but larger file size\n\nTimeout: 60 sec",
    "MERGE_VIDEO_TUNE": "Set the tuning parameter for video encoding. Options: film, animation, grain, etc.\n\nExample: film - for live-action content\nExample: animation - for animated content\n\nTimeout: 60 sec",
    "MERGE_VIDEO_FASTSTART": "Enable or disable faststart flag for MP4 files. Allows videos to start playing before fully downloaded.\n\nExample: true - enable faststart\nExample: false - disable faststart\n\nTimeout: 60 sec",
    # Audio settings
    "MERGE_AUDIO_CODEC": "Set the audio codec for merged audio. Options: copy, aac, mp3, opus, flac.\n\nExample: copy - preserves original codec (fastest)\nExample: aac - good quality and compatibility\n\nTimeout: 60 sec",
    "MERGE_AUDIO_BITRATE": "Set the audio bitrate for merged audio. Examples: 128k, 192k, 320k.\n\nExample: 192k - good quality for most content\nExample: 320k - high quality audio\n\nTimeout: 60 sec",
    "MERGE_AUDIO_CHANNELS": "Set the number of audio channels. Common values: 1 (mono), 2 (stereo).\n\nExample: 2 - stereo audio\nExample: 1 - mono audio\n\nTimeout: 60 sec",
    "MERGE_AUDIO_SAMPLING": "Set the audio sampling rate in Hz. Common values: 44100, 48000.\n\nExample: 44100 - CD quality\nExample: 48000 - DVD/professional audio quality\n\nTimeout: 60 sec",
    "MERGE_AUDIO_VOLUME": "Set the volume adjustment factor (0.0-10.0).\n\nExample: 1.0 - original volume\nExample: 2.0 - double volume\n\nTimeout: 60 sec",
    # Image settings
    "MERGE_IMAGE_MODE": "Set the mode for image merging. Options: auto, horizontal, vertical, collage.\n\nExample: auto - choose based on number of images\nExample: collage - grid layout\n\nTimeout: 60 sec",
    "MERGE_IMAGE_COLUMNS": "Set the number of columns for image collage mode.\n\nExample: 2 - two images per row\nExample: 3 - three images per row\n\nTimeout: 60 sec",
    "MERGE_IMAGE_QUALITY": "Set the quality for image output (1-100). Higher values mean better quality but larger file size.\n\nExample: 90 - high quality\nExample: 75 - good balance of quality and size\n\nTimeout: 60 sec",
    "MERGE_IMAGE_DPI": "Set the DPI (dots per inch) for merged images.\n\nExample: 300 - good for printing\nExample: 72 - standard screen resolution\n\nTimeout: 60 sec",
    "MERGE_IMAGE_RESIZE": "Set the size to resize images to. Format: widthxheight or 'none'.\n\nExample: none - keep original size\nExample: 1920x1080 - resize to Full HD\n\nTimeout: 60 sec",
    "MERGE_IMAGE_BACKGROUND": "Set the background color for image merging.\n\nExample: white - white background\nExample: #FF0000 - red background\n\nTimeout: 60 sec",
    # Subtitle settings
    "MERGE_SUBTITLE_ENCODING": "Set the character encoding for subtitle files.\n\nExample: utf-8 - universal encoding\nExample: latin1 - for Western European languages\n\nTimeout: 60 sec",
    "MERGE_SUBTITLE_FONT": "Set the font for subtitle rendering.\n\nExample: Arial - widely available font\nExample: DejaVu Sans - good for multiple languages\n\nTimeout: 60 sec",
    "MERGE_SUBTITLE_FONT_SIZE": "Set the font size for subtitle rendering.\n\nExample: 24 - medium size\nExample: 32 - larger size for better readability\n\nTimeout: 60 sec",
    "MERGE_SUBTITLE_FONT_COLOR": "Set the font color for subtitle text.\n\nExample: white - white text\nExample: #FFFF00 - yellow text\n\nTimeout: 60 sec",
    "MERGE_SUBTITLE_BACKGROUND": "Set the background color for subtitle text.\n\nExample: black - black background\nExample: transparent - no background\n\nTimeout: 60 sec",
    # Document settings
    "MERGE_DOCUMENT_PAPER_SIZE": "Set the paper size for document output.\n\nExample: a4 - standard international paper size\nExample: letter - standard US paper size\n\nTimeout: 60 sec",
    "MERGE_DOCUMENT_ORIENTATION": "Set the orientation for document output.\n\nExample: portrait - vertical orientation\nExample: landscape - horizontal orientation\n\nTimeout: 60 sec",
    "MERGE_DOCUMENT_MARGIN": "Set the margin size in points for document output.\n\nExample: 50 - standard margin\nExample: 0 - no margin\n\nTimeout: 60 sec",
    # Metadata settings
    "MERGE_METADATA_TITLE": "Set the title metadata for the merged file.\n\nExample: My Video - sets the title to 'My Video'\nExample: empty - no title metadata\n\nTimeout: 60 sec",
    "MERGE_METADATA_AUTHOR": "Set the author metadata for the merged file.\n\nExample: John Doe - sets the author to 'John Doe'\nExample: empty - no author metadata\n\nTimeout: 60 sec",
    "MERGE_METADATA_COMMENT": "Set the comment metadata for the merged file.\n\nExample: Created with Telegram Bot - adds a comment\nExample: empty - no comment metadata\n\nTimeout: 60 sec",
    # General settings
    "MERGE_REMOVE_ORIGINAL": "Enable or disable removing original files after successful merge.\n\nExample: true - remove original files after merge\nExample: false - keep original files\n\nTimeout: 60 sec",
    "MERGE_PRIORITY": "Set priority for merge processing. Lower number means higher priority.\n\nExample: 1 - highest priority\nExample: 10 - lower priority\n\nTimeout: 60 sec",
    "MERGE_THREADING": "Enable or disable threading for merge processing.\n\nExample: true - enable parallel processing\nExample: false - disable parallel processing\n\nTimeout: 60 sec",
    "MERGE_THREAD_NUMBER": "Set the number of threads to use for merge processing.\n\nExample: 4 - process up to 4 files simultaneously\nExample: 1 - process one file at a time\n\nTimeout: 60 sec",
    # Convert Settings
    "CONVERT_ENABLED": "Enable or disable convert feature. Send 'true' to enable or 'false' to disable.\n\nExample: true - enable convert feature\nExample: false - disable convert feature\n\nPriority:\n1. Global (enabled) & User (disabled) -> Apply global\n2. User (enabled) & Global (disabled) -> Apply user\n3. Global (enabled) & User (enabled) -> Apply user\n4. Global (disabled) & User (disabled) -> Don't apply\n\nUse the Reset button to reset all convert settings to default.\n\nTimeout: 60 sec",
    "CONVERT_PRIORITY": "Set priority for convert processing. Lower number means higher priority.\n\nExample: 1 - highest priority\nExample: 10 - lower priority\n\nTimeout: 60 sec",
    "CONVERT_DELETE_ORIGINAL": "Enable or disable deleting original files after conversion.\n\nExample: true - delete original files after conversion\nExample: false - keep original files\n\nThis can be overridden by using the -del flag in the command.\n\nTimeout: 60 sec",
    # Video Convert Settings
    "CONVERT_VIDEO_ENABLED": "Enable or disable video conversion.\n\nExample: true - enable video conversion\nExample: false - disable video conversion\n\nTimeout: 60 sec",
    "CONVERT_VIDEO_FORMAT": "Set the output format for converted videos. Common formats: mp4, mkv, avi, webm.\n\nExample: mp4 - widely compatible format\nExample: mkv - container that supports almost all codecs\n\nTimeout: 60 sec",
    "CONVERT_VIDEO_CODEC": "Set the video codec for converted videos. Common codecs: libx264, libx265, libvpx-vp9.\n\nExample: libx264 - widely compatible codec\nExample: libx265 - better compression but less compatible\n\nTimeout: 60 sec",
    "CONVERT_VIDEO_QUALITY": "Set the quality preset for video encoding. Options: ultrafast, superfast, veryfast, faster, fast, medium, slow, slower, veryslow.\n\nExample: medium - balanced encoding speed and compression\nExample: slow - better compression but slower encoding\n\nTimeout: 60 sec",
    "CONVERT_VIDEO_CRF": "Set the Constant Rate Factor for video quality (0-51, lower is better).\n\nExample: 23 - default value, good balance\nExample: 18 - visually lossless quality\n\nTimeout: 60 sec",
    "CONVERT_VIDEO_PRESET": "Set the encoding preset for video. Options: ultrafast to veryslow.\n\nExample: medium - balanced encoding speed and compression\nExample: slow - better compression but slower encoding\n\nTimeout: 60 sec",
    "CONVERT_VIDEO_MAINTAIN_QUALITY": "Enable or disable maintaining high quality for video conversion.\n\nExample: true - use higher quality settings\nExample: false - use standard quality settings\n\nTimeout: 60 sec",
    "CONVERT_VIDEO_DELETE_ORIGINAL": "Enable or disable deleting original files after video conversion.\n\nExample: true - delete original files after conversion\nExample: false - keep original files\n\nTimeout: 60 sec",
    "CONVERT_VIDEO_RESOLUTION": "Set the resolution for video conversion. Format: widthxheight or 'none'.\n\nExample: 1920x1080 - Full HD\nExample: 1280x720 - HD\nExample: none - keep original resolution\n\nTimeout: 60 sec",
    "CONVERT_VIDEO_FPS": "Set the frame rate for video conversion.\n\nExample: 30 - 30 frames per second\nExample: 60 - 60 frames per second\nExample: none - keep original frame rate\n\nTimeout: 60 sec",
    # Audio Convert Settings
    "CONVERT_AUDIO_ENABLED": "Enable or disable audio conversion.\n\nExample: true - enable audio conversion\nExample: false - disable audio conversion\n\nTimeout: 60 sec",
    "CONVERT_AUDIO_FORMAT": "Set the output format for converted audio. Common formats: mp3, m4a, flac, wav, ogg.\n\nExample: mp3 - widely compatible format\nExample: flac - lossless audio format\n\nTimeout: 60 sec",
    "CONVERT_AUDIO_CODEC": "Set the audio codec for converted audio. Common codecs: libmp3lame, aac, libopus, flac.\n\nExample: libmp3lame - for MP3 encoding\nExample: aac - good quality and compatibility\n\nTimeout: 60 sec",
    "CONVERT_AUDIO_BITRATE": "Set the audio bitrate for converted audio. Examples: 128k, 192k, 320k.\n\nExample: 192k - good quality for most content\nExample: 320k - high quality audio\n\nTimeout: 60 sec",
    "CONVERT_AUDIO_CHANNELS": "Set the number of audio channels. Common values: 1 (mono), 2 (stereo).\n\nExample: 2 - stereo audio\nExample: 1 - mono audio\n\nTimeout: 60 sec",
    "CONVERT_AUDIO_SAMPLING": "Set the audio sampling rate in Hz. Common values: 44100, 48000.\n\nExample: 44100 - CD quality\nExample: 48000 - DVD/professional audio quality\n\nTimeout: 60 sec",
    "CONVERT_AUDIO_VOLUME": "Set the volume adjustment factor (0.0-10.0).\n\nExample: 1.0 - original volume\nExample: 2.0 - double volume\n\nTimeout: 60 sec",
    "CONVERT_AUDIO_DELETE_ORIGINAL": "Enable or disable deleting original files after audio conversion.\n\nExample: true - delete original files after conversion\nExample: false - keep original files\n\nTimeout: 60 sec",
    # Document Convert Settings
    "CONVERT_DOCUMENT_ENABLED": "Enable or disable document conversion.\n\nExample: true - enable document conversion\nExample: false - disable document conversion\n\nTimeout: 60 sec",
    "CONVERT_DOCUMENT_FORMAT": "Set the output format for converted documents. Common formats: pdf, docx, txt.\n\nExample: pdf - standard document format\nExample: docx - Microsoft Word format\nExample: none - use default format\n\nTimeout: 60 sec",
    "CONVERT_DOCUMENT_QUALITY": "Set the quality for document conversion (0-100). Higher values mean better quality but larger file size.\n\nExample: 90 - high quality\nExample: 75 - good balance of quality and size\nExample: none - use default quality\n\nTimeout: 60 sec",
    "CONVERT_DOCUMENT_DPI": "Set the DPI (dots per inch) for document conversion.\n\nExample: 300 - high quality (good for printing)\nExample: 150 - good balance of quality and size\nExample: 72 - screen resolution (smaller file size)\n\nTimeout: 60 sec",
    "CONVERT_DOCUMENT_DELETE_ORIGINAL": "Enable or disable deleting original files after document conversion.\n\nExample: true - delete original files after conversion\nExample: false - keep original files\n\nTimeout: 60 sec",
    # Archive Convert Settings
    "CONVERT_ARCHIVE_ENABLED": "Enable or disable archive conversion.\n\nExample: true - enable archive conversion\nExample: false - disable archive conversion\n\nTimeout: 60 sec",
    "CONVERT_ARCHIVE_FORMAT": "Set the output format for converted archives. Common formats: zip, 7z, tar.gz.\n\nExample: zip - widely compatible format\nExample: 7z - better compression but less compatible\nExample: none - use default format\n\nTimeout: 60 sec",
    "CONVERT_ARCHIVE_LEVEL": "Set the compression level for archive conversion (1-9). Higher values mean better compression but slower processing.\n\nExample: 5 - good balance of speed and compression\nExample: 9 - maximum compression\nExample: 1 - fastest compression\n\nTimeout: 60 sec",
    "CONVERT_ARCHIVE_METHOD": "Set the compression method for archive conversion. Options: deflate, store, bzip2, lzma.\n\nExample: deflate - good balance of speed and compression\nExample: lzma - best compression but slowest\nExample: store - no compression (fastest)\n\nTimeout: 60 sec",
    "CONVERT_ARCHIVE_DELETE_ORIGINAL": "Enable or disable deleting original files after archive conversion.\n\nExample: true - delete original files after conversion\nExample: false - keep original files\n\nTimeout: 60 sec",
    # Subtitle Convert Settings
    "CONVERT_SUBTITLE_ENABLED": "Enable or disable subtitle conversion.\n\nExample: true - enable subtitle conversion\nExample: false - disable subtitle conversion\n\nTimeout: 60 sec",
    "CONVERT_SUBTITLE_FORMAT": "Set the output format for converted subtitles. Common formats: srt, ass, vtt.\n\nExample: srt - simple subtitle format\nExample: ass - advanced subtitle format with styling\nExample: none - use default format\n\nTimeout: 60 sec",
    "CONVERT_SUBTITLE_ENCODING": "Set the character encoding for subtitle conversion.\n\nExample: utf-8 - universal encoding\nExample: latin1 - for Western European languages\nExample: none - use default encoding\n\nTimeout: 60 sec",
    "CONVERT_SUBTITLE_LANGUAGE": "Set the language code for subtitle conversion.\n\nExample: eng - English\nExample: spa - Spanish\nExample: none - don't set language\n\nTimeout: 60 sec",
    "CONVERT_SUBTITLE_DELETE_ORIGINAL": "Enable or disable deleting original files after subtitle conversion.\n\nExample: true - delete original files after conversion\nExample: false - keep original files\n\nTimeout: 60 sec",
    # Compression Settings
    "COMPRESSION_ENABLED": "Enable or disable compression feature. Send 'true' to enable or 'false' to disable.\n\nExample: true - enable compression feature\nExample: false - disable compression feature\n\nPriority:\n1. Global (enabled) & User (disabled) -> Apply global\n2. User (enabled) & Global (disabled) -> Apply user\n3. Global (enabled) & User (enabled) -> Apply user\n4. Global (disabled) & User (disabled) -> Don't apply\n\nUse the Reset button to reset all compression settings to default.\n\nTimeout: 60 sec",
    "COMPRESSION_PRIORITY": "Set priority for compression processing. Lower number means higher priority.\n\nExample: 1 - highest priority\nExample: 10 - lower priority\n\nTimeout: 60 sec",
    "COMPRESSION_DELETE_ORIGINAL": "Enable or disable deleting original files after compression.\n\nExample: true - delete original files after compression\nExample: false - keep original files after compression\n\nTimeout: 60 sec",
    # Video Compression Settings
    "COMPRESSION_VIDEO_ENABLED": "Enable or disable video compression.\n\nExample: true - enable video compression\nExample: false - disable video compression\n\nTimeout: 60 sec",
    "COMPRESSION_VIDEO_PRESET": "Set the compression preset for videos. Options: fast, medium, slow.\n\nExample: fast - faster compression but lower quality\nExample: slow - better quality but slower compression\n\nTimeout: 60 sec",
    "COMPRESSION_VIDEO_CRF": "Set the Constant Rate Factor for video quality (0-51, lower is better).\n\nExample: 23 - default value, good balance\nExample: 28 - more compression, lower quality\n\nTimeout: 60 sec",
    "COMPRESSION_VIDEO_CODEC": "Set the video codec for compression. Common codecs: libx264, libx265.\n\nExample: libx264 - widely compatible codec\nExample: libx265 - better compression but less compatible\n\nTimeout: 60 sec",
    "COMPRESSION_VIDEO_TUNE": "Set the tuning parameter for video compression. Options: film, animation, grain, etc.\n\nExample: film - for live-action content\nExample: animation - for animated content\n\nTimeout: 60 sec",
    "COMPRESSION_VIDEO_PIXEL_FORMAT": "Set the pixel format for video compression. Common formats: yuv420p, yuv444p.\n\nExample: yuv420p - most compatible format\nExample: yuv444p - highest quality but larger file size\n\nTimeout: 60 sec",
    "COMPRESSION_VIDEO_BITDEPTH": "Set the bit depth for video compression. Common values: 8, 10, 12.\n\nExample: 8 - standard 8-bit video (most compatible)\nExample: 10 - 10-bit video (better color gradients)\nExample: none - use default bit depth\n\nTimeout: 60 sec",
    "COMPRESSION_VIDEO_BITRATE": "Set the bitrate for video compression. Examples: 1M, 5M, 10M.\n\nExample: 5M - 5 Mbps (good for 1080p)\nExample: 2M - 2 Mbps (good for 720p)\nExample: none - use automatic bitrate based on CRF\n\nTimeout: 60 sec",
    "COMPRESSION_VIDEO_RESOLUTION": "Set the resolution for video compression. Format: widthxheight or 'none'.\n\nExample: 1920x1080 - Full HD\nExample: 1280x720 - HD\nExample: none - keep original resolution\n\nTimeout: 60 sec",
    "COMPRESSION_VIDEO_FORMAT": "Set the output format for compressed videos. Common formats: mp4, mkv, avi, webm.\n\nExample: mp4 - widely compatible format\nExample: mkv - container that supports almost all codecs\nExample: none - keep original format\n\nTimeout: 60 sec",
    # Audio Compression Settings
    "COMPRESSION_AUDIO_ENABLED": "Enable or disable audio compression.\n\nExample: true - enable audio compression\nExample: false - disable audio compression\n\nTimeout: 60 sec",
    "COMPRESSION_AUDIO_PRESET": "Set the compression preset for audio. Options: fast, medium, slow.\n\nExample: fast - faster compression but lower quality\nExample: slow - better quality but slower compression\n\nTimeout: 60 sec",
    "COMPRESSION_AUDIO_CODEC": "Set the audio codec for compression. Common codecs: aac, mp3, opus.\n\nExample: aac - good quality and compatibility\nExample: opus - better compression\n\nTimeout: 60 sec",
    "COMPRESSION_AUDIO_BITRATE": "Set the audio bitrate for compression. Examples: 64k, 128k, 192k.\n\nExample: 128k - good balance of quality and size\nExample: 64k - smaller files but lower quality\n\nTimeout: 60 sec",
    "COMPRESSION_AUDIO_CHANNELS": "Set the number of audio channels for compression. Common values: 1 (mono), 2 (stereo).\n\nExample: 2 - stereo audio\nExample: 1 - mono audio (smaller files)\n\nTimeout: 60 sec",
    "COMPRESSION_AUDIO_BITDEPTH": "Set the bit depth for audio compression. Common values: 16, 24, 32.\n\nExample: 16 - standard CD quality (most compatible)\nExample: 24 - high-resolution audio\nExample: none - use default bit depth\n\nTimeout: 60 sec",
    "COMPRESSION_AUDIO_FORMAT": "Set the output format for compressed audio. Common formats: mp3, m4a, ogg, flac.\n\nExample: mp3 - widely compatible format\nExample: aac - good quality and compatibility\nExample: none - keep original format\n\nTimeout: 60 sec",
    # Image Compression Settings
    "COMPRESSION_IMAGE_ENABLED": "Enable or disable image compression.\n\nExample: true - enable image compression\nExample: false - disable image compression\n\nTimeout: 60 sec",
    "COMPRESSION_IMAGE_PRESET": "Set the compression preset for images. Options: fast, medium, slow.\n\nExample: fast - faster compression but lower quality\nExample: slow - better quality but slower compression\n\nTimeout: 60 sec",
    "COMPRESSION_IMAGE_QUALITY": "Set the quality for image compression (1-100). Higher values mean better quality but larger file size.\n\nExample: 80 - good balance of quality and size\nExample: 50 - more compression, lower quality\n\nTimeout: 60 sec",
    "COMPRESSION_IMAGE_RESIZE": "Set the size to resize images to during compression. Format: widthxheight or 'none'.\n\nExample: none - keep original size\nExample: 1280x720 - resize to HD\n\nTimeout: 60 sec",
    "COMPRESSION_IMAGE_FORMAT": "Set the output format for compressed images. Common formats: jpg, png, webp.\n\nExample: jpg - good compression, smaller files\nExample: png - lossless format with transparency support\nExample: none - keep original format\n\nTimeout: 60 sec",
    # Document Compression Settings
    "COMPRESSION_DOCUMENT_ENABLED": "Enable or disable document compression.\n\nExample: true - enable document compression\nExample: false - disable document compression\n\nTimeout: 60 sec",
    "COMPRESSION_DOCUMENT_PRESET": "Set the compression preset for documents. Options: fast, medium, slow.\n\nExample: fast - faster compression but lower quality\nExample: slow - better quality but slower compression\n\nTimeout: 60 sec",
    "COMPRESSION_DOCUMENT_DPI": "Set the DPI (dots per inch) for document compression.\n\nExample: 150 - good balance of quality and size\nExample: 72 - more compression, lower quality\n\nTimeout: 60 sec",
    "COMPRESSION_DOCUMENT_FORMAT": "Set the output format for compressed documents. Common formats: pdf, docx, txt.\n\nExample: pdf - standard document format\nExample: docx - Microsoft Word format\nExample: none - keep original format\n\nTimeout: 60 sec",
    # Subtitle Compression Settings
    "COMPRESSION_SUBTITLE_ENABLED": "Enable or disable subtitle compression.\n\nExample: true - enable subtitle compression\nExample: false - disable subtitle compression\n\nTimeout: 60 sec",
    "COMPRESSION_SUBTITLE_PRESET": "Set the compression preset for subtitles. Options: fast, medium, slow.\n\nExample: fast - faster compression but lower quality\nExample: slow - better quality but slower compression\n\nTimeout: 60 sec",
    "COMPRESSION_SUBTITLE_ENCODING": "Set the character encoding for subtitle compression.\n\nExample: utf-8 - universal encoding\nExample: ascii - more compression but limited character support\n\nTimeout: 60 sec",
    "COMPRESSION_SUBTITLE_FORMAT": "Set the output format for compressed subtitles. Common formats: srt, ass, vtt.\n\nExample: srt - simple subtitle format\nExample: ass - advanced subtitle format with styling\nExample: none - keep original format\n\nTimeout: 60 sec",
    # Archive Compression Settings
    "COMPRESSION_ARCHIVE_ENABLED": "Enable or disable archive compression.\n\nExample: true - enable archive compression\nExample: false - disable archive compression\n\nTimeout: 60 sec",
    "COMPRESSION_ARCHIVE_PRESET": "Set the compression preset for archives. Options: fast, medium, slow.\n\nExample: fast - faster compression but lower compression ratio\nExample: slow - better compression ratio but slower\n\nTimeout: 60 sec",
    "COMPRESSION_ARCHIVE_LEVEL": "Set the compression level for archives (1-9). Higher values mean better compression but slower processing.\n\nExample: 5 - good balance of speed and compression\nExample: 9 - maximum compression\n\nTimeout: 60 sec",
    "COMPRESSION_ARCHIVE_METHOD": "Set the compression method for archives. Options: deflate, store, bzip2, lzma.\n\nExample: deflate - good balance of speed and compression\nExample: lzma - best compression but slowest\n\nTimeout: 60 sec",
    "COMPRESSION_ARCHIVE_PASSWORD": "Set a password to protect the archive. Leave as 'none' for no password protection.\nNote: Password protection only works with 7z, zip, and rar formats.\n\nExample: mySecurePassword123\nExample: none - no password protection\n\nTimeout: 60 sec",
    "COMPRESSION_ARCHIVE_ALGORITHM": "Set the archive algorithm. Options: 7z, zip, tar, rar, etc.\n\nExample: 7z - best compression, supports password protection\nExample: zip - more compatible, supports password protection\nExample: tar - good for preserving file permissions (no password support)\n\nTimeout: 60 sec",
    "COMPRESSION_ARCHIVE_FORMAT": "Set the output format for compressed archives. Common formats: zip, 7z, tar.gz.\n\nExample: zip - widely compatible format\nExample: 7z - better compression but less compatible\nExample: none - keep original format\n\nTimeout: 60 sec",
    # Trim Settings
    "TRIM_ENABLED": "Enable or disable trim feature. Send 'true' to enable or 'false' to disable.\n\nExample: true - enable trim feature\nExample: false - disable trim feature\n\nPriority:\n1. Global (enabled) & User (disabled) -> Apply global\n2. User (enabled) & Global (disabled) -> Apply user\n3. Global (enabled) & User (enabled) -> Apply user\n4. Global (disabled) & User (disabled) -> Don't apply\n\nUse the Reset button to reset all trim settings to default.\n\nTimeout: 60 sec",
    "TRIM_PRIORITY": "Set priority for trim processing. Lower number means higher priority.\n\nExample: 1 - highest priority\nExample: 10 - lower priority\n\nTimeout: 60 sec",
    "TRIM_START_TIME": "Set the start time for trimming media files. Format: HH:MM:SS, MM:SS, or SS.\n\nExample: 00:01:30 (1 minute 30 seconds)\nExample: 5:45 (5 minutes 45 seconds)\nExample: 90 (90 seconds)\n\nLeave empty or set to 00:00:00 to start from the beginning.\n\nTimeout: 60 sec",
    "TRIM_END_TIME": "Set the end time for trimming media files. Format: HH:MM:SS, MM:SS, or SS.\n\nExample: 00:02:30 (2 minutes 30 seconds)\nExample: 10:45 (10 minutes 45 seconds)\nExample: 180 (180 seconds)\n\nLeave empty to trim until the end of the file.\n\nTimeout: 60 sec",
    "TRIM_DELETE_ORIGINAL": "Enable or disable deleting the original file after trimming.\n\nExample: true - delete original file after trimming\nExample: false - keep both original and trimmed files\n\nTimeout: 60 sec",
    "TRIM_VIDEO_FORMAT": "Set the output format for video trimming. This determines the container format of the trimmed video file.\n\nExample: mp4 - widely compatible format\nExample: mkv - container that supports almost all codecs\nExample: none - use the same format as the original file\n\nTimeout: 60 sec",
    "TRIM_AUDIO_FORMAT": "Set the output format for audio trimming. This determines the container format of the trimmed audio file.\n\nExample: mp3 - widely compatible format\nExample: flac - lossless audio format\nExample: none - use the same format as the original file\n\nTimeout: 60 sec",
    "TRIM_IMAGE_FORMAT": "Set the output format for image trimming. This determines the format of the trimmed image file.\n\nExample: jpg - good compression, smaller files\nExample: png - lossless format with transparency support\nExample: none - use the same format as the original file\n\nTimeout: 60 sec",
    "TRIM_IMAGE_QUALITY": "Set the quality for image processing during trim operations (0-100). Higher values mean better quality but larger file size.\n\nExample: 90 - high quality (default)\nExample: 75 - good balance of quality and size\nExample: none - use original quality\n\nTimeout: 60 sec",
    "TRIM_DOCUMENT_FORMAT": "Set the output format for document trimming. This determines the format of the trimmed document file.\n\nExample: pdf - standard document format\nExample: docx - Microsoft Word format\nExample: none - use the same format as the original file\n\nTimeout: 60 sec",
    "TRIM_DOCUMENT_QUALITY": "Set the quality for document processing during trim operations (0-100). Higher values mean better quality but larger file size.\n\nExample: 90 - high quality (default)\nExample: 75 - good balance of quality and size\nExample: none - use original quality\n\nTimeout: 60 sec",
    "TRIM_SUBTITLE_FORMAT": "Set the output format for subtitle trimming. This determines the format of the trimmed subtitle file.\n\nExample: srt - simple subtitle format\nExample: ass - advanced subtitle format with styling\nExample: none - use the same format as the original file\n\nTimeout: 60 sec",
    "TRIM_ARCHIVE_FORMAT": "Set the output format for archive trimming. This determines the format of the trimmed archive file.\n\nExample: zip - widely compatible format\nExample: 7z - better compression but less compatible\nExample: none - use the same format as the original file\n\nTimeout: 60 sec",
    # Extract Settings
    "EXTRACT_ENABLED": "Enable or disable the extract feature. Send 'true' to enable or 'false' to disable. When enabled, media tracks can be extracted from container files.\n\nExample: true - enable extract feature\nExample: false - disable extract feature\n\nPriority:\n1. Global (enabled) & User (disabled) -> Apply global\n2. User (enabled) & Global (disabled) -> Apply user\n3. Global (enabled) & User (enabled) -> Apply user\n4. Global (disabled) & User (disabled) -> Don't apply\n\nTimeout: 60 sec",
    "EXTRACT_PRIORITY": "Set the priority for extract processing in the media tools pipeline. Lower number means higher priority.\n\nExample: 1 - highest priority (runs before other tools)\nExample: 5 - medium priority\nExample: 10 - lowest priority (runs after other tools)\n\nDefault: 6\nTimeout: 60 sec",
    "EXTRACT_DELETE_ORIGINAL": "Choose whether to delete the original file after extraction. Send 'true' to delete or 'false' to keep.\n\nExample: true - delete original file after extraction\nExample: false - keep original file after extraction\n\nDefault: true\nTimeout: 60 sec",
    "EXTRACT_MAINTAIN_QUALITY": "Choose whether to maintain quality when extracting and converting tracks. Send 'true' to maintain quality or 'false' to use default settings.\n\nExample: true - use high quality settings for extracted tracks\nExample: false - use default quality settings\n\nDefault: true\nTimeout: 60 sec",
    # Video Extract Settings
    "EXTRACT_VIDEO_ENABLED": "Enable or disable video track extraction. Send 'true' to enable or 'false' to disable.\n\nExample: true - extract video tracks\nExample: false - don't extract video tracks\n\nTimeout: 60 sec",
    "EXTRACT_VIDEO_CODEC": "Set the codec to use for extracted video tracks. Common codecs: copy, h264, h265, vp9.\n\nExample: copy - preserve original codec (fastest)\nExample: h264 - convert to H.264 (widely compatible)\nExample: h265 - convert to H.265 (better compression)\nExample: none - don't specify codec (use default)\n\nTimeout: 60 sec",
    "EXTRACT_VIDEO_FORMAT": "Set the container format for extracted video tracks. Common formats: mp4, mkv, webm.\n\nExample: mp4 - use MP4 container (widely compatible)\nExample: mkv - use MKV container (supports more features)\nExample: none - use default format based on codec\n\nTimeout: 60 sec",
    "EXTRACT_VIDEO_INDEX": "Specify which video track(s) to extract by index (0-based). Leave empty or set to 'none' to extract all video tracks.\n\nExample: 0 - extract first video track only\nExample: 1 - extract second video track only\nExample: 0,1,2 - extract first, second, and third video tracks\nExample: all - extract all video tracks\n\nTimeout: 60 sec",
    "EXTRACT_VIDEO_QUALITY": "Set the quality for extracted video tracks (CRF value). Lower values mean higher quality.\n\nExample: 18 - high quality (larger file size)\nExample: 23 - medium quality (balanced)\nExample: 28 - lower quality (smaller file size)\nExample: none - use default quality\n\nTimeout: 60 sec",
    "EXTRACT_VIDEO_PRESET": "Set the encoding preset for extracted video tracks. Affects encoding speed vs compression efficiency.\n\nExample: ultrafast - fastest encoding, lowest compression\nExample: medium - balanced speed and compression\nExample: veryslow - slowest encoding, best compression\nExample: none - use default preset\n\nTimeout: 60 sec",
    "EXTRACT_VIDEO_BITRATE": "Set the bitrate for extracted video tracks. Higher values mean better quality but larger files.\n\nExample: 5M - 5 Mbps (good for 1080p)\nExample: 2M - 2 Mbps (good for 720p)\nExample: none - use default bitrate\n\nTimeout: 60 sec",
    "EXTRACT_VIDEO_RESOLUTION": "Set the resolution for extracted video tracks. Lower resolution means smaller file size.\n\nExample: 1920x1080 - Full HD\nExample: 1280x720 - HD\nExample: 640x480 - SD\nExample: none - keep original resolution\n\nTimeout: 60 sec",
    "EXTRACT_VIDEO_FPS": "Set the frame rate for extracted video tracks. Lower FPS means smaller file size.\n\nExample: 30 - 30 frames per second\nExample: 60 - 60 frames per second\nExample: none - keep original frame rate\n\nTimeout: 60 sec",
    # Audio Extract Settings
    "EXTRACT_AUDIO_ENABLED": "Enable or disable audio track extraction. Send 'true' to enable or 'false' to disable.\n\nExample: true - extract audio tracks\nExample: false - don't extract audio tracks\n\nTimeout: 60 sec",
    "EXTRACT_AUDIO_CODEC": "Set the codec to use for extracted audio tracks. Common codecs: copy, aac, mp3, opus, flac.\n\nExample: copy - preserve original codec (fastest)\nExample: mp3 - convert to MP3 (widely compatible)\nExample: aac - convert to AAC (good quality/size ratio)\nExample: flac - convert to FLAC (lossless)\nExample: none - don't specify codec (use default)\n\nTimeout: 60 sec",
    "EXTRACT_AUDIO_FORMAT": "Set the container format for extracted audio tracks. Common formats: mp3, m4a, ogg, flac.\n\nExample: mp3 - use MP3 container (widely compatible)\nExample: m4a - use M4A container (good for AAC)\nExample: none - use default format based on codec\n\nTimeout: 60 sec",
    "EXTRACT_AUDIO_INDEX": "Specify which audio track(s) to extract by index (0-based). Leave empty or set to 'none' to extract all audio tracks.\n\nExample: 0 - extract first audio track only\nExample: 1 - extract second audio track only\nExample: 0,1,2 - extract first, second, and third audio tracks\nExample: all - extract all audio tracks\n\nTimeout: 60 sec",
    "EXTRACT_AUDIO_BITRATE": "Set the bitrate for extracted audio tracks. Higher values mean better quality but larger files.\n\nExample: 320k - 320 kbps (high quality)\nExample: 192k - 192 kbps (good quality)\nExample: 128k - 128 kbps (acceptable quality)\nExample: none - use default bitrate\n\nTimeout: 60 sec",
    "EXTRACT_AUDIO_CHANNELS": "Set the number of audio channels for extracted audio tracks.\n\nExample: 2 - stereo\nExample: 1 - mono\nExample: 6 - 5.1 surround\nExample: none - keep original channels\n\nTimeout: 60 sec",
    "EXTRACT_AUDIO_SAMPLING": "Set the sampling rate for extracted audio tracks. Common values: 44100, 48000.\n\nExample: 44100 - CD quality (44.1 kHz)\nExample: 48000 - DVD quality (48 kHz)\nExample: none - keep original sampling rate\n\nTimeout: 60 sec",
    "EXTRACT_AUDIO_VOLUME": "Set the volume adjustment for extracted audio tracks. Values above 1 increase volume, below 1 decrease it.\n\nExample: 1.5 - increase volume by 50%\nExample: 0.8 - decrease volume by 20%\nExample: none - keep original volume\n\nTimeout: 60 sec",
    # Subtitle Extract Settings
    "EXTRACT_SUBTITLE_ENABLED": "Enable or disable subtitle track extraction. Send 'true' to enable or 'false' to disable.\n\nExample: true - extract subtitle tracks\nExample: false - don't extract subtitle tracks\n\nTimeout: 60 sec",
    "EXTRACT_SUBTITLE_CODEC": "Set the codec to use for extracted subtitle tracks. Common codecs: copy, srt, ass.\n\nExample: copy - preserve original codec (fastest)\nExample: srt - convert to SRT (widely compatible)\nExample: ass - convert to ASS (supports styling)\nExample: none - don't specify codec (use default)\n\nTimeout: 60 sec",
    "EXTRACT_SUBTITLE_FORMAT": "Set the format for extracted subtitle tracks. Common formats: srt, ass, vtt.\n\nExample: srt - SubRip format (widely compatible)\nExample: ass - Advanced SubStation Alpha (supports styling)\nExample: vtt - WebVTT format (for web videos)\nExample: none - use default format based on codec\n\nTimeout: 60 sec",
    "EXTRACT_SUBTITLE_INDEX": "Specify which subtitle track(s) to extract by index (0-based). Leave empty or set to 'none' to extract all subtitle tracks.\n\nExample: 0 - extract first subtitle track only\nExample: 1 - extract second subtitle track only\nExample: 0,1,2 - extract first, second, and third subtitle tracks\nExample: all - extract all subtitle tracks\n\nTimeout: 60 sec",
    "EXTRACT_SUBTITLE_LANGUAGE": "Set the language tag for extracted subtitle tracks. Uses ISO 639-2 codes.\n\nExample: eng - English\nExample: spa - Spanish\nExample: fre - French\nExample: none - keep original language tag\n\nTimeout: 60 sec",
    "EXTRACT_SUBTITLE_ENCODING": "Set the character encoding for extracted subtitle tracks. Common encodings: utf-8, latin1.\n\nExample: utf-8 - Unicode (recommended)\nExample: latin1 - Western European\nExample: none - auto-detect encoding\n\nTimeout: 60 sec",
    "EXTRACT_SUBTITLE_FONT": "Set the font for extracted subtitle tracks (only works with ASS/SSA subtitles).\n\nExample: Arial - use Arial font\nExample: none - use default font\n\nTimeout: 60 sec",
    "EXTRACT_SUBTITLE_FONT_SIZE": "Set the font size for extracted subtitle tracks (only works with ASS/SSA subtitles).\n\nExample: 24 - larger font size\nExample: 18 - medium font size\nExample: none - use default font size\n\nTimeout: 60 sec",
    # Attachment Extract Settings
    "EXTRACT_ATTACHMENT_ENABLED": "Enable or disable attachment extraction. Send 'true' to enable or 'false' to disable. When enabled, attachments (like fonts, images) will be extracted from media files.\n\nExample: true - extract attachments\nExample: false - don't extract attachments\n\nTimeout: 60 sec",
    "EXTRACT_ATTACHMENT_FORMAT": "Set the format for extracted attachments. Usually not needed as attachments keep their original format.\n\nExample: none - keep original format (recommended)\n\nTimeout: 60 sec",
    "EXTRACT_ATTACHMENT_INDEX": "Specify which attachment(s) to extract by index (0-based). Leave empty or set to 'none' to extract all attachments.\n\nExample: 0 - extract first attachment only\nExample: 1 - extract second attachment only\nExample: 0,1,2 - extract first, second, and third attachments\nExample: all - extract all attachments\n\nTimeout: 60 sec",
    "EXTRACT_ATTACHMENT_FILTER": "Set a filter pattern for extracting attachments. Only attachments matching the pattern will be extracted.\n\nExample: *.ttf - extract only font files\nExample: *.png - extract only PNG images\nExample: none - extract all attachments\n\nTimeout: 60 sec",
    # Add Settings
    "ADD_ENABLED": "Enable or disable the add feature globally.\n\nExample: true - enable add feature\nExample: false - disable add feature\n\nWhen enabled, you can add media tracks to files using the -add flag or through the configured settings.\n\nTimeout: 60 sec",
    "ADD_PRIORITY": "Set the priority of the add process in the media processing pipeline.\n\nExample: 3 - run add before convert\nExample: 8 - run add after extract\n\nLower numbers run earlier. Default order:\n1. Merge\n2. Watermark\n3. Convert\n4. Trim\n5. Compression\n6. Extract\n7. Add (default: 7)\n\nTimeout: 60 sec",
    "ADD_DELETE_ORIGINAL": "Enable or disable deleting the original file after adding media.\n\nExample: true - delete original file after successful add operation\nExample: false - keep both original and modified files\n\nThis can be overridden by using the -del flag in the command.\n\nTimeout: 60 sec",
    "ADD_PRESERVE_TRACKS": "Enable or disable preserving existing tracks when adding new ones.\n\nExample: true - preserve existing tracks when adding new ones\nExample: false - allow existing tracks to be pushed to other indices\n\nThis can be overridden by using the -preserve flag in the command.\n\nTimeout: 60 sec",
    "ADD_REPLACE_TRACKS": "Enable or disable replacing existing tracks when adding new ones.\n\nExample: true - replace existing tracks with new ones\nExample: false - keep existing tracks and add new ones\n\nThis can be overridden by using the -replace flag in the command.\n\nTimeout: 60 sec",
    # Video Add Settings
    "ADD_VIDEO_ENABLED": "Enable or disable adding video tracks to media files.\n\nExample: true - enable video track addition\nExample: false - disable video track addition\n\nWhen enabled, video tracks will be added according to the specified settings.\n\nTimeout: 60 sec",
    # "ADD_VIDEO_PATH": "Path flag has been removed",
    "ADD_VIDEO_INDEX": "Set the video track index to add. Leave empty to add all video tracks.\n\nExample: 0 - add first video track\nExample: 1 - add second video track\nExample: none - add all video tracks\n\nTimeout: 60 sec",
    "ADD_VIDEO_CODEC": "Set the codec to use for video track addition.\n\nExample: copy - preserve original codec (fastest, no quality loss)\nExample: libx264 - H.264 codec (good compatibility)\nExample: libx265 - H.265/HEVC codec (better compression)\nExample: none - use default codec\n\nTimeout: 60 sec",
    "ADD_VIDEO_QUALITY": "Set the quality (CRF value) for video track addition. Lower values mean better quality but larger file size.\n\nExample: 18 - high quality\nExample: 23 - good quality\nExample: 28 - lower quality\nExample: none - don't set quality\n\nTimeout: 60 sec",
    "ADD_VIDEO_PRESET": "Set the encoding preset for video track addition. Faster presets result in larger files, slower presets in smaller files.\n\nExample: ultrafast - fastest encoding, largest files\nExample: medium - balanced speed and compression\nExample: veryslow - slowest encoding, smallest files\nExample: none - don't set preset\n\nTimeout: 60 sec",
    "ADD_VIDEO_BITRATE": "Set the bitrate for video track addition.\n\nExample: 5M - 5 megabits per second\nExample: 500k - 500 kilobits per second\nExample: none - don't set bitrate\n\nTimeout: 60 sec",
    "ADD_VIDEO_RESOLUTION": "Set the resolution for video track addition.\n\nExample: 1920x1080 - Full HD\nExample: 1280x720 - HD\nExample: none - don't set resolution\n\nTimeout: 60 sec",
    "ADD_VIDEO_FPS": "Set the frame rate for video track addition.\n\nExample: 30 - 30 frames per second\nExample: 60 - 60 frames per second\nExample: none - don't set FPS\n\nTimeout: 60 sec",
    # Audio Add Settings
    "ADD_AUDIO_ENABLED": "Enable or disable adding audio tracks to media files.\n\nExample: true - enable audio track addition\nExample: false - disable audio track addition\n\nWhen enabled, audio tracks will be added according to the specified settings.\n\nTimeout: 60 sec",
    # "ADD_AUDIO_PATH": "Path flag has been removed",
    "ADD_AUDIO_INDEX": "Set the audio track index to add. Leave empty to add all audio tracks.\n\nExample: 0 - add first audio track\nExample: 1 - add second audio track\nExample: none - add all audio tracks\n\nTimeout: 60 sec",
    "ADD_AUDIO_CODEC": "Set the codec to use for audio track addition.\n\nExample: copy - preserve original codec (fastest, no quality loss)\nExample: aac - AAC codec (good quality, compatibility)\nExample: libmp3lame - MP3 codec (widely compatible)\nExample: flac - FLAC codec (lossless)\nExample: none - use default codec\n\nTimeout: 60 sec",
    "ADD_AUDIO_BITRATE": "Set the bitrate for audio track addition.\n\nExample: 320k - high quality\nExample: 192k - good quality\nExample: 128k - acceptable quality\nExample: none - don't set bitrate\n\nTimeout: 60 sec",
    "ADD_AUDIO_CHANNELS": "Set the number of audio channels for track addition.\n\nExample: 2 - stereo\nExample: 1 - mono\nExample: none - don't set channels\n\nTimeout: 60 sec",
    "ADD_AUDIO_SAMPLING": "Set the sampling rate for audio track addition.\n\nExample: 48000 - high quality\nExample: 44100 - CD quality\nExample: none - don't set sampling rate\n\nTimeout: 60 sec",
    "ADD_AUDIO_VOLUME": "Set the volume adjustment for audio track addition.\n\nExample: 1.0 - original volume\nExample: 2.0 - double volume\nExample: 0.5 - half volume\nExample: none - don't adjust volume\n\nTimeout: 60 sec",
    # Subtitle Add Settings
    "ADD_SUBTITLE_ENABLED": "Enable or disable adding subtitle tracks to media files.\n\nExample: true - enable subtitle track addition\nExample: false - disable subtitle track addition\n\nWhen enabled, subtitle tracks will be added according to the specified settings.\n\nTimeout: 60 sec",
    # "ADD_SUBTITLE_PATH": "Path flag has been removed",
    "ADD_SUBTITLE_INDEX": "Set the subtitle track index to add. Leave empty to add all subtitle tracks.\n\nExample: 0 - add first subtitle track\nExample: 1 - add second subtitle track\nExample: none - add all subtitle tracks\n\nTimeout: 60 sec",
    "ADD_SUBTITLE_CODEC": "Set the codec to use for subtitle track addition.\n\nExample: copy - preserve original format\nExample: srt - convert to SRT format\nExample: ass - convert to ASS format\nExample: none - use default codec\n\nTimeout: 60 sec",
    "ADD_SUBTITLE_LANGUAGE": "Set the language code for subtitle track addition.\n\nExample: eng - English\nExample: spa - Spanish\nExample: none - don't set language\n\nTimeout: 60 sec",
    "ADD_SUBTITLE_ENCODING": "Set the character encoding for subtitle track addition.\n\nExample: utf-8 - UTF-8 encoding\nExample: latin1 - Latin-1 encoding\nExample: none - don't set encoding\n\nTimeout: 60 sec",
    "ADD_SUBTITLE_FONT": "Set the font for subtitle track addition (for ASS/SSA subtitles).\n\nExample: Arial - use Arial font\nExample: DejaVu Sans - use DejaVu Sans font\nExample: none - don't set font\n\nTimeout: 60 sec",
    "ADD_SUBTITLE_FONT_SIZE": "Set the font size for subtitle track addition (for ASS/SSA subtitles).\n\nExample: 24 - medium size\nExample: 32 - larger size\nExample: none - don't set font size\n\nTimeout: 60 sec",
    # Attachment Add Settings
    "ADD_ATTACHMENT_ENABLED": "Enable or disable adding attachments to media files.\n\nExample: true - enable attachment addition\nExample: false - disable attachment addition\n\nWhen enabled, attachments will be added according to the specified settings.\n\nTimeout: 60 sec",
    # "ADD_ATTACHMENT_PATH": "Path flag has been removed",
    "ADD_ATTACHMENT_INDEX": "Set the attachment index to add. Leave empty to add all attachments.\n\nExample: 0 - add first attachment\nExample: 1 - add second attachment\nExample: none - add all attachments\n\nTimeout: 60 sec",
    "ADD_ATTACHMENT_MIMETYPE": "Set the MIME type for attachment addition.\n\nExample: font/ttf - TrueType font\nExample: image/png - PNG image\nExample: none - don't set MIME type\n\nTimeout: 60 sec",
    # MediaInfo Settings
    "MEDIAINFO_ENABLED": "Enable or disable the MediaInfo command for detailed media information.\n\nExample: true - enable MediaInfo command\nExample: false - disable MediaInfo command\n\nWhen enabled, you can use the /mediainfo command to get detailed information about media files.\n\nTimeout: 60 sec",
    # Sample Video Settings
    "SAMPLE_VIDEO_ENABLED": "Enable or disable the sample video feature. This allows creating short sample clips from videos.\n\nExample: true - enable sample video feature\nExample: false - disable sample video feature\n\nTimeout: 60 sec",
}

# Main help page
main_help_string = """
<b>📚 Bot Commands Guide</b>

<b>NOTE:</b> Try each command without any argument to see more details.
Use the buttons below to navigate through different command categories.
"""

# Download Commands page
download_commands = """
<b>🔄 Download Commands</b>

/{BotCommands.MirrorCommand[0]} or /{BotCommands.MirrorCommand[1]}: Start mirroring to cloud.
/{BotCommands.JdMirrorCommand[0]} or /{BotCommands.JdMirrorCommand[1]}: Start mirroring to cloud using JDownloader.
/{BotCommands.NzbMirrorCommand[0]} or /{BotCommands.NzbMirrorCommand[1]}: Start mirroring to cloud using Sabnzbd.
/{BotCommands.YtdlCommand[0]} or /{BotCommands.YtdlCommand[1]}: Mirror yt-dlp supported link.
/{BotCommands.LeechCommand[0]} or /{BotCommands.LeechCommand[1]}: Start leeching to Telegram. If helper bots are configured, hyper download will be used for faster downloads.
/{BotCommands.JdLeechCommand[0]} or /{BotCommands.JdLeechCommand[1]}: Start leeching using JDownloader.
/{BotCommands.NzbLeechCommand[0]} or /{BotCommands.NzbLeechCommand[1]}: Start leeching using Sabnzbd.
/{BotCommands.YtdlLeechCommand[0]} or /{BotCommands.YtdlLeechCommand[1]}: Leech yt-dlp supported link.
/{BotCommands.StreamripMirrorCommand[0]} or /{BotCommands.StreamripMirrorCommand[1]}: Mirror music from streaming platforms (Qobuz, Tidal, Deezer, SoundCloud).
/{BotCommands.StreamripLeechCommand[0]} or /{BotCommands.StreamripLeechCommand[1]}: Leech music from streaming platforms to Telegram.
/{BotCommands.StreamripSearchCommand[0]} or /{BotCommands.StreamripSearchCommand[1]}: Search for music across streaming platforms.
/{BotCommands.CloneCommand} [drive_url]: Copy file/folder to Google Drive.
"""

# Status & Management page
status_commands = """
<b>📊 Status & Management</b>

/{BotCommands.StatusCommand[0]} or /{BotCommands.StatusCommand[1]} or /{BotCommands.StatusCommand[2]} or /{BotCommands.StatusCommand[3]}: Shows a status of all the downloads.
/{BotCommands.StatsCommand}: Show stats of the machine where the bot is hosted in.
/{BotCommands.PingCommand}: Check how long it takes to ping the bot.
/{BotCommands.SpeedTest}: Check internet speed of the host machine.
/{BotCommands.CancelAllCommand} [query]: Cancel all [status] tasks.
/{BotCommands.ForceStartCommand[0]} or /{BotCommands.ForceStartCommand[1]} [gid]: Force start task by gid or reply.
/{BotCommands.SelectCommand}: Select files by gid or reply.
/{BotCommands.CheckDeletionsCommand[0]} or /{BotCommands.CheckDeletionsCommand[1]}: Check and manage scheduled message deletions.
"""

# Search Tools page
search_commands = """
<b>🔍 Search Tools</b>

/{BotCommands.ListCommand} [query]: Search in Google Drive(s).
/{BotCommands.HydraSearchCommamd} [query]: Search for NZB files.
/{BotCommands.MediaSearchCommand[0]} or /{BotCommands.MediaSearchCommand[1]}: Search for media files in configured channels.
/{BotCommands.IMDBCommand}: Search for movies or TV series info on IMDB.
"""

# File Management page
file_commands = """
<b>📁 File Management</b>

/{BotCommands.MediaInfoCommand[0]} or /{BotCommands.MediaInfoCommand[1]}: Get MediaInfo from telegram file or direct link.
/{BotCommands.CountCommand} [drive_url]: Count file/folder of Google Drive.
/{BotCommands.DeleteCommand} [drive_url]: Delete file/folder from Google Drive (Only Owner & Sudo).
/{BotCommands.SoxCommand[0]} or /{BotCommands.SoxCommand[1]}: Generate audio spectrum from audio files.
/{BotCommands.PasteCommand}: Paste text/code to a pastebin service.
"""

# Security & Authentication page
security_commands = """
<b>🔒 Security & Authentication</b>

/{BotCommands.LoginCommand}: Login to the bot using password for permanent access.
/{BotCommands.AuthorizeCommand}: Authorize a chat or a user to use the bot (Owner & Sudo only).
/{BotCommands.UnAuthorizeCommand}: Unauthorize a chat or a user from using the bot (Owner & Sudo only).
/{BotCommands.AddSudoCommand}: Add a user to Sudo (Owner only).
/{BotCommands.RmSudoCommand}: Remove a user from Sudo (Owner only).
/{BotCommands.UsersCommand}: Show authorized users (Owner & Sudo only).
/{BotCommands.GenSessionCommand[0]} or /{BotCommands.GenSessionCommand[1]}: Generate a Pyrogram session string securely.
/{BotCommands.VirusTotalCommand}: Scan files or URLs for viruses using VirusTotal.
"""

# Settings & Configuration page
settings_commands = """
<b>⚙️ Settings & Configuration</b>

/{BotCommands.UserSetCommand[0]} or /{BotCommands.UserSetCommand[1]} or /{BotCommands.UserSetCommand[2]} [query]: Users settings.
/{BotCommands.BotSetCommand} [query]: Bot settings (Owner & Sudo only).
/{BotCommands.MediaToolsCommand[0]} or /{BotCommands.MediaToolsCommand[1]}: Media tools settings for watermark and other media features.
/{BotCommands.MediaToolsHelpCommand[0]} or /{BotCommands.MediaToolsHelpCommand[1]}: View detailed help for merge and watermark features.
/{BotCommands.FontStylesCommand[0]} or /{BotCommands.FontStylesCommand[1]}: View available font styles for leech.
/{BotCommands.RssCommand}: Subscribe to RSS feeds (Owner only).
"""

# AI & Special Features page
special_commands = """
<b>🤖 AI & Special Features</b>

/{BotCommands.AskCommand}: Chat with AI using the bot (Mistral or DeepSeek).
/{BotCommands.TruecallerCommand}: Lookup phone numbers using Truecaller.
"""

# System Commands page
system_commands = """
<b>🛠️ System Commands (Owner & Sudo only)</b>

/{BotCommands.RestartCommand[0]} or /{BotCommands.RestartCommand[1]}: Restart and update the bot.
/{BotCommands.LogCommand}: Get the bot log file.
/{BotCommands.ShellCommand}: Execute shell commands.
/{BotCommands.ExecCommand}: Execute sync functions.
/{BotCommands.AExecCommand}: Execute async functions.
/{BotCommands.ClearLocalsCommand}: Clear locals in exec functions.
/{BotCommands.BroadcastCommand[0]} or /{BotCommands.BroadcastCommand[1]}: Broadcast a message to bot users.
"""

# Help page
help_commands = """
<b>❓ Help</b>

/{BotCommands.HelpCommand}: Show this help message.
"""

# Dictionary to store all help pages
help_string = {
    "main": main_help_string,
    "download": download_commands,
    "status": status_commands,
    "search": search_commands,
    "file": file_commands,
    "security": security_commands,
    "settings": settings_commands,
    "special": special_commands,
    "system": system_commands,
    "help": help_commands,
}
