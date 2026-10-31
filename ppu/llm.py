"""Чат-модель через OpenAI-совместимый API с ответом в JSON.

Рассуждения (thinking) выключаем: на рабочем CPU это 10 т/с, каждый
лишний токен — это заметные секунды. Как выключать, зависит от сервера:
polza.ai понимает `reasoning`, llama-server — `chat_template_kwargs`.
Свой вариант можно задать в .env: LLM_EXTRA_BODY={"...": ...}

Ответ читаем потоком: так запрос можно отменить (CancelToken) — поток
закрывается, и llama-server перестаёт генерировать, а не занимает CPU
ответом, который уже никто не ждёт. Пока идёт префилл, кусков нет,
поэтому отмена срабатывает с первым токеном ответа.
"""
import json
import os
import re
import threading
from urllib.parse import urlparse

import openai
from openai import OpenAI

from .config import Endpoint

NO_THINKING = {"reasoning": {"enabled": False},
               "chat_template_kwargs": {"enable_thinking": False}}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_decoder = json.JSONDecoder()


class LLMError(Exception):
    """Ошибка с текстом, который можно показать пользователю."""


class LLMCancelled(LLMError):
    pass


class CancelToken:
    def __init__(self):
        self._event = threading.Event()

    def cancel(self):
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()


def is_local(base_url: str) -> bool:
    return (urlparse(base_url).hostname or "") in LOCAL_HOSTS


def parse_json(text: str):
    """JSON из ответа модели: без обёртки ```json и пояснений вокруг.

    Если модель выдала несколько объектов подряд: с разными ключами —
    склеиваем в один, с одинаковыми — возвращаем списком.
    """
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S)
    found, pos = [], 0
    while (start := next((i for i in range(pos, len(text)) if text[i] in "{["), None)) is not None:
        try:
            obj, pos = _decoder.raw_decode(text, start)
            found.append(obj)
        except json.JSONDecodeError:
            pos = start + 1
    if not found:
        raise ValueError(f"В ответе нет JSON: {text[:200]!r}")
    if len(found) > 1 and all(isinstance(o, dict) for o in found):
        keys = [k for o in found for k in o]
        if len(keys) == len(set(keys)):
            return {k: v for o in found for k, v in o.items()}
        return found
    return found[0]


class LLM:
    def __init__(self, endpoint: Endpoint, model: str | None = None, timeout: float = 600,
                 extra_body: dict | None = None):
        self.model = model or endpoint.model
        if not endpoint.configured or not self.model:
            raise ValueError("LLM не настроена: задай LLM_BASE_URL и LLM_MODEL в .env")
        self.base_url = endpoint.base_url
        self._client = OpenAI(base_url=endpoint.base_url, api_key=endpoint.api_key,
                              timeout=timeout, max_retries=3)
        extra = os.getenv("LLM_EXTRA_BODY")
        self.extra_body = extra_body if extra_body is not None \
            else json.loads(extra) if extra else NO_THINKING
        self._stream_usage = True  # не все серверы понимают stream_options
        # расход последнего вызова: токены промпта и длина ответа (без рассуждений)
        self.last_usage: dict = {}

    def _stream(self, messages, temperature, max_tokens):
        kwargs = dict(model=self.model, messages=messages, temperature=temperature,
                      max_tokens=max_tokens, extra_body=self.extra_body, stream=True)
        if self._stream_usage:
            try:
                return self._client.chat.completions.create(
                    **kwargs, stream_options={"include_usage": True})
            except openai.BadRequestError:
                self._stream_usage = False
        return self._client.chat.completions.create(**kwargs)

    def _complete(self, system: str, user: str, temperature: float, max_tokens: int,
                  token: CancelToken | None) -> tuple[str, str | None]:
        """Текст ответа (без рассуждений) и finish_reason."""
        if token and token.cancelled:
            raise LLMCancelled("Запрос отменён")
        stream = self._stream([{"role": "system", "content": system},
                               {"role": "user", "content": user}], temperature, max_tokens)
        parts, finish, usage = [], None, None
        try:
            for chunk in stream:
                if token and token.cancelled:
                    raise LLMCancelled("Запрос отменён")
                usage = chunk.usage or usage
                if chunk.choices:
                    choice = chunk.choices[0]
                    parts.append(choice.delta.content or "")
                    finish = choice.finish_reason or finish
        finally:
            stream.close()  # при отмене — обрываем соединение, сервер прекращает генерацию
        content = "".join(parts)
        self.last_usage = {"prompt_tokens": usage.prompt_tokens if usage else None,
                           "completion_tokens": usage.completion_tokens if usage else None,
                           "answer_chars": len(content)}
        return content, finish

    def json(self, system: str, user: str, temperature: float = 0.2,
             max_tokens: int = 2000, retries: int = 2, token: CancelToken | None = None):
        """Ответ модели, разобранный как JSON. При битом JSON переспрашиваем."""
        last_error = None
        for _ in range(retries + 1):
            try:
                content, finish = self._complete(system, user, temperature, max_tokens, token)
            except openai.APIConnectionError as e:
                raise LLMError(f"Нет связи с LLM ({self.base_url}): {e}") from e
            except openai.APIStatusError as e:
                raise LLMError(f"LLM ответила ошибкой {e.status_code}: {e.message}") from e
            if not content.strip() and finish == "length":
                # переспрашивать бесполезно: лимит уходит на рассуждения
                raise LLMError(
                    f"Модель не успела ответить: все {max_tokens} токенов ушли на рассуждения. "
                    "Выключите рассуждения (llama-server: --reasoning off; polza: "
                    'LLM_EXTRA_BODY={"reasoning": {"effort": "low"}}) '
                    "или поднимите PPU_LLM_MAX_TOKENS.")
            try:
                return parse_json(content)
            except (ValueError, json.JSONDecodeError) as e:
                last_error = e
        if not content.strip():
            raise LLMError("Модель вернула пустой ответ") from last_error
        raise LLMError(f"Модель ответила не в формате JSON: {content[:200]!r}") from last_error
