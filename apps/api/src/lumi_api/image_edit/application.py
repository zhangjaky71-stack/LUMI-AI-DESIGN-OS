from __future__ import annotations

from dataclasses import dataclass

from lumi_image_edit import EditJob, ImageEditPipeline, ImageEditSpec


@dataclass(slots=True)
class ImageEditApplicationService:
    pipeline: ImageEditPipeline
    code_git_sha: str

    def get(self, *, organization_id: str, edit_id: str) -> EditJob:
        job = self.pipeline.repository.get(organization_id, edit_id)
        if job is None:
            raise LookupError("IMAGE_EDIT_NOT_FOUND")
        return job

    async def submit(self, spec: ImageEditSpec) -> EditJob:
        if spec.code_git_sha != self.code_git_sha:
            raise ValueError("IMAGE_EDIT_CODE_GIT_SHA_MISMATCH")
        return await self.pipeline.submit(spec)

    async def execute(self, *, organization_id: str, edit_id: str) -> EditJob:
        return await self.pipeline.execute(
            organization_id=organization_id,
            edit_id_value=edit_id,
        )

    async def resume_pending(
        self,
        *,
        organization_id: str,
        edit_id: str,
    ) -> EditJob:
        return await self.pipeline.resume_pending(
            organization_id=organization_id,
            edit_id_value=edit_id,
        )

    async def approve_mask(
        self,
        *,
        organization_id: str,
        edit_id: str,
        approved_by: str,
    ) -> EditJob:
        return await self.pipeline.approve_mask(
            organization_id=organization_id,
            edit_id_value=edit_id,
            approved_by=approved_by,
        )

    async def confirm_broad_change(
        self,
        *,
        organization_id: str,
        edit_id: str,
        confirmed_by: str,
    ) -> EditJob:
        return await self.pipeline.confirm_broad_change(
            organization_id=organization_id,
            edit_id_value=edit_id,
            confirmed_by=confirmed_by,
        )

    async def cancel(self, *, organization_id: str, edit_id: str) -> EditJob:
        return await self.pipeline.cancel(
            organization_id=organization_id,
            edit_id_value=edit_id,
        )
