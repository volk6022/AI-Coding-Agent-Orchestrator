# AI Coding Agent Orchestrator

An asynchronous Python service that acts as a bridge between GitHub, Telegram, and isolated instances of the OpenCode agent.

## Features

- **Automated Response:** Reacts to new GitHub Issues.
- **Isolated Environments:** Every task runs in a clean `git clone` with its own `opencode` instance.
- **Two-Way Sync:** Syncs comments between GitHub Issues and the Agent's session.
- **Resource Management:** Concurrency limits and idle timeouts.
- **Telegram Control:** Monitoring and control via a Telegram bot.

## Quick Start

### 1. Prerequisites
- Python 3.12+
- `uv` (recommended) or `pip`
- `redis-server`
- `opencode` CLI (must be in PATH)

### 2. Configuration
Copy `.env.example` to `.env` and fill in your secrets.

```bash
cp .env.example .env
```

### 3. Running with Docker (Recommended)
```bash
docker build -t ai-orchestrator .
docker run -p 8000:8000 --env-file .env ai-orchestrator
```

### 4. Running Locally
```bash
# Install dependencies
uv sync

# Start redis
redis-server &

# Start the web server
uvicorn main:app --reload

# Start the task worker (in a separate terminal)
taskiq worker app.presentation.workers.broker:broker --workers 3
```

## E2E Testing
Run the provided mock tests:
```bash
pytest
```

## Project Structure
- `app/domain`: Core logic and interfaces (Clean Architecture).
- `app/application`: Use cases (the "orchestrator" loop).
- `app/infrastructure`: Concrete implementations (Git, GitHub, OpenCode, DB, Telegram).
- `app/presentation`: Webhooks and Task Workers.
- `main.py`: FastAPI application entry point.
