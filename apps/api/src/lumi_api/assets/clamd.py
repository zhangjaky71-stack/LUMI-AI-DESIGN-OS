from __future__ import annotations

import socket
import struct
from pathlib import Path

from .models import FileScanResult, ScanStatus


class ClamdFileScanner:
    """Streams files to clamd using the documented INSTREAM protocol."""

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 3310,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout_seconds = timeout_seconds

    def scan(self, path: Path) -> FileScanResult:
        try:
            with socket.create_connection(
                (self.host, self.port), timeout=self.timeout_seconds
            ) as connection:
                connection.settimeout(self.timeout_seconds)
                connection.sendall(b"zINSTREAM\x00")
                with path.open("rb") as handle:
                    while True:
                        chunk = handle.read(1024 * 1024)
                        if not chunk:
                            break
                        connection.sendall(struct.pack(">I", len(chunk)))
                        connection.sendall(chunk)
                connection.sendall(struct.pack(">I", 0))
                response = bytearray()
                while True:
                    block = connection.recv(4096)
                    if not block:
                        break
                    response.extend(block)
                    if b"\x00" in block or b"\n" in block:
                        break
        except (OSError, TimeoutError) as exc:
            return FileScanResult(
                status=ScanStatus.UNAVAILABLE,
                engine="clamd",
                detail=type(exc).__name__,
            )
        text = bytes(response).rstrip(b"\x00\r\n").decode("utf-8", errors="replace")
        if text.endswith(" OK"):
            return FileScanResult(status=ScanStatus.CLEAN, engine="clamd")
        if text.endswith(" FOUND"):
            signature = text.rsplit(":", 1)[-1].removesuffix("FOUND").strip() or None
            return FileScanResult(
                status=ScanStatus.INFECTED,
                engine="clamd",
                signature=signature,
                detail="malware signature detected",
            )
        return FileScanResult(
            status=ScanStatus.ERROR,
            engine="clamd",
            detail=text[:1_000] or "empty clamd response",
        )
