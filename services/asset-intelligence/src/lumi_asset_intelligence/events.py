from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class AssetReadyEvent:
    event_id: str
    organization_id: str
    asset_id: str
    asset_version: str
    occurred_at: str


@dataclass(frozen=True)
class AnalysisJob:
    job_id: str
    organization_id: str
    asset_id: str
    asset_version: str
    index_id: str
    state: Literal["PENDING", "RUNNING", "SUCCEEDED", "FAILED"]
    source_event_id: str


def plan_analysis_job(event: AssetReadyEvent, index_id: str) -> AnalysisJob:
    payload = {
        "asset_id": event.asset_id,
        "asset_version": event.asset_version,
        "index_id": index_id,
        "organization_id": event.organization_id,
        "source_event_id": event.event_id,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return AnalysisJob(
        job_id=f"asset-analysis-job:{hashlib.sha256(encoded).hexdigest()}",
        organization_id=event.organization_id,
        asset_id=event.asset_id,
        asset_version=event.asset_version,
        index_id=index_id,
        state="PENDING",
        source_event_id=event.event_id,
    )
