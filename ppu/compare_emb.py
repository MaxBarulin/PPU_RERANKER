"""Сравнение моделей векторов на размеченных парах - до пересчёта всей базы.

    python -m ppu.compare_emb --url http://127.0.0.1:8005/v1 --model qwen3-embedding-8b \
        --instruct "..." --out data/calib-qwen8b

Новой моделью считаются только записи из размеченных пар (сотни, а не весь реестр), и для
каждой модели печатается:
- насколько чисто близость отделяет «ту же идею» (повтор, другое подразделение) от остального:
  AUC (1.0 - идеально, 0.5 - наугад) и лучшая точность при одном пороге;
- на каком месте модель ставит второе ППУ пары «та же идея» среди всех записей из разметки;
- шкала близости: по меткам и для случайных пар (почти всегда несвязанных) - от неё зависят пороги.

--out - папка для калибровки новой модели: пары с близостями новой модели + та же разметка людей.
Потом: python -m ppu.calibrate --dir <out> fit --write data/thresholds-<модель>.json
"""
import argparse
import json
import shutil
from pathlib import Path

import numpy as np

from .calibrate import CALIB_DIR, LABELS, SAME_IDEA, _pair_features, labeled_rows
from .config import Endpoint, emb_instruct
from .index import VIEWS, Index, build_index, load_index
from .lexical import BM25
from .search import dense_scores


def auc(score: np.ndarray, pos: np.ndarray) -> float:
    """Вероятность, что у случайной «той же идеи» близость выше, чем у случайной прочей пары."""
    if pos.sum() == 0 or (~pos).sum() == 0:
        return float("nan")
    ranks = np.argsort(np.argsort(score, kind="stable"), kind="stable") + 1.0
    # одинаковые значения - средний ранг
    for v in np.unique(score):
        m = score == v
        if m.sum() > 1:
            ranks[m] = ranks[m].mean()
    n1, n0 = pos.sum(), (~pos).sum()
    return float((ranks[pos].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def best_split(score: np.ndarray, pos: np.ndarray) -> tuple[float, float, float]:
    """Порог с лучшим F1 для «той же идеи»: (порог, F1, доля верных ответов)."""
    best = (0.0, -1.0, 0.0)
    for t in np.unique(score):
        hit = score >= t
        tp, fp, fn = (hit & pos).sum(), (hit & ~pos).sum(), (~hit & pos).sum()
        f1 = 2 * tp / max(2 * tp + fp + fn, 1)
        if f1 > best[1]:
            best = (float(t), float(f1), float(((hit == pos).sum()) / len(pos)))
    return best


def subset(index: Index, rows: list[int]) -> Index:
    recs = [index.records[i] for i in rows]
    return Index(recs, {v: index.vectors[v][rows] for v in VIEWS}, {v: index.masks[v][rows] for v in VIEWS},
                 BM25([r["lemmas"] for r in recs]), dict(index.meta))


def partner_ranks(index: Index, pairs: list[tuple[int, int]]) -> np.ndarray:
    """Место b среди всех записей index по близости к a (1 - первое)."""
    out = []
    for a, b in pairs:
        q = {v: index.vectors[v][a] for v in VIEWS if index.masks[v][a]}
        dense, _, has = dense_scores(index, q)
        dense = np.where(has, dense, -1.0)
        dense[a] = -np.inf
        out.append(int((dense > dense[b]).sum()) + 1)
    return np.array(out)


def describe(name: str, rows: list[dict], dense: np.ndarray, ranks: np.ndarray, rand: np.ndarray) -> list[str]:
    pos = np.array([r["label"] in SAME_IDEA for r in rows])
    t, f1, acc = best_split(dense, pos)
    lines = [f"== {name}",
             f"  «та же идея» против остального: AUC {auc(dense, pos):.3f}; лучший порог {t:.3f} - "
             f"F1 {f1:.2f}, верных ответов {acc:.0%}"]
    if len(ranks):
        lines.append(f"  второе ППУ пары «та же идея»: на 1-м месте {np.mean(ranks == 1):.0%}, "
                     f"в первых 5 - {np.mean(ranks <= 5):.0%}, в первых 20 - {np.mean(ranks <= 20):.0%} "
                     f"(пар {len(ranks)})")
    lines.append("  близость по меткам (10% / медиана / 90%):")
    for lab, title in LABELS.items():
        d = np.array([x for x, r in zip(dense, rows) if r["label"] == lab])
        if len(d):
            q = np.quantile(d, [0.1, 0.5, 0.9])
            lines.append(f"    {title:32} {q[0]:.3f} / {q[1]:.3f} / {q[2]:.3f}   (пар {len(d)})")
    if len(rand):
        q = np.quantile(rand, [0.1, 0.5, 0.9, 0.99])
        lines.append(f"    {'случайные пары (почти все чужие)':32} {q[0]:.3f} / {q[1]:.3f} / {q[2]:.3f}   "
                     f"(99%: {q[3]:.3f})")
    return lines


def compare(index: Index, rows: list[dict], embed, model: str, instruct: str = "", seed: int = 7):
    """Отчёт (строки) и пары с признаками новой модели (для калибровки)."""
    pos_of = {}
    for i, r in enumerate(index.records):
        pos_of.setdefault(r["id"], i)
    rows = [r for r in rows if r["a"] in pos_of and r["b"] in pos_of]
    ids = sorted({x for r in rows for x in (r["a"], r["b"])}, key=lambda k: pos_of[k])
    sel = [pos_of[k] for k in ids]
    local = {k: n for n, k in enumerate(ids)}

    old = subset(index, sel)
    new = build_index([dict(r) for r in old.records], embed, model)
    new.meta["instruct"] = instruct

    pairs = [(local[r["a"]], local[r["b"]]) for r in rows]
    new_rows = [{**r, **_pair_features(new, a, b)} for r, (a, b) in zip(rows, pairs)]
    old_dense = np.array([_pair_features(old, a, b)["dense"] for a, b in pairs])
    new_dense = np.array([r["dense"] for r in new_rows])

    same = [p for p, r in zip(pairs, rows) if r["label"] in SAME_IDEA]
    rng = np.random.default_rng(seed)
    n = len(ids)
    rand_pairs = [(int(a), int(b)) for a, b in rng.integers(0, n, size=(min(3000, n * n), 2)) if a != b]
    rand_old = np.array([_pair_features(old, a, b)["dense"] for a, b in rand_pairs[:1500]])
    rand_new = np.array([_pair_features(new, a, b)["dense"] for a, b in rand_pairs[:1500]])

    lines = [f"Размеченных пар: {len(rows)} (записей {n}); место второго ППУ - среди этих {n} записей", ""]
    lines += describe(f"сейчас: {index.meta.get('model') or 'текущая модель'}", rows, old_dense,
                      partner_ranks(old, same), rand_old)
    lines.append("")
    lines += describe(f"новая: {model}" + (" (с инструкцией)" if instruct else ""), rows, new_dense,
                      partner_ranks(new, same), rand_new)
    return lines, [{k: v for k, v in r.items() if k != "label"} for r in new_rows]


def main():
    from . import config  # noqa: F401 - загружает .env
    from .embed import Embedder

    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--index", type=Path, default=Path("data/index"), help="текущая база (её модель - эталон)")
    p.add_argument("--dir", type=Path, default=CALIB_DIR, help="разметка пар (страница /label)")
    p.add_argument("--url", required=True, help="адрес новой модели, например http://127.0.0.1:8005/v1")
    p.add_argument("--model", required=True, help="имя новой модели (как в EMB_MODEL)")
    p.add_argument("--instruct", default=None, help="инструкция (по умолчанию EMB_INSTRUCT из .env)")
    p.add_argument("--cache", type=Path, default=Path("data/emb_cache.sqlite"))
    p.add_argument("--out", type=Path, help="папка для калибровки новой модели")
    args = p.parse_args()

    instruct = emb_instruct() if args.instruct is None else args.instruct
    rows = labeled_rows(args.dir)
    if not rows:
        p.error(f"в {args.dir} нет размеченных пар")
    embedder = Embedder(Endpoint(args.url, "none", args.model), cache_path=args.cache, instruct=instruct)
    lines, new_pairs = compare(load_index(args.index), rows, lambda t: embedder(t, progress=True),
                               args.model, instruct)
    print("\n".join(lines))
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        with (args.out / "pairs.jsonl").open("w", encoding="utf-8") as f:
            for r in new_pairs:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        shutil.copy(args.dir / "labels.jsonl", args.out / "labels.jsonl")
        (args.out / "compare_report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        (args.out / "model.json").write_text(json.dumps({"model": args.model, "instruct": instruct},
                                                         ensure_ascii=False), encoding="utf-8")
        print(f"\nДля калибровки: {args.out} (пары с близостями новой модели и та же разметка)")


if __name__ == "__main__":
    main()
