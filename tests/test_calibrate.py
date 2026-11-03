import json

import numpy as np
from fastapi.testclient import TestClient

from ppu import calibrate
from ppu.assess import DEFAULT_CALIBRATION, assess, load_calibration
from ppu.index import build_index
from ppu.search import make_query
from ppu.web import app as web

from test_search import REGISTRY, fake_embed


def row(dense, label, problem=None, solution=None):
    cos = {"full": dense, "name": dense}
    if problem is not None:
        cos.update(problem=problem, solution=solution)
    return {"dense": dense, "cos": cos, "completeness": "full", "place": "unknown", "label": label}


def test_fit_puts_same_threshold_between_classes():
    rng = np.random.default_rng(0)
    rows = [row(float(d), "repeat") for d in rng.uniform(0.80, 0.92, 30)] + \
           [row(float(d), "different") for d in rng.uniform(0.58, 0.72, 30)]
    cal, notes = calibrate.fit(rows)
    assert 0.72 <= cal.with_text.same <= 0.80
    assert cal.with_text.similar <= cal.with_text.same <= cal.with_text.gray_hi
    assert "разметка" in cal.source


def test_fit_learns_alternative_rule():
    rows = [row(0.8, "repeat", problem=0.85, solution=0.85) for _ in range(10)] + \
           [row(0.72, "alternative", problem=0.84, solution=0.62) for _ in range(10)] + \
           [row(0.62, "different", problem=0.6, solution=0.6) for _ in range(10)]
    cal, _ = calibrate.fit(rows)
    assert cal.alt_problem_min <= 0.84 and 0.62 < cal.alt_solution_max <= 0.85


def test_fit_keeps_defaults_without_enough_labels():
    cal, notes = calibrate.fit([row(0.8, "repeat"), row(0.6, "different")])
    assert cal.with_text == DEFAULT_CALIBRATION.with_text and "Мало" in notes[0]


def test_labels_last_wins_and_unset(tmp_path):
    calibrate.save_label("a~b", "repeat", tmp_path)
    calibrate.save_label("a~b", "similar", tmp_path)
    calibrate.save_label("c~d", "different", tmp_path)
    calibrate.save_label("c~d", None, tmp_path)
    assert calibrate.load_labels(tmp_path) == {"a~b": "similar"}


def test_sample_pairs_from_index():
    index = build_index(REGISTRY, fake_embed)
    pairs, stats = calibrate.sample_pairs(index, n_pairs=10, n_queries=4, seed=1, bins=(0.0, 1.01))
    assert stats["queries"] == 4
    for p in pairs:
        assert p["a"] != p["b"] and {"dense", "cos", "place", "completeness"} <= set(p)
    assert pairs


def test_saved_calibration_is_used_by_assess(tmp_path, monkeypatch):
    cal, _ = calibrate.fit([row(0.99, "repeat")] * 6 + [row(0.95, "different")] * 6)
    path = tmp_path / "thresholds.json"
    calibrate._save_calibration(cal, path)
    assert load_calibration(path) == cal
    monkeypatch.setenv("PPU_THRESHOLDS", str(path))
    index = build_index(REGISTRY, fake_embed)
    res = assess(index, make_query("Ручки для напильников"), fake_embed)
    assert res["calibration"] == cal.source


def test_label_api(tmp_path, monkeypatch):
    index = build_index(REGISTRY, fake_embed)
    pairs, _ = calibrate.sample_pairs(index, n_pairs=10, n_queries=4, seed=1, bins=(0.0, 1.01))
    (tmp_path / "pairs.jsonl").write_text(
        "\n".join(json.dumps(p, ensure_ascii=False) for p in pairs), encoding="utf-8")
    monkeypatch.setenv("PPU_CALIB_DIR", str(tmp_path))
    monkeypatch.setattr(web, "engine", lambda: (index, fake_embed))
    web._records_by_id.cache_clear()
    c = TestClient(web.app)

    first = c.get("/api/label/pair").json()
    assert first["progress"] == {"done": 0, "total": len(pairs)}
    pid = first["pair"]["pair_id"]
    assert c.post("/api/label", json={"pair_id": pid, "label": "repeat"}).json() == {"ok": True}
    nxt = c.get("/api/label/pair").json()
    assert nxt["progress"]["done"] == 1 and (nxt["pair"] is None or nxt["pair"]["pair_id"] != pid)
    assert c.get(f"/api/label/pair?pair_id={pid}").json()["pair"]["label"] == "repeat"
    assert c.post("/api/label", json={"pair_id": pid, "label": "чушь"}).status_code == 422
    web._records_by_id.cache_clear()


# --- калибровка из интерфейса (/admin) ---

OBJS = ["ручки напильников", "ящик шаблонов", "подставка паяльника", "лоток крепежа",
        "тележка заготовок", "светильник станка"]
PROBS = ["развалились и травмируют руки", "теряются на верстаке", "прожигают стол",
         "долго искать нужный размер", "тяжело переносить вручную", "плохо видно разметку"]
SOLS = ["изготовлены новые", "сделан ящик с ячейками", "установлена металлическая подставка",
        "установлены поворотные лотки", "изготовлена тележка", "установлен светильник"]


def big_index():
    from test_search import rec
    recs = []
    for k in range(60):
        i, j = k % 6, (k // 6) % 3
        recs.append(rec(str(k), f"{OBJS[i]} цех {k % 5}", f"{OBJS[i]} {PROBS[(i + j) % 6]}",
                        f"{SOLS[(i + j) % 6]} для {OBJS[i]}"))
    return build_index(recs, fake_embed)


def calib_client(tmp_path, monkeypatch, index):
    monkeypatch.setenv("PPU_CALIB_DIR", str(tmp_path / "calib"))
    monkeypatch.setenv("PPU_THRESHOLDS", str(tmp_path / "thresholds.json"))
    monkeypatch.delenv("PPU_ADMIN_TOKEN", raising=False)
    monkeypatch.setattr(web, "engine", lambda: (index, fake_embed))
    monkeypatch.setattr(web, "CALIB_JOB", web.Job())
    web._records_by_id.cache_clear()
    return TestClient(web.app)


def wait_calib(c):
    import time
    for _ in range(200):
        s = c.get("/api/calib/status").json()
        if s["job"]["status"] != "running":
            return s
        time.sleep(0.05)
    raise AssertionError("выбор пар не закончился")


def test_sample_to_dir_append_keeps_existing(tmp_path):
    index = big_index()
    first = calibrate.sample_to_dir(index, tmp_path, n_pairs=16, n_queries=60)
    before = calibrate.load_pairs(tmp_path)
    assert first["count"] == len(before) > 0
    second = calibrate.sample_to_dir(index, tmp_path, n_pairs=40, n_queries=60, append=True)
    after = calibrate.load_pairs(tmp_path)
    assert after[:len(before)] == before and second["total"] == len(after)
    keys = [frozenset((p["a"], p["b"])) for p in after]
    assert len(keys) == len(set(keys))  # без повторов, в том числе A~B / B~A


def test_calibration_via_web(tmp_path, monkeypatch):
    index = big_index()
    c = calib_client(tmp_path, monkeypatch, index)
    s = c.get("/api/calib/status").json()
    assert s["pairs"] == 0 and not s["thresholds"]["custom"]
    assert c.get("/api/label/pair").status_code == 404
    assert c.post("/api/calib/fit").status_code == 422  # разметки ещё нет

    assert c.post("/api/calib/sample", json={"n_pairs": 40, "append": True}).status_code == 200
    s = wait_calib(c)
    assert s["job"]["status"] == "done" and s["pairs"] > 0

    # размечаем: близкие — повтор, дальние — не связаны
    for p in calibrate.load_pairs(tmp_path / "calib"):
        lab = "repeat" if p["dense"] >= 0.8 else "different"
        assert c.post("/api/label", json={"pair_id": p["pair_id"], "label": lab}).status_code == 200
    s = c.get("/api/calib/status").json()
    assert s["labeled"] == s["pairs"] and set(s["by_label"]) <= {"repeat", "different"}

    report = c.post("/api/calib/fit").json()["report"]
    assert "Подобрано" in report and not (tmp_path / "thresholds.json").exists()
    r = c.post("/api/calib/apply").json()
    assert "разметка" in r["source"] and (tmp_path / "thresholds.json").exists()
    assert c.post("/api/assess", json={"name": "ручки напильников"}).json()["calibration"] == r["source"]

    assert c.post("/api/calib/reset").json()["source"] == DEFAULT_CALIBRATION.source
    assert not c.get("/api/calib/status").json()["thresholds"]["custom"]
    web._records_by_id.cache_clear()


def test_calibration_token(tmp_path, monkeypatch):
    index = big_index()
    c = calib_client(tmp_path, monkeypatch, index)
    calibrate.sample_to_dir(index, tmp_path / "calib", n_pairs=16, n_queries=60)
    monkeypatch.setenv("PPU_ADMIN_TOKEN", "t")
    ok = {"X-Admin-Token": "t"}
    for method, url in [("get", "/api/calib/status"), ("post", "/api/calib/fit"),
                        ("post", "/api/calib/apply"), ("post", "/api/calib/reset"),
                        ("post", "/api/calib/llm"), ("post", "/api/calib/llm/stop"),
                        ("get", "/api/label/pair")]:
        assert getattr(c, method)(url).status_code == 403, url
    assert c.post("/api/calib/sample", json={"n_pairs": 20}).status_code == 403
    pid = calibrate.load_pairs(tmp_path / "calib")[0]["pair_id"]
    assert c.post("/api/label", json={"pair_id": pid, "label": "repeat"}).status_code == 403
    assert calibrate.load_labels(tmp_path / "calib") == {}  # без пароля ничего не записалось
    assert c.get("/api/label/pair", headers=ok).status_code == 200
    assert c.post("/api/label", json={"pair_id": pid, "label": "repeat"}, headers=ok).status_code == 200
    assert c.post("/api/calib/reset", headers=ok).status_code == 200
    web._records_by_id.cache_clear()


def test_label_skips_pairs_from_old_base(tmp_path, monkeypatch):
    index = big_index()
    c = calib_client(tmp_path, monkeypatch, index)
    calibrate.sample_to_dir(index, tmp_path / "calib", n_pairs=16, n_queries=60)
    pairs = calibrate.load_pairs(tmp_path / "calib")
    stale = {"pair_id": "старая~запись", "a": "старая", "b": "запись"}
    (tmp_path / "calib" / "pairs.jsonl").write_text(
        "\n".join(json.dumps(p, ensure_ascii=False) for p in [stale] + pairs), encoding="utf-8")
    r = c.get("/api/label/pair").json()
    assert r["pair"]["pair_id"] != stale["pair_id"] and r["progress"]["total"] == len(pairs)
    web._records_by_id.cache_clear()


# --- разметка пар LLM-судьёй ---

def fake_judge(code_for=lambda a, b: "dup", calls=None, fail=False):
    from ppu.llm import LLMError

    def judge(query, cands, token=None):
        if calls is not None:
            calls.append((query["id"], [c["id"] for c in cands]))
        if fail:
            raise LLMError("сервер LLM недоступен")
        return {c["id"]: {"relation": "x", "code": code_for(query["id"], c["id"]), "why": "пояснение"}
                for c in cands}
    return judge


def test_llm_label_pairs_groups_and_keeps_human(tmp_path):
    index = big_index()
    by_id = {r["id"]: r for r in index.records}
    calibrate.sample_to_dir(index, tmp_path, n_pairs=40, n_queries=60)
    pairs = calibrate.load_pairs(tmp_path)
    calibrate.save_label(pairs[0]["pair_id"], "different", tmp_path)  # человек уже разметил

    calls = []
    res = calibrate.llm_label_pairs(by_id, fake_judge(calls=calls), tmp_path)
    meta = calibrate.load_label_meta(tmp_path)
    assert res["count"] == len(pairs) - 1 and len(meta) == len(pairs)
    assert meta[pairs[0]["pair_id"]]["by"] == "human" and meta[pairs[0]["pair_id"]]["label"] == "different"
    assert {r["by"] for pid, r in meta.items() if pid != pairs[0]["pair_id"]} == {"llm"}
    assert all(len(c) <= 4 for _, c in calls) and len(calls) < len(pairs)  # пары по одной A — одним запросом
    # повторный запуск ничего не делает — всё размечено
    assert calibrate.llm_label_pairs(by_id, fake_judge(calls=calls), tmp_path)["total"] == 0


def test_llm_label_pairs_stop_and_failure(tmp_path):
    import pytest
    from ppu.llm import CancelToken, LLMError
    index = big_index()
    by_id = {r["id"]: r for r in index.records}
    calibrate.sample_to_dir(index, tmp_path, n_pairs=40, n_queries=60)
    token = CancelToken()
    calls = []

    def judge(q, c, token=None):
        calls.append(1)
        if len(calls) == 2:
            token.cancel()
        return fake_judge()(q, c)
    res = calibrate.llm_label_pairs(by_id, lambda q, c, token=None: judge(q, c, token), tmp_path,
                                    token=token)
    assert res["report"].startswith("Остановлено") and 0 < res["count"] < res["total"]
    with pytest.raises(LLMError, match="сохранены"):
        calibrate.llm_label_pairs(by_id, fake_judge(fail=True), tmp_path)


def test_llm_labeling_via_web(tmp_path, monkeypatch):
    index = big_index()
    c = calib_client(tmp_path, monkeypatch, index)
    monkeypatch.setattr(web, "judge", lambda: fake_judge(
        code_for=lambda a, b: "dup" if index.records[int(a)]["name_clean"].split()[0]
        == index.records[int(b)]["name_clean"].split()[0] else "diff"))
    assert c.post("/api/calib/llm").status_code == 422  # пар ещё нет
    c.post("/api/calib/sample", json={"n_pairs": 40})
    wait_calib(c)
    assert c.post("/api/calib/llm").status_code == 200
    s = wait_calib(c)
    assert s["job"]["status"] == "done" and s["job"]["source"] == "llm"
    assert s["labeled"] == s["pairs"] == s["labeled_by_llm"] and "LLM разметила" in s["job"]["report"]

    # проверка людьми: пара с меткой LLM и пояснением, ответ человека её подтверждает
    r = c.get("/api/label/pair?review=1").json()
    pair = r["pair"]
    assert pair["label_by"] == "llm" and pair["label_why"] == "пояснение"
    assert r["progress"] == {"done": 0, "total": s["pairs"]}
    c.post("/api/label", json={"pair_id": pair["pair_id"], "label": pair["label"]})
    r2 = c.get("/api/label/pair?review=1").json()
    assert r2["progress"]["done"] == 1 and (r2["pair"] is None or r2["pair"]["pair_id"] != pair["pair_id"])
    assert c.get("/api/calib/status").json()["labeled_by_llm"] == s["pairs"] - 1
    assert "Подобрано" in c.post("/api/calib/fit").json()["report"]
    web._records_by_id.cache_clear()


def test_llm_labeling_without_llm(tmp_path, monkeypatch):
    c = calib_client(tmp_path, monkeypatch, big_index())
    monkeypatch.setattr(web, "judge", lambda: None)
    assert c.post("/api/calib/llm").status_code == 503
    assert c.get("/api/calib/status").json()["llm"] is False
    web._records_by_id.cache_clear()


def test_llm_repeat_in_other_place_becomes_other_place(tmp_path):
    index = big_index()
    by_id = {r["id"]: r for r in index.records}
    calibrate.sample_to_dir(index, tmp_path, n_pairs=40, n_queries=60)
    calibrate.llm_label_pairs(by_id, fake_judge(), tmp_path)
    labels = calibrate.load_labels(tmp_path)
    for p in calibrate.load_pairs(tmp_path):
        assert labels[p["pair_id"]] == ("other_place" if p["place"] == "other" else "repeat")
