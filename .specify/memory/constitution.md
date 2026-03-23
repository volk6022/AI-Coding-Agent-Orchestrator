<!--
<sync_impact_report>
- Version change: 1.1.0 → 1.2.0
- List of modified principles:
  - Added PRINCIPLE_7: Multi-Repository & Multi-Tenant Support
  - Updated Security & Configuration Requirements
- Added sections: None
- Removed sections: None
- Templates requiring updates:
  - .specify/templates/plan-template.md: ✅ updated (N/A)
  - .specify/templates/spec-template.md: ✅ updated (N/A)
  - .specify/templates/tasks-template.md: ✅ updated (N/A)
- Follow-up TODOs: None
</sync_impact_report>
-->

# AI Coding Agent Orchestrator Constitution

## Core Principles

### I. Clean Architecture & Modular Design
The project strictly follows Clean Architecture with distinct layers (Domain, Application, Infrastructure, Presentation). Dependencies must point inwards towards the Domain. Components (Git, GitHub, OpenCode, Telegram) must be abstracted via interfaces in the Domain layer to ensure loose coupling and testability via mocks.

### II. Environment Isolation & Safety
Every agent task MUST run in its own isolated workspace (fresh `git clone`). OpenCode instances must be isolated via dynamic port assignment. Temporary workspaces must be explicitly cleaned up on task completion or failure using robust mechanisms (e.g., `AsyncExitStack`) to prevent resource leaks and code contamination.

### III. Asynchronous & Non-Blocking Workflow (NON-NEGOTIABLE)
All external I/O (GitHub API, Telegram Bot, OpenCode Server) MUST be asynchronous using `asyncio` and `httpx`. Long-running tasks, such as agent sessions, must be handled by background workers (TaskIQ) with proper semaphore-based concurrency control to prevent system overload and ensure responsiveness.

### IV. Integration-First Testing Discipline
Core business logic and external protocol interactions MUST be covered by integration tests. Mock-based E2E tests are required for internal orchestration logic, while real-service integration tests (e.g., `test_opencode_real.py`) are mandatory for verifying compatibility with the OpenCode SSE/REST protocol.

### V. Real-Time Observability & Feedback
The system must provide real-time observability via structured logging and automated notifications. Every significant state change (task start, agent question, PR creation, error, timeout) MUST be reported to the owner via Telegram and logged with relevant context for debugging.

### VI. Human-in-the-Loop Orchestration (Management & Approval)
Agent sessions MUST NOT start autonomously; they require explicit manual approval from the user via the Telegram bot. The bot acts as the primary management interface, allowing the user to intercept, modify, append instructions, and specify target files before forwarding the prompt to the OpenCode server. While the bot handles interactive management, the GitHub server remains the ultimate source of truth, and all change histories must be preserved there. The system must also expose administrative commands via the bot (e.g., `/logs <issue_number>` and `/retry <issue_number>`) for ongoing task observability and recovery.

### VII. Multi-Repository & Multi-Tenant Support
The Orchestrator MUST be designed to handle an arbitrary number of connected repositories simultaneously, rather than being hardcoded or configured for a single project. The system must process webhooks from multiple repositories (or organizational webhooks), correctly attribute tasks to their source repository, and execute them in fully isolated workspaces, ensuring cross-repository boundaries are strictly maintained.

## Security & Configuration Requirements

- GitHub Webhook signatures MUST be securely verified (supporting single or multiple secrets depending on configuration/deployment).
- Telegram interactive commands MUST be restricted to the authenticated `TELEGRAM_OWNER_ID`.
- Sensitive information (API tokens, secrets, credentials) MUST NOT be committed to the repository, logged in plain text, or exposed in error messages.
- Configuration must be managed centrally via `app/core/config.py` using Pydantic Settings, with `.env` as the local override.

## Operational Standards

- **Language**: Python 3.12+ with strict typing and adherence to PEP 8.
- **Dependency Management**: `uv` is the mandatory tool for environment synchronization and package management.
- **Versioning**: Follow Semantic Versioning (SemVer) for the application and internal APIs.
- **Error Handling**: Implement "Fail Fast" with graceful degradation where possible. Ensure all failures result in a clean state and user notification.

## Governance

- This Constitution is the supreme governance document for the AI Coding Agent Orchestrator project and supersedes all other local development practices.
- Amendments to this Constitution require a Sync Impact Report, a version bump, and documentation of the rationale.
- Versioning Policy:
    - MAJOR: Backward incompatible governance changes or removal of core principles.
    - MINOR: New principles or significant section additions.
    - PATCH: Clarifications, wording improvements, and non-semantic refinements.
- Every Pull Request and feature implementation plan must include a "Constitution Check" to verify compliance.

**Version**: 1.2.0 | **Ratified**: 2026-03-23 | **Last Amended**: 2026-03-23
