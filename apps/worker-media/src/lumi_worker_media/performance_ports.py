from __future__ import annotations

from lumi_domain.performance_events import (
    PerformanceStage,
    PerformanceTelemetryContext,
    measure_performance_stage,
)
from lumi_image_generation.model import (
    AuthorizedReference,
    FetchedImage,
    GatewayGenerationRequest,
    GatewayGenerationResult,
    GenerationCandidate,
    GenerationProvenanceSnapshot,
    ImageGenerationSpec,
    StoredImage,
    ValidatedImage,
    ValidationBundle,
)
from lumi_image_generation.ports import (
    ArtifactCandidatePort,
    ArtifactCandidateResult,
    DurableImageStorePort,
    GatewayEstimate,
    GenerationValidationPort,
    ImageModelGatewayPort,
    ProviderOutputFetcherPort,
)

_SERVICE = "worker-media"


class TimedImageModelGateway:
    def __init__(
        self,
        inner: ImageModelGatewayPort,
        telemetry: PerformanceTelemetryContext | None,
    ) -> None:
        self.inner = inner
        self.telemetry = telemetry

    async def estimate(self, request: GatewayGenerationRequest) -> GatewayEstimate:
        with measure_performance_stage(
            self.telemetry,
            stage=PerformanceStage.ROUTING,
            service=_SERVICE,
            operation_id=request.root_operation_id,
            task_id=request.task_id,
        ):
            return await self.inner.estimate(request)

    async def invoke(self, request: GatewayGenerationRequest) -> GatewayGenerationResult:
        with measure_performance_stage(
            self.telemetry,
            stage=PerformanceStage.PROVIDER,
            service=_SERVICE,
            operation_id=request.root_operation_id,
            task_id=request.task_id,
        ):
            return await self.inner.invoke(request)

    async def poll(
        self,
        *,
        request: GatewayGenerationRequest,
        pending_result: GatewayGenerationResult,
    ) -> GatewayGenerationResult:
        with measure_performance_stage(
            self.telemetry,
            stage=PerformanceStage.PROVIDER,
            service=_SERVICE,
            operation_id=request.root_operation_id,
            task_id=request.task_id,
        ):
            return await self.inner.poll(request=request, pending_result=pending_result)


class TimedProviderOutputFetcher:
    def __init__(
        self,
        inner: ProviderOutputFetcherPort,
        telemetry: PerformanceTelemetryContext | None,
        *,
        operation_id: str,
        task_id: str,
    ) -> None:
        self.inner = inner
        self.telemetry = telemetry
        self.operation_id = operation_id
        self.task_id = task_id

    async def fetch(self, ref: str, declared_mime_type: str | None) -> FetchedImage:
        with measure_performance_stage(
            self.telemetry,
            stage=PerformanceStage.DOWNLOAD,
            service=_SERVICE,
            operation_id=self.operation_id,
            task_id=self.task_id,
        ):
            return await self.inner.fetch(ref, declared_mime_type)


class TimedDurableImageStore:
    def __init__(
        self,
        inner: DurableImageStorePort,
        telemetry: PerformanceTelemetryContext | None,
    ) -> None:
        self.inner = inner
        self.telemetry = telemetry

    async def store(
        self,
        *,
        spec: ImageGenerationSpec,
        candidate_id: str,
        image: ValidatedImage,
    ) -> StoredImage:
        with measure_performance_stage(
            self.telemetry,
            stage=PerformanceStage.ARTIFACT_PERSIST,
            service=_SERVICE,
            operation_id=spec.operation_id,
            task_id=spec.task_id,
        ):
            return await self.inner.store(spec=spec, candidate_id=candidate_id, image=image)


class TimedGenerationValidator:
    def __init__(
        self,
        inner: GenerationValidationPort,
        telemetry: PerformanceTelemetryContext | None,
    ) -> None:
        self.inner = inner
        self.telemetry = telemetry

    async def validate(
        self,
        *,
        spec: ImageGenerationSpec,
        candidate_id: str,
        image: ValidatedImage,
        stored: StoredImage,
        references: tuple[AuthorizedReference, ...],
    ) -> ValidationBundle:
        with measure_performance_stage(
            self.telemetry,
            stage=PerformanceStage.VALIDATION,
            service=_SERVICE,
            operation_id=spec.operation_id,
            task_id=spec.task_id,
        ):
            return await self.inner.validate(
                spec=spec,
                candidate_id=candidate_id,
                image=image,
                stored=stored,
                references=references,
            )


class TimedArtifactCandidate:
    def __init__(
        self,
        inner: ArtifactCandidatePort,
        telemetry: PerformanceTelemetryContext | None,
    ) -> None:
        self.inner = inner
        self.telemetry = telemetry

    async def create_candidate(
        self,
        *,
        spec: ImageGenerationSpec,
        candidate: GenerationCandidate,
        stored: StoredImage,
        provenance: GenerationProvenanceSnapshot,
        validation: ValidationBundle,
    ) -> ArtifactCandidateResult:
        with measure_performance_stage(
            self.telemetry,
            stage=PerformanceStage.ARTIFACT_PERSIST,
            service=_SERVICE,
            operation_id=spec.operation_id,
            task_id=spec.task_id,
        ):
            return await self.inner.create_candidate(
                spec=spec,
                candidate=candidate,
                stored=stored,
                provenance=provenance,
                validation=validation,
            )
