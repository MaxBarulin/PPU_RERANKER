import sys
import time
import types
from datetime import datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from ppu import db
from ppu import embed as embed_mod
from ppu.web import app as web

from test_rebuild import FakeEmbedder

EXCEL_LIKE = ["Рег. №", "Наименование", "До улучшения", "После улучшения", "Предложения",
              "Статус", "ЭЭ", "Дата подачи", "Служебное"]
ROWS = [
    (101, "Ручки для напильников", "Ручки развалились, можно травмировать руки.",
     "Изготовлены новые ручки.", None, "Реализовано", Decimal("12000.00"), datetime(2024, 2, 12), "x"),
    (102, "Ящик для шаблонов", "Шаблоны теряются.", "Сделан ящик.", None, "Принято",
     Decimal("8500.50"), datetime(2024, 3, 1), "y"),
    (None, "Подставка под паяльник", "Прожигается стол.", None, "Сделать подставку.", None,
     None, None, "z"),
    (None, None, None, None, None, None, None, None, None),  # пустая строка - пропускается
]


def fake_pymssql(monkeypatch, columns=EXCEL_LIKE, rows=ROWS, fail_connect=None, seen=None):
    mod = types.ModuleType("pymssql")

    class Error(Exception):
        pass

    class Cursor:
        description = None
        _rows = ()

        def execute(self, sql):
            if seen is not None:
                seen.append(sql)
            if "TOP 0 *" in sql:
                self.description, self._rows = [(c,) for c in columns], []
            elif "COUNT(*)" in sql:
                self.description, self._rows = [("",)], [(len(rows),)]
            elif sql.startswith("SELECT [") and " FROM [" in sql:
                wanted = [c.strip()[1:-1].replace("]]", "]")
                          for c in sql[len("SELECT "):sql.index(" FROM ")].split("], [")
                          for c in [c if c.startswith("[") else "[" + c]
                          for c in [c if c.endswith("]") else c + "]"]]
                idx = [columns.index(c) for c in wanted]
                self.description = [(c,) for c in wanted]
                self._rows = [tuple(r[i] for i in idx) for r in rows]
            else:  # запрос из файла - отдаём как есть
                self.description, self._rows = [(c,) for c in columns], list(rows)

        def fetchall(self):
            return list(self._rows)

    class Conn:
        def cursor(self):
            return Cursor()

        def close(self):
            pass

    def connect(**kw):
        if seen is not None:
            seen.append(kw)
        if fail_connect:
            raise Error(fail_connect.encode())
        return Conn()

    mod.Error, mod.connect = Error, connect
    monkeypatch.setitem(sys.modules, "pymssql", mod)


@pytest.fixture
def db_env(monkeypatch):
    for k, v in {"DB_SERVER": "SRV-SPSQL3", "DB_NAME": "URPS", "DB_USER": "ppu",
                 "DB_PASSWORD": "секрет", "DB_TABLE": "PPU_Export"}.items():
        monkeypatch.setenv(k, v)
    for k in ("DB_PORT", "DB_QUERY_FILE"):
        monkeypatch.delenv(k, raising=False)


def test_query_building(db_env, monkeypatch, tmp_path):
    assert db.query(db.settings()) == "SELECT TOP 0 * FROM [PPU_Export]"
    assert db.query(db.settings(), ["Рег. №", "Стран]ное"]) == \
        "SELECT [Рег. №], [Стран]]ное] FROM [PPU_Export]"
    monkeypatch.setenv("DB_TABLE", "dbo.PPU_Export")
    assert db.query(db.settings()) == "SELECT TOP 0 * FROM [dbo].[PPU_Export]"
    monkeypatch.setenv("DB_TABLE", "PPU_Export; DROP TABLE x")
    with pytest.raises(db.DBError):
        db.query(db.settings())
    sql = tmp_path / "registry.sql"
    sql.write_text("SELECT [A] AS reg_no FROM t", encoding="utf-8")
    monkeypatch.setenv("DB_QUERY_FILE", str(sql))
    assert db.query(db.settings()).startswith("SELECT [A] AS reg_no")
    assert "секрет" not in db.describe()


def test_check_and_load(db_env, monkeypatch):
    seen = []
    fake_pymssql(monkeypatch, seen=seen)
    res = db.check()
    assert res["rows"] == 4 and res["records"] == 3 and not res["missing"]
    assert res["mapped"]["name"] == "Наименование" and res["not_used"] == ["Служебное"]
    assert res["without_reg_no"] == 1 and res["duplicate_ids"] == 0
    assert seen[0]["server"] == "SRV-SPSQL3" and seen[0]["database"] == "URPS" and "port" not in seen[0]
    # сначала только названия колонок, потом - только нужные колонки, без «Служебное»
    sqls = [x for x in seen if isinstance(x, str)]
    assert sqls[0] == "SELECT TOP 0 * FROM [PPU_Export]" and "Служебное" not in sqls[1]

    recs = db.load_registry_db()
    assert [r["id"] for r in recs] == ["101", "102", "db3"]
    assert recs[0]["effect"] == 12000 and recs[1]["effect"] == 8500.5  # Decimal → число
    assert recs[0]["date_submitted"] == "2024-02-12"


def test_canonical_column_names(db_env, monkeypatch):
    fake_pymssql(monkeypatch, columns=["reg_no", "name", "before", "after", "proposal"],
                 rows=[(7, "Тележка", "Тяжело", "Сделана тележка", None)])
    assert db.load_registry_db()[0]["id"] == "7"


def test_missing_columns_and_errors(db_env, monkeypatch):
    fake_pymssql(monkeypatch, columns=["ID", "Caption", "Text"], rows=[(1, "a", "b")])
    res = db.check()
    assert "наименование" in res["missing"] and "records" not in res and res["rows"] == 1
    with pytest.raises(db.DBError, match="Колонки в таблице: ID, Caption, Text"):
        db.load_registry_db()
    fake_pymssql(monkeypatch, fail_connect="Adaptive Server connection failed")
    with pytest.raises(db.DBError, match="Не удалось подключиться к SRV-SPSQL3 / URPS"):
        db.check()
    monkeypatch.delenv("DB_SERVER")
    with pytest.raises(db.DBError, match="не настроена"):
        db.check()


def test_web_db_check_and_rebuild(db_env, monkeypatch, tmp_path):
    fake_pymssql(monkeypatch)
    monkeypatch.setenv("PPU_INDEX", str(tmp_path / "index"))
    monkeypatch.setenv("PPU_REGISTRY", str(tmp_path / "registry.xlsx"))
    monkeypatch.setenv("PPU_EMB_CACHE", str(tmp_path / "cache.sqlite"))
    monkeypatch.delenv("PPU_ADMIN_TOKEN", raising=False)
    monkeypatch.setattr(embed_mod, "Embedder", FakeEmbedder)
    monkeypatch.setattr(web, "Embedder", FakeEmbedder)
    monkeypatch.setattr(web, "JOB", web.Job())
    monkeypatch.setattr(web, "judge", lambda: None)
    web.engine.cache_clear()
    c = TestClient(web.app)

    st = c.get("/api/index/status").json()
    assert st["db"] == {"configured": True, "target": "SRV-SPSQL3 / URPS / PPU_Export"}
    assert c.post("/api/db/check").json()["records"] == 3
    assert c.post("/api/index/rebuild-db").status_code == 200
    for _ in range(200):
        if c.get("/api/index/status").json()["status"] != "running":
            break
        time.sleep(0.05)
    info = c.get("/api/info").json()
    assert info["records"] == 3 and info["source"].startswith("база данных SRV-SPSQL3")
    web.engine.cache_clear()

    monkeypatch.delenv("DB_SERVER")
    assert c.get("/api/index/status").json()["db"]["configured"] is False
    assert c.post("/api/index/rebuild-db").status_code == 422


def test_urps_column_names_without_proposal(db_env, monkeypatch):
    # как на скриншоте SSMS: URPS.dbo.PPU_Export2, колонки по-английски, «Предложений» нет
    cols = ["ID", "UID", "Title", "RegNum", "Status", "TabNum", "RegDate", "DeterminationDate",
            "RealizationDate", "EEApprovalDate", "FilingDate", "BeforeImprovement",
            "AfterImprovement", "Result0", "EE"]
    rows = [(9, "F0AC...", "Звукоизоляция круговой виброустановки", 19, "Реализовано", 19024,
             datetime(2018, 10, 18), datetime(2018, 12, 7), datetime(2019, 10, 1), None,
             datetime(2018, 10, 18), "Шумно у установки", "Сделана звукоизоляция", "Тише",
             Decimal("15000.0000"))]
    seen = []
    fake_pymssql(monkeypatch, columns=cols, rows=rows, seen=seen)
    res = db.check()
    assert not res["missing"] and res["records"] == 1
    assert res["mapped"]["name"] == "Title" and res["mapped"]["effect"] == "EE"
    assert "TabNum" in res["not_used"] and "UID" in res["not_used"]
    # табельный номер (персональные данные) и прочие лишние колонки не читаются
    assert not any("TabNum" in x for x in seen if isinstance(x, str) and "TOP 0" not in x)
    r = db.load_registry_db()[0]
    assert r["id"] == "19" and r["name"].startswith("Звукоизоляция") and r["effect"] == 15000
    assert r["date_submitted"] == "2018-10-18" and r["date_implemented"] == "2019-10-01"
    assert r["result"] == "Тише" and "proposal" not in r
