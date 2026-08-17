from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .model import ArtifactVersionSnapshot, ExportFormat
from .ports import ObjectReadPort


_TARGET_MIME = {
    ExportFormat.PNG: "image/png",
    ExportFormat.JPEG: "image/jpeg",
    ExportFormat.MP4: "video/mp4",
    ExportFormat.PDF: "application/pdf",
    ExportFormat.PPTX: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


@dataclass(slots=True)
class VerifiedSameFormatRenderer:
    """Exports an approved exact file without transcoding when MIME already matches."""

    reader: ObjectReadPort
    version: str = "same-format/1.0"

    def supports(self, *, artifact_type: str, target_format: ExportFormat) -> bool:
        return target_format in _TARGET_MIME

    async def render(
        self,
        *,
        snapshot: ArtifactVersionSnapshot,
        target_format: ExportFormat,
        output_name: str,
    ) -> tuple[bytes, str, str]:
        expected_mime = _TARGET_MIME.get(target_format)
        if expected_mime is None:
            raise ValueError("EXPORT_FORMAT_NOT_SUPPORTED")
        source = snapshot.primary_file()
        if source.mime_type != expected_mime:
            raise ValueError("EXPORT_TRANSCODER_REQUIRED")
        payload = await self.reader.read_exact(source=source)
        if len(payload) != source.size_bytes:
            raise ValueError("EXPORT_SOURCE_SIZE_MISMATCH")
        if hashlib.sha256(payload).hexdigest() != source.checksum_sha256:
            raise ValueError("EXPORT_SOURCE_CHECKSUM_MISMATCH")
        return payload, expected_mime, self.version
