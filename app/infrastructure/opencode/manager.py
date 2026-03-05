from __future__ import annotations

import asyncio
import re
import json
from typing import Dict, Any, Optional

import httpx

from app.core.config import settings
from app.core.logger import get_logger
from app.domain.entities import OpenCodeProcess
from app.domain.interfaces import IOpenCodeClient, IOpenCodeProcessManager

logger = get_logger(component="opencode")


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

    async def listen_events(self) -> AsyncGenerator[Dict[str, Any], None]:  # type: ignore[override]
        logger.info("listening_events", session_id=self._session_id)

        async with self._client.stream(
            "GET", f"{self.base_url}/session/{self._session_id}/events"
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


class OpenCodeProcessManager(IOpenCodeProcessManager):
    def __init__(self):
        self._processes: Dict[int, OpenCodeProcess] = {}
        self._clients: Dict[int, OpenCodeClient] = {}

    async def spawn_server(self, workspace_path: str) -> OpenCodeProcess:
        logger.info("spawning_opencode_server", workspace_path=workspace_path)

        process = await asyncio.create_subprocess_exec(
            "opencode",
            "serve",
            "--port",
            "0",
            "--dir",
            workspace_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        port = await self._read_dynamic_port(process.stdout)

        oc_process = OpenCodeProcess(pid=process.pid, port=port)
        self._processes[process.pid] = oc_process
        self._clients[port] = OpenCodeClient(settings.OPENCODE_HOST, port)

        logger.info("opencode_server_started", pid=process.pid, port=port)
        return oc_process

    async def _read_dynamic_port(self, stdout: Optional[asyncio.StreamReader]) -> int:
        if not stdout:
            raise RuntimeError("OpenCode server failed to start - no stdout")

        while True:
            line = await stdout.readline()
            if not line:
                raise RuntimeError("OpenCode server failed to start - no output")

            decoded = line.decode()
            logger.debug("opencode_output", line=decoded)

            match = re.search(r"port[:\s]+(\d+)", decoded, re.IGNORECASE)
            if match:
                return int(match.group(1))

            if "error" in decoded.lower() or "failed" in decoded.lower():
                raise RuntimeError(f"OpenCode server failed to start: {decoded}")

    async def kill_server(self, pid: int) -> None:
        logger.info("killing_opencode_server", pid=pid)

        port_to_remove = None
        if pid in self._processes:
            port_to_remove = self._processes[pid].port
            del self._processes[pid]

        if port_to_remove and port_to_remove in self._clients:
            await self._clients[port_to_remove].close()
            del self._clients[port_to_remove]

        try:
            process = await asyncio.create_subprocess_exec(
                "taskkill",
                "/PID",
                str(pid),
                "/F",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await process.communicate()
        except Exception as e:
            logger.warning("failed_to_kill_process", pid=pid, error=str(e))

    def get_client(self, port: int) -> OpenCodeClient:
        if port not in self._clients:
            self._clients[port] = OpenCodeClient(settings.OPENCODE_HOST, port)
        return self._clients[port]
