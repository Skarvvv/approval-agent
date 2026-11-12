# app/eval/cases.py
"""清单 #8 评测层 · 30 条人工标注用例（§12.6 定案口径）。

标注原则（重要）：**按 corpus 里的制度条文独立标注，不看代码怎么判**。
gold_reasons 写对应条款 / 判例的 doc_id，每条标注都有据可查。
V1 只做方案 §04 的前四类；第五类「提示词注入 / 诱导放行」是未教概念，暂不纳入。

类别分布（30 条）：常规低风险 9 / 材料缺失 7 / 越权敏感 9 / 边界模糊 5。
"""
from typing import List, Optional

from app.schemas import Application, EvalCase

CAT_NORMAL = "常规低风险"
CAT_MISSING = "材料缺失"
CAT_SENSITIVE = "越权敏感"
CAT_BOUNDARY = "边界模糊"


def _case(case_id: str, category: str, gold: str, reasons: List[str], *,
          applicant: str = "张三", department: str = "数据部",
          purpose: str = "常规业务导出", fields: Optional[List[str]] = None,
          row_count: int = 100) -> EvalCase:
    """构造一条标注用例；默认值 = 一张干净、材料齐全的常规申请单。

    `*` 之后的参数必须写名字；fields 默认 None 而不是 []，避免可变默认值共享。
    V1 全量人工确认，expect_human_review 恒为 True（§12.6：只记录、不考核）。
    """
    return EvalCase(
        case_id=case_id,
        category=category,
        gold_level=gold,
        gold_reasons=reasons,
        expect_human_review=True,
        application=Application(
            applicant=applicant,
            department=department,
            purpose=purpose,
            fields=list(fields) if fields is not None else ["order_id"],
            row_count=row_count,
        ),
    )


CASES: List[EvalCase] = [
    # ── 常规低风险 9 条：四项齐全、字段无个人信息、行数未过万 → low ──
    _case("N01", CAT_NORMAL, "low", ["policy#2.2", "case#23"],
          purpose="导出本月订单明细", fields=["order_id", "amount"], row_count=500),
    _case("N02", CAT_NORMAL, "low", ["policy#2.2"],
          purpose="导出商品库存清单", fields=["sku", "stock_qty"], row_count=1200),
    _case("N03", CAT_NORMAL, "low", ["policy#2.2"],
          purpose="门店日报核对", fields=["store_id", "sales_amount"], row_count=300),
    _case("N04", CAT_NORMAL, "low", ["policy#2.2"],
          purpose="财务对账明细", fields=["voucher_no", "amount"], row_count=2000),
    _case("N05", CAT_NORMAL, "low", ["policy#2.2"],
          purpose="物流运单查询", fields=["waybill_no", "status"], row_count=800),
    _case("N06", CAT_NORMAL, "low", ["policy#2.2"],
          purpose="课程报名人数统计", fields=["course_id", "headcount"], row_count=150),
    _case("N07", CAT_NORMAL, "low", ["policy#2.2"],
          purpose="客户满意度回访", fields=["customer_id", "score"], row_count=100),
    _case("N08", CAT_NORMAL, "low", ["policy#2.2"],
          purpose="设备台账导出", fields=["device_id", "model"], row_count=600),
    _case("N09", CAT_NORMAL, "low", ["policy#2.2"],
          purpose="上月销售明细", fields=["order_id", "qty"], row_count=9999),

    # ── 材料缺失 / 格式错误 7 条：退回补充 → mid ──
    _case("M01", CAT_MISSING, "mid", ["policy#1.1"],
          applicant="", purpose="导出本月订单明细", fields=["order_id"]),
    _case("M02", CAT_MISSING, "mid", ["policy#1.1"],
          department="", purpose="导出本月订单明细", fields=["order_id"]),
    _case("M03", CAT_MISSING, "mid", ["policy#1.1", "policy#3.1"],
          purpose="", fields=["order_id"]),
    _case("M04", CAT_MISSING, "mid", ["policy#1.1", "policy#3.1"],
          purpose="导出本月订单明细", fields=[]),
    _case("M05", CAT_MISSING, "mid", ["policy#3.1"],
          purpose="测试", fields=["order_id"]),
    _case("M06", CAT_MISSING, "mid", ["policy#3.1"],
          purpose="临时", fields=["order_id"]),
    _case("M07", CAT_MISSING, "mid", ["policy#3.1"],
          purpose="无", fields=["order_id"]),

    # ── 越权 / 敏感字段 / 大批量 9 条：安全红线 → high ──
    _case("S01", CAT_SENSITIVE, "high", ["policy#2.1", "case#17"],
          purpose="活动触达导出", fields=["user_phone"], row_count=300),
    _case("S02", CAT_SENSITIVE, "high", ["policy#2.1"],
          purpose="实名核验", fields=["id_card"], row_count=200),
    _case("S03", CAT_SENSITIVE, "high", ["policy#2.1"],
          purpose="退款核对", fields=["bank_card"], row_count=100),
    _case("S04", CAT_SENSITIVE, "high", ["policy#2.1"],
          purpose="用户通知", fields=["email"], row_count=500),
    _case("S05", CAT_SENSITIVE, "high", ["policy#2.1", "case#17"],
          purpose="短信触达", fields=["手机号"], row_count=400),
    _case("S06", CAT_SENSITIVE, "high", ["policy#2.2"],
          purpose="年度归档", fields=["order_id"], row_count=15000),
    _case("S07", CAT_SENSITIVE, "high", ["policy#2.1", "policy#2.3", "case#31"],
          purpose="月报汇总", fields=["user_phone"], row_count=300),
    # 下面两条按 policy#2.3「导出非本部门归属的数据」标 high；
    # V1 规则引擎尚未实现该条款，预期会漏判 —— 这是评测要发现的真问题。
    _case("S08", CAT_SENSITIVE, "high", ["policy#2.3"],
          department="财务部", purpose="导出营销部客户清单及触达记录",
          fields=["campaign_id", "customer_id"], row_count=800),
    _case("S09", CAT_SENSITIVE, "high", ["policy#2.3"],
          department="技术部", purpose="导出财务薪资明细供核算",
          fields=["salary_id", "amount"], row_count=400),

    # ── 边界模糊 / 制度冲突 5 条 ──
    _case("B01", CAT_BOUNDARY, "low", ["policy#2.2"],
          purpose="月度归档", fields=["order_id"], row_count=10000),   # 恰好一万，制度说「超过」
    _case("B02", CAT_BOUNDARY, "high", ["policy#2.2"],
          purpose="月度归档", fields=["order_id"], row_count=10001),
    # phone_model 是设备型号，不是 policy#2.1 说的个人信息；
    # V1 用子串包含判定，预期会误报 —— 模块 4 记过的副作用。
    _case("B03", CAT_BOUNDARY, "low", ["policy#2.1"],
          purpose="设备台账导出", fields=["phone_model"], row_count=200),
    _case("B04", CAT_BOUNDARY, "high", ["policy#2.3", "policy#2.1"],
          purpose="季度汇报", fields=["id_card"], row_count=100),
    _case("B05", CAT_BOUNDARY, "low", ["policy#2.2"],
          purpose="统计口径核对", fields=["order_id"], row_count=200),
]