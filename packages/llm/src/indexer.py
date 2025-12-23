"""RAG 인덱서 (pgvector) 스켈레톤."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from langchain.vectorstores.pgvector import PGVector
from langchain.embeddings.base import Embeddings


def _connection_string() -> str:
    url = os.getenv("VECTOR_STORE_URL", "")
    if not url:
        raise RuntimeError("VECTOR_STORE_URL이 설정되지 않았습니다.")
    return url


@dataclass
class DocumentPayload:
    project_id: str
    version_id: str | None
    file_id: str | None
    kind: str  # e.g., project_meta, drawing_stats, semantic_summary
    text: str
    metadata: Mapping[str, Any]


class VectorIndexer:
    """pgvector 인덱서 래퍼."""

    def __init__(self, embeddings: Embeddings, collection_name: str = "laika_rag") -> None:
        self.embeddings = embeddings
        self.collection_name = collection_name
        self.store = PGVector(
            connection_string=_connection_string(),
            collection_name=collection_name,
            embedding_function=embeddings,
        )

    def upsert(self, docs: Iterable[DocumentPayload]) -> None:
        texts = [d.text for d in docs]
        metadatas = []
        for d in docs:
            meta = dict(d.metadata)
            meta.update(
                {
                    "project_id": d.project_id,
                    "version_id": d.version_id,
                    "file_id": d.file_id,
                    "kind": d.kind,
                }
            )
            metadatas.append(meta)
        self.store.add_texts(texts=texts, metadatas=metadatas)
