"""LLM/임베딩 설정 로더."""
from __future__ import annotations

import os
from functools import lru_cache

from langchain.chat_models import ChatOpenAI
from langchain.embeddings import OpenAIEmbeddings
from langchain.embeddings.base import Embeddings


class MissingConfig(Exception):
    pass


@lru_cache(maxsize=1)
def get_embeddings() -> Embeddings:
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_EMBEDDINGS_MODEL", "text-embedding-3-small")
    if not api_key:
        raise MissingConfig("OPENAI_API_KEY가 설정되지 않았습니다.")
    return OpenAIEmbeddings(model=model, api_key=api_key)


@lru_cache(maxsize=1)
def get_llm():
    api_key = os.getenv("OPENAI_API_KEY")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    if not api_key:
        raise MissingConfig("OPENAI_API_KEY가 설정되지 않았습니다.")
    return ChatOpenAI(model=model, temperature=0, api_key=api_key)
