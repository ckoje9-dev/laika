"""Pydantic 스키마 정의."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    address: Optional[str] = None
    purpose: Optional[str] = None


class Project(ProjectCreate):
    id: str

    class Config:
        from_attributes = True


class VersionCreate(BaseModel):
    project_id: str
    label: Optional[str] = None


class Version(VersionCreate):
    id: str

    class Config:
        from_attributes = True


class FileCreate(BaseModel):
    version_id: str
    type: str
    path_original: Optional[str] = None
    path_dxf: Optional[str] = None
    read_only: bool = False


class File(FileCreate):
    id: str

    class Config:
        from_attributes = True
