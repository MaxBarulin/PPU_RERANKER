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


def test_security_headers_and_no_docs(monkeypatch):
    c = client(monkeypatch)
    r = c.get("/")
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["x-frame-options"] == "DENY" and r.headers["x-content-type-options"] == "nosniff"
    assert c.get("/api/info").headers["cache-control"] == "no-store"
    for url in ("/docs", "/redoc", "/openapi.json"):
        assert c.get(url).status_code == 404


def test_password_bruteforce_lockout(monkeypatch):
    c = client(monkeypatch)
    monkeypatch.setenv("PPU_ADMIN_TOKEN", "верный")
    monkeypatch.setattr(web, "_fails", {})
    from urllib.parse import quote
    good = {"X-Admin-Token": quote("верный")}
    # без пароля — не попытка подбора, не блокирует
    for _ in range(20):
        assert c.post("/api/admin/check").status_code == 403
    assert c.post("/api/admin/check", headers=good).status_code == 200
    for _ in range(web.MAX_FAILS):
        assert c.post("/api/admin/check", headers={"X-Admin-Token": "x"}).status_code == 403
    r = c.post("/api/admin/check", headers=good)
    assert r.status_code == 429 and "попыток" in r.json()["detail"]  # даже верный — после блокировки
    monkeypatch.setattr(web, "_fails", {})
    assert c.post("/api/admin/check", headers=good).status_code == 200


def test_label_field_limits(monkeypatch):
    c = client(monkeypatch)
    assert c.post("/api/label", json={"pair_id": "x" * 500, "label": "repeat"}).status_code == 422


def test_bad_llm_extra_body_disables_llm_only(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:1/v1")
    monkeypatch.setenv("LLM_MODEL", "m")
    monkeypatch.setenv("LLM_EXTRA_BODY", "{битый")
    web.judge.cache_clear()
    try:
        assert web.judge() is None
    finally:
        web.judge.cache_clear()


def test_assess_returns_more_and_matched_words(monkeypatch):
    c = client(monkeypatch)
    data = c.post("/api/assess", json={"name": "Ручки для напильников", "before": "мероприятие",
                                      "after": "мероприятие"}).json()
    found = data["candidates"] + data["more"]
    assert len({x["id"] for x in found}) == len(found)  # без повторов
    assert any("ручка" in x["matched"] or "напильник" in x["matched"] for x in found)
