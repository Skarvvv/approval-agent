from typing import List, Optional

from app.schemas import Application

SENSITIVE_TERMS = {
    "手机号", "身份证", "银行卡", "邮箱",
    "phone", "id_card", "bank_card", "email",
}
VAGUE_PURPOSES = {"测试", "临时", "无", "暂无", "随便", "test", ""}
SUMMARY_WORDS = ("汇总", "报表", "统计")
LARGE_EXPORT_ROWS = 10_000


def _has_sensitive(fields: List[str]) -> bool:
    for field in fields:
        for term in SENSITIVE_TERMS:
            if term in field:
                return True
    return False


def _is_vague(purpose: str) -> bool:
    return purpose.strip() in VAGUE_PURPOSES


def _looks_like_summary(purpose: str) -> bool:
    return any(word in purpose for word in SUMMARY_WORDS)


def _rule_missing_materials(app: Application) -> Optional[dict]:
    if (not app.applicant.strip() or not app.department.strip()
            or not app.purpose.strip() or not app.fields):
        return {"rule_id": "R-MISSING-MATERIALS",
                "severity": "mid",
                "reason": "申请人 / 部门 / 用途 / 字段清单存在缺失",
                "evidence": ["policy#1.1"]}
    return None


def _rule_vague_purpose(app: Application) -> Optional[dict]:
    if _is_vague(app.purpose):
        return {"rule_id": "R-VAGUE-PURPOSE", "severity": "mid",
                "reason": "导出用途填写笼统，材料不齐备",
                "evidence": ["policy#3.1"]}
    return None


def _rule_sensitive_fields(app: Application) -> Optional[dict]:
    if _has_sensitive(app.fields):
        return {"rule_id": "R-SENSITIVE-FIELDS", "severity": "high",
                "reason": "字段清单包含个人敏感信息，须双人审批",
                "evidence": ["policy#2.1", "case#17"]}
    return None


def _rule_large_export(app: Application) -> Optional[dict]:
    if app.row_count > LARGE_EXPORT_ROWS:
        return {"rule_id": "R-LARGE-EXPORT", "severity": "high",
                "reason": f"导出行数 {app.row_count} 超过制度阈值 {LARGE_EXPORT_ROWS}",
                "evidence": ["policy#2.2"]}
    return None


def _rule_purpose_field_mismatch(app: Application) -> Optional[dict]:
    if _looks_like_summary(app.purpose) and _has_sensitive(app.fields):
        return {"rule_id": "R-PURPOSE-FIELD-MISMATCH", "severity": "high",
                "reason": "用途为汇总类，字段却含敏感信息，明显不匹配",
                "evidence": ["policy#2.3", "case#31"]}
    return None


RULES = [
    _rule_missing_materials,
    _rule_vague_purpose,
    _rule_sensitive_fields,
    _rule_large_export,
    _rule_purpose_field_mismatch,
]


def evaluate(app: Application) -> dict:
    """跑全部确定性规则，返回命中列表、最高等级与去重后的依据。"""
    hits = []
    for rule in RULES:
        hit = rule(app)
        if hit is not None:
            hits.append(hit)

    severities = [h["severity"] for h in hits]
    if "high" in severities:
        max_severity = "high"
    elif "mid" in severities:
        max_severity = "mid"
    else:
        max_severity = "low"

    evidence = set()
    for hit in hits:
        for e in hit["evidence"]:
            evidence.add(e)

    return {"hits": hits, "max_severity": max_severity,
            "evidence": sorted(evidence),
            "summary": f"命中 {len(hits)} 条规则，最高等级 {max_severity}"}
