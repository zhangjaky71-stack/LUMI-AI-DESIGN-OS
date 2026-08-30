from __future__ import annotations

import runpy
from pathlib import Path

# Temporary release-closure compatibility entrypoint for the one-shot NODE-37 repair.
# The canonical validator remains validate_skill_registry_contract.py.
runpy.run_path(
    str(Path(__file__).with_name("validate_skill_registry_contract.py")),
    run_name="__main__",
)
