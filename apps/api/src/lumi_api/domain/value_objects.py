from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping
from uuid import UUID

from .errors import InvariantViolation

_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_MIME_RE = re.compile(r"^[a-z0-9!#$&^_.+-]+/[a-z0-9!#$&^_.+-]+$")
_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _finite(value: float, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise InvariantViolation(f"{name} must be finite")
    return result


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            raise TypeError("Money.amount must be Decimal")
        if not self.amount.is_finite():
            raise InvariantViolation("Money.amount must be finite")
        normalized = self.currency.upper()
        if not _CURRENCY_RE.fullmatch(normalized):
            raise InvariantViolation("Money.currency must be a 3-letter ISO-style code")
        object.__setattr__(self, "currency", normalized)

    def __add__(self, other: Money) -> Money:
        if self.currency != other.currency:
            raise InvariantViolation("cannot add Money values with different currencies")
        return Money(self.amount + other.amount, self.currency)


class DimensionUnit(StrEnum):
    PX = "px"
    MM = "mm"
    CM = "cm"
    IN = "in"
    PT = "pt"


@dataclass(frozen=True, slots=True)
class Dimensions:
    width: float
    height: float
    unit: DimensionUnit = DimensionUnit.PX

    def __post_init__(self) -> None:
        width = _finite(self.width, "width")
        height = _finite(self.height, "height")
        if width <= 0 or height <= 0:
            raise InvariantViolation("Dimensions must be positive")
        object.__setattr__(self, "width", width)
        object.__setattr__(self, "height", height)


@dataclass(frozen=True, slots=True)
class Point:
    x: float
    y: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", _finite(self.x, "x"))
        object.__setattr__(self, "y", _finite(self.y, "y"))


@dataclass(frozen=True, slots=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        x = _finite(self.x, "x")
        y = _finite(self.y, "y")
        width = _finite(self.width, "width")
        height = _finite(self.height, "height")
        if width < 0 or height < 0:
            raise InvariantViolation("Rect width/height cannot be negative")
        object.__setattr__(self, "x", x)
        object.__setattr__(self, "y", y)
        object.__setattr__(self, "width", width)
        object.__setattr__(self, "height", height)


@dataclass(frozen=True, slots=True)
class Transform:
    translation: Point = Point(0, 0)
    scale_x: float = 1.0
    scale_y: float = 1.0
    rotation_degrees: float = 0.0

    def __post_init__(self) -> None:
        scale_x = _finite(self.scale_x, "scale_x")
        scale_y = _finite(self.scale_y, "scale_y")
        rotation = _finite(self.rotation_degrees, "rotation_degrees")
        if scale_x == 0 or scale_y == 0:
            raise InvariantViolation("Transform scale cannot be zero")
        object.__setattr__(self, "scale_x", scale_x)
        object.__setattr__(self, "scale_y", scale_y)
        object.__setattr__(self, "rotation_degrees", rotation)


@dataclass(frozen=True, slots=True)
class Color:
    value: str

    def __post_init__(self) -> None:
        if not _HEX_RE.fullmatch(self.value):
            raise InvariantViolation("Color must be #RRGGBB or #RRGGBBAA")
        object.__setattr__(self, "value", self.value.upper())


@dataclass(frozen=True, slots=True)
class MimeType:
    value: str

    def __post_init__(self) -> None:
        normalized = self.value.lower().strip()
        if not _MIME_RE.fullmatch(normalized):
            raise InvariantViolation("invalid MIME type")
        object.__setattr__(self, "value", normalized)


@dataclass(frozen=True, slots=True)
class StorageRef:
    bucket: str
    key: str
    checksum_sha256: str
    owner_organization_id: UUID

    def __post_init__(self) -> None:
        if not self.bucket.strip() or not self.key.strip():
            raise InvariantViolation("storage bucket/key are required")
        checksum = self.checksum_sha256.lower()
        if not _SHA256_RE.fullmatch(checksum):
            raise InvariantViolation("storage checksum must be lowercase SHA-256 hex")
        object.__setattr__(self, "checksum_sha256", checksum)


@dataclass(frozen=True, slots=True)
class ProviderRef:
    provider: str
    provider_id: str

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.provider_id.strip():
            raise InvariantViolation("provider and provider_id are required")


@dataclass(frozen=True, slots=True)
class ModelRef:
    provider: str
    model: str
    version: str | None = None

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.model.strip():
            raise InvariantViolation("provider and model are required")


@dataclass(frozen=True, slots=True)
class VersionRef:
    artifact_id: UUID
    version_id: UUID


@dataclass(frozen=True, slots=True)
class Usage:
    input_units: Decimal = Decimal("0")
    output_units: Decimal = Decimal("0")
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.input_units < 0 or self.output_units < 0:
            raise InvariantViolation("usage cannot be negative")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class Budget:
    hard_limit: Money
    soft_limit: Money | None = None

    def __post_init__(self) -> None:
        if self.hard_limit.amount < 0:
            raise InvariantViolation("budget hard limit cannot be negative")
        if self.soft_limit is not None:
            if self.soft_limit.currency != self.hard_limit.currency:
                raise InvariantViolation("budget currency mismatch")
            if self.soft_limit.amount < 0 or self.soft_limit.amount > self.hard_limit.amount:
                raise InvariantViolation("soft limit must be within hard limit")


class RightsLevel(StrEnum):
    UNKNOWN = "unknown"
    OWNED = "owned"
    LICENSED = "licensed"
    PUBLIC_DOMAIN = "public_domain"
    RESTRICTED = "restricted"


@dataclass(frozen=True, slots=True)
class RightsPolicy:
    level: RightsLevel
    commercial_use: bool
    attribution_required: bool = False
    source_uri: str | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class OperationIdentity:
    operation_id: UUID
    idempotency_key: str

    def __post_init__(self) -> None:
        if not self.idempotency_key.strip():
            raise InvariantViolation("idempotency_key is required")
