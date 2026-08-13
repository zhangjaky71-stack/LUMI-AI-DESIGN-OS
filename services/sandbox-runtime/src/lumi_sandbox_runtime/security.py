from __future__ import annotations

import hashlib
import mimetypes
import re
import shutil
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Iterable

_ALLOWED_ZONES = frozenset({"input", "work", "output"})
_WRITABLE_ZONES = frozenset({"work", "output"})
_FORBIDDEN_ARG_FRAGMENTS = (
    "/var/run/docker.sock",
    "/run/docker.sock",
    "/proc/1/root",
    "/proc/self/root",
    "/dev/mem",
    "/dev/kmem",
)
_SECRET_KEY_RE = re.compile(
    r"(?i)(secret|password|passwd|api[_-]?key|access[_-]?token|refresh[_-]?token|credential)"
)
_TEXT_SECRET_RE = re.compile(
    r"(?i)(authorization:\s*bearer\s+|(?:api[_-]?key|access[_-]?token|secret|password)\s*[=:]\s*)"
    r"([^\s,;]+)"
)


class SandboxPathError(ValueError):
    pass


class SandboxCommandError(ValueError):
    pass


class UnsafeArchiveError(ValueError):
    pass


def normalize_workspace_path(path: str, *, writable: bool = False) -> tuple[str, str]:
    if not path or "\x00" in path or "\\" in path:
        raise SandboxPathError("SANDBOX_PATH_INVALID")
    candidate = PurePosixPath(path)
    if candidate.is_absolute():
        raise SandboxPathError("SANDBOX_ABSOLUTE_PATH_FORBIDDEN")
    parts = candidate.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise SandboxPathError("SANDBOX_PATH_TRAVERSAL")
    zone = parts[0]
    if zone not in _ALLOWED_ZONES:
        raise SandboxPathError("SANDBOX_PATH_ZONE_FORBIDDEN")
    if writable and zone not in _WRITABLE_ZONES:
        raise SandboxPathError("SANDBOX_PATH_READ_ONLY")
    relative = "/".join(parts[1:])
    return zone, relative


def workspace_absolute(path: str, *, writable: bool = False) -> str:
    zone, relative = normalize_workspace_path(path, writable=writable)
    if not relative:
        return f"/workspace/{zone}"
    return f"/workspace/{zone}/{relative}"


def validate_command(command: tuple[str, ...]) -> None:
    if not command:
        raise SandboxCommandError("SANDBOX_COMMAND_REQUIRED")
    executable = PurePosixPath(command[0]).name.lower()
    if executable in {"docker", "podman", "nerdctl", "kubectl", "nsenter"}:
        raise SandboxCommandError("SANDBOX_CONTROL_PLANE_COMMAND_FORBIDDEN")
    for arg in command:
        lowered = arg.lower()
        if any(fragment in lowered for fragment in _FORBIDDEN_ARG_FRAGMENTS):
            raise SandboxCommandError("SANDBOX_CONTROL_PATH_FORBIDDEN")


def redact_command(command: tuple[str, ...]) -> tuple[str, ...]:
    output: list[str] = []
    redact_next = False
    for arg in command:
        if redact_next:
            output.append("<redacted>")
            redact_next = False
            continue
        key, separator, _ = arg.partition("=")
        if separator and _SECRET_KEY_RE.search(key):
            output.append(f"{key}=<redacted>")
            continue
        if _SECRET_KEY_RE.search(arg) and arg.startswith("--") and "=" not in arg:
            output.append(arg)
            redact_next = True
            continue
        output.append(arg)
    return tuple(output)


def redact_text(value: str) -> str:
    return _TEXT_SECRET_RE.sub(lambda match: f"{match.group(1)}<redacted>", value)


def safe_filename(value: str) -> str:
    name = PurePosixPath(value.replace("\\", "/")).name.strip()
    name = "".join(char for char in name if 32 <= ord(char) < 127)
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    if not name:
        return "asset.bin"
    return name[:180]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sniff_mime(path: Path) -> str:
    with path.open("rb") as handle:
        header = handle.read(64)
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith(b"%PDF-"):
        return "application/pdf"
    if header.startswith(b"PK\x03\x04"):
        return "application/zip"
    if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "image/webp"
    if len(header) >= 12 and header[4:8] == b"ftyp":
        return "video/mp4"
    guessed, _ = mimetypes.guess_type(path.name)
    if guessed and (guessed.startswith("text/") or guessed == "application/json"):
        return guessed
    if _looks_like_text(path):
        return "text/plain"
    return "application/octet-stream"


def extract_zip_safely(
    archive: Path,
    destination: Path,
    *,
    max_files: int = 1000,
    max_uncompressed_bytes: int = 256 * 1024 * 1024,
) -> tuple[Path, ...]:
    destination.mkdir(parents=True, exist_ok=True)
    destination_root = destination.resolve()
    extracted: list[Path] = []
    total = 0
    with zipfile.ZipFile(archive) as bundle:
        infos = bundle.infolist()
        if len(infos) > max_files:
            raise UnsafeArchiveError("SANDBOX_ARCHIVE_TOO_MANY_FILES")
        for info in infos:
            member = PurePosixPath(info.filename)
            if member.is_absolute() or any(part in {"", ".", ".."} for part in member.parts):
                raise UnsafeArchiveError("SANDBOX_ARCHIVE_PATH_TRAVERSAL")
            mode = (info.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK:
                raise UnsafeArchiveError("SANDBOX_ARCHIVE_SYMLINK_FORBIDDEN")
            total += info.file_size
            if total > max_uncompressed_bytes:
                raise UnsafeArchiveError("SANDBOX_ARCHIVE_TOO_LARGE")
            target = (destination / Path(*member.parts)).resolve()
            if target != destination_root and destination_root not in target.parents:
                raise UnsafeArchiveError("SANDBOX_ARCHIVE_PATH_ESCAPE")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(info) as source, target.open("wb") as sink:
                shutil.copyfileobj(source, sink, length=1024 * 1024)
            extracted.append(target)
    return tuple(extracted)


def private_or_special_host(host: str) -> bool:
    normalized = host.strip().lower().rstrip(".")
    if not normalized:
        return True
    blocked = {
        "localhost",
        "host.docker.internal",
        "metadata.google.internal",
        "metadata.aws.internal",
    }
    if normalized in blocked or normalized.endswith(".internal") or normalized.endswith(".local"):
        return True
    if normalized.startswith("127.") or normalized.startswith("169.254."):
        return True
    if normalized.startswith("10.") or normalized.startswith("192.168."):
        return True
    if normalized.startswith("172."):
        try:
            second = int(normalized.split(".", 2)[1])
        except (ValueError, IndexError):
            return True
        if 16 <= second <= 31:
            return True
    return normalized in {"0.0.0.0", "::", "::1"}


def validate_allowlist(hosts: Iterable[str]) -> tuple[str, ...]:
    clean: list[str] = []
    for host in hosts:
        value = host.strip().lower().rstrip(".")
        if private_or_special_host(value):
            raise ValueError("SANDBOX_ALLOWLIST_PRIVATE_HOST_FORBIDDEN")
        if not re.fullmatch(r"[a-z0-9.-]{1,253}", value):
            raise ValueError("SANDBOX_ALLOWLIST_HOST_INVALID")
        clean.append(value)
    return tuple(dict.fromkeys(clean))


def _looks_like_text(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            sample = handle.read(4096)
        sample.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return b"\x00" not in sample
