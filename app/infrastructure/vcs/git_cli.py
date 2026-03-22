import asyncio
import os
import shutil
from pathlib import Path

from app.core.logger import get_logger
from app.domain.interfaces import ILocalGitClient

logger = get_logger(component="git_cli")


class GitCLIClient(ILocalGitClient):
    async def clone(self, repo_url: str, workspace_path: str) -> None:
        logger.info("cloning_repo", repo_url=repo_url, path=workspace_path)

        w_path = Path(workspace_path)
        parent_dir = w_path.parent
        parent_dir.mkdir(parents=True, exist_ok=True)

        if w_path.exists():
            logger.warning("workspace_already_exists_cleaning", path=workspace_path)
            await self.cleanup_workspace(workspace_path)

        env = os.environ.copy()
        if repo_url.startswith("git@"):
            env["GIT_SSH_COMMAND"] = "ssh -o StrictHostKeyChecking=no"

        process = await asyncio.create_subprocess_exec(
            "git",
            "clone",
            repo_url,
            workspace_path,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            logger.error("git_clone_failed", stderr=stderr.decode(), repo_url=repo_url)
            raise RuntimeError(f"git clone failed: {stderr.decode()}")

        logger.info("repo_cloned", repo_url=repo_url)

    async def create_branch(self, workspace_path: str, branch_name: str) -> None:
        logger.info("creating_branch", workspace_path=workspace_path, branch=branch_name)

        env = os.environ.copy()
        # Note: Branch operations don't usually need SSH unless they touch the remote
        # but we'll keep it safe.

        process = await asyncio.create_subprocess_exec(
            "git",
            "checkout",
            "-b",
            branch_name,
            cwd=workspace_path,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            logger.error("git_branch_failed", stderr=stderr.decode(), branch=branch_name)
            raise RuntimeError(f"git checkout -b failed: {stderr.decode()}")

        logger.info("branch_created", branch=branch_name)

    async def commit_and_push(
        self, workspace_path: str, commit_message: str, branch_name: str
    ) -> None:
        logger.info("commit_and_push", workspace_path=workspace_path, branch=branch_name)

        env = os.environ.copy()
        # Check if origin uses SSH
        # We can just check the repo_url pattern or just always set it if needed.
        # Actually, if the clone was HTTPS with token, push will just work.

        # We'll try to find out the current remote URL to decide
        process_remote = await asyncio.create_subprocess_exec(
            "git",
            "remote",
            "get-url",
            "origin",
            cwd=workspace_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_remote, _ = await process_remote.communicate()
        remote_url = stdout_remote.decode().strip()

        if remote_url.startswith("git@"):
            env["GIT_SSH_COMMAND"] = "ssh -o StrictHostKeyChecking=no"

        commands = [
            ("git", ["add", "-A"]),
            ("git", ["commit", "-m", commit_message]),
            ("git", ["push", "-u", "origin", branch_name]),
        ]

        for cmd, args in commands:
            process = await asyncio.create_subprocess_exec(
                cmd,
                *args,
                cwd=workspace_path,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                logger.error("git_command_failed", cmd=cmd, args=args, stderr=stderr.decode())
                raise RuntimeError(f"git {cmd} failed: {stderr.decode()}")

        logger.info("pushed_successfully", branch=branch_name)

    async def cleanup_workspace(self, workspace_path: str) -> None:
        logger.info("cleanup_workspace", path=workspace_path)

        def onerror(func, path, exc_info):
            import stat

            if not os.access(path, os.W_OK):
                os.chmod(path, stat.S_IWUSR)
                func(path)
            else:
                raise

        path = Path(workspace_path)
        if path.exists():
            # Try a few times on Windows as files might be locked briefly
            for i in range(3):
                try:
                    shutil.rmtree(workspace_path, onerror=onerror)
                    logger.info("workspace_cleaned", path=workspace_path)
                    return
                except Exception as e:
                    if i == 2:
                        logger.error(
                            "failed_to_cleanup_workspace", path=workspace_path, error=str(e)
                        )
                    else:
                        await asyncio.sleep(1)
