# pgvector 기반 + PostGIS 추가
FROM pgvector/pgvector:pg15

# PostGIS 설치
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        postgresql-15-postgis-3 \
        postgresql-15-postgis-3-scripts \
    && rm -rf /var/lib/apt/lists/*
