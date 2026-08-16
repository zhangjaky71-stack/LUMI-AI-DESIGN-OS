from __future__ import annotations

import json
from pathlib import Path

from lumi_api.auth.models import (
    ApiToken,
    AuthAuditEvent,
    BrowserSession,
    OrganizationMembership,
    OneTimeToken,
    PasswordCredential,
    Principal,
    RequestContext,
    User,
    WorkspaceMembership,
)

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "reports" / "nodes" / "NODE-16" / "generated-schemas"

SCHEMAS = {
    "user-v1.schema.json": User.model_json_schema(),
    "password-credential-v1.schema.json": PasswordCredential.model_json_schema(),
    "browser-session-v1.schema.json": BrowserSession.model_json_schema(),
    "organization-membership-v1.schema.json": OrganizationMembership.model_json_schema(),
    "workspace-membership-v1.schema.json": WorkspaceMembership.model_json_schema(),
    "one-time-token-v1.schema.json": OneTimeToken.model_json_schema(),
    "api-token-v1.schema.json": ApiToken.model_json_schema(),
    "principal-v1.schema.json": Principal.model_json_schema(),
    "request-context-v1.schema.json": RequestContext.model_json_schema(),
    "auth-audit-event-v1.schema.json": AuthAuditEvent.model_json_schema(),
}


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, schema in SCHEMAS.items():
        path = OUTPUT / name
        path.write_text(
            json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
