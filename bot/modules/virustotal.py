import asyncio
import base64
import html
import os
import time
from asyncio import create_task
from logging import getLogger

from vt import APIError
from vt import Client as VTClient

from bot import DOWNLOAD_DIR
from bot.core.config_manager import Config
from bot.helper.ext_utils.bot_utils import new_task
from bot.helper.ext_utils.links_utils import is_url
from bot.helper.ext_utils.status_utils import get_readable_file_size
from bot.helper.telegram_helper.message_utils import (
    auto_delete_message,
    edit_message,
    send_message,
)

LOGGER = getLogger(__name__)


class VirusTotalClient:
    def __init__(self):
        """Initialize the VirusTotal client."""
        self.client = VTClient(Config.VT_API_KEY, timeout=Config.VT_API_TIMEOUT)
        self._error_codes = {400: "Invalid API key", 429: "Rate limit exceeded"}

    async def _handle_api_error(self, e: APIError, delay=None):
        if e.code == 429 and delay is not None:
            LOGGER.info(
                f"{self._error_codes[e.code]}. Retrying in {delay} seconds..."
            )
            await asyncio.sleep(delay)
        else:
            raise Exception(
                f"{self._error_codes.get(e.code, f'API Error ({e.code})')}: {e.message}"
            )

    async def analyze_file(self, file_path: str) -> dict:
        """Analyze a file using VirusTotal."""
        try:
            # Upload the file
            # Note: Using blocking open() because VirusTotal API expects a file object, not bytes
            with open(file_path, "rb") as f:
                analysis = await self.client.scan_file_async(
                    f, wait_for_completion=True
                )

            result = analysis.to_dict()
            result.update(
                {
                    "file_name": os.path.basename(file_path),
                    "file_size": os.path.getsize(file_path),
                    "link": self._get_analysis_url(analysis.id),
                }
            )
            # Extract relevant information
            return result
        except APIError as e:
            await self._handle_api_error(e)
            raise
        except Exception as e:
            LOGGER.error(f"Error analyzing file: {e}")
            raise

    async def analyze_url(self, url: str) -> dict:
        """Analyze a URL using VirusTotal."""
        try:
            # Get URL analysis
            analysis = await self.client.scan_url_async(
                url, wait_for_completion=True
            )
            result = analysis.to_dict()
            result.update({"url": url, "link": self._get_analysis_url(analysis.id)})
            # Extract relevant information
            return result
        except APIError as e:
            await self._handle_api_error(e)
            raise
        except Exception as e:
            LOGGER.error(f"Error analyzing URL: {e}")
            raise

    def _get_analysis_url(self, analysis_id: str) -> str:
        # URL analysis
        if analysis_id.startswith("u-"):
            _, hash_value, _ = analysis_id.split("-")
            return f"https://www.virustotal.com/gui/url/{hash_value}"

        # File analysis
        decode_id = base64.b64decode(analysis_id).decode("utf-8")
        hash_value, _ = decode_id.split(":")
        return f"https://www.virustotal.com/gui/file/{hash_value}/analysis"

    async def close(self):
        """Close the VirusTotal client."""
        try:
            await self.client.close()
        except RuntimeError:
            # Ignore "this event loop is already running" errors
            pass
        except Exception as e:
            LOGGER.error(f"Error closing VirusTotal client: {e}")


def create_vt_client():
    """Create a new VirusTotal client if enabled and API key is set."""
    if Config.VT_ENABLED and Config.VT_API_KEY:
        return VirusTotalClient()
    return None


async def scan_file(client, message, file_msg):
    """Scan a file for viruses using VirusTotal."""
    # Get file information
    if file_msg.document:
        file_name = file_msg.document.file_name
        file_size = file_msg.document.file_size
        # We don't need file_id here as we'll use the file_msg directly for download
    elif file_msg.video:
        file_name = (
            file_msg.video.file_name if file_msg.video.file_name else "video.mp4"
        )
        file_size = file_msg.video.file_size
        # We don't need file_id here as we'll use the file_msg directly for download
    elif file_msg.audio:
        file_name = (
            file_msg.audio.file_name if file_msg.audio.file_name else "audio.mp3"
        )
        file_size = file_msg.audio.file_size
        # We don't need file_id here as we'll use the file_msg directly for download
    elif file_msg.photo:
        file_name = f"photo_{int(time.time())}.jpg"
        file_size = (
            file_msg.photo.file_size if hasattr(file_msg.photo, "file_size") else 0
        )
        # We don't need file_id here as we'll use the file_msg directly for download
    else:
        error_msg = await send_message(message, "Unsupported file type.")
        # Auto-delete error message after 5 minutes
        create_task(auto_delete_message(error_msg, time=300))
        return

    # Check file size
    if file_size > Config.VT_MAX_FILE_SIZE:
        error_msg = await send_message(
            message,
            f"File size exceeds the maximum allowed size for VirusTotal scanning ({get_readable_file_size(Config.VT_MAX_FILE_SIZE)}).",
        )
        # Auto-delete error message after 5 minutes
        create_task(auto_delete_message(error_msg, time=300))
        return

    # Send initial message
    status_msg = await send_message(
        message, "⏳ Downloading file for virus scanning..."
    )
    # Auto-delete status message after 5 minutes (only if it's an error)
    status_delete_task = create_task(auto_delete_message(status_msg, time=300))

    # Create a new VirusTotal client for this scan
    vt_client = create_vt_client()
    if not vt_client:
        error_msg = await edit_message(
            status_msg, "❌ Failed to initialize VirusTotal client."
        )
        # Auto-delete error message after 5 minutes
        create_task(auto_delete_message(error_msg, time=300))
        return

    file_path = None
    try:
        # Download the file
        file_path = os.path.join(DOWNLOAD_DIR, f"vt_{file_name}")
        await client.download_media(message=file_msg, file_name=file_path)

        # Update status message
        await edit_message(status_msg, "⏳ Analyzing file with VirusTotal...")

        # Analyze the file
        result = await vt_client.analyze_file(file_path)

        # Process results
        stats = result.get("stats", {})
        malicious = stats.get("malicious", 0)
        suspicious = stats.get("suspicious", 0)
        harmless = stats.get("harmless", 0)
        undetected = stats.get("undetected", 0)

        # Determine threat level
        if malicious >= 3:
            threat_status = "❌ POTENTIALLY DANGEROUS"
        elif malicious > 0 or suspicious > 0:
            threat_status = "⚠️ SUSPICIOUS"
        else:
            threat_status = "✅ SAFE"

        # Format response
        response = "<b>VirusTotal Scan Results</b>\n\n"
        response += f"<b>File:</b> {html.escape(file_name)}\n"
        response += f"<b>Size:</b> {get_readable_file_size(file_size)}\n"
        response += f"<b>Status:</b> {threat_status}\n\n"
        response += "<b>Detection Summary:</b>\n"
        response += f"- Malicious: {malicious}\n"
        response += f"- Suspicious: {suspicious}\n"
        response += f"- Harmless: {harmless}\n"
        response += f"- Undetected: {undetected}\n\n"

        # Add link to full report
        response += f"<b>Full Report:</b> <a href='{result.get('link', '')}'>View on VirusTotal</a>"

        # Send results
        await edit_message(status_msg, response)

    except Exception as e:
        LOGGER.error(f"Error in VirusTotal scan: {e}")
        # For error messages, keep the auto-deletion
        error_msg = await edit_message(status_msg, f"❌ Error scanning file: {e}")
        # No need to cancel the status_delete_task as it will auto-delete the error message
    else:
        # If scan was successful, cancel the auto-deletion task for the result message
        status_delete_task.cancel()
    finally:
        # Clean up
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                LOGGER.error(f"Error removing temporary file: {e}")

        # Close the client
        if vt_client:
            await vt_client.close()


async def scan_url(message, url):
    """Scan a URL for viruses using VirusTotal."""
    # Send initial message
    status_msg = await send_message(
        message, f"⏳ Analyzing URL with VirusTotal: {url}"
    )
    # Auto-delete status message after 5 minutes (only if it's an error)
    status_delete_task = create_task(auto_delete_message(status_msg, time=300))

    # Create a new VirusTotal client for this scan
    vt_client = create_vt_client()
    if not vt_client:
        error_msg = await edit_message(
            status_msg, "❌ Failed to initialize VirusTotal client."
        )
        # Auto-delete error message after 5 minutes
        create_task(auto_delete_message(error_msg, time=300))
        return

    try:
        # Analyze the URL
        result = await vt_client.analyze_url(url)

        # Process results
        stats = result.get("stats", {})
        malicious = stats.get("malicious", 0)
        suspicious = stats.get("suspicious", 0)
        harmless = stats.get("harmless", 0)
        undetected = stats.get("undetected", 0)

        # Determine threat level
        if malicious >= 3:
            threat_status = "❌ POTENTIALLY DANGEROUS"
        elif malicious > 0 or suspicious > 0:
            threat_status = "⚠️ SUSPICIOUS"
        else:
            threat_status = "✅ SAFE"

        # Format response
        response = "<b>VirusTotal URL Scan Results</b>\n\n"
        response += f"<b>URL:</b> {html.escape(url)}\n"
        response += f"<b>Status:</b> {threat_status}\n\n"
        response += "<b>Detection Summary:</b>\n"
        response += f"- Malicious: {malicious}\n"
        response += f"- Suspicious: {suspicious}\n"
        response += f"- Harmless: {harmless}\n"
        response += f"- Undetected: {undetected}\n\n"

        # Add link to full report
        response += f"<b>Full Report:</b> <a href='{result.get('link', '')}'>View on VirusTotal</a>"

        # Send results
        await edit_message(status_msg, response)

    except Exception as e:
        LOGGER.error(f"Error in VirusTotal URL scan: {e}")
        # For error messages, keep the auto-deletion
        error_msg = await edit_message(status_msg, f"❌ Error scanning URL: {e}")
        # No need to cancel the status_delete_task as it will auto-delete the error message
    else:
        # If scan was successful, cancel the auto-deletion task for the result message
        status_delete_task.cancel()
    finally:
        # Close the client
        if vt_client:
            await vt_client.close()


@new_task
async def virustotal_scan(client, message):
    """
    Command handler for /virustotal
    Scans a file or URL for viruses using VirusTotal
    """
    # Auto-delete command message after 5 minutes
    create_task(auto_delete_message(message, time=300))

    # Check if VirusTotal is enabled
    if not Config.VT_ENABLED:
        error_msg = await send_message(
            message, "VirusTotal scanning is disabled. Enable it in bot settings."
        )
        # Auto-delete error message after 5 minutes
        create_task(auto_delete_message(error_msg, time=300))
        return

    # Check if API key is set
    if not Config.VT_API_KEY:
        error_msg = await send_message(
            message, "VirusTotal API key is not set. Please set it in bot settings."
        )
        # Auto-delete error message after 5 minutes
        create_task(auto_delete_message(error_msg, time=300))
        return

    # Check if VirusTotal client can be created
    if not create_vt_client():
        error_msg = await send_message(
            message, "Failed to initialize VirusTotal client."
        )
        # Auto-delete error message after 5 minutes
        create_task(auto_delete_message(error_msg, time=300))
        return

    # Check if this is a reply to a message
    replied = message.reply_to_message

    # Auto-delete replied message after 5 minutes if it exists
    if replied:
        create_task(auto_delete_message(replied, time=300))

    # If this is a command with a URL
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        url = args[1].strip()
        if is_url(url):
            await scan_url(message, url)
            return

    # If this is a reply to a message with a URL
    if replied and replied.text:
        text = replied.text
        urls = [word for word in text.split() if is_url(word)]
        if urls:
            await scan_url(message, urls[0])
            return

    # If this is a reply to a file
    if replied and (
        replied.document or replied.video or replied.audio or replied.photo
    ):
        await scan_file(client, message, replied)
        return

    # Auto PM scanning has been removed

    # If none of the above, show usage instructions
    error_msg = await send_message(
        message,
        "Please use one of the following methods:\n"
        "1. Reply to a file with /virustotal to scan it\n"
        "2. Reply to a message containing a URL with /virustotal\n"
        "3. Use /virustotal <url> to scan a URL directly",
    )
    # Auto-delete error message after 5 minutes
    create_task(auto_delete_message(error_msg, time=300))
