from __future__ import annotations

from decimal import Decimal

from lumi_image_edit import (
    ArtifactEditResult,
    EditFinding,
    EditIntent,
    EditValidationReport,
    GatewayEditResult,
    ImageEditPipeline,
    ImageEditSpec,
    InMemoryEditRepository,
    SourceImageRef,
    ValidatedImage,
)

SHA = "a" * 64
GIT = "b" * 40


def source() -> SourceImageRef:
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
        "USER_OWNED",
        True,
    )


def base(**overrides: object) -> ImageEditSpec:
    values = dict(
        organization_id="org",
        project_id="project",
        task_id="task",
        operation_id="op",
        source=source(),
        intent=EditIntent("BACKGROUND_REPLACE", "make background black"),
        constraints=(),
        protected_regions=(),
        mask=None,
        brand_rule_set_version=None,
        identity_requirement_ids=(),
        budget_limit_usd=Decimal("2"),
        code_git_sha=GIT,
    )
    values.update(overrides)
    return ImageEditSpec(**values)


class Auth:
    def __init__(self, current: SourceImageRef | None = None) -> None:
        self.current = current or source()

    def authorize_current(self, spec: ImageEditSpec) -> SourceImageRef:
        del spec
        return self.current


class Structural:
    def __init__(self) -> None:
        self.calls = 0

    async def apply(self, spec, ops) -> str:
        del spec
        self.calls += 1
        assert ops
        return "design-v4"


class Gateway:
    def __init__(self, result: GatewayEditResult | None = None) -> None:
        self.calls = 0
        self.polls = 0
        self.last = None
        self.result = result or GatewayEditResult(
            "SUCCEEDED",
            "mock",
            "edit-v1",
            "req",
            "provider://output",
            "image/png",
            Decimal("0.2"),
            "exact",
            "price",
            ("route",),
            {},
        )

    async def invoke(self, request):
        self.calls += 1
        self.last = request
        return self.result

    async def poll(self, request, pending):
        del request, pending
        self.polls += 1
        return self.result

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
        )


class Validator:
    def __init__(self, decision: str = "PASS") -> None:
        self.decision = decision
        self.calls = 0

    async def validate(self, **kwargs) -> EditValidationReport:
        del kwargs
        self.calls += 1
        status = "PASS" if self.decision == "PASS" else "FAIL"
        severity = "SOFT" if self.decision == "REPAIR" else "HARD"
        return EditValidationReport(
            (EditFinding("protected-region", status, severity, "TEST"),)
        )


class Artifacts:
    def __init__(self) -> None:
        self.calls = 0

    async def append_candidate(self, **kwargs) -> ArtifactEditResult:
        self.calls += 1
        status = "READY" if kwargs["validation"].decision == "PASS" else "DRAFT"
        return ArtifactEditResult("artifact", "v4", status, "asset-v4")


class Canvas:
    def __init__(self) -> None:
        self.calls = 0

    async def replace_asset(self, **kwargs) -> str:
        del kwargs
        self.calls += 1
        return "design-v5"


class Events:
    def __init__(self) -> None:
        self.events: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def emit(self, *args: object, **kwargs: object) -> None:
        self.events.append((args, kwargs))


class Compositor:
    def __init__(self) -> None:
        self.calls = 0

    async def composite(self, **kwargs):
        self.calls += 1
        return kwargs["generated"]


def pipe(
    gateway: Gateway | None = None,
    validator: Validator | None = None,
    compositor: Compositor | None = None,
):
    repository = InMemoryEditRepository()
    pipeline = ImageEditPipeline(
        repository=repository,
        authorization=Auth(),
        structural=Structural(),
        gateway=gateway or Gateway(),
        materializer=Materializer(),
        postflight=validator or Validator(),
        artifacts=Artifacts(),
        canvas=Canvas(),
        events=Events(),
        compositor=compositor,
    )
    return pipeline, repository
