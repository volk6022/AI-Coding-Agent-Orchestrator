import json
from collections.abc import AsyncGenerator
from typing import Any, Dict, Optional

import httpx

from app.core.logger import get_logger
from app.domain.interfaces import IOpenCodeClient

logger = get_logger(component="opencode_client")


class OpenCodeClient(IOpenCodeClient):
    def __init__(self, host: str, port: int):
        self.base_url = f"http://{host}:{port}"
        self._client = httpx.AsyncClient(timeout=30.0)
        self._session_id: Optional[str] = None

    async def create_session(self, name: str) -> str:
        logger.info("creating_session", name=name, base_url=self.base_url)

        response = await self._client.post(
            f"{self.base_url}/session",
            json={"name": name},
        )
        response.raise_for_status()

        data = response.json()
        self._session_id = data.get("session_id")

        if not self._session_id:
            raise RuntimeError("Failed to get session_id from OpenCode server")

        logger.info("session_created", session_id=self._session_id)
        return self._session_id

    async def send_message(self, session_id: str, message: str) -> None:
        logger.info("sending_message", session_id=session_id)

        response = await self._client.post(
            f"{self.base_url}/session/{session_id}/message",
            json={"message": {"role": "user", "content": message}},
        )
        response.raise_for_status()

    async def send_reply(self, session_id: str, message: str) -> None:
        logger.info("sending_reply", session_id=session_id)

        response = await self._client.post(
            f"{self.base_url}/session/{session_id}/message",
            json={"message": {"role": "user", "content": message}},
        )
        response.raise_for_status()

    async def listen_events(self, session_id: str) -> AsyncGenerator[Dict[str, Any], None]:  # type: ignore[override]
        logger.info("listening_events", session_id=session_id)

        async with self._client.stream(
            "GET", f"{self.base_url}/session/{session_id}/events"
        ) as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = line[6:]
                    try:
                        event = json.loads(data)
                        yield event
                    except Exception as e:
                        logger.warning("failed_to_parse_event", error=str(e), data=data)

    async def close(self) -> None:
        await self._client.aclose()
