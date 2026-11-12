# app/agent/loop.py
"""模块6：ReAct 执行循环（方案 §05 / §9 / §10）。

把三层东西串起来：
- schemas.Action        ：模型输出的「思考-动作」结构
- tools.execute_tool    ：工具分发表（权限握在代码手里，§9）
- LLM（或 mock 替身）   ：决策下一步动作

防幻觉设计（呼应学习笔记 §11「防幻觉四层」）：
- temperature=0            → 降随机；
- 循环上限 MAX_STEPS        → 防无限循环（复核闸）；
- 风险等级只由确定性规则引擎定 → LLM 不参与分级，只「解释 + 引用依据」（依据回填）；
- 模型输出解析失败          → 直接转人工复核（显式拒答的兜底）。
"""
import json
import os
from openai import OpenAI

from app.schemas import Application, Action, Verdict
from app.agent.tools import execute_tool
from app.rules.engine import evaluate
from typing import Optional

MAX_STEPS = 5
LLM_MODEL = "deepseek-chat"
LLM_BASE_URL = "https://api.deepseek.com"
LLM_TEMP = 0.0

SYSTEM_PROMPT = """你是一个「变更申请单智能预审」Agent。
任务：根据一张数据变更申请单，判断风险等级，并给出是否需要人工复核的结论。

可用工具（每轮只能调用其中一个）：
- search_policy(query: str): 按关键词检索制度/判例，返回带 doc_id 的可追溯命中
- check_rules(): 跑确定性合规规则，返回命中的风险条款与最高等级

建议工作流：先 check_rules 拿确定性风险，再按需 search_policy 找依据，最后用 finish 给结论。
每轮你只能输出一个 JSON 对象，二选一：
1) 调工具：{"thought": "思考", "action": "search_policy" 或 "check_rules", "args": {...}}
2) 收尾：{"thought": "思考", "action": "finish", "answer": "结论，必须引用工具返回的 doc_id 作为依据"}
严禁编造 doc_id 或条款；结论里的依据必须来自工具实际返回的 evidence。"""


def _call_llm_real(messages: list) -> Action:
    """真实模式：调 DeepSeek，解析出 Action；解析失败则安全兜底。"""
    client = OpenAI(api_key=os.getenv("DEEPSEEK_API_KEY"), base_url=LLM_BASE_URL)
    resp = client.chat.completions.create(
        model=LLM_MODEL,
        messages=messages,
        temperature=LLM_TEMP,
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content
    try:
        data = json.loads(raw)       # 一级：JSON 字符串 → 字典
        return Action(**data)        # 二级：字典 → 带类型校验的 Action
    except (json.JSONDecodeError, ValueError, TypeError):
        # 解析 / 校验失败 → 显式拒答，强制转人工（防幻觉兜底）
        return Action(thought="模型输出无法解析", action="finish",
                      answer="模型输出解析失败，已转人工复核。")


def _call_llm_mock(messages: list) -> Action:
    """mock 模式：确定性策略，驱动同一套循环，无需任何 API key。"""
    obs_count = sum(
        1 for m in messages
        if m["role"] == "user" and m["content"].startswith("Observation:")
    )
    if obs_count == 0:
        return Action(thought="先跑规则拿确定性风险", action="check_rules", args={})
    if obs_count == 1:
        last = [m for m in messages
                if m["role"] == "user" and m["content"].startswith("Observation:")][-1]["content"]
        if "high" in last or "mid" in last:
            return Action(thought="有风险命中，检索相关制度找依据",
                          action="search_policy", args={"query": "敏感字段 双人审批"})
        return Action(thought="无风险命中，直接收尾", action="finish",
                      answer="经规则检查未发现风险命中，建议等级 low，可自动放行。")
    return Action(thought="已有规则与制度依据，给出结论", action="finish",
                  answer="命中敏感字段相关条款，依据 policy#2.1 / case#17，建议 high，须双人审批，转人工复核。")


def _build_verdict(rule_result: dict, policy_evidence: list) -> Verdict:
    """依据回填：等级取规则引擎的权威结果，证据合并「规则 + 制度检索」。"""
    level = rule_result["max_severity"] if rule_result else "low"
    reasons = ([h["reason"] for h in rule_result["hits"]]
               if rule_result else ["未命中任何规则"])
    evidence = list(sorted(set(
        (rule_result["evidence"] if rule_result else []) + list(policy_evidence)
    )))
    need_human = level in ("high", "mid")
    return Verdict(level=level, reasons=reasons, evidence=evidence,
                   need_human_review=need_human)

def run_agent(app: Application, mock: bool = True, max_steps: int = MAX_STEPS,
              trace: Optional[list] = None) -> Verdict:
    """ReAct 主循环：返回一张预审结论 Verdict。

    trace：可选。传一个空 list，循环会把每步决策与工具结果 append 进去，
           供治理层写成 AuditEvent；默认 None = 不留痕，旧调用完全不受影响。
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"请预审以下申请单：{app.model_dump_json()}"},
    ]
    policy_evidence: list = []

    for _ in range(max_steps):
        action = _call_llm_mock(messages) if mock else _call_llm_real(messages)

        # 留痕 ①：Agent 这一轮的决策
        if trace is not None:
            trace.append({
                "actor": "agent", "action": action.action,
                "args": action.args,
                "result": {"thought": action.thought},
                "evidence": [],
            })

        if action.action == "finish":
            return _build_verdict(evaluate(app), policy_evidence)

        obs = execute_tool(action, app)

        # 留痕 ②：工具实际返回了什么
        if trace is not None:
            trace.append({
                "actor": "tool", "action": obs.tool_name,
                "args": action.args,
                "result": {"ok": obs.ok, "content": obs.content},
                "evidence": obs.evidence,
            })

        if action.action == "search_policy":
            policy_evidence.extend(obs.evidence)

        messages.append({"role": "assistant", "content": action.model_dump_json()})
        messages.append({"role": "user",
                         "content": f"Observation: ok={obs.ok} | {obs.content} | evidence={obs.evidence}"})

    return _build_verdict(evaluate(app), policy_evidence)   # 步数超限兜底
