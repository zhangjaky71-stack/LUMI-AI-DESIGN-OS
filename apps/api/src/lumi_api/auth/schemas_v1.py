from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterRequest(StrictModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=1024)
    display_name: str = Field(min_length=1, max_length=200)
    organization_name: str = Field(min_length=1, max_length=200)
    organization_slug: str = Field(min_length=2, max_length=100)


class AcceptedResponse(StrictModel):
    accepted: bool = True


class VerifyEmailRequest(StrictModel):
    token: str = Field(min_length=32, max_length=2048)


class LoginRequest(StrictModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)
    organization_id: UUID | None = None


class LoginResponse(StrictModel):
    user_id: UUID
    organization_id: UUID
    csrf_token: str
    expires_at: datetime


class PasswordResetRequest(StrictModel):
    email: str = Field(min_length=3, max_length=320)


class PasswordResetConfirmRequest(StrictModel):
    token: str = Field(min_length=32, max_length=2048)
    new_password: str = Field(min_length=12, max_length=1024)


class InviteCreateRequest(StrictModel):
    email: str = Field(min_length=3, max_length=320)
    role: str = Field(pattern="^(OWNER|ADMIN|EDITOR|VIEWER|BILLING)$")


class InviteAcceptRequest(StrictModel):
    token: str = Field(min_length=32, max_length=2048)


class ApiTokenCreateRequest(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    scopes: list[str] = Field(min_length=1, max_length=100)
    expires_at: datetime | None = None


class ApiTokenCreateResponse(StrictModel):
    token_id: UUID
    token: str
    prefix: str


class MemberRoleUpdateRequest(StrictModel):
    role: str = Field(pattern="^(OWNER|ADMIN|EDITOR|VIEWER|BILLING)$")
