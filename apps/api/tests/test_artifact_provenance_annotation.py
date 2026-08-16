from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from lumi_api.artifacts import (
    ArtifactAnnotationType,
    CreatedByType,
    ProvenanceAnnotation,
)
from lumi_api.domain.ids import new_uuid7


def test_provenance_correction_is_an_append_only_annotation_contract() -> None:
    annotation = ProvenanceAnnotation(
        id=new_uuid7(),
        organization_id=new_uuid7(),
        artifact_version_id=new_uuid7(),
        type=ArtifactAnnotationType.PROVENANCE_CORRECTION,
        actor_type=CreatedByType.USER,
        actor_id="auditor-1",
        reason="Correct provider request reference after audit",
        details=(("old_ref", "unknown"), ("new_ref", "request-123")),
        occurred_at=datetime(2026, 8, 16, 6, 30, tzinfo=UTC),
    )
    assert annotation.type == ArtifactAnnotationType.PROVENANCE_CORRECTION
    assert annotation.details == (("new_ref", "request-123"), ("old_ref", "unknown"))
    with pytest.raises(ValidationError):
        annotation.__setattr__("reason", "rewrite history")
