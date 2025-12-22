# Laika Architecture

- Goal: DWG -> structured building data -> searchable projects -> LLM Q&A.
- Services: api (ingest/query), worker (pipeline jobs), converter (DWG->DXF), indexer (RAG).
- Storage: object storage for originals/derivatives, DB for metadata + parsed entities, vector store for RAG.
- Principles: DWG read-only; DXF is canonical for parsing/derivations; logs and statuses persisted.
