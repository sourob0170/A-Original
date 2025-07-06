from asyncio import Lock, gather

from pyrogram import Client, enums

from bot import LOGGER

from .config_manager import Config


class TgClient:
    _lock = Lock()
    _hlock = Lock()
    bot = None
    user = None
    helper_bots = {}
    helper_loads = {}
    NAME = ""
    ID = 0
    IS_PREMIUM_USER = False
    MAX_SPLIT_SIZE = 2097152000

    @classmethod
    async def start_bot(cls):
        LOGGER.info("Creating client from BOT_TOKEN")
        cls.ID = Config.BOT_TOKEN.split(":", 1)[0]
        cls.bot = Client(
            cls.ID,
            Config.TELEGRAM_API,
            Config.TELEGRAM_HASH,
            proxy=Config.TG_PROXY,
            bot_token=Config.BOT_TOKEN,
            workdir="/usr/src/app",
            parse_mode=enums.ParseMode.HTML,
            max_concurrent_transmissions=100,
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

    @classmethod
    async def start_user(cls):
        # Check if USER_SESSION_STRING is a valid string with content
        if (
            Config.USER_SESSION_STRING
            and isinstance(Config.USER_SESSION_STRING, str)
            and len(Config.USER_SESSION_STRING) > 0
        ):
            LOGGER.info("Creating client from USER_SESSION_STRING")
            try:
                cls.user = Client(
                    "user",
                    Config.TELEGRAM_API,
                    Config.TELEGRAM_HASH,
                    proxy=Config.TG_PROXY,
                    session_string=Config.USER_SESSION_STRING,
                    parse_mode=enums.ParseMode.HTML,
                    no_updates=True,
                    max_concurrent_transmissions=100,
                )
                await cls.user.start()
                cls.IS_PREMIUM_USER = cls.user.me.is_premium
                if cls.IS_PREMIUM_USER:
                    cls.MAX_SPLIT_SIZE = 4194304000
            except KeyError as e:
                if str(e) == "None":
                    LOGGER.error(
                        "Failed to connect to Telegram: DataCenter ID is None. This might be due to network issues or API configuration."
                    )
                    LOGGER.error(
                        "Please check your internet connection and TELEGRAM_API/TELEGRAM_HASH configuration."
                    )
                    cls.IS_PREMIUM_USER = False
                    cls.user = None
                else:
                    raise
            except Exception as e:
                LOGGER.error(f"Failed to start client from USER_SESSION_STRING. {e}")
                cls.IS_PREMIUM_USER = False
                cls.user = None
        elif Config.USER_SESSION_STRING and not isinstance(
            Config.USER_SESSION_STRING, str
        ):
            cls.IS_PREMIUM_USER = False
            cls.user = None

    @classmethod
    async def start_hclient(cls, no, b_token):
        try:
            hbot = Client(
                f"helper{no}",
                Config.TELEGRAM_API,
                Config.TELEGRAM_HASH,
                proxy=Config.TG_PROXY,
                bot_token=b_token,
                parse_mode=enums.ParseMode.HTML,
                no_updates=True,
                max_concurrent_transmissions=10,
            )
            await hbot.start()
            LOGGER.info(f"Helper Bot [@{hbot.me.username}] Started!")
            cls.helper_bots[no], cls.helper_loads[no] = hbot, 0
        except Exception as e:
            LOGGER.error(f"Failed to start helper bot {no} from HELPER_TOKENS. {e}")
            cls.helper_bots.pop(no, None)

    @classmethod
    async def start_helper_bots(cls):
        if not Config.HELPER_TOKENS:
            LOGGER.warning(
                "❌ No HELPER_TOKENS found, hyper download will not be available"
            )
            return
        async with cls._hlock:
            await gather(
                *(
                    cls.start_hclient(no, b_token)
                    for no, b_token in enumerate(
                        Config.HELPER_TOKENS.split(), start=1
                    )
                )
            )
        if cls.helper_bots:
            LOGGER.info(
                f"Started {len(cls.helper_bots)} helper bots for hyper download"
            )
        else:
            LOGGER.warning(
                "Failed to start any helper bots, hyper download will not be available"
            )

    @classmethod
    async def stop(cls):
        if cls.bot:
            await cls.bot.stop()
            cls.bot = None
            LOGGER.info("Bot client stopped.")

        if cls.user:
            await cls.user.stop()
            cls.user = None
            LOGGER.info("User client stopped.")

        if cls.helper_bots:
            await gather(*[h_bot.stop() for h_bot in cls.helper_bots.values()])
            cls.helper_bots = {}
            LOGGER.info("Helper bots stopped.")

        cls.IS_PREMIUM_USER = False
        cls.MAX_SPLIT_SIZE = 2097152000

    @classmethod
    async def reload(cls):
        async with cls._lock:
            await cls.bot.restart()
            if cls.user:
                await cls.user.restart()
            if cls.helper_bots:
                await gather(
                    *[h_bot.restart() for h_bot in cls.helper_bots.values()]
                )
            LOGGER.info("All clients restarted")

    @classmethod
    def are_helper_bots_available(cls):
        """Check if helper bots are available for hyper download"""
        return len(cls.helper_bots) > 0
