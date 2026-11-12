# tests/test_loop.py
"""Agent 循环单测：mock 模式、trace 埋点、安全闸与超限兜底。

全部走 mock，不发网络请求、不消耗额度。
"""
from app.agent.loop import run_agent
from app.agent.tools import TOOLS, execute_tool
from app.schemas import Action, Application


def make_app(**kw) -> Application:
    base = dict(applicant="张三", department="数据部", purpose="常规业务导出",
                fields=["order_id"], row_count=100)
    base.update(kw)
    return Application(**base)


def test_finish_is_not_a_tool():
    # finish 是终止信号，由循环提前拦截，不能进 dispatch table
    assert "finish" not in TOOLS
    assert Action(thought="t", action="finish").action == "finish"


def test_dispatch_fallback_for_legal_but_unregistered_action():
    # finish 是合法 Literal，但不在 TOOLS 里 → 走兜底拒绝
    r = execute_tool(Action(thought="t", action="finish", args={}), make_app())
    assert r.ok is False
    assert "未知工具" in r.content


def test_mock_high_risk_verdict():
    trace: list = []
    v = run_agent(make_app(purpose="月报汇总", fields=["user_phone"]),
                  mock=True, trace=trace)
    assert v.level == "high"
    assert v.need_human_review is True
    assert "policy#2.1" in v.evidence


def test_mock_clean_verdict():
    v = run_agent(make_app(purpose="导出本月订单", fields=["order_id"]), mock=True)
    assert v.level == "low"
    assert v.need_human_review is False


def test_trace_records_both_decisions_and_tool_results():
    trace: list = []
    run_agent(make_app(fields=["user_phone"]), mock=True, trace=trace)
    assert len(trace) >= 2
    assert trace[0]["actor"] == "agent"
    assert any(t["actor"] == "tool" for t in trace)
    for t in trace:
        assert {"actor", "action", "args", "result", "evidence"} <= set(t)


def test_trace_none_keeps_old_call_compatible():
    # 不传 trace 的旧调用必须照常工作
    v = run_agent(make_app(), mock=True)
    assert v.level in ("low", "mid", "high")


def test_max_steps_fallback_still_verdicts():
    # 步数用尽走兜底，等级仍由规则引擎拍板
    v = run_agent(make_app(fields=["user_phone"]), mock=True, max_steps=0)
    assert v.level == "high"


def test_prompt_is_loaded_from_prompts_module():
    import app.agent.loop as loop
    from app.agent.prompts import SYSTEM_PROMPT
    assert loop.SYSTEM_PROMPT is SYSTEM_PROMPT
    assert "search_policy" in SYSTEM_PROMPT and "check_rules" in SYSTEM_PROMPT
