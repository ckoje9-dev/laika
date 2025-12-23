"""pgvector 기반 Retriever 생성."""
from __future__ import annotations

import os
from typing import Any, Mapping, Sequence

from langchain.vectorstores.pgvector import PGVector
from langchain.schema import Document
from langchain.embeddings.base import Embeddings

from .config import get_embeddings, MissingConfig


def _connection_string() -> str:
    url = os.getenv("VECTOR_STORE_URL", "")
    if not url:
        raise RuntimeError("VECTOR_STORE_URL이 설정되지 않았습니다.")
    return url


def build_retriever(
    embeddings: Embeddings,
    collection_name: str = "laika_rag",
    *,
    project_id: str,
    k: int = 5,
    kind_filter: Sequence[str] | None = None,
) -> Any:
    store = PGVector(
        connection_string=_connection_string(),
        collection_name=collection_name,
        embedding_function=embeddings,
    )
    filter_meta: Mapping[str, Any] = {"project_id": project_id}
    if kind_filter:
        filter_meta["kind"] = {"$in": list(kind_filter)}
    retriever = store.as_retriever(search_kwargs={"k": k, "filter": filter_meta})
    return retriever


def build_default_retriever(project_id: str, collection_name: str = "laika_rag", *, k: int = 5, kind_filter: Sequence[str] | None = None):
    try:
        embeddings = get_embeddings()
    except MissingConfig as e:
        raise RuntimeError(str(e))
    return build_retriever(
        embeddings=embeddings,
        collection_name=collection_name,
        project_id=project_id,
        k=k,
        kind_filter=kind_filter,
    )
