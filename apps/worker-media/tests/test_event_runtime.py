from datetime import UTC, datetime
from uuid import uuid4

import pytest

from lumi_worker_media.event_runtime import (
    EventValidationError,
    OutboxRecord,
    validate_event_envelope,
)


def test_outbox_record_compiles_to_node12_envelope_shape() -> None:
    event_id = uuid4()
    organization_id = uuid4()
    aggregate_id = uuid4()
    record = OutboxRecord(
        event_id=event_id,
        organization_id=organization_id,
        event_name="asset.ready",
        aggregate_type="asset",
        aggregate_id=aggregate_id,
        schema_version=1,
        payload={"asset_id": str(aggregate_id)},
        created_at=datetime.now(UTC),
    )
    envelope = record.envelope()
    validate_event_envelope(envelope)
    assert envelope["id"] == str(event_id)
    assert envelope["type"] == "lumi.asset.ready"
    assert envelope["partitionkey"] == str(aggregate_id)


def test_invalid_envelope_is_permanent_validation_error() -> None:
    with pytest.raises(EventValidationError, match="EVENT_REQUIRED"):
        validate_event_envelope({"id": str(uuid4())})
