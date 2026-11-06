"""Чтение реестра ППУ из MS SQL - вместо загрузки Excel.

    python -m ppu.db --check      # подключиться, показать колонки и пару записей

Настройки - в .env (DB_SERVER, DB_NAME, DB_USER, DB_PASSWORD, DB_TABLE).
Колонки узнаются так же, как заголовки Excel («Рег. №», «Наименование»,
«До улучшения» …), по названиям из URPS.dbo.PPU_Export (Title, RegNum,
BeforeImprovement …) или по каноническим именам (reg_no, name, before …).
Обязательны наименование, «до» и «после»; «Предложения» - если есть.
Если в таблице они названы иначе - запрос с переименованием в файле
DB_QUERY_FILE, например:

    SELECT [РегНомер] AS reg_no, [Название] AS name, [Было] AS before, ...
    FROM dbo.PPU_Export

Запрос фиксированный (из .env/файла, не от пользователя), учётка - только на чтение.
"""
import argparse
import os
import re
from collections import Counter
from pathlib import Path

from .loader import DB_REQUIRED, _match_columns, records_from_rows

# имя таблицы/представления: буквы, цифры, _, точка (схема), квадратные скобки
TABLE_RE = re.compile(r"^[\w.\[\] ]+$")
FIELD_TITLES = {"reg_no": "рег. №", "name": "наименование", "before": "до улучшения",
                "after": "после улучшения", "proposal": "предложения", "result": "результат",
                "status": "статус", "effect": "ЭЭ", "date_submitted": "дата подачи"}


class DBError(Exception):
    """Ошибка с текстом, который можно показать пользователю."""


def settings() -> dict:
    return {k: os.getenv(f"DB_{k.upper()}", "").strip()
            for k in ("server", "port", "name", "user", "password", "table", "query_file")}


def configured(s: dict | None = None) -> bool:
    s = s or settings()
    return bool(s["server"] and s["name"] and (s["table"] or s["query_file"]))


def describe(s: dict | None = None) -> str:
    """Куда подключаемся - без пароля."""
    s = s or settings()
    what = s["table"] or Path(s["query_file"]).name
    return f"{s['server']}{':' + s['port'] if s['port'] else ''} / {s['name']} / {what}"


def table_name(s: dict) -> str:
    table = s["table"]
    if not TABLE_RE.match(table):
        raise DBError(f"Странное имя таблицы DB_TABLE: {table!r}")
    if "[" not in table:
        table = ".".join(f"[{part.strip()}]" for part in table.split("."))
    return table


def _col(name: str) -> str:
    return "[" + name.replace("]", "]]") + "]"


def query(s: dict, columns: list[str] | None = None) -> str:
    """Запрос за данными: из DB_QUERY_FILE, иначе - только нужные колонки таблицы.

    Без columns - пустой запрос (TOP 0) только чтобы узнать названия колонок:
    в таблице могут быть тяжёлые колонки (вложения), их не читаем.
    """
    if s["query_file"]:
        path = Path(s["query_file"])
        if not path.exists():
            raise DBError(f"Нет файла запроса DB_QUERY_FILE: {path}")
        return path.read_text(encoding="utf-8")
    if columns is None:
        return f"SELECT TOP 0 * FROM {table_name(s)}"
    return f"SELECT {', '.join(_col(c) for c in columns)} FROM {table_name(s)}"


def _connect(s: dict):
    if not configured(s):
        raise DBError("База не настроена: DB_SERVER, DB_NAME и DB_TABLE (или DB_QUERY_FILE) в .env")
    try:
        import pymssql
    except ImportError as e:
        raise DBError("Не установлен драйвер: venv/bin/pip install pymssql") from e
    kwargs = dict(server=s["server"], user=s["user"] or None, password=s["password"] or None,
                  database=s["name"], login_timeout=15, timeout=600, charset="UTF-8",
                  appname="ppu-check")
    if s["port"]:
        kwargs["port"] = s["port"]
    try:
        return pymssql, pymssql.connect(**kwargs)
    except pymssql.Error as e:
        raise DBError(f"Не удалось подключиться к {describe(s)}: {_short(e)}") from e


def _run(driver, conn, sql: str) -> tuple[list[str], list[tuple]]:
    cur = conn.cursor()
    try:
        cur.execute(sql)
    except driver.Error as e:
        raise DBError(f"Ошибка запроса: {_short(e)}") from e
    return [d[0] for d in cur.description or []], cur.fetchall()


def fetch(s: dict | None = None) -> tuple[list[str], list[tuple], list[str]]:
    """Колонки и строки для реестра + все колонки таблицы.

    С DB_QUERY_FILE - что вернул запрос. Иначе сначала узнаём колонки таблицы,
    потом читаем только узнанные (наименование, до, после …).
    """
    s = s or settings()
    driver, conn = _connect(s)
    try:
        if s["query_file"]:
            columns, rows = _run(driver, conn, query(s))
            return columns, rows, columns
        all_columns, _ = _run(driver, conn, query(s))
        mapping = _match_columns(all_columns)
        missing = [f for f in DB_REQUIRED if f not in mapping]
        if missing:
            return all_columns, [], all_columns
        needed = [all_columns[i] for i in sorted(mapping.values())]
        columns, rows = _run(driver, conn, query(s, needed))
        return columns, rows, all_columns
    finally:
        conn.close()


def count_rows(s: dict) -> int | None:
    if s["query_file"]:
        return None
    driver, conn = _connect(s)
    try:
        _, rows = _run(driver, conn, f"SELECT COUNT(*) FROM {table_name(s)}")
        return int(rows[0][0])
    finally:
        conn.close()


def _short(e: Exception) -> str:
    """Суть ошибки pymssql/FreeTDS: без байтовых строк, кодов и служебных префиксов."""
    parts = []

    def walk(x):
        if isinstance(x, (tuple, list)):
            for y in x:
                walk(y)
        elif isinstance(x, bytes):
            parts.append(x.decode("utf-8", "replace"))
        elif isinstance(x, str):
            parts.append(x)
    walk(getattr(e, "args", ()) or str(e))
    text = " ".join(parts) or str(e)
    text = re.sub(r"DB-Lib error message \d+, severity \d+:", "", text)
    return re.sub(r"\s+", " ", text).strip()[:400]


def load_registry_db(s: dict | None = None) -> list[dict]:
    columns, rows, all_columns = fetch(s)
    try:
        return records_from_rows(columns, rows, first_row=1, id_prefix="db", required=DB_REQUIRED)
    except ValueError as e:
        raise DBError(f"{e}. Колонки в таблице: {', '.join(all_columns)}. "
                      "Нужен запрос с переименованием - DB_QUERY_FILE (см. docs)") from e


def check(s: dict | None = None) -> dict:
    """Подключиться и проверить, что колонки узнаются и данные похожи на реестр."""
    s = s or settings()
    columns, rows, all_columns = fetch(s)
    mapping = _match_columns(all_columns)
    missing = [f for f in DB_REQUIRED if f not in mapping]
    out = {"target": describe(s), "columns": all_columns,
           "mapped": {f: all_columns[i] for f, i in mapping.items()},
           "missing": [FIELD_TITLES.get(f, f) for f in missing],
           "not_used": [c for i, c in enumerate(all_columns) if i not in mapping.values()]}
    if missing:
        out["rows"] = count_rows(s)
        return out
    records = records_from_rows(columns, rows, first_row=1, id_prefix="db", required=DB_REQUIRED)
    dup = sum(n - 1 for n in Counter(r["id"] for r in records).values() if n > 1)
    out.update(rows=len(rows), records=len(records),
               without_reg_no=sum(r.get("reg_no") is None for r in records),
               duplicate_ids=dup,
               sample=[{"id": r["id"], "name": r.get("name"), "status": r.get("status"),
                        "date_submitted": r.get("date_submitted"), "effect": r.get("effect")}
                       for r in records[:3]])
    return out


def main():
    from . import config  # noqa: F401 - загружает .env

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="проверить подключение и колонки")
    parser.parse_args()
    try:
        res = check()
    except DBError as e:
        raise SystemExit(f"[ОШИБКА] {e}")
    print(f"Подключение: {res['target']} - строк: {res['rows'] if res['rows'] is not None else '?'}")
    print("Колонки:", ", ".join(res["columns"]))
    print("Узнаны:", ", ".join(f"{FIELD_TITLES.get(f, f)} ← {c}" for f, c in res["mapped"].items()))
    if res["not_used"]:
        print("Не используются:", ", ".join(res["not_used"]))
    if res["missing"]:
        raise SystemExit(f"[ОШИБКА] Не найдены колонки: {', '.join(res['missing'])}. "
                         "Нужен запрос с переименованием (DB_QUERY_FILE)")
    print(f"Записей ППУ: {res['records']}, без рег. номера: {res['without_reg_no']}, "
          f"повторов рег. номера: {res['duplicate_ids']}")
    for r in res["sample"]:
        print(f"  № {r['id']} · {r['name']} · {r['status'] or '-'} · {r['date_submitted'] or '-'}"
              f" · ЭЭ {r['effect'] if r['effect'] is not None else '-'}")
    print("Всё на месте - можно «Обновить из базы» на /admin")


if __name__ == "__main__":
    main()
