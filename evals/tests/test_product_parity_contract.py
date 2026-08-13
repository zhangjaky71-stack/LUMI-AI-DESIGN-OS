from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_product_parity_contract_is_complete() -> None:
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "scripts/validate_product_parity.py"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "PASS categories=7 capabilities=67" in result.stdout
    assert "PARITY:56" in result.stdout
    assert "SUPERSET:7" in result.stdout
    assert "DEFER:4" in result.stdout
    assert "PASS parity_acceptance_cases=56" in result.stdout
