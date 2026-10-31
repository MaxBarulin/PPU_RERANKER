import pytest


@pytest.fixture(autouse=True)
def default_thresholds(monkeypatch, tmp_path):
    # тесты не должны зависеть от data/thresholds.json, записанного калибровкой
    monkeypatch.setenv("PPU_THRESHOLDS", str(tmp_path / "нет.json"))
