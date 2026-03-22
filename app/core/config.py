from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    MAX_CONCURRENT_INSTANCES: int = 3
    IDLE_TIMEOUT: int = 12 * 3600

    DATABASE_URL: str = "sqlite+aiosqlite:///./orchestrator.db"

    GITHUB_WEBHOOK_SECRET: str = ""
    GITHUB_TOKEN: str = ""

    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_OWNER_ID: int = 0

    REDIS_URL: str = "redis://localhost:6379"

    GIT_TRANSPORT: str = "https"  # "https" or "ssh"

    OPENCODE_BASE_DIR: str = "/tmp/workspaces"
    OPENCODE_HOST: str = "127.0.0.1"
    OPENCODE_CLI_NAME: str = "opencode"


settings = Settings()
