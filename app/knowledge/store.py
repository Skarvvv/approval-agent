import json
import math
from pathlib import Path
from typing import List

CORPUS_FILE = Path(__file__).parent / "corpus" / "corpus.json"


def _tokenize(text: str) -> List[str]:
    """按字切分：中文零依赖近似，真分词请用 jieba。"""
    return [c for c in text if not c.isspace()]


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _by_score(hit: dict) -> float:
    """给 list.sort 用：取出每条命中的分数作为排序依据。"""
    return hit["score"]


class KnowledgeStore:
    """极简向量检索：TF-IDF 词频向量 + 余弦相似度（§7/§8 机制）。

    纯标准库、数据随仓库自带；V2 可整体替换为真向量库，调用方不变。
    """

    def __init__(self) -> None:
        raw = CORPUS_FILE.read_text(encoding="utf-8")
        self.docs = json.loads(raw)
        self.vocab = self._build_vocab()
        self.idf = self._build_idf()

    def _build_vocab(self) -> List[str]:
        terms = set()
        for doc in self.docs:
            for t in _tokenize(doc["title"] + doc["content"]):
                terms.add(t)
        return sorted(terms)

    def _build_idf(self) -> dict:
        """真 IDF：出现越少的字权重越高（§8 教学版写成常数，这里补正）。"""
        n = len(self.docs)
        idf = {}
        for t in self.vocab:
            df = 0
            for doc in self.docs:
                if t in doc["title"] + doc["content"]:
                    df += 1
            idf[t] = math.log((n + 1) / (df + 1)) + 1
        return idf

    def _vec(self, text: str) -> List[float]:
        toks = _tokenize(text)
        tf = {}
        for t in toks:
            tf[t] = tf.get(t, 0) + 1
        n = len(toks) or 1
        return [tf.get(t, 0) / n * self.idf[t] for t in self.vocab]

    def search(self, query: str, top_k: int = 3, min_score: float = 0.2) -> List[dict]:
        """返回 top_k 条命中，每条带 doc_id 供结论引用（可追溯率指标用）。"""
        qv = self._vec(query)
        hits = []
        for doc in self.docs:
            text = doc["title"] + " " + doc["content"]
            score = _cosine(qv, self._vec(text))
            if score >= min_score:
                hits.append({
                    "doc_id": doc["doc_id"],
                    "title": doc["title"],
                    "content": doc["content"],
                    "score": round(score, 4),
                })
        hits.sort(key=_by_score, reverse=True)
        return hits[:top_k]
