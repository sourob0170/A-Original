import contextlib
import gc
import json
import os
import re
from hashlib import md5

from aiofiles.os import path as aiopath
from langcodes import Language

from bot import LOGGER
from bot.helper.ext_utils.bot_utils import cmd_exec
from bot.helper.ext_utils.status_utils import (
    get_readable_file_size,
    get_readable_time,
)
from bot.helper.ext_utils.template_processor import process_template

try:
    from bot.helper.ext_utils.gc_utils import smart_garbage_collection
except ImportError:
    smart_garbage_collection = None


class DefaultDict(dict):
    """A dictionary that returns 'Unknown' for missing keys."""

    def __missing__(self, _):
        return "Unknown"


async def calculate_md5(file_path, block_size=8192):
    """Calculate MD5 hash of a file."""
    # Check if file exists before attempting to calculate MD5
    try:
        if not await aiopath.exists(file_path):
            LOGGER.error(f"File does not exist for MD5 calculation: {file_path}")
            return "Unknown"

        # Check if file has content
        file_size = await aiopath.getsize(file_path)
        if file_size == 0:
            LOGGER.error(
                f"File exists but has zero size for MD5 calculation: {file_path}"
            )
            return "Unknown"

        # Use async file operations when possible
        try:
            import aiofiles

            md5_hash = md5()
            async with aiofiles.open(file_path, "rb") as f:
                # Only read the first block for speed
                data = await f.read(block_size)
                md5_hash.update(data)
            # MD5 hash is already a string, so no conversion needed
            return md5_hash.hexdigest()[:10]  # Return first 10 chars for brevity
        except ImportError:
            # Fall back to synchronous operation if aiofiles is not available
            md5_hash = md5()
            with open(file_path, "rb") as f:
                # Only read the first block for speed
                data = f.read(block_size)
                md5_hash.update(data)
            # MD5 hash is already a string, so no conversion needed
            return md5_hash.hexdigest()[:10]  # Return first 10 chars for brevity
    except FileNotFoundError:
        # File might have been deleted between the existence check and now
        LOGGER.error(f"File disappeared during MD5 calculation: {file_path}")
        return "Unknown"
    except PermissionError:
        LOGGER.error(f"Permission denied when calculating MD5: {file_path}")
        return "Unknown"
    except Exception as e:
        LOGGER.error(f"Error calculating MD5: {e}")
        return "Unknown"


def clean_caption(caption):
    """Clean up the caption by removing empty lines and extra whitespace."""
    if not caption:
        return ""

    # Remove empty lines
    lines = [line.strip() for line in caption.split("\n") if line.strip()]

    # Remove duplicate lines
    unique_lines = []
    for line in lines:
        if line not in unique_lines:
            unique_lines.append(line)

    # Join lines with a newline
    return "\n".join(unique_lines)


async def generate_caption(filename, directory, caption_template):
    """
    Generate a caption for a file using a template.

    Args:
        filename (str): The name of the file
        directory (str): The directory containing the file
        caption_template (str): The template to use for the caption

    Returns:
        str: The generated caption
    """
    file_path = os.path.join(directory, filename)

    # Check if the file exists before proceeding
    try:
        if not await aiopath.exists(file_path):
            LOGGER.error(f"File does not exist for caption generation: {file_path}")
            return f"<code>{filename}</code>"  # Return a simple caption with just the filename

        # Also check if file has content
        file_size = await aiopath.getsize(file_path)
        if file_size == 0:
            LOGGER.error(
                f"File exists but has zero size for caption generation: {file_path}"
            )
            return f"<code>{filename}</code>"  # Return a simple caption with just the filename
    except Exception as e:
        LOGGER.error(f"Error checking file existence: {e}")
        return f"<code>{filename}</code>"  # Return a simple caption with just the filename

    # Initialize variables to track temporary resources
    temp_file_created = False
    file_path_to_use = file_path
    temp_dir = None

    try:
        # Check if file still exists before proceeding further
        try:
            # Use async file operations for better performance
            if not await aiopath.exists(file_path):
                LOGGER.error(
                    f"File disappeared during caption generation: {file_path}"
                )
                return f"<code>{filename}</code>"  # Return a simple caption with just the filename

            # Also check if we can access the file's modification time
            mod_time = await aiopath.getmtime(file_path)
            LOGGER.debug(f"File last modified at: {mod_time}")

            # Check file size again
            file_size = await aiopath.getsize(file_path)
            if file_size == 0:
                LOGGER.error(
                    f"File exists but has zero size during processing: {file_path}"
                )
                return f"<code>{filename}</code>"  # Return a simple caption with just the filename
        except FileNotFoundError:
            # File might have been deleted between the existence check and now
            LOGGER.error(f"File disappeared during caption generation: {file_path}")
            return f"<code>{filename}</code>"  # Return a simple caption with just the filename
        except Exception as e:
            LOGGER.error(f"Error accessing file during caption generation: {e}")
            return f"<code>{filename}</code>"  # Return a simple caption with just the filename

        # Check if filename contains special characters that might cause issues with shell commands
        if any(
            c in file_path
            for c in [
                "(",
                ")",
                "[",
                "]",
                "'",
                '"',
                ";",
                "&",
                "|",
                "<",
                ">",
                "$",
                "`",
                "\\",
            ]
        ) and os.path.exists(file_path):  # Create a temporary file with a safe name
            import tempfile
            from time import time

            # Try to create a temp directory in the same filesystem as the original file
            # This helps avoid cross-device link errors
            parent_dir = os.path.dirname(file_path)
            try:
                temp_dir = tempfile.mkdtemp(dir=parent_dir)
                same_filesystem = True
            except Exception:
                # Fall back to system temp directory if we can't create in the parent dir
                temp_dir = tempfile.mkdtemp()
                same_filesystem = False

            safe_name = (
                f"temp_mediainfo_{int(time())}{os.path.splitext(filename)[1]}"
            )
            safe_path = os.path.join(temp_dir, safe_name)
            # We'll use the temp_dir variable for cleanup later

            if same_filesystem:
                try:
                    # If on same filesystem, try a hard link for better performance
                    os.link(file_path, safe_path)
                    file_path_to_use = safe_path
                    temp_file_created = True
                except Exception:  # Fall back to copying a portion of the file
                    try:
                        # Only copy a small portion of the file for MediaInfo analysis
                        # This is much faster than copying the entire file
                        with (
                            open(file_path, "rb") as src,
                            open(safe_path, "wb") as dst,
                        ):
                            # Copy first 10MB which should be enough for MediaInfo
                            dst.write(src.read(10 * 1024 * 1024))
                        file_path_to_use = safe_path
                        temp_file_created = True
                    except Exception as e:
                        LOGGER.error(
                            f"Failed to create temporary copy for file with special characters: {e}"
                        )
                        # Continue with original path as a fallback
                        file_path_to_use = file_path
            else:
                try:
                    # If on different filesystem, copy a portion of the file
                    with open(file_path, "rb") as src, open(safe_path, "wb") as dst:
                        # Copy first 10MB which should be enough for MediaInfo
                        dst.write(src.read(10 * 1024 * 1024))
                    file_path_to_use = safe_path
                    temp_file_created = True
                except Exception as e:
                    LOGGER.error(
                        f"Failed to create temporary copy for file with special characters: {e}"
                    )
                    # Continue with original path as a fallback
                    file_path_to_use = file_path

        # Get media info using mediainfo command
        try:
            # Double-check file existence right before running mediainfo
            if not await aiopath.exists(file_path_to_use):
                LOGGER.error(
                    f"File does not exist before running mediainfo: {file_path_to_use}"
                )
                return filename

            # Check if file is accessible and has size > 0
            try:
                file_size = await aiopath.getsize(file_path_to_use)
                if file_size == 0:
                    LOGGER.error(
                        f"File exists but has zero size: {file_path_to_use}"
                    )
                    return filename
            except Exception as e:
                LOGGER.error(f"Error checking file size before mediainfo: {e}")
                return filename

            # Run mediainfo command with absolute path
            abs_path = os.path.abspath(file_path_to_use)
            LOGGER.info(f"Running mediainfo on: {abs_path}")
            result = await cmd_exec(["mediainfo", "--Output=JSON", abs_path])

            if result[1]:
                LOGGER.info(f"MediaInfo command output: {result[1]}")

            if not result[0]:
                LOGGER.error(f"MediaInfo returned empty output for: {abs_path}")
                return filename

            # Parse JSON output
            try:
                mediainfo_data = json.loads(result[0])
            except json.JSONDecodeError as e:
                LOGGER.error(f"Failed to parse MediaInfo JSON output: {e}")
                return filename

        except FileNotFoundError as error:
            LOGGER.error(f"File not found when running mediainfo: {error}")
            return filename
        except PermissionError as error:
            LOGGER.error(f"Permission denied when running mediainfo: {error}")
            return filename
        except Exception as error:
            LOGGER.error(f"Failed to retrieve media info: {error}")
            return filename

        # Extract media information
        media_data = mediainfo_data.get("media", {})
        track_data = media_data.get("track", [])

        # Get general track info
        general_track = next(
            (track for track in track_data if track["@type"] == "General"),
            {},
        )

        # Get video track info
        video_track = next(
            (track for track in track_data if track["@type"] == "Video"),
            {},
        )

        # Get audio tracks info
        audio_tracks = [track for track in track_data if track["@type"] == "Audio"]

        # Get subtitle tracks info
        subtitle_tracks = [track for track in track_data if track["@type"] == "Text"]

        # Extract video metadata
        video_duration = 0
        video_quality = ""
        video_codec = ""
        video_format = ""
        video_framerate = ""

        # Extract audio metadata
        audio_languages = []
        audio_codecs = []

        # Extract subtitle metadata
        subtitle_languages = []

        # Process general track
        if general_track:
            # Get file format
            video_format = general_track.get("Format", "")

            # Get duration
            if "Duration" in general_track:
                try:
                    duration_str = general_track["Duration"]
                    # Check if duration is in HH:MM:SS format
                    if ":" in duration_str:
                        # Split by colon and handle different formats
                        parts = duration_str.split(":")
                        if len(parts) == 3:
                            # HH:MM:SS format
                            hours, minutes, seconds = map(float, parts)
                            video_duration = int(
                                hours * 3600 + minutes * 60 + seconds
                            )
                        elif len(parts) == 2:
                            # MM:SS format
                            minutes, seconds = map(float, parts)
                            video_duration = int(minutes * 60 + seconds)
                        elif len(parts) == 1:
                            # SS format
                            seconds = float(parts[0])
                            video_duration = int(seconds)
                    else:
                        # Try to parse as a float directly (seconds)
                        video_duration = int(float(duration_str))
                except Exception as e:
                    LOGGER.error(f"Error parsing duration: {e}")

            # Alternative duration field
            elif "Duration/String" in general_track:
                try:
                    duration_str = general_track["Duration/String"]
                    # Parse duration string (e.g., "1h 30mn")
                    hours = minutes = seconds = 0
                    if "h" in duration_str:
                        hours_part = duration_str.split("h")[0].strip()
                        hours = float(hours_part)
                    if "mn" in duration_str:
                        minutes_part = (
                            duration_str.split("h")[-1].split("mn")[0].strip()
                        )
                        minutes = float(minutes_part)
                    if "s" in duration_str and "ms" not in duration_str:
                        seconds_part = (
                            duration_str.split("mn")[-1].split("s")[0].strip()
                        )
                        seconds = float(seconds_part)
                    video_duration = int(hours * 3600 + minutes * 60 + seconds)
                except Exception as e:
                    LOGGER.error(f"Error parsing duration string: {e}")

            # Get file size
            file_size = general_track.get("FileSize", "")
            if not file_size:
                try:
                    file_size = await aiopath.getsize(file_path)
                except Exception as e:
                    LOGGER.error(f"Error getting file size: {e}")
                    file_size = 0

        # Process video track
        if video_track:
            # Get video codec
            video_codec = video_track.get("Format", "")
            if "CodecID" in video_track:
                video_codec = f"{video_codec} ({video_track['CodecID']})"

            # Get video quality
            if "Height" in video_track:
                height = video_track["Height"]
                if isinstance(height, str) and " " in height:
                    height = height.split(" ")[0]
                try:
                    height = int(float(height))
                    if height >= 2160:
                        video_quality = "4K"
                    elif height >= 1440:
                        video_quality = "2K"
                    elif height >= 1080:
                        video_quality = "1080p"
                    elif height >= 720:
                        video_quality = "720p"
                    elif height >= 480:
                        video_quality = "480p"
                    elif height >= 360:
                        video_quality = "360p"
                    else:
                        video_quality = f"{height}p"
                except Exception as e:
                    LOGGER.error(f"Error parsing video height: {e}")
                    video_quality = "Unknown"

            # Get framerate
            if "FrameRate" in video_track:
                try:
                    framerate = float(video_track["FrameRate"])
                    video_framerate = f"{framerate:.2f} fps"
                except Exception as e:
                    LOGGER.error(f"Error parsing framerate: {e}")
                    video_framerate = video_track["FrameRate"]

        # Process audio tracks
        for audio_track in audio_tracks:
            # Get audio language
            language = "Unknown"
            if "Language" in audio_track:
                try:
                    lang_code = audio_track["Language"]
                    language = Language.get(lang_code).display_name()
                except Exception:
                    language = audio_track["Language"]
            elif "Language/String" in audio_track:
                language = audio_track["Language/String"]

            # Get audio codec
            audio_codec = audio_track.get("Format", "")
            if "CodecID" in audio_track:
                audio_codec = f"{audio_codec} ({audio_track['CodecID']})"

            # Add to lists
            audio_languages.append(language)
            audio_codecs.append(audio_codec)

        # Process subtitle tracks
        for subtitle_track in subtitle_tracks:
            # Get subtitle language
            language = "Unknown"
            if "Language" in subtitle_track:
                try:
                    lang_code = subtitle_track["Language"]
                    language = Language.get(lang_code).display_name()
                except Exception:
                    language = subtitle_track["Language"]
            elif "Language/String" in subtitle_track:
                language = subtitle_track["Language/String"]

            # Add to list
            subtitle_languages.append(language)

        # Format metadata for caption
        audio_languages_str = (
            ", ".join(audio_languages) if audio_languages else "Unknown"
        )
        subtitle_languages_str = (
            ", ".join(subtitle_languages) if subtitle_languages else "Unknown"
        )
        audio_codecs_str = ", ".join(audio_codecs) if audio_codecs else "Unknown"

        # Calculate MD5 hash for the file (first 10MB only for speed)
        try:
            file_md5_hash = await calculate_md5(file_path)
        except Exception as e:
            LOGGER.error(f"Error calculating MD5 hash: {e}")
            file_md5_hash = "Unknown"

        # Get file size safely
        try:
            file_size = await aiopath.getsize(file_path)
            readable_size = get_readable_file_size(file_size)
        except Exception as e:
            LOGGER.error(f"Error getting file size: {e}")
            readable_size = "Unknown"

        # Extract metadata from filename
        from bot.helper.ext_utils.template_processor import (
            extract_metadata_from_filename,
        )

        filename_metadata = await extract_metadata_from_filename(
            os.path.splitext(filename)[0]
        )

        # Count number of tracks
        num_videos = len(
            [track for track in track_data if track["@type"] == "Video"]
        )
        num_audios = len(audio_tracks)
        num_subtitles = len(subtitle_tracks)

        # Format track counts with leading zeros for single digits
        num_videos_str = f"{num_videos:02d}" if num_videos < 10 else str(num_videos)
        num_audios_str = f"{num_audios:02d}" if num_audios < 10 else str(num_audios)
        num_subtitles_str = (
            f"{num_subtitles:02d}" if num_subtitles < 10 else str(num_subtitles)
        )

        # Generate a unique ID for the file
        # MD5 hash is already a string, so no conversion needed
        file_id = file_md5_hash[:8]

        # Format extension in uppercase
        format_upper = os.path.splitext(filename)[1][1:].upper()

        # Create caption data dictionary
        caption_data = DefaultDict(
            # Basic variables
            filename=os.path.splitext(filename)[0],  # Filename without extension
            size=readable_size,
            duration=get_readable_time(video_duration, True),
            quality=video_quality or filename_metadata.get("quality", ""),
            audios=audio_languages_str,
            audio_codecs=audio_codecs_str,
            subtitles=subtitle_languages_str,
            md5_hash=file_md5_hash,
            ext=os.path.splitext(filename)[1][1:],  # Extension without dot
            # TV Show variables
            season=filename_metadata.get("season", ""),
            episode=filename_metadata.get("episode", ""),
            year=filename_metadata.get("year", ""),
            # Media Information
            NumVideos=num_videos_str,
            NumAudios=num_audios_str,
            NumSubtitles=num_subtitles_str,
            formate=format_upper,  # Intentional spelling to match documentation
            format=video_format,
            id=file_id,
            framerate=video_framerate or filename_metadata.get("framerate", ""),
            codec=video_codec or filename_metadata.get("codec", ""),
        )

        # Create a cleaned version of the caption data for template processing
        # This ensures all values are strings and handles None values
        cleaned_caption_data = {}
        for key, value in caption_data.items():
            if value is None:
                cleaned_caption_data[key] = "Unknown"
            else:
                cleaned_caption_data[key] = str(value)

        # First try the advanced template processor for Google Fonts and nested variables
        try:
            processed_caption = await process_template(
                caption_template, cleaned_caption_data
            )
            # Clean up empty lines and format the caption
            processed_caption = clean_caption(processed_caption)
            # Log successful caption generation at INFO level only if this is not a metadata extraction call
            if caption_template != "Extracting metadata for {filename}":
                LOGGER.info(
                    f"Successfully applied leech caption template for: {filename}"
                )
            # Clean up temporary resources
            if temp_file_created and os.path.exists(file_path_to_use):
                with contextlib.suppress(Exception):
                    os.remove(file_path_to_use)
            # Clean up temporary directory if created
            if temp_dir and os.path.exists(temp_dir):
                try:
                    import shutil

                    shutil.rmtree(temp_dir)
                except Exception:
                    pass
            # Force garbage collection after processing media info
            # This can create large objects in memory
            if smart_garbage_collection:
                # Use aggressive collection for media info processing
                smart_garbage_collection(aggressive=True)
            else:
                # Collect all generations for thorough cleanup
                gc.collect(0)
                gc.collect(1)
                gc.collect(2)
            return processed_caption
        except Exception as e:
            LOGGER.error(f"Error processing template with advanced processor: {e}")
            # Try to recover by removing problematic parts
            try:
                # Remove nested templates that might be causing issues
                simplified_template = re.sub(r"{{+.*?}+", "", caption_template)
                processed_caption = await process_template(
                    simplified_template, cleaned_caption_data
                )
                processed_caption = clean_caption(processed_caption)
                LOGGER.info(f"Recovered with simplified template for: {filename}")
                return processed_caption
            except Exception as e2:
                LOGGER.error(f"Error recovering with simplified template: {e2}")
                # Fall back to the simple format_map method if advanced processing fails
                try:
                    # Create a custom format string that skips empty variables
                    custom_template = caption_template
                    for key, value in caption_data.items():
                        if not value or not str(value).strip():
                            # Replace the variable and its line if it's on its own line
                            pattern = rf"^.*{{{key}}}.*$\n?"
                            custom_template = re.sub(
                                pattern, "", custom_template, flags=re.MULTILINE
                            )
                            # Replace the variable if it's part of a line
                            custom_template = custom_template.replace(
                                f"{{{key}}}", ""
                            )

                    # Format the template with the data
                    processed_caption = custom_template.format_map(caption_data)
                    # Clean up empty lines and format the caption
                    processed_caption = clean_caption(processed_caption)
                    LOGGER.info(
                        f"Successfully applied simple caption template for: {filename}"
                    )
                    return processed_caption
                except Exception as e:
                    LOGGER.error(
                        f"Error processing template with simple processor: {e}"
                    )
                    # If all else fails, return a basic formatted caption
                    return f"<code>{filename}</code>\n<b>Size:</b> {cleaned_caption_data.get('size', 'Unknown')}"
    except Exception as e:
        LOGGER.error(f"Error generating caption: {e}")
        # Return a basic formatted caption instead of just the filename
        return f"<code>{filename}</code>"
