from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from lumi_image_generation import GenerationJob, ImageGenerationPipeline, ImageGenerationSpec


@dataclass(slots=True)
class ImageGenerationApplicationService:
    pipeline: ImageGenerationPipeline
    code_git_sha: str

    def get(self, *, organization_id: UUID, generation_id: UUID) -> GenerationJob:
        value = self.pipeline.repository.get(organization_id, generation_id)
        if value is None:
            raise LookupError("GENERATION_JOB_NOT_FOUND")
        return value

    async def submit(self, spec: ImageGenerationSpec, *, now: str) -> GenerationJob:
        if spec.code_git_sha != self.code_git_sha:
            raise ValueError("GENERATION_DEPLOYMENT_GIT_SHA_MISMATCH")
        return await self.pipeline.submit(spec, now=now)

    async def cancel(
        self, *, organization_id: UUID, generation_id: UUID, now: str
    ) -> GenerationJob:
        return await self.pipeline.cancel(
            organization_id=organization_id,
            generation_id=generation_id,
            now=now,
        )

    async def execute(
        self, *, organization_id: UUID, generation_id: UUID, now: str
    ) -> GenerationJob:
        return await self.pipeline.execute(
            organization_id=organization_id,
            generation_id=generation_id,
            now=now,
        )

    async def resume_pending(
        self, *, organization_id: UUID, generation_id: UUID, now: str
    ) -> GenerationJob:
        return await self.pipeline.resume_pending(
            organization_id=organization_id,
            generation_id=generation_id,
            now=now,
        )
