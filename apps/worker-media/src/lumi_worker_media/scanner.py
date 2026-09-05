from __future__ import annotations

import asyncio

from lumi_asset_storage.models import ScanStatus


class CommandFileScanner:
    def __init__(self, command: str = "clamdscan") -> None:
        self.command = command

    async def scan_path(self, path: str) -> ScanStatus:
        try:
            process = await asyncio.create_subprocess_exec(
                self.command,
                "--no-summary",
                path,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except FileNotFoundError:
            return "SCAN_UNAVAILABLE"
        return_code = await process.wait()
        if return_code == 0:
            return "CLEAN"
        if return_code == 1:
            return "INFECTED"
        return "ERROR"
