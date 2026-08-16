from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from .models import (
    ApiToken,
    AuthAuditEvent,
    BrowserSession,
    OrganizationMembership,
    OneTimeToken,
    PasswordCredential,
    User,
    WorkspaceMembership,
)


@dataclass(slots=True)
class MemoryAuthStore:
    users: dict[UUID, User] = field(default_factory=dict)
    user_id_by_email: dict[str, UUID] = field(default_factory=dict)
    credentials: dict[UUID, PasswordCredential] = field(default_factory=dict)
    sessions: dict[str, BrowserSession] = field(default_factory=dict)
    organization_memberships: dict[UUID, OrganizationMembership] = field(
        default_factory=dict
    )
    workspace_memberships: dict[UUID, WorkspaceMembership] = field(
        default_factory=dict
    )
    one_time_tokens: dict[str, OneTimeToken] = field(default_factory=dict)
    api_tokens: dict[str, ApiToken] = field(default_factory=dict)
    audit_events: list[AuthAuditEvent] = field(default_factory=list)

    def get_user_by_email(self, email: str) -> User | None:
        user_id = self.user_id_by_email.get(email.strip().casefold())
        return self.users.get(user_id) if user_id is not None else None

    def save_user(self, user: User) -> None:
        existing = self.user_id_by_email.get(user.email)
        if existing is not None and existing != user.id:
            raise ValueError("EMAIL_UNAVAILABLE")
        self.users[user.id] = user
        self.user_id_by_email[user.email] = user.id

    def save_credential(self, credential: PasswordCredential) -> None:
        self.credentials[credential.user_id] = credential

    def save_session(self, session: BrowserSession) -> None:
        self.sessions[session.id] = session

    def save_membership(self, membership: OrganizationMembership) -> None:
        for existing in self.organization_memberships.values():
            if (
                existing.organization_id == membership.organization_id
                and existing.user_id == membership.user_id
                and existing.id != membership.id
            ):
                raise ValueError("MEMBERSHIP_ALREADY_EXISTS")
        self.organization_memberships[membership.id] = membership

    def save_workspace_membership(self, membership: WorkspaceMembership) -> None:
        for existing in self.workspace_memberships.values():
            if (
                existing.workspace_id == membership.workspace_id
                and existing.user_id == membership.user_id
                and existing.id != membership.id
            ):
                raise ValueError("WORKSPACE_MEMBERSHIP_ALREADY_EXISTS")
        self.workspace_memberships[membership.id] = membership

    def memberships_for_user(self, user_id: UUID) -> tuple[OrganizationMembership, ...]:
        return tuple(
            membership
            for membership in self.organization_memberships.values()
            if membership.user_id == user_id
        )

    def memberships_for_organization(
        self, organization_id: UUID
    ) -> tuple[OrganizationMembership, ...]:
        return tuple(
            membership
            for membership in self.organization_memberships.values()
            if membership.organization_id == organization_id
        )

    def save_one_time_token(self, token: OneTimeToken) -> None:
        self.one_time_tokens[token.token_hash] = token

    def save_api_token(self, token: ApiToken) -> None:
        self.api_tokens[token.secret_hash] = token

    def append_audit(self, event: AuthAuditEvent) -> None:
        self.audit_events.append(event)
