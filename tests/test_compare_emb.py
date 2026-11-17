import numpy as np

from ppu.compare_emb import auc, best_split, compare
from ppu.config import Endpoint
from ppu.embed import Embedder
from ppu.index import build_index
from test_search import REGISTRY, fake_embed, rec


def test_auc_and_split():
    pos = np.array([True, True, False, False])
    assert auc(np.array([0.9, 0.8, 0.3, 0.2]), pos) == 1.0
    assert auc(np.array([0.2, 0.3, 0.8, 0.9]), pos) == 0.0
    assert auc(np.array([0.5, 0.5, 0.5, 0.5]), pos) == 0.5
    t, f1, acc = best_split(np.array([0.9, 0.8, 0.3, 0.2]), pos)
    assert t == 0.8 and f1 == 1.0 and acc == 1.0


def test_compare_on_labeled_pairs():
    registry = REGISTRY + [rec("5", "Ручки напильников треснули", "Ручки напильников развалились.",
                               "Ручки целые.", "Сделать новые ручки для напильников.")]
    index = build_index(registry, fake_embed, "старая")
    rows = [{"pair_id": "1~5", "a": "1", "b": "5", "label": "repeat"},
            {"pair_id": "1~2", "a": "1", "b": "2", "label": "different"},
            {"pair_id": "2~3", "a": "2", "b": "3", "label": "different"},
            {"pair_id": "1~нет", "a": "1", "b": "нет", "label": "repeat"}]  # записи нет в базе - пропуск
    lines, new_pairs = compare(index, rows, fake_embed, "новая")
    text = "\n".join(lines)
    assert "Размеченных пар: 3" in text and "сейчас: старая" in text and "новая: новая" in text
    assert "AUC 1.000" in text and "на 1-м месте 100%" in text
    assert [p["pair_id"] for p in new_pairs] == ["1~5", "1~2", "2~3"]
    assert all("dense" in p and "label" not in p for p in new_pairs)


def test_instruct_goes_into_text_and_cache_key(tmp_path):
    seen = []

    class E(Embedder):
        def _request(self, texts):
            seen.extend(texts)
            return fake_embed(texts)

    ep = Endpoint("http://127.0.0.1:1/v1", "none", "m")
    plain = E(ep, cache_path=tmp_path / "c.sqlite", instruct="")
    inst = E(ep, cache_path=tmp_path / "c.sqlite", instruct="Find the same proposal")
    plain(["ручки напильников"])
    inst(["ручки напильников"])  # другой текст для модели - не из кэша «без инструкции»
    assert seen == ["ручки напильников", "Instruct: Find the same proposal\nQuery: ручки напильников"]
    inst(["ручки напильников"])  # а теперь из кэша
    assert len(seen) == 2
