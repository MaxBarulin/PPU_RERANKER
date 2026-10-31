"""Веб-интерфейс проверки ППУ (FastAPI).

    python -m ppu.web                       # http://127.0.0.1:8000
    python -m ppu.web --host 0.0.0.0 --index data/index

API: POST /api/assess {"name", "before", "after", "proposal"}
"""
