# AI Coding Agent Orchestrator
An asynchronous Python service that acts as a bridge between GitHub, Telegram, and isolated instances of the OpenCode agent.

## What This Agent Does

This AI Coding Agent Orchestrator automates software development tasks by connecting GitHub issues with AI-powered coding assistance. Here's what it does:

### Core Functionality
- **Monitors GitHub Repositories:** Automatically detects new issues opened in connected repositories
- **Spawns Isolated AI Environments:** For each issue, creates a dedicated OpenCode instance in a clean repository clone
- **Processes Development Tasks:** Guides the AI agent to implement solutions based on issue requirements
- **Manages Code Changes:** Commits and pushes implemented changes to feature branches
- **Creates Pull Requests:** Automatically generates PRs when tasks are completed
- **Facilitates Communication:** Enables two-way communication between humans and AI agents

### Technical Implementation
- Runs OpenCode instances in isolated environments to prevent conflicts between concurrent tasks
- Maintains separate Git workspaces for each issue to avoid code contamination
- Provides real-time monitoring and control through Telegram notifications
- Implements resource management with concurrency limits and idle timeouts

## How Users Interact With the Agent

### Automated Workflow (GitHub Issues)
1. **Issue Creation:** User opens a GitHub issue describing a task/bug/feature
2. **Agent Detection:** The orchestrator detects the new issue via webhooks
3. **Environment Setup:** A dedicated OpenCode instance is spawned with a clean clone of the repository
4. **Task Processing:** The AI agent works on implementing the requested changes
5. **Progress Updates:** Users receive Telegram notifications about task progress
6. **Solution Submission:** When complete, the agent creates a pull request with the solution

### Interactive Communication (GitHub Comments)
When the AI agent needs clarification or encounters questions during development:
1. **Agent Inquiry:** The AI posts a comment on the GitHub issue asking for clarification
2. **User Response:** The repository owner responds to the AI's question in the issue comments
3. **Agent Continues:** The orchestrator forwards the response to the AI agent, which continues working
4. **Notification:** Users receive a Telegram notification confirming the reply was sent

### Telegram Control Interface
The orchestrator provides a Telegram bot for real-time monitoring and control:

#### Available Commands:
- `/start` - Displays available commands and bot information
- `/status` - Shows orchestrator status including resource usage and configuration
- `/list` - Lists all active tasks with their current status
- `/cancel <issue_number>` - Cancels a specific running task

#### Notifications:
- Task started notifications
- Task waiting for reply notifications  
- Task completion and PR creation notifications
- Error and timeout alerts

### Example Interaction Flow
1. User creates a GitHub issue: "Fix the login form validation error"
2. Agent spawns isolated environment and begins working
3. Agent analyzes code and starts implementing fixes
4. If agent needs clarification, it posts: "@owner Could you provide the expected validation rules?"
5. User responds to the comment with specific requirements
6. Agent continues implementation based on user's guidance
7. Once fixed, agent commits changes and creates a PR titled "Fix login form validation error"

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

#### Required Environment Variables:
- `GITHUB_WEBHOOK_SECRET` - GitHub webhook secret for authentication
- `GITHUB_TOKEN` - Personal access token for GitHub API access  
- `TELEGRAM_BOT_TOKEN` - Telegram bot token (optional, for notifications)
- `TELEGRAM_OWNER_ID` - Telegram user ID for receiving notifications (optional)
- `REDIS_URL` - Redis connection URL (default: redis://localhost:6379)
- `MAX_CONCURRENT_INSTANCES` - Maximum number of simultaneous agent instances (default: 3)
- `IDLE_TIMEOUT` - Time (in seconds) before abandoning idle tasks (default: 43200 = 12 hours)

#### Setting Up GitHub Integration:
1. Create a GitHub personal access token with repository permissions
2. Configure the webhook in your GitHub repository pointing to `{your-domain}/webhook/github`
3. Set the webhook secret to match your `GITHUB_WEBHOOK_SECRET` environment variable

#### Setting Up Telegram Integration (Optional):
1. Create a Telegram bot using @BotFather
2. Get your chat ID using @userinfobot or similar
3. Add your bot token and chat ID to the environment variables

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

### 5. Connecting GitHub Repository
1. In your GitHub repository settings, go to Webhooks
2. Click "Add webhook"
3. Set Payload URL to: `https://{your-domain}/webhook/github`
4. Set Content type to: `application/json`
5. Set Secret to match your `GITHUB_WEBHOOK_SECRET`
6. Select individual events: Issues, Issue comments
7. Click "Add webhook"

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

## Extending the System

### Adding New Integrations
The modular architecture allows for easy addition of new integrations by implementing the interfaces defined in `app/domain/interfaces`.

### Custom Use Cases
New automation workflows can be added by creating new use cases in `app/application/use_cases` that follow the same patterns as existing use cases.

### Supported Platforms
Currently supports GitHub as the primary platform with plans to expand to other platforms like GitLab, Bitbucket, etc.
