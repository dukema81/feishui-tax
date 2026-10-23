# -*- coding: utf-8 -*-
"""税计算内核单元测试：口径依据现行税法（2026）。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "backend"))
from decimal import Decimal as D  # noqa: E402

import pytest  # noqa: E402

import tax as T  # noqa: E402


def f(x):
    return float(x) if isinstance(x, D) else x


# ---------- 增值税 ----------
class TestVat:
    def test_invoice_exclusive_13(self):
        r = T.vat_invoice_tax(100000, "13%")
        assert f(r["tax"]) == 13000.0
        assert f(r["gross"]) == 113000.0

    def test_invoice_inclusive_13(self):
        r = T.vat_invoice_tax(113000, "13%", inclusive=True)
        assert f(r["net"]) == 100000.0
        assert f(r["tax"]) == 13000.0

    def test_rate_9_6(self):
        assert f(T.vat_invoice_tax(100000, "9%")["tax"]) == 9000.0
        assert f(T.vat_invoice_tax(100000, "6%")["tax"]) == 6000.0

    def test_invalid_rate(self):
        with pytest.raises(T.TaxError):
            T.vat_invoice_tax(100, "7%")

    def test_small_scale_exempt_quarter(self):
        r = T.vat_small_scale(250000, quarterly=True)
        assert r["exempt"] is True
        assert f(r["tax"]) == 0.0

    def test_small_scale_reduced_1pct(self):
        r = T.vat_small_scale(350000, quarterly=True)
        assert f(r["tax"]) == 3500.0

    def test_small_scale_month_threshold(self):
        assert T.vat_small_scale(99999, quarterly=False)["exempt"] is True
        assert T.vat_small_scale(100001, quarterly=False)["exempt"] is False

    def test_general(self):
        r = T.vat_general([{"amount": 1000000, "rate": "13%"}],
                          [{"amount": 500000, "rate": "13%"}])
        assert f(r["out_tax"]) == 130000.0
        assert f(r["in_tax"]) == 65000.0
        assert f(r["payable"]) == 65000.0

    def test_general_carry(self):
        r = T.vat_general([{"amount": 100000, "rate": "13%"}],
                          [{"amount": 500000, "rate": "13%"}])
        assert f(r["payable"]) == 0.0
        assert f(r["carry_forward"]) == 52000.0


# ---------- 附加税费 ----------
class TestSurtax:
    def test_city_halved(self):
        r = T.surtaxes(100000, "市区", small_scale_or_small_profit=True)
        total = sum(float(i["amount"]) for i in r["items"])
        assert abs(total - 6000.0) < 0.01

    def test_city_full(self):
        r = T.surtaxes(100000, "市区", small_scale_or_small_profit=False)
        total = sum(float(i["amount"]) for i in r["items"])
        assert abs(total - 12000.0) < 0.01

    def test_county(self):
        r = T.surtaxes(100000, "县城/镇", small_scale_or_small_profit=False)
        total = sum(float(i["amount"]) for i in r["items"])
        assert abs(total - 10000.0) < 0.01


# ---------- 企业所得税 ----------
class TestCit:
    def test_small_profit(self):
        r = T.cit_annual(2800000, is_small_profit=True)
        assert f(r["tax"]) == 140000.0

    def test_standard(self):
        r = T.cit_annual(2800000)
        assert f(r["tax"]) == 700000.0

    def test_high_tech(self):
        r = T.cit_annual(2800000, rate=D("0.15"))
        assert f(r["tax"]) == 420000.0

    def test_loss_carry(self):
        r = T.cit_annual(1000000, loss_carry=400000)
        assert f(r["taxable"]) == 600000.0


# ---------- 个人所得税 ----------
class TestIit:
    def test_annual_200k(self):
        r = T.iit_annual(200000)
        assert f(r["tax"]) == 23080.0

    def test_annual_low(self):
        r = T.iit_annual(30000)
        assert f(r["tax"]) == 900.0

    def test_salary(self):
        r = T.iit_salary(360000, social_insurance=54000, special_deduct=24000)
        # 应纳税所得额 = 360000 - 60000 - 54000 - 24000 = 222000
        assert f(r["taxable"]) == 222000.0
        assert f(r["tax"]) == 27480.0

    def test_bonus_separate(self):
        r = T.iit_bonus(100000, mode="separate")
        assert f(r["tax"]) == 9790.0

    def test_best_bonus_returns_both(self):
        r = T.iit_best_bonus(100000, 0)
        assert "separate" in r and "merge" in r


# ---------- 印花税 / 房产税 / 土地使用税 ----------
class TestOther:
    def test_stamp_buy_sell(self):
        r = T.stamp_duty("买卖合同", 1000000)
        assert f(r["tax"]) == 300.0

    def test_stamp_loan(self):
        r = T.stamp_duty("借款合同", 1000000)
        assert f(r["tax"]) == 50.0

    def test_stamp_inclusive(self):
        r = T.stamp_duty("买卖合同", 1130000, vat_excluded=False, vat_rate="13%")
        assert f(r["tax"]) == 300.0

    def test_house_from_value(self):
        r = T.house_tax("从价", original_value=5000000, deduct_ratio=D("0.30"))
        assert f(r["tax"]) == 42000.0

    def test_house_from_rent(self):
        r = T.house_tax("从租", rent=100000)
        assert f(r["tax"]) == 12000.0

    def test_land(self):
        r = T.land_tax(1000, 3)
        assert f(r["tax"]) == 18000.0

    def test_land_custom_rate(self):
        r = T.land_tax(1000, 3, unit_rate=D("9"))
        assert f(r["tax"]) == 9000.0


# ---------- 风险与工具 ----------
class TestRiskTools:
    def test_three_flow_ok(self):
        r = T.three_flow_check({"amount": 100, "contract_amount": 100,
                                "paid_amount": 100, "seller_name": "A",
                                "contract_party": "A", "buyer_name": "B"})
        assert r["ok"] is True

    def test_three_flow_mismatch(self):
        r = T.three_flow_check({"amount": 900, "contract_amount": 700,
                                "seller_name": "A", "contract_party": "C",
                                "buyer_name": "B"})
        assert r["ok"] is False
        assert r["issues"]

    def test_risk_score(self):
        r = T.risk_score([{"weight": 35}, {"weight": 35}])
        assert r["score"] == 70
        assert r["grade"] == "高"

    def test_burden_alert(self):
        r = T.burden_alert(0.0128, 0.0285)
        assert r["alert"] is True

    def test_late_fee(self):
        r = T.late_fee(10000, 10)
        assert f(r["fee"]) == 50.0

    def test_due_date_vat(self):
        d = T.due_date("2026-10", "增值税")
        assert str(d).startswith("2026-11")

    def test_is_late(self):
        assert T.is_late("2026-10-15", "2026-10-20") is True
        assert T.is_late("2026-10-15", "2026-10-10") is False


# ---------- 校验 ----------
class TestValidate:
    def test_entity_ok(self):
        assert T.validate_entity({"code": "E99", "name": "测试主体",
                                  "tax_no": "91310115MA1K8X2N3P",
                                  "taxpayer_type": "一般纳税人"}) == []

    def test_entity_missing(self):
        errs = T.validate_entity({"code": "", "name": "", "tax_no": ""})
        assert len(errs) >= 2

    def test_declaration_missing(self):
        errs = T.validate_declaration({"entity": "", "tax_type": "", "period": ""})
        assert len(errs) >= 3


# ---------- 权限 ----------
class TestPerms:
    def test_wildcard(self):
        assert T.has_perm({"*"}, "anything") is True

    def test_exact(self):
        assert T.has_perm({"invoice.read"}, "invoice.read") is True
        assert T.has_perm({"invoice.read"}, "invoice.write") is False

    def test_role_exists(self):
        for role in ("admin", "manager", "finance", "tax_accountant",
                     "auditor", "reader"):
            assert role in T.ROLE_PERMS
