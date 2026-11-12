# app/eval/metrics.py
"""清单 #8 评测层 · 5 指标计算（§12.6 定案口径）。

纯函数：只吃 runner 收集的行数据，不碰文件、不调模型，方便单测。
"""
import json
from pathlib import Path
from typing import List

# metrics.py 在 app/eval/ 下，parents[1] 即 app/
CORPUS_FILE = Path(__file__).resolve().parents[1] / "knowledge" / "corpus" / "corpus.json"


def load_corpus_ids(path: Path = CORPUS_FILE) -> set:
    """读语料里所有合法 doc_id，供「依据可追溯率」校验。"""
    docs = json.loads(path.read_text(encoding="utf-8"))
    return {d["doc_id"] for d in docs}


def _div(a: float, b: float) -> float:
    """除法小工具：分母为 0 时返回 0.0，避免 ZeroDivisionError。"""
    return a / b if b else 0.0


def compute_metrics(rows: List[dict], mode: str, corpus_ids: set) -> dict:
    """按 §12.6 口径算 5 个指标 + 分类别准确率 + 不一致清单。"""
    n = len(rows)

    correct = sum(1 for r in rows if r["gold_level"] == r["predicted_level"])

    # 分类别准确率：类别不均衡会把总准确率刷高，必须分开报
    by_cat = {}
    for r in rows:
        by_cat.setdefault(r["category"], []).append(r)
    accuracy_by_category = {
        cat: {"correct": sum(1 for x in xs if x["gold_level"] == x["predicted_level"]),
              "total": len(xs),
              "value": _div(sum(1 for x in xs if x["gold_level"] == x["predicted_level"]), len(xs))}
        for cat, xs in by_cat.items()
    }

    # 漏判率：标注 high 但建议非 high / 全部标注 high
    high_rows = [r for r in rows if r["gold_level"] == "high"]
    missed = [r for r in high_rows if r["predicted_level"] != "high"]

    # 依据可追溯率：evidence 非空，且每个 ID 都能在 corpus 查到（只测形式）
    def traceable(r: dict) -> bool:
        ev = r["evidence"]
        return bool(ev) and all(doc_id in corpus_ids for doc_id in ev)

    traceable_n = sum(1 for r in rows if traceable(r))

    tool_calls = sum(r["tool_calls"] for r in rows)
    tokens = sum(r["tokens_in"] + r["tokens_out"] for r in rows)
    cost = sum(r["cost"] for r in rows)

    confusions = [
        {"case_id": r["case_id"], "category": r["category"],
         "gold_level": r["gold_level"], "predicted_level": r["predicted_level"],
         "gold_reasons": r["gold_reasons"]}
        for r in rows if r["gold_level"] != r["predicted_level"]
    ]

    return {
        "mode": mode,
        "n_cases": n,
        "accuracy": {"correct": correct, "total": n, "value": _div(correct, n)},
        "accuracy_by_category": accuracy_by_category,
        "miss_rate": {"numerator": len(missed), "denominator": len(high_rows),
                      "value": _div(len(missed), len(high_rows))},
        "traceability_rate": {"traceable": traceable_n, "total": n,
                              "value": _div(traceable_n, n)},
        "avg_tool_calls": _div(tool_calls, n),
        "avg_tokens": _div(tokens, n),
        "avg_cost": _div(cost, n),
        "confusions": confusions,
        "token_note": "mock 组不产生真实 token，tokens / cost 恒为 0；仅 live 组有成本意义",
    }
