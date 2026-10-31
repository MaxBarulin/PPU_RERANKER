"""Очистка текста ППУ для поиска.

Оригинальные поля не трогаем — их показываем людям. Для поиска строим
нормализованные копии: без HTML и заглушек «См.вложение», с раскрытыми
сокращениями, плюс отдельно извлекаем место (цех, участок) и номера
проектов, чтобы отличать «та же идея в другом цехе» от повтора.
"""
import html
import re

TEXT_FIELDS = ("name", "before", "after", "proposal", "result")
BODY_FIELDS = ("before", "after", "proposal")

# Заглушки вместо текста: «См.вложение», «см. приложение», «См. файл»
PLACEHOLDER_RE = re.compile(
    r"\bсм\.?\s*(?:во?\s+)?(?:вложени|приложени|файл|документ)\w*\.?", re.I
)
LIST_TAG_RE = re.compile(r"</?(?:li|ul|ol|p|br|div)\b[^>]*>", re.I)
TAG_RE = re.compile(r"<[^>]+>")
HAS_CONTENT_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁё]")

# (шаблон, замена). Порядок важен: длинные формы раньше коротких.
# Пополнять по отчёту prepare (раздел «Кандидаты в сокращения»).
ABBREVIATIONS = [
    (r"\bпр-ва\b", "производства"),
    (r"\bпр-ти\b", "производительности"),
    (r"\bпов-ие\b", "повышение"),
    (r"\bорг\.\s*", "организация "),
    (r"\bэл\.\s*", "электронного "),
    (r"\bраб\.\s*", "рабочего "),
    (r"\bпольз\.\s*", "пользователя "),
    (r"\bизг\.\s*", "изготовления "),
    (r"\bинвест\.\s*", "инвестиционного "),
    (r"\bмод\.\s*", "модели "),
    (r"\bинв\.\s*", "инвентарный "),
    (r"\bуч\.?\s*(?=№?\s*\d)", "участок "),
    (r"\bпр\.\s*(?=\d)", "проект "),
    (r"\bт\.\s*д\.", "так далее"),
    (r"\bт\.\s*п\.", "тому подобное"),
]
# Аббревиатуры (с учётом регистра) не заменяем, а дописываем расшифровку
ACRONYMS = {
    "РКД": "рабочая конструкторская документация",
    "ДСЕ": "детали и сборочные единицы",
    "ОТЗ": "отдел труда и заработной платы",
}
_ABBR = [(re.compile(p, re.I), r) for p, r in ABBREVIATIONS] + [
    (re.compile(rf"\b{a}\b"), f"{a} ({full})") for a, full in ACRONYMS.items()
]

WORKSHOP_RE = re.compile(r"\bцех\w*\s*№?\s*(\d+)", re.I)
SITE_RE = re.compile(r"\bучаст\w*\s*№?\s*(\d+)", re.I)
PROJECT_RE = re.compile(r"\b(?:проект|заказ)\w*\s*№?\s*(\d{3,})", re.I)
MODEL_RE = re.compile(r"\bмодели\s+([A-ZА-ЯЁ0-9][\w\-]*\d[\w\-]*)", re.I)
INVENTORY_RE = re.compile(r"\bинвентарный\s*№\s*(\d+)", re.I)
# Место без номера («Участок люм-контроля»). Ищем только в названии:
# в описании такой шаблон ловит мусор вроде «на участке участка №19»
NAMED_PLACE_RE = re.compile(r"\b(цех|участ)\w*\s+(?!№|\d)([а-яёa-z][\w\-]*)", re.I)
DATE_RE = re.compile(r"\b\d{1,2}\.\d{1,2}\.\d{2,4}\b")

# Что вырезаем из названия, чтобы получить «суть» без места и дат
LOCATION_RE = re.compile(
    r"\b(?:цех|участ)\w*\s*№?\s*[\w\-]*(?:\s*\([^)]*\))?", re.I
)
PROJECT_STRIP_RE = re.compile(r"\b(?:проект|заказ)\w*\s*№?\s*\d+", re.I)
TRAILING_JUNK_RE = re.compile(r"(?:[\s.,;:\-]|\b(?:на|в|для|по)\b)+$", re.I)

# Кандидаты в сокращения для отчёта
ABBR_DOT_RE = re.compile(r"\b([А-ЯЁа-яё]{1,7})\.(?=\s*[а-яё0-9])")
ABBR_HYPHEN_RE = re.compile(r"\b[А-ЯЁа-яё]{1,4}-[а-яё]{1,3}\b")
ACRONYM_RE = re.compile(r"\b[А-ЯЁ]{2,6}\b")


def clean_text(value) -> str:
    """Убирает HTML, заглушки и лишние пробелы. Пусто, если смысла нет."""
    if value is None:
        return ""
    text = html.unescape(str(value)).replace("\xa0", " ")
    text = LIST_TAG_RE.sub("; ", text)
    text = TAG_RE.sub(" ", text)
    text = PLACEHOLDER_RE.sub(" ", text)
    text = re.sub(r"\s*;\s*(?:;\s*)+", "; ", text)
    text = re.sub(r"([.!?])\s*;", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip(" ;")
    return text if HAS_CONTENT_RE.search(text) else ""


def expand_abbreviations(text: str) -> str:
    for pattern, repl in _ABBR:
        text = pattern.sub(repl, text)
    return re.sub(r"\s+", " ", text).strip()


def extract_entities(text: str) -> dict[str, list[str]]:
    """Места и номера из нормализованного текста (после expand_abbreviations)."""
    found = {
        "workshops": WORKSHOP_RE.findall(text),
        "sites": SITE_RE.findall(text),
        "projects": PROJECT_RE.findall(text),
        "models": MODEL_RE.findall(text),
        "inventory": INVENTORY_RE.findall(text),
    }
    return {k: sorted(set(v)) for k, v in found.items() if v}


def named_places(name_norm: str) -> list[str]:
    kinds = {"цех": "цех", "участ": "участок"}
    return sorted({f"{kinds[k.lower()]} {v.lower()}" for k, v in NAMED_PLACE_RE.findall(name_norm)})


def core_name(name_norm: str) -> str:
    """Название без дат, цехов, участков и номеров проектов."""
    text = DATE_RE.sub(" ", name_norm)
    text = LOCATION_RE.sub(" ", text)
    text = PROJECT_STRIP_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text)
    text = TRAILING_JUNK_RE.sub("", text).strip(" .,;:-")
    return text


def completeness(rec: dict) -> str:
    """full — заполнены все три поля описания, partial — часть, name_only — только название."""
    filled = sum(bool(rec[f"{f}_clean"]) for f in BODY_FIELDS)
    if filled == len(BODY_FIELDS):
        return "full"
    return "partial" if filled else "name_only"


def normalize_record(rec: dict) -> dict:
    """Возвращает копию записи с полями *_clean, *_norm, core_name, entities, completeness."""
    out = dict(rec)
    for f in TEXT_FIELDS:
        out[f"{f}_clean"] = clean_text(rec.get(f))
        out[f"{f}_norm"] = expand_abbreviations(out[f"{f}_clean"])
    out["core_name"] = core_name(out["name_norm"])
    all_text = " ".join(out[f"{f}_norm"] for f in TEXT_FIELDS)
    out["entities"] = extract_entities(all_text)
    if places := named_places(out["name_norm"]):
        out["entities"]["places"] = places
    out["completeness"] = completeness(out)
    return out


def abbreviation_candidates(texts) -> dict[str, list[str]]:
    """Похожие на сокращения токены. Подавать текст после expand_abbreviations."""
    dots, hyphens, acronyms = [], [], []
    for t in texts:
        dots += [m.lower() + "." for m in ABBR_DOT_RE.findall(t)]
        hyphens += [m.lower() for m in ABBR_HYPHEN_RE.findall(t)]
        acronyms += ACRONYM_RE.findall(t)
    return {"с точкой": dots, "через дефис": hyphens, "аббревиатуры": acronyms}
