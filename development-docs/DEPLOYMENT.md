# Deployment Guide

This guide covers deployment options for the AI Orchestrator, from local development to production.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Local Development](#local-development)
- [Docker Deployment](#docker-deployment)
- [Production Deployment](#production-deployment)
- [Environment Configuration](#environment-configuration)
- [Monitoring & Health Checks](#monitoring--health-checks)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Software

- **Python 3.12+** or **Docker 20.10+**
- **uv** package manager (for local development)
- **Git** with SSH key configured
- **Redis** (included in Docker Compose)
- **PostgreSQL** (optional, SQLite for development)

### External Services

1. **GitHub**: Personal Access Token with `repo` scope
2. **Telegram**: Bot token from [@BotFather](https://t.me/BotFather)
3. **OpenCode**: Installed and accessible via CLI (`opencode serve`)

---

## Local Development

### 1. Clone and Setup

```bash
# Clone the repository
git clone <repository-url>
cd AI-Coding-Agent-Orchestrator

# Create virtual environment using uv
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
uv pip install -e .
```

### 2. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your credentials
# See Environment Configuration section below
```

### 3. Start Services

```bash
# Option A: Using Docker Compose (recommended)
docker-compose -f docker-compose.dev.yml --profile dev up

# Option B: Manual startup
# Terminal 1: Start Redis
redis-server

# Terminal 2: Start FastAPI app
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Terminal 3: Start Taskiq worker
taskiq worker app.presentation.workers.broker:broker --workers 2
```

### 4. Verify Installation

```bash
# Check health endpoint
curl http://localhost:8000/health

# Expected response: {"status": "healthy"}
```

---

## Docker Deployment

### Production Docker Compose

```bash
# 1. Set environment variables
export GITHUB_WEBHOOK_SECRET="your-secret"
export GITHUB_TOKEN="ghp_your-token"
export TELEGRAM_BOT_TOKEN="your-bot-token"
export TELEGRAM_OWNER_ID="your-user-id"

# 2. Start all services
docker-compose up -d

# 3. Check service status
docker-compose ps

# 4. View logs
docker-compose logs -f app
docker-compose logs -f worker
```

### Service Architecture

```
┌─────────────┐     ┌─────────────┐
│   FastAPI   │────▶│   Redis     │
│   (Port 8000)│    │  (Port 6379)│
└──────┬──────┘     └─────────────┘
       │
       ▼
┌─────────────┐     ┌─────────────┐
│  Taskiq     │────▶│  PostgreSQL │
│   Worker    │     │  (Port 5432)│
└─────────────┘     └─────────────┘
```

---

## Production Deployment

### Kubernetes Deployment (Example)

```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orchestrator-app
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orchestrator
  template:
    metadata:
      labels:
        app: orchestrator
    spec:
      containers:
      - name: app
        image: your-registry/orchestrator:latest
        ports:
        - containerPort: 8000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: orchestrator-secrets
              key: database-url
        # ... other environment variables
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 30
---
apiVersion: v1
kind: Service
metadata:
  name: orchestrator-service
spec:
  selector:
    app: orchestrator
  ports:
  - port: 80
    targetPort: 8000
  type: LoadBalancer
```

### Security Considerations

1. **SSH Keys**: Mount SSH key as secret
   ```yaml
   volumes:
   - name: ssh-key
     secret:
       secretName: github-ssh-key
       defaultMode: 0400
   ```

2. **Environment Secrets**: Use Kubernetes Secrets or AWS Secrets Manager
3. **Network Policies**: Restrict outbound access to GitHub API only
4. **Resource Limits**: Set CPU/memory limits for worker pods

---

## Environment Configuration

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `GITHUB_WEBHOOK_SECRET` | HMAC secret for webhook validation | `your-secret-key` |
| `GITHUB_TOKEN` | GitHub Personal Access Token | `ghp_xxx` |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot API token | `123456:ABC-DEF1234` |
| `TELEGRAM_OWNER_ID` | Your Telegram user ID | `123456789` |
| `REDIS_URL` | Redis connection string | `redis://localhost:6379` |
| `DATABASE_URL` | Database connection string | `sqlite+aiosqlite:///./orchestrator.db` |

### Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MAX_CONCURRENT_INSTANCES` | Max parallel OpenCode instances | `3` |
| `IDLE_TIMEOUT` | Timeout for idle sessions (seconds) | `43200` (12h) |
| `OPENCODE_BASE_DIR` | Base directory for workspaces | `/tmp/workspaces` |
| `OPENCODE_HOST` | Host for OpenCode server | `127.0.0.1` |

### Getting Your Telegram User ID

1. Start a chat with [@userinfobot](https://t.me/userinfobot)
2. Send any message
3. Copy the returned ID

---

## Monitoring & Health Checks

### Health Endpoints

```bash
# Basic health check
curl http://localhost:8000/health

# Response: {"status": "healthy"}
```

### Application Logs

```bash
# Docker logs
docker-compose logs -f app

# Structured logs (JSON format)
docker-compose logs app | jq '.message'
```

### Key Metrics to Monitor

1. **Active Tasks**: Check `/list` Telegram command
2. **Worker Status**: Monitor Taskiq worker logs
3. **Database Connections**: Check PostgreSQL/SQLite connection pool
4. **Redis Queue Depth**: `redis-cli LLEN taskiq:queue`

### Alerting

Configure Telegram alerts for:
- Task failures
- Idle timeouts
- Process crashes
- GitHub API rate limits

---

## Troubleshooting

### Common Issues

#### 1. Worker Not Processing Tasks

```bash
# Check Redis connection
redis-cli ping

# Check worker logs
docker-compose logs worker

# Restart worker
docker-compose restart worker
```

#### 2. Database Connection Errors

```bash
# For PostgreSQL
docker-compose exec postgres pg_isready

# For SQLite, check file permissions
ls -la orchestrator.db
```

#### 3. GitHub Webhook Not Triggering

```bash
# Verify webhook signature
# Check logs for "github_webhook_received"

# Test webhook manually
curl -X POST http://localhost:8000/webhook/github \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: issues" \
  -H "X-Hub-Signature-256: sha256=..." \
  -d '{"action": "opened", "issue": {"number": 1}}'
```

#### 4. OpenCode Server Not Starting

```bash
# Verify OpenCode installation
opencode --version

# Check if port is available
netstat -tlnp | grep 8765

# Review OpenCode logs
docker-compose logs app | grep opencode
```

#### 5. Git SSH Authentication Failed

```bash
# Test SSH connection
ssh -T git@github.com

# Verify SSH agent
ssh-add -l

# Add SSH key
ssh-add ~/.ssh/id_ed25519
```

### Debug Mode

Enable verbose logging:

```bash
# Set log level
export LOG_LEVEL=debug

# Or modify config.py
# Add: LOG_LEVEL: str = "debug"
```

---

## Backup & Recovery

### Database Backup

```bash
# SQLite backup
cp orchestrator.db orchestrator.db.backup

# PostgreSQL backup
docker-compose exec postgres pg_dump -U orchestrator orchestrator > backup.sql

# Restore
docker-compose exec -T postgres psql -U orchestrator orchestrator < backup.sql
```

### Workspace Cleanup

```bash
# Clean old workspaces
docker-compose exec app rm -rf /tmp/workspaces/issue_*

# Or use the cleanup endpoint (if implemented)
curl -X POST http://localhost:8000/admin/cleanup-workspaces
```

---

## Performance Tuning

### Recommended Settings

| Component | Setting | Value |
|-----------|---------|-------|
| Taskiq Workers | `--workers` | `3-5` |
| Max Concurrent Instances | `MAX_CONCURRENT_INSTANCES` | `3` |
| Redis Persistence | `appendonly` | `yes` |
| PostgreSQL Pool Size | `pool_size` | `10` |

### Scaling

For high-load scenarios:

1. **Horizontal Scaling**: Run multiple worker instances
2. **Redis Cluster**: Use Redis Cluster for distributed queue
3. **Database Read Replicas**: Offload read queries
4. **Load Balancer**: Distribute webhook traffic

---

## Update & Migration

### Updating the Application

```bash
# Pull latest changes
git pull origin main

# Rebuild Docker images
docker-compose build

# Restart services
docker-compose down
docker-compose up -d

# Run migrations (if any)
# (Currently no migrations needed - SQLAlchemy auto-creates tables)
```

### Version Compatibility

| Version | Python | OpenCode | Redis | PostgreSQL |
|---------|--------|----------|-------|------------|
| 0.1.x   | 3.12+  | Latest   | 7+    | 15+        |

---

## Support

For issues and questions:

1. Check existing issues on GitHub
2. Review logs for error messages
3. Test with health endpoints
4. Contact via Telegram bot `/start` command
