from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any, Mapping
from uuid import UUID

_EVENT_TYPE = re.compile(r"^lumi\.[a-z0-9_]+\.[a-z0-9_]+$")
_SOURCE = re.compile(r"^lumi://[a-z0-9][a-z0-9._/-]*$")

JsonScalar = str | int | float | bool | None
FrozenJson = JsonScalar | tuple["FrozenJson", ...] | Mapping[str, "FrozenJson"]


def _freeze(value: Any) -> FrozenJson:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    raise TypeError(f"event data is not JSON-compatible: {type(value).__name__}")


def _thaw(value: FrozenJson) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _parse_time(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("event time must be timezone-aware")
    return parsed.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    id: UUID
    source: str
    type: str
    subject: str
    organization_id: UUID
    correlation_id: UUID
    partition_key: str
    schema_version: int
    data_schema: str
    data: Mapping[str, FrozenJson]
    time: datetime
    causation_id: UUID | None = None
    trace_id: str | None = None
    spec_version: str = "1.0"
    data_content_type: str = "application/json"

    def __post_init__(self) -> None:
        if self.spec_version != "1.0":
            raise ValueError("event specversion must be 1.0")
        if self.data_content_type != "application/json":
            raise ValueError("event datacontenttype must be application/json")
        if not _SOURCE.fullmatch(self.source):
            raise ValueError("event source must be a lumi:// URI-like identifier")
        if not _EVENT_TYPE.fullmatch(self.type):
            raise ValueError("invalid LUMI event type")
        if not self.subject or len(self.subject) > 512:
            raise ValueError("event subject must contain 1..512 characters")
        if not self.partition_key or len(self.partition_key) > 255:
            raise ValueError("event partitionkey must contain 1..255 characters")
        if self.schema_version < 1:
            raise ValueError("event schema version must be >= 1")
        expected_suffix = f":{self.schema_version}"
        if not self.data_schema.startswith("urn:lumi:event:") or not self.data_schema.endswith(
            expected_suffix
        ):
            raise ValueError("dataschema must identify the matching LUMI schema version")
        if self.trace_id is not None and len(self.trace_id) > 128:
            raise ValueError("traceid must be <= 128 characters")
        object.__setattr__(self, "time", _parse_time(self.time))
        object.__setattr__(self, "data", _freeze(dict(self.data)))

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "specversion": self.spec_version,
            "id": str(self.id),
            "source": self.source,
            "type": self.type,
            "subject": self.subject,
            "time": self.time.isoformat().replace("+00:00", "Z"),
            "datacontenttype": self.data_content_type,
            "dataschema": self.data_schema,
            "organizationid": str(self.organization_id),
            "correlationid": str(self.correlation_id),
            "partitionkey": self.partition_key,
            "schemaversion": self.schema_version,
            "data": _thaw(self.data),
        }
        if self.causation_id is not None:
            payload["causationid"] = str(self.causation_id)
        if self.trace_id is not None:
            payload["traceid"] = self.trace_id
        return payload

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "EventEnvelope":
        return cls(
            id=UUID(str(value["id"])),
            source=str(value["source"]),
            type=str(value["type"]),
            subject=str(value["subject"]),
            organization_id=UUID(str(value["organizationid"])),
            correlation_id=UUID(str(value["correlationid"])),
            causation_id=(
                UUID(str(value["causationid"])) if value.get("causationid") is not None else None
            ),
            trace_id=str(value["traceid"]) if value.get("traceid") is not None else None,
            partition_key=str(value["partitionkey"]),
            schema_version=int(value["schemaversion"]),
            data_schema=str(value["dataschema"]),
            data=dict(value["data"]),
            time=_parse_time(str(value["time"])),
            spec_version=str(value["specversion"]),
            data_content_type=str(value["datacontenttype"]),
        )
