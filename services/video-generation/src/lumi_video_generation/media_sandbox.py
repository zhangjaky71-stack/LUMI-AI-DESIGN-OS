from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol

from .model import RenderedVideo, VideoTimeline


@dataclass(frozen=True, slots=True)
class SandboxLimits:
    timeout_seconds: int = 300
    memory_mb: int = 2048
    cpu_seconds: int = 240
    network_disabled: bool = True


@dataclass(frozen=True, slots=True)
class FfmpegInvocation:
    argv: tuple[str, ...]
    limits: SandboxLimits
    output_path: str


class SandboxExecutor(Protocol):
    async def execute(self, invocation: FfmpegInvocation) -> None: ...


class SandboxPathResolver(Protocol):
    def resolve_readonly(self, durable_ref: str) -> str: ...
    def allocate_output(self, suffix: str) -> str: ...
    async def ingest_rendered_video(self, path: str, timeline: VideoTimeline) -> RenderedVideo: ...


def _safe_path(path: str) -> str:
    if not path.startswith("/sandbox/") or "\x00" in path or "\n" in path or "\r" in path:
        raise ValueError("VIDEO_SANDBOX_PATH_INVALID")
    return path


class FfmpegArgvCompiler:
    """Compiles typed timeline data into argv. It never creates a shell command string."""

    def compile(self, timeline: VideoTimeline, resolver: SandboxPathResolver) -> FfmpegInvocation:
        if not timeline.clips:
            raise ValueError("VIDEO_TIMELINE_CLIPS_REQUIRED")
        if any(transition.kind != "CUT" for transition in timeline.transitions):
            raise ValueError("VIDEO_FFMPEG_TRANSITION_NOT_SUPPORTED_V1")
        clip_paths = [_safe_path(resolver.resolve_readonly(clip.durable_ref)) for clip in timeline.clips]
        audio_paths = [_safe_path(resolver.resolve_readonly(track.durable_ref)) for track in timeline.audio_tracks]
        overlay_paths = [_safe_path(resolver.resolve_readonly(item.durable_ref)) for item in timeline.overlays]
        output_path = _safe_path(resolver.allocate_output(".mp4"))
        argv: list[str] = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y"]
        for path in clip_paths:
            argv.extend(("-i", path))
        for path in audio_paths:
            argv.extend(("-i", path))
        for path in overlay_paths:
            argv.extend(("-i", path))
        clip_count = len(clip_paths)
        filter_parts: list[str] = []
        if clip_count == 1:
            filter_parts.append("[0:v]setpts=PTS-STARTPTS[vbase]")
        else:
            labels = "".join(f"[{index}:v]" for index in range(clip_count))
            filter_parts.append(f"{labels}concat=n={clip_count}:v=1:a=0[vbase]")
        current = "vbase"
        overlay_input_start = clip_count + len(audio_paths)
        for index, overlay in enumerate(timeline.overlays):
            next_label = f"vov{index}"
            overlay_input = overlay_input_start + index
            filter_parts.append(
                f"[{current}][{overlay_input}:v]overlay=x={overlay.x}:y={overlay.y}:enable='between(t,{format(overlay.start_seconds, 'f')},{format(overlay.end_seconds, 'f')})'[{next_label}]"
            )
            current = next_label
        argv.extend(("-filter_complex", ";".join(filter_parts), "-map", f"[{current}]"))
        if audio_paths:
            argv.extend(("-map", f"{clip_count}:a?"))
        argv.extend((
            "-r", str(timeline.output_spec.fps),
            "-s", f"{timeline.output_spec.width}x{timeline.output_spec.height}",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
        ))
        if audio_paths:
            argv.extend(("-c:a", "aac"))
        argv.append(output_path)
        return FfmpegInvocation(argv=tuple(argv), limits=SandboxLimits(), output_path=output_path)


class TypedFfmpegSandbox:
    def __init__(self, *, executor: SandboxExecutor, resolver: SandboxPathResolver) -> None:
        self.executor = executor
        self.resolver = resolver
        self.compiler = FfmpegArgvCompiler()

    async def render(self, timeline: VideoTimeline) -> RenderedVideo:
        invocation = self.compiler.compile(timeline, self.resolver)
        await self.executor.execute(invocation)
        return await self.resolver.ingest_rendered_video(invocation.output_path, timeline)
