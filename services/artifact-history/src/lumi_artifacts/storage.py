from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .history import ArtifactHistory, ArtifactHistoryError
from .model import ArtifactFile


@dataclass(frozen=True, slots=True)
class StoredObjectStat:
    storage_key: str
    size_bytes: int
    checksum_sha256: str
    mime_type: str | None = None


class ArtifactObjectStore(Protocol):
    def stat(self, storage_key: str) -> StoredObjectStat | None: ...


def attach_verified_file(
    history: ArtifactHistory,
    file: ArtifactFile,
    store: ArtifactObjectStore,
) -> None:
    """Attach only after a durable object HEAD matches immutable file metadata."""
    stat = store.stat(file.storage_key)
    if stat is None:
        raise ArtifactHistoryError("storage object missing")
    if stat.storage_key != file.storage_key:
        raise ArtifactHistoryError("storage key mismatch")
    if stat.checksum_sha256 != file.checksum_sha256:
        raise ArtifactHistoryError("storage checksum mismatch")
    if stat.size_bytes != file.size_bytes:
        raise ArtifactHistoryError("storage size mismatch")
    if stat.mime_type is not None and stat.mime_type != file.mime_type:
        raise ArtifactHistoryError("storage MIME mismatch")
    history.add_file(file)
