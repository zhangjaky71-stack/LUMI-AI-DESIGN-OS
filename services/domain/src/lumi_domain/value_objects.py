from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Mapping

from .ids import DomainId

_CURRENCY = re.compile(r"^[A-Z]{3}$")
_MIME = re.compile(r"^[a-z0-9!#$&^_.+-]+/[a-z0-9!#$&^_.+-]+$")
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_HEX_COLOR = re.compile(r"^#[0-9A-F]{6}([0-9A-F]{2})?$")


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        if isinstance(self.amount, float):
            raise TypeError("Money.amount must use Decimal, never float")
        if not isinstance(self.amount, Decimal):
            raise TypeError("Money.amount must be Decimal")
        normalized = self.currency.upper()
        if not _CURRENCY.fullmatch(normalized):
            raise ValueError("currency must be an ISO-like 3-letter code")
        object.__setattr__(self, "currency", normalized)


@dataclass(frozen=True, slots=True)
class Dimensions:
    width: Decimal
    height: Decimal
    unit: str = "px"

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("dimensions must be positive")
        if not self.unit.strip():
            raise ValueError("dimension unit is required")


@dataclass(frozen=True, slots=True)
class Point:
    x: Decimal
    y: Decimal


@dataclass(frozen=True, slots=True)
class Rect:
    x: Decimal
    y: Decimal
    width: Decimal
    height: Decimal

    def __post_init__(self) -> None:
        if self.width < 0 or self.height < 0:
            raise ValueError("rect width and height cannot be negative")


@dataclass(frozen=True, slots=True)
class Transform:
    x: Decimal = Decimal("0")
    y: Decimal = Decimal("0")
    scale_x: Decimal = Decimal("1")
    scale_y: Decimal = Decimal("1")
    rotation_deg: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        if self.scale_x == 0 or self.scale_y == 0:
            raise ValueError("transform scale cannot be zero")


@dataclass(frozen=True, slots=True)
class Color:
    value: str

    def __post_init__(self) -> None:
        normalized = self.value.upper()
        if not _HEX_COLOR.fullmatch(normalized):
            raise ValueError("color must be #RRGGBB or #RRGGBBAA")
        object.__setattr__(self, "value", normalized)


@dataclass(frozen=True, slots=True)
class MimeType:
    value: str

    def __post_init__(self) -> None:
        normalized = self.value.lower().strip()
        if not _MIME.fullmatch(normalized):
            raise ValueError("invalid MIME type")
        object.__setattr__(self, "value", normalized)


@dataclass(frozen=True, slots=True)
class StorageRef:
    bucket: str
    key: str
    checksum: str
    owner_organization_id: DomainId

    def __post_init__(self) -> None:
        if not self.bucket.strip() or not self.key.strip():
            raise ValueError("storage bucket and key are required")
        normalized = self.checksum.lower()
        if not _SHA256.fullmatch(normalized):
            raise ValueError("storage checksum must be sha256:<64 lowercase hex chars>")
        object.__setattr__(self, "checksum", normalized)


@dataclass(frozen=True, slots=True)
class ProviderRef:
    provider: str
    native_id: str

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.native_id.strip():
            raise ValueError("provider and native_id are required")


@dataclass(frozen=True, slots=True)
class ModelRef:
    provider: str
    model: str
    registry_version: str


@dataclass(frozen=True, slots=True)
class VersionRef:
    artifact_id: DomainId
    version_id: DomainId


@dataclass(frozen=True, slots=True)
class Usage:
    units: Mapping[str, Decimal]

    def __post_init__(self) -> None:
        if any(value < 0 for value in self.units.values()):
            raise ValueError("usage cannot be negative")


@dataclass(frozen=True, slots=True)
class Budget:
    money: Money | None = None
    max_model_calls: int | None = None
    max_tool_calls: int | None = None

    def __post_init__(self) -> None:
        for value in (self.max_model_calls, self.max_tool_calls):
            if value is not None and value < 0:
                raise ValueError("budget call limits cannot be negative")


class RightsScope(StrEnum):
    INTERNAL = "internal"
    COMMERCIAL = "commercial"
    PUBLIC = "public"
    RESTRICTED = "restricted"


@dataclass(frozen=True, slots=True)
class RightsPolicy:
    scope: RightsScope
    source: str
    attribution_required: bool = False
    expires_at_iso: str | None = None


@dataclass(frozen=True, slots=True)
class OperationIdentity:
    operation_id: DomainId
    idempotency_key: str

    def __post_init__(self) -> None:
        if not self.idempotency_key.strip():
            raise ValueError("idempotency_key is required")


class ProviderErrorCode(StrEnum):
    RATE_LIMITED = "rate_limited"
    AUTHENTICATION = "authentication"
    INVALID_REQUEST = "invalid_request"
    SAFETY_BLOCK = "safety_block"
    TIMEOUT = "timeout"
    UNAVAILABLE = "unavailable"
    QUOTA_EXCEEDED = "quota_exceeded"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class NormalizedProviderError:
    code: ProviderErrorCode
    retryable: bool
    provider: str
    provider_code: str | None = None
    safe_message: str | None = None
