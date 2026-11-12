import os
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from app.schemas import Application
from app.agent.loop import run_agent
from app.governance.audit import write_trace
from app.schemas import Application, ReviewRequest
from app.governance.approval import get_trace, submit_review

# 让 .env 生效（.env 已被 .gitignore 屏蔽，永远不会进仓库）
load_dotenv()

app = FastAPI(
    title="变更申请单智能预审 Agent",
    version="0.1.0",
    description="V1：受理数据导出申请，跑 ReAct 预审循环，输出带依据的风险建议；全量转人工确认。",
)


@app.get("/", include_in_schema=False)
def index() -> RedirectResponse:
    """打开根地址直接跳到 API 文档，方便展示。"""
    return RedirectResponse(url="/docs")


@app.get("/health")
def health() -> dict:
    """存活检查：clone 后第一条验证服务起来的命令。"""
    return {"status": "ok"}


@app.post("/applications", status_code=202)
def submit_application(application: Application) -> dict:
    """受理一张数据导出申请，并返回 Agent 的预审建议。

    两层「需不需要人工」要分清：
    - verdict.need_human_review 是 Agent 的**建议**（low 时会是 False）；
    - 顶层 need_human_review 是**系统策略**，V1 一律 True（§12.6 定案：全量人工确认）。
    """
    mock = not bool(os.getenv("DEEPSEEK_API_KEY"))
    request_id = f"req-{uuid4().hex[:8]}"
    mode = "mock" if mock else "live"

    trace: list = []
    verdict = run_agent(application, mock=mock, trace=trace)
    write_trace(request_id, trace, verdict.model_dump(), mode)

    return {
        "request_id": request_id,
        "status": "pending_review",
        "need_human_review": True,           # 系统策略：V1 全量人工确认
        "mode": "mock" if mock else "live",  # 标明哪组结果，评测时分开报（§12.6）
        "verdict": verdict.model_dump(),     # Agent 建议：level / reasons / evidence / 建议是否转人工
        "applicant": application.applicant,
        "row_count": application.row_count,
    }


@app.get("/requests/{request_id}")
def replay_request(request_id: str) -> dict:
    """按 request_id 回放完整轨迹与 Agent 建议（治理层验收项）。"""
    return get_trace(request_id)


@app.post("/review")
def review_application(review: ReviewRequest) -> dict:
    """人工确认门：V1 全量确认，结果作为 human 事件写回同一张审计表。"""
    return submit_review(review)
