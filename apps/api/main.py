"""FastAPI 엔트리포인트.

앱 책임
- 프로젝트/버전/파일 메타데이터 CRUD
- 업로드 초기화 및 변환 상태 조회
- RAG 기반 질의응답 엔드포인트
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

try:
    # apps.api.src.routes.__init__에서 router 객체를 export함
    from apps.api.src.routes import uploads, queries  # type: ignore
except ModuleNotFoundError:
    uploads = queries = None  # type: ignore


def create_app() -> FastAPI:
    app = FastAPI(title="laika API", version="0.1.0")

    # 개발/도메인 테스트용 CORS 허용 (필요 시 환경변수 기반으로 조정)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # convert/parsing/queries 라우터
    if uploads:
        app.include_router(uploads.convert_router, prefix="/convert")
        app.include_router(uploads.parsing_router, prefix="/parsing")
    if queries:
        app.include_router(queries, prefix="/create/queries")

    @app.get("/health", tags=["health"])
    def health():
        return {"status": "ok"}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
