"""FastAPI-приложение: форма нового ППУ и вердикт по реестру."""
import asyncio
import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .. import calibrate, config
from ..assess import assess
from ..embed import Embedder
from ..index import load_index
from ..judge import Judge
from ..llm import LLM, CancelToken, LLMCancelled, LLMError, is_local
from ..search import make_query

STATIC = Path(__file__).parent / "static"


class PPU(BaseModel):
    name: str = Field(min_length=3, max_length=500)
    before: str = Field("", max_length=10000)
    after: str = Field("", max_length=10000)
    proposal: str = Field("", max_length=10000)


@lru_cache(maxsize=1)
def engine():
    """Индекс и клиент эмбеддингов — один раз на процесс."""
    index = load_index(os.getenv("PPU_INDEX", "data/index"))
    embedder = Embedder(config.embeddings(),
                        cache_path=os.getenv("PPU_EMB_CACHE", "data/emb_cache.sqlite"))
    return index, embedder


@lru_cache(maxsize=1)
def judge() -> Judge | None:
    """LLM-судья, если LLM настроена. Параметры запроса — LLM_EXTRA_BODY в .env."""
    ep = config.llm()
    if not ep.configured or not ep.model:
        return None
    # с включёнными рассуждениями (polza) ответу нужно больше токенов
    return Judge(LLM(ep), max_tokens=int(os.getenv("PPU_LLM_MAX_TOKENS", "400")))


app = FastAPI(title="Проверка ППУ")


@app.get("/")
def page():
    return FileResponse(STATIC / "index.html")


@app.get("/api/info")
def info():
    index, _ = engine()
    ep = config.llm()
    return {"records": len(index), "built": index.meta.get("built"),
            "embedding_model": index.meta.get("model"), "llm": judge() is not None,
            # чтобы в интерфейсе было видно, что текст уходит во внешний сервис
            "llm_host": urlparse(ep.base_url).hostname if ep.configured else None,
            "llm_local": is_local(ep.base_url) if ep.configured else None}


def _assess(ppu: PPU, with_llm: bool, token: CancelToken) -> dict:
    index, embedder = engine()
    query = make_query(ppu.name, ppu.before, ppu.after, ppu.proposal)
    j = judge() if with_llm else None
    res = assess(index, query, embedder, force_judge=with_llm,
                 judge=(lambda q, cands: j(q, cands, token=token)) if j else None)
    res["query"] = {"name": query["name_clean"], "completeness": query["completeness"],
                    "entities": query["entities"]}
    return res


def _ignore_result(task: asyncio.Future):
    # задача после отмены доработает в потоке до ближайшей проверки токена — результат не нужен
    if not task.cancelled():
        task.exception()


async def _run(ppu: PPU, with_llm: bool, request: Request):
    token = CancelToken()
    # эмбеддинги и LLM — блокирующие HTTP-вызовы, уводим из event loop
    task = asyncio.ensure_future(run_in_threadpool(_assess, ppu, with_llm, token))
    try:
        while not task.done():
            await asyncio.wait({task}, timeout=0.5)
            if not task.done() and await request.is_disconnected():
                # браузер оборвал запрос (кнопка «Отменить») — останавливаем LLM
                token.cancel()
                task.add_done_callback(_ignore_result)
                raise HTTPException(status_code=499, detail="Запрос отменён")
        return task.result()
    except HTTPException:
        raise
    except LLMCancelled as e:
        raise HTTPException(status_code=499, detail=str(e))
    except LLMError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:  # модель недоступна и т.п. — показываем причину в интерфейсе
        raise HTTPException(status_code=502, detail=f"{e.__class__.__name__}: {e}")


@app.post("/api/assess")
async def api_assess(ppu: PPU, request: Request):
    return await _run(ppu, False, request)


@app.post("/api/judge")
async def api_judge(ppu: PPU, request: Request):
    """То же, но верхних кандидатов дополнительно проверяет LLM (медленно на CPU)."""
    if judge() is None:
        raise HTTPException(status_code=503, detail="LLM не настроена: LLM_BASE_URL и LLM_MODEL в .env")
    return await _run(ppu, True, request)


# --- разметка пар для калибровки порогов (ppu.calibrate) ---

class Label(BaseModel):
    pair_id: str
    label: str | None  # None — снять метку


def _calib_dir() -> Path:
    return Path(os.getenv("PPU_CALIB_DIR", str(calibrate.CALIB_DIR)))


@lru_cache(maxsize=1)
def _records_by_id() -> dict:
    index, _ = engine()
    return {r["id"]: r for r in index.records}


def _record_view(rec: dict) -> dict:
    return {"id": rec["id"], "name": rec.get("name_clean") or rec.get("name"),
            "status": rec.get("status"), "date_submitted": rec.get("date_submitted"),
            "effect": rec.get("effect"), "entities": rec.get("entities", {}),
            "completeness": rec.get("completeness"),
            **{f: rec.get(f"{f}_clean", "") for f in ("before", "after", "proposal")}}


@app.get("/label")
def label_page():
    return FileResponse(STATIC / "label.html")


@app.get("/api/label/pair")
def label_pair(pair_id: str | None = None):
    """Пара для разметки: указанная или первая неразмеченная."""
    pairs = calibrate.load_pairs(_calib_dir())
    if not pairs:
        raise HTTPException(status_code=404,
                            detail="Пар нет — сначала: python -m ppu.calibrate sample")
    labels = calibrate.load_labels(_calib_dir())
    pair = next((p for p in pairs if p["pair_id"] == pair_id), None) if pair_id \
        else next((p for p in pairs if p["pair_id"] not in labels), None)
    by_id = _records_by_id()
    progress = {"done": sum(p["pair_id"] in labels for p in pairs), "total": len(pairs)}
    if pair is None:
        return {"pair": None, "progress": progress}
    missing = [x for x in (pair["a"], pair["b"]) if x not in by_id]
    if missing:
        raise HTTPException(status_code=409, detail=f"Записей {missing} нет в индексе — "
                            "пары выбраны по другому индексу, выберите заново (sample --force)")
    return {"pair": {"pair_id": pair["pair_id"], "a": _record_view(by_id[pair["a"]]),
                     "b": _record_view(by_id[pair["b"]]), "label": labels.get(pair["pair_id"])},
            "progress": progress, "labels": calibrate.LABELS}


@app.post("/api/label")
def label_save(item: Label):
    if item.label is not None and item.label not in {*calibrate.LABELS, "unclear"}:
        raise HTTPException(status_code=422, detail=f"Неизвестная метка: {item.label}")
    calibrate.save_label(item.pair_id, item.label, _calib_dir())
    return {"ok": True}
