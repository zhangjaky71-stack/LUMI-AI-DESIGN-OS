from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "services" / "video-generation" / "src" / "lumi_video_generation"
REQUIRED = {
    "model.py",
    "ports.py",
    "storyboard.py",
    "model_gateway_adapter.py",
    "output_adapter.py",
    "validation.py",
    "media_sandbox.py",
    "repository.py",
    "pipeline.py",
}


def main() -> None:
    present = {path.name for path in SERVICE.glob("*.py")}
    missing = sorted(REQUIRED - present)
    assert not missing, f"missing runtime files: {missing}"

    parsed = 0
    for path in sorted(SERVICE.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        ast.parse(source, filename=str(path))
        parsed += 1
        if path.name == "media_sandbox.py":
            assert "shell=True" not in source
            assert "subprocess" not in source
            assert "FFMPEG_NETWORK_OR_PROTOCOL_INPUT_FORBIDDEN" in source
        if path.name == "pipeline.py":
            assert "WAITING_EXTERNAL" in source
            assert "retry_shot" in source
            assert "CANCEL_REQUESTED" in source
        if path.name == "model_gateway_adapter.py":
            assert "VIDEO_PROVIDER_ASYNC_SUBMIT_REQUIRED" in source
            assert "get_async_status" in source

    migration = ROOT / "apps" / "api" / "migrations" / "versions" / "20260817_0017_video_generation.py"
    migration_source = migration.read_text(encoding="utf-8")
    assert 'down_revision = "20260817_0016"' in migration_source

    print(f"NODE48_VIDEO_GENERATION_VALIDATION_PASS ast_files={parsed}")


if __name__ == "__main__":
    main()
