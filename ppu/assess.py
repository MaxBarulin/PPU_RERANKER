"""Этап 3: вердикт по новому ППУ — было ли такое и насколько оно уникально.

    python -m ppu.assess --name "..." --before "..." --after "..." --proposal "..."
    python -m ppu.assess --json new_ppu.json
    python -m ppu.assess --id row2

Кандидаты из гибридного поиска раскладываем по векторной близости (dense)
на «повтор / другое подразделение / альтернатива / похоже / далеко».

Почему не реранкер: на синтетике (ppu.evaluate) bge-reranker-v2-m3 мерил
«про ту же тему», а не «та же идея» — новые ППУ получали у него такие же
оценки, как дубли. Косинус bge-m3 разделяет заметно лучше.

Пороги подобраны на синтетике и разные для записей с описанием и
«только название»: у вторых сравнивать почти нечего, и близость ниже.
Спорные случаи помечаются needs_llm; с --llm их уточняет LLM-судья (ppu.judge).

    python -m ppu.assess --llm --name "..."         # LLM только для спорных
    python -m ppu.assess --llm-always --name "..."  # LLM всегда
"""
import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path

from .index import EmbedFn, Index, load_index
from .judge import MAX_CANDIDATES
from .search import make_query, search


@dataclass(frozen=True)
class Thresholds:
    same: float      # ≥ — та же идея (повтор или тиражирование)
    similar: float   # ≥ — похожее, стоит посмотреть
    gray_lo: float   # [gray_lo, gray_hi) — уверенности нет, нужен LLM
    gray_hi: float


# Синтетика, запись с описанием: при 0.72 ловим 93% «та же идея», новых — 0%
WITH_TEXT = Thresholds(same=0.72, similar=0.65, gray_lo=0.65, gray_hi=0.76)
# «Только название»: дубли и новые перекрываются, уверенно — только очень близкие
NAME_ONLY = Thresholds(same=0.76, similar=0.62, gray_lo=0.62, gray_hi=0.76)
# Та же проблема, но решение другое: у дублей косинус решений почти всегда ≥ 0.77.
# На синтетике ловит ~половину альтернатив при ~10% ложных на новых ППУ;
# пропущенные уходят в «похоже», а не в «уникально»
ALT_PROBLEM_MIN = 0.75
ALT_SOLUTION_MAX = 0.75
ALT_DENSE_MIN = 0.65
# Шкала «уникальности»: близость ниже FLOOR — совсем другое ППУ
FLOOR = 0.55


@dataclass(frozen=True)
class Calibration:
    with_text: Thresholds
    name_only: Thresholds
    alt_problem_min: float
    alt_solution_max: float
    alt_dense_min: float
    source: str


DEFAULT_CALIBRATION = Calibration(WITH_TEXT, NAME_ONLY, ALT_PROBLEM_MIN, ALT_SOLUTION_MAX,
                                  ALT_DENSE_MIN, source="синтетика (по умолчанию)")


def load_calibration(path: str | Path) -> Calibration:
    """Пороги из файла (пишет ppu.calibrate); чего нет в файле — по умолчанию."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    d, alt = DEFAULT_CALIBRATION, data.get("alt", {})
    return Calibration(
        with_text=Thresholds(**{**d.with_text.__dict__, **data.get("with_text", {})}),
        name_only=Thresholds(**{**d.name_only.__dict__, **data.get("name_only", {})}),
        alt_problem_min=alt.get("problem_min", d.alt_problem_min),
        alt_solution_max=alt.get("solution_max", d.alt_solution_max),
        alt_dense_min=alt.get("dense_min", d.alt_dense_min),
        source=data.get("source", str(path)),
    )


def active_calibration() -> Calibration:
    path = Path(os.getenv("PPU_THRESHOLDS", "data/thresholds.json"))
    return load_calibration(path) if path.exists() else DEFAULT_CALIBRATION

RELATION_TEXT = {
    "repeat": "повтор",
    "other_place": "другое подразделение",
    "alternative": "та же проблема, другое решение",
    "similar": "похоже",
    "far": "далеко",
}
VERDICT_TEXT = {
    "repeat": "Такое ППУ уже было",
    "other_place": "Такая идея уже была в другом подразделении (тиражирование)",
    "alternative": "Эта проблема уже поднималась, но с другим решением",
    "similar": "Есть похожие ППУ — стоит сравнить",
    "unique": "Похожих ППУ не найдено",
}
VERDICT_ORDER = ("repeat", "other_place", "alternative", "similar")
# Уникальность после LLM: по самой близкой связи среди проверенных кандидатов
LLM_UNIQUENESS = {"repeat": 0.05, "other_place": 0.1, "alternative": 0.4, "similar": 0.65, "far": 1.0}


def _thresholds(cand: dict, cal: Calibration) -> Thresholds:
    return cal.name_only if cand["completeness"] == "name_only" else cal.with_text


def relation(cand: dict, cal: Calibration = DEFAULT_CALIBRATION) -> str:
    """Связь кандидата по векторам: нужны dense, cos, completeness, place."""
    t, score, cos = _thresholds(cand, cal), cand["dense"], cand["cos"]
    # раньше порога similar: при другом решении общая близость бывает ниже него
    if "problem" in cos and "solution" in cos and score >= cal.alt_dense_min \
            and cos["problem"] >= cal.alt_problem_min and cos["solution"] < cal.alt_solution_max:
        return "alternative"
    if score < t.similar:
        return "far"
    if score >= t.same:
        return "other_place" if cand["place"] == "other" else "repeat"
    return "similar"


def _closeness(cand: dict, cal: Calibration) -> float:
    """0 — совсем другое, 1 — точно та же идея (порог same ≈ 0.7)."""
    t = _thresholds(cand, cal)
    top = t.same + 0.08
    return min(max((cand["dense"] - FLOOR) / (top - FLOOR), 0.0), 1.0)


def _verdict(cands: list[dict]) -> str:
    relations = {c["relation"] for c in cands}
    return next((v for v in VERDICT_ORDER if v in relations), "unique")


def _apply_judge(res: dict, query: dict, judge, by_id: dict) -> None:
    """Переоценивает верхних кандидатов LLM-судьёй и пересчитывает вердикт."""
    to_judge = res["candidates"][:MAX_CANDIDATES]
    verdicts = judge(query, [dict(c, record=by_id[c["id"]]) for c in to_judge])
    judged = []
    for c in to_judge:
        v = verdicts.get(c["id"])
        if not v:
            continue
        c["relation_vectors"] = c["relation"]
        # место по извлечённым сущностям надёжнее: LLM могла не заметить номер цеха
        c["relation"] = "other_place" if v["relation"] == "repeat" and c["place"] == "other" \
            else v["relation"]
        c["llm"] = {"code": v["code"], "why": v["why"]}
        c["uncertain"] = v["code"] == "unclear"
        judged.append(c)
    if not judged:
        return
    res["candidates"].sort(key=lambda c: (VERDICT_ORDER + ("far",)).index(c["relation"]))
    res["verdict"] = _verdict(res["candidates"])
    res["verdict_text"] = VERDICT_TEXT[res["verdict"]]
    res["uniqueness"] = min(LLM_UNIQUENESS[c["relation"]] for c in judged)
    res["needs_llm"] = False
    res["judged_by"] = "llm"


def assess(index: Index, query: dict, embed: EmbedFn, top_k: int = 20,
           exclude_ids: tuple[str, ...] = (), judge=None, force_judge: bool = False,
           cal: Calibration | None = None) -> dict:
    """Вердикт по векторам; спорный (или force_judge) — уточняется judge, если он передан.

    cal — пороги; по умолчанию data/thresholds.json (если есть) или синтетика.
    """
    cal = cal or active_calibration()
    cands = search(index, query, embed, top_k=top_k, exclude_ids=exclude_ids)
    by_id = {r["id"]: r for r in index.records}

    for c in cands:
        c["score"] = round(_closeness(c, cal), 3)
        c["relation"] = relation(c, cal)
        t = _thresholds(c, cal)
        c["uncertain"] = t.gray_lo <= c["dense"] < t.gray_hi
        c["sure_same"] = c["relation"] in ("repeat", "other_place") and c["dense"] >= t.gray_hi
        rec = by_id[c["id"]]
        c["texts"] = {f: rec.get(f"{f}_clean", "") for f in ("before", "after", "proposal", "result")}
        c["date_submitted"] = rec.get("date_submitted")
    cands.sort(key=lambda c: (c["score"], c["dense"]), reverse=True)

    verdict = _verdict(cands)
    shown = [c for c in cands if c["relation"] != "far"] or cands[:3]
    res = {
        "verdict": verdict,
        "verdict_text": VERDICT_TEXT[verdict],
        "uniqueness": round(1 - (cands[0]["score"] if cands else 0.0), 3),
        # LLM нужен, если нет уверенного повтора, а спорные есть (в т.ч. неуверенный «повтор»)
        "needs_llm": not any(c["sure_same"] for c in shown) and any(c["uncertain"] for c in shown),
        "judged_by": "vectors",
        "calibration": cal.source,
        "candidates": shown,
    }
    if judge and (res["needs_llm"] or force_judge):
        _apply_judge(res, query, judge, by_id)
    return res


def format_assessment(query: dict, res: dict) -> str:
    lines = [f"Запрос: {query['name_clean']}  [{query['completeness']}]",
             f"Вердикт: {res['verdict_text']}",
             f"Уникальность: {res['uniqueness']:.2f}"
             + ("  — спорно, нужен LLM" if res["needs_llm"] else "")
             + ("  (уточнено LLM)" if res["judged_by"] == "llm" else ""),
             "",
             f"{'#':>2} {'id':>7} {'близ.':>5} {'dense':>6}  {'связь':30} {'статус':14} наименование"]
    for k, c in enumerate(res["candidates"], 1):
        lines.append(f"{k:>2} {c['id']:>7} {c['score']:5.2f} {c['dense']:6.3f}  "
                     f"{RELATION_TEXT[c['relation']]:30} {(c['status'] or '—')[:14]:14} "
                     f"{(c['name'] or '')[:70]}")
        if "llm" in c:
            lines.append(f"{'':>17}LLM: {c['llm']['code']} — {c['llm']['why']}"
                         f"  (по векторам: {RELATION_TEXT[c['relation_vectors']]})")
    return "\n".join(lines)


def main():
    from . import config
    from .embed import Embedder
    from .judge import Judge
    from .llm import LLM

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--index", type=Path, default=Path("data/index"))
    parser.add_argument("--cache", type=Path, default=Path("data/emb_cache.sqlite"))
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--name")
    src.add_argument("--json", type=Path, help='{"name", "before", "after", "proposal"}')
    src.add_argument("--id", help="взять запись из индекса как запрос")
    parser.add_argument("--before", default="")
    parser.add_argument("--after", default="")
    parser.add_argument("--proposal", default="")
    parser.add_argument("--raw", action="store_true", help="вывести JSON")
    llm_mode = parser.add_mutually_exclusive_group()
    llm_mode.add_argument("--llm", action="store_true", help="уточнять спорные случаи у LLM")
    llm_mode.add_argument("--llm-always", action="store_true", help="всегда уточнять у LLM")
    parser.add_argument("--llm-model", help="модель (по умолчанию LLM_MODEL)")
    parser.add_argument("--llm-extra",
                        help="""доп. параметры запроса, JSON: '{"reasoning": {"effort": "low"}}'""")
    parser.add_argument("--llm-max-tokens", type=int, default=400)
    args = parser.parse_args()

    index = load_index(args.index)
    exclude = ()
    if args.id:
        query = next((r for r in index.records if r["id"] == args.id), None)
        if query is None:
            parser.error(f"нет записи {args.id} в индексе")
        exclude = (args.id,)
    elif args.json:
        data = json.loads(args.json.read_text(encoding="utf-8"))
        query = make_query(data["name"], data.get("before", ""),
                           data.get("after", ""), data.get("proposal", ""))
    else:
        query = make_query(args.name, args.before, args.after, args.proposal)

    judge = None
    if args.llm or args.llm_always:
        llm = LLM(config.llm(), model=args.llm_model,
                  extra_body=json.loads(args.llm_extra) if args.llm_extra else None)
        judge = Judge(llm, max_tokens=args.llm_max_tokens)

    embedder = Embedder(config.embeddings(), cache_path=args.cache)
    res = assess(index, query, embedder, exclude_ids=exclude, judge=judge,
                 force_judge=args.llm_always)
    if args.raw:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(format_assessment(query, res))


if __name__ == "__main__":
    main()
