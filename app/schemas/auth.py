from pydantic import BaseModel, EmailStr


class RegisterRequest(BaseModel):
    tenant_name: str
    tenant_slug: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserMe(BaseModel):
    id: str
    email: str
    role: str
    tenant_id: str
    tenant_name: str
    tenant_slug: str
    plan: str
