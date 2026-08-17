from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from lumi_image_edit import (
    EditProvenance,
    EditValidationReport,
    GatewayEditResult,
)
from lumi_api.persistence.models_image_edit import (
    ImageEditAuditModel,
    ImageEditCostProjectionModel,
)


def _json(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, dict):
        return {str(key): _json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json(item) for item in value]
    return value


class PostgresImageEditAudit:
    def __init__(self, session: Session, organization_id: UUID) -> None:
        self.session = session
        self.organization_id = organization_id

    async def record(
        self,
        *,
        provenance: EditProvenance,
        validation: EditValidationReport,
    ) -> None:
        edit_id = UUID(provenance.edit_id)
        provenance_json = _json(asdict(provenance))
        validation_json = _json(asdict(validation))
        row = self.session.get(ImageEditAuditModel, edit_id)
        if row is None:
            self.session.add(
                ImageEditAuditModel(
                    edit_id=edit_id,
                    organization_id=self.organization_id,
                    snapshot_id=provenance.snapshot_id,
                    provenance_json=provenance_json,
                    validation_json=validation_json,
                )
            )
        elif row.snapshot_id != provenance.snapshot_id:
            raise ValueError("IMAGE_EDIT_AUDIT_IMMUTABLE_CONFLICT")
        self.session.commit()


class PostgresImageEditCostProjection:
    """Audit projection only; NODE-27 through NODE-22 owns monetary settlement."""

    def __init__(self, session: Session) -> None:
        self.session = session

    async def record(
        self,
        *,
        edit_id: str,
        operation_id: str,
        result: GatewayEditResult,
    ) -> None:
        edit_uuid = UUID(edit_id)
        row = self.session.get(ImageEditCostProjectionModel, edit_uuid)
        values = {
            "operation_id": UUID(operation_id),
            "provider": result.provider,
            "model": result.model,
            "provider_request_id": result.provider_request_id,
            "amount": result.cost_usd,
            "confidence": result.cost_confidence,
            "pricing_snapshot_id": result.pricing_snapshot_id,
            "monetary_owner": "NODE27_MODEL_GATEWAY_SETTLEMENT",
            "reconciled_at": datetime.now(UTC),
        }
        if row is None:
            self.session.add(
                ImageEditCostProjectionModel(edit_id=edit_uuid, **values)
            )
        else:
            for key, value in values.items():
                setattr(row, key, value)
        self.session.commit()
