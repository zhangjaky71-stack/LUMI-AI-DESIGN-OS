from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime
from decimal import Decimal
from typing import Any, Iterator, Mapping
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from lumi_api.domain.ids import new_uuid7

from .contracts import (
    AdminDashboard,
    BreakGlassGrant,
    DeadLetterReplayRequest,
    FeatureFlag,
    PlatformAdminConflict,
    PlatformAdminNotFound,
    PlatformAdminPrincipal,
    PlatformAdminRole,
    ProviderControlSummary,
    SafeDeadLetter,
    SafeRunSummary,
    role_permissions,
)


class PostgresPlatformAdminRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    @contextmanager
    def transaction(self) -> Iterator[None]:
        if self.session.in_transaction():
            self.session.rollback()
        with self.session.begin():
            yield

    def principal_for_user(self, user_id: UUID) -> PlatformAdminPrincipal | None:
        row = self.session.execute(
            text("SELECT id,user_id,role,active FROM platform_admin_principals WHERE user_id=:user_id AND active=true"),
            {"user_id": user_id},
        ).mappings().one_or_none()
        if row is None:
            return None
        role = PlatformAdminRole(str(row["role"]))
        return PlatformAdminPrincipal(id=row["id"], user_id=row["user_id"], role=role, permissions=role_permissions(role), active=True)

    def dashboard(self) -> AdminDashboard:
        row = self.session.execute(text("""
            SELECT
              (SELECT count(*) FROM agent_runs WHERE status IN ('pending','running','waiting_user','waiting_external','paused')) AS active_runs,
              (SELECT count(*) FROM agent_runs WHERE status='failed') AS failed_runs,
              (SELECT count(*) FROM tasks WHERE status='failed') AS failed_tasks,
              (SELECT count(*) FROM runtime_jobs WHERE status IN ('pending','retrying')) AS queue_pending,
              (SELECT count(*) FROM dead_letter_records WHERE status='open') AS dlq_open,
              (SELECT count(*) FROM provider_health_summaries WHERE state IN ('degraded','open_circuit','disabled')) AS degraded_providers,
              (SELECT count(*) FROM billing_payment_events WHERE status='RECEIVED') AS payment_events_pending,
              (SELECT COALESCE(sum(amount),0) FROM cost_ledger WHERE occurred_at >= now()-interval '24 hours' AND currency='USD' AND cost_basis='provider_cost') AS provider_cost_24h
        """)).mappings().one()
        return AdminDashboard(
            active_runs=int(row["active_runs"]), failed_runs=int(row["failed_runs"]), failed_tasks=int(row["failed_tasks"]),
            queue_pending=int(row["queue_pending"]), dlq_open=int(row["dlq_open"]), degraded_providers=int(row["degraded_providers"]),
            payment_events_pending=int(row["payment_events_pending"]), provider_cost_24h=str(Decimal(row["provider_cost_24h"])),
        )

    def failing_runs(self, limit: int = 100) -> tuple[SafeRunSummary, ...]:
        rows = self.session.execute(text("""
            SELECT id,organization_id,project_id,status,graph_key,graph_version,agent_config_version,code_git_sha,
                   budget_amount,budget_currency,created_at,updated_at
            FROM agent_runs WHERE status='failed' ORDER BY updated_at DESC LIMIT :limit
        """), {"limit": limit}).mappings().all()
        return tuple(SafeRunSummary(
            id=r["id"], organization_id=r["organization_id"], project_id=r["project_id"], status=str(r["status"]), graph_key=str(r["graph_key"]),
            graph_version=str(r["graph_version"]), agent_config_version=str(r["agent_config_version"]), code_git_sha=str(r["code_git_sha"]),
            budget_amount=str(r["budget_amount"]), budget_currency=str(r["budget_currency"]), created_at=r["created_at"], updated_at=r["updated_at"]
        ) for r in rows)

    def dead_letters(self, limit: int = 100) -> tuple[SafeDeadLetter, ...]:
        rows = self.session.execute(text("""
            SELECT id,organization_id,message_id,message_kind,source_queue,consumer,error_category,error_code,error_message,
                   attempts,status,first_failed_at,last_failed_at,replayed_at
            FROM dead_letter_records ORDER BY last_failed_at DESC LIMIT :limit
        """), {"limit": limit}).mappings().all()
        return tuple(self._safe_dead_letter(r) for r in rows)

    def replay_material(self, dead_letter_id: UUID) -> DeadLetterReplayRequest:
        row = self.session.execute(text("""
            SELECT id,organization_id,message_id,message_kind,source_queue,exchange_name,routing_key,payload_json,traceparent,status
            FROM dead_letter_records WHERE id=:id FOR UPDATE
        """), {"id": dead_letter_id}).mappings().one_or_none()
        if row is None:
            raise PlatformAdminNotFound("ADMIN_DEAD_LETTER_NOT_FOUND")
        if str(row["status"]) not in {"open", "replayed"}:
            raise PlatformAdminConflict("ADMIN_DEAD_LETTER_NOT_REPLAYABLE")
        return DeadLetterReplayRequest(
            replay_key=f"admin-dlq-replay:{dead_letter_id}", dead_letter_id=row["id"], organization_id=row["organization_id"], message_id=str(row["message_id"]),
            message_kind=str(row["message_kind"]), source_queue=str(row["source_queue"]), exchange=str(row["exchange_name"]), routing_key=str(row["routing_key"]),
            payload=dict(row["payload_json"] or {}), traceparent=row["traceparent"],
        )

    def mark_replayed(self, dead_letter_id: UUID) -> None:
        with self.transaction():
            result = self.session.execute(text("UPDATE dead_letter_records SET status='replayed', replayed_at=COALESCE(replayed_at,now()), updated_at=now(), version=version+1 WHERE id=:id AND status IN ('open','replayed')"), {"id": dead_letter_id})
            if result.rowcount != 1:
                raise PlatformAdminConflict("ADMIN_DEAD_LETTER_REPLAY_STATE_CHANGED")

    def discard_dead_letter(self, dead_letter_id: UUID) -> None:
        with self.transaction():
            result = self.session.execute(text("UPDATE dead_letter_records SET status='discarded', updated_at=now(), version=version+1 WHERE id=:id AND status='open'"), {"id": dead_letter_id})
            if result.rowcount != 1:
                raise PlatformAdminConflict("ADMIN_DEAD_LETTER_NOT_DISCARDABLE")

    def provider_summaries(self, limit: int = 100) -> tuple[ProviderControlSummary, ...]:
        rows = self.session.execute(text("""
            SELECT DISTINCT ON (h.provider,h.model,h.capability)
              h.provider,h.model,h.capability,h.state,h.score,h.observed_at,
              a.action AS override_action,a.expires_at AS override_expires_at
            FROM provider_health_summaries h
            LEFT JOIN LATERAL (
              SELECT action,expires_at FROM provider_health_override_audit a
              WHERE a.provider=h.provider AND a.model IS NOT DISTINCT FROM h.model AND a.capability IS NOT DISTINCT FROM h.capability
              ORDER BY observed_at DESC LIMIT 1
            ) a ON true
            ORDER BY h.provider,h.model,h.capability,h.observed_at DESC LIMIT :limit
        """), {"limit": limit}).mappings().all()
        return tuple(ProviderControlSummary(provider=str(r["provider"]),model=r["model"],capability=r["capability"],state=str(r["state"]),score=int(r["score"]),observed_at=r["observed_at"],override_action=r["override_action"],override_expires_at=r["override_expires_at"]) for r in rows)

    def provider_override(self, *, provider: str, model: str | None, capability: str | None, action: str, actor_user_id: UUID, reason: str, expires_at: datetime | None) -> UUID:
        if action not in {"force_disabled","force_degraded","clear_override","clear_breaker"}:
            raise ValueError("ADMIN_PROVIDER_ACTION_INVALID")
        override_id = new_uuid7()
        with self.transaction():
            self.session.execute(text("""
                INSERT INTO provider_health_override_audit(id,action,provider,model,capability,actor_id,reason,observed_at,expires_at,created_at)
                VALUES(:id,:action,:provider,:model,:capability,:actor_id,:reason,now(),:expires_at,now())
            """), {"id":override_id,"action":action,"provider":provider,"model":model,"capability":capability,"actor_id":str(actor_user_id),"reason":reason,"expires_at":expires_at})
        return override_id

    def feature_flags(self) -> tuple[FeatureFlag, ...]:
        rows = self.session.execute(text("""
            SELECT * FROM platform_feature_flags WHERE expires_at IS NULL OR expires_at>now() ORDER BY flag_key,scope,target_id NULLS FIRST
        """)).mappings().all()
        return tuple(self._flag(r) for r in rows)

    def upsert_feature_flag(self, *, actor_user_id: UUID, flag_key: str, scope: str, target_id: str | None, value: dict[str, Any], owner: str, reason: str, expires_at: datetime | None) -> FeatureFlag:
        flag_id = new_uuid7()
        payload = json.dumps(value, separators=(",",":"), sort_keys=True)
        with self.transaction():
            existing = self.session.execute(text("SELECT security_locked FROM platform_feature_flags WHERE flag_key=:key AND scope=:scope AND target_id IS NOT DISTINCT FROM :target FOR UPDATE"), {"key":flag_key,"scope":scope,"target":target_id}).mappings().one_or_none()
            if existing is not None and bool(existing["security_locked"]):
                raise PlatformAdminConflict("ADMIN_SECURITY_FLAG_IMMUTABLE")
            row = self.session.execute(text("""
                INSERT INTO platform_feature_flags(id,flag_key,scope,target_id,value_json,owner,reason,security_locked,expires_at,created_by_user_id,updated_by_user_id,created_at,updated_at,version)
                VALUES(:id,:key,:scope,:target,CAST(:value AS jsonb),:owner,:reason,false,:expires,:actor,:actor,now(),now(),1)
                ON CONFLICT (flag_key,scope,target_id) DO UPDATE SET value_json=EXCLUDED.value_json,owner=EXCLUDED.owner,reason=EXCLUDED.reason,expires_at=EXCLUDED.expires_at,updated_by_user_id=EXCLUDED.updated_by_user_id,updated_at=now(),version=platform_feature_flags.version+1
                RETURNING *
            """), {"id":flag_id,"key":flag_key,"scope":scope,"target":target_id,"value":payload,"owner":owner,"reason":reason,"expires":expires_at,"actor":actor_user_id}).mappings().one()
        return self._flag(row)

    def break_glass(self, *, actor_user_id: UUID, scope: str, target_type: str, target_id: str, reason: str, expires_at: datetime) -> BreakGlassGrant:
        grant_id = new_uuid7()
        with self.transaction():
            row = self.session.execute(text("""
              INSERT INTO platform_break_glass_grants(id,actor_user_id,scope,target_type,target_id,reason,expires_at,created_at)
              VALUES(:id,:actor,:scope,:target_type,:target_id,:reason,:expires,now()) RETURNING *
            """), {"id":grant_id,"actor":actor_user_id,"scope":scope,"target_type":target_type,"target_id":target_id,"reason":reason,"expires":expires_at}).mappings().one()
        return BreakGlassGrant(**dict(row))

    def audit(self, *, principal: PlatformAdminPrincipal, action: str, resource_type: str, resource_id: str | None = None, target_organization_id: UUID | None = None, reason: str | None = None, metadata: dict[str, Any] | None = None) -> None:
        with self.transaction():
            self.session.execute(text("""
              INSERT INTO platform_admin_audit_events(id,actor_user_id,actor_role,action,resource_type,resource_id,target_organization_id,reason,metadata_json,created_at)
              VALUES(:id,:actor,:role,:action,:rtype,:rid,:org,:reason,CAST(:metadata AS jsonb),now())
            """), {"id":new_uuid7(),"actor":principal.user_id,"role":principal.role.value,"action":action,"rtype":resource_type,"rid":resource_id,"org":target_organization_id,"reason":reason,"metadata":json.dumps(metadata or {}, separators=(",",":"), sort_keys=True)})

    @staticmethod
    def _safe_dead_letter(row: Mapping[str, Any]) -> SafeDeadLetter:
        return SafeDeadLetter(id=row["id"],organization_id=row["organization_id"],message_id=str(row["message_id"]),message_kind=str(row["message_kind"]),source_queue=str(row["source_queue"]),consumer=str(row["consumer"] or "unknown"),error_category=str(row["error_category"]),error_code=row["error_code"],error_message=str(row["error_message"]),attempts=int(row["attempts"]),status=str(row["status"]),failed_at=row["first_failed_at"],last_failed_at=row["last_failed_at"],replayed_at=row["replayed_at"])

    @staticmethod
    def _flag(row: Mapping[str, Any]) -> FeatureFlag:
        return FeatureFlag(id=row["id"],flag_key=str(row["flag_key"]),scope=str(row["scope"]),target_id=row["target_id"],value=dict(row["value_json"] or {}),owner=str(row["owner"]),reason=str(row["reason"]),security_locked=bool(row["security_locked"]),expires_at=row["expires_at"],created_at=row["created_at"],updated_at=row["updated_at"])
