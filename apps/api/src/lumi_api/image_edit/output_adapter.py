from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from lumi_image_edit import GatewayEditResult, ImageEditSpec, ValidatedImage
from lumi_image_generation.image_validation import validate_provider_image
from lumi_image_generation.model import FetchedImage, OutputFormat, OutputRequirements


class OutputFetchPort(Protocol):
    async def fetch(
        self,
        ref: str,
        declared_mime_type: str | None,
    ) -> FetchedImage: ...


class OutputStorePort(Protocol):
    async def store_bytes(
        self,
        *,
        organization_id: str,
        project_id: str,
        edit_id: str,
        content: bytes,
        mime_type: str,
        checksum_sha256: str,
        width: int,
        height: int,
    ) -> tuple[str, str, str | None]: ...


@dataclass(slots=True)
class ProviderOutputMaterializer:
    fetcher: OutputFetchPort
    store: OutputStorePort

    async def materialize(
        self,
        *,
        spec: ImageEditSpec,
        edit_id: str,
        result: GatewayEditResult,
    ) -> ValidatedImage:
        if not result.output_ref:
            raise ValueError("IMAGE_EDIT_OUTPUT_REF_REQUIRED")
        fetched = await self.fetcher.fetch(
            result.output_ref,
            result.output_mime_type,
        )
        declared = fetched.declared_mime_type or "image/png"
        formats = {
            "image/png": OutputFormat.PNG,
            "image/jpeg": OutputFormat.JPEG,
            "image/webp": OutputFormat.WEBP,
        }
        if declared not in formats:
            raise ValueError("IMAGE_EDIT_OUTPUT_MIME_UNSUPPORTED")
        output_format = formats[declared]

        class _Spec:
            target_width = spec.source.width
            target_height = spec.source.height
            output_requirements = OutputRequirements(
                output_format,
                False,
                True,
                None,
                None,
            )

        checked = validate_provider_image(fetched, _Spec())
        bucket, key, asset_id = await self.store.store_bytes(
            organization_id=spec.organization_id,
            project_id=spec.project_id,
            edit_id=edit_id,
            content=checked.content,
            mime_type=checked.mime_type,
            checksum_sha256=checked.checksum_sha256,
            width=checked.width,
            height=checked.height,
        )
        return ValidatedImage(
            bucket,
            key,
            checked.checksum_sha256,
            checked.mime_type,
            checked.width,
            checked.height,
            len(checked.content),
            asset_id,
        )
