from lumi_agent_runtime.recipe_engine.approval_bridge import resume_command, resume_payload
from lumi_project_core.approval import ApprovalResumeEnvelope


def test_resume_command_uses_exact_approval_and_subject_version():
    envelope = ApprovalResumeEnvelope(
        approval_id="approval-1",
        decision="APPROVE",
        status="APPROVED",
        subject_type="ARTIFACT_VERSION",
        subject_id="artifact-1",
        subject_version="artifact-v7",
        feedback=None,
    )
    command = resume_command(envelope)
    payload = resume_payload(envelope)
    assert command.resume["approval_id"] == "approval-1"
    assert payload["subject_version"] == "artifact-v7"
    assert payload["decision"] == "APPROVE"
