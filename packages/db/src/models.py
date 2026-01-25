"""SQLAlchemy 테이블 정의 (필요 필드만 최소화)."""
from __future__ import annotations

from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import Boolean, Text, ForeignKey, DateTime, Numeric, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
import sqlalchemy as sa
from geoalchemy2 import Geometry

Base = declarative_base()


SRID_WGS84 = 4326  # 프로젝트 위치는 WGS84 고정
SRID_LOCAL_CAD = 0  # CAD 로컬 좌표; 혼합 금지


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    address: Mapped[str | None] = mapped_column(Text)
    purpose: Mapped[str | None] = mapped_column(Text)
    location_geom = mapped_column(Geometry(geometry_type="POINT", srid=SRID_WGS84), nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=sa.text("now()"))


class Version(Base):
    __tablename__ = "versions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()"))
    project_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    label: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=sa.text("now()"))


class File(Base):
    __tablename__ = "files"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()"))
    version_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("versions.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    path_original: Mapped[str | None] = mapped_column(Text)
    path_dxf: Mapped[str | None] = mapped_column(Text)
    read_only: Mapped[bool] = mapped_column(Boolean, server_default=sa.text("false"), nullable=False)
    layer_count: Mapped[int | None] = mapped_column(Integer)
    entity_count: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=sa.text("now()"))


class ConversionLog(Base):
    __tablename__ = "conversion_logs"

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=True)
    file_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    tool_version: Mapped[str | None] = mapped_column(Text)
    message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)
    finished_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    width: Mapped[Numeric | None] = mapped_column(Numeric)
    height: Mapped[Numeric | None] = mapped_column(Numeric)
    layer_count: Mapped[int | None] = mapped_column(Integer)
    entity_count: Mapped[int | None] = mapped_column(Integer)


class DxfParseSection(Base):
    __tablename__ = "dxf_parse_sections"

    file_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), primary_key=True)
    header = mapped_column(JSONB, nullable=True)
    classes = mapped_column(JSONB, nullable=True)
    tables = mapped_column(JSONB, nullable=True)
    blocks = mapped_column(JSONB, nullable=True)
    entities = mapped_column(JSONB, nullable=True)
    objects = mapped_column(JSONB, nullable=True)
    thumbnail = mapped_column(JSONB, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=sa.text("now()"))


class SemanticObject(Base):
    __tablename__ = "semantic_objects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[Numeric | None] = mapped_column(Numeric)
    source_rule: Mapped[str | None] = mapped_column(Text)
    geom = mapped_column(Geometry(geometry_type="GEOMETRY", srid=SRID_LOCAL_CAD), nullable=True)
    properties = mapped_column(JSONB, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=sa.text("now()"))


class QaHistory(Base):
    __tablename__ = "qa_history"

    id: Mapped[int] = mapped_column(sa.BigInteger, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text)
    sources = mapped_column(JSONB, nullable=True)
    confidence: Mapped[Numeric | None] = mapped_column(Numeric)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=sa.text("now()"))
