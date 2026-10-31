"""Лексический поиск: лемматизация (pymorphy3) и BM25.

Ловит то, что векторы размывают: точные термины, марки оборудования,
номера («каплеструйный принтер», «SCV-400»).
"""
import math
import re
from collections import Counter, defaultdict
from functools import lru_cache

import numpy as np
import pymorphy3

TOKEN_RE = re.compile(r"[a-zа-я0-9]+(?:-[a-zа-я0-9]+)*")

# Стоп-слова по леммам. Частые, но содержательные слова («собственный»,
# «сила», «работа») не выкидываем — их приглушит IDF.
STOPWORDS = set("""
и в во не на с со по для от до из к ко о об а но что это как же бы у за при то так
все весь его её ее их был быть есть он она оно они мы вы я ты который этот тот
также или ли чтобы нет да после теперь где когда чем там тут уже ещё еще очень
свой наш ваш себя сам самый каждый другой такой мочь
""".split())


@lru_cache(maxsize=1)
def _morph():
    return pymorphy3.MorphAnalyzer()


@lru_cache(maxsize=300_000)
def lemma(word: str) -> str:
    return _morph().parse(word)[0].normal_form.replace("ё", "е")


def lemmas(text: str) -> list[str]:
    tokens = TOKEN_RE.findall(text.lower().replace("ё", "е"))
    out = []
    for t in tokens:
        lm = t if "-" in t or not t.isalpha() else lemma(t)
        if lm not in STOPWORDS and (len(lm) > 1 or lm.isdigit()):
            out.append(lm)
    return out


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.n_docs = len(docs)
        doc_len = np.array([len(d) for d in docs], dtype=np.float32)
        avgdl = float(doc_len.mean()) if self.n_docs and doc_len.mean() > 0 else 1.0
        # нормировка длины не зависит от запроса — считаем один раз
        self._len_norm = k1 * (1 - b + b * doc_len / avgdl)
        self.k1 = k1

        postings = defaultdict(list)
        for i, doc in enumerate(docs):
            for term, tf in Counter(doc).items():
                postings[term].append((i, tf))
        self._postings = {
            t: (np.array([i for i, _ in p]), np.array([tf for _, tf in p], dtype=np.float32))
            for t, p in postings.items()
        }
        self.idf = {
            t: math.log(1 + (self.n_docs - len(p) + 0.5) / (len(p) + 0.5))
            for t, p in postings.items()
        }

    def scores(self, query: list[str]) -> np.ndarray:
        s = np.zeros(self.n_docs, dtype=np.float32)
        for term in set(query):
            if term not in self._postings:
                continue
            ids, tf = self._postings[term]
            s[ids] += self.idf[term] * tf * (self.k1 + 1) / (tf + self._len_norm[ids])
        return s
