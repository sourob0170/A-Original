import asyncio
import time
from typing import ClassVar

from bot import LOGGER


class DCChecker:
    """Handles Telegram datacenter detection and optimization"""

    # Telegram DC locations (approximate)
    DC_LOCATIONS: ClassVar[dict[int, dict[str, str]]] = {
        1: {"name": "Miami, FL", "region": "Americas"},
        2: {"name": "Amsterdam, NL", "region": "Europe"},
        3: {"name": "Miami, FL", "region": "Americas"},
        4: {"name": "Amsterdam, NL", "region": "Europe"},
        5: {"name": "Singapore, SG", "region": "Asia-Pacific"},
    }

    _dc_cache: ClassVar[dict[int, dict]] = {}

    @staticmethod
    def get_user_dc_info(user) -> dict:
        """Get user's datacenter information"""
        try:
            dc_id = getattr(user, "dc_id", None)
            if not dc_id:
                return {
                    "dc_id": None,
                    "location": "Unknown",
                    "region": "Unknown",
                    "status": "Unable to detect",
                }

            dc_info = DCChecker.DC_LOCATIONS.get(
                dc_id, {"name": f"DC{dc_id}", "region": "Unknown"}
            )

            return {
                "dc_id": dc_id,
                "location": dc_info["name"],
                "region": dc_info["region"],
                "status": "Detected",
            }

        except Exception as e:
            LOGGER.error(f"Error getting user DC info: {e}")
            return {
                "dc_id": None,
                "location": "Error",
                "region": "Error",
                "status": "Error detecting DC",
            }

    @staticmethod
    def format_dc_info(dc_info: dict) -> str:
        """Format DC information for display"""
        try:
            if not dc_info.get("dc_id"):
                return "🌐 <b>Datacenter:</b> <code>Unable to detect</code>"

            dc_id = dc_info["dc_id"]
            location = dc_info["location"]
            region = dc_info["region"]

            # Add emoji based on region
            region_emoji = {
                "Americas": "🌎",
                "Europe": "🌍",
                "Asia-Pacific": "🌏",
            }.get(region, "🌐")

            return (
                f"{region_emoji} <b>Your DC:</b> <code>DC{dc_id}</code> ({location})"
            )

        except Exception as e:
            LOGGER.error(f"Error formatting DC info: {e}")
            return "🌐 <b>Datacenter:</b> <code>Error</code>"

    @staticmethod
    async def check_dc_latency(dc_id: int) -> float | None:
        """Check latency to specific datacenter (simulated)"""
        try:
            # This is a simplified simulation
            # In a real implementation, you might ping actual Telegram servers

            base_latency = {
                1: 150,  # Miami
                2: 50,  # Amsterdam
                3: 150,  # Miami
                4: 50,  # Amsterdam
                5: 200,  # Singapore
            }.get(dc_id, 100)

            # Add some random variation
            import random

            variation = random.uniform(-20, 50)
            latency = base_latency + variation

            # Simulate network delay
            await asyncio.sleep(0.1)

            return max(latency, 10)  # Minimum 10ms

        except Exception as e:
            LOGGER.error(f"Error checking DC latency: {e}")
            return None

    @staticmethod
    async def get_optimal_dc(user_dc: int) -> dict:
        """Get optimal datacenter for streaming"""
        try:
            # Check latency to user's DC and nearby DCs
            latencies = {}

            # Always check user's DC
            if user_dc:
                latencies[user_dc] = await DCChecker.check_dc_latency(user_dc)

            # Check a few other DCs for comparison
            test_dcs = [2, 4, 5]  # Common DCs
            if user_dc not in test_dcs:
                test_dcs.append(user_dc)

            for dc_id in test_dcs:
                if dc_id != user_dc:
                    latencies[dc_id] = await DCChecker.check_dc_latency(dc_id)

            # Find optimal DC (lowest latency)
            optimal_dc = min(
                latencies.keys(), key=lambda x: latencies[x] or float("inf")
            )
            optimal_latency = latencies[optimal_dc]

            dc_info = DCChecker.DC_LOCATIONS.get(optimal_dc, {})

            return {
                "dc_id": optimal_dc,
                "latency": optimal_latency,
                "location": dc_info.get("name", f"DC{optimal_dc}"),
                "region": dc_info.get("region", "Unknown"),
                "is_user_dc": optimal_dc == user_dc,
                "all_latencies": latencies,
            }

        except Exception as e:
            LOGGER.error(f"Error getting optimal DC: {e}")
            return {}

    @staticmethod
    def cache_user_dc(user_id: int, dc_info: dict):
        """Cache user's DC information"""
        try:
            DCChecker._dc_cache[user_id] = {**dc_info, "cached_at": time.time()}
        except Exception as e:
            LOGGER.error(f"Error caching user DC: {e}")

    @staticmethod
    def get_cached_dc(user_id: int, max_age: int = 3600) -> dict | None:
        """Get cached DC information"""
        try:
            if user_id not in DCChecker._dc_cache:
                return None

            cached_data = DCChecker._dc_cache[user_id]
            cache_age = time.time() - cached_data.get("cached_at", 0)

            if cache_age > max_age:
                del DCChecker._dc_cache[user_id]
                return None

            return cached_data

        except Exception as e:
            LOGGER.error(f"Error getting cached DC: {e}")
            return None

    @staticmethod
    def get_dc_recommendations(user_dc: int) -> dict:
        """Get recommendations based on user's DC"""
        try:
            recommendations = {
                "streaming_quality": "Auto",
                "buffer_size": "Medium",
                "connection_type": "Standard",
            }

            # Recommendations based on DC location
            if user_dc in [1, 3]:  # Americas
                recommendations.update(
                    {
                        "streaming_quality": "High",
                        "buffer_size": "Large",
                        "connection_type": "Optimized for Americas",
                    }
                )
            elif user_dc in [2, 4]:  # Europe
                recommendations.update(
                    {
                        "streaming_quality": "High",
                        "buffer_size": "Medium",
                        "connection_type": "Optimized for Europe",
                    }
                )
            elif user_dc == 5:  # Asia-Pacific
                recommendations.update(
                    {
                        "streaming_quality": "Medium",
                        "buffer_size": "Large",
                        "connection_type": "Optimized for Asia-Pacific",
                    }
                )

            return recommendations

        except Exception as e:
            LOGGER.error(f"Error getting DC recommendations: {e}")
            return {}

    @staticmethod
    def format_dc_stats() -> str:
        """Format DC statistics for display"""
        try:
            if not DCChecker._dc_cache:
                return "📊 <b>DC Statistics:</b> <code>No data available</code>"

            dc_counts = {}
            total_users = len(DCChecker._dc_cache)

            for user_data in DCChecker._dc_cache.values():
                dc_id = user_data.get("dc_id")
                if dc_id:
                    dc_counts[dc_id] = dc_counts.get(dc_id, 0) + 1

            stats_text = f"📊 <b>DC Statistics</b> (Total: {total_users})\n\n"

            for dc_id, count in sorted(dc_counts.items()):
                dc_info = DCChecker.DC_LOCATIONS.get(dc_id, {})
                location = dc_info.get("name", f"DC{dc_id}")
                percentage = (count / total_users) * 100

                stats_text += f"🌐 <b>DC{dc_id}</b> ({location}): <code>{count}</code> ({percentage:.1f}%)\n"

            return stats_text.strip()

        except Exception as e:
            LOGGER.error(f"Error formatting DC stats: {e}")
            return "📊 <b>DC Statistics:</b> <code>Error</code>"

    @staticmethod
    def cleanup_cache(max_age: int = 86400):
        """Clean up old cache entries"""
        try:
            current_time = time.time()
            expired_users = [
                user_id
                for user_id, data in DCChecker._dc_cache.items()
                if current_time - data.get("cached_at", 0) > max_age
            ]

            for user_id in expired_users:
                del DCChecker._dc_cache[user_id]

            if expired_users:
                LOGGER.info(
                    f"Cleaned up {len(expired_users)} expired DC cache entries"
                )

        except Exception as e:
            LOGGER.error(f"Error cleaning up DC cache: {e}")

    @staticmethod
    def get_cache_stats() -> dict:
        """Get cache statistics"""
        try:
            return {
                "cached_users": len(DCChecker._dc_cache),
                "cache_size_mb": len(str(DCChecker._dc_cache)) / (1024 * 1024),
            }
        except Exception as e:
            LOGGER.error(f"Error getting cache stats: {e}")
            return {}
