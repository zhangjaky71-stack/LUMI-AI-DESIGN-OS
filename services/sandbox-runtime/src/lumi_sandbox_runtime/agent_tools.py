from __future__ import annotations

from uuid import uuid4

from .models import SandboxAccessContext, SandboxCommand
from .service import SandboxRuntimeService


class SandboxToolset:
    """Capability-scoped tools exposed to an agent.

    This object never exposes subprocess, Docker, host paths, credentials, or a raw host shell.
    The agent can only invoke the already-authorized sandbox runtime service.
    """

    def __init__(
        self,
        runtime: SandboxRuntimeService,
        *,
        sandbox_id: str,
        context: SandboxAccessContext,
    ) -> None:
        self.runtime = runtime
        self.sandbox_id = sandbox_id
        self.context = context

    async def run_python(self, source: str, *, timeout_seconds: int | None = None) -> str:
        path = f"/workspace/work/agent-{uuid4().hex}.py"
        await self.runtime.write_file(
            self.sandbox_id,
            path,
            source.encode("utf-8"),
            context=self.context,
        )
        result = await self.runtime.exec(
            self.sandbox_id,
            SandboxCommand(
                argv=("python", path),
                timeout_seconds=timeout_seconds,
            ),
            context=self.context,
        )
        if result.exit_code != 0:
            raise RuntimeError(result.stderr or f"python exited {result.exit_code}")
        return result.stdout

    async def run_node(self, source: str, *, timeout_seconds: int | None = None) -> str:
        path = f"/workspace/work/agent-{uuid4().hex}.mjs"
        await self.runtime.write_file(
            self.sandbox_id,
            path,
            source.encode("utf-8"),
            context=self.context,
        )
        result = await self.runtime.exec(
            self.sandbox_id,
            SandboxCommand(
                argv=("node", path),
                timeout_seconds=timeout_seconds,
            ),
            context=self.context,
        )
        if result.exit_code != 0:
            raise RuntimeError(result.stderr or f"node exited {result.exit_code}")
        return result.stdout

    async def ffprobe(self, path: str) -> str:
        result = await self.runtime.exec(
            self.sandbox_id,
            SandboxCommand(
                argv=(
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_format",
                    "-show_streams",
                    path,
                )
            ),
            context=self.context,
        )
        if result.exit_code != 0:
            raise RuntimeError(result.stderr or f"ffprobe exited {result.exit_code}")
        return result.stdout

    async def image_convert(self, source: str, target: str, *args: str) -> None:
        result = await self.runtime.exec(
            self.sandbox_id,
            SandboxCommand(argv=("convert", source, *args, target)),
            context=self.context,
        )
        if result.exit_code != 0:
            raise RuntimeError(result.stderr or f"ImageMagick exited {result.exit_code}")

    async def read_file(self, path: str) -> bytes:
        return await self.runtime.read_file(self.sandbox_id, path, context=self.context)

    async def write_file(self, path: str, content: bytes) -> None:
        await self.runtime.write_file(
            self.sandbox_id, path, content, context=self.context
        )

    async def list_files(self, path: str):
        return await self.runtime.list_files(self.sandbox_id, path, context=self.context)

    async def collect_output(self, path: str):
        return await self.runtime.collect_artifact(
            self.sandbox_id, path, context=self.context
        )
