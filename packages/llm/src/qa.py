"""Retrieval QA 체인 스켈레톤 (LangChain)."""
from __future__ import annotations

from typing import Sequence

from langchain.chat_models import ChatOpenAI
from langchain.embeddings import OpenAIEmbeddings
from langchain.chains import RetrievalQA

from .retriever import build_retriever


def build_qa_chain(project_id: str, *, kinds: Sequence[str] | None = None):
    embeddings = OpenAIEmbeddings()  # OPENAI_API_KEY 필요
    retriever = build_retriever(embeddings, project_id=project_id, kind_filter=kinds)
    llm = ChatOpenAI(temperature=0)
    chain = RetrievalQA.from_chain_type(
        llm=llm,
        retriever=retriever,
        return_source_documents=True,
        chain_type="stuff",
    )
    return chain
