import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, Float, Integer, ARRAY, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    plan: Mapped[str] = mapped_column(Enum("free", "pro", "enterprise", name="plan_enum"), default="free")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    users: Mapped[list["User"]] = relationship(back_populates="tenant")
    documents: Mapped[list["Document"]] = relationship(back_populates="tenant")
    settings: Mapped["TenantSettings"] = relationship(back_populates="tenant", uselist=False)


class TenantSettings(Base):
    __tablename__ = "tenant_settings"

    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True)
    system_prompt: Mapped[str] = mapped_column(Text, default="You are a helpful assistant. Answer questions based only on the provided context.")
    model: Mapped[str] = mapped_column(String(100), default="claude-sonnet-4-6")
    temperature: Mapped[float] = mapped_column(Float, default=0.3)
    top_k_chunks: Mapped[int] = mapped_column(Integer, default=5)
    max_response_tokens: Mapped[int] = mapped_column(Integer, default=1024)
    fallback_message: Mapped[str] = mapped_column(
        Text,
        default="I'm sorry, I don't have information about that.",
    )
    suggested_questions: Mapped[list] = mapped_column(ARRAY(String), default=list)
    # Branding
    bot_name: Mapped[str] = mapped_column(String(100), default="AI Assistant")
    primary_color: Mapped[str] = mapped_column(String(7), default="#2563eb")
    logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    tenant: Mapped["Tenant"] = relationship(back_populates="settings")
