from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_model_provider_matrix_contract_is_complete() -> None:
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "scripts/validate_model_provider_matrix.py"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "PASS providers=5 models=28 route_eligible=27" in result.stdout
    assert "stable:23, preview:4, deprecated:1" in result.stdout
    assert "PASS official_sources=30 routes=15" in result.stdout
    assert "PASS benchmark_status=NOT_MEASURED:28" in result.stdout
    assert "PASS no provider winner selected before LUMI live benchmark" in result.stdout
