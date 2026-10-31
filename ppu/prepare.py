"""Этап 1: загрузка и нормализация реестра + отчёт о качестве данных.

    python -m ppu.prepare "пример/Реестр ППУ пример.xlsx" --out data/registry_clean.jsonl

Работает без сети, реальный реестр можно гонять где угодно.
"""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from .loader import load_registry
from .normalize import ACRONYMS, abbreviation_candidates, normalize_record

TOP = 30


def report(records: list[dict]) -> str:
    lines = [f"Записей: {len(records)}", ""]

    lines.append("Полнота описания:")
    for level, n in Counter(r["completeness"] for r in records).most_common():
        lines.append(f"  {level:10} {n:6}  ({n / len(records):.0%})")

    lines.append("\nСтатусы:")
    for status, n in Counter(r.get("status") or "—" for r in records).most_common():
        lines.append(f"  {status:20} {n:6}")

    with_effect = [r for r in records if isinstance(r.get("effect"), (int, float))]
    lines.append(f"\nС экономическим эффектом: {len(with_effect)}")

    lens = sorted(len(r["name_clean"].split()) for r in records)
    lines.append(f"Длина названия в словах: медиана {lens[len(lens) // 2]}, "
                 f"1–3 слова у {sum(n <= 3 for n in lens)} записей")

    groups = defaultdict(list)
    for r in records:
        if r["core_name"]:
            groups[r["core_name"].lower()].append(r)
    same = sorted((g for g in groups.values() if len(g) > 1), key=len, reverse=True)
    lines.append(f"\nОдинаковая «суть» названия (без места и дат): {len(same)} групп, "
                 f"{sum(map(len, same))} записей")
    for g in same[:TOP]:
        ids = ", ".join(r["id"] for r in g[:8]) + (" …" if len(g) > 8 else "")
        lines.append(f"  [{len(g)}] {g[0]['core_name']}  ← {ids}")

    # Ищем по уже раскрытому тексту: известные сокращения туда не попадут
    texts = [r[f"{f}_norm"] for r in records for f in ("name", "before", "after", "proposal")]
    lines.append("\nКандидаты в сокращения (ещё не раскрыты, пополнить normalize.py):")
    for kind, tokens in abbreviation_candidates(texts).items():
        counts = Counter(t for t in tokens if t not in ACRONYMS)
        top = ", ".join(f"{t}×{n}" for t, n in counts.most_common(TOP))
        lines.append(f"  {kind}: {top or '—'}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("registry", type=Path, help="Excel-файл реестра")
    parser.add_argument("--out", type=Path, default=Path("data/registry_clean.jsonl"))
    args = parser.parse_args()

    records = [normalize_record(r) for r in load_registry(args.registry)]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")

    print(report(records))
    print(f"\nСохранено: {args.out}")


if __name__ == "__main__":
    main()
