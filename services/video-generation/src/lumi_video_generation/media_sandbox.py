from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Protocol

from .model import VideoTimeline


@dataclass(frozen=True, slots=True)
class FfmpegInvocation:
    argv: tuple[str, ...]
    shell: bool = False

    def __post_init__(self) -> None:
        if self.shell:
            raise ValueError("FFMPEG_SHELL_EXECUTION_FORBIDDEN")
        if not self.argv or self.argv[0] != "ffmpeg":
            raise ValueError("ffmpeg argv must start with ffmpeg")


@dataclass(frozen=True, slots=True)
class SandboxLimits:
    timeout_seconds: int = 300
    memory_mb: int = 2048
    cpu_seconds: int = 240
    max_output_bytes: int = 2_000_000_000

    def __post_init__(self) -> None:
        if min(self.timeout_seconds, self.memory_mb, self.cpu_seconds, self.max_output_bytes) <= 0:
            raise ValueError("sandbox limits must be positive")


class SandboxExecutorPort(Protocol):
    async def execute(self, invocation: FfmpegInvocation, limits: SandboxLimits) -> None: ...


def _safe_local_path(value: str) -> str:
    if not value or "\x00" in value or "\n" in value or "\r" in value:
        raise ValueError("FFMPEG_PATH_INVALID")
    lowered = value.lower()
    if "://" in lowered or lowered.startswith(("file:", "concat:", "pipe:")):
        raise ValueError("FFMPEG_NETWORK_OR_PROTOCOL_INPUT_FORBIDDEN")
    path = PurePosixPath(value)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("FFMPEG_PATH_MUST_BE_ABSOLUTE_SANDBOX_PATH")
    if any(part in {";", "|", "&", "`", "$("} for part in path.parts):
        raise ValueError("FFMPEG_PATH_TOKEN_FORBIDDEN")
    return str(path)


class FfmpegArgvCompiler:
    def compile(
        self,
        *,
        timeline: VideoTimeline,
        local_clip_paths: tuple[str, ...],
        output_path: str,
    ) -> FfmpegInvocation:
        if len(local_clip_paths) != len(timeline.clips):
            raise ValueError("FFMPEG_INPUT_COUNT_MISMATCH")
        inputs = tuple(_safe_local_path(item) for item in local_clip_paths)
        output = _safe_local_path(output_path)
        argv: list[str] = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error"]
        for source in inputs:
            argv.extend(("-i", source))

        transitions = tuple(clip.transition for clip in timeline.clips)
        if any(item not in {"CUT", "FADE"} for item in transitions):
            raise ValueError("FFMPEG_TRANSITION_UNSUPPORTED")

        # P0 composition is deterministic concat. FADE is expressed as bounded
        # per-clip fade-in/out filters; arbitrary filter text is never accepted.
        filters: list[str] = []
        labels: list[str] = []
        for index, clip in enumerate(timeline.clips):
            label = f"v{index}"
            duration = format(clip.duration_seconds, "f")
            if clip.transition == "FADE":
                filters.append(
                    f"[{index}:v]scale={timeline.width}:{timeline.height},"
                    f"fps={timeline.fps},fade=t=in:st=0:d=0.25,"
                    f"fade=t=out:st=max(0,{duration}-0.25):d=0.25[{label}]"
                )
            else:
                filters.append(
                    f"[{index}:v]scale={timeline.width}:{timeline.height},"
                    f"fps={timeline.fps}[{label}]"
                )
            labels.append(f"[{label}]")
        filters.append("".join(labels) + f"concat=n={len(labels)}:v=1:a=0[vout]")
        argv.extend(("-filter_complex", ";".join(filters), "-map", "[vout]"))
        argv.extend(("-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart"))
        argv.extend(("-y", output))
        return FfmpegInvocation(tuple(argv))


@dataclass(slots=True)
class TypedFfmpegSandbox:
    executor: SandboxExecutorPort
    limits: SandboxLimits = SandboxLimits()

    async def run(self, invocation: FfmpegInvocation) -> None:
        await self.executor.execute(invocation, self.limits)
