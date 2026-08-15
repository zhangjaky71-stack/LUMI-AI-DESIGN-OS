from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable, Literal

CapabilityState = Literal["READY", "MISSING", "DISABLED"]

# These are product/runtime capabilities, not process boundaries. A capability can
# be implemented in-process today and moved behind a transport later without
# changing the product readiness contract.
LAUNCH_REQUIRED_CAPABILITIES = frozenset(
    {
        "auth",
        "projects",
        "asset_upload",
        "artifact_versions",
        "agent_runs",
        "tasks",
        "generation",
        "approval",
        "billing",
        "collaboration",
        "governance",
        "admin",
    }
)

CORE_DEVELOPMENT_CAPABILITIES = frozenset({"auth", "projects"})


@dataclass(frozen=True, slots=True)
class RuntimeCapability:
    name: str
    state: CapabilityState
    adapter: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)


class RuntimeCapabilityRegistry:
    def __init__(self, *, required: Iterable[str]) -> None:
        self.required = frozenset(required)
        self._items: dict[str, RuntimeCapability] = {}

    def ready(self, name: str, *, adapter: str) -> None:
        self._items[name] = RuntimeCapability(name=name, state="READY", adapter=adapter)

    def missing(self, name: str, *, reason: str) -> None:
        self._items[name] = RuntimeCapability(name=name, state="MISSING", reason=reason)

    def disabled(self, name: str, *, reason: str) -> None:
        self._items[name] = RuntimeCapability(name=name, state="DISABLED", reason=reason)

    def get(self, name: str) -> RuntimeCapability:
        return self._items.get(
            name,
            RuntimeCapability(
                name=name,
                state="MISSING",
                reason="No runtime adapter has been registered for this capability.",
            ),
        )

    @property
    def missing_required(self) -> tuple[str, ...]:
        return tuple(sorted(name for name in self.required if self.get(name).state != "READY"))

    @property
    def ready_for_release(self) -> bool:
        return not self.missing_required

    def snapshot(self) -> dict[str, object]:
        names = sorted(set(self._items) | set(self.required))
        return {
            "ready": self.ready_for_release,
            "required": sorted(self.required),
            "missing_required": list(self.missing_required),
            "capabilities": [self.get(name).to_dict() for name in names],
        }


def required_capabilities_for_environment(environment: str) -> frozenset[str]:
    # Staging is intentionally production-like. Do not permit a reduced Staging
    # capability set to generate a false NODE-71 release acceptance.
    if environment in {"staging", "production"}:
        return LAUNCH_REQUIRED_CAPABILITIES
    return CORE_DEVELOPMENT_CAPABILITIES
