from asyncio import Lock, gather

from pyrogram import Client, enums

from bot import LOGGER

from .config_manager import Config


class TgClient:
    _lock = Lock()
    _hlock = Lock()
    bot = None
    user = None
    helper_bots = {} # Will remain empty
    helper_loads = {} # Will remain empty
    NAME = ""
    ID = 0
    IS_PREMIUM_USER = False # Defaulting to False as user client is disabled
    MAX_SPLIT_SIZE = 2097152000 # Default non-premium split size

    @classmethod
    async def start_bot(cls):
        LOGGER.info("Creating client from BOT_TOKEN")
        cls.ID = Config.BOT_TOKEN.split(":", 1)[0]
        cls.bot = Client(
            name=":memory:", # Use in-memory session for testing this specific error
            api_id=Config.TELEGRAM_API,
            api_hash=Config.TELEGRAM_HASH,
            proxy=Config.TG_PROXY,
            bot_token=Config.BOT_TOKEN,
            # workdir="/usr/src/app", # Workdir might not be needed for in-memory
            parse_mode=enums.ParseMode.HTML,
            no_updates=False,  # Ensure updates are enabled
        )
        try:
            await cls.bot.start()
            cls.NAME = cls.bot.me.username
        except KeyError as e:
            if str(e) == "None":
                LOGGER.error(
                    "Failed to connect to Telegram: DataCenter ID is None. This might be due to network issues or API configuration."
                )
                LOGGER.error(
                    "Please check your internet connection and TELEGRAM_API/TELEGRAM_HASH configuration."
                )
                raise Exception(
                    "Failed to connect to Telegram servers. Check your internet connection and API configuration."
                ) from e
            raise

    # @classmethod
    # async def start_user(cls):
    #     # User client initialization logic is removed/commented out
    #     # USER_SESSION_STRING is no longer used to start a client here.
    #     # cls.IS_PREMIUM_USER will remain False as set by default.
    #     # cls.MAX_SPLIT_SIZE will remain 2097152000 as set by default.
    #     LOGGER.info("User client (USER_SESSION_STRING) initialization is disabled.")
    #     cls.user = None
    #     cls.IS_PREMIUM_USER = False


    # @classmethod
    # async def start_hclient(cls, no, b_token):
    #     # Helper bot client initialization logic is removed/commented out
    #     LOGGER.info(f"Helper bot {no} initialization is disabled.")


    # @classmethod
    # async def start_helper_bots(cls):
    #     # Helper bots initialization logic is removed/commented out
    #     # HELPER_TOKENS is no longer used here.
    #     LOGGER.info("Helper bots (HELPER_TOKENS) initialization is disabled.")
    #     cls.helper_bots = {} # Ensure it's empty

    @classmethod
    async def stop(cls):
        if cls.bot:
            await cls.bot.stop()
            cls.bot = None
            LOGGER.info("Bot client stopped.")

        if cls.user: # Check if user client was somehow initialized (should not happen)
            await cls.user.stop()
            cls.user = None
            LOGGER.info("User client stopped (unexpectedly).")

        if cls.helper_bots: # Check if helper_bots was somehow populated (should not happen)
            await gather(*[h_bot.stop() for h_bot in cls.helper_bots.values()])
            cls.helper_bots = {}
            LOGGER.info("Helper bots stopped (unexpectedly).")

        # These are already defaulted, but ensure they are reset if stop is called.
        cls.IS_PREMIUM_USER = False
        cls.MAX_SPLIT_SIZE = 2097152000

    @classmethod
    async def reload(cls):
        async with cls._lock:
            await cls.bot.restart()
            # User client and helper bots are disabled, so no need to restart them.
            # if cls.user:
            #     await cls.user.restart()
            # if cls.helper_bots:
            #     await gather(
            #         *[h_bot.restart() for h_bot in cls.helper_bots.values()]
            #     )
            LOGGER.info("Main bot client restarted. User/Helper clients are disabled.")

    @classmethod
    def are_helper_bots_available(cls):
        """Check if helper bots are available for hyper download"""
        return len(cls.helper_bots) > 0
