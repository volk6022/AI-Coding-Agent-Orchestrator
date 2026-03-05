from __future__ import annotations

import asyncio
import re
from typing import Dict, Optional

from app.core.config import settings
from app.core.logger import get_logger
from app.domain.entities import OpenCodeProcess
from app.domain.interfaces import IOpenCodeProcessManager
from app.infrastructure.opencode.client import OpenCodeClient

logger = get_logger(component="opencode_manager")


class OpenCodeProcessManager(IOpenCodeProcessManager):
    def __init__(self) -> None:
        self._processes: Dict[int, OpenCodeProcess] = {}
        self._clients: Dict[int, OpenCodeClient] = {}

    async def spawn_server(self, workspace_path: str) -> OpenCodeProcess:
        logger.info("spawning_opencode_server", workspace_path=workspace_path)

        process = await asyncio.create_subprocess_exec(
            settings.OPENCODE_CLI_NAME,
            "serve",
            "--port",
            "0",
            "--dir",
            workspace_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            async with asyncio.timeout(30.0):
                port = await self._read_dynamic_port(process.stdout)
        except TimeoutError:
            try:
                # Cleanup the hanging process if it didn't start in time
                await self.kill_server(process.pid)
            except Exception:
                pass
            raise RuntimeError("OpenCode server failed to start - timeout waiting for port")

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
            # For Windows compatibility as per previous manager code
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
