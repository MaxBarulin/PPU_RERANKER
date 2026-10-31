"""Реранкер bge-reranker-v2-m3 через llama-server (--reranking).

Кросс-энкодер читает запрос и кандидата вместе, поэтому точнее векторов,
и на CPU в разы быстрее LLM. Сервер отдаёт сырые логиты — переводим
в вероятность сигмоидой, пороги задаём по вероятности.
"""
import math

import httpx

from .config import Endpoint

MAX_CHARS = 4000


def sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


class Reranker:
    def __init__(self, endpoint: Endpoint, timeout: float = 600):
        if not endpoint.configured:
            raise ValueError("Реранкер не настроен: задай RERANK_BASE_URL в .env")
        self.url = f"{endpoint.base_url}/rerank"
        self.model = endpoint.model
        self._client = httpx.Client(timeout=timeout,
                                    headers={"Authorization": f"Bearer {endpoint.api_key}"})

    def _post(self, payload: dict) -> dict:
        resp = self._client.post(self.url, json=payload)
        resp.raise_for_status()
        return resp.json()

    def __call__(self, query: str, documents: list[str]) -> list[float]:
        """Вероятность релевантности для каждого документа, в исходном порядке."""
        if not documents:
            return []
        payload = {"query": query[:MAX_CHARS],
                   "documents": [d[:MAX_CHARS] for d in documents],
                   "top_n": len(documents)}
        if self.model:
            payload["model"] = self.model
        scores = [0.0] * len(documents)
        for item in self._post(payload)["results"]:
            scores[item["index"]] = sigmoid(item["relevance_score"])
        return scores
