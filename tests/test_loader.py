from pathlib import Path

import pytest

from ppu.loader import load_registry

ROOT = Path(__file__).parent.parent
EXAMPLE = next((p for p in (ROOT / "пример" / "Реестр ППУ пример.xlsx",
                            ROOT / "rrr" / "Реестр ППУ пример.xlsx") if p.exists()),
               ROOT / "пример" / "Реестр ППУ пример.xlsx")


@pytest.mark.skipif(not EXAMPLE.exists(), reason="нет файла примера")
def test_example_registry():
    records = load_registry(EXAMPLE)
    assert len(records) == 24
    assert all(r["sheet"] == "Лист2" for r in records)
    # ещё не зарегистрированные получают id по строке
    assert records[0]["id"] == "row2"
    assert records[0]["date_submitted"] == "2026-10-29"
    by_id = {r["id"]: r for r in records}
    assert by_id["7"]["effect"] == 1055000
    assert by_id["7"]["status"] == "Реализовано"
