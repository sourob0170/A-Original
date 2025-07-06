import asyncio
import time
from collections import deque
from typing import ClassVar

from bot import LOGGER
from bot.core.aeon_client import TgClient
from bot.core.config_manager import Config


class OptimizedLoadBalancer:
    """Lightweight, high-performance load balancer for bot clients with unified client management"""

    # Use more memory-efficient data structures with slots for better memory usage
    _client_loads: ClassVar[dict[int, int]] = {}
    _client_health: ClassVar[dict[int, bool]] = {}  # Simplified to boolean
    _client_response_times: ClassVar[dict[int, float]] = {}
    _client_error_counts: ClassVar[dict[int, int]] = {}
    _last_health_check: float = 0
    _health_check_interval: int = 120  # Increased to 2 minutes for efficiency
    _round_robin_queue: ClassVar[deque] = deque()
    _last_used_client: int = -1
    _initialized: ClassVar[bool] = False

    @staticmethod
    def initialize():
        """Optimized load balancer initialization with minimal overhead"""
        try:
            # Prevent re-initialization - preserve existing helper bots
            if OptimizedLoadBalancer._initialized:
                LOGGER.info(
                    f"LoadBalancer already initialized with {len(OptimizedLoadBalancer._client_loads)} clients"
                )
                return

            # Clear existing data only if not already initialized
            OptimizedLoadBalancer._client_loads.clear()
            OptimizedLoadBalancer._client_health.clear()
            OptimizedLoadBalancer._client_response_times.clear()
            OptimizedLoadBalancer._client_error_counts.clear()
            OptimizedLoadBalancer._round_robin_queue.clear()

            # Initialize main client
            OptimizedLoadBalancer._client_loads[0] = 0
            OptimizedLoadBalancer._client_health[0] = True
            OptimizedLoadBalancer._client_response_times[0] = 0.0
            OptimizedLoadBalancer._client_error_counts[0] = 0
            OptimizedLoadBalancer._round_robin_queue.append(0)

            # Initialize helper clients efficiently (helper_bots is a dict, not list)
            helper_count = 0
            if hasattr(TgClient, "helper_bots") and TgClient.helper_bots:
                LOGGER.info(
                    f"Found {len(TgClient.helper_bots)} helper bots to initialize"
                )
                for helper_id, client in TgClient.helper_bots.items():
                    if client:
                        # Use helper_id as-is since it's already an integer from start_hclient
                        client_id = (
                            helper_id
                            if isinstance(helper_id, int)
                            else int(helper_id)
                        )
                        OptimizedLoadBalancer._client_loads[client_id] = 0
                        OptimizedLoadBalancer._client_health[client_id] = True
                        OptimizedLoadBalancer._client_response_times[client_id] = 0.0
                        OptimizedLoadBalancer._client_error_counts[client_id] = 0
                        OptimizedLoadBalancer._round_robin_queue.append(client_id)
                        helper_count += 1
                        LOGGER.info(
                            f"Initialized helper client {client_id} in LoadBalancer"
                        )
            else:
                # Fallback: If helper_bots not available (e.g., in web server process),
                # initialize placeholder slots based on HELPER_TOKENS count
                from bot.core.config_manager import Config

                if Config.HELPER_TOKENS:
                    helper_tokens = Config.HELPER_TOKENS.split()
                    LOGGER.info(
                        f"TgClient.helper_bots not available, creating {len(helper_tokens)} placeholder helper slots"
                    )
                    for i, _ in enumerate(helper_tokens, start=1):
                        OptimizedLoadBalancer._client_loads[i] = 0
                        OptimizedLoadBalancer._client_health[i] = (
                            True  # Assume healthy initially
                        )
                        OptimizedLoadBalancer._client_response_times[i] = 0.0
                        OptimizedLoadBalancer._client_error_counts[i] = 0
                        OptimizedLoadBalancer._round_robin_queue.append(i)
                        helper_count += 1
                        LOGGER.info(
                            f"Initialized placeholder helper client {i} in LoadBalancer"
                        )
                else:
                    LOGGER.warning(
                        "No helper bots found in TgClient.helper_bots and no HELPER_TOKENS configured"
                    )

            total_clients = len(OptimizedLoadBalancer._client_loads)
            actual_helper_count = total_clients - 1

            # Mark as initialized
            OptimizedLoadBalancer._initialized = True

            LOGGER.info(
                f"Optimized load balancer initialized: {total_clients} clients "
                f"(1 main + {actual_helper_count} helpers) with round-robin and health tracking"
            )

        except Exception as e:
            LOGGER.error(f"Error initializing optimized load balancer: {e}")

    @staticmethod
    def refresh_helper_bots():
        """Refresh helper bots without full re-initialization"""
        try:
            if not OptimizedLoadBalancer._initialized:
                LOGGER.warning(
                    "LoadBalancer not initialized, calling initialize() instead"
                )
                OptimizedLoadBalancer.initialize()
                return

            # Add any new helper bots that weren't previously registered
            if hasattr(TgClient, "helper_bots") and TgClient.helper_bots:
                for helper_id, client in TgClient.helper_bots.items():
                    if (
                        client
                        and helper_id not in OptimizedLoadBalancer._client_loads
                    ):
                        client_id = (
                            helper_id
                            if isinstance(helper_id, int)
                            else int(helper_id)
                        )
                        OptimizedLoadBalancer._client_loads[client_id] = 0
                        OptimizedLoadBalancer._client_health[client_id] = True
                        OptimizedLoadBalancer._client_response_times[client_id] = 0.0
                        OptimizedLoadBalancer._client_error_counts[client_id] = 0
                        OptimizedLoadBalancer._round_robin_queue.append(client_id)
                        LOGGER.info(
                            f"Added new helper client {client_id} to LoadBalancer"
                        )

            total_clients = len(OptimizedLoadBalancer._client_loads)
            helper_count = total_clients - 1
            LOGGER.info(
                f"LoadBalancer refreshed: {total_clients} clients (1 main + {helper_count} helpers)"
            )

        except Exception as e:
            LOGGER.error(f"Error refreshing helper bots in LoadBalancer: {e}")

    @staticmethod
    def get_optimal_client() -> tuple[int, object | None]:
        """Optimized client selection with unified client management and efficient round-robin"""
        try:
            # Ensure initialization (only if not already initialized)
            if not OptimizedLoadBalancer._initialized:
                # Initialize synchronously to avoid repeated initialization
                OptimizedLoadBalancer.initialize()

            # Always ensure we have a fallback to main bot
            if not TgClient.bot:
                LOGGER.warning("Main bot client not available")
                return 0, None

            # Check if load balancing is disabled
            if (
                not getattr(Config, "STREAM_LOAD_BALANCING", True)
                or not OptimizedLoadBalancer._client_loads
            ):
                return 0, TgClient.bot

            # Fast path: use round-robin for healthy clients with optimized selection
            if OptimizedLoadBalancer._round_robin_queue:
                max_attempts = min(
                    len(OptimizedLoadBalancer._round_robin_queue), 3
                )  # Limit attempts for efficiency

                for _ in range(max_attempts):
                    # Rotate queue efficiently
                    OptimizedLoadBalancer._round_robin_queue.rotate(-1)
                    client_id = OptimizedLoadBalancer._round_robin_queue[0]

                    # Quick health and load check
                    if (
                        OptimizedLoadBalancer._client_health.get(client_id, False)
                        and OptimizedLoadBalancer._client_loads.get(client_id, 0) < 8
                    ):  # Reduced max concurrent for better performance
                        client = OptimizedLoadBalancer._get_client_by_id(client_id)
                        if client:
                            return client_id, client
                        # Mark as unhealthy if client not found
                        OptimizedLoadBalancer._client_health[client_id] = False

            # Fallback: find least loaded healthy client (optimized)
            best_client_id = None
            min_load = float("inf")

            for client_id, load in OptimizedLoadBalancer._client_loads.items():
                if (
                    OptimizedLoadBalancer._client_health.get(client_id, False)
                    and load < min_load
                ):
                    client = OptimizedLoadBalancer._get_client_by_id(client_id)
                    if client:
                        min_load = load
                        best_client_id = client_id

            if best_client_id is not None:
                client = OptimizedLoadBalancer._get_client_by_id(best_client_id)
                if client:
                    return best_client_id, client

            # Final fallback to main client
            return 0, TgClient.bot

        except Exception as e:
            LOGGER.error(f"Error getting optimal client: {e}")
            return 0, TgClient.bot

    @staticmethod
    def _get_client_by_id(client_id: int):
        """Unified client retrieval method - handles helper_bots as dict with fallback"""
        try:
            if client_id == 0:
                return TgClient.bot

            # helper_bots is a dictionary, not a list
            if (
                hasattr(TgClient, "helper_bots")
                and TgClient.helper_bots
                and client_id in TgClient.helper_bots
            ):
                return TgClient.helper_bots[client_id]

            # Fallback: If helper_bots not available (e.g., web server process),
            # return main bot client for any helper client request
            if client_id > 0 and TgClient.bot:
                return TgClient.bot

            return None
        except (IndexError, AttributeError, KeyError):
            return None

    @staticmethod
    def increment_load(client_id: int):
        """Optimized load increment with bounds checking"""
        try:
            if client_id in OptimizedLoadBalancer._client_loads:
                OptimizedLoadBalancer._client_loads[client_id] += 1
        except Exception as e:
            LOGGER.error(f"Error incrementing load for client {client_id}: {e}")

    @staticmethod
    def decrement_load(client_id: int):
        """Optimized load decrement with bounds checking"""
        try:
            if client_id in OptimizedLoadBalancer._client_loads:
                OptimizedLoadBalancer._client_loads[client_id] = max(
                    0, OptimizedLoadBalancer._client_loads[client_id] - 1
                )
        except Exception as e:
            LOGGER.error(f"Error decrementing load for client {client_id}: {e}")

    @staticmethod
    def record_client_error(client_id: int):
        """Record client error efficiently"""
        try:
            if client_id in OptimizedLoadBalancer._client_error_counts:
                OptimizedLoadBalancer._client_error_counts[client_id] += 1
                # Mark as unhealthy if too many errors
                if OptimizedLoadBalancer._client_error_counts[client_id] >= 3:
                    OptimizedLoadBalancer._client_health[client_id] = False
                    LOGGER.warning(
                        f"Client {client_id} marked unhealthy due to errors"
                    )
        except Exception as e:
            LOGGER.error(f"Error recording client error: {e}")

    @staticmethod
    def reset_client_errors(client_id: int):
        """Reset client errors and mark as healthy"""
        try:
            if client_id in OptimizedLoadBalancer._client_error_counts:
                OptimizedLoadBalancer._client_error_counts[client_id] = 0
                OptimizedLoadBalancer._client_health[client_id] = True
        except Exception as e:
            LOGGER.error(f"Error resetting client errors: {e}")

    @staticmethod
    async def check_client_health(client_id: int, client) -> bool:
        """Check health of a specific client"""
        try:
            start_time = time.time()

            # Simple health check - try to get bot info
            try:
                if hasattr(client, "get_me"):
                    await asyncio.wait_for(client.get_me(), timeout=5.0)
                    status = "healthy"
                    error_count = 0
                else:
                    status = "unknown"
                    error_count = 0
            except TimeoutError:
                status = "timeout"
                error_count = (
                    OptimizedLoadBalancer._client_error_counts.get(client_id, 0) + 1
                )
            except Exception as e:
                LOGGER.warning(f"Health check failed for client {client_id}: {e}")
                status = "unhealthy"
                error_count = (
                    OptimizedLoadBalancer._client_error_counts.get(client_id, 0) + 1
                )

            response_time = time.time() - start_time

            health_info = {
                "status": status,
                "last_check": time.time(),
                "response_time": response_time,
                "error_count": error_count,
            }

            # Mark as unhealthy if too many errors
            if error_count >= 3:
                health_info["status"] = "unhealthy"

            # Update both health and error count
            OptimizedLoadBalancer._client_health[client_id] = status == "healthy"
            OptimizedLoadBalancer._client_error_counts[client_id] = error_count
            OptimizedLoadBalancer._client_response_times[client_id] = response_time

            return health_info

        except Exception as e:
            LOGGER.error(f"Error checking client health: {e}")
            return {
                "status": "error",
                "last_check": time.time(),
                "response_time": 0,
                "error_count": 999,
            }

    @staticmethod
    async def health_check_all():
        """Perform health check on all clients"""
        try:
            current_time = time.time()

            # Skip if checked recently
            if (
                current_time - OptimizedLoadBalancer._last_health_check
                < OptimizedLoadBalancer._health_check_interval
            ):
                return

            OptimizedLoadBalancer._last_health_check = current_time

            # Check main client
            await OptimizedLoadBalancer.check_client_health(0, TgClient.bot)

            # Check helper clients (optimized for unlimited helper bots)
            if hasattr(TgClient, "helper_bots") and TgClient.helper_bots:
                # Use asyncio.gather for concurrent health checks when many helper bots
                helper_count = len(TgClient.helper_bots)
                if helper_count > 10:
                    # Concurrent health checks for better performance with many bots
                    health_check_tasks = []
                    for i, client in enumerate(TgClient.helper_bots, 1):
                        if client:
                            health_check_tasks.append(
                                OptimizedLoadBalancer.check_client_health(i, client)
                            )
                    if health_check_tasks:
                        await asyncio.gather(
                            *health_check_tasks, return_exceptions=True
                        )
                else:
                    # Sequential health checks for smaller numbers
                    for i, client in enumerate(TgClient.helper_bots, 1):
                        if client:
                            await OptimizedLoadBalancer.check_client_health(
                                i, client
                            )

        except Exception as e:
            LOGGER.error(f"Error in health check: {e}")

    @staticmethod
    def get_load_stats() -> dict:
        """Get current load statistics"""
        try:
            total_load = sum(OptimizedLoadBalancer._client_loads.values())
            healthy_clients = sum(
                1
                for health in OptimizedLoadBalancer._client_health.values()
                if health
            )

            return {
                "total_clients": len(OptimizedLoadBalancer._client_loads),
                "healthy_clients": healthy_clients,
                "total_load": total_load,
                "average_load": total_load / len(OptimizedLoadBalancer._client_loads)
                if OptimizedLoadBalancer._client_loads
                else 0,
                "client_loads": OptimizedLoadBalancer._client_loads.copy(),
                "client_health": {
                    client_id: "healthy" if health else "unhealthy"
                    for client_id, health in OptimizedLoadBalancer._client_health.items()
                },
            }

        except Exception as e:
            LOGGER.error(f"Error getting load stats: {e}")
            return {}

    @staticmethod
    def format_load_stats() -> str:
        """Format load statistics for display"""
        try:
            stats = LoadBalancer.get_load_stats()
            if not stats:
                return "📊 <b>Load Balancer:</b> <code>No data available</code>"

            text = "📊 <b>Load Balancer Statistics</b>\n\n"
            text += (
                f"🤖 <b>Total Clients:</b> <code>{stats['total_clients']}</code>\n"
            )
            text += f"✅ <b>Healthy Clients:</b> <code>{stats['healthy_clients']}</code>\n"
            text += f"⚡ <b>Total Load:</b> <code>{stats['total_load']}</code>\n"
            text += f"📈 <b>Average Load:</b> <code>{stats['average_load']:.1f}</code>\n\n"

            text += "<b>Client Details:</b>\n"
            for client_id, load in stats["client_loads"].items():
                health = stats["client_health"].get(client_id, "unknown")
                health_emoji = {
                    "healthy": "✅",
                    "unhealthy": "❌",
                    "timeout": "⏰",
                    "unknown": "❓",
                    "error": "💥",
                }.get(health, "❓")

                client_name = "Main" if client_id == 0 else f"Helper-{client_id}"
                text += f"{health_emoji} <b>{client_name}:</b> <code>{load}</code> requests\n"

            return text.strip()

        except Exception as e:
            LOGGER.error(f"Error formatting load stats: {e}")
            return "📊 <b>Load Balancer:</b> <code>Error</code>"

    @staticmethod
    async def redistribute_load():
        """Redistribute load if imbalanced"""
        try:
            if not Config.STREAM_LOAD_BALANCING:
                return

            stats = LoadBalancer.get_load_stats()
            if not stats or stats["total_clients"] <= 1:
                return

            # Check if load is imbalanced
            loads = list(stats["client_loads"].values())
            max_load = max(loads)
            min_load = min(loads)

            # If difference is significant, log it (actual redistribution would be complex)
            if max_load - min_load > 10:
                LOGGER.info(
                    f"Load imbalance detected: max={max_load}, min={min_load}"
                )
                # In a real implementation, you might implement request migration

        except Exception as e:
            LOGGER.error(f"Error redistributing load: {e}")

    @staticmethod
    def get_helper_bot_stats():
        """Get detailed statistics about helper bots"""
        try:
            stats = {
                "total_clients": len(OptimizedLoadBalancer._client_loads),
                "main_client": 1,
                "helper_bots": len(OptimizedLoadBalancer._client_loads) - 1,
                "healthy_clients": 0,
                "unhealthy_clients": 0,
                "total_load": 0,
                "client_details": {},
            }

            for client_id, load in OptimizedLoadBalancer._client_loads.items():
                health = OptimizedLoadBalancer._client_health.get(client_id, False)
                error_count = OptimizedLoadBalancer._client_error_counts.get(
                    client_id, 0
                )
                response_time = OptimizedLoadBalancer._client_response_times.get(
                    client_id, 0.0
                )
                status = "healthy" if health else "unhealthy"

                if status == "healthy":
                    stats["healthy_clients"] += 1
                else:
                    stats["unhealthy_clients"] += 1

                stats["total_load"] += load

                client_type = "main" if client_id == 0 else f"helper_{client_id}"
                stats["client_details"][client_type] = {
                    "load": load,
                    "status": status,
                    "error_count": error_count,
                    "response_time": response_time,
                }

            return stats

        except Exception as e:
            LOGGER.error(f"Error getting helper bot stats: {e}")
            return {"error": str(e)}

    @staticmethod
    def get_client_by_id(client_id: int):
        """Get client object by ID"""
        try:
            if client_id == 0:
                return TgClient.bot
            if hasattr(TgClient, "helper_bots") and TgClient.helper_bots:
                try:
                    return TgClient.helper_bots[client_id - 1]
                except IndexError:
                    return None
            return None
        except Exception as e:
            LOGGER.error(f"Error getting client by ID: {e}")
            return None


# Compatibility alias for existing code
LoadBalancer = OptimizedLoadBalancer
