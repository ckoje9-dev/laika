"""SQLAlchemy 테이블 정의 (필요 필드만 최소화)."""
from __future__ import annotations

from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import String, Boolean, Text, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID
import sqlalchemy as sa

Base = declarative_base()


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    purpose: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=sa.text("now()"))


class Version(Base):
    __tablename__ = "versions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    project_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    label: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=sa.text("now()"))


class File(Base):
    __tablename__ = "files"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True)
    version_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("versions.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    path_original: Mapped[str | None] = mapped_column(Text)
    path_dxf: Mapped[str | None] = mapped_column(Text)
    read_only: Mapped[bool] = mapped_column(Boolean, server_default=sa.text("false"), nullable=False)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=sa.text("now()"))
