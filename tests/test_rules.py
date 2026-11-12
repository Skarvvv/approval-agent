# tests/test_rules.py
"""规则引擎单测：确定性、可回归，不调 LLM。

覆盖 5 条规则、等级取最高、证据去重、边界值，以及两处已知副作用/修复点。
"""
import pytest

from app.schemas import Application
from app.rules.engine import (
    LARGE_EXPORT_ROWS, _has_sensitive, evaluate,
)


def make_app(**kw) -> Application:
    """一张干净、材料齐全的常规申请单；用例只覆盖要改的字段。"""
    base = dict(applicant="张三", department="数据部", purpose="常规业务导出",
                fields=["order_id"], row_count=100)
    base.update(kw)
    return Application(**base)


def test_clean_application_is_low():
    r = evaluate(make_app())
    assert r["max_severity"] == "low"
    assert r["hits"] == []
    assert r["evidence"] == []


@pytest.mark.parametrize("purpose", ["测试", "临时", "无", "暂无", "随便", "test", "", "   "])
def test_vague_purpose_hits_mid(purpose):
    r = evaluate(make_app(purpose=purpose))
    assert any(h["rule_id"] == "R-VAGUE-PURPOSE" for h in r["hits"])
    assert r["max_severity"] == "mid"


@pytest.mark.parametrize("field", ["user_phone", "id_card", "bank_card",
                                   "email", "手机号", "身份证"])
def test_sensitive_field_hits_high(field):
    r = evaluate(make_app(fields=[field]))
    assert any(h["rule_id"] == "R-SENSITIVE-FIELDS" for h in r["hits"])
    assert r["max_severity"] == "high"


def test_missing_materials_mid():
    r = evaluate(make_app(fields=[]))
    assert r["max_severity"] == "mid"
    assert any(h["rule_id"] == "R-MISSING-MATERIALS" for h in r["hits"])


def test_large_export_threshold_is_strict():
    # 制度说「超过一万行」，恰好一万不算
    assert evaluate(make_app(row_count=LARGE_EXPORT_ROWS))["max_severity"] == "low"
    assert evaluate(make_app(row_count=LARGE_EXPORT_ROWS + 1))["max_severity"] == "high"


def test_max_severity_wins_not_vote():
    # 同时命中 high 与 mid 时取最高，不是按命中数量投票
    r = evaluate(make_app(purpose="月报汇总", fields=["user_phone"]))
    assert r["max_severity"] == "high"
    assert len(r["hits"]) >= 2


def test_evidence_dedup_and_sorted():
    r = evaluate(make_app(purpose="月报汇总", fields=["user_phone"]))
    assert r["evidence"] == sorted(set(r["evidence"]))


def test_summary_words_narrowed_regression():
    # 模块 4 修过的 bug：「月报导出」不该触发用途-字段不匹配
    r = evaluate(make_app(purpose="月报导出", fields=["user_phone"]))
    assert not any(h["rule_id"] == "R-PURPOSE-FIELD-MISMATCH" for h in r["hits"])


def test_substring_side_effect_is_documented():
    # 已知副作用（评测 B03）：设备型号 phone_model 也被子串命中
    assert _has_sensitive(["phone_model"]) is True
