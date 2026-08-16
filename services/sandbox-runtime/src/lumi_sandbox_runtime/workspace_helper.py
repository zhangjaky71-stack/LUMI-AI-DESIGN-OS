from __future__ import annotations

import argparse
import base64
import hashlib
import json
import mimetypes
import os
import stat
from pathlib import PurePosixPath

WORKSPACE = "/workspace"
_ALLOWED_ROOTS = {"input", "work", "output"}
_WRITE_ROOTS = {"work", "output"}


class UnsafePath(ValueError):
    pass


def _parts(path: str) -> tuple[str, ...]:
    pure = PurePosixPath(path)
    if pure.is_absolute():
        try:
            pure = pure.relative_to(WORKSPACE)
        except ValueError as exc:
            raise UnsafePath("path outside workspace") from exc
    parts = pure.parts
    if not parts or parts[0] not in _ALLOWED_ROOTS:
        raise UnsafePath("path must start with input/work/output")
    if any(part in {"", ".", ".."} for part in parts):
        raise UnsafePath("path traversal forbidden")
    return parts


def _open_parent(parts: tuple[str, ...], *, write: bool) -> tuple[int, str]:
    if write and parts[0] not in _WRITE_ROOTS:
        raise UnsafePath("input is read-only")
    root_fd = os.open(WORKSPACE, os.O_RDONLY | os.O_DIRECTORY)
    current = root_fd
    try:
        for component in parts[:-1]:
            next_fd = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=current,
            )
            if current != root_fd:
                os.close(current)
            current = next_fd
        return current, parts[-1]
    except Exception:
        if current != root_fd:
            os.close(current)
        os.close(root_fd)
        raise


def read_bytes(path: str, max_bytes: int) -> bytes:
    parts = _parts(path)
    parent_fd, name = _open_parent(parts, write=False)
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise UnsafePath("only regular files may be read")
            if info.st_size > max_bytes:
                raise UnsafePath("file exceeds read limit")
            return os.read(fd, max_bytes + 1)
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)


def write_bytes(path: str, payload: bytes, max_bytes: int) -> None:
    if len(payload) > max_bytes:
        raise UnsafePath("write exceeds file limit")
    parts = _parts(path)
    parent_fd, name = _open_parent(parts, write=True)
    try:
        fd = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW,
            0o600,
            dir_fd=parent_fd,
        )
        try:
            view = memoryview(payload)
            while view:
                written = os.write(fd, view)
                view = view[written:]
        finally:
            os.close(fd)
    finally:
        os.close(parent_fd)


def list_entries(path: str) -> list[dict[str, object]]:
    parts = _parts(path)
    root_fd = os.open(WORKSPACE, os.O_RDONLY | os.O_DIRECTORY)
    current = root_fd
    try:
        for component in parts:
            next_fd = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=current,
            )
            if current != root_fd:
                os.close(current)
            current = next_fd
        entries: list[dict[str, object]] = []
        base = "/workspace/" + "/".join(parts)
        for name in sorted(os.listdir(current)):
            info = os.stat(name, dir_fd=current, follow_symlinks=False)
            if stat.S_ISLNK(info.st_mode):
                continue
            entries.append(
                {
                    "path": f"{base}/{name}",
                    "size": int(info.st_size),
                    "is_directory": stat.S_ISDIR(info.st_mode),
                }
            )
        return entries
    finally:
        if current != root_fd:
            os.close(current)
        os.close(root_fd)


def inspect_file(path: str, max_bytes: int) -> dict[str, object]:
    payload = read_bytes(path, max_bytes)
    detected = _detect_mime(path, payload)
    return {
        "size": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "detected_mime": detected,
        "content_b64": base64.b64encode(payload).decode("ascii"),
    }


def _detect_mime(path: str, payload: bytes) -> str:
    signatures = (
        (b"\x89PNG\r\n\x1a\n", "image/png"),
        (b"\xff\xd8\xff", "image/jpeg"),
        (b"GIF87a", "image/gif"),
        (b"GIF89a", "image/gif"),
        (b"%PDF-", "application/pdf"),
        (b"PK\x03\x04", "application/zip"),
    )
    for signature, mime in signatures:
        if payload.startswith(signature):
            return mime
    guessed, _ = mimetypes.guess_type(path)
    return guessed or "application/octet-stream"


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    read = sub.add_parser("read")
    read.add_argument("path")
    read.add_argument("--max-bytes", type=int, required=True)
    write = sub.add_parser("write")
    write.add_argument("path")
    write.add_argument("--max-bytes", type=int, required=True)
    listing = sub.add_parser("list")
    listing.add_argument("path")
    inspect = sub.add_parser("inspect")
    inspect.add_argument("path")
    inspect.add_argument("--max-bytes", type=int, required=True)
    args = parser.parse_args()
    if args.action == "read":
        payload = read_bytes(args.path, args.max_bytes)
        print(base64.b64encode(payload).decode("ascii"))
    elif args.action == "write":
        payload = base64.b64decode(input().encode("ascii"), validate=True)
        write_bytes(args.path, payload, args.max_bytes)
        print("ok")
    elif args.action == "list":
        print(json.dumps(list_entries(args.path), separators=(",", ":")))
    elif args.action == "inspect":
        print(json.dumps(inspect_file(args.path, args.max_bytes), separators=(",", ":")))


if __name__ == "__main__":
    main()
