"""Retrieval QA 체인 (LangChain)."""
from __future__ import annotations

from typing import Sequence

from langchain.chains import RetrievalQA

from .config import get_embeddings, get_llm, MissingConfig
from .retriever import build_retriever


def build_qa_chain(project_id: str, *, kinds: Sequence[str] | None = None):
    try:
        embeddings = get_embeddings()
        llm = get_llm()
    except MissingConfig as e:
        raise RuntimeError(str(e))

    retriever = build_retriever(embeddings, project_id=project_id, kind_filter=kinds)
    chain = RetrievalQA.from_chain_type(
        llm=llm,
        retriever=retriever,
        return_source_documents=True,
        chain_type="stuff",
    )
    return chain
