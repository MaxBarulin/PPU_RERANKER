import io
import time

import numpy as np
import openpyxl
import pytest
from fastapi.testclient import TestClient

from ppu import embed as embed_mod
from ppu.config import Endpoint
from ppu.embed import Embedder
from ppu.index import load_index
from ppu.rebuild import rebuild
from ppu.web import app as web

from test_search import fake_embed

RAW = [
    {"id": "1", "name": "Ручки для напильников",
     "before": "Ручки напильников развалились, можно травмировать руки.",
     "after": "Изготовлены новые деревянные ручки.", "proposal": None, "result": None},
    {"id": "2", "name": "Ящик для хранения шаблонов",
     "before": "Шаблоны лежат на столе и теряются.", "after": "Сделан ящик с ячейками.",
     "proposal": None, "result": None},
    {"id": "3", "name": "Подставка под паяльник", "before": None, "after": None,
     "proposal": None, "result": None},
]


class FakeEmbedder:
    def __init__(self, *args, **kwargs):
        pass

    def __call__(self, texts, progress=False):
        if callable(progress):
            progress(len(texts), len(texts))
        return fake_embed(texts)


def test_rebuild_swaps_index(tmp_path):
    out = tmp_path / "index"
    stages = []
    meta = rebuild(RAW, out, FakeEmbedder(), "fake", source="реестр.xlsx",
                   progress=lambda **kw: stages.append(kw["stage"]))
    assert meta["count"] == 3 and meta["source"] == "реестр.xlsx" and "Записей: 3" in meta["report"]
    assert any(s.startswith("Векторы") for s in stages)
    assert len(load_index(out)) == 3

    rebuild(RAW[:2], out, FakeEmbedder(), "fake")
    assert len(load_index(out)) == 2
    assert sorted(p.name for p in tmp_path.iterdir()) == ["index"]  # без .new / .old


def test_rebuild_empty_registry(tmp_path):
    with pytest.raises(ValueError):
        rebuild([], tmp_path / "index", FakeEmbedder())
    assert not (tmp_path / "index").exists()


def test_embedder_progress_and_cache(tmp_path):
    calls = []
    e = Embedder(Endpoint("http://127.0.0.1:1/v1", "none", "m"), cache_path=tmp_path / "c.sqlite",
                 batch_size=2)
    e._request = lambda texts: (calls.append(len(texts)), fake_embed(texts))[1]
    seen = []
    e(["раз", "два", "три", "раз"], progress=lambda d, t: seen.append((d, t)))
    assert calls == [2, 1] and seen[0] == (0, 3) and seen[-1] == (3, 3)
    seen.clear()
    e(["раз", "четыре"], progress=lambda d, t: seen.append((d, t)))
    assert calls == [2, 1, 1] and seen == [(1, 2), (2, 2)]  # «раз» - из кэша


def xlsx_bytes(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Рег. №", "Наименование", "До улучшения", "После улучшения", "Предложения", "Статус"])
    for r in rows:
        ws.append([r["id"], r["name"], r["before"], r["after"], r["proposal"], "Принято"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("PPU_INDEX", str(tmp_path / "index"))
    monkeypatch.setenv("PPU_REGISTRY", str(tmp_path / "registry.xlsx"))
    monkeypatch.setenv("PPU_EMB_CACHE", str(tmp_path / "cache.sqlite"))
    monkeypatch.delenv("PPU_ADMIN_TOKEN", raising=False)
    monkeypatch.setattr(embed_mod, "Embedder", FakeEmbedder)
    monkeypatch.setattr(web, "Embedder", FakeEmbedder)
    monkeypatch.setattr(web, "JOB", web.Job())
    monkeypatch.setattr(web, "judge", lambda: None)
    web.engine.cache_clear()
    web._records_by_id.cache_clear()
    yield TestClient(web.app)
    web.engine.cache_clear()
    web._records_by_id.cache_clear()


def wait_job(c):
    for _ in range(200):
        s = c.get("/api/index/status").json()
        if s["status"] != "running":
            return s
        time.sleep(0.05)
    raise AssertionError("сборка не закончилась")


def test_web_without_index(app_client):
    info = app_client.get("/api/info").json()
    assert info["index"] is False and info["records"] == 0
    r = app_client.post("/api/assess", json={"name": "Ручки для напильников"})
    assert r.status_code == 503 and "/admin" in r.json()["detail"]
    assert "Обновление базы" in app_client.get("/admin").text


def test_upload_builds_and_reloads(app_client):
    c = app_client
    r = c.post("/api/index/upload?filename=Реестр.xlsx", content=xlsx_bytes(RAW))
    assert r.status_code == 200, r.text
    s = wait_job(c)
    assert s["status"] == "done" and s["records"] == 3 and s["registry"] == "Реестр.xlsx"
    info = c.get("/api/info").json()
    assert info["index"] and info["records"] == 3 and info["source"] == "Реестр.xlsx"
    r = c.post("/api/assess", json={"name": "Ручки для напильников", "before": RAW[0]["before"]})
    assert r.status_code == 200 and r.json()["candidates"][0]["id"] == "1"

    # новый реестр подменяет базу без перезапуска веба
    c.post("/api/index/upload?filename=new.xlsx", content=xlsx_bytes(RAW[:2]))
    wait_job(c)
    assert c.get("/api/info").json()["records"] == 2

    assert c.post("/api/index/rebuild").status_code == 200
    assert wait_job(c)["status"] == "done"


def test_upload_bad_file(app_client):
    c = app_client
    assert c.post("/api/index/upload?filename=r.xls", content=b"x").status_code == 422
    assert c.post("/api/index/upload?filename=r.xlsx", content=b"").status_code == 422
    c.post("/api/index/upload?filename=r.xlsx", content=b"not excel")
    s = wait_job(c)
    assert s["status"] == "error" and s["error"]
    assert c.get("/api/info").json()["index"] is False


def test_upload_token(app_client, monkeypatch):
    from urllib.parse import quote
    monkeypatch.setenv("PPU_ADMIN_TOKEN", "секрет 1")
    ok = {"X-Admin-Token": quote("секрет 1")}  # так кодирует браузер (encodeURIComponent)
    c = app_client
    assert c.get("/api/admin/auth").json() == {"required": True}
    assert c.post("/api/admin/check").status_code == 403
    assert c.post("/api/admin/check", headers={"X-Admin-Token": "неверно".encode().hex()}).status_code == 403
    assert c.post("/api/admin/check", headers=ok).json() == {"ok": True}
    assert c.get("/api/index/status").status_code == 403
    assert c.get("/api/index/status", headers=ok).json()["token_required"]
    assert c.post("/api/index/upload?filename=r.xlsx", content=xlsx_bytes(RAW)).status_code == 403
    assert c.post("/api/index/upload?filename=r.xlsx", content=xlsx_bytes(RAW), headers=ok).status_code == 200
    for _ in range(200):
        if c.get("/api/index/status", headers=ok).json()["status"] != "running":
            break
        time.sleep(0.05)
    assert c.post("/api/index/rebuild").status_code == 403
    # проверка ППУ и страницы - без пароля
    assert c.get("/api/info").status_code == 200
    assert c.post("/api/assess", json={"name": "Ручки для напильников"}).status_code == 200
    assert c.get("/admin").status_code == 200 and c.get("/label").status_code == 200


def test_without_token_everything_open(app_client):
    assert app_client.get("/api/admin/auth").json() == {"required": False}
    assert app_client.post("/api/admin/check").json() == {"ok": True}


def test_no_numpy_handles_left(tmp_path):
    # load_index закрывает vectors.npz - папку индекса можно заменить (важно на Windows)
    rebuild(RAW, tmp_path / "index", FakeEmbedder())
    index = load_index(tmp_path / "index")
    (tmp_path / "index").rename(tmp_path / "moved")
    assert isinstance(index.vectors["full"], np.ndarray)
