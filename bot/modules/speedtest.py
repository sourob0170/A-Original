import re
import subprocess

from speedtest import Speedtest

from bot import LOGGER
from bot.core.aeon_client import TgClient
from bot.helper.ext_utils.bot_utils import new_task
from bot.helper.ext_utils.status_utils import get_readable_file_size
from bot.helper.telegram_helper.message_utils import (
    delete_message,
    edit_message,
    send_message,
)


def get_cloudflare_speedtest_results():
    """Get Cloudflare speedtest results using speedtest-cloudflare-cli"""
    try:
        # Run speedtest-cloudflare-cli using Python module approach
        # Increased timeout for slow connections
        result = subprocess.run(
            [
                "python",
                "-c",
                "from speedtest_cloudflare_cli.main import main; main()",
                "--json",
                "--download",
                "--upload",
            ],
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout for slow connections
            check=False,
        )

        if result.returncode != 0:
            return None

        output = result.stdout

        # Parse Python dict output (not JSON format)
        try:
            # Extract the dictionary part from the output
            dict_start = output.find("{")
            if dict_start == -1:
                raise ValueError("No dictionary found in output")

            dict_part = output[dict_start:]

            # Use eval to parse Python dict format (safe since we control the source)
            # First, clean up the datetime object
            dict_part = re.sub(
                r"datetime\.datetime\([^)]+\)", '"datetime_object"', dict_part
            )

            data = eval(dict_part)

            # Extract values from dict structure
            download_data = data.get("download", {})
            upload_data = data.get("upload", {})
            metadata = data.get("metadata", {})

            download_speed = (
                f"{download_data.get('speed', 0):.2f} Mbps"
                if download_data.get("speed")
                else "Test failed"
            )
            upload_speed = (
                f"{upload_data.get('speed', 0):.2f} Mbps"
                if upload_data.get("speed")
                else "Test failed"
            )

            # Use download latency if available, otherwise use http_latency
            ping_latency = download_data.get("latency") or download_data.get(
                "http_latency", 0
            )
            ping_result = f"{ping_latency:.2f} ms" if ping_latency else "N/A"

            # Extract jitter from download data
            download_jitter = download_data.get("jitter", 0)
            jitter = f"{download_jitter:.2f} ms" if download_jitter else "N/A"

            # Extract HTTP latency
            http_lat = download_data.get("http_latency", 0)
            http_latency = f"{http_lat:.2f} ms" if http_lat else "N/A"

            # Extract metadata
            ip_address = metadata.get("client_ip", "N/A")
            isp = metadata.get("isp", "N/A")

            city = metadata.get("city", "")
            region = metadata.get("region", "")
            country = metadata.get("country", "")

            location_parts = []
            if city:
                location_parts.append(city)
            if region and region != city:
                location_parts.append(region)
            if country:
                location_parts.append(country)

            location = ", ".join(location_parts) if location_parts else "N/A"
            hostname = metadata.get("hostname", "speed.cloudflare.com")
            protocol = metadata.get("http_protocol", "HTTP/2")
            timestamp = str(data.get("timestamp", "N/A"))

        except Exception:
            # Fall back to regex parsing if dict parsing fails
            download_speed = "Test failed"
            upload_speed = "Test failed"
            ping_result = "N/A"
            jitter = "N/A"
            http_latency = "N/A"
            ip_address = "N/A"
            isp = "N/A"
            location = "N/A"
            hostname = "N/A"
            protocol = "N/A"
            timestamp = "N/A"

            # Try regex fallback for speed values
            try:
                speed_match = re.search(r"'speed':\s*(\d+\.?\d*)", output)
                if speed_match:
                    download_speed = f"{float(speed_match.group(1)):.2f} Mbps"

                # Find second speed value for upload
                speeds = re.findall(r"'speed':\s*(\d+\.?\d*)", output)
                if len(speeds) >= 2:
                    upload_speed = f"{float(speeds[1]):.2f} Mbps"
            except Exception:
                pass

        return {
            "download_speed": download_speed,
            "upload_speed": upload_speed,
            "ping": ping_result,
            "jitter": jitter,
            "http_latency": http_latency,
            "ip": ip_address,
            "isp": isp,
            "location": location,
            "hostname": hostname,
            "protocol": protocol,
            "timestamp": timestamp,
            "server": "Cloudflare",
            "note": "Cloudflare speed test completed successfully",
        }

    except subprocess.TimeoutExpired:
        return None
    except Exception:
        return None


def get_fallback_speedtest_results():
    """Fallback speedtest using regular speedtest-cli (speedtest.net format)"""
    try:
        # Run regular speedtest-cli command
        result = subprocess.run(
            ["speedtest-cli"],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )

        if result.returncode != 0:
            return None

        output = result.stdout

        # Parse speedtest.net format
        download_speed = "Test failed"
        upload_speed = "Test failed"
        ping_result = "N/A"
        ip_address = "N/A"
        isp = "N/A"
        location = "N/A"
        server_info = "N/A"

        # Extract download speed (e.g., "Download: 3294.62 Mbit/s")
        download_match = re.search(r"Download:\s*(\d+\.?\d*)\s*Mbit/s", output)
        if download_match:
            download_mbps = float(download_match.group(1))
            download_speed = f"{download_mbps:.2f} Mbps"

        # Extract upload speed (e.g., "Upload: 3098.67 Mbit/s")
        upload_match = re.search(r"Upload:\s*(\d+\.?\d*)\s*Mbit/s", output)
        if upload_match:
            upload_mbps = float(upload_match.group(1))
            upload_speed = f"{upload_mbps:.2f} Mbps"

        # Extract ping and server info (e.g., "Hosted by BT Ireland (Dublin) [1.10 km]: 1.437 ms")
        server_match = re.search(r"Hosted by ([^:]+):\s*(\d+\.?\d*)\s*ms", output)
        if server_match:
            server_info = server_match.group(1).strip()
            ping_result = f"{float(server_match.group(2)):.2f} ms"

        # Extract IP and ISP info (e.g., "Testing from Amazon.com (18.201.55.198)...")
        testing_match = re.search(r"Testing from ([^(]+)\(([^)]+)\)", output)
        if testing_match:
            isp = testing_match.group(1).strip()
            ip_address = testing_match.group(2).strip()

        # Extract location from server info if available
        if server_info != "N/A":
            # Try to extract location from server name (e.g., "BT Ireland (Dublin)")
            location_match = re.search(r"\(([^)]+)\)", server_info)
            if location_match:
                location = location_match.group(1).strip()

        return {
            "download_speed": download_speed,
            "upload_speed": upload_speed,
            "ping": ping_result,
            "jitter": "N/A",
            "http_latency": "N/A",
            "ip": ip_address,
            "isp": isp,
            "location": location,
            "hostname": "speedtest.net",
            "protocol": "N/A",
            "timestamp": "N/A",
            "server": "Speedtest.net (Fallback)",
            "note": "Fallback speedtest completed successfully",
        }

    except subprocess.TimeoutExpired:
        return None
    except Exception:
        return None


def get_standard_speedtest_results():
    """Get standard speedtest results using speedtest-net library"""
    try:
        test = Speedtest()
        test.get_best_server()
        test.download()
        test.upload()
        return test.results
    except Exception:
        return None


@new_task
async def speedtest(_, message):
    """Enhanced speedtest command with both standard and Cloudflare tests"""
    # Delete the /speedtest command message immediately
    await delete_message(message)

    # Initialize status message
    status_msg = await send_message(message, "🚀 <b>Initializing Speed Tests...</b>")

    # Run standard speedtest first
    await edit_message(
        status_msg,
        "🔄 <b>Running Standard Speedtest...</b>\n<i>Testing with nearest server...</i>",
    )

    standard_result = await TgClient.bot.loop.run_in_executor(
        None, get_standard_speedtest_results
    )

    if standard_result:
        # Format standard speedtest results with enhanced display
        standard_speed_text = "<b>🚀 STANDARD SPEEDTEST RESULTS</b>\n\n"
        standard_speed_text += "<b>📊 Performance Metrics:</b>\n"
        standard_speed_text += (
            f"• <b>Ping:</b> <code>{standard_result.ping:.2f} ms</code>\n"
        )
        standard_speed_text += f"• <b>Download:</b> <code>{get_readable_file_size(standard_result.download / 8)}/s</code> <i>({standard_result.download / 1_000_000:.2f} Mbps)</i>\n"
        standard_speed_text += f"• <b>Upload:</b> <code>{get_readable_file_size(standard_result.upload / 8)}/s</code> <i>({standard_result.upload / 1_000_000:.2f} Mbps)</i>\n\n"

        standard_speed_text += "<b>🌐 Connection Details:</b>\n"
        standard_speed_text += (
            f"• <b>IP Address:</b> <code>{standard_result.client['ip']}</code>\n"
        )
        standard_speed_text += (
            f"• <b>ISP:</b> <code>{standard_result.client['isp']}</code>\n"
        )
        standard_speed_text += (
            f"• <b>Server:</b> <code>{standard_result.server['name']}</code>\n"
        )
        standard_speed_text += f"• <b>Location:</b> <code>{standard_result.server['name']}, {standard_result.server['country']}</code>\n"
        standard_speed_text += (
            f"• <b>Distance:</b> <code>{standard_result.server['d']:.2f} km</code>"
        )

        # Send standard speedtest results with photo
        try:
            await send_message(
                message, standard_speed_text, photo=standard_result.share()
            )
        except Exception as e:
            LOGGER.error(f"Error sending standard speedtest with photo: {e}")
            await send_message(message, standard_speed_text)
    else:
        error_text = "<b>🚀 STANDARD SPEEDTEST</b>\n\n<code>❌ Standard speedtest failed to complete</code>"
        await send_message(message, error_text)

    # Update status for Cloudflare test
    await edit_message(
        status_msg,
        "☁️ <b>Running Cloudflare Speedtest...</b>\n<i>Testing with Cloudflare servers...</i>\n<i>⏱️ This may take several minutes for slow connections...</i>",
    )

    # Run Cloudflare speedtest with fallback
    cf_result = await TgClient.bot.loop.run_in_executor(
        None, get_cloudflare_speedtest_results
    )

    # If Cloudflare test failed, try fallback
    if not cf_result:
        await edit_message(
            status_msg,
            "🔄 <b>Cloudflare test failed, running fallback speedtest...</b>\n<i>Using speedtest.net servers...</i>\n<i>⏱️ This may take several minutes...</i>",
        )
        cf_result = await TgClient.bot.loop.run_in_executor(
            None, get_fallback_speedtest_results
        )

    if cf_result:
        # Format enhanced Cloudflare speedtest results
        cf_speed_text = "<b>☁️ CLOUDFLARE SPEEDTEST RESULTS</b>\n\n"
        cf_speed_text += "<b>📊 Performance Metrics:</b>\n"
        cf_speed_text += (
            f"• <b>Ping (Latency):</b> <code>{cf_result['ping']}</code>\n"
        )

        if cf_result["jitter"] != "N/A":
            cf_speed_text += f"• <b>Jitter:</b> <code>{cf_result['jitter']}</code>\n"

        if cf_result["http_latency"] != "N/A":
            cf_speed_text += (
                f"• <b>HTTP Latency:</b> <code>{cf_result['http_latency']}</code>\n"
            )

        cf_speed_text += (
            f"• <b>Download:</b> <code>{cf_result['download_speed']}</code>\n"
        )
        cf_speed_text += (
            f"• <b>Upload:</b> <code>{cf_result['upload_speed']}</code>\n\n"
        )

        cf_speed_text += "<b>🌐 Connection Details:</b>\n"
        cf_speed_text += f"• <b>IP Address:</b> <code>{cf_result['ip']}</code>\n"
        cf_speed_text += f"• <b>ISP:</b> <code>{cf_result['isp']}</code>\n"
        cf_speed_text += f"• <b>Location:</b> <code>{cf_result['location']}</code>\n"

        if cf_result["hostname"] != "N/A":
            cf_speed_text += (
                f"• <b>Server:</b> <code>{cf_result['hostname']}</code>\n"
            )

        if cf_result["protocol"] != "N/A":
            cf_speed_text += (
                f"• <b>Protocol:</b> <code>{cf_result['protocol']}</code>\n"
            )

        if cf_result["timestamp"] != "N/A":
            cf_speed_text += (
                f"• <b>Test Time:</b> <code>{cf_result['timestamp'][:19]}</code>"
            )
    else:
        cf_speed_text = "<b>☁️ CLOUDFLARE SPEEDTEST</b>\n\n<code>❌ Cloudflare speedtest failed to complete</code>"

    # Send Cloudflare results
    await send_message(message, cf_speed_text)

    # Clean up status message
    await delete_message(status_msg)
