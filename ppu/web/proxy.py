"""Доступ к моделям сервера через веб-сервис: OpenAI-совместимый /v1.

Модели слушают только 127.0.0.1, наружу открыт один порт - порт сервиса.
Запросы пересылаются как есть, ответы (в том числе потоковые, stream=true) -
тоже как есть:

    POST /v1/embeddings          -> EMB_BASE_URL (bge-m3)
    GET  /v1/models              -> обе модели одним списком
    всё остальное под /v1/...    -> LLM_BASE_URL (chat/completions, completions …)

Без ограничений на число и размер запросов. Ключ доступа - по желанию:
PPU_API_TOKEN в .env, тогда нужен заголовок Authorization: Bearer <ключ>.
Тексты запросов в лог не пишутся (в логе uvicorn - только путь и код ответа).
"""
import asyncio
import os
import secrets

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.background import BackgroundTask

from .. import config
from ..llm import is_local

router = APIRouter(prefix="/v1")

# генерация длинного ответа идёт минутами - ждём сколько нужно, но не вечно
TIMEOUT = httpx.Timeout(connect=10, read=1800, write=60, pool=60)
# заголовки, которые нельзя пересылать: их выставляет сам транспорт
HOP = {"host", "content-length", "connection", "keep-alive", "transfer-encoding", "te", "trailer",
       "upgrade", "proxy-authorization", "proxy-authenticate", "authorization", "accept-encoding",
       "cookie", "x-admin-token"}
DROP_BACK = {"content-length", "content-encoding", "transfer-encoding", "connection", "keep-alive",
             "server", "date"}

_transport: httpx.AsyncBaseTransport | None = None  # для тестов
_client: httpx.AsyncClient | None = None


def client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=TIMEOUT, transport=_transport,
                                    limits=httpx.Limits(max_connections=None, max_keepalive_connections=20))
    return _client


def _check_key(request: Request) -> None:
    expected = os.getenv("PPU_API_TOKEN", "")
    if not expected:
        return
    auth = request.headers.get("authorization", "")
    given = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    if not given or not secrets.compare_digest(given.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Нужен ключ: Authorization: Bearer <PPU_API_TOKEN>")


def _upstream(kind: str) -> config.Endpoint:
    ep = config.embeddings() if kind == "emb" else config.llm()
    name = "векторов (EMB_BASE_URL)" if kind == "emb" else "LLM (LLM_BASE_URL)"
    if not ep.configured:
        raise HTTPException(status_code=503, detail=f"Модель {name} не настроена в .env")
    # без ключа наружу отдаём только свои модели: внешний платный API с ключом из .env
    # (например, polza дома) иначе стал бы доступен всей сети
    if not is_local(ep.base_url) and not os.getenv("PPU_API_TOKEN"):
        raise HTTPException(status_code=503, detail=f"Модель {name} не на этом сервере: пересылка к ней "
                            "открыта только с ключом PPU_API_TOKEN")
    return ep


def _headers(request: Request, ep: config.Endpoint) -> dict:
    h = {k: v for k, v in request.headers.items() if k.lower() not in HOP}
    if ep.api_key and ep.api_key != "none":
        h["authorization"] = f"Bearer {ep.api_key}"
    return h


async def _forward(request: Request, kind: str, path: str):
    _check_key(request)
    ep = _upstream(kind)
    url = f"{ep.base_url}/{path}"
    body = await request.body()
    req = client().build_request(request.method, url, params=request.query_params,
                                 headers=_headers(request, ep), content=body)
    try:
        resp = await client().send(req, stream=True)
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail=f"Модель не ответила вовремя ({url})")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Модель недоступна ({url}): {type(e).__name__}")
    headers = {k: v for k, v in resp.headers.items() if k.lower() not in DROP_BACK}
    headers["cache-control"] = "no-store"
    # клиент закрыл соединение - закрываем и запрос к модели: llama.cpp перестанет генерировать
    return StreamingResponse(resp.aiter_bytes(), status_code=resp.status_code, headers=headers,
                             background=BackgroundTask(resp.aclose))


@router.post("/embeddings")
async def embeddings(request: Request):
    return await _forward(request, "emb", "embeddings")


@router.get("/models")
async def models(request: Request):
    """Список моделей обоих серверов; если один не отвечает - отдаём второй."""
    _check_key(request)
    data, errors = [], []

    async def one(kind: str):
        try:
            ep = _upstream(kind)
            r = await client().get(f"{ep.base_url}/models", headers=_headers(request, ep), timeout=10)
            r.raise_for_status()
            return r.json().get("data", [])
        except (HTTPException, httpx.HTTPError, ValueError) as e:
            errors.append(f"{kind}: {getattr(e, 'detail', None) or type(e).__name__}")
            return []

    for part in await asyncio.gather(one("llm"), one("emb")):
        data += part
    if not data and errors:
        raise HTTPException(status_code=502, detail="; ".join(errors))
    return JSONResponse({"object": "list", "data": data}, headers={"cache-control": "no-store"})


@router.api_route("/{path:path}", methods=["GET", "POST"])
async def llm(path: str, request: Request):
    return await _forward(request, "llm", path)
