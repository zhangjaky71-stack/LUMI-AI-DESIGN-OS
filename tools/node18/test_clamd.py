from __future__ import annotations

import os
import tempfile
from pathlib import Path

from lumi_api.assets.clamd import ClamdFileScanner
from lumi_api.assets.models import ScanStatus

HOST = os.environ.get("LUMI_CLAMD_HOST", "127.0.0.1")
PORT = int(os.environ.get("LUMI_CLAMD_PORT", "3310"))
EICAR = (
    b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!"
    b"$H+H*"
)


def scan_bytes(scanner: ClamdFileScanner, payload: bytes):
    with tempfile.NamedTemporaryFile() as handle:
        handle.write(payload)
        handle.flush()
        return scanner.scan(Path(handle.name))


def main() -> None:
    scanner = ClamdFileScanner(host=HOST, port=PORT, timeout_seconds=30)
    clean = scan_bytes(scanner, b"LUMI NODE-18 clean fixture")
    assert clean.status is ScanStatus.CLEAN, clean
    eicar = scan_bytes(scanner, EICAR)
    assert eicar.status is ScanStatus.INFECTED, eicar
    print("NODE18_CLAMD_PASS")


if __name__ == "__main__":
    main()
