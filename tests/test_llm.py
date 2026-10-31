from types import SimpleNamespace as NS

import pytest

from ppu.config import Endpoint
from ppu.llm import LLM, CancelToken, LLMCancelled, LLMError, is_local


class FakeStream:
    def __init__(self, pieces, finish="stop", on_chunk=None):
        self.pieces, self.finish, self.on_chunk = pieces, finish, on_chunk
        self.closed = False

    def __iter__(self):
        for i, p in enumerate(self.pieces):
            if self.on_chunk:
                self.on_chunk(i)
            last = i == len(self.pieces) - 1
            yield NS(usage=NS(prompt_tokens=100, completion_tokens=7) if last else None,
                     choices=[NS(delta=NS(content=p), finish_reason=self.finish if last else None)])

    def close(self):
        self.closed = True


def make_llm(monkeypatch, *streams):
    llm = LLM(Endpoint("http://127.0.0.1:8080/v1", "none", "qwen"))
    queue = list(streams)
    monkeypatch.setattr(llm, "_stream", lambda *a: queue.pop(0))
    return llm


def test_stream_assembled_and_usage(monkeypatch):
    s = FakeStream(['{"items": ', '[{"id": "1"}]', "}"])
    llm = make_llm(monkeypatch, s)
    assert llm.json("sys", "user") == {"items": [{"id": "1"}]}
    assert s.closed and llm.last_usage == {"prompt_tokens": 100, "completion_tokens": 7,
                                           "answer_chars": 24}


def test_empty_because_of_token_limit_is_explained_without_retry(monkeypatch):
    llm = make_llm(monkeypatch, FakeStream(["", ""], finish="length"))
    with pytest.raises(LLMError, match="рассуждения"):
        llm.json("sys", "user", max_tokens=400)   # второго потока нет — значит, не переспрашивал


def test_bad_json_retried(monkeypatch):
    llm = make_llm(monkeypatch, FakeStream(["не json"]), FakeStream(['{"ok": 1}']))
    assert llm.json("sys", "user") == {"ok": 1}


def test_cancel_stops_reading_and_closes_stream(monkeypatch):
    token = CancelToken()
    s = FakeStream(["{", '"a"', ": 1}"], on_chunk=lambda i: token.cancel() if i == 1 else None)
    llm = make_llm(monkeypatch, s)
    with pytest.raises(LLMCancelled):
        llm.json("sys", "user", token=token)
    assert s.closed


def test_is_local():
    assert is_local("http://127.0.0.1:8080/v1") and is_local("http://localhost:8081/v1")
    assert not is_local("https://api.polza.ai/api/v1")
