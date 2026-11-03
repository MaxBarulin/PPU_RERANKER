"""Обновление базы: реестр -> нормализация -> эмбеддинги -> индекс, одним шагом.

    python -m ppu.rebuild "Реестр ППУ.xlsx"

То же делает кнопка на странице /admin веб-интерфейса. Источник записей —
просто список словарей (см. loader.load_registry), поэтому Excel потом можно
заменить чтением из базы данных, не трогая остальное.

Новый индекс собирается рядом (data/index.new) и подменяет старый только
целиком и только при успехе: пока идёт сборка, веб отвечает по старому.
"""
import argparse
import shutil
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Callable

from .index import VIEWS, build_index, save_index, view_texts
from .loader import load_registry
from .normalize import normalize_record
from .prepare import report

VIEW_TITLES = {"name": "названия", "full": "полные тексты",
               "problem": "проблемы («До»)", "solution": "решения («После»)"}
Progress = Callable[..., None]


def _swap(new: Path, target: Path):
    old = target.with_name(target.name + ".old")
    shutil.rmtree(old, ignore_errors=True)
    if target.exists():
        target.rename(old)
    new.rename(target)
    shutil.rmtree(old, ignore_errors=True)


def rebuild(raw_records: list[dict], index_dir: str | Path, embedder, model: str = "",
            source: str = "", progress: Progress | None = None) -> dict:
    """Собирает индекс из сырых записей и подменяет им index_dir. Возвращает meta."""
    progress = progress or (lambda **kw: None)
    progress(stage="Нормализация текстов")
    records = [normalize_record(r) for r in raw_records]
    if not records:
        raise ValueError("В реестре нет ни одной записи")
    rep = report(records)

    # какие представления реально будут считаться — для подписи «часть k из n»
    texts = [view_texts(r) for r in records]
    views = [v for v in VIEWS if any(t[v] for t in texts)]
    step = iter(range(1, len(views) + 1))

    def embed(batch: list[str]):
        k = next(step, len(views))
        title = f"Векторы: {VIEW_TITLES[views[k - 1]]} (часть {k} из {len(views)})"
        progress(stage=title, done=0, total=len(batch))
        return embedder(batch, progress=lambda done, total: progress(stage=title, done=done,
                                                                      total=total))

    index = build_index(records, embed, model)
    index.meta.update(source=source, report=rep)

    progress(stage="Сохранение индекса")
    target = Path(index_dir)
    new = target.with_name(target.name + ".new")
    shutil.rmtree(new, ignore_errors=True)
    save_index(index, new)
    (new / "prepare_report.txt").write_text(rep, encoding="utf-8")
    _swap(new, target)
    return index.meta


class Job:
    """Одна фоновая пересборка за раз; состояние читает страница /admin."""

    def __init__(self):
        self._lock = threading.Lock()
        self._state = {"status": "idle"}

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._state)

    @property
    def running(self) -> bool:
        return self.snapshot()["status"] == "running"

    def _update(self, **kw):
        with self._lock:
            self._state.update(kw)

    def start(self, work: Callable[[Progress], dict], on_success: Callable[[], None] = lambda: None,
              source: str = "") -> bool:
        """Запускает work(progress) в отдельном потоке. False — уже идёт другая сборка."""
        with self._lock:
            if self._state["status"] == "running":
                return False
            self._state = {"status": "running", "source": source, "stage": "Запуск",
                           "done": None, "total": None,
                           "started": datetime.now().isoformat(timespec="seconds")}

        def progress(stage: str, done: int | None = None, total: int | None = None):
            self._update(stage=stage, done=done, total=total)

        def run():
            try:
                meta = work(progress)
                on_success()
                self._update(status="done", stage="Готово", done=None, total=None,
                             records=meta.get("count"), report=meta.get("report"))
            except Exception as e:  # покажем причину на странице, подробности — в лог
                traceback.print_exc()
                # свои ошибки уже написаны для человека — без имени класса
                own = type(e).__name__ in ("DBError", "LLMError", "ValueError")
                self._update(status="error", error=str(e) if own else f"{type(e).__name__}: {e}")
            finally:
                self._update(finished=datetime.now().isoformat(timespec="seconds"))

        threading.Thread(target=run, name="ppu-rebuild", daemon=True).start()
        return True


def rebuild_from_excel(path: str | Path, index_dir: str | Path, cache_path: str | Path,
                       progress: Progress | None = None, source: str = "") -> dict:
    from . import config
    from .embed import Embedder

    progress = progress or (lambda **kw: None)
    progress(stage="Чтение Excel")
    raw = load_registry(path)
    endpoint = config.embeddings()
    embedder = Embedder(endpoint, cache_path=cache_path)
    return rebuild(raw, index_dir, embedder, endpoint.model,
                   source=source or Path(path).name, progress=progress)


def rebuild_from_db(index_dir: str | Path, cache_path: str | Path,
                    progress: Progress | None = None) -> dict:
    from . import config, db
    from .embed import Embedder

    progress = progress or (lambda **kw: None)
    progress(stage="Чтение базы данных")
    raw = db.load_registry_db()
    endpoint = config.embeddings()
    embedder = Embedder(endpoint, cache_path=cache_path)
    return rebuild(raw, index_dir, embedder, endpoint.model,
                   source=f"база данных {db.describe()}", progress=progress)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("registry", type=Path, help="Excel-файл реестра")
    parser.add_argument("--out", type=Path, default=Path("data/index"))
    parser.add_argument("--cache", type=Path, default=Path("data/emb_cache.sqlite"))
    args = parser.parse_args()

    def progress(stage, done=None, total=None):
        tail = f" {done}/{total}" if total else ""
        print(f"\r{stage}{tail}\033[K", end="", file=sys.stderr, flush=True)

    meta = rebuild_from_excel(args.registry, args.out, args.cache, progress)
    print(file=sys.stderr)
    print(meta["report"])
    print(f"\nИндекс: {meta['count']} записей -> {args.out}")


if __name__ == "__main__":
    main()
