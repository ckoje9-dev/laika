# packages/db

- 애플리케이션 코드에서 DB 접근/ORM/쿼리 유틸을 두는 공간.
- 스키마 정의와 마이그레이션은 `infra/db` (Alembic)에서 관리하며, 모델/리포지토리는 이 패키지에서 구성.
- Python 예시 스택: SQLAlchemy + async (asyncpg/psycopg3).
