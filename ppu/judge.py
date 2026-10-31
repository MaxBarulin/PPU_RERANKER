"""Этап 4: LLM-судья для спорных случаев.

Векторы уверенно ловят повторы у записей с описанием, но у записей
«только название» и у пар «та же проблема / другое решение» ошибаются.
Такие случаи (needs_llm) отдаём LLM: она читает новое ППУ и 3–4 кандидата
и для каждого говорит, что это за связь.

Рассчитано на рабочий CPU (~10 т/с):
- постоянная часть промпта (правила и пример) идёт первой — llama-server
  кэширует её между запросами, считать заново приходится только ППУ;
- тексты обрезаны, кандидатов немного;
- ответ — короткие коды, пояснение — несколько слов.
"""
from .index import view_texts
from .llm import LLM, CancelToken

MAX_QUERY_CHARS = 1200
MAX_CAND_CHARS = 600
MAX_CANDIDATES = 4

# Код ответа LLM -> связь из assess
CODES = {
    "dup": "repeat",
    "place": "other_place",
    "alt": "alternative",
    "sim": "similar",
    "diff": "far",
    "unclear": "similar",
}

SYSTEM = """Ты эксперт комиссии по предложениям по улучшению (ППУ) на судостроительном заводе.
Тебе дают НОВОЕ ППУ и несколько ППУ из реестра. Для каждого ППУ из реестра определи связь с новым:
- dup — то же предложение: та же проблема и по сути то же решение (слова могут быть другими);
- place — то же предложение, но явно для другого цеха или участка;
- alt — та же проблема, но принципиально другое решение;
- sim — похожая тема или то же оборудование, но другая проблема;
- diff — не связаны;
- unclear — нельзя понять (например, в реестре только короткое общее название).
Если у ППУ из реестра есть только название — суди по названию, но dup ставь, только если
название однозначно описывает то же самое; общие названия («Улучшение условий труда») — unclear.
Ответ — только JSON: {"items": [{"id": "<id>", "v": "<код>", "why": "<до 8 слов>"}]}

Пример.
НОВОЕ: Подставка под ноги для сварщика. Проблема: устают ноги при работе сидя. Решение: сварить подставку.
РЕЕСТР:
[A1] Подставка для ног на сварочном посту. Проблема: неудобно сидеть, затекают ноги. Решение: изготовить подставку из уголка.
[A2] Регулируемый стул для сварщика. Проблема: устают ноги и спина. Решение: купить регулируемые стулья.
[A3] Вытяжка на сварочном посту.
Ответ: {"items": [{"id": "A1", "v": "dup", "why": "та же подставка для ног"},
{"id": "A2", "v": "alt", "why": "та же проблема, решение - стулья"},
{"id": "A3", "v": "sim", "why": "тот же пост, другая проблема"}]}"""


def _ppu_text(rec: dict, limit: int) -> str:
    t = view_texts(rec)
    text = t["full"].replace("\n", ". ")
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "…"
    return text


def build_prompt(query: dict, candidates: list[dict]) -> str:
    lines = [f"НОВОЕ: {_ppu_text(query, MAX_QUERY_CHARS)}", "РЕЕСТР:"]
    for c in candidates:
        suffix = " (в реестре только название)" if c["completeness"] == "name_only" else ""
        lines.append(f"[{c['id']}] {_ppu_text(c['record'], MAX_CAND_CHARS)}{suffix}")
    lines.append("Ответ:")
    return "\n".join(lines)


class Judge:
    def __init__(self, llm: LLM, max_tokens: int = 400):
        self.llm = llm
        self.max_tokens = max_tokens

    def __call__(self, query: dict, candidates: list[dict],
                 token: CancelToken | None = None) -> dict[str, dict]:
        """id кандидата -> {"relation", "code", "why"}. Кандидат — элемент assess с полем record."""
        candidates = candidates[:MAX_CANDIDATES]
        if not candidates:
            return {}
        data = self.llm.json(SYSTEM, build_prompt(query, candidates),
                             temperature=0.0, max_tokens=self.max_tokens, token=token)
        items = data.get("items", []) if isinstance(data, dict) else data
        known = {c["id"] for c in candidates}
        out = {}
        for it in items:
            cid, code = str(it.get("id", "")), str(it.get("v", "")).strip().lower()
            if cid in known and code in CODES:
                out[cid] = {"relation": CODES[code], "code": code, "why": str(it.get("why", ""))[:120]}
        return out
