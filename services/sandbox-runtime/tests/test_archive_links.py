from __future__ import annotations

import io
import stat
import tarfile
import zipfile

import pytest

from lumi_sandbox_runtime.workspace import WorkspaceViolation, validate_archive_bytes


def test_tar_symlink_is_rejected() -> None:
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w") as archive:
        member = tarfile.TarInfo("safe-link")
        member.type = tarfile.SYMTYPE
        member.linkname = "../../etc/passwd"
        archive.addfile(member)
    with pytest.raises(WorkspaceViolation, match="link member"):
        validate_archive_bytes("evil.tar", payload.getvalue())


def test_zip_unix_symlink_is_rejected() -> None:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        member = zipfile.ZipInfo("safe-link")
        member.create_system = 3
        member.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(member, "../../etc/passwd")
    with pytest.raises(WorkspaceViolation, match="symlink member"):
        validate_archive_bytes("evil.zip", payload.getvalue())
