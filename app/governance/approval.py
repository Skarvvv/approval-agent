# app/governance/approval.py
"""清单 #7 治理层 · 人工确认门（V1 全量确认）。

设计要点：**不引入第二套存储**。
待审项、Agent 建议、是否已复核，全部从 audit.jsonl 回放得到；
复核结果作为一条 actor="human" 的 AuditEvent 追加写回同一张表。
方案 §05 的「留痕 / 人工干预 / 成本归因三合一」由此闭合。

human_override / override_reason 是 V4 做 Bad Case 回流的种子数据。
"""
from typing import List, Optional

from fastapi import HTTPException

from app.schemas import AuditEvent, ReviewRequest
from app.governance.audit import append_event, read_events


def _events_for(request_id: str) -> List[AuditEvent]:
    """按 request_id 过滤出这次请求的所有事件。"""
    return [e for e in read_events() if e.request_id == request_id]


def _verdict_event(events: List[AuditEvent]) -> Optional[AuditEvent]:
    """找 Agent 结论那条事件；生成器取第一个，取不到返回 None。"""
    return next((e for e in events if e.action == "verdict"), None)


def _review_event(events: List[AuditEvent]) -> Optional[AuditEvent]:
    """找人工复核那条事件（用来判断是否重复提交）。"""
    return next((e for e in events if e.actor == "human" and e.action == "review"), None)


def get_trace(request_id: str) -> dict:
    """回放一次请求的完整轨迹（治理层验收项：任意请求能回放）。"""
    events = _events_for(request_id)
    if not events:
        raise HTTPException(status_code=404, detail=f"request_id 不存在：{request_id}")

    verdict_ev = _verdict_event(events)
    review_ev = _review_event(events)
    return {
        "request_id": request_id,
        "status": "reviewed" if review_ev else "pending_review",
        "suggested_level": verdict_ev.result.get("level") if verdict_ev else None,
        "review": review_ev.result if review_ev else None,
        "events": [e.model_dump() for e in events],
    }


def submit_review(review: ReviewRequest) -> dict:
    """人工复核：校验 → 判断是否覆盖建议 → 追加一条 human 事件。"""
    events = _events_for(review.request_id)
    if not events:
        raise HTTPException(status_code=404, detail=f"request_id 不存在：{review.request_id}")
    if _review_event(events):
        raise HTTPException(status_code=409, detail="该申请已复核，不可重复提交")

    verdict_ev = _verdict_event(events)
    suggested = verdict_ev.result.get("level") if verdict_ev else None
    override = suggested is not None and review.final_level != suggested
    if override and not review.reason.strip():
        raise HTTPException(status_code=422, detail="覆盖了 Agent 建议，必须填写复核理由")

    event = AuditEvent(
        request_id=review.request_id,
        step=max(e.step for e in events) + 1,
        actor="human",
        action="review",
        args={"decision": review.decision, "reviewer": review.reviewer},
        result={
            "decision": review.decision,
            "final_level": review.final_level,
            "suggested_level": suggested,
            "human_override": override,
            "note": review.reason.strip(),
        },
        evidence=verdict_ev.evidence if verdict_ev else [],
        human_override=override,
        # 语义收窄：override_reason 只在「人工确实覆盖了建议」时有值；
        # 普通复核意见放在 result.note，两条信息都不丢。
        override_reason=(review.reason.strip() or None) if override else None,
    )
    append_event(event)

    return {
        "request_id": review.request_id,
        "status": "reviewed",
        "decision": review.decision,
        "reviewer": review.reviewer,
        "suggested_level": suggested,
        "final_level": review.final_level,
        "human_override": override,
        "step": event.step,
    }
