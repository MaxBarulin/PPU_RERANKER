"""Оценка поиска и вердикта на наборе с известными ответами (ppu.synth).

    python -m ppu.evaluate --data data/synth
    python -m ppu.evaluate --data data/synth --rerank-url http://127.0.0.1:8082/v1

Что меряем:
- recall@k — находит ли поиск исходное ППУ среди первых k кандидатов
  (по типу связи и по полноте записи в реестре);
- близость (dense) лучшего кандидата по типам связи — по ней ставятся пороги;
- матрица вердиктов: какой ответ дала система на каждый тип связи;
- (с --llm) матрица после LLM-судьи для спорных случаев и сколько это
  стоит по времени на рабочем CPU;
- (с --rerank-url) то же для реранкера — для перепроверки на реальных данных.

    python -m ppu.evaluate --data data/synth --llm --llm-model qwen/qwen3.6-35b-a3b \
        --llm-extra '{"reasoning": {"effort": "low"}}' --llm-max-tokens 4000
"""
import argparse
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from . import config
from .assess import VERDICT_ORDER, assess
from .config import Endpoint
from .embed import Embedder
from .index import build_index, load_index, save_index, view_texts
from .judge import SYSTEM as JUDGE_SYSTEM, Judge
from .llm import LLM
from .rerank import Reranker
from .search import make_query, search

KS = (1, 3, 5, 10, 20)
CHARS_PER_TOKEN = 3.0  # грубо для русского текста в токенизаторе Qwen
SAME_IDEA = ("duplicate", "other_place")
LABELS = ("duplicate", "other_place", "alternative", "related", "novel")
VERDICTS = VERDICT_ORDER + ("unique",)
# Какой вердикт считаем правильным для каждого типа связи
SAME_IDEA_VERDICTS = ("repeat", "other_place")
EXPECTED = {"duplicate": "repeat", "other_place": "other_place", "alternative": "alternative",
            "related": "similar", "novel": "unique"}


def _load_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def run(index, queries, embedder, reranker=None, judge=None, top_k: int = 20) -> list[dict]:
    by_id = {r["id"]: r for r in index.records}
    rows = []
    for n, q in enumerate(queries, 1):
        query = make_query(q["name"], q["before"], q["after"], q["proposal"])
        cands = search(index, query, embedder, top_k=top_k)
        ids = [c["id"] for c in cands]
        top = max(cands, key=lambda c: c["dense"]) if cands else None
        res = assess(index, query, embedder, top_k=top_k)
        row = {
            "qid": q["qid"], "label": q["label"], "target": q["target"],
            "target_completeness": by_id[q["target"]]["completeness"] if q["target"] else None,
            "retrieval_rank": ids.index(q["target"]) + 1 if q["target"] in ids else None,
            "top_dense": top["dense"] if top else None,
            "top_is_target": bool(top and top["id"] == q["target"]),
            "verdict": res["verdict"],
            "needs_llm": res["needs_llm"],
            "target_relation": next((c["relation"] for c in res["candidates"]
                                     if c["id"] == q["target"]), None),
            "verdict_llm": res["verdict"],
        }
        if judge and res["needs_llm"]:
            started = time.time()
            res_llm = assess(index, query, embedder, top_k=top_k, judge=judge)
            row.update(verdict_llm=res_llm["verdict"], llm_seconds=time.time() - started,
                       llm_usage=judge.llm.last_usage)
        if reranker and cands:
            probs = reranker(view_texts(query)["full"],
                             [view_texts(by_id[i])["full"] for i in ids])
            best = int(np.argmax(probs))
            row.update(max_prob=float(max(probs)), rerank_top_is_target=ids[best] == q["target"],
                       target_prob=float(probs[ids.index(q["target"])]) if q["target"] in ids else None)
        rows.append(row)
        print(f"\r  запросы: {n}/{len(queries)}", end="", flush=True)
    print()
    return rows


def _quantiles(values) -> str:
    v = [x for x in values if x is not None]
    if not v:
        return "—"
    p10, p50, p90 = np.percentile(v, [10, 50, 90])
    return f"p10 {p10:.3f}  p50 {p50:.3f}  p90 {p90:.3f}  (n={len(v)})"


def _by_completeness(rows, label):
    groups = [("все", rows)]
    if label != "novel":
        groups += [(c, [r for r in rows if r["target_completeness"] == c]) for c in ("full", "name_only")]
    return [(c, rs) for c, rs in groups if rs]


def _verdict_matrix(by_label: dict, key: str, title: str) -> list[str]:
    lines = [f"\n{title} (доля запросов; * — ожидаемый ответ):",
             f"  {'связь':12} {'полнота':10} " + " ".join(f"{v[:9]:>10}" for v in VERDICTS)
             + f" {'нужен LLM':>10}"]
    for label in LABELS:
        for compl, rs in _by_completeness(by_label[label], label):
            cnt = Counter(r[key] for r in rs)
            cells = [f"{cnt[v] / len(rs):9.2f}{'*' if EXPECTED[label] == v else ' '}" for v in VERDICTS]
            llm = np.mean([r["needs_llm"] for r in rs])
            lines.append(f"  {label:12} {compl:10} " + " ".join(cells) + f" {llm:10.2f}")
    same = [r for l in SAME_IDEA for r in by_label[l]]
    as_same = lambda rs: np.mean([r[key] in SAME_IDEA_VERDICTS for r in rs]) if rs else float("nan")
    by_compl = {c: [r for r in same if r["target_completeness"] == c] for c in ("full", "name_only")}
    exact = np.mean([r[key] == EXPECTED[r["label"]] for rs in by_label.values() for r in rs])
    lines += [
        "",
        "  «Та же идея» (дубль или другое подразделение):",
        f"    опознана как повтор/тиражирование: {as_same(same):.2f}  "
        f"(с описанием: {as_same(by_compl['full']):.2f}, только название: {as_same(by_compl['name_only']):.2f})",
        f"    не пропущена (вердикт не «уникально»): {np.mean([r[key] != 'unique' for r in same]):.2f}",
        f"  Новые ППУ: названы уникальными {np.mean([r[key] == 'unique' for r in by_label['novel']]):.2f}, "
        f"ошибочно повтором {as_same(by_label['novel']):.2f}",
        f"  Точный вердикт по всем типам: {exact:.2f}",
        "  (повтор и тиражирование не различаются, если в найденном ППУ место не указано)",
    ]
    return lines


def _llm_cost(rows: list[dict], prefill_tps: float, decode_tps: float) -> list[str]:
    used = [r for r in rows if "llm_usage" in r]
    prompt = np.array([r["llm_usage"]["prompt_tokens"] or 0 for r in used], dtype=float)
    answer = np.array([r["llm_usage"]["answer_chars"] for r in used], dtype=float) / CHARS_PER_TOKEN
    cached = len(JUDGE_SYSTEM) / CHARS_PER_TOKEN  # постоянная часть, llama-server её кэширует
    t_work = np.maximum(prompt - cached, 0) / prefill_tps + answer / decode_tps
    return [
        f"\nLLM-судья: вызван в {len(used)} из {len(rows)} запросов ({len(used) / len(rows):.0%})",
        f"  промпт, токенов: {_quantiles(prompt)}  (из них постоянная часть ≈ {cached:.0f})",
        f"  ответ, токенов (оценка): {_quantiles(answer)}",
        f"  время сейчас, с: {_quantiles([r['llm_seconds'] for r in used])}",
        f"  оценка на рабочем CPU (префилл {prefill_tps:g} т/с, вывод {decode_tps:g} т/с), с: {_quantiles(t_work)}",
    ]


def report(rows: list[dict], prefill_tps: float = 40, decode_tps: float = 10) -> str:
    by_label = defaultdict(list)
    for r in rows:
        by_label[r["label"]].append(r)
    lines = ["Recall@k поиска (BM25 + векторы), исходное ППУ среди первых k:",
             f"  {'связь':12} {'полнота':10} " + " ".join(f"@{k:<4}" for k in KS) + "  n"]
    for label in LABELS[:-1]:
        for compl, rs in _by_completeness(by_label[label], label):
            rec = [np.mean([r["retrieval_rank"] is not None and r["retrieval_rank"] <= k for r in rs])
                   for k in KS]
            lines.append(f"  {label:12} {compl:10} " + " ".join(f"{x:5.2f}" for x in rec) + f"  {len(rs)}")

    lines.append("\nБлизость (dense) лучшего кандидата:")
    for label in LABELS:
        for compl, rs in _by_completeness(by_label[label], label):
            lines.append(f"  {label:12} {compl:10} {_quantiles(r['top_dense'] for r in rs)}")

    lines += _verdict_matrix(by_label, "verdict", "Вердикт по векторам")
    if any("llm_usage" in r for r in rows):
        lines += _verdict_matrix(by_label, "verdict_llm", "Вердикт после LLM-судьи (только спорные)")
        lines += _llm_cost(rows, prefill_tps, decode_tps)

    if any("max_prob" in r for r in rows):
        lines.append("\nРеранкер: вероятность для исходного ППУ (novel — максимум по кандидатам):")
        for label in LABELS[:-1]:
            lines.append(f"  {label:12} {_quantiles(r.get('target_prob') for r in by_label[label])}")
        lines.append(f"  {'novel':12} {_quantiles(r.get('max_prob') for r in by_label['novel'])}")
        lines.append("  Лучший кандидат = исходное ППУ: реранкер / векторы")
        for label in LABELS[:-1]:
            rs = by_label[label]
            lines.append(f"  {label:12} {np.mean([r.get('rerank_top_is_target') for r in rs]):.2f} / "
                         f"{np.mean([r['top_is_target'] for r in rs]):.2f}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, default=Path("data/synth"))
    parser.add_argument("--cache", type=Path, default=Path("data/emb_cache.sqlite"))
    parser.add_argument("--top", type=int, default=20, help="кандидатов из поиска")
    parser.add_argument("--rerank-url", help="проверить и реранкер (адрес llama-server)")
    parser.add_argument("--rebuild", action="store_true", help="пересобрать индекс")
    parser.add_argument("--llm", action="store_true", help="уточнять спорные случаи LLM-судьёй")
    parser.add_argument("--llm-model", help="модель (по умолчанию LLM_MODEL)")
    parser.add_argument("--llm-extra", help="доп. параметры запроса, JSON")
    parser.add_argument("--llm-max-tokens", type=int, default=400)
    parser.add_argument("--prefill-tps", type=float, default=40, help="скорость префилла на работе")
    parser.add_argument("--decode-tps", type=float, default=10, help="скорость вывода на работе")
    args = parser.parse_args()

    embedder = Embedder(config.embeddings(), cache_path=args.cache)
    index_dir = args.data / "index"
    if args.rebuild or not (index_dir / "meta.json").exists():
        index = build_index(_load_jsonl(args.data / "registry.jsonl"), embedder,
                            config.embeddings().model)
        save_index(index, index_dir)
    index = load_index(index_dir)

    reranker = None
    if args.rerank_url:
        ep = config.reranker()
        reranker = Reranker(Endpoint(args.rerank_url.rstrip("/"), ep.api_key, ep.model))

    judge = None
    if args.llm:
        llm = LLM(config.llm(), model=args.llm_model,
                  extra_body=json.loads(args.llm_extra) if args.llm_extra else None)
        judge = Judge(llm, max_tokens=args.llm_max_tokens)

    rows = run(index, _load_jsonl(args.data / "queries.jsonl"), embedder, reranker, judge, args.top)
    with (args.data / "eval.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    text = report(rows, args.prefill_tps, args.decode_tps)
    (args.data / "eval_report.txt").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
