# app/agent/tools.py
"""工具层：把知识库与规则引擎包成 Agent 可调用的工具（方案 §05 / §9）。

设计要点：
- 所有工具统一签名 (app, args) -> ToolResult，方便 execute_tool 盲分发；
- TOOLS 分发表 = 工具权限清单，LLM 只能挑表里的名字；
- 模块加载时构建一次知识库（与 FastAPI 单例思路一致，避免每次调用重读语料）。
"""
from app.schemas import Application, Action, ToolResult
from app.knowledge.store import KnowledgeStore
from app.rules.engine import evaluate

# 模块加载时构建一次知识库（语料随仓库自带，无 IO 依赖）
store = KnowledgeStore()


def search_policy(app: Application, args: dict) -> ToolResult:
    """工具1：按查询词检索制度/判例，返回可追溯的命中。"""
    query = args.get("query", "")
    hits = store.search(query, top_k=3, min_score=0.2)
    # content 是交给模型的纯文本资料；evidence 是结构化、可追溯的 doc_id
    lines = [f"[{h['doc_id']}] {h['title']}: {h['content']}" for h in hits]
    content = "\n".join(lines) if lines else "未检索到相关制度/判例"
    return ToolResult(
        tool_name="search_policy",
        ok=True,                     # 工具执行成功（区别于「是否发现风险」）
        content=content,
        evidence=[h["doc_id"] for h in hits],
    )


def check_rules(app: Application, args: dict) -> ToolResult:
    """工具2：跑确定性规则，返回命中与风险等级。"""
    result = evaluate(app)
    content = f"{result['summary']}；依据：{', '.join(result['evidence'])}"
    return ToolResult(
        tool_name="check_rules",
        ok=True,
        content=content,
        evidence=result["evidence"],
    )


# 分发表：工具名 -> 实现函数。代码在这里握着工具权限（§9）。
TOOLS = {
    "search_policy": search_policy,
    "check_rules": check_rules,
}


def execute_tool(action: Action, app: Application) -> ToolResult:
    """统一入口：查表分发，未知工具一律拒绝（安全闸）。"""
    fn = TOOLS.get(action.action)    # 查不到返回 None
    if fn is None:
        return ToolResult(
            tool_name=action.action,
            ok=False,
            content=f"未知工具：{action.action}；可用：{list(TOOLS)}",
            evidence=[],
        )
    return fn(app, action.args)