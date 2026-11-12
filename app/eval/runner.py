# app/eval/runner.py
"""清单 #8 评测层 · 一键回归。

用法（项目根）：
    uv run python -m app.eval.runner                 # 默认 mock，无密钥可跑
    EVAL_MODE=live uv run python -m app.eval.runner  # 真实模型组，需 DEEPSEEK_API_KEY

设计：直接调 run_agent，不经过 main.submit_application —— 评测不污染生产审计表。
两条组分开报（§12.6），报告写到 eval_results/<mode>.json。
"""
import json
import os
from pathlib import Path
from typing import Optional

from app.agent.loop import run_agent
from app.eval.cases import CASES
from app.eval.metrics import compute_metrics, load_corpus_ids

# runner.py 在 app/eval/ 下，parents[2] 即项目根
RESULTS_DIR = Path(__file__).resolve().parents[2] / "eval_results"


def run(mode: str = "mock") -> dict:
    """跑完整用例集，返回 {report, rows}。"""
    corpus_ids = load_corpus_ids()
    rows = []
    for case in CASES:
        trace: list = []
        verdict = run_agent(case.application, mock=(mode != "live"), trace=trace)
        rows.append({
            "case_id": case.case_id,
            "category": case.category,
            "gold_level": case.gold_level,
            "gold_reasons": case.gold_reasons,
            "predicted_level": verdict.level,
            "evidence": verdict.evidence,
            # 工具调用轮数 = 轨迹里 actor="tool" 的条数
            "tool_calls": sum(1 for t in trace if t["actor"] == "tool"),
            "tokens_in": 0,
            "tokens_out": 0,
            "cost": 0.0,
        })
    return {"report": compute_metrics(rows, mode, corpus_ids), "rows": rows}


def _baseline_file(mode: str) -> Path:
    """首次运行自动固化的基线；之后每次回归都与它比，看指标有没有退化。"""
    return RESULTS_DIR / f"baseline_{mode}.json"


def print_report(report: dict, baseline: Optional[dict] = None) -> None:
    """在终端打印人能读的报告（README.md 里的表就从这里抄）。"""
    def pct(x: float) -> str:
        return f"{x * 100:.1f}%"

    a = report["accuracy"]
    print(f"=== approval-agent 评测报告 [{report['mode']}] ===")
    print(f"用例数: {report['n_cases']}")
    print(f"风险分级准确率: {pct(a['value'])}  ({a['correct']}/{a['total']})")
    print("  分类别:")
    for cat, item in report["accuracy_by_category"].items():
        print(f"    {cat}: {pct(item['value'])}  ({item['correct']}/{item['total']})")
    m = report["miss_rate"]
    print(f"漏判率: {pct(m['value'])}  ({m['numerator']}/{m['denominator']} 条标注 high)")
    t = report["traceability_rate"]
    print(f"依据可追溯率: {pct(t['value'])}  ({t['traceable']}/{t['total']})")
    print(f"平均工具调用轮数: {report['avg_tool_calls']:.2f}")
    print(f"单均 token: {report['avg_tokens']:.0f}  |  单均成本: {report['avg_cost']:.4f}")
    print(f"  * {report['token_note']}")
    cs = report["confusions"]
    print(f"--- 分级不一致用例 ({len(cs)}) ---")
    for c in cs:
        print(f"  {c['case_id']} [{c['category']}] gold={c['gold_level']} "
              f"pred={c['predicted_level']} 依据={c['gold_reasons']}")

    # 与首次固化的基线比：改了规则 / prompt / 模型后，一眼看出指标有没有退化
    if baseline is not None:
        old = baseline["report"]
        print("--- 与基线对比（基线为首次运行结果）---")
        for key, label in (("accuracy", "风险分级准确率"),
                           ("miss_rate", "漏判率"),
                           ("traceability_rate", "依据可追溯率")):
            before, after = old[key]["value"], report[key]["value"]
            print(f"  {label}: {pct(before)} -> {pct(after)}  ({(after - before) * 100:+.1f} pp)")
        delta_calls = report["avg_tool_calls"] - old["avg_tool_calls"]
        print(
            f"  平均工具调用轮数: {old['avg_tool_calls']:.2f} -> {report['avg_tool_calls']:.2f}  ({delta_calls:+.2f} 次)")

    else:
        print("--- 首次运行：本次结果将固化为基线 ---")
    print("--------------------------------")


def main() -> None:
    mode = os.getenv("EVAL_MODE", "mock")
    baseline_file = _baseline_file(mode)
    baseline = None
    if baseline_file.exists():
        baseline = json.loads(baseline_file.read_text(encoding="utf-8"))

    result = run(mode)
    print_report(result["report"], baseline)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    (RESULTS_DIR / f"{mode}.json").write_text(payload, encoding="utf-8")
    if baseline is None:
        baseline_file.write_text(payload, encoding="utf-8")
        print(f"基线已固化: {baseline_file}")
    print(f"报告已写入: {RESULTS_DIR / (mode + '.json')}")


if __name__ == "__main__":
    main()
