"""LLM/임베딩 설정 로더 (Anthropic Claude 사용)."""
from __future__ import annotations

import os
from functools import lru_cache

from langchain_anthropic import ChatAnthropic
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_core.embeddings import Embeddings


class MissingConfig(Exception):
    pass


@lru_cache(maxsize=1)
def get_embeddings() -> Embeddings:
    """임베딩 모델 반환 (HuggingFace 로컬 모델 사용)."""
    model_name = os.getenv("EMBEDDINGS_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    return HuggingFaceEmbeddings(
        model_name=model_name,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )


@lru_cache(maxsize=1)
def get_llm():
    """Claude LLM 반환."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
    if not api_key:
        raise MissingConfig("ANTHROPIC_API_KEY가 설정되지 않았습니다.")
    return ChatAnthropic(model=model, temperature=0, anthropic_api_key=api_key)
