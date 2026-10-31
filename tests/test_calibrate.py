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
