"""FastAPI-приложение: форма нового ППУ и вердикт по реестру."""
import asyncio
import os
import sys
import threading
import time
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

import secrets
from urllib.parse import unquote

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from .. import calibrate, config
from ..assess import active_calibration, assess, thresholds_path
from ..embed import Embedder
from ..index import load_index
from .. import db
from ..rebuild import Job, rebuild_from_db, rebuild_from_excel
from ..judge import Judge
from ..lexical import lemmas
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
    try:
        llm = LLM(ep)
    except ValueError as e:  # например, битый LLM_EXTRA_BODY — проверка ППУ должна работать
        print(f"[LLM отключена] {e}", file=sys.stderr, flush=True)
        return None
    # с включёнными рассуждениями (polza) ответу нужно больше токенов
    return Judge(llm, max_tokens=int(os.getenv("PPU_LLM_MAX_TOKENS", "400")))


# Документацию API (/docs, /openapi.json) не публикуем: незачем показывать всем список
# служебных адресов
app = FastAPI(title="Проверка ППУ", docs_url=None, redoc_url=None, openapi_url=None)

# Тексты страниц и скрипты — только свои; чужой сайт не встроит страницу в рамку
# (защита от «подсовывания» кнопок), запросы — только к этому же серверу
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; "
       "form-action 'self'; object-src 'none'")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    h = response.headers
    h.setdefault("Content-Security-Policy", CSP)
    h.setdefault("X-Content-Type-Options", "nosniff")
    h.setdefault("X-Frame-Options", "DENY")
    h.setdefault("Referrer-Policy", "no-referrer")
    if request.url.path.startswith("/api/"):
        # тексты реестра не должны оседать в кэше браузера на общих компьютерах
        h.setdefault("Cache-Control", "no-store")
    return response


# Список имён, по которым разрешено обращаться к серверу (защита от DNS rebinding:
# чужой сайт не сможет выдать себя за этот сервер). Пусто — не проверяем.
if os.getenv("PPU_ALLOWED_HOSTS"):
    from starlette.middleware.trustedhost import TrustedHostMiddleware
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[
        h.strip() for h in os.environ["PPU_ALLOWED_HOSTS"].split(",") if h.strip()])

# Подбор пароля: после MAX_FAILS неверных попыток с одного адреса за FAIL_WINDOW секунд
# этот адрес ждёт, пока старые попытки не выйдут из окна
MAX_FAILS, FAIL_WINDOW = 10, 600
_fails: dict[str, list[float]] = {}
_fails_lock = threading.Lock()


def require_admin(request: Request, x_admin_token: str | None = Header(None)):
    """Всё, что на /admin и /label, — только с паролем PPU_ADMIN_TOKEN из .env (если он задан).

    Браузер передаёт пароль через encodeURIComponent: в HTTP-заголовке нельзя кириллицу.
    """
    expected = os.getenv("PPU_ADMIN_TOKEN", "")
    if not expected:
        return
    ip = request.client.host if request.client else "?"
    now = time.monotonic()
    with _fails_lock:
        recent = [t for t in _fails.get(ip, ()) if now - t < FAIL_WINDOW]
        if recent:
            _fails[ip] = recent
        else:
            _fails.pop(ip, None)
        if len(recent) >= MAX_FAILS:
            wait = int(FAIL_WINDOW - (now - recent[0])) // 60 + 1
            raise HTTPException(status_code=429, detail=f"Слишком много неверных попыток ввода "
                                f"пароля. Попробуйте через {wait} мин.")
    if not x_admin_token:
        raise HTTPException(status_code=403, detail="Нужен пароль администратора")
    if not secrets.compare_digest(unquote(x_admin_token).encode(), expected.encode()):
        with _fails_lock:
            _fails.setdefault(ip, []).append(now)
        raise HTTPException(status_code=403, detail="Неверный пароль администратора")
    with _fails_lock:
        _fails.pop(ip, None)


ADMIN = [Depends(require_admin)]


@app.exception_handler(NoIndex)
def _no_index(request: Request, exc: NoIndex):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get("/")
def page():
    return FileResponse(STATIC / "index.html")


@app.get("/logo.png")
def logo():
    return FileResponse(STATIC / "logo.png", media_type="image/png",
                        headers={"Cache-Control": "public, max-age=86400"})


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
    # 100 лучших по поиску: под «Показать ещё» идут все, кто прошёл фильтр (общие слова или
    # близость > 0); дальше по списку — уже не похожие записи
    res = assess(index, query, embedder, force_judge=with_llm, top_k=100,
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
    pair_id: str = Field(max_length=200)
    label: str | None = Field(None, max_length=30)  # None — снять метку


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


WORD_LIST_MAX = 200


@app.get("/api/word")
def word_list(w: str = Query(min_length=2, max_length=60)):
    """Все ППУ базы, где встречается слово (в любой форме), — новые сверху.

    Открыто, как и проверка ППУ: по клику на слово в сводке «В базе: …».
    """
    index, _ = engine()
    found = lemmas(w)
    if not found:
        raise HTTPException(status_code=422, detail="Слово слишком общее или пустое")
    lemma = found[0]
    recs = [index.records[i] for i in index.bm25.docs_with(lemma)]
    recs.sort(key=lambda r: r.get("date_submitted") or "", reverse=True)
    return {"word": lemma, "count": len(recs),
            "records": [_record_view(r) for r in recs[:WORD_LIST_MAX]]}


@app.get("/label")
def label_page():
    return FileResponse(STATIC / "label.html")


@app.get("/api/label/pair", dependencies=ADMIN)
def label_pair(pair_id: str | None = None, review: bool = False):
    """Пара для разметки: указанная или первая неразмеченная.

    review — проверка меток LLM: первая пара, размеченная LLM и ещё не
    подтверждённая человеком (ответ человека пишется поверх, by=human).
    """
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
    meta = calibrate.load_label_meta(_calib_dir())
    labels = {pid: row["label"] for pid, row in meta.items()}
    by_llm = {pid for pid, row in meta.items() if row.get("by") == "llm"}
    if pair_id:
        pair = next((p for p in pairs if p["pair_id"] == pair_id), None)
    elif review:
        pair = next((p for p in pairs if p["pair_id"] in by_llm), None)
    else:
        pair = next((p for p in pairs if p["pair_id"] not in labels), None)
    if review:  # проверено людьми из всех размеченных
        labeled = [p for p in pairs if p["pair_id"] in labels]
        progress = {"done": sum(p["pair_id"] not in by_llm for p in labeled), "total": len(labeled)}
    else:
        progress = {"done": sum(p["pair_id"] in labels for p in pairs), "total": len(pairs)}
    if pair is None:
        return {"pair": None, "progress": progress}
    return {"pair": {"pair_id": pair["pair_id"], "a": _record_view(by_id[pair["a"]]),
                     "b": _record_view(by_id[pair["b"]]), "label": labels.get(pair["pair_id"]),
                     "label_by": meta.get(pair["pair_id"], {}).get("by"),
                     "label_why": meta.get(pair["pair_id"], {}).get("why")},
            "progress": progress, "labels": calibrate.LABELS}


@app.post("/api/label", dependencies=ADMIN)
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


@app.get("/api/admin/auth")
def admin_auth():
    """Нужен ли пароль (страницы спрашивают его до показа содержимого)."""
    return {"required": bool(os.getenv("PPU_ADMIN_TOKEN"))}


@app.post("/api/admin/check", dependencies=ADMIN)
def admin_check():
    return {"ok": True}


@app.get("/admin")
def admin_page():
    return FileResponse(STATIC / "admin.html")


@app.get("/api/index/status", dependencies=ADMIN)
def index_status():
    reg, src = _registry_path(), _source_file()
    name = (src.read_text(encoding="utf-8") if src.exists() else reg.name) if reg.exists() else None
    return {**JOB.snapshot(), "token_required": bool(os.getenv("PPU_ADMIN_TOKEN")),
            "registry": name,
            "db": {"configured": db.configured(), "target": db.describe() if db.configured() else None}}


@app.post("/api/index/upload", dependencies=ADMIN)
async def index_upload(request: Request, filename: str = "registry.xlsx"):
    """Тело запроса — сам файл Excel. Сохраняет его и запускает пересборку в фоне."""
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


@app.post("/api/db/check", dependencies=ADMIN)
def db_check():
    """Подключиться к базе и показать, узнаются ли колонки. Ничего не меняет."""
    try:
        return db.check()
    except db.DBError as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.post("/api/index/rebuild-db", dependencies=ADMIN)
def index_rebuild_db():
    """Пересобрать индекс из базы данных (вместо Excel)."""
    if not db.configured():
        raise HTTPException(status_code=422, detail="База не настроена: DB_* в .env")

    def work(progress):
        return rebuild_from_db(_index_dir(), _cache_path(), progress)
    if not JOB.start(work, on_success=_reload, source=f"база данных {db.describe()}"):
        raise HTTPException(status_code=409, detail="Сборка индекса уже идёт")
    return JOB.snapshot()


@app.post("/api/index/rebuild", dependencies=ADMIN)
def index_rebuild():
    """Пересобрать из последнего загруженного реестра (например, после обрыва)."""
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


@app.get("/api/calib/status", dependencies=ADMIN)
def calib_status():
    pairs = calibrate.load_pairs(_calib_dir())
    meta = calibrate.load_label_meta(_calib_dir())
    ids = {p["pair_id"] for p in pairs}
    by_label, by_llm = {}, 0
    for pid, row in meta.items():
        if pid in ids:
            by_label[row["label"]] = by_label.get(row["label"], 0) + 1
            by_llm += row.get("by") == "llm"
    path = thresholds_path()
    return {"pairs": len(pairs), "labeled": sum(by_label.values()), "by_label": by_label,
            "labeled_by_llm": by_llm, "llm": judge() is not None,
            "label_names": {**calibrate.LABELS, "unclear": "непонятно"},
            "thresholds": {"custom": path.exists(), "source": active_calibration().source},
            "token_required": bool(os.getenv("PPU_ADMIN_TOKEN")),
            "job": CALIB_JOB.snapshot()}


@app.post("/api/calib/sample", dependencies=ADMIN)
def calib_sample(req: SampleRequest):
    """Выбрать пары для разметки в фоне: добавить к уже выбранным или заменить их."""
    index, _ = engine()
    if len(index) < 10:
        raise HTTPException(status_code=422, detail="В базе слишком мало записей для калибровки")

    calib_dir = _calib_dir()

    def work(progress):
        return calibrate.sample_to_dir(
            index, calib_dir, req.n_pairs, append=req.append,
            progress=lambda done, total: progress(stage="Поиск ближайших соседей",
                                                  done=done, total=total))
    if not CALIB_JOB.start(work, on_success=_records_by_id.cache_clear, source="sample"):
        raise HTTPException(status_code=409, detail="Уже идёт выбор или разметка пар")
    return CALIB_JOB.snapshot()


@app.post("/api/calib/fit", dependencies=ADMIN)
def calib_fit():
    """Подобрать пороги по разметке и показать, что изменится. Ничего не применяет."""
    try:
        _, text = calibrate.fit_from_dir(_calib_dir())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"report": text}


@app.post("/api/calib/apply", dependencies=ADMIN)
def calib_apply():
    """Подобрать пороги и сразу применить: проверка ППУ начнёт их использовать со следующего запроса."""
    try:
        fitted, text = calibrate.fit_from_dir(_calib_dir())
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    calibrate.save_calibration(fitted)
    return {"report": text, "source": fitted.source}


@app.post("/api/calib/reset", dependencies=ADMIN)
def calib_reset():
    """Вернуть пороги по умолчанию (с синтетики). Разметка не удаляется."""
    thresholds_path().unlink(missing_ok=True)
    return {"source": active_calibration().source}


_llm_label_token: CancelToken | None = None


@app.post("/api/calib/llm", dependencies=ADMIN)
def calib_llm():
    """Разметить неразмеченные пары LLM-судьёй в фоне. Метки можно поправить на /label."""
    global _llm_label_token
    j = judge()
    if j is None:
        raise HTTPException(status_code=503, detail="LLM не настроена: LLM_BASE_URL и LLM_MODEL в .env")
    if not calibrate.load_pairs(_calib_dir()):
        raise HTTPException(status_code=422, detail="Сначала выберите пары")
    by_id = _records_by_id()
    token = CancelToken()
    calib_dir = _calib_dir()

    def work(progress):
        return calibrate.llm_label_pairs(
            by_id, j, calib_dir, token=token,
            progress=lambda done, total: progress(stage="LLM размечает пары", done=done, total=total))
    if not CALIB_JOB.start(work, source="llm"):
        raise HTTPException(status_code=409, detail="Уже идёт выбор или разметка пар")
    _llm_label_token = token
    return CALIB_JOB.snapshot()


@app.post("/api/calib/llm/stop", dependencies=ADMIN)
def calib_llm_stop():
    """Остановить разметку LLM: уже размеченные пары сохранятся."""
    if _llm_label_token is not None:
        _llm_label_token.cancel()
    return CALIB_JOB.snapshot()
