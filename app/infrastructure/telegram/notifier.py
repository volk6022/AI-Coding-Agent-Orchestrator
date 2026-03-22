import asyncio
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message

from app.core.config import settings
from app.core.logger import get_logger
from app.domain.entities import TaskStatus
from app.domain.interfaces import ITelegramNotifier

logger = get_logger(component="telegram")

_telegram_bot: Optional[Bot] = None
_telegram_dp: Optional[Dispatcher] = None


def get_telegram_bot() -> Bot:
    global _telegram_bot
    if _telegram_bot is None:
        _telegram_bot = Bot(
            token=settings.TELEGRAM_BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
    return _telegram_bot


def get_telegram_dispatcher() -> Dispatcher:
    global _telegram_dp
    if _telegram_dp is None:
        _telegram_dp = Dispatcher()
    return _telegram_dp


async def setup_telegram_commands():
    bot = get_telegram_bot()
    dp = get_telegram_dispatcher()

    @dp.message(Command("start"))
    async def cmd_start(message: Message):
        if message.from_user.id != settings.TELEGRAM_OWNER_ID:
            await message.answer("Unauthorized")
            return
        await message.answer(
            "AI Orchestrator Bot\n\n"
            "Commands:\n"
            "/start - Show this message\n"
            "/status - Show bot status\n"
            "/list - List active tasks\n"
            "/cancel &lt;issue_number&gt; - Cancel a task"
        )

    @dp.message(Command("status"))
    async def cmd_status(message: Message):
        if message.from_user.id != settings.TELEGRAM_OWNER_ID:
            await message.answer("Unauthorized")
            return

        from app.presentation.workers.broker import broker

        await message.answer(
            f"Bot Status:\n"
            f"- Redis: {settings.REDIS_URL}\n"
            f"- Max Instances: {settings.MAX_CONCURRENT_INSTANCES}\n"
            f"- Idle Timeout: {settings.IDLE_TIMEOUT}s"
        )

    @dp.message(Command("list"))
    async def cmd_list(message: Message):
        if message.from_user.id != settings.TELEGRAM_OWNER_ID:
            await message.answer("Unauthorized")
            return

        from app.infrastructure.db.repository import StateRepository
        from app.infrastructure.db.database import async_session_maker
        from sqlalchemy import select
        from app.infrastructure.db.database import TaskStateModel

        async with async_session_maker() as session:
            stmt = select(TaskStateModel)
            result = await session.execute(stmt)
            tasks = result.scalars().all()

        if not tasks:
            await message.answer("No active tasks")
            return

        task_list = []
        for task in tasks:
            status_emoji = {
                TaskStatus.PENDING: "⏳",
                TaskStatus.RUNNING: "🔄",
                TaskStatus.WAITING_REPLY: "❓",
                TaskStatus.DONE: "✅",
                TaskStatus.FAILED: "❌",
                TaskStatus.ABORTED: "🛑",
            }.get(task.status, "❓")

            task_list.append(
                f"{status_emoji} Issue #{task.issue_number}: {task.status.value} "
                f"(port: {task.active_port or 'N/A'})"
            )

        await message.answer("\n".join(task_list))

    @dp.message(Command("cancel"))
    async def cmd_cancel(message: Message):
        if message.from_user.id != settings.TELEGRAM_OWNER_ID:
            await message.answer("Unauthorized")
            return

        parts = message.text.split()
        if len(parts) < 2:
            await message.answer("Usage: /cancel &lt;issue_number&gt;")
            return

        try:
            issue_number = int(parts[1])
        except ValueError:
            await message.answer("Invalid issue number")
            return

        from app.infrastructure.db.repository import StateRepository
        from app.infrastructure.db.database import async_session_maker
        from sqlalchemy import select
        from app.infrastructure.db.database import TaskStateModel

        async with async_session_maker() as session:
            stmt = select(TaskStateModel).where(TaskStateModel.issue_number == issue_number)
            result = await session.execute(stmt)
            task = result.scalar_one_or_none()

        if not task:
            await message.answer(f"No task found for issue #{issue_number}")
            return

        task.status = TaskStatus.ABORTED
        async with async_session_maker() as session:
            session.add(task)
            await session.commit()

        await message.answer(f"Task #{issue_number} marked as aborted")

    logger.info("telegram_commands_setupped")


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
            # We use parse_mode=None here to treat the message as plain text and avoid HTML parsing errors
            await self.bot.send_message(chat_id=self._owner_id, text=text, parse_mode=None)
            logger.info("telegram_message_sent")
        except Exception as e:
            logger.error("telegram_send_failed", error=str(e))

    async def close(self) -> None:
        if self._bot:
            await self._bot.session.close()
            self._bot = None
