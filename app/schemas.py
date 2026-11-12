from typing import List, Literal, Optional

from pydantic import BaseModel, Field

RiskLevel = Literal["low", "mid", "high"]
ActionName = Literal["search_policy", "check_rules", "finish"]
Actor = Literal["agent", "human", "tool"]
ReviewDecision = Literal["approve", "reject"]


class Application(BaseModel):
    """一张 数据导出申请单。"""
    applicant: str = Field(..., description="申请人")
    department: str = Field(..., description="申请部门")
    purpose: str = Field(..., description="导出用途")
    fields: List[str] = Field(..., description="申请导出的字段列表")
    row_count: int = Field(..., ge=0, description="预计导出行数")


class ToolResult(BaseModel):
    """工具执行结果，作为 Observation 回填 messages。"""
    tool_name: str
    ok: bool
    content: str = Field(..., description="交给模型的文本资料")
    evidence: List[str] = Field(default_factory=list, description="命中的条款/判例 ID")


class Action(BaseModel):
    """LLM 一轮的结构化决策（§10 契约）。"""
    thought: str = Field(..., description="显式推理，便于复盘")
    action: ActionName = Field(..., description="工具名或结束")
    args: dict = Field(default_factory=dict, description="工具入参，代码查表后传入")
    answer: Optional[str] = Field(default=None, description="仅 finish 时填")


class Verdict(BaseModel):
    """预审结论：这是模型建议，不是最终放行。"""
    level: RiskLevel = Field(..., description="建议风险等级")
    reasons: List[str] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)
    need_human_review: bool = Field(default=True, description="V1 恒为 True")


class ReviewRequest(BaseModel):
    """人工复核提交（清单 #7 确认门）。"""
    request_id: str = Field(..., description="要复核的申请单 ID")
    decision: ReviewDecision = Field(..., description="人工最终决定：approve / reject")
    reviewer: str = Field(..., description="复核人")
    final_level: RiskLevel = Field(..., description="人工认定的风险等级")
    reason: str = Field(default="", description="复核意见；覆盖 Agent 建议时必填")


class AuditEvent(BaseModel):
    """一条审计事件 = 留痕 + 人工干预 + 成本归因（方案 §05）。"""
    request_id: str
    step: int
    actor: Actor
    action: str
    args: dict = Field(default_factory=dict)
    result: dict = Field(default_factory=dict)
    evidence: List[str] = Field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    cost: float = 0.0
    human_override: bool = False
    override_reason: Optional[str] = None


class EvalCase(BaseModel):
    """一条评测用例，字段与笔记 §12.6 的六字段口径对齐。"""
    case_id: str
    application: Application
    gold_level: RiskLevel
    gold_reasons: List[str] = Field(default_factory=list)
    expect_human_review: bool = True
    category: str
