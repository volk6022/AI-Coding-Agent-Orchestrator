from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import TaskState, TaskStatus
from app.domain.interfaces import IStateRepository
from app.infrastructure.db.database import TaskStateModel, async_session_maker


class StateRepository(IStateRepository):
    async def set_active_instance(
        self,
        issue_number: int,
        port: Optional[int],
        session_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> None:
        async with async_session_maker() as session:
            stmt = select(TaskStateModel).where(TaskStateModel.issue_number == issue_number)
            result = await session.execute(stmt)
            task = result.scalar_one_or_none()

            if task:
                task.active_port = port
                if session_id:
                    task.session_id = session_id
                if status:
                    task.status = TaskStatus(status)
                await session.commit()

    async def get_task_state(self, issue_number: int) -> Optional[TaskState]:
        async with async_session_maker() as session:
            stmt = select(TaskStateModel).where(TaskStateModel.issue_number == issue_number)
            result = await session.execute(stmt)
            task = result.scalar_one_or_none()

            if task:
                return TaskState(
                    issue_number=task.issue_number,
                    repo_url=task.repo_url,
                    branch_name=task.branch_name,
                    status=task.status,
                    active_port=task.active_port,
                    session_id=task.session_id,
                    workspace_path=task.workspace_path,
                )
            return None

    async def create_task(self, task_state: TaskState) -> None:
        async with async_session_maker() as session:
            stmt = select(TaskStateModel).where(
                TaskStateModel.issue_number == task_state.issue_number
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                existing.repo_url = task_state.repo_url
                existing.branch_name = task_state.branch_name
                existing.status = task_state.status
                existing.active_port = task_state.active_port
                existing.session_id = task_state.session_id
                existing.workspace_path = task_state.workspace_path
            else:
                task = TaskStateModel(
                    issue_number=task_state.issue_number,
                    repo_url=task_state.repo_url,
                    branch_name=task_state.branch_name,
                    status=task_state.status,
                    active_port=task_state.active_port,
                    session_id=task_state.session_id,
                    workspace_path=task_state.workspace_path,
                )
                session.add(task)
            await session.commit()
