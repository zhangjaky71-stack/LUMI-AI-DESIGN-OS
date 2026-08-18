from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"NODE61_STATIC_ACCEPTANCE_FAIL: {message}")


def main() -> None:
    migration = read("apps/api/migrations/versions/20260818_0021_collaboration.py")
    up_sql = read("apps/api/migrations/versions/20260818_0021_sql/up.sql")
    schemas = read("apps/api/src/lumi_api/api/v1/collaboration_schemas.py")
    routes = read("apps/api/src/lumi_api/api/v1/collaboration_routes.py")
    repository = read("apps/api/src/lumi_api/collaboration/repository.py")
    service = read("apps/api/src/lumi_api/collaboration/service.py")
    workspace = read("apps/web/src/components/workspace/ai-workspace.tsx")
    comments = read("apps/web/src/components/collaboration/comments-panel.tsx")
    ledger = json.loads(read("reports/nodes/NODE-61/gap-ledger.json"))

    require('down_revision = "20260818_0020"' in migration, "migration must extend NODE-60 schema head")
    require("CREATE TABLE comment_threads" in up_sql, "comment_threads table missing")
    require("CREATE TABLE comments" in up_sql, "comments table missing")
    require("CREATE TABLE comment_revisions" in up_sql, "comment_revisions table missing")
    require("presence" not in up_sql.casefold(), "presence must never become durable SQL truth")
    require("artifact_version_id UUID NOT NULL" in up_sql, "thread exact ArtifactVersion binding missing")

    require("display_name" not in schemas.split("class PresenceHeartbeatRequest", 1)[1], "presence display_name must not be client supplied")
    require("avatar_url" not in schemas.split("class PresenceHeartbeatRequest", 1)[1], "presence avatar_url must not be client supplied")
    require("user_id" not in schemas.split("class PresenceHeartbeatRequest", 1)[1], "presence user_id must not be client supplied")
    require("get_presence_identity" in service, "service must derive canonical presence identity")
    require("FROM users u" in repository and "organization_members" in repository, "presence profile must be organization-scoped canonical user data")

    forbidden_design_bypass = (
        "CanvasCommandBatchRequest",
        "DesignOperation",
        "design_document_service",
        "UPDATE design_",
        "INSERT INTO design_",
    )
    for marker in forbidden_design_bypass:
        require(marker not in routes, f"collaboration route must not mutate Design truth: {marker}")

    require("if_match: IfMatch" in routes, "comment mutation If-Match fence missing")
    require("artifact_version_id=body.artifact_version_id" in routes, "thread creation must carry exact ArtifactVersion")
    require("CommentsPanel" in workspace, "CommentsPanel not mounted in Workspace")
    require("artifact={selectedArtifact}" in workspace, "CommentsPanel must receive selected exact artifact")
    require("selectedNodeIds={canvasSelection?.nodeIds ?? []}" in workspace, "CommentsPanel Canvas anchor context missing")
    require("includeHistory: true" in comments, "Workspace comments must expose historical threads")
    require("NEEDS RE-ANCHOR" in comments, "historical thread re-anchor warning missing")

    require(ledger["node"] == "NODE-61", "gap ledger node mismatch")
    require(ledger["status"] == "CORE_IMPLEMENTED_VALIDATING_NOT_COMPLETE", "gap ledger status mismatch")
    require(any(gap["status"] == "open" and gap["severity"] == "P0" for gap in ledger["gaps"]), "open P0 gaps must remain explicit")
    require(any(gap["id"] == "NODE61-GAP-003" and gap["status"] == "closed" for gap in ledger["gaps"]), "server-authoritative presence identity gap should be closed")
    require(any(gap["id"] == "NODE61-GAP-004" and gap["status"] == "closed" for gap in ledger["gaps"]), "Workspace mounting gap should be closed")

    print("NODE61_STATIC_ACCEPTANCE_PASS")


if __name__ == "__main__":
    main()
