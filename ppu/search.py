"""Гибридный поиск похожих ППУ: BM25 + векторы, слияние через RRF.

    python -m ppu.search --name "..." --before "..." --after "..." --proposal "..."
    python -m ppu.search --json new_ppu.json
    python -m ppu.search --id row2          # запись из реестра как запрос (себя исключаем)

Здесь только отбор кандидатов. Вердикт «дубль / другое место /
альтернатива» — следующий этап (реранкер и LLM).
"""
import argparse
import json
from pathlib import Path

import numpy as np

from .index import VIEWS, EmbedFn, Index, load_index, view_texts
from .lexical import lemmas
from .normalize import normalize_record

# Вклад представлений в векторную близость; у записи без текста
# в представлении его вес перераспределяется на остальные
WEIGHTS = {"full": 0.4, "name": 0.2, "problem": 0.2, "solution": 0.2}
RRF_K = 60
PLACE_KEYS = ("workshops", "sites", "places")


def make_query(name: str, before: str = "", after: str = "", proposal: str = "") -> dict:
    return normalize_record({"id": "new", "name": name, "before": before,
                             "after": after, "proposal": proposal, "result": None})


def _ranks(scores: np.ndarray, valid: np.ndarray) -> np.ndarray:
    """Место в списке (с 1) для valid-записей, inf — для остальных."""
    ranks = np.full(len(scores), np.inf)
    order = np.argsort(-np.where(valid, scores, -np.inf), kind="stable")
    n_valid = int(valid.sum())
    ranks[order[:n_valid]] = np.arange(1, n_valid + 1)
    return ranks


def dense_scores(index: Index, q_vecs: dict[str, np.ndarray]):
    """Векторная близость запроса ко всем записям.

    q_vecs — векторы запроса по представлениям (только те, где у запроса есть текст).
    Возвращает (dense, cos по представлениям, есть ли у записи общее представление).
    """
    n = len(index)
    # представление, которого нет ни у одной записи базы, пропускаем
    views = [v for v in q_vecs if index.vectors[v].shape[1]]
    cos = {v: np.where(index.masks[v], index.vectors[v] @ q_vecs[v], np.nan) for v in views}
    num, den = np.zeros(n), np.zeros(n)
    for v in views:
        m = index.masks[v]
        num[m] += WEIGHTS[v] * cos[v][m]
        den[m] += WEIGHTS[v]
    has_dense = den > 0
    dense = np.where(has_dense, num / np.where(has_dense, den, 1), 0.0)
    return dense, cos, has_dense


def place_relation(q_ent: dict, r_ent: dict) -> str:
    """same — совпадает цех/участок, other — указаны разные, unknown — где-то не указано."""
    q = {(k, v) for k in PLACE_KEYS for v in q_ent.get(k, [])}
    r = {(k, v) for k in PLACE_KEYS for v in r_ent.get(k, [])}
    if not q or not r:
        return "unknown"
    return "same" if q & r else "other"


def search(index: Index, query: dict, embed: EmbedFn, top_k: int = 20,
           exclude_ids: tuple[str, ...] = ()) -> list[dict]:
    q_texts = view_texts(query)
    q_views = [v for v in VIEWS if q_texts[v]]
    q_vecs = dict(zip(q_views, embed([q_texts[v] for v in q_views])))
    dense, cos, has_dense = dense_scores(index, q_vecs)
    bm25 = index.bm25.scores(lemmas(q_texts["full"]))

    allowed = np.array([r["id"] not in exclude_ids for r in index.records])
    dense_rank = _ranks(dense, has_dense & allowed)
    bm25_rank = _ranks(bm25, (bm25 > 0) & allowed)
    rrf = 1 / (RRF_K + dense_rank) + 1 / (RRF_K + bm25_rank)

    results = []
    for i in np.argsort(-rrf, kind="stable")[:top_k]:
        if not allowed[i] or rrf[i] == 0:
            continue
        r = index.records[i]
        results.append({
            "id": r["id"],
            "name": r.get("name"),
            "status": r.get("status"),
            "effect": r.get("effect"),
            "completeness": r["completeness"],
            "entities": r["entities"],
            "place": place_relation(query["entities"], r["entities"]),
            "rrf": float(rrf[i]),
            "dense": float(dense[i]),
            "bm25": float(bm25[i]),
            "cos": {v: round(float(c[i]), 4) for v, c in cos.items() if not np.isnan(c[i])},
            # None — кандидат не попал в этот список (нет общих слов и т.п.)
            "rank": {k: int(v) if np.isfinite(v) else None
                     for k, v in (("dense", dense_rank[i]), ("bm25", bm25_rank[i]))},
        })
    return results


def format_results(query: dict, results: list[dict]) -> str:
    lines = [f"Запрос: {query['name_clean']}  [{query['completeness']}]",
             f"{'#':>2} {'id':>7} {'dense':>6} {'bm25':>6}  {'место':7} {'статус':14} наименование"]
    for k, r in enumerate(results, 1):
        lines.append(f"{k:>2} {r['id']:>7} {r['dense']:6.3f} {r['bm25']:6.2f}  "
                     f"{r['place']:7} {(r['status'] or '—')[:14]:14} {(r['name'] or '')[:80]}")
    return "\n".join(lines)


def main():
    from . import config
    from .embed import Embedder

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--index", type=Path, default=Path("data/index"))
    parser.add_argument("--cache", type=Path, default=Path("data/emb_cache.sqlite"))
    parser.add_argument("--top", type=int, default=10)
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--name")
    src.add_argument("--json", type=Path, help='{"name", "before", "after", "proposal"}')
    src.add_argument("--id", help="взять запись из индекса как запрос")
    parser.add_argument("--before", default="")
    parser.add_argument("--after", default="")
    parser.add_argument("--proposal", default="")
    parser.add_argument("--raw", action="store_true", help="вывести JSON")
    args = parser.parse_args()

    index = load_index(args.index)
    exclude = ()
    if args.id:
        rec = next((r for r in index.records if r["id"] == args.id), None)
        if rec is None:
            parser.error(f"нет записи {args.id} в индексе")
        query, exclude = rec, (args.id,)
    elif args.json:
        data = json.loads(args.json.read_text(encoding="utf-8"))
        query = make_query(data["name"], data.get("before", ""),
                           data.get("after", ""), data.get("proposal", ""))
    else:
        query = make_query(args.name, args.before, args.after, args.proposal)

    embedder = Embedder(config.embeddings(), cache_path=args.cache)
    results = search(index, query, embedder, top_k=args.top, exclude_ids=exclude)
    if args.raw:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(format_results(query, results))


if __name__ == "__main__":
    main()
