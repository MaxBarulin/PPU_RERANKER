"""FastAPI-приложение: форма нового ППУ и вердикт по реестру."""
import asyncio
import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from .. import calibrate, config
from ..assess import active_calibration, assess, thresholds_path
from ..embed import Embedder
from ..index import load_index
from ..rebuild import Job, rebuild_from_excel
from ..judge import Judge
from ..llm import LLM, CancelToken, LLMCancelled, LLMError, is_local
from ..search import make_query

STATIC = Path(__file__).parent / "static"


class PPU(BaseModel):
    name: str = Field(min_length=3, max_length=500)
    before: str = Field("", max_length=10000)
    after: str = Field("", max_length=10000)
    proposal: str = Field("", max_length=10000)


class NoIndex(Exception):
    pass


def _index_dir() -> Path:
    return Path(os.getenv("PPU_INDEX", "data/index"))


def _cache_path() -> str:
    return os.getenv("PPU_EMB_CACHE", "data/emb_cache.sqlite")


@lru_cache(maxsize=1)
def engine():
    """Индекс и клиент эмбеддингов — один раз на процесс (сбрасывается после пересборки)."""
    if not (_index_dir() / "meta.json").exists():
        raise NoIndex("Индекса ещё нет — загрузите реестр на странице /admin")
    index = load_index(_index_dir())
    embedder = Embedder(config.embeddings(), cache_path=_cache_path())
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


@app.exception_handler(NoIndex)
def _no_index(request: Request, exc: NoIndex):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get("/")
def page():
    return FileResponse(STATIC / "index.html")


@app.get("/api/info")
def info():
    try:
        index, _ = engine()
        meta = {"index": True, "records": len(index), "built": index.meta.get("built"),
                "source": index.meta.get("source"), "embedding_model": index.meta.get("model")}
    except NoIndex:
        meta = {"index": False, "records": 0, "built": None, "source": None,
                "embedding_model": None}
    ep = config.llm()
    return {**meta, "llm": judge() is not None, "rebuild": JOB.snapshot()["status"],
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
    except NoIndex as e:
        raise HTTPException(status_code=503, detail=str(e))
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
                            detail="Пар нет — выберите их на странице /admin, раздел «Калибровка порогов»")
    by_id = _records_by_id()
    # после обновления базы часть пар может ссылаться на исчезнувшие записи — пропускаем их
    pairs = [p for p in pairs if p["a"] in by_id and p["b"] in by_id]
    if not pairs:
        raise HTTPException(status_code=409, detail="Пары выбраны по другой базе: "
                            "на /admin нажмите «выбрать заново»")
    labels = calibrate.load_labels(_calib_dir())
    pair = next((p for p in pairs if p["pair_id"] == pair_id), None) if pair_id \
        else next((p for p in pairs if p["pair_id"] not in labels), None)
    progress = {"done": sum(p["pair_id"] in labels for p in pairs), "total": len(pairs)}
    if pair is None:
        return {"pair": None, "progress": progress}
    return {"pair": {"pair_id": pair["pair_id"], "a": _record_view(by_id[pair["a"]]),
                     "b": _record_view(by_id[pair["b"]]), "label": labels.get(pair["pair_id"])},
            "progress": progress, "labels": calibrate.LABELS}


@app.post("/api/label")
def label_save(item: Label):
    if item.label is not None and item.label not in {*calibrate.LABELS, "unclear"}:
        raise HTTPException(status_code=422, detail=f"Неизвестная метка: {item.label}")
    calibrate.save_label(item.pair_id, item.label, _calib_dir())
    return {"ok": True}


# --- обновление базы: загрузка реестра и пересборка индекса (страница /admin) ---

JOB = Job()
EXCEL_SUFFIXES = (".xlsx", ".xlsm")
_upload_lock = asyncio.Lock()


def _registry_path() -> Path:
    """Последний загруженный реестр — из него же «Пересобрать» без новой загрузки."""
    return Path(os.getenv("PPU_REGISTRY", "data/registry.xlsx"))


def _check_token(token: str | None):
    """Если в .env задан PPU_ADMIN_TOKEN — без него базу не обновить."""
    expected = os.getenv("PPU_ADMIN_TOKEN", "")
    if expected and token != expected:
        raise HTTPException(status_code=403, detail="Неверный пароль администратора")


def _source_file() -> Path:
    # исходное имя загруженного файла — чтобы показывать его, а не «registry.xlsx»
    return _registry_path().with_name(_registry_path().name + ".source")


def _reload():
    engine.cache_clear()
    _records_by_id.cache_clear()


def _start(path: Path, source: str):
    def work(progress):
        return rebuild_from_excel(path, _index_dir(), _cache_path(), progress, source=source)
    if not JOB.start(work, on_success=_reload, source=source):
        raise HTTPException(status_code=409, detail="Сборка индекса уже идёт")
    return JOB.snapshot()


@app.get("/admin")
def admin_page():
    return FileResponse(STATIC / "admin.html")


@app.get("/api/index/status")
def index_status():
    reg, src = _registry_path(), _source_file()
    name = (src.read_text(encoding="utf-8") if src.exists() else reg.name) if reg.exists() else None
    return {**JOB.snapshot(), "token_required": bool(os.getenv("PPU_ADMIN_TOKEN")),
            "registry": name}


@app.post("/api/index/upload")
async def index_upload(request: Request, filename: str = "registry.xlsx",
                       x_admin_token: str | None = Header(None)):
    """Тело запроса — сам файл Excel. Сохраняет его и запускает пересборку в фоне."""
    _check_token(x_admin_token)
    name = Path(filename).name
    if not name.lower().endswith(EXCEL_SUFFIXES):
        raise HTTPException(status_code=422, detail="Нужен файл .xlsx (старый .xls — "
                            "пересохраните в Excel как «Книга Excel (.xlsx)»)")
    if JOB.running or _upload_lock.locked():
        raise HTTPException(status_code=409, detail="Сборка индекса уже идёт")
    async with _upload_lock:
        limit = int(os.getenv("PPU_MAX_UPLOAD_MB", "200")) * 1024 * 1024
        target = _registry_path()
        target.parent.mkdir(parents=True, exist_ok=True)
        part = target.with_name(target.name + ".part")
        size = 0
        with part.open("wb") as f:
            async for chunk in request.stream():
                size += len(chunk)
                if size > limit:
                    break
                f.write(chunk)
        if size > limit or not size:
            part.unlink(missing_ok=True)
            raise HTTPException(status_code=413 if size else 422,
                                detail="Файл слишком большой (предел — PPU_MAX_UPLOAD_MB в .env)"
                                if size else "Пустой файл")
        part.replace(target)
        _source_file().write_text(name, encoding="utf-8")
        return _start(target, name)


@app.post("/api/index/rebuild")
def index_rebuild(x_admin_token: str | None = Header(None)):
    """Пересобрать из последнего загруженного реестра (например, после обрыва)."""
    _check_token(x_admin_token)
    path = _registry_path()
    if not path.exists():
        raise HTTPException(status_code=404, detail="Реестр ещё не загружался")
    src = _source_file()
    return _start(path, src.read_text(encoding="utf-8") if src.exists() else path.name)


# --- калибровка порогов из интерфейса: выбор пар → разметка (/label) → подбор → применение ---

CALIB_JOB = Job()


class SampleRequest(BaseModel):
    n_pairs: int = Field(240, ge=10, le=2000)
    append: bool = True


@app.get("/api/calib/status")
def calib_status():
    pairs = calibrate.load_pairs(_calib_dir())
    labels = calibrate.load_labels(_calib_dir())
    ids = {p["pair_id"] for p in pairs}
    by_label = {}
    for pid, lab in labels.items():
        if pid in ids:
            by_label[lab] = by_label.get(lab, 0) + 1
    path = thresholds_path()
    return {"pairs": len(pairs), "labeled": sum(by_label.values()), "by_label": by_label,
            "label_names": {**calibrate.LABELS, "unclear": "непонятно"},
            "thresholds": {"custom": path.exists(), "source": active_calibration().source},
            "token_required": bool(os.getenv("PPU_ADMIN_TOKEN")),
            "job": CALIB_JOB.snapshot()}


@app.post("/api/calib/sample")
def calib_sample(req: SampleRequest, x_admin_token: str | None = Header(None)):
    """Выбрать пары для разметки в фоне: добавить к уже выбранным или заменить их."""
    _check_token(x_admin_token)
    index, _ = engine()
    if len(index) < 10:
        raise HTTPException(status_code=422, detail="В базе слишком мало записей для калибровки")

    def work(progress):
        return calibrate.sample_to_dir(
            index, _calib_dir(), req.n_pairs, append=req.append,
            progress=lambda done, total: progress(stage="Поиск ближайших соседей",
                                                  done=done, total=total))
    if not CALIB_JOB.start(work, on_success=_records_by_id.cache_clear):
        raise HTTPException(status_code=409, detail="Выбор пар уже идёт")
    return CALIB_JOB.snapshot()


@app.post("/api/calib/fit")
def calib_fit(x_admin_token: str | None = Header(None)):
    """Подобрать пороги по разметке и показать, что изменится. Ничего не применяет."""
    _check_token(x_admin_token)
    try:
        _, text = calibrate.fit_from_dir(_calib_dir())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"report": text}


@app.post("/api/calib/apply")
def calib_apply(x_admin_token: str | None = Header(None)):
    """Подобрать пороги и сразу применить: проверка ППУ начнёт их использовать со следующего запроса."""
    _check_token(x_admin_token)
    try:
        fitted, text = calibrate.fit_from_dir(_calib_dir())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    calibrate.save_calibration(fitted)
    return {"report": text, "source": fitted.source}


@app.post("/api/calib/reset")
def calib_reset(x_admin_token: str | None = Header(None)):
    """Вернуть пороги по умолчанию (с синтетики). Разметка не удаляется."""
    _check_token(x_admin_token)
    thresholds_path().unlink(missing_ok=True)
    return {"source": active_calibration().source}
