# app/governance/audit.py
"""清单 #7 治理层 · 留痕：把每次决策与工具调用写成一条 AuditEvent。

方案 §05 的判断：留痕 / 人工干预 / 成本归因是同一次实现的三个面 ——
只要把「每一次工具调用和每一次决策」记成结构化事件，三件事同时成立。

V1 边界：mock 无真实 token，tokens / cost 先记 0；确认门 /review 留到 #7 第二块。
"""
import json
from pathlib import Path
from typing import List

from app.schemas import AuditEvent

# audit.py 在 app/governance/ 下，parents[2] 即项目根
AUDIT_PATH = Path(__file__).resolve().parents[2] / "logs" / "audit.jsonl"


def append_event(event: AuditEvent, path: Path = AUDIT_PATH) -> None:
    """追加一条事件；父目录不存在就建。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(event.model_dump_json() + "\n")


def read_events(path: Path = AUDIT_PATH) -> List[AuditEvent]:
    """读回所有事件（回放 / 评测用）；文件不存在返回空列表。"""
    if not path.exists():
        return []
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            events.append(AuditEvent(**json.loads(line)))
    return events


def write_trace(request_id: str, trace: list, verdict: dict, mode: str,
                path: Path = AUDIT_PATH) -> List[AuditEvent]:
    """把 loop 收集的轨迹逐条转成 AuditEvent 落盘，最后补一条 verdict 事件。"""
    events: List[AuditEvent] = []
    for step, item in enumerate(trace, start=1):
        events.append(AuditEvent(
            request_id=request_id,
            step=step,
            actor=item["actor"],
            action=item["action"],
            args=item.get("args", {}),
            result=item.get("result", {}),
            evidence=item.get("evidence", []),
        ))
    events.append(AuditEvent(
        request_id=request_id,
        step=len(trace) + 1,
        actor="agent",
        action="verdict",
        args={"mode": mode},
        result=verdict,
        evidence=verdict.get("evidence", []),
    ))
    for event in events:
        append_event(event, path)
    return events
