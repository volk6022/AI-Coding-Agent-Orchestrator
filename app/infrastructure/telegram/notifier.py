from typing import Optional

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.core.config import settings
from app.core.logger import get_logger
from app.domain.interfaces import ITelegramNotifier

logger = get_logger(component="telegram")


class TelegramNotifier(ITelegramNotifier):
    def __init__(self):
        self._bot: Optional[Bot] = None
        self._owner_id = settings.TELEGRAM_OWNER_ID

    @property
    def bot(self) -> Bot:
        if self._bot is None:
            self._bot = Bot(
                token=settings.TELEGRAM_BOT_TOKEN,
                default=DefaultBotProperties(parse_mode=ParseMode.HTML),
            )
        return self._bot

    async def send_message(self, text: str) -> None:
        if not self._owner_id:
            logger.warning("telegram_owner_id_not_set")
            return

        logger.info("sending_telegram_message", owner_id=self._owner_id)

        try:
            await self.bot.send_message(chat_id=self._owner_id, text=text)
            logger.info("telegram_message_sent")
        except Exception as e:
            logger.error("telegram_send_failed", error=str(e))

    async def close(self) -> None:
        if self._bot:
            await self._bot.session.close()
