from __future__ import annotations

import base64
import binascii
import hashlib
from pathlib import Path


def sha256_hex_to_base64(value: str) -> str:
    normalized = value.strip().lower()
    if len(normalized) != 64:
        raise ValueError("SHA256_HEX_INVALID")
    try:
        raw = bytes.fromhex(normalized)
    except ValueError as exc:
        raise ValueError("SHA256_HEX_INVALID") from exc
    return base64.b64encode(raw).decode("ascii")


def sha256_base64_to_hex(value: str) -> str:
    try:
        raw = base64.b64decode(value.strip(), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("SHA256_BASE64_INVALID") from exc
    if len(raw) != 32:
        raise ValueError("SHA256_BASE64_INVALID")
    return raw.hex()


def sha256_path(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
