import asyncio
import time
from typing import ClassVar

import psutil

from bot import LOGGER, StartTime
from bot.helper.ext_utils.status_utils import get_readable_time


class SystemMonitor:
    """Real-time system monitoring for streaming server"""

    _monitoring_active = False
    _stats_history: ClassVar[list[dict]] = []
    _max_history = 100  # Keep last 100 readings

    @staticmethod
    async def start_monitoring(interval: int = 30):
        """Start continuous system monitoring"""
        if SystemMonitor._monitoring_active:
            return

        SystemMonitor._monitoring_active = True
        LOGGER.info("Starting system monitoring for streaming server")

        while SystemMonitor._monitoring_active:
            try:
                stats = SystemMonitor.get_current_stats()
                SystemMonitor._add_to_history(stats)
                await asyncio.sleep(interval)
            except Exception as e:
                LOGGER.error(f"Error in system monitoring: {e}")
                await asyncio.sleep(interval)

    @staticmethod
    def stop_monitoring():
        """Stop system monitoring"""
        SystemMonitor._monitoring_active = False
        LOGGER.info("Stopped system monitoring")

    @staticmethod
    def get_current_stats() -> dict:
        """Get current system statistics"""
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()

            # Memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_used = memory.used
            memory_total = memory.total

            # Disk usage
            disk = psutil.disk_usage("/")
            disk_percent = disk.percent
            disk_used = disk.used
            disk_total = disk.total

            # Network I/O
            network = psutil.net_io_counters()
            bytes_sent = network.bytes_sent
            bytes_recv = network.bytes_recv

            # System uptime
            uptime = time.time() - StartTime

            # Process info
            process = psutil.Process()
            process_memory = process.memory_info().rss
            process_cpu = process.cpu_percent()

            return {
                "timestamp": time.time(),
                "cpu": {
                    "percent": cpu_percent,
                    "count": cpu_count,
                    "process_percent": process_cpu,
                },
                "memory": {
                    "percent": memory_percent,
                    "used": memory_used,
                    "total": memory_total,
                    "process_used": process_memory,
                },
                "disk": {
                    "percent": disk_percent,
                    "used": disk_used,
                    "total": disk_total,
                },
                "network": {"bytes_sent": bytes_sent, "bytes_recv": bytes_recv},
                "uptime": uptime,
            }

        except Exception as e:
            LOGGER.error(f"Error getting system stats: {e}")
            return {}

    @staticmethod
    def _add_to_history(stats: dict):
        """Add stats to history with size limit"""
        if stats:
            SystemMonitor._stats_history.append(stats)

            # Keep only recent history
            if len(SystemMonitor._stats_history) > SystemMonitor._max_history:
                SystemMonitor._stats_history = SystemMonitor._stats_history[
                    -SystemMonitor._max_history :
                ]

    @staticmethod
    def get_formatted_stats() -> str:
        """Get formatted system statistics for display"""
        try:
            stats = SystemMonitor.get_current_stats()
            if not stats:
                return "❌ Unable to get system stats"

            # Format uptime
            uptime_str = get_readable_time(int(stats["uptime"]))

            # Format memory sizes
            def format_bytes(bytes_val):
                for unit in ["B", "KB", "MB", "GB", "TB"]:
                    if bytes_val < 1024.0:
                        return f"{bytes_val:.1f} {unit}"
                    bytes_val /= 1024.0
                return f"{bytes_val:.1f} PB"

            memory_used = format_bytes(stats["memory"]["used"])
            memory_total = format_bytes(stats["memory"]["total"])
            disk_used = format_bytes(stats["disk"]["used"])
            disk_total = format_bytes(stats["disk"]["total"])

            network_sent = format_bytes(stats["network"]["bytes_sent"])
            network_recv = format_bytes(stats["network"]["bytes_recv"])

            formatted = f"""
<b>🖥 System Statistics</b>

<b>⏱ Uptime:</b> <code>{uptime_str}</code>

<b>🔥 CPU Usage:</b>
├ <b>Overall:</b> <code>{stats["cpu"]["percent"]:.1f}%</code>
├ <b>Cores:</b> <code>{stats["cpu"]["count"]}</code>
└ <b>Bot Process:</b> <code>{stats["cpu"]["process_percent"]:.1f}%</code>

<b>🧠 Memory Usage:</b>
├ <b>Overall:</b> <code>{stats["memory"]["percent"]:.1f}%</code>
├ <b>Used:</b> <code>{memory_used} / {memory_total}</code>
└ <b>Bot Process:</b> <code>{format_bytes(stats["memory"]["process_used"])}</code>

<b>💾 Disk Usage:</b>
├ <b>Used:</b> <code>{stats["disk"]["percent"]:.1f}%</code>
└ <b>Space:</b> <code>{disk_used} / {disk_total}</code>

<b>🌐 Network I/O:</b>
├ <b>Sent:</b> <code>{network_sent}</code>
└ <b>Received:</b> <code>{network_recv}</code>
"""

            return formatted.strip()

        except Exception as e:
            LOGGER.error(f"Error formatting stats: {e}")
            return "❌ Error formatting system stats"

    @staticmethod
    def get_performance_summary() -> dict:
        """Get performance summary from history"""
        try:
            if not SystemMonitor._stats_history:
                return {}

            recent_stats = SystemMonitor._stats_history[-10:]  # Last 10 readings

            cpu_values = [s["cpu"]["percent"] for s in recent_stats if "cpu" in s]
            memory_values = [
                s["memory"]["percent"] for s in recent_stats if "memory" in s
            ]

            if not cpu_values or not memory_values:
                return {}

            return {
                "avg_cpu": sum(cpu_values) / len(cpu_values),
                "max_cpu": max(cpu_values),
                "avg_memory": sum(memory_values) / len(memory_values),
                "max_memory": max(memory_values),
                "readings_count": len(recent_stats),
            }

        except Exception as e:
            LOGGER.error(f"Error getting performance summary: {e}")
            return {}

    @staticmethod
    def is_system_healthy() -> bool:
        """Check if system is healthy for streaming"""
        try:
            stats = SystemMonitor.get_current_stats()
            if not stats:
                return False

            # Check thresholds
            cpu_threshold = 90.0
            memory_threshold = 90.0
            disk_threshold = 95.0

            if stats["cpu"]["percent"] > cpu_threshold:
                LOGGER.warning(f"High CPU usage: {stats['cpu']['percent']:.1f}%")
                return False

            if stats["memory"]["percent"] > memory_threshold:
                LOGGER.warning(
                    f"High memory usage: {stats['memory']['percent']:.1f}%"
                )
                return False

            if stats["disk"]["percent"] > disk_threshold:
                LOGGER.warning(f"High disk usage: {stats['disk']['percent']:.1f}%")
                return False

            return True

        except Exception as e:
            LOGGER.error(f"Error checking system health: {e}")
            return True  # Assume healthy on error

    @staticmethod
    def get_history_stats(minutes: int = 30) -> list[dict]:
        """Get historical stats for specified minutes"""
        try:
            cutoff_time = time.time() - (minutes * 60)
            return [
                stats
                for stats in SystemMonitor._stats_history
                if stats.get("timestamp", 0) > cutoff_time
            ]
        except Exception as e:
            LOGGER.error(f"Error getting history stats: {e}")
            return []
