import json

import httpx
import pytest
from fastapi.testclient import TestClient

from ppu.web import app as web
from ppu.web import proxy

LLM = "http://127.0.0.1:8003/v1"
EMB = "http://127.0.0.1:8004/v1"


@pytest.fixture
def seen(monkeypatch):
    """Подменяем модели: запросы записываем, отвечаем как llama.cpp."""
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        url = str(req.url)
        if url == f"{LLM}/models":
            return httpx.Response(200, json={"object": "list", "data": [{"id": "qwen", "object": "model"}]})
        if url == f"{EMB}/models":
            return httpx.Response(200, json={"object": "list", "data": [{"id": "bge-m3", "object": "model"}]})
        if url == f"{EMB}/embeddings":
            return httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2], "index": 0}]})
        if url == f"{LLM}/chat/completions":
            body = json.loads(req.content)
            if body.get("stream"):
                sse = b"".join(f"data: {json.dumps({'n': i})}\n\n".encode() for i in range(3)) + b"data: [DONE]\n\n"
                return httpx.Response(200, content=sse, headers={"content-type": "text/event-stream"})
            if not body.get("messages"):
                return httpx.Response(400, json={"error": {"message": "messages required"}})
            return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})
        return httpx.Response(404, json={"error": "not found"})

    monkeypatch.setenv("LLM_BASE_URL", LLM)
    monkeypatch.setenv("EMB_BASE_URL", EMB)
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("EMB_API_KEY", "")
    monkeypatch.delenv("PPU_API_TOKEN", raising=False)
    monkeypatch.setattr(proxy, "_transport", httpx.MockTransport(handler))
    monkeypatch.setattr(proxy, "_client", None)
    return calls


def test_chat_goes_to_llm_as_is(seen):
    body = {"model": "qwen", "messages": [{"role": "user", "content": "Привет"}]}
    r = TestClient(web.app).post("/v1/chat/completions", json=body, headers={"Authorization": "Bearer client-key"})
    assert r.status_code == 200 and r.json()["choices"][0]["message"]["content"] == "ok"
    req = seen[-1]
    assert str(req.url) == f"{LLM}/chat/completions" and json.loads(req.content) == body
    # ключ клиента к модели не уходит
    assert "authorization" not in req.headers
    assert r.headers["cache-control"] == "no-store"


def test_stream_passes_through_uncompressed(seen):
    r = TestClient(web.app).post("/v1/chat/completions", headers={"Accept-Encoding": "gzip"},
                                 json={"model": "qwen", "stream": True, "messages": [{"role": "user", "content": "x"}]})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    assert "content-encoding" not in r.headers
    assert r.text.count("data: ") == 4 and r.text.endswith("data: [DONE]\n\n")


def test_embeddings_go_to_embedding_model(seen):
    r = TestClient(web.app).post("/v1/embeddings", json={"model": "bge-m3", "input": ["ручки"]})
    assert r.status_code == 200 and r.json()["data"][0]["embedding"] == [0.1, 0.2]
    assert str(seen[-1].url) == f"{EMB}/embeddings"


def test_models_lists_both_and_survives_one_down(seen, monkeypatch):
    ids = [m["id"] for m in TestClient(web.app).get("/v1/models").json()["data"]]
    assert ids == ["qwen", "bge-m3"]
    monkeypatch.setenv("EMB_BASE_URL", "")
    assert [m["id"] for m in TestClient(web.app).get("/v1/models").json()["data"]] == ["qwen"]


def test_model_errors_are_passed_back(seen):
    r = TestClient(web.app).post("/v1/chat/completions", json={"model": "qwen", "messages": []})
    assert r.status_code == 400 and r.json()["error"]["message"] == "messages required"


def test_model_down_is_502(seen, monkeypatch):
    def down(req):
        raise httpx.ConnectError("refused")
    monkeypatch.setattr(proxy, "_transport", httpx.MockTransport(down))
    monkeypatch.setattr(proxy, "_client", None)
    r = TestClient(web.app).post("/v1/embeddings", json={"input": "x"})
    assert r.status_code == 502 and "недоступна" in r.json()["detail"]


def test_optional_key(seen, monkeypatch):
    monkeypatch.setenv("PPU_API_TOKEN", "sekret-1")
    c = TestClient(web.app)
    assert c.get("/v1/models").status_code == 401
    assert c.get("/v1/models", headers={"Authorization": "Bearer wrong"}).status_code == 401
    ok = c.post("/v1/embeddings", json={"input": "x"}, headers={"Authorization": "Bearer sekret-1"})
    assert ok.status_code == 200 and "authorization" not in seen[-1].headers


def test_remote_paid_model_not_exposed_without_key(seen, monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("LLM_API_KEY", "платный")
    r = TestClient(web.app).post("/v1/chat/completions", json={"messages": [{"role": "user", "content": "x"}]})
    assert r.status_code == 503 and not seen
