# -*- coding: utf-8 -*-
"""飞税税务管理系统 · 税计算内核

纯函数模块：不访问数据库、不做 IO，所有入参出参都是基本类型。
设计原则：
  1. 金额一律用 Decimal 计算，最后量化到分（ROUND_HALF_UP），避免浮点误差；
  2. 每个税种一个入口函数，返回结构化的明细（含中间量），便于前端逐步展示与核对；
  3. 政策参数集中在 POLICY / RATES 常量，随政策变更只改这里；
  4. 校验与预警独立成函数，不与计算耦合。

政策依据（截至 2026-10）：
  - 《中华人民共和国增值税法》（2026-01-01 施行）
  - 财政部 税务总局公告 2026 年第 10 号（起征点、3% 减按 1%）
  - 财政部 税务总局公告 2023 年第 12 号（小型微利企业、六税两费减半）
  - 《中华人民共和国企业所得税法》及实施条例
  - 《中华人民共和国个人所得税法》综合所得七级超额累进
  - 财政部 税务总局公告 2023 年第 30 号（全年一次性奖金单独计税，至 2027-12-31）
  - 《中华人民共和国印花税法》（2022-07-01 施行）税目税率表
  - 《中华人民共和国房产税暂行条例》（从价 1.2% / 从租 12%）
  - 《中华人民共和国城镇土地使用税暂行条例》（分级幅度税额）
"""
from decimal import Decimal, ROUND_HALF_UP

D = Decimal
CENT = D("0.01")


# ==================================================== 基础工具
def dec(x, default="0"):
    """安全转 Decimal：None/'' → default，非法值 → default。"""
    if x is None or x == "":
        return D(default)
    try:
        return D(str(x))
    except Exception:                                        # noqa: BLE001
        return D(default)


def money(x):
    """量化到分（四舍五入）。"""
    return D(x).quantize(CENT, rounding=ROUND_HALF_UP)


def rate(x):
    """量化到 6 位小数（税率）。"""
    return D(x).quantize(D("0.000001"), rounding=ROUND_HALF_UP)


def pct(x, digits=2):
    """比率转百分数，返回 Decimal。"""
    return (D(x) * 100).quantize(D("1." + "0" * digits), rounding=ROUND_HALF_UP)


class TaxError(Exception):
    """税务规则错误，服务层转 400。"""


# ==================================================== 政策常量
# 增值税税率（一般纳税人）
VAT_RATES = {
    "13%": D("0.13"),      # 货物、加工修理修配、有形动产租赁、进口
    "9%": D("0.09"),       # 交通运输、邮政、基础电信、建筑、不动产租赁与销售、农产品、自来水暖气
    "6%": D("0.06"),       # 现代服务、金融服务、生活服务、无形资产（除土地使用权）
    "0%": D("0"),          # 出口货物、跨境应税行为
    "3%": D("0.03"),       # 简易计税征收率（小规模纳税人法定征收率）
    "1%": D("0.01"),       # 小规模纳税人减按征收率（2026-2027）
}
# 法定税率（不含征收率），用于发票税率校验
VAT_STANDARD_RATES = ("13%", "9%", "6%", "0%")
VAT_LEVY_RATES_ALLOWED = ("3%", "1%")
# 简易计税征收率
VAT_LEVY_RATE = D("0.03")
# 小规模纳税人减按 1%（2026-01-01 ~ 2027-12-31，不含销售/出租不动产、转让土地使用权）
VAT_SMALL_REDUCED = D("0.01")
# 小规模纳税人起征点（月 / 季）
VAT_THRESHOLD_MONTH = D("100000")
VAT_THRESHOLD_QUARTER = D("300000")

# 附加税费
SURTAX = {
    "城建税": D("0.07"),        # 市区 7%；县城/镇 5%；其他 1%
    "教育费附加": D("0.03"),
    "地方教育附加": D("0.02"),
}
SURTAX_CITY_RATES = {"市区": D("0.07"), "县城/镇": D("0.05"), "其他": D("0.01")}

# 企业所得税
CIT_RATE = D("0.25")
CIT_HIGH_TECH = D("0.15")           # 高新技术企业
CIT_WEST = D("0.15")                # 西部大开发鼓励类
CIT_SMALL_PROFIT = D("0.05")        # 小型微利实际税负：25% × 20%
CIT_SMALL_LIMIT = {"profit": D("3000000"), "staff": 300, "assets": D("50000000")}
# 研发费用加计扣除比例（2023 起制造业/科技型中小企业 100%）
RD_SUPER_DEDUCT = D("1.00")

# 个人所得税综合所得（年度）七级超额累进
IIT_SALARY_THRESHOLD = D("60000")   # 综合所得年度基本减除费用
IIT_BRACKETS = [
    (D("36000"), D("0.03"), D("0")),
    (D("144000"), D("0.10"), D("2520")),
    (D("300000"), D("0.20"), D("16920")),
    (D("420000"), D("0.25"), D("31920")),
    (D("660000"), D("0.30"), D("52920")),
    (D("960000"), D("0.35"), D("85920")),
    (None, D("0.45"), D("181920")),
]
IIT_THRESHOLD_YEAR = D("60000")     # 基本减除费用 5000/月

# 全年一次性奖金按月换算表（单独计税）
IIT_BONUS_BRACKETS = [
    (D("3000"), D("0.03"), D("0")),
    (D("12000"), D("0.10"), D("210")),
    (D("25000"), D("0.20"), D("1410")),
    (D("35000"), D("0.25"), D("2660")),
    (D("55000"), D("0.30"), D("4410")),
    (D("80000"), D("0.35"), D("7160")),
    (None, D("0.45"), D("15160")),
]

# 印花税税目税率（万分比 / 千分比 折算成小数）
STAMP_DUTY = {
    "借款合同": D("0.00005"),
    "融资租赁合同": D("0.00005"),
    "买卖合同": D("0.0003"),
    "承揽合同": D("0.0003"),
    "建设工程合同": D("0.0003"),
    "运输合同": D("0.0003"),
    "技术合同": D("0.0003"),
    "租赁合同": D("0.001"),
    "保管合同": D("0.001"),
    "仓储合同": D("0.001"),
    "财产保险合同": D("0.001"),
    "土地使用权出让书据": D("0.0005"),
    "不动产转让书据": D("0.0005"),
    "股权转让书据": D("0.0005"),
    "知识产权转让书据": D("0.0003"),
    "营业账簿": D("0.00025"),
    "证券交易": D("0.001"),
}

# 房产税
HOUSE_TAX_FROM_VALUE = D("0.012")        # 从价计征 1.2%
HOUSE_TAX_FROM_RENT = D("0.12")          # 从租计征 12%
HOUSE_VALUE_DEDUCT = D("0.30")           # 从价计征减除比例（各省 10%~30%，缺省 30%）

# 城镇土地使用税分级年税额（元/㎡），各省在幅度内确定
LAND_TAX_GRADES = {1: D("30"), 2: D("24"), 3: D("18"),
                   4: D("12"), 5: D("6"), 6: D("1.5")}

# 六税两费减半：资源税（不含水资源）、城建税、房产税、城镇土地使用税、
# 印花税（不含证券交易）、耕地占用税、教育费附加、地方教育附加
SIX_TAX_TWO_FEE_HALF = ["城建税", "房产税", "城镇土地使用税", "印花税",
                        "耕地占用税", "教育费附加", "地方教育附加", "资源税"]


# ==================================================== 一、增值税
def vat_invoice_tax(amount, tax_rate, inclusive=False):
    """单张发票税额。inclusive=True 表示 amount 是含税额。

    返回 {net, tax, gross, rate}
    """
    r = VAT_RATES.get(str(tax_rate))
    if r is None:
        raise TaxError("未知增值税税率：%s" % tax_rate)
    a = dec(amount)
    if inclusive:
        gross = a
        net = (gross / (1 + r))
        tax = gross - net
    else:
        net = a
        tax = a * r
        gross = a + tax
    return {"net": money(net), "tax": money(tax), "gross": money(gross),
            "rate": str(tax_rate)}


def vat_small_scale(sales, quarterly=True, has_realestate=False, waive=False):
    """小规模纳税人增值税。

    规则（财政部 税务总局公告 2026 年第 10 号）：
      - 起征点：月 10 万 / 季 30 万，未达起征点免征；
      - 达起征点全额计税，除销售/出租不动产、转让土地使用权外，3% 减按 1%；
      - 销售/出租不动产、转让土地使用权仍按 3%；
      - 开专票可放弃免税。
    """
    s = dec(sales)
    thresh = VAT_THRESHOLD_QUARTER if quarterly else VAT_THRESHOLD_MONTH
    period = "季" if quarterly else "月"
    if waive:
        rate_ = VAT_SMALL_REDUCED if not has_realestate else VAT_LEVY_RATE
        tax = money(s * rate_)
        return {"sales": money(s), "threshold": money(thresh), "period": period,
                "exempt": False, "rate": str(rate_), "tax": tax,
                "note": "已放弃免税，按征收率计税"}
    if s < thresh:
        return {"sales": money(s), "threshold": money(thresh), "period": period,
                "exempt": True, "rate": "0", "tax": D("0.00"),
                "note": "未达起征点（%s销售额 %s 万），免征增值税" % (period, money(thresh / 10000))}
    rate_ = VAT_LEVY_RATE if has_realestate else VAT_SMALL_REDUCED
    tax = money(s * rate_)
    note = "达到起征点，全额计税"
    if not has_realestate:
        note += "（3% 减按 1%）"
    return {"sales": money(s), "threshold": money(thresh), "period": period,
            "exempt": False, "rate": str(rate_), "tax": tax, "note": note}


def vat_general(outputs, inputs, prior_credit=0, input_transfer_out=0,
                pre_paid=0, additional_deduct=0):
    """一般纳税人增值税一般计税。

    outputs: [{"rate":"13%","net":金额,"tax":税额}] 或 [{"amount":..,"rate":..,"inclusive":bool}]
    inputs:  进项税额合计（认证抵扣的专票 + 计算抵扣的农产品等）
    返回：销项、进项、上期留抵、本期留抵、应纳、附加税基数
    """
    detail = []
    out_tax = D("0")
    out_net = D("0")
    for it in outputs or []:
        amt = it.get("amount", it.get("net", 0))
        line = vat_invoice_tax(amt, it.get("rate", "13%"),
                              inclusive=bool(it.get("inclusive")))
        if it.get("tax") is not None and not it.get("amount"):
            # 直接给了税额
            line["tax"] = money(it.get("tax"))
            line["net"] = money(it.get("net", 0))
            line["gross"] = money(line["net"] + line["tax"])
        out_tax += line["tax"]
        out_net += line["net"]
        detail.append(line)

    # inputs 既支持合计数，也支持明细列表：[{"amount":..,"rate":..,"inclusive":bool}]
    if isinstance(inputs, (list, tuple)):
        in_tax = D("0")
        for it in inputs:
            if not isinstance(it, dict):
                in_tax += dec(it)
                continue
            if it.get("tax") is not None and not it.get("amount"):
                in_tax += dec(it.get("tax"))
                continue
            line = vat_invoice_tax(it.get("amount", it.get("net", 0)),
                                   it.get("rate", "13%"),
                                   inclusive=bool(it.get("inclusive")))
            in_tax += line["tax"]
    else:
        in_tax = dec(inputs)
    credit_in = dec(prior_credit)
    transfer = dec(input_transfer_out)
    add = dec(additional_deduct)          # 加计抵减（先进制造业 5%）
    prepaid = dec(pre_paid)

    deductible = in_tax + credit_in + add - transfer
    if deductible < 0:
        deductible = D("0")
    payable = out_tax - deductible
    carry = D("0")
    if payable < 0:
        carry = -payable
        payable = D("0")
    actual = payable - prepaid
    if actual < 0:
        actual = D("0")
    return {
        "out_tax": money(out_tax), "out_net": money(out_net),
        "in_tax": money(in_tax), "prior_credit": money(credit_in),
        "transfer_out": money(transfer), "additional": money(add),
        "deductible": money(deductible),
        "payable": money(payable), "carry_forward": money(carry),
        "pre_paid": money(prepaid), "actual": money(actual),
        "lines": detail,
    }


def surtaxes(vat_payable, city_type="市区", small_scale_or_small_profit=False,
             exempt_fund=False):
    """附加税费：城建税 + 教育费附加 + 地方教育附加。

    city_type: 市区 7% / 县城镇 5% / 其他 1%
    月销售额 ≤10 万（季 ≤30 万）免征教育费附加与地方教育附加
    六税两费减半：小规模纳税人、小型微利企业、个体工商户减半征收
    """
    base = dec(vat_payable)
    city_r = SURTAX_CITY_RATES.get(city_type, SURTAX["城建税"])
    items = []
    total = D("0")
    for name, r in (("城建税", city_r), ("教育费附加", SURTAX["教育费附加"]),
                    ("地方教育附加", SURTAX["地方教育附加"])):
        amount = base * r
        half = small_scale_or_small_profit and name in SIX_TAX_TWO_FEE_HALF
        if exempt_fund and name in ("教育费附加", "地方教育附加"):
            amount = D("0")
        if half:
            amount = amount / 2
        amount = money(amount)
        total += amount
        items.append({"name": name, "rate": str(rate(r)), "base": money(base),
                      "amount": amount, "halved": half})
    return {"items": items, "total": money(total), "base": money(base),
            "city_type": city_type}


# ==================================================== 二、企业所得税
def cit_quarterly(profit, rate=CIT_RATE, prior_paid=0, is_small_profit=False,
                  rd_expense=0, super_deduct=RD_SUPER_DEDUCT):
    """企业所得税季度预缴。

    小型微利：应纳税所得额 ≤300 万 → 减按 25% 计入 × 20% = 实际 5%
    研发费用加计扣除在预缴时也可享受（按实际发生额 × 加计比例）
    """
    p = dec(profit)
    rd = dec(rd_expense)
    extra = rd * dec(super_deduct)
    taxable = p - extra
    if taxable < 0:
        taxable = D("0")
    if is_small_profit:
        eff = CIT_SMALL_PROFIT
        tax = money(taxable * eff)
        note = "小型微利企业：减按 25% 计入应纳税所得额，按 20% 税率（实际 5%）"
    else:
        eff = dec(rate)
        tax = money(taxable * eff)
        note = "法定税率 %s" % (pct(eff))
    paid = dec(prior_paid)
    should = tax - paid
    if should < 0:
        should = D("0")
    return {"profit": money(p), "rd_expense": money(rd), "rd_extra": money(extra),
            "taxable": money(taxable), "rate": str(ratef(eff)), "tax": money(tax),
            "prior_paid": money(paid), "should_pay": money(should), "note": note}


def ratef(x):
    return D(x).quantize(D("0.0001"), rounding=ROUND_HALF_UP)


def cit_annual(profit, rate=CIT_RATE, adjust_add=0, adjust_less=0,
               prior_paid=0, is_small_profit=False, rd_expense=0,
               super_deduct=RD_SUPER_DEDUCT, loss_carry=0):
    """企业所得税年度汇算清缴。

    taxable = 利润总额 + 纳税调增 - 纳税调减 - 弥补以前年度亏损 - 研发加计
    """
    p = dec(profit)
    add = dec(adjust_add)
    less = dec(adjust_less)
    loss = dec(loss_carry)
    rd = dec(rd_expense)
    extra = rd * dec(super_deduct)
    taxable = p + add - less - loss - extra
    if taxable < 0:
        taxable = D("0")

    # 小型微利判定：三项同时满足
    small_ok = is_small_profit and taxable <= CIT_SMALL_LIMIT["profit"]
    if small_ok:
        eff = CIT_SMALL_PROFIT
        tax = money(taxable * eff)
        note = "小型微利企业优惠（实际税负 5%）"
    else:
        eff = dec(rate)
        tax = money(taxable * eff)
        note = "法定税率 %s" % (pct(eff))
    paid = dec(prior_paid)
    diff = tax - paid
    return {"profit": money(p), "adjust_add": money(add), "adjust_less": money(less),
            "loss_carry": money(loss), "rd_expense": money(rd), "rd_extra": money(extra),
            "taxable": money(taxable), "rate": str(ratef(eff)), "tax": money(tax),
            "prior_paid": money(paid), "diff": money(diff),
            "refund": money(-diff) if diff < 0 else D("0.00"),
            "should_pay": money(diff) if diff > 0 else D("0.00"),
            "small_profit": bool(small_ok), "note": note}


# ==================================================== 三、个人所得税
def iit_annual(taxable_income):
    """综合所得年度应纳税额（七级超额累进）。"""
    t = dec(taxable_income)
    if t <= 0:
        return {"taxable": D("0.00"), "rate": "0", "quick": D("0.00"),
                "tax": D("0.00"), "level": 0}
    prev = D("0")
    for idx, (cap, r, q) in enumerate(IIT_BRACKETS, 1):
        if cap is None or t <= cap:
            tax = money(t * r - q)
            if tax < 0:
                tax = D("0.00")
            return {"taxable": money(t), "rate": str(ratef(r)), "quick": money(q),
                    "tax": tax, "level": idx}
        prev = cap
    return {"taxable": money(t), "rate": "0.45", "quick": money(IIT_BRACKETS[-1][2]),
            "tax": money(t * IIT_BRACKETS[-1][1] - IIT_BRACKETS[-1][2]), "level": 7}


def iit_salary(gross_year, social_insurance=0, special_deduct=0,
               other_deduct=0, threshold=IIT_THRESHOLD_YEAR):
    """工资薪金综合所得个人所得税（年度口径）。

    gross_year: 全年工资薪金收入
    social_insurance: 全年三险一金个人部分
    special_deduct: 全年专项附加扣除（子女教育/房贷/赡养老人等）
    other_deduct: 其他扣除（年金/商业健康险/公益捐赠等）
    """
    g = dec(gross_year)
    si = dec(social_insurance)
    sp = dec(special_deduct)
    ot = dec(other_deduct)
    th = dec(threshold)
    taxable = g - si - sp - ot - th
    if taxable < 0:
        taxable = D("0")
    r = iit_annual(taxable)
    return {"gross": money(g), "social_insurance": money(si),
            "special_deduct": money(sp), "other_deduct": money(ot),
            "threshold": money(th), "taxable": money(taxable),
            "level": r["level"], "rate": r["rate"], "quick": r["quick"],
            "tax": r["tax"], "net": money(g - si - r["tax"])}


def iit_bonus(bonus, mode="separate", salary_taxable=0):
    """全年一次性奖金。

    mode="separate"：单独计税，奖金/12 查按月换算表
    mode="merge"：并入综合所得
    """
    b = dec(bonus)
    if mode == "merge":
        base = dec(salary_taxable) + b
        r = iit_annual(base)
        return {"mode": "merge", "bonus": money(b), "tax": r["tax"],
                "rate": r["rate"], "note": "并入综合所得一并计税"}
    monthly = b / 12
    for cap, r_, q in IIT_BONUS_BRACKETS:
        if cap is None or monthly <= cap:
            tax = money(b * r_ - q)
            if tax < 0:
                tax = D("0.00")
            return {"mode": "separate", "bonus": money(b),
                    "monthly_avg": money(monthly), "rate": str(ratef(r_)),
                    "quick": money(q), "tax": tax,
                    "note": "单独计税：奖金÷12=%s 适用 %s" % (money(monthly), pct(r_))}
    return {"mode": "separate", "bonus": money(b), "tax": D("0.00")}


def iit_best_bonus(bonus, salary_taxable=0):
    """对比单独计税与并入综合所得，返回更优方案。"""
    a = iit_bonus(bonus, "separate")
    b = iit_bonus(bonus, "merge", salary_taxable)
    better = "separate" if a["tax"] <= b["tax"] else "merge"
    saved = abs(a["tax"] - b["tax"])
    return {"separate": a, "merge": b, "better": better,
            "saved": money(saved)}


# ==================================================== 四、印花税
def stamp_duty(contract_type, amount, vat_excluded=True, vat_rate="13%"):
    """印花税。

    vat_excluded=True 表示 amount 已不含增值税（税法要求按不含税金额计税）；
    否则先按 vat_rate 剥离增值税。
    营业账簿按实收资本+资本公积合计金额，只对增加部分计税。
    """
    t = str(contract_type).strip()
    if t not in STAMP_DUTY:
        raise TaxError("未知印花税税目：%s" % t)
    a = dec(amount)
    if not vat_excluded and t != "营业账簿":
        r = VAT_RATES.get(str(vat_rate), D("0"))
        a = a / (1 + r)
    tax = money(a * STAMP_DUTY[t])
    if tax < D("0.01"):
        tax = D("0.01")     # 应纳税额不足一角的按一角计（实务口径）
    return {"type": t, "base": money(a), "rate": str(STAMP_DUTY[t]),
            "tax": tax, "vat_excluded": bool(vat_excluded),
            "note": "按不含税金额计税" if vat_excluded else "已剥离增值税"}


def stamp_duty_batch(items):
    """批量计税，按税目汇总。"""
    total = D("0")
    detail = []
    for it in items or []:
        line = stamp_duty(it.get("type"), it.get("amount", 0),
                         it.get("vat_excluded", True),
                         it.get("vat_rate", "13%"))
        total += line["tax"]
        detail.append(line)
    by_type = {}
    for it in detail:
        by_type[it["type"]] = by_type.get(it["type"], D("0")) + it["tax"]
    return {"items": detail, "total": money(total),
            "by_type": [{"type": k, "tax": money(v)} for k, v in by_type.items()]}


# ==================================================== 五、房产税与土地使用税
def house_tax(mode="从价", original_value=0, rent=0, deduct_ratio=HOUSE_VALUE_DEDUCT):
    """房产税。从价：余值 × 1.2%；从租：租金 × 12%。"""
    if mode == "从价":
        ov = dec(original_value)
        dr = dec(deduct_ratio)
        residual = ov * (1 - dr)
        tax = money(residual * HOUSE_TAX_FROM_VALUE)
        return {"mode": "从价", "original_value": money(ov), "deduct_ratio": str(dr),
                "residual": money(residual), "rate": "0.012", "tax": tax,
                "note": "房产原值减除 %s%% 后的余值 × 1.2%%" % pct(dr, 0)}
    r = dec(rent)
    tax = money(r * HOUSE_TAX_FROM_RENT)
    return {"mode": "从租", "rent": money(r), "rate": "0.12", "tax": tax,
            "note": "租金收入 × 12%（个人出租住房减按 4%）"}


def land_tax(area, grade=3, unit_rate=None):
    """城镇土地使用税：实际占用面积 × 单位税额（元/㎡·年）。"""
    a = dec(area)
    r = dec(unit_rate) if unit_rate not in (None, "") else LAND_TAX_GRADES.get(int(grade), D("18"))
    tax = money(a * r)
    return {"area": money(a), "grade": int(grade), "unit_rate": str(r),
            "tax": tax, "note": "%s 元/㎡·年 × %s ㎡" % (r, money(a))}


# ==================================================== 六、综合申报汇总
def tax_burden(tax_total, revenue):
    """税负率 = 税额 / 营业收入。"""
    r = dec(revenue)
    if r == 0:
        return {"tax": money(tax_total), "revenue": D("0.00"), "burden": "0",
                "burden_pct": D("0.00")}
    b = dec(tax_total) / r
    return {"tax": money(tax_total), "revenue": money(r),
            "burden": str(ratef(b)), "burden_pct": pct(b)}


def full_tax_burden(revenue, vat_payable=0, surtax=0, cit=0, stamp=0,
                    house=0, land=0, iit=0, other=0):
    """企业综合税负测算。"""
    items = [
        ("增值税", dec(vat_payable)),
        ("附加税费", dec(surtax)),
        ("企业所得税", dec(cit)),
        ("印花税", dec(stamp)),
        ("房产税", dec(house)),
        ("城镇土地使用税", dec(land)),
        ("个人所得税（代扣）", dec(iit)),
        ("其他税费", dec(other)),
    ]
    total = sum((v for _, v in items), D("0"))
    rev = dec(revenue)
    by = [{"name": k, "amount": money(v),
           "share": str(ratef(v / total)) if total else "0"} for k, v in items]
    return {"items": by, "total": money(total), "revenue": money(rev),
            "burden": str(ratef(total / rev)) if rev else "0",
            "burden_pct": pct(total / rev) if rev else D("0.00")}


# ==================================================== 七、三流一致校验
def three_flow_check(invoice):
    """三流一致：合同流（合同金额=发票金额）、资金流（付款额=发票额）、
    发票流（发票信息与合同主体一致）。返回问题清单。"""
    issues = []
    inv_amt = dec(invoice.get("amount"))
    contract_amt = dec(invoice.get("contract_amount"))
    paid = dec(invoice.get("paid_amount"))
    if contract_amt and abs(inv_amt - contract_amt) > D("0.01"):
        issues.append({
            "level": "险",
            "code": "CONTRACT_MISMATCH",
            "message": "发票金额 %s 与合同金额 %s 不一致" % (money(inv_amt), money(contract_amt)),
        })
    if paid and abs(paid - inv_amt) > D("0.01"):
        issues.append({
            "level": "警",
            "code": "PAYMENT_MISMATCH",
            "message": "付款金额 %s 与发票金额 %s 不一致（差额 %s）"
                       % (money(paid), money(inv_amt), money(inv_amt - paid)),
        })
    seller = (invoice.get("seller_name") or "").strip()
    contract_party = (invoice.get("contract_party") or "").strip()
    if seller and contract_party and seller != contract_party:
        issues.append({
            "level": "险",
            "code": "PARTY_MISMATCH",
            "message": "开票方「%s」与合同相对方「%s」不一致" % (seller, contract_party),
        })
    buyer = (invoice.get("buyer_name") or "").strip()
    entity = (invoice.get("entity_name") or "").strip()
    if buyer and entity and buyer not in entity and entity not in buyer:
        issues.append({
            "level": "险",
            "code": "BUYER_MISMATCH",
            "message": "购买方「%s」与纳税主体「%s」不一致" % (buyer, entity),
        })
    return {"ok": not issues, "issues": issues}


# ==================================================== 八、风险预警
def risk_score(signals):
    """风险打分：每条信号带权重，汇总得 0~100 分与等级。

    signals: [{"code":..,"level":"险"/"警"/"提","message":..,"weight":n}]
    等级：≥70 高 / ≥40 中 / >0 低 / 0 无
    """
    total = D("0")
    for s in signals or []:
        try:
            total += dec(s.get("weight", 10))
        except Exception:                                    # noqa: BLE001
            total += D("10")
    if total > 100:
        total = D("100")
    score = int(total)
    if score >= 70:
        grade = "高"
    elif score >= 40:
        grade = "中"
    elif score > 0:
        grade = "低"
    else:
        grade = "无"
    return {"score": score, "grade": grade, "count": len(signals or [])}


def burden_alert(burden_rate, industry_avg, tolerance=D("0.30")):
    """税负率偏离预警：与行业均值偏离超过容差即预警。"""
    b = dec(burden_rate)
    avg = dec(industry_avg)
    if avg == 0:
        return {"alert": False, "deviation": "0", "message": "无行业基准"}
    dev = (b - avg) / avg
    alert = abs(dev) > dec(tolerance)
    if not alert:
        msg = "税负率 %s%%，与行业均值 %s%% 基本持平" % (pct(b), pct(avg))
    elif dev < 0:
        msg = "税负率 %s%% 低于行业均值 %s%% 达 %s%%，关注少计销项/多抵进项风险" % (
            pct(b), pct(avg), pct(-dev))
    else:
        msg = "税负率 %s%% 高于行业均值 %s%% 达 %s%%，关注多缴或未享受优惠" % (
            pct(b), pct(avg), pct(dev))
    return {"alert": alert, "deviation": str(ratef(dev)),
            "deviation_pct": pct(dev), "industry_avg": str(ratef(avg)),
            "message": msg}


def invoice_risk(invoice, today=None):
    """单张发票风险检查：抬头、税号、金额、税率、作废重开。"""
    out = []
    if not (invoice.get("buyer_tax_no") or "").strip():
        out.append({"code": "NO_TAX_NO", "level": "警",
                    "message": "购买方纳税人识别号为空，不得作为抵扣凭证",
                    "weight": 20})
    r = str(invoice.get("rate") or "")
    if r not in VAT_RATES:
        out.append({"code": "BAD_RATE", "level": "险",
                    "message": "税率「%s」不在法定税率范围" % r, "weight": 30})
    elif r in VAT_LEVY_RATES_ALLOWED and str(invoice.get("invoice_type") or "").find("专用") >= 0 \
            and invoice.get("kind") == "销项":
        # 小规模开专票按征收率可以，仅提示
        out.append({"code": "LEVY_RATE", "level": "提",
                    "message": "发票按征收率 %s 开具，注意与纳税人类型匹配" % r, "weight": 5})
    if dec(invoice.get("amount")) <= 0:
        out.append({"code": "ZERO_AMOUNT", "level": "警",
                    "message": "发票金额为 0 或负数", "weight": 20})
    if str(invoice.get("status") or "") == "作废":
        out.append({"code": "VOIDED", "level": "提",
                    "message": "发票已作废，不得抵扣", "weight": 10})
    if dec(invoice.get("tax")) > dec(invoice.get("amount")) * D("0.13") + D("0.01"):
        out.append({"code": "TAX_TOO_HIGH", "level": "险",
                    "message": "税额超过金额的 13%，疑为虚开", "weight": 40})
    return out


# ==================================================== 九、申报期限
def due_date(period, tax_type):
    """申报期限（简化：次月 15 日内；遇节假日顺延在服务层按工作日表处理）。"""
    import datetime as _dt
    try:
        y, m = [int(x) for x in str(period).split("-")[:2]]
    except Exception:                                        # noqa: BLE001
        raise TaxError("申报期格式应为 YYYY-MM")
    if tax_type in ("企业所得税", "经营所得个人所得税"):
        # 季度预缴：季度终了 15 日内
        q = (m - 1) // 3 + 1
        end_m = q * 3
        ny, nm = (y, end_m + 1) if end_m < 12 else (y + 1, end_m - 11)
        return "%04d-%02d-15" % (ny, nm)
    ny, nm = (y, m + 1) if m < 12 else (y + 1, 1)
    return "%04d-%02d-15" % (ny, nm)


def is_late(due, paid_date):
    """是否逾期。日期字符串比较即可（ISO 格式）。"""
    if not due or not paid_date:
        return False
    return str(paid_date)[:10] > str(due)[:10]


def late_fee(tax_amount, days, rate_per_day=D("0.0005")):
    """滞纳金：按日加收万分之五（税收征管法第 32 条）。"""
    rate_per_day = dec(rate_per_day, "0.0005") or D("0.0005")
    days = int(days or 0)
    if days <= 0:
        return {"days": 0, "fee": D("0.00"), "rate": str(rate_per_day)}
    fee = money(dec(tax_amount) * rate_per_day * D(days))
    return {"days": int(days), "fee": fee, "rate": str(rate_per_day),
            "note": "自滞纳税款之日起按日加收万分之五"}


# ==================================================== 十、规则默认值
DEFAULT_RULES = {
    "city_type": "市区",
    "surtax_halve": "1",                # 六税两费减半 1 开 0 关
    "fund_exempt_sales": "100000",      # 教育费附加免征月销售额门槛
    "burden_tolerance": "0.30",         # 税负率偏离容差
    "invoice_amount_limit": "10000000",  # 单张发票金额上限（超限提示）
    "late_fee_rate": "0.0005",
    "declare_warn_days": "3",            # 申报到期前 N 天提醒
}

ROLE_PERMS = {
    "admin": {"*"},
    "manager": {"tax.read", "tax.declare", "invoice.read", "invoice.write",
                "input.read", "input.verify", "entity.read", "voucher.read",
                "report.read", "risk.read", "policy.read"},
    "tax_accountant": {"tax.read", "tax.declare", "tax.calc",
                       "invoice.read", "invoice.write", "invoice.void",
                       "input.read", "input.verify", "input.transfer",
                       "entity.read", "voucher.read", "voucher.write",
                       "report.read", "risk.read", "policy.read"},
    "finance": {"tax.read", "invoice.read", "invoice.write", "input.read",
                "input.verify", "entity.read", "voucher.read", "report.read",
                "risk.read", "policy.read"},
    "auditor": {"tax.read", "invoice.read", "input.read", "entity.read",
                "voucher.read", "report.read", "risk.read", "policy.read"},
    "reader": {"tax.read", "invoice.read", "report.read", "policy.read"},
}


def has_perm(perms, need):
    """权限通配：* / 前缀 flow.* / 后缀 *.read"""
    if not need:
        return True
    for p in perms or []:
        if p == "*" or p == need:
            return True
        if p.endswith(".*") and need.startswith(p[:-1]):
            return True
        if p.startswith("*.") and need.endswith(p[1:]):
            return True
    return False


def validate_entity(entity):
    """纳税主体必填校验。"""
    errs = []
    if not (entity.get("name") or "").strip():
        errs.append("主体名称必填")
    tax_no = (entity.get("tax_no") or "").strip().upper()
    if not tax_no:
        errs.append("纳税人识别号必填")
    elif len(tax_no) not in (15, 17, 18, 20):
        errs.append("纳税人识别号长度应为 15/17/18/20 位")
    if (entity.get("taxpayer_type") or "") not in ("一般纳税人", "小规模纳税人"):
        errs.append("纳税人类型应为 一般纳税人 或 小规模纳税人")
    return errs


def validate_declaration(decl):
    """申报单校验。"""
    errs = []
    if not (decl.get("entity") or "").strip():
        errs.append("纳税主体必填")
    if not (decl.get("tax_type") or "").strip():
        errs.append("税种必填")
    period = (decl.get("period") or "").strip()
    if not period:
        errs.append("所属期必填")
    elif len(period) != 7 or period[4] != "-":
        errs.append("所属期格式应为 YYYY-MM")
    return errs
