from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UploadQuota:
    max_file_bytes: int
    max_org_storage_bytes: int
    current_org_storage_bytes: int
    max_project_file_bytes: int | None = None

    def __post_init__(self) -> None:
        if self.max_file_bytes <= 0 or self.max_org_storage_bytes <= 0:
            raise ValueError("quota limits must be positive")
        if self.current_org_storage_bytes < 0:
            raise ValueError("current storage must be non-negative")
        if self.max_project_file_bytes is not None and self.max_project_file_bytes <= 0:
            raise ValueError("project file limit must be positive")


def require_upload_allowed(*, declared_size: int, quota: UploadQuota) -> None:
    if declared_size <= 0:
        raise ValueError("UPLOAD_SIZE_INVALID")
    effective_file_limit = quota.max_file_bytes
    if quota.max_project_file_bytes is not None:
        effective_file_limit = min(effective_file_limit, quota.max_project_file_bytes)
    if declared_size > effective_file_limit:
        raise ValueError("UPLOAD_FILE_TOO_LARGE")
    if quota.current_org_storage_bytes + declared_size > quota.max_org_storage_bytes:
        raise ValueError("ORG_STORAGE_QUOTA_EXCEEDED")


def require_verified_size_within_quota(
    *,
    verified_size: int,
    declared_size: int,
    quota: UploadQuota,
) -> None:
    if verified_size != declared_size:
        raise ValueError("UPLOAD_SIZE_MISMATCH")
    require_upload_allowed(declared_size=verified_size, quota=quota)
