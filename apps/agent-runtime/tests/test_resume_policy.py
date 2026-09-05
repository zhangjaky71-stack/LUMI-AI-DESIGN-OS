from __future__ import annotations

import unittest
from datetime import UTC, datetime
from uuid import uuid4

from lumi_agent_runtime.control_plane.contracts import (
    GraphInterrupt,
    GraphRunSnapshot,
    GraphRunStatus,
    InterruptKind,
    ResumeDecision,
    ResumeRequest,
)
from lumi_agent_runtime.control_plane.errors import GraphResumeDeniedError
from lumi_agent_runtime.control_plane.resume_policy import (
    ApprovalDecisionRecord,
    PolicyResumeAuthorizer,
)


class ApprovalReader:
    def __init__(self, record: ApprovalDecisionRecord) -> None:
        self.record = record

    async def get_approval(self, approval_id):
        if approval_id != self.record.approval_id:
            raise KeyError(approval_id)
        return self.record


def current_snapshot(*, approval_id, organization_id, project_id, agent_run_id):
    now = datetime.now(UTC)
    return GraphRunSnapshot(
        organization_id=organization_id,
        project_id=project_id,
        agent_run_id=agent_run_id,
        task_id=None,
        thread_id="thread-1",
        graph_key="design.plan",
        graph_version="1.0.0",
        agent_config_version="agent-v1",
        status=GraphRunStatus.INTERRUPTED,
        checkpoint_id="cp-1",
        checkpoint_namespace="",
        state_values={},
        next_nodes=("review",),
        interrupts=(
            GraphInterrupt(
                interrupt_id="i-1",
                kind=InterruptKind.APPROVAL,
                namespace=("review",),
                node_name="review",
                payload={"approval_id": str(approval_id), "kind": "approval"},
                resumable=True,
            ),
        ),
        created_at=now,
        updated_at=now,
    )


class ResumePolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_durable_rejection_is_authorized_resume_with_rejected_value(self) -> None:
        organization_id = uuid4()
        project_id = uuid4()
        agent_run_id = uuid4()
        approval_id = uuid4()
        record = ApprovalDecisionRecord(
            approval_id=approval_id,
            organization_id=organization_id,
            project_id=project_id,
            agent_run_id=agent_run_id,
            status="rejected",
            decision_payload={"reason": "not ready"},
        )
        authorizer = PolicyResumeAuthorizer(approvals=ApprovalReader(record))
        current = current_snapshot(
            approval_id=approval_id,
            organization_id=organization_id,
            project_id=project_id,
            agent_run_id=agent_run_id,
        )
        result = await authorizer.authorize(
            ResumeRequest(
                organization_id=organization_id,
                project_id=project_id,
                agent_run_id=agent_run_id,
                operation_id=uuid4(),
                thread_id="thread-1",
                interrupt_id="i-1",
                decision=ResumeDecision.REJECTED,
                value={"forged": True},
            ),
            current=current,
        )
        self.assertTrue(result.approved)
        self.assertEqual(result.normalized_value["decision"], "rejected")
        self.assertEqual(result.normalized_value["payload"], {"reason": "not ready"})
        self.assertNotIn("forged", result.normalized_value)

    async def test_pending_approval_does_not_resume(self) -> None:
        organization_id = uuid4()
        project_id = uuid4()
        agent_run_id = uuid4()
        approval_id = uuid4()
        authorizer = PolicyResumeAuthorizer(
            approvals=ApprovalReader(
                ApprovalDecisionRecord(
                    approval_id=approval_id,
                    organization_id=organization_id,
                    project_id=project_id,
                    agent_run_id=agent_run_id,
                    status="pending",
                    decision_payload={},
                )
            )
        )
        result = await authorizer.authorize(
            ResumeRequest(
                organization_id=organization_id,
                project_id=project_id,
                agent_run_id=agent_run_id,
                operation_id=uuid4(),
                thread_id="thread-1",
                interrupt_id="i-1",
                decision=ResumeDecision.APPROVED,
                value=True,
            ),
            current=current_snapshot(
                approval_id=approval_id,
                organization_id=organization_id,
                project_id=project_id,
                agent_run_id=agent_run_id,
            ),
        )
        self.assertFalse(result.approved)
        self.assertEqual(result.reason, "approval is still pending")

    async def test_tenant_mismatch_is_denied(self) -> None:
        organization_id = uuid4()
        project_id = uuid4()
        agent_run_id = uuid4()
        approval_id = uuid4()
        authorizer = PolicyResumeAuthorizer(
            approvals=ApprovalReader(
                ApprovalDecisionRecord(
                    approval_id=approval_id,
                    organization_id=uuid4(),
                    project_id=project_id,
                    agent_run_id=agent_run_id,
                    status="approved",
                    decision_payload={},
                )
            )
        )
        with self.assertRaises(GraphResumeDeniedError):
            await authorizer.authorize(
                ResumeRequest(
                    organization_id=organization_id,
                    project_id=project_id,
                    agent_run_id=agent_run_id,
                    operation_id=uuid4(),
                    thread_id="thread-1",
                    interrupt_id="i-1",
                    decision=ResumeDecision.APPROVED,
                    value=True,
                ),
                current=current_snapshot(
                    approval_id=approval_id,
                    organization_id=organization_id,
                    project_id=project_id,
                    agent_run_id=agent_run_id,
                ),
            )


if __name__ == "__main__":
    unittest.main()
