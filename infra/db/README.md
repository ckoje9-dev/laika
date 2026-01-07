# laika DB (PostgreSQL + PostGIS)

- 마이그레이션: Alembic (경로: `infra/db/migrations`)
- 접속: `DATABASE_URL` 환경변수 사용 (예: `postgresql+psycopg://user:pass@localhost:5432/laika`)
- 확장: `postgis`, `"uuid-ossp"` 를 초기 마이그레이션에서 생성

실행 예시
```
cd infra/db
alembic upgrade head
```

구성
- `alembic.ini` : Alembic 설정
- `migrations/env.py` : DB 연결/컨텍스트
- `migrations/versions/0001_initial.py` : 초기 스키마 (projects, versions, files, conversion_logs, semantic_objects, project_stats, qa_history)
