import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import settings
from app.core.logger import get_logger
from app.infrastructure.db.database import init_db
from app.presentation.webhooks.router import router as webhook_router


logger = get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting AI Orchestrator")
    from app.presentation.workers.broker import broker

    await broker.startup()
    await init_db()
    logger.info("Database initialized")

    if settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_OWNER_ID:
        from app.infrastructure.telegram.notifier import (
            setup_telegram_commands,
            get_telegram_dispatcher,
            get_telegram_bot,
        )

        await setup_telegram_commands()
        dp = get_telegram_dispatcher()
        bot = get_telegram_bot()

        asyncio.create_task(dp.start_polling(bot))
        logger.info("Telegram bot started")

    yield

    logger.info("Shutting down AI Orchestrator")
    await broker.shutdown()


app = FastAPI(
    title="AI Coding Agent Orchestrator",
    description="Asynchronous bridge between GitHub, Telegram, and a local coding agent server (OpenCode)",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(webhook_router)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
