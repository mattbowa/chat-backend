import re
import secrets
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.tenant import Tenant, TenantSettings
from app.models.user import User
from app.routers.deps import current_user
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserMe

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    slug = re.sub(r"[^a-z0-9-]", "", body.tenant_slug.lower().replace(" ", "-"))
    if not slug:
        raise HTTPException(400, "Invalid slug")

    existing = await db.execute(select(Tenant).where(Tenant.slug == slug))
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Slug already taken")

    email_taken = await db.execute(select(User).where(User.email == body.email))
    if email_taken.scalar_one_or_none():
        raise HTTPException(400, "Email already registered")

    tenant = Tenant(name=body.tenant_name, slug=slug)
    db.add(tenant)
    await db.flush()

    db.add(TenantSettings(tenant_id=tenant.id))

    user = User(
        tenant_id=tenant.id,
        email=body.email,
        hashed_password=hash_password(body.password),
        role="owner",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return TokenResponse(access_token=create_access_token(str(user.id)))


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    return TokenResponse(access_token=create_access_token(str(user.id)))


@router.get("/me", response_model=UserMe)
async def me(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
    tenant = result.scalar_one()
    return UserMe(
        id=str(user.id),
        email=user.email,
        role=user.role,
        tenant_id=str(tenant.id),
        tenant_name=tenant.name,
        tenant_slug=tenant.slug,
        plan=tenant.plan,
    )


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    password: str


@router.post("/forgot-password", status_code=200)
async def forgot_password(body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    # Always return 200 so we don't leak whether email exists
    if not user:
        return {"message": "If that email exists, a reset link has been sent."}

    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    await db.execute(
        text("INSERT INTO password_reset_tokens (token, user_id, expires_at) VALUES (:token, :user_id, :expires_at)"),
        {"token": token, "user_id": str(user.id), "expires_at": expires_at},
    )
    await db.commit()

    reset_url = f"http://localhost:3000/reset-password?token={token}"

    # TODO: replace print with real email sending (e.g. Resend)
    # import resend
    # resend.Emails.send({ "from": "...", "to": user.email, "subject": "Reset your password", "html": f"<a href='{reset_url}'>Reset password</a>" })
    print(f"\n🔑 PASSWORD RESET LINK for {user.email}:\n{reset_url}\n")

    return {"message": "If that email exists, a reset link has been sent."}


@router.post("/reset-password", status_code=200)
async def reset_password(body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("SELECT user_id, expires_at, used FROM password_reset_tokens WHERE token = :token"),
        {"token": body.token},
    )
    row = result.fetchone()

    if not row:
        raise HTTPException(400, "Invalid or expired reset link")
    if row.used:
        raise HTTPException(400, "Reset link has already been used")
    if row.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(400, "Reset link has expired")

    await db.execute(
        text("UPDATE users SET hashed_password = :pw WHERE id = :id"),
        {"pw": hash_password(body.password), "id": str(row.user_id)},
    )
    await db.execute(
        text("UPDATE password_reset_tokens SET used = TRUE WHERE token = :token"),
        {"token": body.token},
    )
    await db.commit()

    return {"message": "Password updated successfully"}
