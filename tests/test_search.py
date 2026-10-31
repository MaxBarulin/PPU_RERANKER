import zlib

import numpy as np

from ppu.index import build_index, load_index, save_index
from ppu.lexical import BM25, lemmas
from ppu.normalize import normalize_record
from ppu.search import make_query, search

DIM = 512


def fake_embed(texts):
    """Мешок лемм, захэшированный в вектор: похожие слова — похожие векторы."""
    out = np.zeros((len(texts), DIM), dtype=np.float32)
    for i, t in enumerate(texts):
        for lm in lemmas(t):
            out[i, zlib.crc32(lm.encode()) % DIM] += 1
    norms = np.linalg.norm(out, axis=1, keepdims=True)
    return out / np.where(norms == 0, 1, norms)


def rec(id_, name, before=None, after=None, proposal=None):
    return normalize_record({"id": id_, "name": name, "before": before, "after": after,
                             "proposal": proposal, "result": None})


REGISTRY = [
    rec("1", "Ручки для напильников",
        "Ручки напильников развалились, можно травмировать руки.",
        "Сделали деревянные ручки, работать безопасно.",
        "Изготовить деревянные ручки для напильников."),
    rec("2", "Звукоизоляция круговой виброустановки",
        "Повышенный уровень шума на участке №19 цеха 14016 от виброустановки.",
        "Приемлемый уровень шума.",
        "Установить звукопоглощающую перегородку."),
    rec("3", "Контейнер для хранения шаблонов"),
    rec("4", "Улучшение культуры пр-ва. Цех 26", "См.вложение", "См.вложение", "См.вложение"),
]


def test_lemmas_drop_stopwords_and_normalize():
    assert lemmas("Изготовили ручки для напильников") == ["изготовить", "ручка", "напильник"]


def test_bm25_prefers_matching_doc():
    bm = BM25([["ручка", "напильник"], ["шум", "виброустановка"], ["шаблон"]])
    s = bm.scores(["напильник"])
    assert s.argmax() == 0 and s[1] == s[2] == 0


def test_paraphrase_found_first():
    index = build_index(REGISTRY, fake_embed)
    q = make_query("Снижение шума от виброустановки",
                   before="Шумно работать рядом с виброустановкой, участок 19 цех 14016",
                   proposal="Поставить звукопоглощающую перегородку")
    res = search(index, q, fake_embed, top_k=3)
    assert res[0]["id"] == "2"
    assert res[0]["place"] == "same"
    assert set(res[0]["cos"]) == {"name", "full", "problem", "solution"}


def test_name_only_records_are_searchable():
    index = build_index(REGISTRY, fake_embed)
    q = make_query("Ящик для хранения шаблонов", before="Шаблоны лежат где попало")
    res = search(index, q, fake_embed, top_k=3)
    assert res[0]["id"] == "3"
    # у записи «только название» сравнение идёт по name и full
    assert set(res[0]["cos"]) == {"name", "full"}


def test_other_place_is_flagged():
    index = build_index(REGISTRY, fake_embed)
    res = search(index, make_query("Улучшение культуры производства. Цех 29"), fake_embed)
    top = res[0]
    assert top["id"] == "4" and top["place"] == "other"


def test_exclude_self_and_roundtrip(tmp_path):
    index = build_index(REGISTRY, fake_embed)
    save_index(index, tmp_path)
    loaded = load_index(tmp_path)
    res = search(loaded, loaded.records[0], fake_embed, exclude_ids=("1",))
    assert "1" not in {r["id"] for r in res}


def test_query_view_missing_in_whole_index():
    index = build_index([REGISTRY[2], REGISTRY[3]], fake_embed)  # ни у кого нет описания
    res = search(index, make_query("Хранение шаблонов", before="Нет места"), fake_embed)
    assert res[0]["id"] == "3"


def test_assess_repeat_and_unique():
    from ppu.assess import assess

    index = build_index(REGISTRY, fake_embed)
    dup = assess(index, REGISTRY[0], fake_embed)
    assert dup["verdict"] == "repeat" and dup["uniqueness"] == 0
    novel = assess(index, make_query("Автоматизация расчёта зарплаты в 1С"), fake_embed)
    assert novel["verdict"] == "unique" and novel["uniqueness"] == 1


def test_assess_alternative_same_problem_other_solution():
    from ppu.assess import assess

    index = build_index(REGISTRY, fake_embed)
    q = make_query("Ручки для напильников",
                   before="Ручки напильников развалились, можно травмировать руки.",
                   after="Закупили готовые пластиковые ручки у поставщика.",
                   proposal="Купить пластиковые ручки в магазине.")
    res = assess(index, q, fake_embed)
    assert res["candidates"][0]["id"] == "1"
    assert res["verdict"] == "alternative"


def test_assess_other_place():
    from ppu.assess import assess

    index = build_index(REGISTRY, fake_embed)
    res = assess(index, make_query("Улучшение культуры производства. Цех 29"), fake_embed)
    top = res["candidates"][0]
    assert top["id"] == "4" and top["relation"] == "other_place"
    assert res["verdict"] == "other_place"


def test_results_are_json_serializable():
    import json

    from ppu.assess import assess

    index = build_index(REGISTRY, fake_embed)
    res = assess(index, make_query("Ручки для напильников"), fake_embed)
    json.dumps(res, allow_nan=False)
