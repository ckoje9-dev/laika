"""프로젝트/버전/파일 메타데이터 라우터."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from packages.core.src import models as schema
from packages.db.src import models as db_models
from packages.db.src.session import get_session

router = APIRouter(tags=["projects"])


@router.get("/", response_model=list[schema.Project])
async def list_projects(
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(db_models.Project).limit(limit).offset(offset))
    return result.scalars().all()


@router.post("/", response_model=schema.Project, status_code=201)
async def create_project(payload: schema.ProjectCreate, session: AsyncSession = Depends(get_session)):
    project = db_models.Project(name=payload.name, address=payload.address, purpose=payload.purpose)
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


@router.get("/{project_id}", response_model=schema.Project)
async def get_project(project_id: str, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(db_models.Project).where(db_models.Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="project not found")
    return project


@router.post("/{project_id}/versions", response_model=schema.Version, status_code=201)
async def create_version(project_id: str, payload: schema.VersionCreate | None = None, session: AsyncSession = Depends(get_session)):
    # 프로젝트 존재 확인
    exists = await session.execute(select(db_models.Project.id).where(db_models.Project.id == project_id))
    if exists.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="project not found")

    label = payload.label if payload else None
    version = db_models.Version(project_id=project_id, label=label)
    session.add(version)
    await session.commit()
    await session.refresh(version)
    return version


@router.get("/{project_id}/versions", response_model=list[schema.Version])
async def list_versions(project_id: str, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(db_models.Version).where(db_models.Version.project_id == project_id).order_by(db_models.Version.created_at))
    return result.scalars().all()


class FileWithVersion(schema.File):
    version_label: str | None = None

    class Config:
        from_attributes = True


@router.get("/{project_id}/files", response_model=list[FileWithVersion])
async def list_files(project_id: str, session: AsyncSession = Depends(get_session)):
    # 프로젝트 존재 확인
    exists = await session.execute(select(db_models.Project.id).where(db_models.Project.id == project_id))
    if exists.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="project not found")

    stmt = (
        select(db_models.File, db_models.Version.label)
        .join(db_models.Version, db_models.File.version_id == db_models.Version.id)
        .where(db_models.Version.project_id == project_id)
        .order_by(db_models.File.created_at)
    )
    result = await session.execute(stmt)
    rows = []
    for file_row, vlabel in result:
        item = FileWithVersion.from_orm(file_row)
        item.version_label = vlabel
        rows.append(item)
    return rows
