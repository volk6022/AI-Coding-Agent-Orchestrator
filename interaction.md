# Interaction Flow

This document illustrates the complete interaction lifecycle between GitHub, the OpenCode Agent, and the Telegram Bot as managed by the AI Coding Agent Orchestrator.

## Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    
    actor User
    participant GH as GitHub (Repo A/B)
    participant Web as FastAPI Server
    participant Worker as TaskIQ Worker
    participant Git as Local Git CLI
    participant OC as OpenCode Server
    participant TG as Telegram Bot
    
    %% Task Initialization
    User->>GH: Open new issue
    GH->>Web: Webhook POST (Issue Created)
    Note over Web: Signature verified via<br/>multi-secret GITHUB_WEBHOOK_SECRET
    Web->>Worker: Queue execute_task job
    Worker->>TG: Task Pending: Issue #N (Repo X)
    
    %% HITL Approval
    TG-->>User: Request manual approval to start session
    User->>TG: /approve (or interactive button)
    Note over Worker: Session parameters can be<br/>modified/appended here
    
    %% Environment Setup
    Worker->>Git: Clone repository into isolated workspace
    Worker->>Git: Create feature branch
    Worker->>OC: Spawn `opencode serve` process
    OC-->>Worker: Dynamically assigned port
    
    %% Session Initialization
    Worker->>OC: POST /session (Create session)
    OC-->>Worker: Return session_id
    Worker->>OC: POST /session/:id/prompt_async (Send User-Modified Prompt)
    
    %% SSE Event Loop
    loop Event Stream (SSE)
        OC-->>Worker: GET /event (Stream connection)
        OC-->>Worker: data: {"type": "message.updated", ...}
        
        %% Accumulating Assistant text parts
        OC-->>Worker: data: {"type": "message.part.updated", "text": "..."}
        
        %% Turn completion logic
        OC-->>Worker: data: {"type": "session.idle"}
        
        alt Agent finished the task [TASK_COMPLETED]
            Worker->>Git: Commit workspace changes
            Worker->>Git: Push feature branch to remote
            Worker->>GH: Create Pull Request
            Worker->>TG: Send Success Notification with PR link
            
        else Agent asks a question (no completion flag)
            Worker->>GH: Post agent's question as Issue comment
            Worker->>TG: Send Notification (Waiting for User Reply)
            
            %% Reply logic
            User->>GH: Reply to the agent's comment
            GH->>Web: Webhook POST (Issue Commented)
            Web->>Worker: Queue handle_reply job
            Worker->>OC: POST /session/:id/prompt_async (Send User Reply)
            Worker->>TG: Notification (User replied, resuming...)
        end
    end
    
    %% Error Handling & Cleanup
    alt Error or Idle Timeout
        OC-->>Worker: data: {"type": "session.error", ...}
        Worker->>TG: Send Error Alert / Timeout Warning
        Worker->>GH: Post Error / Timeout comment on Issue
        
        %% Admin recovery
        User->>TG: /retry <issue> <repo>
        Note over Worker: Restarts the process flow
    end
    
    Worker->>OC: Kill OpenCode Server process
    Worker->>Git: Cleanup workspace directory
```

## Description of Key Steps

1. **GitHub Webhooks (Multi-Repo)**: The system supports an arbitrary number of repositories. Webhooks are verified using a comma-separated list of secrets in `GITHUB_WEBHOOK_SECRET`. Tasks are identified by a composite key of `issue_number` and `repo_url`.
2. **Asynchronous Processing**: The FastAPI server immediately acknowledges the webhook to GitHub and delegates task management to TaskIQ workers.
3. **Human-in-the-Loop (HITL)**: Agent sessions do not start automatically. The user must approve the task via Telegram. During this stage, the user can modify the request, append specific files to the prompt, or dictate which commands the agent should use.
4. **Isolated Workspaces**: Each task executes in a fresh `git clone` with a dedicated `opencode` instance on a dynamically assigned port to prevent cross-task contamination.
5. **OpenCode Integration**: The worker interacts with the local `opencode` server via its REST API (`/session`, `/session/:id/prompt_async`) and monitors progress via the Server-Sent Events (`/event`) stream.
6. **Interactive Feedback**: If the agent requires human clarification, its response is accumulated from `message.part.updated` events and posted to GitHub. Human replies are injected back into the active agent session.
7. **Persistence & Observability**: All task states are stored in a database. Users can monitor active tasks via `/list`, view logs via `/logs`, and recover from failures using `/retry` or `/cancel`.
8. **Completion**: Upon detecting the `[TASK_COMPLETED]` marker, the orchestrator automatically commits the changes, pushes the branch, and creates a Pull Request on the target repository.
