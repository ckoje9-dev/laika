"""프로젝트 RAG 인덱싱 파이프라인."""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.db.src.session import SessionLocal
from packages.db.src import models
from packages.llm.src.indexer import build_default_indexer, DocumentPayload

logger = logging.getLogger(__name__)


async def _build_project_documents(session: AsyncSession, project_id: str) -> list[DocumentPayload]:
    """프로젝트 메타데이터를 문서로 변환."""
    docs = []

    project = await session.get(models.Project, project_id)
    if not project:
        return docs

    project_text = f"""
    프로젝트명: {project.name}
    주소: {project.address or '미지정'}
    용도: {project.purpose or '미지정'}
    생성일: {project.created_at}
    """

    docs.append(DocumentPayload(
        project_id=project_id,
        version_id=None,
        file_id=None,
        kind="project_meta",
        text=project_text.strip(),
        metadata={
            "project_name": project.name,
            "address": project.address,
            "purpose": project.purpose
        }
    ))

    versions_result = await session.execute(
        select(models.Version).where(models.Version.project_id == project_id)
    )
    versions = versions_result.scalars().all()

    for version in versions:
        files_result = await session.execute(
            select(models.File).where(models.File.version_id == version.id)
        )
        files = files_result.scalars().all()

        for file in files:
            file_text = f"""
            파일 ID: {file.id}
            버전: {version.label or 'default'}
            타입: {file.type}
            레이어 수: {file.layer_count or 0}
            엔티티 수: {file.entity_count or 0}
            """

            docs.append(DocumentPayload(
                project_id=project_id,
                version_id=str(version.id),
                file_id=str(file.id),
                kind="drawing_stats",
                text=file_text.strip(),
                metadata={
                    "file_type": file.type,
                    "layer_count": file.layer_count or 0,
                    "entity_count": file.entity_count or 0
                }
            ))

    return docs


async def _build_semantic_documents(session: AsyncSession, project_id: str) -> list[DocumentPayload]:
    """시맨틱 객체를 종류별로 요약하여 문서 생성."""
    docs = []

    versions_result = await session.execute(
        select(models.Version).where(models.Version.project_id == project_id)
    )
    versions = versions_result.scalars().all()

    file_ids = []
    for version in versions:
        files_result = await session.execute(
            select(models.File).where(models.File.version_id == version.id)
        )
        files = files_result.scalars().all()
        file_ids.extend([str(f.id) for f in files])

    for file_id in file_ids:
        semantic_result = await session.execute(
            select(models.SemanticObject).where(
                models.SemanticObject.file_id == file_id
            )
        )
        objects = semantic_result.scalars().all()

        by_kind = {}
        for obj in objects:
            kind = obj.kind
            by_kind.setdefault(kind, []).append(obj)

        for kind, objs in by_kind.items():
            source_rules = set(o.source_rule for o in objs if o.source_rule)
            summary_text = f"""
            파일 ID: {file_id}
            객체 종류: {kind}
            개수: {len(objs)}
            검출 규칙: {', '.join(source_rules) if source_rules else '없음'}
            """

            docs.append(DocumentPayload(
                project_id=project_id,
                version_id=None,
                file_id=file_id,
                kind="semantic_summary",
                text=summary_text.strip(),
                metadata={
                    "object_kind": kind,
                    "count": len(objs),
                    "file_id": file_id
                }
            ))

    return docs


async def run(project_id: Optional[str] = None) -> None:
    """프로젝트를 벡터 DB에 인덱싱."""
    if not project_id:
        logger.error("project_id가 없어 인덱싱을 건너뜁니다.")
        return

    logger.info("프로젝트 인덱싱 시작: %s", project_id)

    async with SessionLocal() as session:
        project_docs = await _build_project_documents(session, project_id)
        semantic_docs = await _build_semantic_documents(session, project_id)

        all_docs = project_docs + semantic_docs
        logger.info("생성된 문서 수: %d", len(all_docs))

        if not all_docs:
            logger.warning("인덱싱할 문서가 없습니다.")
            return

        try:
            indexer = build_default_indexer()
            indexer.upsert(all_docs)
            logger.info("인덱싱 완료: %s (%d 문서)", project_id, len(all_docs))
        except Exception as e:
            logger.exception("인덱싱 실패: %s", e)
            raise
