"""Этап 2: индекс реестра — BM25 по леммам + векторы bge-m3 по представлениям.

    python -m ppu.index data/registry_clean.jsonl --out data/index

Представления записи:
    name     — название;
    full     — название + проблема + решение (у записей «только название» = name);
    problem  — «До улучшения»;
    solution — «После улучшения» + «Предложения».
Одна проблема с другим решением — альтернатива, а не дубль, поэтому
проблему и решение сравниваем отдельно.
"""
import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

import numpy as np

from .lexical import BM25, lemmas

VIEWS = ("name", "full", "problem", "solution")
EmbedFn = Callable[[list[str]], np.ndarray]


def view_texts(rec: dict) -> dict[str, str]:
    name = rec["name_norm"]
    problem = rec["before_norm"]
    solution = " ".join(t for t in (rec["after_norm"], rec["proposal_norm"]) if t)
    full = "\n".join([name]
                     + ([f"Проблема: {problem}"] if problem else [])
                     + ([f"Решение: {solution}"] if solution else []))
    return {"name": name, "full": full, "problem": problem, "solution": solution}


@dataclass
class Index:
    records: list[dict]
    vectors: dict[str, np.ndarray]  # представление -> (n, dim), нули там, где текста нет
    masks: dict[str, np.ndarray]    # представление -> есть ли текст у записи
    bm25: BM25
    meta: dict

    def __len__(self):
        return len(self.records)


def build_index(records: list[dict], embed: EmbedFn, model: str = "") -> Index:
    records = [dict(r) for r in records]
    texts = [view_texts(r) for r in records]
    for r, t in zip(records, texts):
        r["lemmas"] = lemmas(t["full"])

    vectors, masks = {}, {}
    for view in VIEWS:
        mask = np.array([bool(t[view]) for t in texts])
        present = [t[view] for t, m in zip(texts, mask) if m]
        if present:
            vecs = embed(present)
            full = np.zeros((len(records), vecs.shape[1]), dtype=np.float32)
            full[mask] = vecs
        else:  # ни у одной записи нет такого текста
            full = np.zeros((len(records), 0), dtype=np.float32)
        vectors[view], masks[view] = full, mask

    meta = {"model": model, "count": len(records), "built": datetime.now().isoformat(timespec="seconds")}
    return Index(records, vectors, masks, BM25([r["lemmas"] for r in records]), meta)


def save_index(index: Index, out_dir: str | Path):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "records.jsonl").open("w", encoding="utf-8") as f:
        for r in index.records:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")
    np.savez(out / "vectors.npz",
             **{v: index.vectors[v] for v in VIEWS},
             **{f"{v}_mask": index.masks[v] for v in VIEWS})
    (out / "meta.json").write_text(json.dumps(index.meta, ensure_ascii=False, indent=2), encoding="utf-8")


def load_index(index_dir: str | Path) -> Index:
    src = Path(index_dir)
    with (src / "records.jsonl").open(encoding="utf-8") as f:
        records = [json.loads(line) for line in f]
    data = np.load(src / "vectors.npz")
    meta = json.loads((src / "meta.json").read_text(encoding="utf-8"))
    return Index(records,
                 {v: data[v] for v in VIEWS},
                 {v: data[f"{v}_mask"] for v in VIEWS},
                 BM25([r["lemmas"] for r in records]),
                 meta)


def main():
    from . import config
    from .embed import Embedder

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("registry", type=Path, help="JSONL после ppu.prepare")
    parser.add_argument("--out", type=Path, default=Path("data/index"))
    parser.add_argument("--cache", type=Path, default=Path("data/emb_cache.sqlite"))
    parser.add_argument("--batch", type=int, default=32)
    args = parser.parse_args()

    with args.registry.open(encoding="utf-8") as f:
        records = [json.loads(line) for line in f]
    endpoint = config.embeddings()
    embedder = Embedder(endpoint, cache_path=args.cache, batch_size=args.batch)
    index = build_index(records, lambda texts: embedder(texts, progress=True), endpoint.model)
    save_index(index, args.out)
    dims = {v: index.vectors[v].shape[1] for v in VIEWS}
    filled = {v: int(index.masks[v].sum()) for v in VIEWS}
    print(f"Индекс: {len(index)} записей, размерность {dims['full']}, "
          f"заполнено по представлениям {filled} -> {args.out}")


if __name__ == "__main__":
    main()
