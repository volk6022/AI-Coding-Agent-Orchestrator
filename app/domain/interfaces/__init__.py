from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Dict, Any, Optional

from app.domain.entities import IssueData, OpenCodeProcess, TaskState


class ILocalGitClient(ABC):
    @abstractmethod
    async def clone(self, repo_url: str, workspace_path: str) -> None:
        pass

    @abstractmethod
    async def create_branch(self, workspace_path: str, branch_name: str) -> None:
        pass

    @abstractmethod
    async def commit_and_push(
        self, workspace_path: str, commit_message: str, branch_name: str
    ) -> None:
        pass

    @abstractmethod
    async def cleanup_workspace(self, workspace_path: str) -> None:
        pass


class IGitHubClient(ABC):
    @abstractmethod
    async def post_comment(self, issue_number: int, body: str, repo: str) -> None:
        pass

    @abstractmethod
    async def create_pull_request(
        self, issue_number: int, branch_name: str, repo: str, title: Optional[str] = None
    ) -> None:
        pass

    @abstractmethod
    async def get_issue(self, issue_number: int, repo: str) -> IssueData:
        pass

    @abstractmethod
    def get_clone_url(self, repo: str) -> str:
        pass

    @abstractmethod
    async def close(self) -> None:
        pass


class IOpenCodeProcessManager(ABC):
    @abstractmethod
    async def spawn_server(self, workspace_path: str) -> OpenCodeProcess:
        pass

    @abstractmethod
    async def kill_server(self, pid: int) -> None:
        pass

    @abstractmethod
    def get_client(self, port: int) -> "IOpenCodeClient":
        pass


class IOpenCodeClient(ABC):
    @abstractmethod
    async def create_session(self, name: str) -> str:
        pass

    @abstractmethod
    async def send_message(self, session_id: str, message: str) -> None:
        pass

    @abstractmethod
    async def send_reply(self, session_id: str, message: str) -> None:
        pass

    @abstractmethod
    def listen_events(self, session_id: str) -> AsyncGenerator[Dict[str, Any], None]:
        pass


class ITelegramNotifier(ABC):
    @abstractmethod
    async def send_message(self, text: str) -> None:
        pass

    @abstractmethod
    async def close(self) -> None:
        pass


class IStateRepository(ABC):
    @abstractmethod
    async def set_active_instance(
        self,
        issue_number: int,
        repo_url: str,
        port: Optional[int],
        session_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> None:
        pass

    @abstractmethod
    async def get_task_state(self, issue_number: int, repo_url: str) -> Optional[TaskState]:
        pass

    @abstractmethod
    async def create_task(self, task_state: TaskState) -> None:
        pass
