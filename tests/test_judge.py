from ppu.assess import assess
from ppu.index import build_index
from ppu.judge import Judge, build_prompt
from ppu.search import make_query

from test_search import REGISTRY, fake_embed


class FakeLLM:
    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def json(self, system, user, **kw):
        self.calls.append(user)
        return self.answer


def cand(id_, completeness="full"):
    rec = next(r for r in REGISTRY if r["id"] == id_)
    return {"id": id_, "completeness": completeness, "record": rec}


def test_judge_maps_codes_and_drops_unknown_ids():
    llm = FakeLLM({"items": [{"id": "1", "v": "DUP", "why": "то же"},
                             {"id": "2", "v": "sim"},
                             {"id": "99", "v": "dup"},          # не было среди кандидатов
                             {"id": "3", "v": "что-то"}]})       # неизвестный код
    out = Judge(llm)(make_query("Ручки"), [cand("1"), cand("2"), cand("3", "name_only")])
    assert out == {"1": {"relation": "repeat", "code": "dup", "why": "то же"},
                   "2": {"relation": "similar", "code": "sim", "why": ""}}
    assert "[3] Контейнер для хранения шаблонов (в реестре только название)" in llm.calls[0]


def test_prompt_puts_new_ppu_first_and_truncates():
    q = make_query("Ручки", before="очень " * 1000)
    prompt = build_prompt(q, [cand("1")])
    assert prompt.startswith("НОВОЕ: Ручки") and "…" in prompt and len(prompt) < 2500


def test_assess_with_judge_overrides_vectors():
    index = build_index(REGISTRY, fake_embed)
    llm = FakeLLM({"items": [{"id": "3", "v": "dup", "why": "тот же контейнер"}]})
    q = make_query("Ящик для хранения шаблонов")
    res = assess(index, q, fake_embed, judge=Judge(llm), force_judge=True)
    top = res["candidates"][0]
    assert res["judged_by"] == "llm" and res["verdict"] == "repeat"
    assert top["id"] == "3" and top["llm"]["code"] == "dup" and "relation_vectors" in top
    assert res["uniqueness"] == 0.05 and not res["needs_llm"]


def test_judge_dup_with_other_place_becomes_other_place():
    index = build_index(REGISTRY, fake_embed)
    llm = FakeLLM({"items": [{"id": "4", "v": "dup"}]})
    res = assess(index, make_query("Улучшение культуры производства. Цех 29"), fake_embed,
                 judge=Judge(llm), force_judge=True)
    assert res["candidates"][0]["relation"] == "other_place"


def test_judge_not_called_when_vectors_are_sure():
    index = build_index(REGISTRY, fake_embed)
    llm = FakeLLM({"items": []})
    res = assess(index, REGISTRY[0], fake_embed, judge=Judge(llm))
    assert res["verdict"] == "repeat" and llm.calls == [] and res["judged_by"] == "vectors"
