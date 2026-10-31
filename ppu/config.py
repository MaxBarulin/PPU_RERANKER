"""Настройки моделей из .env.

Один и тот же код работает и с polza.ai, и с llama.cpp на работе:
меняются только адреса и имена моделей в .env.
"""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Endpoint:
    base_url: str
    api_key: str
    model: str

    @property
    def configured(self) -> bool:
        return bool(self.base_url)


def _endpoint(prefix: str) -> Endpoint:
    return Endpoint(
        base_url=os.getenv(f"{prefix}_BASE_URL", "").rstrip("/"),
        # llama.cpp ключ не проверяет, но OpenAI-клиенту нужен непустой
        api_key=os.getenv(f"{prefix}_API_KEY", "") or "none",
        model=os.getenv(f"{prefix}_MODEL", ""),
    )


def llm() -> Endpoint:
    return _endpoint("LLM")


def embeddings() -> Endpoint:
    return _endpoint("EMB")


def reranker() -> Endpoint:
    return _endpoint("RERANK")
