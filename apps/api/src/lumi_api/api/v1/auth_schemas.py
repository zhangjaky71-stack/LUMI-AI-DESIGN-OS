from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AuthHttpModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterRequest(AuthHttpModel):
    email: str = Field(min_length=3, max_length=320)
    display_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=12, max_length=1024)


class LoginRequest(AuthHttpModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class UserResponse(AuthHttpModel):
    id: UUID
    email: str
    display_name: str


class LoginResponse(AuthHttpModel):
    user_id: UUID
    authenticated: bool = True


class PrincipalResponse(AuthHttpModel):
    actor_id: str
    user_id: UUID | None
    organization_id: UUID
    roles: tuple[str, ...]
    permissions: tuple[str, ...]


class LogoutResponse(AuthHttpModel):
    logged_out: bool = True
