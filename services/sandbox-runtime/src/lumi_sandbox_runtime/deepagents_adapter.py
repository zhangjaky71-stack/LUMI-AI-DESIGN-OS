from __future__ import annotations

import asyncio
import base64
import fnmatch
import inspect
import shlex
import threading
from collections.abc import Coroutine
from typing import Any, TypeVar

from deepagents.backends.protocol import (
    EditResult,
    ExecuteResponse,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GlobResult,
    GrepMatch,
    GrepResult,
    LsResult,
    ReadResult,
    SandboxBackendProtocol,
    WriteResult,
)

from .audit import AuditSink, MemoryAuditSink
from .backend import ArtifactStoragePort
from .docker_backend import DockerSandboxBackend
from .models import SandboxAccessContext, SandboxCommand, SandboxSpec
from .service import SandboxRuntimeService

T = TypeVar("T")
_SHELL_OPERATORS = {"|", "||", "&", "&&", ";", ">", ">>", "<", "<<", "(", ")"}
_WORKSPACE_ROOTS = {
    "/workspace/input",
    "/workspace/work",
    "/workspace/output",
}


class DeepAgentsCommandRejected(ValueError):
    code = "DEEPAGENTS_SANDBOX_COMMAND_REJECTED"


class _LoopBridge:
    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(
            target=self._run,
            name="lumi-sandbox-loop",
            daemon=True,
        )
        self.thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def submit(self, coroutine: Coroutine[Any, Any, T]):
        return asyncio.run_coroutine_threadsafe(coroutine, self.loop)

    def run(self, coroutine: Coroutine[Any, Any, T]) -> T:
        return self.submit(coroutine).result()

    async def arun(self, coroutine: Coroutine[Any, Any, T]) -> T:
        return await asyncio.wrap_future(self.submit(coroutine))

    def close(self) -> None:
        if self.loop.is_closed():
            return
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=5)
        self.loop.close()


def parse_deepagents_command(command: str) -> tuple[str, ...]:
    if not command.strip() or "\x00" in command:
        raise DeepAgentsCommandRejected("command is empty or contains NUL")
    lexer = shlex.shlex(command, posix=True, punctuation_chars="|&;><()")
    lexer.whitespace_split = True
    tokens = tuple(lexer)
    if not tokens:
        raise DeepAgentsCommandRejected("command is empty")
    if any(token in _SHELL_OPERATORS for token in tokens):
        raise DeepAgentsCommandRejected(
            "shell operators are not allowed; execute one approved command at a time"
        )
    return tokens


def _grep_result(
    *,
    error: str | None = None,
    matches: list[GrepMatch] | None = None,
    truncated: bool = False,
) -> GrepResult:
    kwargs: dict[str, Any] = {"error": error, "matches": matches}
    if "truncated" in inspect.signature(GrepResult).parameters:
        kwargs["truncated"] = truncated
    return GrepResult(**kwargs)


def _glob_result(
    *,
    error: str | None = None,
    matches: list[FileInfo] | None = None,
    truncated: bool = False,
) -> GlobResult:
    kwargs: dict[str, Any] = {"error": error, "matches": matches}
    if "truncated" in inspect.signature(GlobResult).parameters:
        kwargs["truncated"] = truncated
    return GlobResult(**kwargs)


class DeepAgentsSandboxAdapter(SandboxBackendProtocol):
    """Deep Agents protocol adapter backed by the isolated LUMI runtime."""

    def __init__(
        self,
        *,
        bridge: _LoopBridge,
        runtime: SandboxRuntimeService,
        sandbox_id: str,
        context: SandboxAccessContext,
    ) -> None:
        self._bridge = bridge
        self._runtime = runtime
        self._sandbox_id = sandbox_id
        self._context = context
        self._closed = False

    @classmethod
    def create(
        cls,
        spec: SandboxSpec,
        *,
        context: SandboxAccessContext,
        storage: ArtifactStoragePort | None = None,
        audit: AuditSink | None = None,
    ) -> DeepAgentsSandboxAdapter:
        bridge = _LoopBridge()
        backend = DockerSandboxBackend(storage=storage)
        runtime = SandboxRuntimeService(backend, audit or MemoryAuditSink())
        try:
            handle = bridge.run(runtime.create(spec, context=context))
        except Exception:
            bridge.close()
            raise
        return cls(
            bridge=bridge,
            runtime=runtime,
            sandbox_id=handle.sandbox_id,
            context=context,
        )

    @property
    def id(self) -> str:
        return self._sandbox_id

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        return self._bridge.run(self._aexecute_impl(command, timeout=timeout))

    async def aexecute(
        self,
        command: str,
        *,
        timeout: int | None = None,
    ) -> ExecuteResponse:
        return await self._bridge.arun(self._aexecute_impl(command, timeout=timeout))

    async def _aexecute_impl(
        self,
        command: str,
        *,
        timeout: int | None,
    ) -> ExecuteResponse:
        if timeout == 0:
            timeout = None
        argv = parse_deepagents_command(command)
        result = await self._runtime.exec(
            self._sandbox_id,
            SandboxCommand(argv=argv, timeout_seconds=timeout),
            context=self._context,
        )
        output = result.stdout
        if result.stderr:
            output = f"{output}\n{result.stderr}" if output else result.stderr
        return ExecuteResponse(
            output=output,
            exit_code=result.exit_code,
            truncated=result.usage.output_truncated,
        )

    def ls(self, path: str) -> LsResult:
        return self._bridge.run(self._als_impl(path))

    async def als(self, path: str) -> LsResult:
        return await self._bridge.arun(self._als_impl(path))

    async def _als_impl(self, path: str) -> LsResult:
        mapped = self._map_path(path)
        try:
            entries = await self._runtime.list_files(
                self._sandbox_id,
                mapped,
                context=self._context,
            )
        except Exception as exc:
            return LsResult(error=str(exc), entries=None)
        infos: list[FileInfo] = [
            {
                "path": entry.path,
                "is_dir": entry.is_directory,
                "size": entry.size,
            }
            for entry in entries
        ]
        return LsResult(entries=infos)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        return self._bridge.run(self._aread_impl(file_path, offset, limit))

    async def aread(
        self,
        file_path: str,
        offset: int = 0,
        limit: int = 2000,
    ) -> ReadResult:
        return await self._bridge.arun(self._aread_impl(file_path, offset, limit))

    async def _aread_impl(
        self,
        file_path: str,
        offset: int,
        limit: int,
    ) -> ReadResult:
        mapped = self._map_path(file_path)
        if offset < 0 or limit <= 0:
            return ReadResult(error="offset must be >= 0 and limit must be > 0")
        try:
            payload = await self._runtime.read_file(
                self._sandbox_id,
                mapped,
                context=self._context,
            )
        except Exception as exc:
            return ReadResult(error=str(exc))
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError:
            return ReadResult(
                file_data={
                    "content": base64.b64encode(payload).decode("ascii"),
                    "encoding": "base64",
                }
            )
        lines = text.splitlines(keepends=True)
        selected = lines[offset : offset + limit]
        return ReadResult(
            file_data={
                "content": "".join(selected),
                "encoding": "utf-8",
            }
        )

    def write(self, file_path: str, content: str) -> WriteResult:
        return self._bridge.run(self._awrite_impl(file_path, content))

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        return await self._bridge.arun(self._awrite_impl(file_path, content))

    async def _awrite_impl(self, file_path: str, content: str) -> WriteResult:
        mapped = self._map_path(file_path)
        try:
            await self._runtime.write_file(
                self._sandbox_id,
                mapped,
                content.encode("utf-8"),
                context=self._context,
            )
        except Exception as exc:
            return WriteResult(error=str(exc))
        return WriteResult(path=mapped)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        return self._bridge.run(
            self._aedit_impl(file_path, old_string, new_string, replace_all)
        )

    async def aedit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        return await self._bridge.arun(
            self._aedit_impl(file_path, old_string, new_string, replace_all)
        )

    async def _aedit_impl(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool,
    ) -> EditResult:
        if old_string == new_string:
            return EditResult(error="old_string and new_string must differ")
        mapped = self._map_path(file_path)
        try:
            payload = await self._runtime.read_file(
                self._sandbox_id,
                mapped,
                context=self._context,
            )
            text = payload.decode("utf-8")
        except Exception as exc:
            return EditResult(error=str(exc))
        count = text.count(old_string)
        if count == 0:
            return EditResult(error="old_string not found")
        if not replace_all and count != 1:
            return EditResult(
                error="old_string must be unique unless replace_all=true"
            )
        updated = text.replace(old_string, new_string, -1 if replace_all else 1)
        try:
            await self._runtime.write_file(
                self._sandbox_id,
                mapped,
                updated.encode("utf-8"),
                context=self._context,
            )
        except Exception as exc:
            return EditResult(error=str(exc))
        return EditResult(path=mapped, occurrences=count if replace_all else 1)

    def glob(self, pattern: str, path: str | None = None) -> GlobResult:
        return self._bridge.run(self._aglob_impl(pattern, path))

    async def aglob(self, pattern: str, path: str | None = None) -> GlobResult:
        return await self._bridge.arun(self._aglob_impl(pattern, path))

    async def _aglob_impl(self, pattern: str, path: str | None) -> GlobResult:
        root = self._map_path(path or "/")
        try:
            files, walk_truncated = await self._walk(root)
        except Exception as exc:
            return _glob_result(error=str(exc), matches=None)
        matches: list[FileInfo] = []
        for info in files:
            candidate = info["path"]
            relative = candidate.removeprefix(root.rstrip("/") + "/")
            if fnmatch.fnmatch(relative, pattern) or fnmatch.fnmatch(candidate, pattern):
                matches.append(info)
        return _glob_result(matches=matches, truncated=walk_truncated)

    def grep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> GrepResult:
        return self._bridge.run(self._agrep_impl(pattern, path, glob))

    async def agrep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> GrepResult:
        return await self._bridge.arun(self._agrep_impl(pattern, path, glob))

    async def _agrep_impl(
        self,
        pattern: str,
        path: str | None,
        glob_pattern: str | None,
    ) -> GrepResult:
        root = self._map_path(path or "/")
        try:
            files, walk_truncated = await self._walk(root)
        except Exception as exc:
            return _grep_result(error=str(exc), matches=None)
        matches: list[GrepMatch] = []
        for info in files:
            if info.get("is_dir"):
                continue
            candidate = info["path"]
            relative = candidate.removeprefix(root.rstrip("/") + "/")
            if glob_pattern and not (
                fnmatch.fnmatch(relative, glob_pattern)
                or fnmatch.fnmatch(candidate, glob_pattern)
            ):
                continue
            try:
                payload = await self._runtime.read_file(
                    self._sandbox_id,
                    candidate,
                    context=self._context,
                )
                text = payload.decode("utf-8")
            except Exception:
                continue
            for line_number, line in enumerate(text.splitlines(), start=1):
                if pattern in line:
                    matches.append(
                        {
                            "path": candidate,
                            "line": line_number,
                            "text": line,
                        }
                    )
        return _grep_result(matches=matches, truncated=walk_truncated)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return self._bridge.run(self._aupload_files_impl(files))

    async def aupload_files(
        self,
        files: list[tuple[str, bytes]],
    ) -> list[FileUploadResponse]:
        return await self._bridge.arun(self._aupload_files_impl(files))

    async def _aupload_files_impl(
        self,
        files: list[tuple[str, bytes]],
    ) -> list[FileUploadResponse]:
        responses: list[FileUploadResponse] = []
        for path, content in files:
            mapped = self._map_path(path)
            try:
                await self._runtime.write_file(
                    self._sandbox_id,
                    mapped,
                    content,
                    context=self._context,
                )
            except Exception as exc:
                responses.append(FileUploadResponse(path=path, error=str(exc)))
            else:
                responses.append(FileUploadResponse(path=path))
        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        return self._bridge.run(self._adownload_files_impl(paths))

    async def adownload_files(
        self,
        paths: list[str],
    ) -> list[FileDownloadResponse]:
        return await self._bridge.arun(self._adownload_files_impl(paths))

    async def _adownload_files_impl(
        self,
        paths: list[str],
    ) -> list[FileDownloadResponse]:
        responses: list[FileDownloadResponse] = []
        for path in paths:
            mapped = self._map_path(path)
            try:
                content = await self._runtime.read_file(
                    self._sandbox_id,
                    mapped,
                    context=self._context,
                )
            except Exception as exc:
                responses.append(FileDownloadResponse(path=path, error=str(exc)))
            else:
                responses.append(FileDownloadResponse(path=path, content=content))
        return responses

    def close(self) -> None:
        if self._closed:
            return
        try:
            self._bridge.run(
                self._runtime.terminate(
                    self._sandbox_id,
                    context=self._context,
                )
            )
        finally:
            self._closed = True
            self._bridge.close()

    def __enter__(self) -> DeepAgentsSandboxAdapter:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    async def _walk(
        self,
        root: str,
        *,
        max_entries: int = 5000,
    ) -> tuple[list[FileInfo], bool]:
        pending = [root]
        results: list[FileInfo] = []
        while pending:
            current = pending.pop()
            entries = await self._runtime.list_files(
                self._sandbox_id,
                current,
                context=self._context,
            )
            for entry in entries:
                info: FileInfo = {
                    "path": entry.path,
                    "is_dir": entry.is_directory,
                    "size": entry.size,
                }
                results.append(info)
                if len(results) >= max_entries:
                    return results, True
                if entry.is_directory:
                    pending.append(entry.path)
        return results, False

    @staticmethod
    def _map_path(path: str) -> str:
        if path in {"", "/", "/workspace", "/workspace/"}:
            return "/workspace/work"
        if path in _WORKSPACE_ROOTS:
            return path
        if path.startswith(
            ("/workspace/input/", "/workspace/work/", "/workspace/output/")
        ):
            return path
        if path.startswith("/"):
            return "/workspace/work/" + path.lstrip("/")
        return "/workspace/work/" + path
