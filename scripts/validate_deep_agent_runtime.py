from __future__ import annotations

import runpy
from pathlib import Path

# Temporary release-closure compatibility entrypoint for the one-shot NODE-37 repair.
# The canonical validator remains validate_deep_agents_runtime_contract_v2.py.
runpy.run_path(
    str(Path(__file__).with_name("validate_deep_agents_runtime_contract_v2.py")),
    run_name="__main__",
)
