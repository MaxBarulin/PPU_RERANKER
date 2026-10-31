import pytest

from ppu.config import Endpoint
from ppu.llm import parse_json
from ppu.rerank import Reranker, sigmoid


def test_scores_returned_in_document_order(monkeypatch):
    rr = Reranker(Endpoint("http://x/v1", "none", ""))
    sent = {}

    def fake_post(payload):
        sent.update(payload)
        # сервер сортирует по убыванию — мы должны вернуть исходный порядок
        return {"results": [{"index": 1, "relevance_score": 2.0},
                            {"index": 0, "relevance_score": -3.0}]}

    monkeypatch.setattr(rr, "_post", fake_post)
    assert rr("q", ["a", "b"]) == [sigmoid(-3.0), sigmoid(2.0)]
    assert "model" not in sent and sent["top_n"] == 2


def test_not_configured():
    with pytest.raises(ValueError):
        Reranker(Endpoint("", "none", ""))


def test_parse_json_strips_wrapping():
    assert parse_json('<think>хм</think>\n```json\n{"a": [1, 2]}\n```') == {"a": [1, 2]}
    assert parse_json('{"a": 1}\nи ещё {"b": {"c": 2}} конец') == {"a": 1, "b": {"c": 2}}
    assert parse_json('{"name": "x"}\n{"name": "y"}') == [{"name": "x"}, {"name": "y"}]
    with pytest.raises(ValueError):
        parse_json("нет json")
