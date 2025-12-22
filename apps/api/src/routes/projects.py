"""프로젝트/버전/파일 메타데이터 라우터."""
from fastapi import APIRouter

router = APIRouter(tags=["projects"])


@router.get("/")
async def list_projects():
    # TODO: DB 연동 후 프로젝트 목록 반환
    return {"items": [], "total": 0}


@router.post("/")
async def create_project():
    # TODO: 입력 검증 및 프로젝트 생성 로직
    return {"id": "project-id-placeholder"}


@router.get("/{project_id}")
async def get_project(project_id: str):
    # TODO: 단일 프로젝트 조회
    return {"id": project_id}


@router.post("/{project_id}/versions")
async def create_version(project_id: str):
    # TODO: 버전 생성 및 파일 메타데이터 초기화
    return {"project_id": project_id, "version_id": "version-id-placeholder"}
