"""FastAPI 엔트리포인트.

앱 책임
- 프로젝트/버전/파일 메타데이터 CRUD
- 업로드 초기화 및 변환 상태 조회
- RAG 기반 질의응답 엔드포인트
"""
from fastapi import FastAPI

try:
    from apps.api.src.routes import projects, uploads, queries  # type: ignore
except ModuleNotFoundError:
    projects = uploads = queries = None  # type: ignore


def create_app() -> FastAPI:
    app = FastAPI(title="laika API", version="0.1.0")

    if projects and hasattr(projects, "router"):
        app.include_router(projects.router, prefix="/projects")
    if uploads and hasattr(uploads, "router"):
        app.include_router(uploads.router, prefix="/uploads")
    if queries and hasattr(queries, "router"):
        app.include_router(queries.router, prefix="/queries")

    @app.get("/health", tags=["health"])
    def health():
        return {"status": "ok"}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
