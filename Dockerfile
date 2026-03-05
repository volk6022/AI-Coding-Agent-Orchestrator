# Multi-stage Dockerfile for AI Orchestrator

# Stage 1: Dependencies
FROM python:3.12-slim as dependencies

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    openssh-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Copy dependency files
COPY pyproject.toml .

# Install Python dependencies
RUN uv pip install --system --no-cache-dir -r pyproject.toml

# Stage 2: Runtime
FROM python:3.12-slim as runtime

# Install runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    openssh-client \
    ssh-agent \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash orchestrator

# Copy installed packages from dependencies stage
COPY --from=dependencies /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=dependencies /usr/local/bin /usr/local/bin

WORKDIR /app

# Copy application code
COPY --chown=orchestrator:orchestrator . .

# Create workspace directory
RUN mkdir -p /tmp/workspaces && chown orchestrator:orchestrator /tmp/workspaces

# Switch to non-root user
USER orchestrator

# Expose FastAPI port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command (can be overridden by docker-compose)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
