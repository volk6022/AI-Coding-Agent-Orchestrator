from app.core.logger import get_logger
from app.domain.entities import TaskStatus
from app.domain.interfaces import IOpenCodeProcessManager, IStateRepository, ITelegramNotifier

logger = get_logger(component="handle_reply")


async def handle_user_reply(
    issue_number: int,
    comment_body: str,
    oc_manager: IOpenCodeProcessManager,
    db: IStateRepository,
    telegram: ITelegramNotifier,
) -> None:
    task_state = await db.get_task_state(issue_number)

    if not task_state:
        logger.warning("no_active_task_for_issue", issue_number=issue_number)
        return

    if task_state.status not in (TaskStatus.RUNNING, TaskStatus.WAITING_REPLY):
        logger.warning(
            "task_not_awaiting_reply", issue_number=issue_number, status=task_state.status
        )
        return

    if not task_state.active_port or not task_state.session_id:
        logger.warning("no_active_session_for_issue", issue_number=issue_number)
        return

    await db.set_active_instance(
        issue_number,
        task_state.active_port,
        task_state.session_id,
        status="RUNNING",
    )

    oc_client = oc_manager.get_client(task_state.active_port)
    await oc_client.send_reply(task_state.session_id, comment_body)

    await telegram.send_message(f"Reply sent to Agent for Issue #{issue_number}")
