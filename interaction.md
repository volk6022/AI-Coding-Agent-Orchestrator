# Interaction Flow

This document illustrates the complete interaction lifecycle between GitHub, the OpenCode Agent, and the Telegram Bot as managed by the AI Coding Agent Orchestrator.

## Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    
    actor User
    participant GH as GitHub (Repo)
    participant Web as FastAPI Server
    participant Worker as TaskIQ Worker
    participant Git as Local Git CLI
    participant OC as OpenCode Server
    participant TG as Telegram Bot
    
    %% Task Initialization
    User->>GH: Open new issue
    GH->>Web: Webhook POST (Issue Created)
    Web->>Worker: Queue execute_task job
    Worker->>TG: (Optional) Notify task started
    
    %% Environment Setup
    Worker->>Git: Clone repository into new workspace
    Worker->>Git: Create feature branch
    Worker->>OC: Spawn `opencode serve` process
    OC-->>Worker: Dynamically assigned port
    
    %% Session Initialization
    Worker->>OC: POST /session (Create session)
    OC-->>Worker: Return session_id
    Worker->>OC: POST /session/:id/prompt_async (Send Issue prompt)
    
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
    end
    
    Worker->>OC: Kill OpenCode Server process
    Worker->>Git: Cleanup workspace directory
```

## Description of Key Steps

1. **GitHub Webhooks**: The system acts on two primary webhook events: `issues` (opened) and `issue_comment` (created).
2. **Asynchronous Processing**: The FastAPI server immediately acknowledges the webhook to GitHub and delegates the heavy lifting to TaskIQ workers.
3. **Isolated Workspaces**: Each task executes in a fresh `git clone` to guarantee that the `opencode` instance does not conflict with concurrent tasks or previous state.
4. **OpenCode Integration**: The worker interacts with the local `opencode` server exclusively via its exposed REST API (`/session`, `/session/:id/prompt_async`) and listens to the Server-Sent Events (`/event`) stream to parse the agent's response incrementally (`message.part.updated`).
5. **Interactive Loop**: The TUI-less agent session allows for a back-and-forth conversation. If the agent requires human clarification, its text is forwarded to GitHub as a comment. When the user replies, it's sent right back into the active agent session.
6. **Completion**: A successful run is explicitly signaled by the agent outputting `[TASK_COMPLETED]`. The system automatically wraps the changes up into a commit and opens a pull request.
7. **Telegram Control**: Throughout this lifecycle, the Telegram Bot serves as an active observer, providing real-time observability over timeouts, active process handling, user reply prompts, and final results.
