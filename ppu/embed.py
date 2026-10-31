"""Эмбеддинги через OpenAI-совместимый API (polza.ai или llama-server).

Кэш на диске (SQLite, ключ — модель + текст): расчёт базы на CPU идёт
долго, при обрыве перезапуск продолжит с того же места, а одинаковые
тексты (например, название = полный текст у записей «только название»)
считаются один раз.
"""
import hashlib
import sqlite3
import sys
from pathlib import Path

import numpy as np
from openai import OpenAI

from .config import Endpoint

# bge-m3 держит 8192 токена; llama-server для эмбеддингов требует,
# чтобы текст влез в -ub, поэтому режем с запасом
MAX_CHARS = 4000


def _normalize(vecs: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    return (vecs / np.where(norms == 0, 1, norms)).astype(np.float32)


class Embedder:
    def __init__(self, endpoint: Endpoint, cache_path: str | Path | None = None,
                 batch_size: int = 32):
        if not endpoint.configured or not endpoint.model:
            raise ValueError("Эмбеддинги не настроены: задай EMB_BASE_URL и EMB_MODEL в .env")
        self.model = endpoint.model
        self.batch_size = batch_size
        self._client = OpenAI(base_url=endpoint.base_url, api_key=endpoint.api_key,
                              timeout=600)
        self._db = None
        if cache_path:
            Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(cache_path)
            self._db.execute("CREATE TABLE IF NOT EXISTS emb (key TEXT PRIMARY KEY, vec BLOB)")

    def _key(self, text: str) -> str:
        return hashlib.sha1(f"{self.model}\n{text}".encode()).hexdigest()

    def _cached(self, keys: list[str]) -> dict[str, np.ndarray]:
        if not self._db:
            return {}
        found = {}
        for i in range(0, len(keys), 500):
            chunk = keys[i:i + 500]
            rows = self._db.execute(
                f"SELECT key, vec FROM emb WHERE key IN ({','.join('?' * len(chunk))})", chunk
            )
            found.update((k, np.frombuffer(v, dtype=np.float32)) for k, v in rows)
        return found

    def _request(self, texts: list[str]) -> np.ndarray:
        resp = self._client.embeddings.create(model=self.model, input=texts)
        data = sorted(resp.data, key=lambda d: d.index)
        return _normalize(np.array([d.embedding for d in data], dtype=np.float32))

    def __call__(self, texts: list[str], progress: bool = False) -> np.ndarray:
        """Нормированные векторы (косинус = скалярное произведение)."""
        texts = [t[:MAX_CHARS] for t in texts]
        keys = [self._key(t) for t in texts]
        vecs = self._cached(keys)
        todo = list(dict.fromkeys(k for k in keys if k not in vecs))
        text_by_key = dict(zip(keys, texts))
        for i in range(0, len(todo), self.batch_size):
            batch = todo[i:i + self.batch_size]
            out = self._request([text_by_key[k] for k in batch])
            vecs.update(zip(batch, out))
            if self._db:
                self._db.executemany("INSERT OR REPLACE INTO emb VALUES (?, ?)",
                                     [(k, v.tobytes()) for k, v in zip(batch, out)])
                self._db.commit()
            if progress:
                print(f"\r  эмбеддинги: {min(i + self.batch_size, len(todo))}/{len(todo)}",
                      end="", file=sys.stderr, flush=True)
        if progress and todo:
            print(file=sys.stderr)
        return np.stack([vecs[k] for k in keys]) if keys else np.zeros((0, 0), np.float32)
