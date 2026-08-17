from __future__ import annotations

import asyncio
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "services/image-edit/src"))

from lumi_image_edit import (  # noqa: E402
    ArtifactEditResult,
    EditFinding,
    EditIntent,
    EditValidationReport,
    GatewayEditResult,
    ImageEditPipeline,
    ImageEditSpec,
    InMemoryEditRepository,
    MaskSpec,
    PixelRect,
    SourceImageRef,
    ValidatedImage,
)

SHA = "a" * 64
GIT = "b" * 40


def _source() -> SourceImageRef:
    return SourceImageRef(
        "org",
        "project",
        "artifact",
        "v3",
        "asset",
        "7",
        "bucket/source.png",
        SHA,
        1000,
        1000,
        "image/png",
        "owned",
        True,
    )


def _spec(operation_id: str, *, structural: bool) -> ImageEditSpec:
    if structural:
        return ImageEditSpec(
            "org",
            "project",
            "task",
            operation_id,
            _source(),
            EditIntent(
                "RESIZE_TEXT",
                "resize title",
                ("title",),
                {"width": 100, "height": 20},
            ),
            (),
            (),
            None,
            None,
            (),
            Decimal("1"),
            GIT,
            "doc",
            1,
        )
    mask = MaskSpec(
        "m",
        "1",
        "USER_BRUSH",
        "asset",
        "7",
        SHA,
        1000,
        1000,
        PixelRect(0, 0, 300, 1000),
        "d" * 64,
        "bucket/mask.png",
    )
    return ImageEditSpec(
        "org",
        "project",
        "task",
        operation_id,
        _source(),
        EditIntent("BACKGROUND_REPLACE", "background black"),
        (),
        (),
        mask,
        None,
        (),
        Decimal("1"),
        GIT,
    )


class Authorization:
    def authorize_current(self, spec: ImageEditSpec) -> SourceImageRef:
        return spec.source


class Structural:
    calls = 0

    async def apply(self, spec, operations) -> str:
        del spec, operations
        self.calls += 1
        return "design-v4"


class Gateway:
    calls = 0

    async def invoke(self, request):
        del request
        self.calls += 1
        return GatewayEditResult(
            "SUCCEEDED",
            "mock",
            "edit-v1",
            "provider-request",
            "provider://output",
            "image/png",
            Decimal("0.1"),
            "exact",
            "pricing-v1",
        )

    async def poll(self, request, pending):
        del request
        return pending

    async def cancel(self, pending) -> bool:
        del pending
        return True


class Materializer:
    async def materialize(self, **kwargs) -> ValidatedImage:
        del kwargs
        return ValidatedImage(
            "generated",
            "edit.png",
            "c" * 64,
            "image/png",
            1000,
            1000,
            100,
            "asset-v4",
        )


class Validator:
    async def validate(self, **kwargs) -> EditValidationReport:
        del kwargs
        return EditValidationReport(
            (EditFinding("protected-region", "PASS", "HARD", "SMOKE"),)
        )


class Artifacts:
    async def append_candidate(self, **kwargs) -> ArtifactEditResult:
        del kwargs
        return ArtifactEditResult("artifact", "v4", "READY", "asset-v4")


class Canvas:
    async def replace_asset(self, **kwargs) -> str:
        del kwargs
        return "design-v5"


class Events:
    async def emit(self, *args, **kwargs) -> None:
        del args, kwargs


async def main() -> None:
    gateway = Gateway()
    pipeline = ImageEditPipeline(
        repository=InMemoryEditRepository(),
        authorization=Authorization(),
        structural=Structural(),
        gateway=gateway,
        materializer=Materializer(),
        postflight=Validator(),
        artifacts=Artifacts(),
        canvas=Canvas(),
        events=Events(),
    )
    structural = await pipeline.submit(_spec("smoke-struct", structural=True))
    queued = await pipeline.submit(_spec("smoke-pixel", structural=False))
    pixel = await pipeline.execute(
        organization_id="org",
        edit_id_value=queued.edit_id,
    )
    assert structural.status == "COMPLETED"
    assert pixel.status == "COMPLETED"
    assert gateway.calls == 1
    assert pixel.result_artifact_version_id == "v4"
    print("NODE47_IMAGE_EDIT_RUNTIME_SMOKE_PASS")
    print("structural_provider_calls=0 pixel_provider_calls=1 append_only_candidate=v4")


if __name__ == "__main__":
    asyncio.run(main())
