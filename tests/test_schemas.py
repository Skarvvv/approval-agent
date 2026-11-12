# tests/test_schemas.py
"""契约层单测：Pydantic 校验（对应 API 的 422）与默认值行为。"""
import json

import pytest
from pydantic import ValidationError

from app.schemas import Action, Application, AuditEvent, ReviewRequest, ToolResult, Verdict


def test_application_rejects_negative_row_count():
    with pytest.raises(ValidationError):
        Application(applicant="a", department="d", purpose="p",
                    fields=["x"], row_count=-1)


def test_application_requires_all_five_fields():
    with pytest.raises(ValidationError):
        Application(applicant="a")


def test_action_rejects_unknown_name():
    # 类型层（Literal）先于 dispatch table 拦住非法动作
    with pytest.raises(ValidationError):
        Action(thought="t", action="drop_table", args={})


def test_action_finish_is_a_valid_literal():
    a = Action(thought="t", action="finish", args={}, answer="结论")
    assert a.action == "finish"
    assert a.answer == "结论"


def test_default_factory_is_not_shared():
    a = ToolResult(tool_name="x", ok=True, content="")
    b = ToolResult(tool_name="y", ok=True, content="")
    a.evidence.append("policy#1.1")
    assert b.evidence == []          # 可变默认值陷阱


def test_verdict_defaults():
    v = Verdict(level="low")
    assert v.need_human_review is True
    assert v.reasons == []
    assert v.evidence == []


def test_review_request_rejects_bad_decision():
    with pytest.raises(ValidationError):
        ReviewRequest(request_id="r", decision="maybe", reviewer="x", final_level="low")


def test_review_request_rejects_bad_level():
    with pytest.raises(ValidationError):
        ReviewRequest(request_id="r", decision="approve", reviewer="x", final_level="critical")


def test_audit_event_actor_is_literal():
    with pytest.raises(ValidationError):
        AuditEvent(request_id="r", step=1, actor="robot", action="x")


def test_model_dump_json_roundtrip():
    v = Verdict(level="high", reasons=["r"], evidence=["policy#2.1"])
    assert Verdict(**json.loads(v.model_dump_json())) == v
