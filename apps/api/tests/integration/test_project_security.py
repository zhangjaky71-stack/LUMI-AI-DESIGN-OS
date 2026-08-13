from __future__ import annotations

import asyncio
import os
from collections.abc import Coroutine
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, TypeVar

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from lumi_auth import issue_opaque_token
from lumi_domain import new_uuid7
from sqlalchemy import delete

from lumi_api.api.v1.context import RequestContext
from lumi_api.persistence.models import Organization, OrganizationMember, Session, User
from lumi_api.persistence.seed import ORG_ID, USER_OWNER_ID
from lumi_api.persistence.session import create_engine, create_session_factory
from lumi_api.projects.security import get_secure_project_context

if os.environ.get("LUMI_DB_INTEGRATION") != "1":
    pytest.skip("set LUMI_DB_INTEGRATION=1 to run PostgreSQL tests", allow_module_level=True)

T = TypeVar("T")
ContextDep = Annotated[RequestContext, Depends(get_secure_project_context)]


def run(coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coroutine)


async def _prepare_security_fixtures():
    engine = create_engine()
    factory = create_session_factory(engine)
    owner_session = issue_opaque_token(label="session")
    owner_csrf = issue_opaque_token(label="csrf")
    viewer_session = issue_opaque_token(label="session")
    viewer_csrf = issue_opaque_token(label="csrf")
    viewer_id = new_uuid7()
    tenant_b = new_uuid7()
    owner_session_id = new_uuid7()
    viewer_session_id = new_uuid7()
    async with factory() as session:
        async with session.begin():
            session.add(
                Organization(
                    id=tenant_b,
                    name="Security Tenant B",
                    slug=f"security-tenant-b-{str(tenant_b)[-8:]}",
                    status="active",
                    plan="test",
                    settings_json={},
                )
            )
            session.add(
                User(
                    id=viewer_id,
                    email=f"viewer-{viewer_id}@lumi.local",
                    display_name="Project Security Viewer",
                    status="active",
                )
            )
            session.add(
                OrganizationMember(
                    id=new_uuid7(),
                    organization_id=ORG_ID,
                    user_id=viewer_id,
                    role="VIEWER",
                    status="active",
                )
            )
            now = datetime.now(UTC)
            session.add_all(
                [
                    Session(
                        id=owner_session_id,
                        user_id=USER_OWNER_ID,
                        organization_id=ORG_ID,
                        token_hash=owner_session.token_hash,
                        csrf_token_hash=owner_csrf.token_hash,
                        expires_at=now + timedelta(hours=1),
                        last_seen_at=now,
                        revoked=False,
                        ip_risk_metadata={},
                    ),
                    Session(
                        id=viewer_session_id,
                        user_id=viewer_id,
                        organization_id=ORG_ID,
                        token_hash=viewer_session.token_hash,
                        csrf_token_hash=viewer_csrf.token_hash,
                        expires_at=now + timedelta(hours=1),
                        last_seen_at=now,
                        revoked=False,
                        ip_risk_metadata={},
                    ),
                ]
            )
    return (
        engine,
        factory,
        owner_session.plaintext,
        owner_csrf.plaintext,
        viewer_session.plaintext,
        viewer_csrf.plaintext,
        viewer_id,
        tenant_b,
        owner_session_id,
        viewer_session_id,
    )


async def _cleanup_security_fixtures(
    factory,
    *,
    viewer_id,
    tenant_b,
    owner_session_id,
    viewer_session_id,
) -> None:
    async with factory() as session:
        async with session.begin():
            await session.execute(
                delete(Session).where(Session.id.in_([owner_session_id, viewer_session_id]))
            )
            await session.execute(
                delete(OrganizationMember).where(OrganizationMember.user_id == viewer_id)
            )
            await session.execute(delete(User).where(User.id == viewer_id))
            await session.execute(delete(Organization).where(Organization.id == tenant_b))


def test_project_security_requires_real_principal_tenant_membership_and_csrf() -> None:
    (
        engine,
        factory,
        owner_token,
        owner_csrf,
        viewer_token,
        viewer_csrf,
        viewer_id,
        tenant_b,
        owner_session_id,
        viewer_session_id,
    ) = run(_prepare_security_fixtures())

    app = FastAPI()
    app.state.project_session_factory = factory
    app.state.project_allowed_origins = frozenset({"http://localhost:3000"})

    @app.get("/probe")
    async def read_probe(context: ContextDep):
        return {
            "actor_id": str(context.actor_id),
            "organization_id": str(context.organization_id),
        }

    @app.post("/probe")
    async def write_probe(context: ContextDep):
        return {"actor_id": str(context.actor_id)}

    client = TestClient(app)
    org = str(ORG_ID)
    try:
        header_only = client.get("/probe", headers={"X-Lumi-Organization-Id": org})
        assert header_only.status_code == 401

        owner_read = client.get(
            "/probe",
            headers={"X-Lumi-Organization-Id": org},
            cookies={"lumi_session": owner_token},
        )
        assert owner_read.status_code == 200
        assert owner_read.json()["actor_id"] == str(USER_OWNER_ID)

        cross_tenant = client.get(
            "/probe",
            headers={"X-Lumi-Organization-Id": str(tenant_b)},
            cookies={"lumi_session": owner_token},
        )
        assert cross_tenant.status_code == 401

        missing_csrf = client.post(
            "/probe",
            headers={"X-Lumi-Organization-Id": org, "Origin": "http://localhost:3000"},
            cookies={"lumi_session": owner_token},
        )
        assert missing_csrf.status_code == 403
        assert missing_csrf.json()["code"] == "CSRF_VALIDATION_FAILED"

        owner_write = client.post(
            "/probe",
            headers={
                "X-Lumi-Organization-Id": org,
                "Origin": "http://localhost:3000",
                "X-CSRF-Token": owner_csrf,
            },
            cookies={"lumi_session": owner_token},
        )
        assert owner_write.status_code == 200

        viewer_read = client.get(
            "/probe",
            headers={"X-Lumi-Organization-Id": org},
            cookies={"lumi_session": viewer_token},
        )
        assert viewer_read.status_code == 200
        assert viewer_read.json()["actor_id"] == str(viewer_id)

        viewer_write = client.post(
            "/probe",
            headers={
                "X-Lumi-Organization-Id": org,
                "Origin": "http://localhost:3000",
                "X-CSRF-Token": viewer_csrf,
            },
            cookies={"lumi_session": viewer_token},
        )
        assert viewer_write.status_code == 403
        assert viewer_write.json()["code"] == "PERMISSION_DENIED"
    finally:
        run(
            _cleanup_security_fixtures(
                factory,
                viewer_id=viewer_id,
                tenant_b=tenant_b,
                owner_session_id=owner_session_id,
                viewer_session_id=viewer_session_id,
            )
        )
        run(engine.dispose())
