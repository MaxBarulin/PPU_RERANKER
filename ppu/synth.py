"""Синтетический набор ППУ с известными ответами — для калибровки порогов.

    python -m ppu.synth --out data/synth --model qwen/qwen3-235b-a22b-2507

Только выдуманные ППУ, реальный реестр сюда не попадает — поэтому
можно генерировать во внешней модели.

1. По каждой теме генерируем несколько разных «базовых» ППУ.
2. Для каждой базы — четыре варианта с известным отношением к ней:
     duplicate   — то же самое другими словами (другой автор);
     other_place — та же идея в другом цехе / на другом участке;
     alternative — та же проблема, другое решение;
     related     — та же область, но другая проблема.
3. Реестр = базы (часть превращаем в «только название», как в старых
   записях). Запросы = варианты + отложенные базы (label novel —
   похожего в реестре быть не должно).

Ответы модели кэшируются в out/raw, повторный запуск продолжит с места.
"""
import argparse
import json
import random
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import config
from .llm import LLM, LLMError
from .normalize import normalize_record

TOPICS = [
    "охрана труда и травмобезопасность",
    "эргономика рабочего места",
    "хранение инструмента, оснастки и шаблонов",
    "шум, вибрация, освещение и микроклимат в цехе",
    "сварочные работы",
    "покраска и антикоррозионная защита",
    "механообработка и станки с ЧПУ",
    "монтаж трубопроводов и оборудования на строящемся заказе (судне)",
    "контроль качества и измерения",
    "складская логистика, перемещение грузов, краны и тележки",
    "экономия материалов и переработка отходов",
    "энергосбережение: электричество, сжатый воздух, отопление",
    "конструкторская и технологическая документация",
    "цифровизация: учёт, базы данных, программы",
    "организация и планирование производства",
    "обучение персонала и бытовые условия",
]
LABELS = ("duplicate", "other_place", "alternative", "related")

SYSTEM = ("Ты помогаешь готовить тестовые данные для системы поиска дублей "
          "предложений по улучшению (ППУ) на крупном судостроительном заводе. "
          "Отвечай только JSON без пояснений.")

PPU_FIELDS = """Поля ППУ:
- name: наименование (коротко, как пишут в реестре);
- before: «До улучшения» — в чём проблема;
- after: «После улучшения» — что стало после внедрения;
- proposal: «Предложения» — что сделать / что сделали."""

BASES_PROMPT = """Придумай {n} разных ППУ на тему «{topic}».
{fields}
Требования:
- ППУ не должны быть похожи друг на друга: разные проблемы и решения;
- пиши как реальные рабочие, мастера и инженеры: кто-то кратко и просто,
  кто-то подробно; иногда сокращения («пр-ва», «уч.», «т.к.»), иногда опечатки;
- у части ППУ укажи место: цех или участок с номером (например «цех 14016»,
  «участок №7») — в названии или в тексте «До улучшения»; у части места нет.
Формат: {{"items": [{{"name": "...", "before": "...", "after": "...", "proposal": "..."}}]}}"""

VARIANTS_PROMPT = """Вот ППУ из реестра:
{base}

Напиши четыре новых ППУ, связанных с ним по-разному:
- duplicate: то же самое предложение (та же проблема и то же решение), но подал
  другой человек — полностью другими словами, другой длины и стиля, без
  копирования фраз; место то же или не указано;
- other_place: та же проблема и то же решение, но в другом подразделении —
  явно укажи другой цех или участок (с другим номером);
- alternative: та же проблема, но принципиально другое решение;
- related: та же область или то же оборудование, но другая проблема и другое решение.
{fields}
Формат: {{"duplicate": {{...}}, "other_place": {{...}}, "alternative": {{...}}, "related": {{...}}}}"""


def _cached_call(path: Path, fn):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    result = fn()
    path.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return result


def _ppu(item: dict) -> dict:
    return {k: str(item.get(k) or "").strip() for k in ("name", "before", "after", "proposal")}


def generate(llm: LLM, raw_dir: Path, per_topic: int, workers: int):
    raw_dir.mkdir(parents=True, exist_ok=True)

    def bases_for(i_topic):
        i, topic = i_topic
        prompt = BASES_PROMPT.format(n=per_topic, topic=topic, fields=PPU_FIELDS)
        data = _cached_call(raw_dir / f"bases_{i:02d}.json",
                            lambda: llm.json(SYSTEM, prompt, temperature=0.9, max_tokens=4000))
        return [(topic, _ppu(it)) for it in data["items"]]

    with ThreadPoolExecutor(workers) as pool:
        bases = [b for chunk in pool.map(bases_for, enumerate(TOPICS)) for b in chunk]
    print(f"Базовых ППУ: {len(bases)}")

    def variants_for(i_base):
        i, (_, base) = i_base
        prompt = VARIANTS_PROMPT.format(base=json.dumps(base, ensure_ascii=False, indent=1),
                                        fields=PPU_FIELDS)
        try:
            data = _cached_call(raw_dir / f"variants_{i:03d}.json",
                                lambda: llm.json(SYSTEM, prompt, temperature=0.8, max_tokens=4000))
            if isinstance(data, list) and len(data) == len(LABELS):
                # четыре ППУ без меток — в том порядке, в каком просили
                data = dict(zip(LABELS, data))
            return {label: _ppu(data[label]) for label in LABELS}
        except (LLMError, ValueError, KeyError, TypeError) as e:
            print(f"  база {i}: варианты не получены ({e.__class__.__name__}: {str(e)[:100]})")
            return None

    with ThreadPoolExecutor(workers) as pool:
        variants = list(pool.map(variants_for, enumerate(bases)))
    return bases, variants


def assemble(bases, variants, holdout_per_topic: int, name_only_share: float, seed: int):
    """Реестр и запросы с эталоном."""
    rng = random.Random(seed)
    by_topic = {}
    for i, (topic, _) in enumerate(bases):
        by_topic.setdefault(topic, []).append(i)
    # из каждой темы откладываем базы — это «новые» ППУ с похожими соседями по теме
    holdout = {i for idx in by_topic.values() for i in rng.sample(idx, holdout_per_topic)}

    registry, queries = [], []
    for i, (topic, base) in enumerate(bases):
        if i in holdout:
            queries.append({"qid": f"Q{i:03d}-novel", "label": "novel", "target": None,
                            "topic": topic, **base})
            continue
        rec = {"id": f"S{i:03d}", "topic": topic, **base, "result": None}
        if rng.random() < name_only_share:
            rec.update(before="См.вложение", after="См.вложение", proposal="См.вложение")
        registry.append(normalize_record(rec))
        for label, var in (variants[i] or {}).items():
            queries.append({"qid": f"Q{i:03d}-{label}", "label": label, "target": rec["id"],
                            "topic": topic, **var})
    return registry, queries


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("data/synth"))
    parser.add_argument("--model", help="модель для генерации (по умолчанию LLM_MODEL)")
    parser.add_argument("--per-topic", type=int, default=5)
    parser.add_argument("--holdout", type=int, default=1, help="отложенных баз на тему")
    parser.add_argument("--name-only", type=float, default=0.4,
                        help="доля записей реестра «только название»")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    llm = LLM(config.llm(), model=args.model)
    bases, variants = generate(llm, args.out / "raw", args.per_topic, args.workers)
    registry, queries = assemble(bases, variants, args.holdout, args.name_only, args.seed)

    for name, rows in (("registry.jsonl", registry), ("queries.jsonl", queries)):
        with (args.out / name).open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    name_only = sum(r["completeness"] == "name_only" for r in registry)
    print(f"Реестр: {len(registry)} (только название: {name_only}), запросов: {len(queries)} -> {args.out}")


if __name__ == "__main__":
    main()
