from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECOVERY = ROOT / "apps" / "api" / "src" / "lumi_api" / "recovery"
POLICY = RECOVERY / "policy.py"
SERVICE = RECOVERY / "service.py"
REPOSITORY = RECOVERY / "repository.py"
MODEL = RECOVERY / "model.py"


def parse(path: Path) -> str:
    source = path.read_text(encoding="utf-8")
    ast.parse(source, filename=str(path))
    return source


def main() -> None:
    for path in (POLICY, SERVICE, REPOSITORY, MODEL):
        assert path.exists(), path

    policy = parse(POLICY)
    service = parse(SERVICE)
    repository = parse(REPOSITORY)
    model = parse(MODEL)

    # PostgreSQL/control-plane truth drives the planner. Rabbit/Redis must never be
    # imported as business truth by the recovery scanner.
    assert "models_queue_runtime" in repository
    assert "models_execution" in repository
    assert "models_control_plane" in repository
    assert "rabbit" not in repository.casefold()
    assert "redis" not in repository.casefold()

    # Paid/external ambiguity is fail-closed and existing native provider identity
    # is preserved for reconciliation rather than replaced by a new request.
    assert "PAID_SIDE_EFFECT_WITHOUT_NATIVE_REQUEST_ID" in policy
    assert "RUNNING_PAID_SIDE_EFFECT_WITHOUT_PROVIDER_ID" in policy
    assert "RECONCILE_EXTERNAL" in policy
    assert "preserve_provider_request_id" in policy
    assert "submit" not in service.casefold()
    assert "new_provider" not in service.casefold()

    # Agent recovery requires exact graph compatibility and preserves human waits.
    assert "AGENT_GRAPH_DEFINITION_HASH_MISMATCH" in policy
    assert "AGENT_WAITING_FOR_USER_MUST_BE_PRESERVED" in policy
    assert "checkpoint_id" in policy

    # Artifact recovery uses internal immutable object identity, not signed URLs.
    assert "RECOVERY_OBJECT_REF_MUST_BE_INTERNAL" in model
    assert "expected_checksum_sha256" in model
    assert "expected_size_bytes" in model

    # Targets are not evidence: no measurement means target_met must remain false.
    assert "has_measured_evidence" in model
    assert "if not self.has_measured_evidence" in model

    print("NODE68_RECOVERY_VALIDATION_PASS")


if __name__ == "__main__":
    main()
