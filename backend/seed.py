# -*- coding: utf-8 -*-
"""飞税税务管理系统 · 种子数据

覆盖 8 家纳税主体（一般纳税人 / 小规模 / 高新 / 小微），
12 用户 6 角色，2026-07 ~ 2026-10 四个月发票、申报单、凭证、
合同、风险信号、政策库。
"""
import hashlib
import random
import time
from decimal import Decimal as D

import db
import tax as T

random.seed(20261023)


def _sha(s):
    return hashlib.sha256(str(s).encode()).hexdigest()


def _dt(day_offset, h=9, m=0):
    """相对今天的日期时间。"""
    t = time.time() + day_offset * 86400
    st = time.localtime(t)
    return time.strftime("%Y-%m-%d", st) + " %02d:%02d:00" % (h, m)


def _d(day_offset):
    t = time.time() + day_offset * 86400
    return time.strftime("%Y-%m-%d", time.localtime(t))


PERIODS = ["2026-07", "2026-08", "2026-09", "2026-10"]

DEPTS = [
    ("D100", "集团总部", "", "zhangwei", 1, "战略、投资、合并报表"),
    ("D200", "财务中心", "D100", "wangfang", 2, "核算、税务、资金"),
    ("D210", "税务部", "D200", "liyan", 3, "纳税申报与税务筹划"),
    ("D220", "资金部", "D200", "zhaolei", 3, "收付款与融资"),
    ("D300", "商务中心", "D100", "sunhao", 2, "销售与采购"),
    ("D400", "技术中心", "D100", "chenjing", 2, "研发与信息化"),
    ("D500", "制造中心", "D100", "wuting", 2, "生产与仓储"),
    ("D600", "综合管理部", "D100", "zhoumin", 2, "人力、行政、法务"),
]

USERS = [
    ("admin", "系统管理员", "D100", "系统管理员", "admin", "13800000001", "admin@feishui.cn", "tax@2026"),
    ("zhangwei", "张伟", "D100", "财务总监", "manager", "13800000002", "zhangwei@feishui.cn", "123456"),
    ("wangfang", "王芳", "D200", "财务经理", "finance", "13800000003", "wangfang@feishui.cn", "123456"),
    ("liyan", "李燕", "D210", "税务主管", "tax_accountant", "13800000004", "liyan@feishui.cn", "123456"),
    ("zhaolei", "赵磊", "D220", "资金主管", "finance", "13800000005", "zhaolei@feishui.cn", "123456"),
    ("sunhao", "孙浩", "D300", "商务经理", "manager", "13800000006", "sunhao@feishui.cn", "123456"),
    ("chenjing", "陈静", "D400", "研发经理", "manager", "13800000007", "chenjing@feishui.cn", "123456"),
    ("wuting", "吴婷", "D500", "制造经理", "manager", "13800000008", "wuting@feishui.cn", "123456"),
    ("zhoumin", "周敏", "D600", "行政主管", "manager", "13800000009", "zhoumin@feishui.cn", "123456"),
    ("liuyang", "刘洋", "D210", "税务会计", "tax_accountant", "13800000010", "liuyang@feishui.cn", "123456"),
    ("xumei", "徐梅", "D200", "总账会计", "finance", "13800000011", "xumei@feishui.cn", "123456"),
    ("hejun", "何俊", "D100", "内审专员", "auditor", "13800000012", "hejun@feishui.cn", "123456"),
    ("reader01", "宋洁", "D200", "报表使用者", "reader", "13800000013", "reader01@feishui.cn", "123456"),
]

ENTITIES = [
    # code, name, tax_no, type, industry, city, region, legal, capital, staff, assets, small, hightech
    ("E01", "飞税科技集团有限公司", "91310115MA1K8X2N3P", "一般纳税人", "软件和信息技术服务",
     "市区", "东部", "张伟", 50000000, 286, 48000000, 0, 1),
    ("E02", "飞税智能制造有限公司", "91320500MA1MT4R7Q8", "一般纳税人", "通用设备制造",
     "市区", "东部", "吴婷", 30000000, 412, 62000000, 0, 0),
    ("E03", "飞税商贸（上海）有限公司", "91310104MA1FR9K2L6", "一般纳税人", "批发零售",
     "市区", "东部", "孙浩", 10000000, 68, 22000000, 0, 0),
    ("E04", "飞税建筑安装工程有限公司", "91330106MA2A8Y5W4X", "一般纳税人", "建筑安装",
     "县城/镇", "东部", "赵磊", 20000000, 156, 31000000, 0, 0),
    ("E05", "飞税咨询服务有限公司", "91440300MA5F7J3H9D", "小规模纳税人", "商务服务",
     "市区", "东部", "周敏", 2000000, 18, 3600000, 1, 0),
    ("E06", "飞税文化传媒有限公司", "91510107MA6C2B8V1N", "小规模纳税人", "文化传媒",
     "市区", "西部", "陈静", 1000000, 12, 1800000, 1, 0),
    ("E07", "飞税供应链管理有限公司", "91420100MA4L9T6P2K", "一般纳税人", "物流仓储",
     "其他", "中部", "王芳", 8000000, 92, 15000000, 0, 0),
    ("E08", "飞税新能源科技有限公司", "91610131MA7W5R9D3F", "一般纳税人", "新能源设备",
     "市区", "西部", "李燕", 25000000, 178, 39000000, 0, 1),
]

TAX_TYPES = [
    ("VAT", "增值税", "流转税", "月", 0, "13% / 9% / 6% / 0%；简易 3%"),
    ("SUR", "附加税费", "流转税附加", "月", 0, "城建 7% + 教育 3% + 地方教育 2%"),
    ("CIT", "企业所得税", "所得税", "季", 0, "25%；小微实际 5%；高新 15%"),
    ("IIT", "个人所得税", "所得税", "月", 0, "综合所得 3%~45% 七级累进"),
    ("SD", "印花税", "财产行为税", "月", 0, "5 档比例税率，万分之零点五~千分之一"),
    ("HT", "房产税", "财产行为税", "半年", 1, "从价 1.2% / 从租 12%"),
    ("LT", "城镇土地使用税", "财产行为税", "半年", 1, "分级 1.5~30 元/㎡·年"),
    ("DT", "城市维护建设税", "流转税附加", "月", 0, "市区 7% / 县镇 5% / 其他 1%"),
]

SUPPLIERS = [
    ("上海华虹电子有限公司", "91310115000011111X"),
    ("苏州精密机械制造有限公司", "91320500000022222Y"),
    ("杭州通达物流有限公司", "91330106000033333Z"),
    ("深圳前海数据科技有限公司", "91440300000044444A"),
    ("北京中科软件技术有限公司", "91110108000055555B"),
    ("宁波众诚包装材料厂", "91330200000066666C"),
]

CUSTOMERS = [
    ("广州盛世贸易有限公司", "91440101000077777D"),
    ("成都联创电子科技有限公司", "91510107000088888E"),
    ("武汉智能制造股份有限公司", "91420100000099999F"),
    ("南京易通信息技术有限公司", "91320100000111111G"),
    ("西安新能源装备有限公司", "91610131000122222H"),
]


def seed():
    db.init()
    if (db.val("SELECT COUNT(*) FROM users", (), 0) or 0) > 0:
        return 0
    conn_ts = db.now()

    for code, name, parent, leader, sort, memo in DEPTS:
        db.insert("depts", {"code": code, "name": name, "parent": parent,
                            "leader": leader, "sort": sort, "memo": memo})

    for un, nm, dp, title, role, ph, em, pwd in USERS:
        db.insert("users", {"username": un, "name": nm, "dept": dp, "title": title,
                            "role": role, "phone": ph, "email": em,
                            "pwd": _sha(pwd), "status": "启用", "created_at": conn_ts})

    for t in TAX_TYPES:
        db.insert("tax_types", {"code": t[0], "name": t[1], "category": t[2],
                                "period_rule": t[3], "shared": t[4],
                                "rate_desc": t[5], "sort": TAX_TYPES.index(t) + 1})

    for e in ENTITIES:
        code, name, tax_no, tp, ind, city, region, legal, cap, staff, assets, small, ht = e
        db.insert("entities", {
            "code": code, "name": name, "tax_no": tax_no, "taxpayer_type": tp,
            "industry": ind, "city_type": city, "region": region,
            "legal_person": legal, "contact": legal, "phone": "021-6%07d" % random.randint(0, 9999999),
            "reg_address": "上海市浦东新区张江路 %d 号" % random.randint(100, 999),
            "reg_capital": cap, "staff_count": staff, "asset_total": assets,
            "small_profit": small, "high_tech": ht, "status": "启用",
            "created_at": "2024-03-01 09:00:00",
        })

    for k, v in T.DEFAULT_RULES.items():
        db.set_rule(k, v)

    # ---------------- 发票
    _seed_invoices()
    # ---------------- 申报单
    _seed_declarations()
    # ---------------- 凭证
    _seed_vouchers()
    # ---------------- 合同
    _seed_contracts()
    # ---------------- 风险信号
    _seed_risks()
    # ---------------- 政策库
    _seed_policies()
    # ---------------- 公告
    for title, body, top in [
        ("2026 年 10 月申报期提醒", "10 月申报期为 10 月 1 日至 10 月 26 日（因国庆顺延）。"
                                 "请各主体于 10 月 20 日前完成增值税、附加税费、个税申报。", 1),
        ("增值税法施行后申报口径调整", "自 2026 年 1 月 1 日起《增值税法》施行，小规模纳税人取消 5% 征收率，"
                                 "原 5% 应税行为填入 3% 相关栏次；3% 减按 1% 政策延续至 2027 年底。", 1),
        ("小型微利企业所得税优惠延续", "对小型微利企业减按 25% 计算应纳税所得额、按 20% 税率缴纳企业所得税，"
                                "实际税负 5%，执行至 2027 年 12 月 31 日。", 0),
        ("研发费用加计扣除 100% 口径说明", "制造业企业、科技型中小企业研发费用未形成无形资产的，按实际发生额 100% 加计扣除；"
                                  "形成无形资产的按成本 200% 摊销。", 0),
    ]:
        db.insert("notices", {"title": title, "body": body, "author": "系统",
                              "top": top, "created_at": _dt(-random.randint(1, 20))})

    db.bumpsync("entities", "invoices", "declarations", "vouchers", "contracts",
                "risks", "policies")
    return 1


def _seed_invoices():
    """每个主体每月 6~10 张销项 + 5~9 张进项。"""
    n = 0
    for e in ENTITIES:
        code, name, tax_no, tp, ind = e[0], e[1], e[2], e[3], e[4]
        for p in PERIODS:
            is_small = tp == "小规模纳税人"
            # 销项
            cnt = random.randint(4, 7) if is_small else random.randint(6, 9)
            for _ in range(cnt):
                cust, cust_no = random.choice(CUSTOMERS)
                if ind == "软件和信息技术服务":
                    r = "6%"
                elif ind in ("建筑安装", "物流仓储"):
                    r = "9%"
                elif is_small:
                    r = "3%"
                else:
                    r = "13%"
                amt = round(random.uniform(20000, 380000), 2)
                line = T.vat_invoice_tax(amt, r, inclusive=False)
                day = "%s-%02d" % (p, random.randint(1, 28))
                inv_no = db.gen_no("invoices", "XX")
                db.insert("invoices", {
                    "no": inv_no, "kind": "销项", "code": "0%d" % random.randint(1000, 9999),
                    "number": "%08d" % random.randint(1, 99999999),
                    "invoice_type": "增值税专用发票" if not is_small else "增值税普通发票",
                    "entity": code, "seller_name": name, "seller_tax_no": tax_no,
                    "buyer_name": cust, "buyer_tax_no": cust_no,
                    "amount": float(line["net"]), "tax_rate": r, "tax": float(line["tax"]),
                    "total": float(line["gross"]), "biz_date": day, "period": p,
                    "status": "正常", "verify_status": "-", "category": "销售货物" if r == "13%" else "提供服务",
                    "contract_no": "", "remark": "", "created_by": "liuyang",
                    "created_at": day + " 10:30:00",
                })
                db.insert("invoice_items", {
                    "invoice": inv_no, "goods": "产品/服务 A", "spec": "标准",
                    "unit": "批", "qty": 1, "price": float(line["net"]),
                    "amount": float(line["net"]), "tax_rate": r, "tax": float(line["tax"]),
                })
                n += 1
            # 进项
            cnt = random.randint(3, 5) if is_small else random.randint(5, 8)
            for _ in range(cnt):
                sup, sup_no = random.choice(SUPPLIERS)
                r = random.choice(["13%", "13%", "9%", "6%"])
                amt = round(random.uniform(15000, 250000), 2)
                line = T.vat_invoice_tax(amt, r, inclusive=False)
                day = "%s-%02d" % (p, random.randint(1, 28))
                inv_no = db.gen_no("invoices", "XX")
                verified = random.random() > 0.15
                db.insert("invoices", {
                    "no": inv_no, "kind": "进项", "code": "0%d" % random.randint(1000, 9999),
                    "number": "%08d" % random.randint(1, 99999999),
                    "invoice_type": "增值税专用发票",
                    "entity": code, "seller_name": sup, "seller_tax_no": sup_no,
                    "buyer_name": name, "buyer_tax_no": tax_no,
                    "amount": float(line["net"]), "tax_rate": r, "tax": float(line["tax"]),
                    "total": float(line["gross"]), "biz_date": day, "period": p,
                    "status": "正常",
                    "verify_status": "已认证" if verified and not is_small else "未认证",
                    "category": "采购货物", "contract_no": "",
                    "remark": "", "created_by": "liuyang", "created_at": day + " 14:20:00",
                })
                n += 1
    # 少量异常发票用于风险演示
    db.insert("invoices", {
        "no": db.gen_no("invoices", "XX"), "kind": "进项", "code": "044001", "number": "90000001",
        "invoice_type": "增值税专用发票", "entity": "E02",
        "seller_name": "某商贸有限公司", "seller_tax_no": "",
        "buyer_name": "飞税智能制造有限公司", "buyer_tax_no": "91320500MA1MT4R7Q8",
        "amount": 800000.0, "tax_rate": "13%", "tax": 104000.0, "total": 904000.0,
        "biz_date": "2026-09-18", "period": "2026-09", "status": "正常",
        "verify_status": "未认证", "category": "采购货物",
        "contract_no": "HT0007", "contract_amount": 700000.0, "paid_amount": 500000.0,
        "contract_party": "上海华虹电子有限公司", "remark": "三流不一致待核实",
        "created_by": "liuyang", "created_at": "2026-09-19 09:00:00",
    })
    db.insert("invoices", {
        "no": db.gen_no("invoices", "XX"), "kind": "销项", "code": "044001", "number": "90000002",
        "invoice_type": "增值税专用发票", "entity": "E03",
        "seller_name": "飞税商贸（上海）有限公司", "seller_tax_no": "91310104MA1FR9K2L6",
        "buyer_name": "广州盛世贸易有限公司", "buyer_tax_no": "91440101000077777D",
        "amount": 1500000.0, "tax_rate": "13%", "tax": 195000.0, "total": 1695000.0,
        "biz_date": "2026-09-25", "period": "2026-09", "status": "作废",
        "verify_status": "-", "category": "销售货物", "remark": "开票有误已作废重开",
        "created_by": "liuyang", "created_at": "2026-09-25 16:00:00",
    })


def _seed_declarations():
    """按月/季生成申报单，10 月为进行中。"""
    for e in ENTITIES:
        code, name, tp = e[0], e[1], e[3]
        is_small = tp == "小规模纳税人"
        city = e[5]
        for p in PERIODS:
            # 增值税
            outs = db.rows("SELECT SUM(amount) a, SUM(tax) t FROM invoices "
                           "WHERE entity=? AND period=? AND kind='销项' AND status='正常'", (code, p))
            ins = db.rows("SELECT SUM(amount) a, SUM(tax) t FROM invoices "
                          "WHERE entity=? AND period=? AND kind='进项' AND status='正常' "
                          "AND verify_status='已认证'", (code, p))
            out_amt = (outs[0]["a"] or 0) if outs else 0
            out_tax = (outs[0]["t"] or 0) if outs else 0
            in_tax = (ins[0]["t"] or 0) if ins else 0

            if is_small:
                r = T.vat_small_scale(out_amt, quarterly=False)
                vat_pay = r["tax"]
                vat_base = r["sales"]
                detail = {"mode": "简易计税", "sales": str(r["sales"]),
                          "rate": r["rate"], "exempt": r["exempt"], "note": r["note"]}
            else:
                r = T.vat_general([{"amount": out_amt, "rate": "13%"}], in_tax)
                vat_pay = r["payable"]
                vat_base = r["out_net"]
                detail = {"mode": "一般计税", "out_tax": str(r["out_tax"]),
                          "in_tax": str(r["in_tax"]), "deductible": str(r["deductible"])}

            sur = T.surtaxes(float(vat_pay), city, is_small)
            done = p != "2026-10"
            due = T.due_date(p, "增值税")
            status = "已申报" if done else random.choice(["草稿", "已申报", "待申报"])
            db.insert("declarations", {
                "no": db.gen_no("declarations", "SB"), "entity": code, "tax_type": "增值税",
                "period": p, "status": status, "base_amount": round(float(vat_base), 2),
                "tax_amount": round(float(vat_pay), 2),
                "relief_amount": round(float(sur["total"]), 2), "paid_amount": 0,
                "carry_forward": round(float(r.get("carry_forward", 0) if isinstance(r, dict) else 0), 2),
                "due_date": due,
                "filed_at": (_d(-3) + " 10:00:00") if done else "",
                "paid_at": (_d(-2) + " 15:00:00") if done else "",
                "detail": str(detail), "memo": "",
                "created_by": "liyan", "created_at": p + "-01 09:00:00",
            })
            # 附加税费
            db.insert("declarations", {
                "no": db.gen_no("declarations", "SB"), "entity": code, "tax_type": "附加税费",
                "period": p, "status": status, "base_amount": round(float(vat_pay), 2),
                "tax_amount": round(float(sur["total"]), 2),
                "relief_amount": 0, "paid_amount": 0, "carry_forward": 0,
                "due_date": due,
                "filed_at": (_d(-3) + " 10:05:00") if done else "",
                "paid_at": (_d(-2) + " 15:05:00") if done else "",
                "detail": str({"items": [{"name": i["name"], "amount": str(i["amount"])}
                                         for i in sur["items"]]}),
                "memo": "", "created_by": "liyan", "created_at": p + "-01 09:05:00",
            })
        # 企业所得税（季度）：7-9 为 Q3，10 为 Q4
        for p, q in [("2026-09", "Q3"), ("2026-10", "Q4")]:
            profit = round(random.uniform(800000, 4200000), 2)
            small = bool(e[11])
            ci = T.cit_quarterly(profit, is_small_profit=small,
                                 rd_expense=profit * 0.12 if e[12] else 0)
            db.insert("declarations", {
                "no": db.gen_no("declarations", "SB"), "entity": code, "tax_type": "企业所得税",
                "period": p, "status": "已申报" if p == "2026-09" else "草稿",
                "base_amount": float(ci["taxable"]), "tax_amount": float(ci["tax"]),
                "relief_amount": 0, "paid_amount": float(ci["tax"]) if p == "2026-09" else 0,
                "carry_forward": 0, "due_date": T.due_date(p, "企业所得税"),
                "filed_at": (_d(-5) + " 10:00:00") if p == "2026-09" else "",
                "paid_at": (_d(-4) + " 14:00:00") if p == "2026-09" else "",
                "detail": str({"profit": str(ci["profit"]), "taxable": str(ci["taxable"]),
                               "rate": ci["rate"], "rd_extra": str(ci["rd_extra"])}),
                "memo": "%s 季度预缴" % q, "created_by": "liyan",
                "created_at": p + "-28 09:00:00",
            })
        # 个人所得税（月度）
        for p in PERIODS:
            gross = round(random.uniform(180000, 620000), 2)
            it = T.iit_salary(gross, social_insurance=gross * 0.105,
                              special_deduct=len(USERS) * 2000 * 12 / 12)
            db.insert("declarations", {
                "no": db.gen_no("declarations", "SB"), "entity": code, "tax_type": "个人所得税",
                "period": p, "status": "已申报" if p != "2026-10" else "待申报",
                "base_amount": float(it["taxable"]), "tax_amount": float(it["tax"]),
                "relief_amount": 0, "paid_amount": float(it["tax"]) if p != "2026-10" else 0,
                "carry_forward": 0, "due_date": T.due_date(p, "个人所得税"),
                "filed_at": (_d(-3) + " 11:00:00") if p != "2026-10" else "",
                "paid_at": (_d(-2) + " 16:00:00") if p != "2026-10" else "",
                "detail": str({"gross": str(it["gross"]), "taxable": str(it["taxable"]),
                               "level": it["level"], "rate": it["rate"]}),
                "memo": "工资薪金代扣代缴", "created_by": "liuyang",
                "created_at": p + "-05 09:00:00",
            })


def _seed_vouchers():
    """凭证台账：与申报税额勾稽。"""
    for e in ENTITIES:
        code = e[0]
        for p in PERIODS:
            decls = db.rows("SELECT tax_type,tax_amount FROM declarations "
                            "WHERE entity=? AND period=? AND status<>'草稿'", (code, p))
            for d in decls:
                amt = float(d["tax_amount"] or 0)
                if amt <= 0:
                    continue
                db.insert("vouchers", {
                    "no": db.gen_no("vouchers", "PZ"),
                    "entity": code, "period": p, "vdate": p + "-15",
                    "summary": "计提%s" % d["tax_type"],
                    "account": "2221 应交税费", "debit": 0, "credit": round(amt, 2),
                    "tax_type": d["tax_type"], "src": "申报单", "memo": "",
                    "created_by": "xumei", "created_at": p + "-15 17:00:00",
                })


def _seed_contracts():
    for i, e in enumerate(ENTITIES):
        for t, party, amt in [
            ("买卖合同", random.choice(SUPPLIERS)[0], round(random.uniform(500000, 3000000), 2)),
            ("租赁合同", "上海张江科技园发展有限公司", round(random.uniform(200000, 800000), 2)),
            ("技术合同", "北京中科软件技术有限公司", round(random.uniform(300000, 1500000), 2)),
        ]:
            sd = T.stamp_duty(t, amt)
            db.insert("contracts", {
                "no": db.gen_no("contracts", "HT"), "entity": e[0], "ctype": t,
                "title": "%s-%s" % (e[1][:6], t), "party": party, "amount": amt,
                "vat_excluded": 1, "sign_date": "2026-0%d-1%d" % (random.randint(5, 9), random.randint(0, 9)),
                "stamp_tax": float(sd["tax"]), "stamp_paid": random.randint(0, 1),
                "status": "执行中", "memo": "", "created_at": "2026-06-01 09:00:00",
            })


def _seed_risks():
    data = [
        ("E02", "2026-09", "CONTRACT_MISMATCH", "险",
         "进项发票金额与合同金额不一致", "某商贸有限公司开具 904,000 元发票，合同金额 700,000 元，差额 204,000 元", 35),
        ("E02", "2026-09", "NO_TAX_NO", "警",
         "进项发票销方税号为空", "发票号码 90000001 销方纳税人识别号缺失，不得作为抵扣凭证", 20),
        ("E03", "2026-09", "VOIDED", "提",
         "已作废发票仍计入销售额", "发票 90000002 已作废，核对申报表是否已冲减", 10),
        ("E03", "2026-09", "BURDEN_LOW", "警",
         "增值税税负率低于行业均值", "本期税负率 1.28%，行业均值 2.85%，偏离 -55%", 30),
        ("E01", "2026-09", "HIGH_TECH_RD", "提",
         "高企研发费用归集不足", "研发费用占收入 8.2%，低于高企认定 3% 但加计扣除基数偏小，建议复核", 10),
        ("E04", "2026-09", "SURTAX_CITY", "警",
         "城建税适用税率与注册地不符", "注册地县城/镇应为 5%，本期按 7% 申报，多缴", 20),
        ("E05", "2026-10", "SMALL_THRESHOLD", "提",
         "小规模纳税人接近起征点", "季度销售额 28.6 万，距 30 万起征点仅 1.4 万，注意跨季开票安排", 10),
        ("E07", "2026-09", "INPUT_TRANSFER", "警",
         "进项税额转出未同步", "用于集体福利的购进货物未做进项转出", 25),
    ]
    for e, p, code, level, title, detail, w in data:
        st = random.choice(["待处理", "待处理", "已整改"])
        db.insert("risks", {
            "entity": e, "period": p, "code": code, "level": level,
            "title": title, "detail": detail, "weight": w, "status": st,
            "handler": "liyan" if st == "已整改" else "",
            "created_at": _dt(-random.randint(1, 15)),
            "closed_at": _dt(-random.randint(0, 5)) if st == "已整改" else "",
        })


def _seed_policies():
    data = [
        ("中华人民共和国增值税法", "主席令第四十一号", "增值税", "法律",
         "2026-01-01", "", "2026 年起施行，税率 13%/9%/6%/0%，征收率 3%，取消 5%",
         "第八条 小规模纳税人可以按照销售额和征收率计算应纳税额的简易计税方法。"
         "第十一条 适用简易计税方法计算缴纳增值税的征收率为百分之三。"
         "第二十三条 小规模纳税人发生应税交易，销售额未达到起征点的，免征增值税。"
         "第三十八条 本法自 2026 年 1 月 1 日起施行，《增值税暂行条例》同时废止。",
         "增值税,小规模,征收率"),
        ("财政部 税务总局关于增值税法施行后增值税优惠政策衔接事项的公告", "2026 年第 10 号",
         "增值税", "部门公告", "2026-01-01", "2027-12-31",
         "起征点：月 10 万 / 季 30 万；3% 减按 1% 延续至 2027 年底",
         "一、起征点：以一个月为计税期间的月销售额 10 万元；以一个季度为计税期间的季度销售额 30 万元。"
         "三、（三）6. 自 2026 年 1 月 1 日至 2027 年 12 月 31 日，小规模纳税人发生除销售、出租不动产"
         "或者转让土地使用权之外的应税交易，依照 3% 征收率减按 1% 征收率征收增值税。",
         "起征点,减按1%,小规模"),
        ("财政部 税务总局关于进一步支持小微企业和个体工商户发展有关税费政策的公告",
         "2023 年第 12 号", "综合", "部门公告", "2023-01-01", "2027-12-31",
         "小型微利企业 5% 实际税负；六税两费减半",
         "一、对小型微利企业年应纳税所得额不超过 300 万元的部分，减按 25% 计算应纳税所得额，"
         "按 20% 的税率缴纳企业所得税。"
         "二、对增值税小规模纳税人、小型微利企业和个体工商户减半征收资源税（不含水资源税）、"
         "城市维护建设税、房产税、城镇土地使用税、印花税（不含证券交易印花税）、"
         "耕地占用税和教育费附加、地方教育附加。"
         "五、小型微利企业须同时符合：年度应纳税所得额≤300 万元、从业人数≤300 人、资产总额≤5000 万元。",
         "小型微利,六税两费,减半"),
        ("财政部 税务总局关于延续实施全年一次性奖金个人所得税政策的公告", "2023 年第 30 号",
         "个人所得税", "部门公告", "2023-01-01", "2027-12-31",
         "全年一次性奖金可不并入综合所得，单独计税",
         "一、居民个人取得全年一次性奖金，符合规定的，不并入当年综合所得，"
         "以全年一次性奖金收入除以 12 个月得到的数额，按照按月换算后的综合所得税率表，"
         "确定适用税率和速算扣除数，单独计算纳税。"
         "计算公式：应纳税额＝全年一次性奖金收入×适用税率－速算扣除数。"
         "二、也可以选择并入当年综合所得计算纳税。三、本公告执行至 2027 年 12 月 31 日。",
         "年终奖,单独计税,个税"),
        ("中华人民共和国印花税法", "主席令第八十九号", "印花税", "法律",
         "2022-07-01", "", "4 税目 17 子目 5 档比例税率",
         "税目税率：借款合同万分之零点五；融资租赁合同万分之零点五；买卖合同万分之三；"
         "承揽合同万分之三；建设工程合同万分之三；运输合同万分之三；技术合同万分之三；"
         "租赁合同千分之一；保管合同千分之一；仓储合同千分之一；财产保险合同千分之一；"
         "土地使用权出让书据万分之五；不动产转让书据万分之五；股权转让书据万分之五；"
         "知识产权转让书据万分之三；营业账簿万分之二点五；证券交易千分之一。"
         "第五条 计税依据为合同所列金额，不包括列明的增值税税款。",
         "印花税,税目,税率"),
        ("中华人民共和国企业所得税法", "主席令第六十三号", "企业所得税", "法律",
         "2008-01-01", "", "法定税率 25%，高新 15%，小微实际 5%",
         "第四条 企业所得税的税率为 25%。第二十八条 国家需要重点扶持的高新技术企业，"
         "减按 15% 的税率征收企业所得税。符合条件的小型微利企业，减按 20% 的税率征收企业所得税。",
         "企业所得税,税率,高新"),
        ("中华人民共和国房产税暂行条例", "国发〔1986〕90 号", "房产税", "行政法规",
         "1986-10-01", "", "从价 1.2% / 从租 12%",
         "第三条 房产税依照房产原值一次减除 10% 至 30% 后的余值计算缴纳，税率为 1.2%；"
         "房产出租的，以房产租金收入为房产税的计税依据，税率为 12%。",
         "房产税,从价,从租"),
        ("中华人民共和国城镇土地使用税暂行条例", "国务院令第 483 号", "城镇土地使用税",
         "行政法规", "2007-01-01", "", "分级幅度税额 1.5~30 元/㎡·年",
         "第四条 土地使用税每平方米年税额：大城市 1.5 元至 30 元；中等城市 1.2 元至 24 元；"
         "小城市 0.9 元至 18 元；县城、建制镇、工矿区 0.6 元至 12 元。",
         "土地使用税,分级,税额"),
    ]
    for t in data:
        db.insert("policies", {
            "title": t[0], "doc_no": t[1], "tax_type": t[2], "category": t[3],
            "effect_date": t[4], "expire_date": t[5], "summary": t[6],
            "content": t[7], "tags": t[8], "status": "有效",
            "created_at": "2026-01-05 09:00:00",
        })


if __name__ == "__main__":
    print("seeded:", seed())
