from __future__ import annotations

import io
import posixpath
import stat
import tarfile
import zipfile
from pathlib import PurePosixPath


class WorkspaceViolation(ValueError):
    code = "SANDBOX_WORKSPACE_VIOLATION"


_ALLOWED_ROOTS = {"input", "work", "output"}


def normalize_workspace_path(path: str) -> str:
    if not path or "\x00" in path:
        raise WorkspaceViolation("path is empty or contains NUL")
    candidate = PurePosixPath(path)
    if candidate.is_absolute():
        try:
            relative = candidate.relative_to("/workspace")
        except ValueError as exc:
            raise WorkspaceViolation("absolute path must remain under /workspace") from exc
    else:
        relative = candidate
    parts = relative.parts
    if not parts or parts[0] not in _ALLOWED_ROOTS:
        raise WorkspaceViolation("path must start with input/, work/, or output/")
    if any(part in {"", ".", ".."} for part in parts):
        raise WorkspaceViolation("path traversal is forbidden")
    normalized = posixpath.normpath("/workspace/" + "/".join(parts))
    if not normalized.startswith("/workspace/"):
        raise WorkspaceViolation("path escaped workspace")
    return normalized


def relative_workspace_path(path: str) -> str:
    normalized = normalize_workspace_path(path)
    return normalized.removeprefix("/workspace/")


def _validate_member_name(member: str) -> None:
    if not member or "\x00" in member:
        raise WorkspaceViolation("archive member name is empty or contains NUL")
    pure = PurePosixPath(member)
    if pure.is_absolute() or any(part == ".." for part in pure.parts):
        raise WorkspaceViolation(f"archive member escapes destination: {member}")


def _zip_member_is_symlink(member: zipfile.ZipInfo) -> bool:
    unix_mode = (member.external_attr >> 16) & 0xFFFF
    return stat.S_ISLNK(unix_mode)


def validate_archive_bytes(
    filename: str,
    payload: bytes,
    *,
    max_members: int = 10_000,
) -> None:
    lowered = filename.lower()
    if lowered.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            members = archive.infolist()
            if len(members) > max_members:
                raise WorkspaceViolation("archive has too many members")
            for member in members:
                _validate_member_name(member.filename)
                if _zip_member_is_symlink(member):
                    raise WorkspaceViolation(
                        f"archive symlink member is forbidden: {member.filename}"
                    )
        return
    if lowered.endswith((".tar", ".tar.gz", ".tgz")):
        mode = "r:gz" if lowered.endswith((".tar.gz", ".tgz")) else "r:"
        with tarfile.open(fileobj=io.BytesIO(payload), mode=mode) as archive:
            members = archive.getmembers()
            if len(members) > max_members:
                raise WorkspaceViolation("archive has too many members")
            for member in members:
                _validate_member_name(member.name)
                if member.issym() or member.islnk():
                    raise WorkspaceViolation(
                        f"archive link member is forbidden: {member.name}"
                    )
        return
