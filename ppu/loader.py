"""Чтение реестра ППУ из Excel.

Лист и строку заголовка ищем сами: в реальном реестре они могут
отличаться от примера (в примере данные на «Лист2», «Лист1» пустой).
"""
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import openpyxl

# Каноническое имя поля -> варианты заголовка в реестре (после _norm_header):
# заголовки Excel и названия колонок таблицы URPS.dbo.PPU_Export (MS SQL)
COLUMNS = {
    "reg_no": ["рег. №", "рег.№", "рег №", "регистрационный номер", "№", "№ п/п", "regnum"],
    "name": ["наименование", "наименование ппу", "title"],
    "before": ["до улучшения", "beforeimprovement"],
    "after": ["после улучшения", "afterimprovement"],
    "proposal": ["предложения", "предложение", "proposals", "offer", "offers"],
    "result": ["результат", "result0"],
    "status": ["статус"],
    "effect": ["ээ", "экономический эффект", "ee"],
    "date_submitted": ["дата подачи", "filingdate"],
    "date_registered": ["дата регистрации", "regdate"],
    "date_reviewed": ["дата рассмотрения", "determinationdate"],
    "date_implemented": ["дата реализации", "realizationdate"],
    "date_effect": ["дата ээ", "eeapprovaldate"],
}
REQUIRED = ("name", "before", "after", "proposal")
# в базе колонки «Предложения» может не быть — без неё запись всё равно полноценная
DB_REQUIRED = ("name", "before", "after")
HEADER_SCAN_ROWS = 10


def _norm_header(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def _match_columns(header_row) -> dict[str, int]:
    """Канонические поля -> индекс колонки."""
    # канонические имена тоже подходят: в SQL-запросе можно написать AS reg_no, AS name …
    lookup = {field: field for field in COLUMNS}
    lookup.update({alias: field for field, aliases in COLUMNS.items() for alias in aliases})
    mapping = {}
    for idx, cell in enumerate(header_row):
        field = lookup.get(_norm_header(cell))
        if field and field not in mapping:
            mapping[field] = idx
    return mapping


def _find_table(wb):
    """Первый лист, где в первых строках есть заголовок с нужными колонками."""
    for ws in wb.worksheets:
        for row_idx, row in enumerate(
            ws.iter_rows(max_row=HEADER_SCAN_ROWS, values_only=True), start=1
        ):
            mapping = _match_columns(row)
            if all(f in mapping for f in REQUIRED):
                return ws, row_idx, mapping
    raise ValueError(f"Не найден лист с колонками: {', '.join(REQUIRED)}")


def _convert(value):
    if isinstance(value, (datetime, date)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    if isinstance(value, str):
        value = value.strip()
        return value or None
    if isinstance(value, Decimal):  # деньги из MS SQL (money/decimal)
        return int(value) if value == value.to_integral_value() else float(value)
    return value


def records_from_rows(header, rows, first_row: int = 1, id_prefix: str = "row",
                      sheet: str | None = None, mapping: dict[str, int] | None = None,
                      required: tuple[str, ...] = REQUIRED) -> list[dict]:
    """Строки таблицы (Excel или SQL) -> записи с каноническими полями.

    `id` — регистрационный номер, а если его нет — `<id_prefix><номер строки>`.
    """
    mapping = mapping if mapping is not None else _match_columns(header)
    missing = [f for f in required if f not in mapping]
    if missing:
        raise ValueError(f"Нет колонок: {', '.join(missing)}")
    records = []
    for row_idx, row in enumerate(rows, start=first_row):
        rec = {field: _convert(row[idx]) if idx < len(row) else None
               for field, idx in mapping.items()}
        if not any(rec.get(f) for f in required):
            continue
        reg_no = rec.get("reg_no")
        if isinstance(reg_no, float) and reg_no.is_integer():
            reg_no = rec["reg_no"] = int(reg_no)
        rec["id"] = str(reg_no) if reg_no is not None else f"{id_prefix}{row_idx}"
        if sheet is not None:
            rec["sheet"] = sheet
        rec["row"] = row_idx
        records.append(rec)
    return records


def load_registry(path: str | Path) -> list[dict]:
    """Строки реестра как словари с каноническими полями.

    У каждой записи есть `id`: регистрационный номер, а если его нет
    (ещё не зарегистрированные ППУ) — `row<номер строки>`.
    """
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws, header_row, mapping = _find_table(wb)
        return records_from_rows(None, ws.iter_rows(min_row=header_row + 1, values_only=True),
                                 first_row=header_row + 1, sheet=ws.title, mapping=mapping)
    finally:
        wb.close()
