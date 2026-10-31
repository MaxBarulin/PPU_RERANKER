from fastapi.testclient import TestClient

from ppu.index import build_index
from ppu.judge import Judge
from ppu.web import app as web

from test_judge import FakeLLM
from test_search import REGISTRY, fake_embed


def client(monkeypatch, llm=None):
    index = build_index(REGISTRY, fake_embed)
    monkeypatch.setattr(web, "engine", lambda: (index, fake_embed))
    monkeypatch.setattr(web, "judge", lambda: Judge(llm) if llm else None)
    return TestClient(web.app)


def test_page_and_info(monkeypatch):
    c = client(monkeypatch)
    assert "Проверка ППУ" in c.get("/").text
    assert c.get("/api/info").json()["records"] == len(REGISTRY)


def test_assess(monkeypatch):
    r = client(monkeypatch).post("/api/assess", json={"name": "Ручки для напильников",
                                                       "before": REGISTRY[0]["before"]})
    data = r.json()
    assert r.status_code == 200 and data["candidates"][0]["id"] == "1"
    assert data["judged_by"] == "vectors" and data["query"]["completeness"] == "partial"


def test_validation(monkeypatch):
    assert client(monkeypatch).post("/api/assess", json={"name": "a"}).status_code == 422


def test_judge_endpoint(monkeypatch):
    llm = FakeLLM({"items": [{"id": "3", "v": "dup", "why": "тот же контейнер"}]})
    r = client(monkeypatch, llm).post("/api/judge", json={"name": "Ящик для хранения шаблонов"})
    data = r.json()
    assert data["judged_by"] == "llm" and data["verdict"] == "repeat"
    assert data["candidates"][0]["llm"]["why"] == "тот же контейнер"


def test_judge_without_llm(monkeypatch):
    r = client(monkeypatch).post("/api/judge", json={"name": "Ящик для шаблонов"})
    assert r.status_code == 503
