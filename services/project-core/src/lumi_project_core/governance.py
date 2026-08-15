from __future__ import annotations

import base64
import csv
import io
import json
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from threading import RLock
from typing import Literal, Mapping, Protocol
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

AuditActorType = Literal["USER", "PLATFORM_ADMIN", "AGENT", "SERVICE"]
AuditResult = Literal["SUCCESS", "DENIED", "FAILED"]
RetentionClass = Literal[
    "SECURITY_AUDIT",
    "BILLING",
    "CONTENT",
    "AGENT_TRACE",
    "TEMP_SANDBOX",
    "EXPORT",
    "ANALYTICS",
]
HoldType = Literal["LEGAL", "BILLING"]
HoldAction = Literal["CREATE", "RELEASE"]
HoldScopeType = Literal["USER", "ORGANIZATION", "RESOURCE", "RETENTION_CLASS"]
DeletionStatus = Literal[
    "REQUESTED",
    "BLOCKED_HOLD",
    "DEACTIVATED",
    "DELETING",
    "COMPLETED",
    "FAILED",
]
ErasureMode = Literal["DELETE", "ANONYMIZE", "RETENTION_ONLY"]
ExportFormat = Literal["JSON", "CSV"]
ExportStatus = Literal["PENDING", "RUNNING", "READY", "FAILED", "EXPIRED"]

DEFAULT_RETENTION_DAYS: dict[RetentionClass, int] = {
    "SECURITY_AUDIT": 2555,
    "BILLING": 2555,
    "CONTENT": 365,
    "AGENT_TRACE": 90,
    "TEMP_SANDBOX": 7,
    "EXPORT": 30,
    "ANALYTICS": 400,
}

_SECRET_KEY_FRAGMENTS = (
    "password",
    "authorization",
    "api_key",
    "apikey",
    "session_secret",
    "client_secret",
    "access_token",
    "refresh_token",
    "card_number",
    "cvc",
    "cvv",
    "pan",
)
_HASH_ONLY_KEYS = {
    "prompt",
    "raw_prompt",
    "user_content",
    "message_body",
    "request_body",
    "response_body",
}
_IP_KEYS = {"ip", "ip_address", "remote_ip", "client_ip"}


class GovernanceError(RuntimeError):
    def __init__(self, code: str, status: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


@dataclass(frozen=True, slots=True)
class GovernanceActor:
    actor_id: str
    actor_type: AuditActorType
    organization_id: str | None
    permissions: frozenset[str]
    session_ref: str | None = None
    api_token_ref: str | None = None
    agent_run_id: str | None = None
    task_id: str | None = None
    actor_version: str | None = None
    human_initiator_id: str | None = None

    def __post_init__(self) -> None:
        if not self.actor_id.strip():
            raise GovernanceError("GOVERNANCE_ACTOR_INVALID", 401)
        if self.actor_type == "AGENT" and not all(
            (self.actor_version, self.agent_run_id, self.task_id, self.human_initiator_id)
        ):
            raise GovernanceError("GOVERNANCE_AGENT_IDENTITY_INCOMPLETE", 400)


@dataclass(frozen=True, slots=True)
class AuditChangeSummary:
    changed_fields: tuple[str, ...] = ()
    version_refs: tuple[str, ...] = ()
    semantic_diff_ref: str | None = None

    def __post_init__(self) -> None:
        if len(self.changed_fields) > 100 or len(self.version_refs) > 100:
            raise GovernanceError("AUDIT_CHANGE_SUMMARY_TOO_LARGE")
        if any(len(value) > 240 for value in self.changed_fields + self.version_refs):
            raise GovernanceError("AUDIT_CHANGE_SUMMARY_INVALID")


@dataclass(frozen=True, slots=True)
class AuditEvent:
    event_id: str
    organization_id: str | None
    actor_type: AuditActorType
    actor_id: str
    actor_version: str | None
    session_ref: str | None
    api_token_ref: str | None
    agent_run_ref: str | None
    task_ref: str | None
    human_initiator_id: str | None
    action: str
    resource_type: str
    resource_id: str
    resource_version: str | None
    result: AuditResult
    reason_code: str
    request_id: str | None
    trace_id: str | None
    security_metadata: tuple[tuple[str, str], ...]
    change_summary: AuditChangeSummary
    evidence_ref: str | None
    retention_class: RetentionClass
    retention_policy_version: int
    correction_of_event_id: str | None
    occurred_at: str
    prev_hash: str | None
    event_hash: str


@dataclass(frozen=True, slots=True)
class AuditQuery:
    organization_id: str | None = None
    actor_id: str | None = None
    action: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    result: AuditResult | None = None
    trace_id: str | None = None
    start_at: str | None = None
    end_at: str | None = None
    cursor: str | None = None
    limit: int = 50

    def __post_init__(self) -> None:
        if self.limit < 1 or self.limit > 200:
            raise GovernanceError("AUDIT_PAGE_LIMIT_INVALID")


@dataclass(frozen=True, slots=True)
class AuditPage:
    items: tuple[AuditEvent, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    retention_class: RetentionClass
    version: int
    retention_days: int
    created_by: str
    created_at: str
    policy_note: str

    def __post_init__(self) -> None:
        if self.version < 1 or self.retention_days < 1 or self.retention_days > 36500:
            raise GovernanceError("RETENTION_POLICY_INVALID")
        if not self.created_by.strip() or not self.policy_note.strip():
            raise GovernanceError("RETENTION_POLICY_INVALID")


@dataclass(frozen=True, slots=True)
class GovernanceResourceRef:
    resource_type: str
    resource_id: str
    organization_id: str
    retention_class: RetentionClass
    created_at: str
    subject_user_id: str | None = None
    erasure_mode: ErasureMode = "DELETE"
    object_ref: str | None = None
    search_ref: str | None = None


@dataclass(frozen=True, slots=True)
class RetentionCandidate:
    resource: GovernanceResourceRef
    policy_version: int
    eligible_at: str


@dataclass(frozen=True, slots=True)
class LegalHoldEvent:
    hold_event_id: str
    hold_id: str
    hold_type: HoldType
    action: HoldAction
    organization_id: str | None
    scope_type: HoldScopeType
    scope_id: str
    reason_code: str
    ticket_ref: str
    actor_id: str
    occurred_at: str


@dataclass(frozen=True, slots=True)
class ActiveLegalHold:
    hold_id: str
    hold_type: HoldType
    organization_id: str | None
    scope_type: HoldScopeType
    scope_id: str
    reason_code: str
    ticket_ref: str
    created_by: str
    created_at: str


@dataclass(frozen=True, slots=True)
class DeletionEvent:
    deletion_event_id: str
    request_id: str
    subject_user_id: str
    organization_id: str
    status: DeletionStatus
    resource_refs: tuple[str, ...]
    blocked_hold_ids: tuple[str, ...]
    deleted_count: int
    anonymized_count: int
    retained_count: int
    error_code: str | None
    actor_id: str
    occurred_at: str


@dataclass(frozen=True, slots=True)
class DeletionRequestView:
    request_id: str
    subject_user_id: str
    organization_id: str
    status: DeletionStatus
    resource_refs: tuple[str, ...]
    blocked_hold_ids: tuple[str, ...]
    deleted_count: int
    anonymized_count: int
    retained_count: int
    error_code: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class AuditExportJob:
    job_id: str
    organization_id: str | None
    export_format: ExportFormat
    status: ExportStatus
    query: AuditQuery
    created_by: str
    created_at: str
    completed_at: str | None = None
    object_ref: str | None = None
    file_name: str | None = None
    checksum_sha256: str | None = None
    size_bytes: int | None = None
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class StoredAuditExport:
    object_ref: str
    file_name: str
    checksum_sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class AuditDownloadLease:
    job_id: str
    signed_url: str
    expires_at: str


class GovernanceRepository(Protocol):
    def append_audit(self, event: AuditEvent) -> None: ...
    def latest_chain_hash(self, chain_key: str) -> str | None: ...
    def get_audit(self, event_id: str) -> AuditEvent | None: ...
    def search_audit(self, query: AuditQuery) -> AuditPage: ...
    def publish_retention_policy(self, policy: RetentionPolicy) -> None: ...
    def list_retention_policies(self) -> tuple[RetentionPolicy, ...]: ...
    def current_retention_policy(self, retention_class: RetentionClass) -> RetentionPolicy: ...
    def append_hold_event(self, event: LegalHoldEvent) -> None: ...
    def list_hold_events(self) -> tuple[LegalHoldEvent, ...]: ...
    def append_deletion_event(self, event: DeletionEvent) -> None: ...
    def list_deletion_events(self, request_id: str | None = None) -> tuple[DeletionEvent, ...]: ...
    def save_export_job(self, job: AuditExportJob) -> None: ...
    def get_export_job(self, job_id: str) -> AuditExportJob | None: ...
    def list_export_jobs(self) -> tuple[AuditExportJob, ...]: ...


class GovernanceDataPort(Protocol):
    def resources_for_subject(
        self, subject_user_id: str, organization_id: str
    ) -> tuple[GovernanceResourceRef, ...]: ...
    def retention_resources(self, organization_id: str | None) -> tuple[GovernanceResourceRef, ...]: ...
    def deactivate_subject(self, subject_user_id: str, organization_id: str) -> None: ...
    def erase_resource(self, resource: GovernanceResourceRef, mode: ErasureMode) -> None: ...
    def gc_object(self, object_ref: str) -> None: ...
    def remove_search_ref(self, search_ref: str) -> None: ...


class AuditExportStoragePort(Protocol):
    def put(self, job_id: str, export_format: ExportFormat, payload: bytes) -> StoredAuditExport: ...
    def create_download(self, stored: StoredAuditExport, ttl_seconds: int) -> AuditDownloadLease: ...


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat()


def _parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise GovernanceError("GOVERNANCE_TIME_INVALID") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _hash_text(value: str) -> str:
    return f"sha256:{sha256(value.encode('utf-8')).hexdigest()}"


def _safe_url(value: str) -> str:
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.netloc:
        return "[REDACTED_URL]"
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "[REDACTED]" if parsed.query else "", ""))


def sanitize_metadata(metadata: Mapping[str, object] | None) -> tuple[tuple[str, str], ...]:
    if not metadata:
        return ()
    safe: list[tuple[str, str]] = []
    for raw_key, raw_value in sorted(metadata.items(), key=lambda item: item[0]):
        key = str(raw_key)[:120]
        normalized = key.lower().replace("-", "_")
        value = "" if raw_value is None else str(raw_value)
        if any(fragment in normalized for fragment in _SECRET_KEY_FRAGMENTS):
            rendered = "[REDACTED]"
        elif normalized in _HASH_ONLY_KEYS:
            rendered = _hash_text(value)
        elif normalized in _IP_KEYS:
            rendered = _hash_text(value)
        elif "url" in normalized:
            rendered = _safe_url(value)
        else:
            rendered = value[:1000]
        safe.append((key, rendered))
    return tuple(safe)


def _event_payload(event: AuditEvent) -> dict[str, object]:
    value = asdict(event)
    value.pop("event_hash", None)
    return value


def _event_hash(event: AuditEvent) -> str:
    encoded = json.dumps(_event_payload(event), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(encoded.encode("utf-8")).hexdigest()


def _chain_key(organization_id: str | None) -> str:
    return organization_id or "__platform__"


def _encode_cursor(event: AuditEvent) -> str:
    payload = json.dumps([event.occurred_at, event.event_id], separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_cursor(value: str) -> tuple[str, str]:
    try:
        padded = value + "=" * (-len(value) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        if not isinstance(decoded, list) or len(decoded) != 2:
            raise ValueError
        return str(decoded[0]), str(decoded[1])
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GovernanceError("AUDIT_CURSOR_INVALID") from exc


def _resource_ref(resource: GovernanceResourceRef) -> str:
    return f"{resource.resource_type}:{resource.resource_id}"


class GovernanceEngine:
    def __init__(
        self,
        *,
        repository: GovernanceRepository,
        data: GovernanceDataPort,
        export_storage: AuditExportStoragePort,
    ) -> None:
        self._repository = repository
        self._data = data
        self._export_storage = export_storage

    def record_audit(
        self,
        actor: GovernanceActor,
        *,
        action: str,
        resource_type: str,
        resource_id: str,
        result: AuditResult,
        reason_code: str,
        retention_class: RetentionClass = "SECURITY_AUDIT",
        resource_version: str | None = None,
        request_id: str | None = None,
        trace_id: str | None = None,
        security_metadata: Mapping[str, object] | None = None,
        change_summary: AuditChangeSummary | None = None,
        evidence_ref: str | None = None,
        correction_of_event_id: str | None = None,
        organization_id: str | None = None,
        occurred_at: str | None = None,
    ) -> AuditEvent:
        if not action.strip() or not resource_type.strip() or not resource_id.strip() or not reason_code.strip():
            raise GovernanceError("AUDIT_EVENT_IDENTITY_REQUIRED")
        effective_org = organization_id if organization_id is not None else actor.organization_id
        if actor.organization_id is not None and effective_org not in {None, actor.organization_id}:
            raise GovernanceError("AUDIT_TENANT_SCOPE_MISMATCH", 403)
        if correction_of_event_id and self._repository.get_audit(correction_of_event_id) is None:
            raise GovernanceError("AUDIT_CORRECTION_SOURCE_NOT_FOUND", 404)
        policy = self._repository.current_retention_policy(retention_class)
        previous = self._repository.latest_chain_hash(_chain_key(effective_org))
        event = AuditEvent(
            event_id=f"audit-{uuid4()}",
            organization_id=effective_org,
            actor_type=actor.actor_type,
            actor_id=actor.actor_id,
            actor_version=actor.actor_version,
            session_ref=actor.session_ref,
            api_token_ref=actor.api_token_ref,
            agent_run_ref=actor.agent_run_id,
            task_ref=actor.task_id,
            human_initiator_id=actor.human_initiator_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_version=resource_version,
            result=result,
            reason_code=reason_code[:160],
            request_id=request_id[:160] if request_id else None,
            trace_id=trace_id[:160] if trace_id else None,
            security_metadata=sanitize_metadata(security_metadata),
            change_summary=change_summary or AuditChangeSummary(),
            evidence_ref=evidence_ref[:500] if evidence_ref else None,
            retention_class=retention_class,
            retention_policy_version=policy.version,
            correction_of_event_id=correction_of_event_id,
            occurred_at=occurred_at or _iso(_now()),
            prev_hash=previous,
            event_hash="",
        )
        event = replace(event, event_hash=_event_hash(event))
        self._repository.append_audit(event)
        return event

    def correct_audit(
        self,
        actor: GovernanceActor,
        *,
        event_id: str,
        reason_code: str,
        note: str,
        request_id: str | None = None,
    ) -> AuditEvent:
        self._require(actor, "audit.correct")
        source = self._repository.get_audit(event_id)
        if source is None:
            raise GovernanceError("AUDIT_EVENT_NOT_FOUND", 404)
        if not note.strip():
            raise GovernanceError("AUDIT_CORRECTION_NOTE_REQUIRED")
        return self.record_audit(
            actor,
            action="AUDIT_CORRECTION",
            resource_type="AUDIT_EVENT",
            resource_id=event_id,
            result="SUCCESS",
            reason_code=reason_code,
            request_id=request_id,
            security_metadata={"correction_note": note},
            correction_of_event_id=event_id,
            organization_id=source.organization_id,
        )

    def search_audit(self, actor: GovernanceActor, query: AuditQuery) -> AuditPage:
        scoped = self._scope_query(actor, query, permission="audit.read")
        return self._repository.search_audit(scoped)

    def list_retention_policies(self, actor: GovernanceActor) -> tuple[RetentionPolicy, ...]:
        self._require_any(actor, {"governance.retention.read", "governance.retention.manage", "admin.audit.read"})
        return self._repository.list_retention_policies()

    def publish_retention_policy(
        self,
        actor: GovernanceActor,
        *,
        retention_class: RetentionClass,
        version: int,
        retention_days: int,
        policy_note: str,
    ) -> RetentionPolicy:
        self._require(actor, "governance.retention.manage")
        policy = RetentionPolicy(
            retention_class=retention_class,
            version=version,
            retention_days=retention_days,
            created_by=actor.actor_id,
            created_at=_iso(_now()),
            policy_note=policy_note,
        )
        self._repository.publish_retention_policy(policy)
        self.record_audit(
            actor,
            action="RETENTION_POLICY_PUBLISHED",
            resource_type="RETENTION_POLICY",
            resource_id=f"{retention_class}:v{version}",
            result="SUCCESS",
            reason_code="GOVERNANCE_POLICY_CHANGE",
            change_summary=AuditChangeSummary(
                changed_fields=("retention_days",),
                version_refs=(f"{retention_class}:v{version}",),
            ),
        )
        return policy

    def retention_candidates(
        self, actor: GovernanceActor, *, organization_id: str | None = None, now: str | None = None
    ) -> tuple[RetentionCandidate, ...]:
        self._require_any(actor, {"governance.retention.read", "governance.retention.manage", "admin.audit.read"})
        scoped_org = self._scope_organization(actor, organization_id)
        instant = _parse_time(now) if now else _now()
        holds = self.active_holds(actor, organization_id=scoped_org)
        candidates: list[RetentionCandidate] = []
        for resource in self._data.retention_resources(scoped_org):
            if self._resource_is_held(resource, holds):
                continue
            policy = self._repository.current_retention_policy(resource.retention_class)
            eligible_at = _parse_time(resource.created_at) + timedelta(days=policy.retention_days)
            if eligible_at <= instant:
                candidates.append(
                    RetentionCandidate(resource=resource, policy_version=policy.version, eligible_at=_iso(eligible_at))
                )
        return tuple(sorted(candidates, key=lambda item: (item.eligible_at, item.resource.resource_id)))

    def create_hold(
        self,
        actor: GovernanceActor,
        *,
        hold_type: HoldType,
        organization_id: str | None,
        scope_type: HoldScopeType,
        scope_id: str,
        reason_code: str,
        ticket_ref: str,
    ) -> ActiveLegalHold:
        self._require(actor, "governance.legal_hold.manage")
        if not scope_id.strip() or not reason_code.strip() or not ticket_ref.strip():
            raise GovernanceError("LEGAL_HOLD_INVALID")
        scoped_org = self._scope_organization(actor, organization_id)
        hold_id = f"hold-{uuid4()}"
        occurred_at = _iso(_now())
        event = LegalHoldEvent(
            hold_event_id=f"hold-event-{uuid4()}",
            hold_id=hold_id,
            hold_type=hold_type,
            action="CREATE",
            organization_id=scoped_org,
            scope_type=scope_type,
            scope_id=scope_id,
            reason_code=reason_code,
            ticket_ref=ticket_ref,
            actor_id=actor.actor_id,
            occurred_at=occurred_at,
        )
        self._repository.append_hold_event(event)
        self.record_audit(
            actor,
            action="LEGAL_HOLD_CREATED",
            resource_type="LEGAL_HOLD",
            resource_id=hold_id,
            result="SUCCESS",
            reason_code=reason_code,
            security_metadata={"ticket_ref": ticket_ref, "scope_type": scope_type, "scope_id": scope_id},
            organization_id=scoped_org,
        )
        return ActiveLegalHold(
            hold_id=hold_id,
            hold_type=hold_type,
            organization_id=scoped_org,
            scope_type=scope_type,
            scope_id=scope_id,
            reason_code=reason_code,
            ticket_ref=ticket_ref,
            created_by=actor.actor_id,
            created_at=occurred_at,
        )

    def release_hold(
        self,
        actor: GovernanceActor,
        *,
        hold_id: str,
        reason_code: str,
        ticket_ref: str,
    ) -> ActiveLegalHold:
        self._require(actor, "governance.legal_hold.manage")
        active = next((item for item in self._active_holds_unscoped() if item.hold_id == hold_id), None)
        if active is None:
            raise GovernanceError("LEGAL_HOLD_NOT_ACTIVE", 404)
        self._scope_organization(actor, active.organization_id)
        self._repository.append_hold_event(
            LegalHoldEvent(
                hold_event_id=f"hold-event-{uuid4()}",
                hold_id=hold_id,
                hold_type=active.hold_type,
                action="RELEASE",
                organization_id=active.organization_id,
                scope_type=active.scope_type,
                scope_id=active.scope_id,
                reason_code=reason_code,
                ticket_ref=ticket_ref,
                actor_id=actor.actor_id,
                occurred_at=_iso(_now()),
            )
        )
        self.record_audit(
            actor,
            action="LEGAL_HOLD_RELEASED",
            resource_type="LEGAL_HOLD",
            resource_id=hold_id,
            result="SUCCESS",
            reason_code=reason_code,
            security_metadata={"ticket_ref": ticket_ref},
            organization_id=active.organization_id,
        )
        return active

    def active_holds(
        self, actor: GovernanceActor, *, organization_id: str | None = None
    ) -> tuple[ActiveLegalHold, ...]:
        self._require_any(actor, {"governance.legal_hold.read", "governance.legal_hold.manage", "admin.audit.read"})
        scoped_org = self._scope_organization(actor, organization_id)
        return tuple(
            item for item in self._active_holds_unscoped() if scoped_org is None or item.organization_id == scoped_org
        )

    def request_deletion(
        self,
        actor: GovernanceActor,
        *,
        subject_user_id: str,
        organization_id: str,
        request_id: str | None = None,
        reason_code: str = "DATA_SUBJECT_REQUEST",
    ) -> DeletionRequestView:
        self._require(actor, "governance.deletion.manage")
        scoped_org = self._scope_organization(actor, organization_id)
        if scoped_org is None or not subject_user_id.strip():
            raise GovernanceError("DELETION_REQUEST_INVALID")
        resources = self._data.resources_for_subject(subject_user_id, scoped_org)
        request = request_id or f"delete-{uuid4()}"
        existing = self._repository.list_deletion_events(request)
        if existing:
            return self._deletion_view(existing)
        event = DeletionEvent(
            deletion_event_id=f"deletion-event-{uuid4()}",
            request_id=request,
            subject_user_id=subject_user_id,
            organization_id=scoped_org,
            status="REQUESTED",
            resource_refs=tuple(_resource_ref(item) for item in resources),
            blocked_hold_ids=(),
            deleted_count=0,
            anonymized_count=0,
            retained_count=0,
            error_code=None,
            actor_id=actor.actor_id,
            occurred_at=_iso(_now()),
        )
        self._repository.append_deletion_event(event)
        self.record_audit(
            actor,
            action="DATA_DELETION_REQUESTED",
            resource_type="USER",
            resource_id=subject_user_id,
            result="SUCCESS",
            reason_code=reason_code,
            security_metadata={"deletion_request_id": request, "resource_count": len(resources)},
            organization_id=scoped_org,
        )
        return self._deletion_view((event,))

    def execute_deletion(self, actor: GovernanceActor, request_id: str) -> DeletionRequestView:
        self._require(actor, "governance.deletion.manage")
        events = self._repository.list_deletion_events(request_id)
        if not events:
            raise GovernanceError("DELETION_REQUEST_NOT_FOUND", 404)
        current = self._deletion_view(events)
        if current.status == "COMPLETED":
            return current
        self._scope_organization(actor, current.organization_id)
        resources = self._data.resources_for_subject(current.subject_user_id, current.organization_id)
        holds = self._active_holds_unscoped()
        blocking = tuple(
            sorted({hold.hold_id for resource in resources for hold in holds if self._hold_matches(resource, hold)})
        )
        if blocking:
            self._append_deletion_status(current, actor, "BLOCKED_HOLD", blocked_hold_ids=blocking)
            self.record_audit(
                actor,
                action="DATA_DELETION_BLOCKED",
                resource_type="DELETION_REQUEST",
                resource_id=request_id,
                result="DENIED",
                reason_code="ACTIVE_HOLD",
                security_metadata={"hold_count": len(blocking)},
                organization_id=current.organization_id,
            )
            return self._deletion_view(self._repository.list_deletion_events(request_id))
        try:
            self._data.deactivate_subject(current.subject_user_id, current.organization_id)
            self._append_deletion_status(current, actor, "DEACTIVATED")
            self._append_deletion_status(current, actor, "DELETING")
            deleted = 0
            anonymized = 0
            retained = 0
            for resource in resources:
                if resource.erasure_mode == "RETENTION_ONLY":
                    retained += 1
                    continue
                self._data.erase_resource(resource, resource.erasure_mode)
                if resource.erasure_mode == "DELETE":
                    deleted += 1
                else:
                    anonymized += 1
                if resource.object_ref:
                    self._data.gc_object(resource.object_ref)
                if resource.search_ref:
                    self._data.remove_search_ref(resource.search_ref)
            self._append_deletion_status(
                current,
                actor,
                "COMPLETED",
                deleted_count=deleted,
                anonymized_count=anonymized,
                retained_count=retained,
            )
            self.record_audit(
                actor,
                action="DATA_DELETION_COMPLETED",
                resource_type="DELETION_REQUEST",
                resource_id=request_id,
                result="SUCCESS",
                reason_code="DATA_SUBJECT_REQUEST_COMPLETED",
                security_metadata={
                    "deleted_count": deleted,
                    "anonymized_count": anonymized,
                    "retained_count": retained,
                },
                organization_id=current.organization_id,
            )
        except GovernanceError:
            raise
        except Exception as exc:
            self._append_deletion_status(current, actor, "FAILED", error_code="DELETION_ADAPTER_FAILED")
            raise GovernanceError("DELETION_ADAPTER_FAILED", 502) from exc
        return self._deletion_view(self._repository.list_deletion_events(request_id))

    def list_deletions(self, actor: GovernanceActor) -> tuple[DeletionRequestView, ...]:
        self._require(actor, "governance.deletion.manage")
        grouped: dict[str, list[DeletionEvent]] = {}
        for event in self._repository.list_deletion_events():
            if actor.organization_id is not None and event.organization_id != actor.organization_id:
                continue
            grouped.setdefault(event.request_id, []).append(event)
        return tuple(
            sorted(
                (self._deletion_view(tuple(items)) for items in grouped.values()),
                key=lambda item: item.updated_at,
                reverse=True,
            )
        )

    def create_export(
        self, actor: GovernanceActor, *, export_format: ExportFormat, query: AuditQuery
    ) -> AuditExportJob:
        scoped = self._scope_query(actor, query, permission="audit.export")
        job = AuditExportJob(
            job_id=f"audit-export-{uuid4()}",
            organization_id=scoped.organization_id,
            export_format=export_format,
            status="PENDING",
            query=replace(scoped, cursor=None, limit=200),
            created_by=actor.actor_id,
            created_at=_iso(_now()),
        )
        self._repository.save_export_job(job)
        self.record_audit(
            actor,
            action="AUDIT_EXPORT_REQUESTED",
            resource_type="AUDIT_EXPORT",
            resource_id=job.job_id,
            result="SUCCESS",
            reason_code="AUDIT_EXPORT",
            retention_class="EXPORT",
            security_metadata={"format": export_format},
            organization_id=job.organization_id,
        )
        return job

    def run_export(self, actor: GovernanceActor, job_id: str) -> AuditExportJob:
        self._require(actor, "audit.export.execute")
        job = self._require_export_job(job_id)
        if job.status == "READY":
            return job
        if job.status not in {"PENDING", "FAILED"}:
            raise GovernanceError("AUDIT_EXPORT_STATE_CONFLICT", 409)
        running = replace(job, status="RUNNING", error_code=None)
        self._repository.save_export_job(running)
        try:
            events = self._all_export_events(running.query)
            payload = self._serialize_export(events, running.export_format)
            stored = self._export_storage.put(running.job_id, running.export_format, payload)
            ready = replace(
                running,
                status="READY",
                completed_at=_iso(_now()),
                object_ref=stored.object_ref,
                file_name=stored.file_name,
                checksum_sha256=stored.checksum_sha256,
                size_bytes=stored.size_bytes,
            )
            self._repository.save_export_job(ready)
            self.record_audit(
                actor,
                action="AUDIT_EXPORT_READY",
                resource_type="AUDIT_EXPORT",
                resource_id=job_id,
                result="SUCCESS",
                reason_code="AUDIT_EXPORT_RENDERED",
                retention_class="EXPORT",
                security_metadata={"record_count": len(events), "checksum_sha256": stored.checksum_sha256},
                organization_id=job.organization_id,
            )
            return ready
        except GovernanceError:
            raise
        except Exception as exc:
            failed = replace(running, status="FAILED", error_code="AUDIT_EXPORT_FAILED")
            self._repository.save_export_job(failed)
            raise GovernanceError("AUDIT_EXPORT_FAILED", 502) from exc

    def get_export(self, actor: GovernanceActor, job_id: str) -> AuditExportJob:
        job = self._require_export_job(job_id)
        self._authorize_export_scope(actor, job)
        return job

    def get_download(self, actor: GovernanceActor, job_id: str, ttl_seconds: int = 300) -> AuditDownloadLease:
        if ttl_seconds < 30 or ttl_seconds > 900:
            raise GovernanceError("AUDIT_DOWNLOAD_TTL_INVALID")
        job = self._require_export_job(job_id)
        self._authorize_export_scope(actor, job)
        if job.status != "READY" or not all(
            (job.object_ref, job.file_name, job.checksum_sha256, job.size_bytes is not None)
        ):
            raise GovernanceError("AUDIT_EXPORT_NOT_READY", 409)
        stored = StoredAuditExport(
            object_ref=job.object_ref or "",
            file_name=job.file_name or "",
            checksum_sha256=job.checksum_sha256 or "",
            size_bytes=job.size_bytes or 0,
        )
        lease = self._export_storage.create_download(stored, ttl_seconds)
        lease = replace(lease, job_id=job_id)
        self.record_audit(
            actor,
            action="AUDIT_EXPORT_DOWNLOADED",
            resource_type="AUDIT_EXPORT",
            resource_id=job_id,
            result="SUCCESS",
            reason_code="AUDIT_EXPORT_DOWNLOAD",
            retention_class="EXPORT",
            security_metadata={"ttl_seconds": ttl_seconds},
            organization_id=job.organization_id,
        )
        return lease

    def list_exports(self, actor: GovernanceActor) -> tuple[AuditExportJob, ...]:
        self._require_any(actor, {"audit.export", "admin.audit.read"})
        values = self._repository.list_export_jobs()
        if actor.actor_type == "PLATFORM_ADMIN" and "admin.audit.read" in actor.permissions:
            return values
        if actor.organization_id is None:
            raise GovernanceError("AUDIT_ORGANIZATION_REQUIRED", 403)
        return tuple(item for item in values if item.organization_id == actor.organization_id)

    def _scope_query(self, actor: GovernanceActor, query: AuditQuery, *, permission: str) -> AuditQuery:
        platform = actor.actor_type == "PLATFORM_ADMIN" and "admin.audit.read" in actor.permissions
        if platform:
            return query
        self._require(actor, permission)
        if actor.organization_id is None:
            raise GovernanceError("AUDIT_ORGANIZATION_REQUIRED", 403)
        if query.organization_id not in {None, actor.organization_id}:
            raise GovernanceError("AUDIT_TENANT_SCOPE_MISMATCH", 403)
        return replace(query, organization_id=actor.organization_id)

    def _scope_organization(self, actor: GovernanceActor, organization_id: str | None) -> str | None:
        if actor.actor_type == "PLATFORM_ADMIN" and "admin.audit.read" in actor.permissions:
            return organization_id
        if actor.organization_id is None:
            raise GovernanceError("GOVERNANCE_ORGANIZATION_REQUIRED", 403)
        if organization_id not in {None, actor.organization_id}:
            raise GovernanceError("GOVERNANCE_TENANT_SCOPE_MISMATCH", 403)
        return actor.organization_id

    def _active_holds_unscoped(self) -> tuple[ActiveLegalHold, ...]:
        events = sorted(self._repository.list_hold_events(), key=lambda item: item.occurred_at)
        active: dict[str, ActiveLegalHold] = {}
        for event in events:
            if event.action == "CREATE":
                active[event.hold_id] = ActiveLegalHold(
                    hold_id=event.hold_id,
                    hold_type=event.hold_type,
                    organization_id=event.organization_id,
                    scope_type=event.scope_type,
                    scope_id=event.scope_id,
                    reason_code=event.reason_code,
                    ticket_ref=event.ticket_ref,
                    created_by=event.actor_id,
                    created_at=event.occurred_at,
                )
            else:
                active.pop(event.hold_id, None)
        return tuple(active.values())

    @staticmethod
    def _hold_matches(resource: GovernanceResourceRef, hold: ActiveLegalHold) -> bool:
        if hold.organization_id is not None and hold.organization_id != resource.organization_id:
            return False
        if hold.scope_type == "ORGANIZATION":
            return hold.scope_id == resource.organization_id
        if hold.scope_type == "USER":
            return hold.scope_id == resource.subject_user_id
        if hold.scope_type == "RESOURCE":
            return hold.scope_id in {resource.resource_id, _resource_ref(resource)}
        return hold.scope_id == resource.retention_class

    def _resource_is_held(
        self, resource: GovernanceResourceRef, holds: tuple[ActiveLegalHold, ...]
    ) -> bool:
        return any(self._hold_matches(resource, hold) for hold in holds)

    def _append_deletion_status(
        self,
        current: DeletionRequestView,
        actor: GovernanceActor,
        status: DeletionStatus,
        *,
        blocked_hold_ids: tuple[str, ...] = (),
        deleted_count: int = 0,
        anonymized_count: int = 0,
        retained_count: int = 0,
        error_code: str | None = None,
    ) -> None:
        self._repository.append_deletion_event(
            DeletionEvent(
                deletion_event_id=f"deletion-event-{uuid4()}",
                request_id=current.request_id,
                subject_user_id=current.subject_user_id,
                organization_id=current.organization_id,
                status=status,
                resource_refs=current.resource_refs,
                blocked_hold_ids=blocked_hold_ids,
                deleted_count=deleted_count,
                anonymized_count=anonymized_count,
                retained_count=retained_count,
                error_code=error_code,
                actor_id=actor.actor_id,
                occurred_at=_iso(_now()),
            )
        )

    @staticmethod
    def _deletion_view(events: tuple[DeletionEvent, ...]) -> DeletionRequestView:
        if not events:
            raise GovernanceError("DELETION_REQUEST_NOT_FOUND", 404)
        ordered = sorted(events, key=lambda item: item.occurred_at)
        first = ordered[0]
        last = ordered[-1]
        return DeletionRequestView(
            request_id=first.request_id,
            subject_user_id=first.subject_user_id,
            organization_id=first.organization_id,
            status=last.status,
            resource_refs=first.resource_refs,
            blocked_hold_ids=last.blocked_hold_ids,
            deleted_count=last.deleted_count,
            anonymized_count=last.anonymized_count,
            retained_count=last.retained_count,
            error_code=last.error_code,
            created_at=first.occurred_at,
            updated_at=last.occurred_at,
        )

    def _require_export_job(self, job_id: str) -> AuditExportJob:
        job = self._repository.get_export_job(job_id)
        if job is None:
            raise GovernanceError("AUDIT_EXPORT_NOT_FOUND", 404)
        return job

    def _authorize_export_scope(self, actor: GovernanceActor, job: AuditExportJob) -> None:
        if actor.actor_type == "PLATFORM_ADMIN" and "admin.audit.read" in actor.permissions:
            return
        self._require(actor, "audit.export")
        if actor.organization_id is None or job.organization_id != actor.organization_id:
            raise GovernanceError("AUDIT_EXPORT_FORBIDDEN", 403)

    def _all_export_events(self, query: AuditQuery) -> tuple[AuditEvent, ...]:
        items: list[AuditEvent] = []
        cursor: str | None = None
        while True:
            page = self._repository.search_audit(replace(query, cursor=cursor, limit=200))
            items.extend(page.items)
            if not page.next_cursor:
                break
            cursor = page.next_cursor
            if len(items) > 50_000:
                raise GovernanceError("AUDIT_EXPORT_TOO_LARGE", 413)
        return tuple(items)

    @staticmethod
    def _serialize_export(events: tuple[AuditEvent, ...], export_format: ExportFormat) -> bytes:
        rows = [
            {
                "id": item.event_id,
                "organization_id": item.organization_id,
                "actor_type": item.actor_type,
                "actor_id": item.actor_id,
                "action": item.action,
                "resource_type": item.resource_type,
                "resource_id": item.resource_id,
                "resource_version": item.resource_version,
                "result": item.result,
                "reason_code": item.reason_code,
                "request_id": item.request_id,
                "trace_id": item.trace_id,
                "retention_class": item.retention_class,
                "retention_policy_version": item.retention_policy_version,
                "occurred_at": item.occurred_at,
                "event_hash": item.event_hash,
            }
            for item in events
        ]
        if export_format == "JSON":
            return json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        output = io.StringIO()
        fields = list(rows[0].keys()) if rows else [
            "id",
            "organization_id",
            "actor_type",
            "actor_id",
            "action",
            "resource_type",
            "resource_id",
            "resource_version",
            "result",
            "reason_code",
            "request_id",
            "trace_id",
            "retention_class",
            "retention_policy_version",
            "occurred_at",
            "event_hash",
        ]
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
        return output.getvalue().encode("utf-8")

    @staticmethod
    def _require(actor: GovernanceActor, permission: str) -> None:
        if permission not in actor.permissions:
            raise GovernanceError("GOVERNANCE_FORBIDDEN", 403)

    @staticmethod
    def _require_any(actor: GovernanceActor, permissions: set[str]) -> None:
        if not actor.permissions.intersection(permissions):
            raise GovernanceError("GOVERNANCE_FORBIDDEN", 403)


class InMemoryGovernanceRepository:
    def __init__(self) -> None:
        self.audit_events: list[AuditEvent] = []
        self.retention_policies: dict[tuple[RetentionClass, int], RetentionPolicy] = {}
        self.hold_events: list[LegalHoldEvent] = []
        self.deletion_events: list[DeletionEvent] = []
        self.export_jobs: dict[str, AuditExportJob] = {}
        self._lock = RLock()
        created_at = _iso(_now())
        for retention_class, days in DEFAULT_RETENTION_DAYS.items():
            policy = RetentionPolicy(
                retention_class=retention_class,
                version=1,
                retention_days=days,
                created_by="system:node-65-default",
                created_at=created_at,
                policy_note="Engineering default; legal review required before production launch.",
            )
            self.retention_policies[(retention_class, 1)] = policy

    def append_audit(self, event: AuditEvent) -> None:
        with self._lock:
            if any(item.event_id == event.event_id for item in self.audit_events):
                raise GovernanceError("AUDIT_EVENT_IMMUTABLE", 409)
            expected_previous = self.latest_chain_hash(_chain_key(event.organization_id))
            if event.prev_hash != expected_previous or event.event_hash != _event_hash(event):
                raise GovernanceError("AUDIT_HASH_CHAIN_INVALID", 409)
            self.audit_events.append(event)

    def latest_chain_hash(self, chain_key: str) -> str | None:
        for event in reversed(self.audit_events):
            if _chain_key(event.organization_id) == chain_key:
                return event.event_hash
        return None

    def get_audit(self, event_id: str) -> AuditEvent | None:
        return next((item for item in self.audit_events if item.event_id == event_id), None)

    def search_audit(self, query: AuditQuery) -> AuditPage:
        values = list(self.audit_events)
        if query.organization_id is not None:
            values = [item for item in values if item.organization_id == query.organization_id]
        if query.actor_id:
            values = [item for item in values if item.actor_id == query.actor_id]
        if query.action:
            values = [item for item in values if item.action == query.action]
        if query.resource_type:
            values = [item for item in values if item.resource_type == query.resource_type]
        if query.resource_id:
            values = [item for item in values if item.resource_id == query.resource_id]
        if query.result:
            values = [item for item in values if item.result == query.result]
        if query.trace_id:
            values = [item for item in values if item.trace_id == query.trace_id]
        if query.start_at:
            start = _parse_time(query.start_at)
            values = [item for item in values if _parse_time(item.occurred_at) >= start]
        if query.end_at:
            end = _parse_time(query.end_at)
            values = [item for item in values if _parse_time(item.occurred_at) <= end]
        values.sort(key=lambda item: (item.occurred_at, item.event_id), reverse=True)
        if query.cursor:
            cursor_key = _decode_cursor(query.cursor)
            values = [item for item in values if (item.occurred_at, item.event_id) < cursor_key]
        page = values[: query.limit]
        next_cursor = _encode_cursor(page[-1]) if len(values) > len(page) and page else None
        return AuditPage(items=tuple(page), next_cursor=next_cursor)

    def publish_retention_policy(self, policy: RetentionPolicy) -> None:
        key = (policy.retention_class, policy.version)
        if key in self.retention_policies:
            raise GovernanceError("RETENTION_POLICY_IMMUTABLE", 409)
        current = self.current_retention_policy(policy.retention_class)
        if policy.version != current.version + 1:
            raise GovernanceError("RETENTION_POLICY_VERSION_CONFLICT", 409)
        self.retention_policies[key] = policy

    def list_retention_policies(self) -> tuple[RetentionPolicy, ...]:
        return tuple(
            sorted(self.retention_policies.values(), key=lambda item: (item.retention_class, item.version))
        )

    def current_retention_policy(self, retention_class: RetentionClass) -> RetentionPolicy:
        values = [
            item for item in self.retention_policies.values() if item.retention_class == retention_class
        ]
        if not values:
            raise GovernanceError("RETENTION_POLICY_NOT_FOUND", 500)
        return max(values, key=lambda item: item.version)

    def append_hold_event(self, event: LegalHoldEvent) -> None:
        if any(item.hold_event_id == event.hold_event_id for item in self.hold_events):
            raise GovernanceError("LEGAL_HOLD_EVENT_IMMUTABLE", 409)
        self.hold_events.append(event)

    def list_hold_events(self) -> tuple[LegalHoldEvent, ...]:
        return tuple(self.hold_events)

    def append_deletion_event(self, event: DeletionEvent) -> None:
        if any(item.deletion_event_id == event.deletion_event_id for item in self.deletion_events):
            raise GovernanceError("DELETION_EVENT_IMMUTABLE", 409)
        self.deletion_events.append(event)

    def list_deletion_events(self, request_id: str | None = None) -> tuple[DeletionEvent, ...]:
        values = self.deletion_events
        if request_id is not None:
            values = [item for item in values if item.request_id == request_id]
        return tuple(values)

    def save_export_job(self, job: AuditExportJob) -> None:
        prior = self.export_jobs.get(job.job_id)
        if prior is not None and prior.created_by != job.created_by:
            raise GovernanceError("AUDIT_EXPORT_OWNER_CONFLICT", 409)
        self.export_jobs[job.job_id] = job

    def get_export_job(self, job_id: str) -> AuditExportJob | None:
        return self.export_jobs.get(job_id)

    def list_export_jobs(self) -> tuple[AuditExportJob, ...]:
        return tuple(sorted(self.export_jobs.values(), key=lambda item: item.created_at, reverse=True))

    def verify_hash_chains(self) -> bool:
        previous: dict[str, str | None] = {}
        for event in self.audit_events:
            key = _chain_key(event.organization_id)
            if event.prev_hash != previous.get(key) or event.event_hash != _event_hash(event):
                return False
            previous[key] = event.event_hash
        return True


class InMemoryGovernanceDataPort:
    def __init__(self, resources: tuple[GovernanceResourceRef, ...] = ()) -> None:
        self.resources = list(resources)
        self.deactivated: list[tuple[str, str]] = []
        self.erased: list[tuple[str, ErasureMode]] = []
        self.gc_objects: list[str] = []
        self.removed_search_refs: list[str] = []

    def resources_for_subject(
        self, subject_user_id: str, organization_id: str
    ) -> tuple[GovernanceResourceRef, ...]:
        return tuple(
            item
            for item in self.resources
            if item.organization_id == organization_id and item.subject_user_id == subject_user_id
        )

    def retention_resources(self, organization_id: str | None) -> tuple[GovernanceResourceRef, ...]:
        if organization_id is None:
            return tuple(self.resources)
        return tuple(item for item in self.resources if item.organization_id == organization_id)

    def deactivate_subject(self, subject_user_id: str, organization_id: str) -> None:
        self.deactivated.append((subject_user_id, organization_id))

    def erase_resource(self, resource: GovernanceResourceRef, mode: ErasureMode) -> None:
        self.erased.append((_resource_ref(resource), mode))

    def gc_object(self, object_ref: str) -> None:
        self.gc_objects.append(object_ref)

    def remove_search_ref(self, search_ref: str) -> None:
        self.removed_search_refs.append(search_ref)


class InMemoryAuditExportStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.lease_counter = 0

    def put(self, job_id: str, export_format: ExportFormat, payload: bytes) -> StoredAuditExport:
        suffix = "json" if export_format == "JSON" else "csv"
        object_ref = f"audit-export://{job_id}/events.{suffix}"
        self.objects[object_ref] = payload
        return StoredAuditExport(
            object_ref=object_ref,
            file_name=f"lumi-audit-{job_id}.{suffix}",
            checksum_sha256=sha256(payload).hexdigest(),
            size_bytes=len(payload),
        )

    def create_download(self, stored: StoredAuditExport, ttl_seconds: int) -> AuditDownloadLease:
        if stored.object_ref not in self.objects:
            raise GovernanceError("AUDIT_EXPORT_OBJECT_MISSING", 404)
        self.lease_counter += 1
        return AuditDownloadLease(
            job_id="",
            signed_url=f"https://audit-download.invalid/{self.lease_counter}/{stored.checksum_sha256}?sig=ephemeral",
            expires_at=_iso(_now() + timedelta(seconds=ttl_seconds)),
        )


class Node64AdminAuditSink:
    """Adapter from NODE-64 AdminAuditSink into the canonical NODE-65 audit pipeline."""

    def __init__(self, engine: GovernanceEngine, repository: GovernanceRepository) -> None:
        self._engine = engine
        self._repository = repository

    def emit(self, event: object) -> None:
        event_type = str(getattr(event, "event_type"))
        actor_id = str(getattr(event, "actor_id"))
        target_type = str(getattr(event, "target_type"))
        target_id = str(getattr(event, "target_id"))
        reason = str(getattr(event, "reason"))
        ticket_ref = str(getattr(event, "ticket_ref"))
        safe_metadata = dict(getattr(event, "safe_metadata", ()))
        organization_id = safe_metadata.get("organization_id")
        if target_type == "ORGANIZATION":
            organization_id = target_id
        actor = GovernanceActor(
            actor_id=actor_id,
            actor_type="PLATFORM_ADMIN",
            organization_id=None,
            permissions=frozenset({"admin.audit.read"}),
        )
        self._engine.record_audit(
            actor,
            action=event_type,
            resource_type=target_type,
            resource_id=target_id,
            result="SUCCESS",
            reason_code="ADMIN_ACTION",
            security_metadata={
                **safe_metadata,
                "ticket_ref": ticket_ref,
                "reason_hash": _hash_text(reason),
            },
            organization_id=organization_id,
            occurred_at=str(getattr(event, "created_at")),
        )

    def recent(self) -> tuple[object, ...]:
        from lumi_project_core.admin_console import AdminAuditEvent

        page = self._repository.search_audit(AuditQuery(limit=100))
        values: list[AdminAuditEvent] = []
        for item in page.items:
            if not item.action.startswith("ADMIN_"):
                continue
            metadata = dict(item.security_metadata)
            values.append(
                AdminAuditEvent(
                    event_id=item.event_id,
                    event_type=item.action,
                    actor_id=item.actor_id,
                    target_type=item.resource_type,
                    target_id=item.resource_id,
                    reason="Recorded in governance audit",
                    ticket_ref=metadata.get("ticket_ref", "governance"),
                    created_at=item.occurred_at,
                    safe_metadata=tuple(
                        (key, value)
                        for key, value in item.security_metadata
                        if key not in {"ticket_ref", "reason_hash"}
                    ),
                )
            )
        return tuple(values)
