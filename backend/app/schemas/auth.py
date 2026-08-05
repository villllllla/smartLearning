"""Auth API schemas."""
from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=200)


class RegisterRequest(BaseModel):
    tenant_name: str = Field(min_length=2, max_length=200)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=200)
    display_name: str = Field(default="", max_length=120)


class AuthUserOut(BaseModel):
    id: int
    email: str
    display_name: str
    role: str
    tenant_id: int
    tenant_name: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AuthUserOut


class MeResponse(BaseModel):
    user: AuthUserOut
    auth_enabled: bool


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)
