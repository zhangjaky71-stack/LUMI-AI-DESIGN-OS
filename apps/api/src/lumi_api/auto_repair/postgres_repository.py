from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from lumi_api.persistence.models_auto_repair import (
    AutoRepairAttemptModel,
    AutoRepairJobModel,
    RepairPolicySnapshotModel,
)
from lumi_auto_repair import (
    AutoRepairJob,
    AutoRepairOperationConflict,
    RepairAttempt,
    RepairPolicySnapshot,
)

from .codec import encode_attempt, encode_job, encode_policy, decode_job


class PostgresAutoRepairRepository:
    """Durable NODE-51 repository with append-only attempt semantics."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, job_id: str) -> AutoRepairJob:
        row = self.session.get(AutoRepairJobModel, UUID(job_id))
        if row is None:
            raise KeyError("REPAIR_JOB_NOT_FOUND")
        return decode_job(dict(row.job_json))

    def get_by_operation(
        self,
        *,
        organization_id: str,
        operation_id: str,
    ) -> AutoRepairJob | None:
        row = self.session.scalar(
            select(AutoRepairJobModel).where(
                AutoRepairJobModel.organization_id == UUID(organization_id),
                AutoRepairJobModel.operation_id == UUID(operation_id),
            )
        )
        return None if row is None else decode_job(dict(row.job_json))

    def create(self, job: AutoRepairJob) -> AutoRepairJob:
        existing = self.get_by_operation(
            organization_id=job.spec.organization_id,
            operation_id=job.spec.operation_id,
        )
        if existing is not None:
            self._assert_same_operation(existing, job)
            return existing

        self._ensure_policy(job.spec.policy)
        self.session.add(self._job_row(job))
        try:
            self.session.flush()
            self._sync_attempts(job)
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            concurrent = self.get_by_operation(
                organization_id=job.spec.organization_id,
                operation_id=job.spec.operation_id,
            )
            if concurrent is None:
                raise
            self._assert_same_operation(concurrent, job)
            return concurrent
        return job

    def save(self, job: AutoRepairJob) -> AutoRepairJob:
        row = self.session.get(AutoRepairJobModel, UUID(job.job_id))
        if row is None:
            raise KeyError("REPAIR_JOB_NOT_FOUND")
        expected_hash = job.spec.semantic_hash()
        if row.semantic_hash != expected_hash:
            raise AutoRepairOperationConflict(
                "REPAIR_PERSISTED_SPEC_HASH_MISMATCH"
            )
        self._ensure_policy(job.spec.policy)
        encoded = encode_job(job)
        row.status = job.status.value
        row.working_artifact_version_id = UUID(
            job.working_source.artifact_version_id
        )
        row.current_quality_result_id = UUID(
            job.current_quality.quality_result_id
        )
        row.spent_usd = job.spent_usd
        row.final_artifact_version_id = (
            UUID(job.final_artifact_version_id)
            if job.final_artifact_version_id is not None
            else None
        )
        row.job_json = encoded
        row.reason_codes = list(job.reason_codes)
        row.updated_at = datetime.now(UTC)
        try:
            self._sync_attempts(job)
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            stored = self.get(job.job_id)
            if encode_job(stored) == encoded:
                return stored
            raise AutoRepairOperationConflict(
                "REPAIR_CONCURRENT_SAVE_CONFLICT"
            ) from exc
        return job

    def _job_row(self, job: AutoRepairJob) -> AutoRepairJobModel:
        policy_hash = job.spec.policy.semantic_hash()
        return AutoRepairJobModel(
            repair_job_id=UUID(job.job_id),
            organization_id=UUID(job.spec.organization_id),
            project_id=UUID(job.spec.project_id),
            task_id=UUID(job.spec.task_id),
            operation_id=UUID(job.spec.operation_id),
            requested_by=job.spec.requested_by,
            source_artifact_id=UUID(job.original_source.artifact_id),
            source_artifact_version_id=UUID(
                job.original_source.artifact_version_id
            ),
            source_quality_result_id=UUID(job.spec.quality_result_id),
            original_branch_id=UUID(job.original_source.original_branch_id),
            original_head_version_id=UUID(
                job.original_source.original_head_version_id
            ),
            working_artifact_version_id=UUID(
                job.working_source.artifact_version_id
            ),
            current_quality_result_id=UUID(
                job.current_quality.quality_result_id
            ),
            policy_id=job.spec.policy.policy_id,
            policy_version=job.spec.policy.version,
            policy_hash=policy_hash,
            status=job.status.value,
            spent_usd=job.spent_usd,
            final_artifact_version_id=(
                UUID(job.final_artifact_version_id)
                if job.final_artifact_version_id is not None
                else None
            ),
            semantic_hash=job.spec.semantic_hash(),
            job_json=encode_job(job),
            reason_codes=list(job.reason_codes),
        )

    def _ensure_policy(self, policy: RepairPolicySnapshot) -> None:
        key = (policy.policy_id, policy.version)
        row = self.session.get(RepairPolicySnapshotModel, key)
        policy_hash = policy.semantic_hash()
        encoded = encode_policy(policy)
        if row is not None:
            if row.policy_hash != policy_hash or dict(row.policy_json) != encoded:
                raise AutoRepairOperationConflict(
                    "REPAIR_POLICY_VERSION_HASH_CONFLICT"
                )
            return
        self.session.add(
            RepairPolicySnapshotModel(
                policy_id=policy.policy_id,
                version=policy.version,
                policy_hash=policy_hash,
                policy_json=encoded,
            )
        )
        self.session.flush()

    def _sync_attempts(self, job: AutoRepairJob) -> None:
        for attempt in job.attempts:
            key = (UUID(job.job_id), attempt.iteration)
            row = self.session.get(AutoRepairAttemptModel, key)
            encoded = encode_attempt(attempt)
            if row is not None:
                if dict(row.attempt_json) != encoded:
                    raise AutoRepairOperationConflict(
                        "REPAIR_ATTEMPT_IS_APPEND_ONLY"
                    )
                continue
            self.session.add(self._attempt_row(job, attempt, encoded))
            self.session.flush()

    @staticmethod
    def _attempt_row(
        job: AutoRepairJob,
        attempt: RepairAttempt,
        encoded: dict,
    ) -> AutoRepairAttemptModel:
        candidate_id = (
            UUID(attempt.candidate.artifact_version_id)
            if attempt.candidate is not None
            else None
        )
        return AutoRepairAttemptModel(
            repair_job_id=UUID(job.job_id),
            iteration=attempt.iteration,
            organization_id=UUID(job.spec.organization_id),
            source_artifact_version_id=UUID(
                attempt.source_artifact_version_id
            ),
            before_quality_result_id=UUID(attempt.before_quality_result_id),
            repair_kind=attempt.plan.kind.value,
            decision=attempt.decision.value,
            estimated_cost_usd=attempt.plan.estimated_cost_usd,
            actual_cost_usd=attempt.actual_cost_usd,
            reservation_id=attempt.reservation_id,
            candidate_artifact_version_id=candidate_id,
            after_quality_result_id=(
                UUID(attempt.after_quality_result_id)
                if attempt.after_quality_result_id is not None
                else None
            ),
            promoted_artifact_version_id=(
                UUID(attempt.promoted_artifact_version_id)
                if attempt.promoted_artifact_version_id is not None
                else None
            ),
            promotion_quality_result_id=(
                UUID(attempt.promotion_quality_result_id)
                if attempt.promotion_quality_result_id is not None
                else None
            ),
            before_score=Decimal(str(attempt.before_score)),
            after_score=(
                Decimal(str(attempt.after_score))
                if attempt.after_score is not None
                else None
            ),
            score_delta=(
                Decimal(str(attempt.score_delta))
                if attempt.score_delta is not None
                else None
            ),
            attempt_json=encoded,
        )

    @staticmethod
    def _assert_same_operation(
        existing: AutoRepairJob,
        requested: AutoRepairJob,
    ) -> None:
        if existing.spec.semantic_hash() != requested.spec.semantic_hash():
            raise AutoRepairOperationConflict(
                "REPAIR_OPERATION_ID_REUSED_WITH_DIFFERENT_SPEC"
            )
