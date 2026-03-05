from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import settings
from app.core.logger import get_logger
from app.infrastructure.db.database import init_db


logger = get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting AI Orchestrator")
    await init_db()
    logger.info("Database initialized")
    yield
    logger.info("Shutting down AI Orchestrator")


app = FastAPI(
    title="AI Coding Agent Orchestrator",
    description="Asynchronous bridge between GitHub, Telegram, and OpenCode",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
