from dataclasses import dataclass
from enum import Enum
from typing import Optional


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING_REPLY = "WAITING_REPLY"
    DONE = "DONE"
    FAILED = "FAILED"
    ABORTED = "ABORTED"


@dataclass
class TaskState:
    issue_number: int
    repo_url: str
    branch_name: str
    status: TaskStatus
    active_port: Optional[int] = None
    session_id: Optional[str] = None
    workspace_path: Optional[str] = None


@dataclass
class IssueData:
    issue_number: int
    repo_url: str
    title: str
    body: str
    sender: str
    owner: str


@dataclass
class OpenCodeProcess:
    pid: int
    port: int
