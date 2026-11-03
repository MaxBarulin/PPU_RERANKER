"""Калибровка порогов на реальном реестре: выборка пар → разметка людьми → пороги.

    python -m ppu.calibrate sample            # 1. выбрать пары для разметки
    (разметка в вебе: http://127.0.0.1:8000/label)
    python -m ppu.calibrate fit               # 2. подобрать пороги по разметке
    python -m ppu.calibrate fit --write       #    ... и записать data/thresholds.json

Вместо людей пары может разметить LLM-судья (кнопка на /admin, llm_label_pairs):
те же определения, метки помечаются by=llm, человек может их поправить на /label.

То же — из браузера: страница /admin, раздел «Калибровка порогов».

Пары — запись реестра и её ближайший сосед по векторам. Все векторы уже
лежат в индексе, поэтому выборка не обращается к моделям. Чтобы разметка
покрыла всю зону, где принимается решение, пары берутся поровну из полос
близости (dense) — иначе почти все были бы «далеко».

Всё локально: тексты реестра никуда не отправляются.
"""
import argparse
import json
import random
import threading
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Callable

import numpy as np

from .assess import (DEFAULT_CALIBRATION, Calibration, Thresholds, active_calibration,
                     relation, thresholds_path)
from .index import VIEWS, Index, load_index
from .search import dense_scores, place_relation

CALIB_DIR = Path("data/calib")
BINS = (0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 1.01)
NEIGHBOURS = 5
# Разметка: код -> подпись. Повтор и другое подразделение — «та же идея»
LABELS = {
    "repeat": "повтор",
    "other_place": "то же, другое подразделение",
    "alternative": "та же проблема, другое решение",
    "similar": "похоже",
    "different": "не связаны",
}
SAME_IDEA = ("repeat", "other_place")
# Код ответа LLM-судьи -> метка разметки
LLM_LABELS = {"dup": "repeat", "place": "other_place", "alt": "alternative",
              "sim": "similar", "diff": "different", "unclear": "unclear"}
_labels_lock = threading.Lock()


def _pair_features(index: Index, i: int, j: int) -> dict:
    q_vecs = {v: index.vectors[v][i] for v in VIEWS if index.masks[v][i]}
    # считаем по одной строке j — так же, как это сделал бы поиск
    dense, cos, _ = dense_scores(_one(index, j), q_vecs)
    a, b = index.records[i], index.records[j]
    return {
        "dense": round(float(dense[0]), 4),
        "cos": {v: round(float(c[0]), 4) for v, c in cos.items() if not np.isnan(c[0])},
        "completeness": b["completeness"],
        "completeness_a": a["completeness"],
        "place": place_relation(a["entities"], b["entities"]),
    }


def _one(index: Index, j: int) -> Index:
    return Index([index.records[j]], {v: index.vectors[v][j:j + 1] for v in VIEWS},
                 {v: index.masks[v][j:j + 1] for v in VIEWS}, index.bm25, index.meta)


def sample_pairs(index: Index, n_pairs: int, n_queries: int, seed: int,
                 bins: tuple[float, ...] = BINS, exclude: frozenset[str] = frozenset(),
                 progress: Callable[[int, int], None] | None = None) -> tuple[list[dict], dict]:
    """exclude — pair_id уже выбранных пар (в любом порядке A~B / B~A), их не берём."""
    rng = random.Random(seed)
    n = len(index)
    queries = rng.sample(range(n), min(n_queries, n))
    pool, seen, near_identical = defaultdict(list), set(), 0
    for step, i in enumerate(queries):
        if progress and step % 50 == 0:
            progress(step, len(queries))
        q_vecs = {v: index.vectors[v][i] for v in VIEWS if index.masks[v][i]}
        dense, _, has = dense_scores(index, q_vecs)
        dense[i] = -1
        for j in np.argsort(-np.where(has, dense, -1))[:NEIGHBOURS]:
            j = int(j)
            key = (min(i, j), max(i, j))
            ida, idb = index.records[i]["id"], index.records[j]["id"]
            if key in seen or f"{ida}~{idb}" in exclude or f"{idb}~{ida}" in exclude:
                continue
            seen.add(key)
            d = float(dense[j])
            near_identical += d >= 0.97
            band = next((k for k in range(len(bins) - 1) if bins[k] <= d < bins[k + 1]), None)
            if band is not None:
                pool[band].append((i, j))

    per_band = max(1, n_pairs // (len(bins) - 1))
    pairs = []
    for band in sorted(pool):
        for i, j in rng.sample(pool[band], min(per_band, len(pool[band]))):
            a, b = index.records[i], index.records[j]
            pairs.append({"pair_id": f"{a['id']}~{b['id']}", "a": a["id"], "b": b["id"],
                          "band": f"{bins[band]:.2f}–{min(bins[band + 1], 1):.2f}",
                          **_pair_features(index, i, j)})
    rng.shuffle(pairs)
    stats = {"queries": len(queries), "candidate_pairs": len(seen),
             "near_identical_share": near_identical / max(len(seen), 1),
             "pool_by_band": {f"{bins[k]:.2f}": len(v) for k, v in sorted(pool.items())}}
    return pairs, stats


def sample_to_dir(index: Index, calib_dir: Path = CALIB_DIR, n_pairs: int = 240,
                  n_queries: int = 1500, seed: int | None = None, append: bool = False,
                  progress: Callable[[int, int], None] | None = None) -> dict:
    """Выбрать пары и записать pairs.jsonl.

    append — добавить к уже выбранным (разметка сохраняется), иначе — заменить.
    Метки хранятся отдельно по pair_id, поэтому и при замене не теряются:
    совпавшие пары останутся размеченными.
    """
    existing = load_pairs(calib_dir) if append else []
    if seed is None:
        seed = random.randrange(10 ** 9) if existing else 7
    pairs, stats = sample_pairs(index, n_pairs, n_queries, seed, progress=progress,
                                exclude=frozenset(p["pair_id"] for p in existing))
    calib_dir.mkdir(parents=True, exist_ok=True)
    out = calib_dir / "pairs.jsonl"
    tmp = out.with_name(out.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for p in existing + pairs:
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")
    tmp.replace(out)
    text = "\n".join([
        f"Запросов: {stats['queries']}, пар-соседей: {stats['candidate_pairs']}, "
        f"почти одинаковых (dense ≥ 0.97): {stats['near_identical_share']:.1%}",
        f"Пар-соседей по полосам близости: {stats['pool_by_band']}",
        f"Выбрано для разметки: {len(pairs)}" + (f" (всего {len(existing) + len(pairs)})"
                                                 if existing else "")])
    return {"count": len(pairs), "total": len(existing) + len(pairs), "report": text}


# --- разметка (её пишет веб-страница /label) ---

def load_pairs(calib_dir: Path = CALIB_DIR) -> list[dict]:
    path = calib_dir / "pairs.jsonl"
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def load_label_meta(calib_dir: Path = CALIB_DIR) -> dict[str, dict]:
    """pair_id -> последняя запись разметки {label, by, why, at}; снятые метки убираются."""
    path = calib_dir / "labels.jsonl"
    rows = {}
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                if row.get("label"):
                    rows[row["pair_id"]] = row
                else:
                    rows.pop(row["pair_id"], None)
    return rows


def load_labels(calib_dir: Path = CALIB_DIR) -> dict[str, str]:
    """pair_id -> метка; последняя запись по паре побеждает (можно переразметить)."""
    return {pid: row["label"] for pid, row in load_label_meta(calib_dir).items()}


def save_label(pair_id: str, label: str | None, calib_dir: Path = CALIB_DIR,
               by: str = "human", why: str | None = None):
    calib_dir.mkdir(parents=True, exist_ok=True)
    row = {"pair_id": pair_id, "label": label, "by": by,
           "at": datetime.now().isoformat(timespec="seconds")}
    if why:
        row["why"] = why
    with _labels_lock, (calib_dir / "labels.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def llm_label_pairs(records_by_id: dict[str, dict], judge, calib_dir: Path = CALIB_DIR,
                    progress: Callable[[int, int], None] | None = None, token=None,
                    max_failures: int = 3) -> dict:
    """Разметить LLM-судьёй выбранные, но ещё не размеченные пары.

    Пары с одной и той же записью A идут одним запросом (как кандидаты к новому
    ППУ при проверке) — так быстрее. Метки пишутся сразу, поэтому остановка или
    обрыв ничего не теряют; повторный запуск продолжит с неразмеченных.
    """
    from .judge import MAX_CANDIDATES
    from .llm import LLMCancelled, LLMError

    pairs = [p for p in load_pairs(calib_dir) if p["a"] in records_by_id and p["b"] in records_by_id]
    labeled = load_labels(calib_dir)
    todo = [p for p in pairs if p["pair_id"] not in labeled]
    groups = defaultdict(list)
    for p in todo:
        groups[p["a"]].append(p)
    batches = [ps[k:k + MAX_CANDIDATES] for ps in groups.values()
               for k in range(0, len(ps), MAX_CANDIDATES)]

    done, failed, fails_in_row, counts, stopped = 0, 0, 0, Counter(), False
    if progress:
        progress(0, len(todo))
    for batch in batches:
        if token is not None and token.cancelled:
            stopped = True
            break
        a = records_by_id[batch[0]["a"]]
        cands = [{"id": p["b"], "completeness": records_by_id[p["b"]]["completeness"],
                  "record": records_by_id[p["b"]]} for p in batch]
        try:
            verdicts = judge(a, cands, token=token)
            fails_in_row = 0
        except LLMCancelled:
            stopped = True
            break
        except LLMError as e:
            fails_in_row += 1
            if fails_in_row >= max_failures:
                raise LLMError(f"LLM не отвечает ({e}). Размечено до ошибки: "
                               f"{sum(counts.values())} пар — они сохранены") from e
            verdicts = {}
        for p in batch:
            v = verdicts.get(p["b"])
            if v:
                label = LLM_LABELS[v["code"]]
                # как при проверке ППУ: цех/участок из текста надёжнее — LLM могла не заметить номер
                if label == "repeat" and p.get("place") == "other":
                    label = "other_place"
                save_label(p["pair_id"], label, calib_dir, by="llm", why=v["why"])
                counts[label] += 1
            else:
                failed += 1
        done += len(batch)
        if progress:
            progress(done, len(todo))

    names = {**LABELS, "unclear": "непонятно"}
    lines = [("Остановлено. " if stopped else "")
             + f"LLM разметила пар: {sum(counts.values())} из {len(todo)}"]
    if counts:
        lines.append(", ".join(f"{names[k]}: {n}" for k, n in counts.most_common()))
    if failed:
        lines.append(f"Без ответа: {failed} — их можно разметить вручную или запустить LLM ещё раз")
    return {"count": sum(counts.values()), "total": len(todo), "report": "\n".join(lines)}


# --- подбор порогов ---

def _f1(tp, fp, fn) -> float:
    return 2 * tp / (2 * tp + fp + fn) if tp else 0.0


def fit(rows: list[dict], base: Calibration = DEFAULT_CALIBRATION,
        precision_sure: float = 0.9, recall_flag: float = 0.95) -> tuple[Calibration, list[str]]:
    """Пороги для записей с описанием по размеченным парам.

    same      — максимум F1 для «та же идея» против остального;
    similar   — ниже него остаётся не больше (1 - recall_flag) «той же идеи»:
                повторы не должны уходить в «уникально»;
    gray_hi   — от него «та же идея» верна с точностью ≥ precision_sure (выше LLM не нужен);
    alt       — перебор правила «проблема похожа, решение нет» по F1 для alternative.
    """
    notes = []
    rows = [r for r in rows if r["completeness"] != "name_only"]
    dense = np.array([r["dense"] for r in rows])
    same = np.array([r["label"] in SAME_IDEA for r in rows])
    grid = np.round(np.arange(0.55, 0.951, 0.005), 3)
    wt = base.with_text

    if same.sum() >= 5 and (~same).sum() >= 5:
        f1 = np.array([_f1((same & (dense >= t)).sum(), (~same & (dense >= t)).sum(),
                           (same & (dense < t)).sum()) for t in grid])
        # середина «плато» лучшего F1, а не его край — устойчивее на новых данных
        t_same = float(np.median(grid[f1 >= f1.max() - 1e-9]))
        t_similar = float(np.floor(np.quantile(dense[same], 1 - recall_flag) * 200) / 200)
        prec = [(same & (dense >= t)).sum() / max((dense >= t).sum(), 1) for t in grid]
        sure = [t for t, p in zip(grid, prec) if p >= precision_sure and (dense >= t).sum() >= 3]
        t_gray_hi = float(sure[0]) if sure else float(grid[-1])
        t_similar = min(t_similar, t_same)
        t_gray_hi = max(t_gray_hi, t_same)
        wt = Thresholds(same=t_same, similar=t_similar, gray_lo=t_similar, gray_hi=t_gray_hi)
        notes.append(f"same={t_same:.3f} (F1 {max(f1):.2f}), similar={t_similar:.3f}, "
                     f"gray_hi={t_gray_hi:.3f}")
    else:
        notes.append("Мало размеченных «та же идея» / остального — пороги same/similar не меняю")

    alt_rows = [r for r in rows if "problem" in r["cos"] and "solution" in r["cos"]]
    is_alt = np.array([r["label"] == "alternative" for r in alt_rows])
    alt = (base.alt_problem_min, base.alt_solution_max, base.alt_dense_min)
    if is_alt.sum() >= 5:
        p = np.array([r["cos"]["problem"] for r in alt_rows])
        s = np.array([r["cos"]["solution"] for r in alt_rows])
        d = np.array([r["dense"] for r in alt_rows])
        best = (-1, alt)
        for pmin in np.arange(0.65, 0.91, 0.01):
            for smax in np.arange(0.60, 0.86, 0.01):
                for dmin in (0.55, 0.60, 0.65, 0.70):
                    hit = (p >= pmin) & (s < smax) & (d >= dmin)
                    score = _f1((hit & is_alt).sum(), (hit & ~is_alt).sum(), (~hit & is_alt).sum())
                    if score > best[0]:
                        best = (score, (round(pmin, 2), round(smax, 2), dmin))
        alt = best[1]
        notes.append(f"alt: problem≥{alt[0]}, solution<{alt[1]}, dense≥{alt[2]} (F1 {best[0]:.2f})")
    else:
        notes.append(f"Мало размеченных альтернатив ({is_alt.sum()}) — правило не меняю")

    cal = Calibration(wt, base.name_only, *alt,
                      source=f"разметка реальных пар, {len(rows)} шт., "
                             f"{datetime.now():%Y-%m-%d}")
    return cal, notes


def _confusion(rows, cal: Calibration) -> list[str]:
    pred_names = ("repeat", "other_place", "alternative", "similar", "far")
    lines = [f"  {'разметка':12} " + " ".join(f"{p[:9]:>10}" for p in pred_names) + "      n"]
    for lab in LABELS:
        rs = [r for r in rows if r["label"] == lab]
        if not rs:
            continue
        cnt = Counter(relation(r, cal) for r in rs)
        lines.append(f"  {lab:12} " + " ".join(f"{cnt[p] / len(rs):10.2f}" for p in pred_names)
                     + f"  {len(rs):5}")
    same = [r for r in rows if r["label"] in SAME_IDEA]
    rest = [r for r in rows if r["label"] not in SAME_IDEA]
    if same and rest:
        caught = np.mean([relation(r, cal) in SAME_IDEA for r in same])
        missed = np.mean([relation(r, cal) == "far" for r in same])
        false = np.mean([relation(r, cal) in SAME_IDEA for r in rest])
        lines.append(f"  «та же идея» опознана: {caught:.2f}, ушла в «далеко»: {missed:.2f}; "
                     f"остальное ошибочно названо повтором: {false:.2f}")
    return lines


def report(rows: list[dict], current: Calibration, fitted: Calibration, notes: list[str]) -> str:
    lines = [f"Размечено пар: {len(rows)}  " + ", ".join(f"{LABELS[k]}: {v}" for k, v in
                                                   Counter(r["label"] for r in rows).most_common())]
    lines.append("\nБлизость (dense) по разметке:")
    for lab in LABELS:
        v = [r["dense"] for r in rows if r["label"] == lab]
        if v:
            q = np.percentile(v, [10, 50, 90])
            lines.append(f"  {LABELS[lab]:32} p10 {q[0]:.3f}  p50 {q[1]:.3f}  p90 {q[2]:.3f}  (n={len(v)})")
    lines.append(f"\nСейчас ({current.source}):")
    lines += _confusion(rows, current)
    lines.append("\nПодобрано:")
    lines += [f"  {n}" for n in notes]
    lines += _confusion(rows, fitted)
    lines.append("\n(на тех же парах, по которым подбирали — оценка оптимистичная;"
                 " чем больше разметки, тем честнее)")
    return "\n".join(lines)


def labeled_rows(calib_dir: Path = CALIB_DIR) -> list[dict]:
    """Выбранные пары с метками; «непонятно» (unclear) в подбор не идёт."""
    labels = load_labels(calib_dir)
    return [{**p, "label": labels[p["pair_id"]]} for p in load_pairs(calib_dir)
            if labels.get(p["pair_id"]) in LABELS]


def fit_from_dir(calib_dir: Path = CALIB_DIR) -> tuple[Calibration, str]:
    """Подобрать пороги по разметке; отчёт пишется в fit_report.txt."""
    rows = labeled_rows(calib_dir)
    if not rows:
        raise ValueError("Нет размеченных пар — сначала выберите пары и разметьте их")
    current = active_calibration()
    fitted, notes = fit(rows, base=current)
    text = report(rows, current, fitted, notes)
    (calib_dir / "fit_report.txt").write_text(text, encoding="utf-8")
    return fitted, text


def save_calibration(cal: Calibration, path: Path | None = None):
    path = path or thresholds_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    _save_calibration(cal, path)


def _save_calibration(cal: Calibration, path: Path):
    data = {"source": cal.source,
            "with_text": cal.with_text.__dict__, "name_only": cal.name_only.__dict__,
            "alt": {"problem_min": cal.alt_problem_min, "solution_max": cal.alt_solution_max,
                    "dense_min": cal.alt_dense_min}}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--index", type=Path, default=Path("data/index"))
    parser.add_argument("--dir", type=Path, default=CALIB_DIR)
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample", help="выбрать пары для разметки")
    s.add_argument("--pairs", type=int, default=240)
    s.add_argument("--queries", type=int, default=1500, help="сколько записей взять как запросы")
    s.add_argument("--seed", type=int, default=7)
    s.add_argument("--force", action="store_true", help="перезаписать уже выбранные пары")
    f = sub.add_parser("fit", help="подобрать пороги по разметке")
    f.add_argument("--write", type=Path, nargs="?", const=Path("data/thresholds.json"),
                   help="записать пороги (по умолчанию data/thresholds.json)")
    args = parser.parse_args()

    if args.cmd == "sample":
        out = args.dir / "pairs.jsonl"
        if out.exists() and not args.force:
            parser.error(f"{out} уже есть (и, может быть, размечен). --force, чтобы выбрать заново")
        res = sample_to_dir(load_index(args.index), args.dir, args.pairs, args.queries, args.seed)
        print(res["report"], "->", out)
        print("Размечать: веб-интерфейс, страница /label")
        return

    try:
        fitted, text = fit_from_dir(args.dir)
    except ValueError as e:
        parser.error(str(e))
    print(text)
    if args.write:
        _save_calibration(fitted, args.write)
        print(f"\nПороги записаны: {args.write}. Веб подхватит их со следующей проверки.")


if __name__ == "__main__":
    main()
