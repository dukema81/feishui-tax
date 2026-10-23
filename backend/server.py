# -*- coding: utf-8 -*-
"""飞税税务管理系统 · HTTP 服务层

零依赖：http.server.ThreadingHTTPServer + sqlite3，Python 3.9+ 即可运行。
统一响应 {code, message, data}，code 与 HTTP 状态码一致。
"""
import hashlib
import json
import os
import re
import sys
import time
import traceback
import urllib.parse
from decimal import Decimal

D = Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db                                           # noqa: E402
import seed as seedmod                              # noqa: E402
import tax as T                                     # noqa: E402

BRAND = "飞税税务管理系统"
VERSION = "1.0.0"
PORT = int(os.environ.get("TAX_PORT") or 8024)
PREFIX = (os.environ.get("TAX_PREFIX") or "").rstrip("/")
FRONTEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")


# ==================================================== 工具
class ApiError(Exception):
    def __init__(self, message, code=400):
        self.message = message
        self.code = code
        super().__init__(message)


def sha(s):
    return hashlib.sha256(str(s).encode()).hexdigest()


def num(x, default=0.0):
    try:
        return float(x)
    except Exception:                                    # noqa: BLE001
        return default


def intn(x, default=0):
    try:
        return int(x)
    except Exception:                                    # noqa: BLE001
        return default


def jloads(s, default=None):
    try:
        return json.loads(s) if s else (default if default is not None else {})
    except Exception:                                    # noqa: BLE001
        return default if default is not None else {}


def jdumps(o):
    return json.dumps(o, ensure_ascii=False, default=str)


def fmt(rows_):
    """把 Decimal / datetime 等转成 JSON 友好值。"""
    if isinstance(rows_, list):
        return [fmt(r) for r in rows_]
    if isinstance(rows_, dict):
        out = {}
        for k, v in rows_.items():
            out[k] = fmt(v)
        return out
    if isinstance(rows_, Decimal):
        return float(rows_)
    return rows_


def has_perm(u, need):
    return T.has_perm(u.get("perms") or [], need)


def need(u, perm):
    if not has_perm(u, perm):
        raise ApiError("无权限：需要 %s" % perm, 403)


def log(u, action, target="", detail="", ip=""):
    db.run("INSERT INTO logs (ts,username,action,target,detail,ip) VALUES (?,?,?,?,?,?)",
           (db.now(), (u or {}).get("username", "-"), action, target,
            str(detail)[:800], ip))


# ==================================================== 鉴权
def user_by_token(value):
    """五通道鉴权：Bearer / X-Tax-Token / Cookie / ?token= / X-Tax-Key。"""
    if not value:
        return None
    tok = str(value)
    if tok.lower().startswith("bearer "):
        tok = tok[7:].strip()
    r = db.one("SELECT u.* FROM tokens t JOIN users u ON u.username=t.username "
               "WHERE t.token=?", (tok,))
    if not r or r.get("status") != "启用":
        return None
    return build_user(r)


def user_by_apikey(value):
    if not value:
        return None
    h = sha(value)
    k = db.one("SELECT * FROM api_keys WHERE key_hash=? AND status='启用'", (h,))
    if not k:
        return None
    db.run("UPDATE api_keys SET last_used=? WHERE id=?", (db.now(), k["id"]))
    scope = k.get("scope") or "read"
    perms = ["tax.read", "invoice.read", "input.read", "entity.read",
             "voucher.read", "report.read", "policy.read"]
    if scope in ("write", "full"):
        perms += ["invoice.write", "invoice.void", "input.verify", "input.transfer",
                  "tax.declare", "tax.calc", "voucher.write"]
    if scope == "full":
        perms += ["risk.read", "org.read", "system.read"]
    return {"username": "__apikey__", "name": k["name"], "role": "apikey",
            "roleLabel": "接口密钥", "dept": "", "deptName": "",
            "perms": perms, "api_key_id": k["id"]}


def build_user(r):
    perms = sorted(T.ROLE_PERMS.get(r.get("role") or "reader", []))
    dept = db.one("SELECT name FROM depts WHERE code=?", (r.get("dept") or "",))
    return {
        "username": r["username"], "name": r["name"], "role": r["role"],
        "roleLabel": ROLE_LABELS.get(r["role"], r["role"]),
        "dept": r.get("dept") or "", "deptName": (dept or {}).get("name", ""),
        "title": r.get("title") or "", "phone": r.get("phone") or "",
        "email": r.get("email") or "", "perms": perms,
    }


ROLE_LABELS = {
    "admin": "系统管理员", "manager": "管理层", "tax_accountant": "税务会计",
    "finance": "财务会计", "auditor": "内审", "reader": "只读用户",
}


# ==================================================== 认证相关
def api_health(u, b, q):
    return {
        "brand": BRAND, "version": VERSION, "routes": len(ROUTES),
        "users": db.val("SELECT COUNT(*) FROM users", (), 0),
        "entities": db.val("SELECT COUNT(*) FROM entities", (), 0),
        "invoices": db.val("SELECT COUNT(*) FROM invoices", (), 0),
        "declarations": db.val("SELECT COUNT(*) FROM declarations", (), 0),
        "periods": list(reversed([r["period"] for r in db.rows(
            "SELECT DISTINCT period FROM declarations ORDER BY period")])),
        "time": db.now(),
    }


def api_login(u, b, q):
    un = (b.get("username") or "").strip()
    pw = b.get("password") or ""
    if not un or not pw:
        raise ApiError("用户名与密码必填", 401)
    r = db.one("SELECT * FROM users WHERE username=?", (un,))
    if not r or r.get("pwd") != sha(pw):
        raise ApiError("用户名或密码错误", 401)
    if r.get("status") != "启用":
        raise ApiError("账号已停用", 403)
    tok = sha(un + str(time.time()) + os.urandom(8).hex())
    db.run("INSERT INTO tokens (token,username,created_at) VALUES (?,?,?)",
           (tok, un, db.now()))
    me = build_user(r)
    log(me, "登录", un)
    return {"token": tok, "username": un, "name": r["name"], "role": r["role"],
            "roleLabel": me["roleLabel"], "dept": r.get("dept") or ""}


def api_logout(u, b, q):
    tok = (b.get("token") or "").strip()
    if tok:
        db.run("DELETE FROM tokens WHERE token=?", (tok,))
    return {"ok": True}


def api_me(u, b, q):
    return u


def api_change_pwd(u, b, q):
    old = b.get("old_password") or ""
    new = b.get("new_password") or ""
    if len(new) < 6:
        raise ApiError("新密码至少 6 位")
    r = db.one("SELECT * FROM users WHERE username=?", (u["username"],))
    if not r or r.get("pwd") != sha(old):
        raise ApiError("原密码不正确")
    db.run("UPDATE users SET pwd=? WHERE username=?", (sha(new), u["username"]))
    db.run("DELETE FROM tokens WHERE username=?", (u["username"],))
    log(u, "修改密码", u["username"])
    return {"ok": True, "relogin": True}


def listwrap(items):
    """列表型接口统一返回 {list,total}，便于前端与外部系统一致处理。"""
    items = items or []
    return {"list": items, "total": len(items)}

# ==================================================== 工作台
def api_dashboard(u, b, q):
    period = (q.get("period") or [None])[0] or db.val(
        "SELECT MAX(period) FROM declarations", (), "2026-10")
    ents = db.rows("SELECT code,name,taxpayer_type,small_profit,high_tech FROM entities WHERE status='启用'")
    vat_out = num(db.val("SELECT SUM(tax) FROM invoices WHERE period=? AND kind='销项' AND status='正常'",
                         (period,), 0))
    vat_in = num(db.val("SELECT SUM(tax) FROM invoices WHERE period=? AND kind='进项' "
                        "AND status='正常' AND verify_status='已认证'", (period,), 0))
    vat_pay = max(0.0, vat_out - vat_in)
    decl = db.rows("SELECT no,entity,tax_type,status,tax_amount,paid_amount,due_date "
                   "FROM declarations WHERE period=?", (period,))
    declared = sum(num(d["tax_amount"]) for d in decl)
    paid = sum(num(d["paid_amount"]) for d in decl)
    unpaid = sum(num(d["tax_amount"]) - num(d["paid_amount"]) for d in decl
                 if d["status"] in ("已申报", "待申报"))
    pending = [d for d in decl if d["status"] in ("草稿", "待申报")]
    overdue = [d for d in decl if d["status"] in ("草稿", "待申报")
               and d["due_date"] and d["due_date"] < db.today()]
    risk_open = db.val("SELECT COUNT(*) FROM risks WHERE status='待处理'", (), 0)
    risk_high = db.val("SELECT COUNT(*) FROM risks WHERE status='待处理' AND level='险'", (), 0)

    # 近 6 期税负趋势
    trend = []
    for p in db.rows("SELECT DISTINCT period FROM declarations ORDER BY period DESC LIMIT 6"):
        pp = p["period"]
        o = num(db.val("SELECT SUM(tax) FROM invoices WHERE period=? AND kind='销项' "
                       "AND status='正常'", (pp,), 0))
        i2 = num(db.val("SELECT SUM(tax) FROM invoices WHERE period=? AND kind='进项' "
                        "AND status='正常' AND verify_status='已认证'", (pp,), 0))
        s = num(db.val("SELECT SUM(tax_amount) FROM declarations WHERE period=?", (pp,), 0))
        trend.append({"period": pp, "output": round(o, 2), "input": round(i2, 2),
                      "vat": round(max(0.0, o - i2), 2), "total": round(s, 2)})
    trend.reverse()

    by_type = db.rows(
        "SELECT tax_type AS name, ROUND(SUM(tax_amount),2) AS amount, COUNT(*) AS cnt "
        "FROM declarations WHERE period=? GROUP BY tax_type ORDER BY amount DESC", (period,))

    return {
        "period": period,
        "kpi": {
            "entities": len(ents),
            "outputTax": round(vat_out, 2), "inputTax": round(vat_in, 2),
            "vatPayable": round(vat_pay, 2),
            "declared": round(declared, 2), "paid": round(paid, 2),
            "unpaid": round(unpaid, 2),
            "pendingCount": len(pending), "overdueCount": len(overdue),
            "riskOpen": risk_open, "riskHigh": risk_high,
        },
        "trend": trend, "byType": by_type,
        "pending": sorted(pending, key=lambda x: (x["due_date"] or "", x["no"]))[:8],
        "entities": ents,
        "notices": db.rows("SELECT id,title,created_at,top FROM notices ORDER BY top DESC, id DESC LIMIT 4"),
        "risks": db.rows("SELECT id,entity,level,title,status FROM risks WHERE status='待处理' "
                         "ORDER BY weight DESC LIMIT 5"),
    }


# ==================================================== 纳税主体
def api_entities(u, b, q):
    need(u, "entity.read")
    kw = (q.get("kw") or [""])[0]
    sql = "SELECT * FROM entities WHERE 1=1"
    args = []
    if kw:
        sql += " AND (name LIKE ? OR tax_no LIKE ? OR code LIKE ?)"
        args += ["%%%s%%" % kw] * 3
    sql += " ORDER BY code"
    return listwrap(fmt(db.rows(sql, tuple(args))))


def api_entity_get(u, b, q, code):
    need(u, "entity.read")
    r = db.one("SELECT * FROM entities WHERE code=?", (code,))
    if not r:
        raise ApiError("纳税主体不存在：%s" % code, 404)
    # 汇总该主体当期数据
    period = (q.get("period") or [None])[0] or db.val(
        "SELECT MAX(period) FROM invoices WHERE entity=?", (code,), "")
    out_tax = num(db.val("SELECT SUM(tax) FROM invoices WHERE entity=? AND period=? "
                         "AND kind='销项' AND status='正常'", (code, period), 0))
    in_tax = num(db.val("SELECT SUM(tax) FROM invoices WHERE entity=? AND period=? "
                        "AND kind='进项' AND status='正常' AND verify_status='已认证'",
                        (code, period), 0))
    r["stats"] = {"period": period, "outputTax": round(out_tax, 2),
                  "inputTax": round(in_tax, 2),
                  "vatPayable": round(max(0.0, out_tax - in_tax), 2),
                  "declarations": db.val("SELECT COUNT(*) FROM declarations WHERE entity=?",
                                         (code,), 0),
                  "invoices": db.val("SELECT COUNT(*) FROM invoices WHERE entity=?", (code,), 0)}
    return fmt(r)


def api_entity_save(u, b, q):
    need(u, "entity.write")
    b = b or {}
    errs = T.validate_entity(b)
    if errs:
        raise ApiError("；".join(errs))
    code = (b.get("code") or "").strip() or db.gen_no("entities", "E")
    data = {
        "code": code, "name": (b.get("name") or "").strip(),
        "tax_no": (b.get("tax_no") or "").strip().upper(),
        "taxpayer_type": b.get("taxpayer_type") or "一般纳税人",
        "industry": b.get("industry") or "", "city_type": b.get("city_type") or "市区",
        "region": b.get("region") or "东部",
        "legal_person": b.get("legal_person") or "",
        "contact": b.get("contact") or "", "phone": b.get("phone") or "",
        "reg_address": b.get("reg_address") or "",
        "reg_capital": num(b.get("reg_capital")),
        "staff_count": intn(b.get("staff_count")),
        "asset_total": num(b.get("asset_total")),
        "small_profit": 1 if b.get("small_profit") else 0,
        "high_tech": 1 if b.get("high_tech") else 0,
        "status": b.get("status") or "启用",
    }
    old = db.one("SELECT * FROM entities WHERE code=?", (code,))
    if old:
        db.update("entities", "code", code, data)
    else:
        data["created_at"] = db.now()
        db.insert("entities", data)
    db.bumpsync("entities")
    log(u, "保存纳税主体", code)
    return {"code": code, "created": not bool(old)}


# ==================================================== 发票
def api_invoices(u, b, q):
    need(u, "invoice.read")
    kind = (q.get("kind") or [""])[0]
    entity = (q.get("entity") or [""])[0]
    period = (q.get("period") or [""])[0]
    status = (q.get("status") or [""])[0]
    verify = (q.get("verify") or [""])[0]
    kw = (q.get("kw") or [""])[0]
    sql = ("SELECT i.*,e.name AS entity_name FROM invoices i "
           "LEFT JOIN entities e ON e.code=i.entity WHERE 1=1")
    args = []
    for col, v in (("i.kind", kind), ("i.entity", entity), ("i.period", period),
                   ("i.status", status), ("i.verify_status", verify)):
        if v:
            sql += " AND %s=?" % col
            args.append(v)
    if kw:
        sql += (" AND (i.no LIKE ? OR i.seller_name LIKE ? OR i.buyer_name LIKE ? "
                "OR i.number LIKE ?)")
        args += ["%%%s%%" % kw] * 4
    sql += " ORDER BY i.biz_date DESC, i.no DESC LIMIT 500"
    rows_ = db.rows(sql, tuple(args))
    total_amt = sum(num(r["amount"]) for r in rows_)
    total_tax = sum(num(r["tax"]) for r in rows_)
    return {"list": fmt(rows_), "total": len(rows_), "count": len(rows_),
            "sumAmount": round(total_amt, 2), "sumTax": round(total_tax, 2)}


def api_invoice_get(u, b, q, no):
    need(u, "invoice.read")
    r = db.one("SELECT i.*,e.name AS entity_name FROM invoices i "
               "LEFT JOIN entities e ON e.code=i.entity WHERE i.no=?", (no,))
    if not r:
        raise ApiError("发票不存在：%s" % no, 404)
    r["items"] = db.rows("SELECT * FROM invoice_items WHERE invoice=?", (no,))
    r["risks"] = T.invoice_risk(r)
    if r.get("contract_no"):
        r["three_flow"] = T.three_flow_check({
            "amount": r["amount"], "contract_amount": r["contract_amount"],
            "paid_amount": r["paid_amount"], "seller_name": r["seller_name"],
            "contract_party": r["contract_party"], "buyer_name": r["buyer_name"],
            "entity_name": r.get("entity_name") or "",
        })
    return fmt(r)


def api_invoice_save(u, b, q):
    need(u, "invoice.write")
    b = b or {}
    entity = (b.get("entity") or "").strip()
    if not entity:
        raise ApiError("纳税主体必填")
    ent = db.one("SELECT * FROM entities WHERE code=?", (entity,))
    if not ent:
        raise ApiError("纳税主体不存在：%s" % entity, 404)
    kind = b.get("kind") or "销项"
    amount = num(b.get("amount"))
    if amount <= 0:
        raise ApiError("金额必须大于 0")
    rate = b.get("rate") or "13%"
    if rate not in T.VAT_RATES:
        raise ApiError("税率不在法定范围：%s" % rate)
    inclusive = bool(b.get("inclusive"))
    line = T.vat_invoice_tax(amount, rate, inclusive=inclusive)

    no = (b.get("no") or "").strip()
    old = db.one("SELECT * FROM invoices WHERE no=?", (no,)) if no else None
    if not no:
        no = db.gen_no("invoices", "XX")

    biz_date = b.get("biz_date") or db.today()
    data = {
        "no": no, "kind": kind, "code": b.get("code") or "",
        "number": b.get("number") or "",
        "invoice_type": b.get("invoice_type") or "增值税专用发票",
        "entity": entity,
        "seller_name": b.get("seller_name") or (ent["name"] if kind == "销项" else ""),
        "seller_tax_no": b.get("seller_tax_no") or (ent["tax_no"] if kind == "销项" else ""),
        "buyer_name": b.get("buyer_name") or (ent["name"] if kind == "进项" else ""),
        "buyer_tax_no": b.get("buyer_tax_no") or (ent["tax_no"] if kind == "进项" else ""),
        "amount": float(line["net"]), "tax_rate": rate, "tax": float(line["tax"]),
        "total": float(line["gross"]), "biz_date": biz_date, "period": biz_date[:7],
        "status": b.get("status") or "正常",
        "verify_status": b.get("verify_status") or ("未认证" if kind == "进项" else "-"),
        "category": b.get("category") or "", "contract_no": b.get("contract_no") or "",
        "contract_amount": num(b.get("contract_amount")),
        "paid_amount": num(b.get("paid_amount")),
        "contract_party": b.get("contract_party") or "",
        "remark": b.get("remark") or "",
    }
    if old:
        db.update("invoices", "no", no, data)
    else:
        data["created_by"] = u["username"]
        data["created_at"] = db.now()
        db.insert("invoices", data)
    # 明细
    db.run("DELETE FROM invoice_items WHERE invoice=?", (no,))
    items = b.get("items") or [{"goods": data.get("category") or "货物/服务",
                                "qty": 1, "price": float(line["net"]),
                                "amount": float(line["net"]), "tax_rate": rate,
                                "tax": float(line["tax"])}]
    for it in items:
        db.insert("invoice_items", {
            "invoice": no, "goods": it.get("goods") or "",
            "spec": it.get("spec") or "", "unit": it.get("unit") or "",
            "qty": num(it.get("qty")), "price": num(it.get("price")),
            "amount": num(it.get("amount")), "tax_rate": it.get("tax_rate") or rate,
            "tax": num(it.get("tax")),
        })
    db.bumpsync("invoices")
    log(u, "保存发票", no, "%s %s %s" % (kind, entity, amount))
    return {"no": no, "created": not bool(old), "amount": float(line["net"]),
            "tax": float(line["tax"]), "total": float(line["gross"])}


def api_invoice_void(u, b, q, no):
    need(u, "invoice.void")
    r = db.one("SELECT * FROM invoices WHERE no=?", (no,))
    if not r:
        raise ApiError("发票不存在：%s" % no, 404)
    if r["status"] == "作废":
        raise ApiError("发票已作废")
    db.run("UPDATE invoices SET status='作废', remark=? WHERE no=?",
           ((r.get("remark") or "") + " 已作废", no))
    db.bumpsync("invoices")
    log(u, "作废发票", no)
    return {"no": no, "status": "作废"}


def api_invoice_verify(u, b, q):
    """进项发票认证（可批量）。"""
    need(u, "input.verify")
    nos = b.get("nos") or ([b["no"]] if b.get("no") else [])
    if not nos:
        raise ApiError("请选择要认证的发票")
    ok, fail = [], []
    for no in nos:
        r = db.one("SELECT * FROM invoices WHERE no=?", (no,))
        if not r:
            fail.append({"no": no, "reason": "不存在"})
            continue
        if r["kind"] != "进项":
            fail.append({"no": no, "reason": "非进项发票"})
            continue
        if r["status"] == "作废":
            fail.append({"no": no, "reason": "已作废，不得认证"})
            continue
        if not (r.get("seller_tax_no") or "").strip():
            fail.append({"no": no, "reason": "销方税号缺失，不得抵扣"})
            continue
        db.run("UPDATE invoices SET verify_status='已认证' WHERE no=?", (no,))
        ok.append(no)
    db.bumpsync("invoices")
    log(u, "认证进项发票", ",".join(ok[:20]), "成功 %d 失败 %d" % (len(ok), len(fail)))
    return {"verified": ok, "failed": fail, "okCount": len(ok)}


# ==================================================== 申报
def api_declarations(u, b, q):
    need(u, "tax.read")
    entity = (q.get("entity") or [""])[0]
    tax_type = (q.get("tax_type") or [""])[0]
    period = (q.get("period") or [""])[0]
    status = (q.get("status") or [""])[0]
    kw = (q.get("kw") or [""])[0]
    sql = ("SELECT d.*,e.name AS entity_name FROM declarations d "
           "LEFT JOIN entities e ON e.code=d.entity WHERE 1=1")
    args = []
    for col, v in (("d.entity", entity), ("d.tax_type", tax_type),
                   ("d.period", period), ("d.status", status)):
        if v:
            sql += " AND %s=?" % col
            args.append(v)
    if kw:
        sql += " AND (d.no LIKE ? OR e.name LIKE ?)"
        args += ["%%%s%%" % kw] * 2
    sql += " ORDER BY d.period DESC, d.entity, d.tax_type LIMIT 600"
    rows_ = db.rows(sql, tuple(args))
    today = db.today()
    for r in rows_:
        r["overdue"] = bool(r["due_date"] and r["status"] in ("草稿", "待申报")
                            and r["due_date"] < today)
        r["detail"] = jloads(r.get("detail"), {})
    return {"list": fmt(rows_), "total": len(rows_), "count": len(rows_),
            "sumTax": round(sum(num(r["tax_amount"]) for r in rows_), 2),
            "sumUnpaid": round(sum(num(r["tax_amount"]) - num(r["paid_amount"])
                                   for r in rows_ if r["status"] in ("已申报", "待申报")), 2)}


def api_decl_get(u, b, q, no):
    need(u, "tax.read")
    r = db.one("SELECT d.*,e.name AS entity_name,e.taxpayer_type,e.city_type "
               "FROM declarations d LEFT JOIN entities e ON e.code=d.entity WHERE d.no=?", (no,))
    if not r:
        raise ApiError("申报单不存在：%s" % no, 404)
    r["detail"] = jloads(r.get("detail"), {})
    r["vouchers"] = db.rows("SELECT no,vdate,summary,credit FROM vouchers "
                            "WHERE entity=? AND period=? AND tax_type=?",
                            (r["entity"], r["period"], r["tax_type"]))
    return fmt(r)


def api_decl_calc(u, b, q):
    """按主体+税种+期间试算申报数据（不落库）。"""
    need(u, "tax.calc")
    b = b or {}
    entity = (b.get("entity") or "").strip()
    tax_type = (b.get("tax_type") or "增值税").strip()
    period = (b.get("period") or db.today()[:7]).strip()
    ent = db.one("SELECT * FROM entities WHERE code=?", (entity,))
    if not ent:
        raise ApiError("纳税主体不存在：%s" % entity, 404)

    if tax_type == "增值税":
        out_amt = num(db.val("SELECT SUM(amount) FROM invoices WHERE entity=? AND period=? "
                             "AND kind='销项' AND status='正常'", (entity, period), 0))
        out_tax = num(db.val("SELECT SUM(tax) FROM invoices WHERE entity=? AND period=? "
                             "AND kind='销项' AND status='正常'", (entity, period), 0))
        in_tax = num(db.val("SELECT SUM(tax) FROM invoices WHERE entity=? AND period=? "
                            "AND kind='进项' AND status='正常' AND verify_status='已认证'",
                            (entity, period), 0))
        if ent["taxpayer_type"] == "小规模纳税人":
            r = T.vat_small_scale(out_amt, quarterly=False)
            return fmt({"tax_type": tax_type, "period": period, "mode": "简易计税",
                        "result": r, "tax": r["tax"], "base": r["sales"],
                        "lines": []})
        r = T.vat_general([{"amount": out_amt, "rate": "13%"}], in_tax,
                          prior_credit=num(b.get("prior_credit")),
                          input_transfer_out=num(b.get("transfer_out")),
                          pre_paid=num(b.get("pre_paid")))
        return fmt({"tax_type": tax_type, "period": period, "mode": "一般计税",
                    "result": r, "tax": r["payable"], "base": r["out_net"],
                    "lines": r["lines"]})

    if tax_type == "附加税费":
        base = num(b.get("vat_payable"))
        if not base:
            out_tax = num(db.val("SELECT SUM(tax) FROM invoices WHERE entity=? AND period=? "
                                 "AND kind='销项' AND status='正常'", (entity, period), 0))
            in_tax = num(db.val("SELECT SUM(tax) FROM invoices WHERE entity=? AND period=? "
                                "AND kind='进项' AND status='正常' AND verify_status='已认证'",
                                (entity, period), 0))
            base = max(0.0, out_tax - in_tax)
        halve = db.rule("surtax_halve", "1") == "1" and (
            ent["taxpayer_type"] == "小规模纳税人" or bool(ent["small_profit"]))
        r = T.surtaxes(base, ent["city_type"], halve)
        return fmt({"tax_type": tax_type, "base": base, "result": r,
                    "tax": r["total"], "lines": r["items"]})

    if tax_type == "企业所得税":
        profit = num(b.get("profit"))
        small = bool(ent["small_profit"])
        r = T.cit_quarterly(profit, prior_paid=num(b.get("prior_paid")),
                            is_small_profit=small, rd_expense=num(b.get("rd_expense")),
                            rate=T.CIT_HIGH_TECH if ent["high_tech"] else T.CIT_RATE)
        return fmt({"tax_type": tax_type, "result": r, "tax": r["tax"],
                    "base": r["taxable"], "lines": []})

    if tax_type == "个人所得税":
        r = T.iit_salary(num(b.get("gross")), social_insurance=num(b.get("social_insurance")),
                         special_deduct=num(b.get("special_deduct")),
                         other_deduct=num(b.get("other_deduct")))
        return fmt({"tax_type": tax_type, "result": r, "tax": r["tax"],
                    "base": r["taxable"], "lines": []})

    if tax_type == "印花税":
        items = b.get("items") or []
        r = T.stamp_duty_batch(items)
        return fmt({"tax_type": tax_type, "result": r, "tax": r["total"],
                    "base": sum(num(i["base"]) for i in r["items"]),
                    "lines": r["items"]})

    if tax_type == "房产税":
        r = T.house_tax(b.get("mode") or "从价", original_value=num(b.get("original_value")),
                        rent=num(b.get("rent")),
                        deduct_ratio=num(b.get("deduct_ratio"), 0.3))
        return fmt({"tax_type": tax_type, "result": r, "tax": r["tax"],
                    "base": num(r.get("residual") or r.get("rent")), "lines": []})

    if tax_type == "城镇土地使用税":
        r = T.land_tax(num(b.get("area")), intn(b.get("grade"), 3),
                       b.get("unit_rate") or None)
        return fmt({"tax_type": tax_type, "result": r, "tax": r["tax"],
                    "base": r["area"], "lines": []})

    raise ApiError("不支持的税种：%s" % tax_type)


def api_decl_save(u, b, q):
    need(u, "tax.declare")
    b = b or {}
    errs = T.validate_declaration(b)
    if errs:
        raise ApiError("；".join(errs))
    no = (b.get("no") or "").strip()
    old = db.one("SELECT * FROM declarations WHERE no=?", (no,)) if no else None
    if not no:
        no = db.gen_no("declarations", "SB")
    period = (b.get("period") or "").strip()
    tax_type = (b.get("tax_type") or "").strip()
    data = {
        "no": no, "entity": b.get("entity"), "tax_type": tax_type, "period": period,
        "status": b.get("status") or (old or {}).get("status") or "草稿",
        "base_amount": num(b.get("base_amount")),
        "tax_amount": num(b.get("tax_amount")),
        "relief_amount": num(b.get("relief_amount")),
        "paid_amount": num(b.get("paid_amount")),
        "carry_forward": num(b.get("carry_forward")),
        "due_date": b.get("due_date") or T.due_date(period, tax_type),
        "detail": jdumps(b.get("detail") or (old or {}).get("detail") or {}),
        "memo": b.get("memo") or "",
    }
    if old:
        db.update("declarations", "no", no, data)
    else:
        data["created_by"] = u["username"]
        data["created_at"] = db.now()
        db.insert("declarations", data)
    db.bumpsync("declarations")
    log(u, "保存申报单", no, "%s %s %s" % (data["entity"], tax_type, period))
    return {"no": no, "created": not bool(old)}


def api_decl_file(u, b, q, no):
    """申报（提交）→ 状态置已申报，记 filed_at。"""
    need(u, "tax.declare")
    r = db.one("SELECT * FROM declarations WHERE no=?", (no,))
    if not r:
        raise ApiError("申报单不存在：%s" % no, 404)
    if r["status"] == "已申报":
        raise ApiError("该申报单已申报", 409)
    if r["status"] == "已缴款":
        raise ApiError("该申报单已缴款", 409)
    db.run("UPDATE declarations SET status='已申报', filed_at=? WHERE no=?", (db.now(), no))
    db.bumpsync("declarations")
    log(u, "申报", no, "%s %s" % (r["entity"], r["tax_type"]))
    return {"no": no, "status": "已申报", "filedAt": db.now(),
            "dueDate": r["due_date"], "late": T.is_late(r["due_date"], db.today())}


def api_decl_pay(u, b, q, no):
    """缴款 → 状态置已缴款，自动生成凭证。"""
    need(u, "tax.declare")
    r = db.one("SELECT * FROM declarations WHERE no=?", (no,))
    if not r:
        raise ApiError("申报单不存在：%s" % no, 404)
    if r["status"] == "草稿":
        raise ApiError("请先完成申报再缴款", 409)
    if r["status"] == "已缴款":
        raise ApiError("该申报单已缴款", 409)
    amt = num(r["tax_amount"])
    db.run("UPDATE declarations SET status='已缴款', paid_amount=?, paid_at=? WHERE no=?",
           (amt, db.now(), no))
    # 生成缴款凭证
    vno = db.gen_no("vouchers", "PZ")
    db.insert("vouchers", {
        "no": vno, "entity": r["entity"], "period": r["period"],
        "vdate": db.today(), "summary": "缴纳%s" % r["tax_type"],
        "account": "2221 应交税费", "debit": amt, "credit": 0,
        "tax_type": r["tax_type"], "src": "缴款", "memo": no,
        "created_by": u["username"], "created_at": db.now(),
    })
    db.bumpsync("declarations", "vouchers")
    log(u, "缴款", no, "金额 %s 凭证 %s" % (amt, vno))
    return {"no": no, "status": "已缴款", "paidAmount": amt, "voucher": vno}


def api_decl_delete(u, b, q, no):
    need(u, "tax.declare")
    r = db.one("SELECT * FROM declarations WHERE no=?", (no,))
    if not r:
        raise ApiError("申报单不存在：%s" % no, 404)
    if r["status"] in ("已申报", "已缴款"):
        raise ApiError("已申报或已缴款的单据不可删除", 409)
    db.run("DELETE FROM declarations WHERE no=?", (no,))
    db.bumpsync("declarations")
    log(u, "删除申报单", no)
    return {"ok": True}


# ==================================================== 税种计算器
def api_calc(u, b, q):
    """通用税种计算器（不入库），供前端即时试算。

    入参兼容 snake_case 与 camelCase，外部系统接入时不必记忆命名风格。
    """
    b = b or {}

    def g(*names, **kw):
        """按候选键名依次取值，支持默认值。"""
        for n in names:
            if n in b and b[n] is not None:
                return b[n]
        return kw.get("default")

    def gb(*names):
        v = g(*names)
        if isinstance(v, str):
            return v.strip().lower() in ("1", "true", "yes", "y", "on")
        return bool(v)

    kind = str(g("kind", "type", default="vat")).strip().lower().replace("-", "_")

    # 别名字典：外部系统可能传 vat_invoice / invoice / vatInvoice
    aliases = {"vat_invoice": "vat", "invoice": "vat", "vat_rate": "vat",
               "general": "vat_general", "vatgeneral": "vat_general",
               "small": "vat_small", "vat_small_scale": "vat_small",
               "sur": "surtax", "surtaxes": "surtax",
               "cit_annual": "cit", "cit_q": "cit_q", "cit_quarterly": "cit_q",
               "iit_salary": "iit", "salary": "iit",
               "iitbonus": "iit_bonus", "bonus": "iit_bonus",
               "stamp_duty": "stamp", "sd": "stamp",
               "house_tax": "house", "ht": "house",
               "land_tax": "land", "lt": "land",
               "tax_burden": "burden", "threeflow": "three_flow",
               "three_flow_check": "three_flow", "latefee": "late_fee"}
    kind = aliases.get(kind, kind)

    if kind == "vat":
        return fmt(T.vat_invoice_tax(g("amount", "total", default=0),
                                     g("rate", "taxRate", "tax_rate", default="13%"),
                                     inclusive=gb("inclusive", "taxInclusive", "tax_inclusive")))
    if kind == "vat_general":
        outs = g("outputs", "output", "outputList", default=[])
        if isinstance(outs, (int, float, str)):
            outs = [{"amount": outs, "rate": g("rate", "taxRate", default="13%")}]
        ins = g("inputs", "input", "inputList", default=[])
        if isinstance(ins, (int, float, str)):
            ins = [{"amount": ins, "rate": g("rate", "taxRate", default="13%")}]
        return fmt(T.vat_general(
            outs, ins,
            prior_credit=g("prior_credit", "priorCredit", default=0),
            input_transfer_out=g("transfer_out", "transferOut", "input_transfer_out", default=0),
            pre_paid=g("pre_paid", "prePaid", default=0),
            additional_deduct=g("additional", "additional_deduct", "additionalDeduct", default=0)))
    if kind == "vat_small":
        return fmt(T.vat_small_scale(
            g("sales", "amount", default=0),
            gb("quarterly") if "quarterly" in b else (str(g("period", default="季")) != "月"),
            gb("has_realestate", "hasRealEstate"),
            gb("waive")))
    if kind == "surtax":
        city = g("city_type", "cityType", default="市区")
        halve = gb("halve") if ("halve" in b) else gb("small", "small_scale", "smallScale")
        return fmt(T.surtaxes(g("vat_payable", "vatPayable", "vat", default=0), city,
                              halve, gb("fund_exempt", "fundExempt")))
    if kind == "cit":
        return fmt(T.cit_annual(
            g("profit", "taxable_profit", "taxableProfit", default=0),
            rate=g("rate", "taxRate", default=0.25),
            adjust_add=g("adjust_add", "adjustAdd", default=0),
            adjust_less=g("adjust_less", "adjustLess", default=0),
            prior_paid=g("prior_paid", "priorPaid", default=0),
            is_small_profit=gb("small_profit", "small", "smallProfit"),
            rd_expense=g("rd_expense", "rdExpense", default=0),
            loss_carry=g("loss_carry", "lossCarry", default=0)))
    if kind == "cit_q":
        return fmt(T.cit_quarterly(
            g("profit", "taxable_profit", "taxableProfit", default=0),
            rate=g("rate", "taxRate", default=0.25),
            prior_paid=g("prior_paid", "priorPaid", default=0),
            is_small_profit=gb("small_profit", "small", "smallProfit"),
            rd_expense=g("rd_expense", "rdExpense", default=0)))
    if kind == "iit":
        if "taxable_income" in b or "taxableIncome" in b:
            return fmt(T.iit_annual(g("taxable_income", "taxableIncome")))
        return fmt(T.iit_salary(
            g("gross", "gross_year", "grossYear", default=0),
            social_insurance=g("social_insurance", "socialInsurance", default=0),
            special_deduct=g("special_deduct", "specialDeduct", default=0),
            other_deduct=g("other_deduct", "otherDeduct", default=0),
            threshold=g("threshold", default=T.IIT_SALARY_THRESHOLD)))
    if kind == "iit_bonus":
        mode = g("mode", default="best")
        if mode in ("best", "compare", "all"):
            return fmt(T.iit_best_bonus(g("bonus", "amount", default=0),
                                        g("salary_taxable", "salaryTaxable", default=0)))
        return fmt(T.iit_bonus(g("bonus", "amount", default=0), mode=mode,
                               salary_taxable=g("salary_taxable", "salaryTaxable", default=0)))
    if kind == "stamp":
        if b.get("items"):
            return fmt(T.stamp_duty_batch(b["items"]))
        return fmt(T.stamp_duty(
            g("type", "contract_type", "contractType", default="买卖合同"),
            g("amount", "base", default=0),
            bool(gb("vat_excluded", "vatExcluded")) if ("vat_excluded" in b or "vatExcluded" in b) else True,
            g("vat_rate", "vatRate", default="13%")))
    if kind == "house":
        mode = g("mode", default="从价")
        mode = "从价" if str(mode).lower() in ("value", "from_value", "ad") else (
            "从租" if str(mode).lower() in ("rent", "from_rent") else mode)
        return fmt(T.house_tax(mode,
                               g("original_value", "originalValue", "value", default=0),
                               g("rent", "rent_income", "rentIncome", default=0),
                               g("deduct_ratio", "deductRatio", default=T.HOUSE_VALUE_DEDUCT)))
    if kind == "land":
        return fmt(T.land_tax(g("area", default=0),
                              intn(g("grade", default=3), 3),
                              g("unit_rate", "unitRate") or None))
    if kind == "burden":
        return fmt(T.full_tax_burden(
            g("revenue", "sales", default=0),
            vat_payable=g("vat", "vat_payable", "vatPayable", default=0),
            surtax=g("surtax", default=0),
            cit=g("cit", "citTax", default=0),
            stamp=g("stamp", default=0),
            house=g("house", default=0),
            land=g("land", default=0),
            iit=g("iit", default=0),
            other=g("other", default=0)))
    if kind == "three_flow":
        return fmt(T.three_flow_check(b.get("invoice") or b))
    if kind == "late_fee":
        return fmt(T.late_fee(
            g("tax", "tax_amount", "taxAmount", default=0),
            intn(g("days", default=0), 0),
            g("rate", "rate_per_day", "ratePerDay") or None))
    raise ApiError("未知计算类型：%s（可用：vat / vat_general / vat_small / surtax / cit / "
                   "cit_q / iit / iit_bonus / stamp / house / land / burden / three_flow / "
                   "late_fee）" % kind)


def api_calc_meta(u, b, q):
    """计算器元数据：税率表、税目、级距。"""
    return {
        "vatRates": [{"rate": k, "value": str(v)} for k, v in T.VAT_RATES.items()],
        "surtax": {k: str(v) for k, v in T.SURTAX.items()},
        "cityRates": {k: str(v) for k, v in T.SURTAX_CITY_RATES.items()},
        "stampDuty": [{"type": k, "rate": str(v)} for k, v in T.STAMP_DUTY.items()],
        "iitBrackets": [{"cap": (str(c) if c else None), "rate": str(r), "quick": str(qq)}
                        for c, r, qq in T.IIT_BRACKETS],
        "iitBonusBrackets": [{"cap": (str(c) if c else None), "rate": str(r), "quick": str(qq)}
                             for c, r, qq in T.IIT_BONUS_BRACKETS],
        "landGrades": [{"grade": k, "rate": str(v)} for k, v in sorted(T.LAND_TAX_GRADES.items())],
        "smallLimit": {"profit": str(T.CIT_SMALL_LIMIT["profit"]),
                       "staff": T.CIT_SMALL_LIMIT["staff"],
                       "assets": str(T.CIT_SMALL_LIMIT["assets"])},
    }


# ==================================================== 报表
def api_report_flow(u, b, q):
    """税负分析：按主体列出各税种税额与税负率。"""
    need(u, "report.read")
    period = (q.get("period") or [None])[0] or db.val(
        "SELECT MAX(period) FROM declarations", (), "2026-10")
    ents = db.rows("SELECT code,name,taxpayer_type,industry,small_profit,high_tech "
                   "FROM entities WHERE status='启用' ORDER BY code")
    out = []
    for e in ents:
        decls = db.rows("SELECT tax_type,SUM(tax_amount) t FROM declarations "
                        "WHERE entity=? AND period=? AND status<>'草稿' GROUP BY tax_type",
                        (e["code"], period))
        by = {d["tax_type"]: num(d["t"]) for d in decls}
        rev = num(db.val("SELECT SUM(amount) FROM invoices WHERE entity=? AND period=? "
                         "AND kind='销项' AND status='正常'", (e["code"], period), 0))
        total = sum(by.values())
        out.append({
            "entity": e["code"], "name": e["name"], "taxpayerType": e["taxpayer_type"],
            "industry": e["industry"], "revenue": round(rev, 2),
            "vat": round(by.get("增值税", 0), 2),
            "surtax": round(by.get("附加税费", 0), 2),
            "cit": round(by.get("企业所得税", 0), 2),
            "iit": round(by.get("个人所得税", 0), 2),
            "total": round(total, 2),
            "burden": round(total / rev * 100, 3) if rev else 0,
        })
    return {"period": period, "list": out,
            "sumRevenue": round(sum(x["revenue"] for x in out), 2),
            "sumTax": round(sum(x["total"] for x in out), 2)}


def api_report_trend(u, b, q):
    """月度趋势：销项/进项/应纳/申报总额。"""
    need(u, "report.read")
    entity = (q.get("entity") or [""])[0]
    where = " AND entity=?" if entity else ""
    args = (entity,) if entity else ()
    periods = [r["period"] for r in db.rows(
        "SELECT DISTINCT period FROM invoices ORDER BY period")]
    out = []
    for p in periods:
        o = num(db.val("SELECT SUM(tax) FROM invoices WHERE period=? AND kind='销项' "
                       "AND status='正常'" + where,
                       (p,) + args, 0))
        i2 = num(db.val("SELECT SUM(tax) FROM invoices WHERE period=? AND kind='进项' "
                        "AND status='正常' AND verify_status='已认证'" + where,
                        (p,) + args, 0))
        s = num(db.val("SELECT SUM(tax_amount) FROM declarations WHERE period=? "
                       "AND status<>'草稿'" + where, (p,) + args, 0))
        rev = num(db.val("SELECT SUM(amount) FROM invoices WHERE period=? AND kind='销项' "
                         "AND status='正常'" + where, (p,) + args, 0))
        out.append({"period": p, "output": round(o, 2), "input": round(i2, 2),
                    "vat": round(max(0.0, o - i2), 2), "declared": round(s, 2),
                    "revenue": round(rev, 2),
                    "burden": round(s / rev * 100, 3) if rev else 0})
    return {"list": out, "entity": entity}


def api_report_type(u, b, q):
    """按税种汇总。"""
    need(u, "report.read")
    period = (q.get("period") or [""])[0]
    where = " WHERE period=?" if period else ""
    args = (period,) if period else ()
    rows_ = db.rows(
        "SELECT tax_type AS name, ROUND(SUM(tax_amount),2) AS amount, "
        "ROUND(SUM(paid_amount),2) AS paid, COUNT(*) AS cnt, "
        "SUM(CASE WHEN status IN ('草稿','待申报') THEN 1 ELSE 0 END) AS pending "
        "FROM declarations" + where + " GROUP BY tax_type ORDER BY amount DESC", args)
    total = sum(num(r["amount"]) for r in rows_)
    for r in rows_:
        r["share"] = round(num(r["amount"]) / total * 100, 2) if total else 0
    return {"period": period or "全部", "list": rows_, "total": round(total, 2)}


def api_report_input(u, b, q):
    """进项抵扣结构分析。"""
    need(u, "report.read")
    period = (q.get("period") or [None])[0] or db.val(
        "SELECT MAX(period) FROM invoices", (), "2026-10")
    by_rate = db.rows(
        "SELECT tax_rate AS rate, COUNT(*) AS cnt, ROUND(SUM(amount),2) AS amount, "
        "ROUND(SUM(tax),2) AS tax FROM invoices WHERE period=? AND kind='进项' "
        "AND status='正常' GROUP BY tax_rate ORDER BY tax DESC", (period,))
    by_verify = db.rows(
        "SELECT verify_status AS status, COUNT(*) AS cnt, ROUND(SUM(tax),2) AS tax "
        "FROM invoices WHERE period=? AND kind='进项' AND status='正常' "
        "GROUP BY verify_status", (period,))
    by_supplier = db.rows(
        "SELECT seller_name AS name, COUNT(*) AS cnt, ROUND(SUM(tax),2) AS tax "
        "FROM invoices WHERE period=? AND kind='进项' AND status='正常' "
        "GROUP BY seller_name ORDER BY tax DESC LIMIT 10", (period,))
    return {"period": period, "byRate": by_rate, "byVerify": by_verify,
            "bySupplier": by_supplier}


def api_report_summary(u, b, q):
    """综合总览：一次返回税负/税种/进项/趋势四块，供大屏与外部系统取数。"""
    need(u, "report.read")
    period = (q.get("period") or [None])[0] or db.val(
        "SELECT MAX(period) FROM declarations", (), "2026-10")
    flow = api_report_flow(u, b, {"period": [period]})
    typ = api_report_type(u, b, {"period": [period]})
    inp = api_report_input(u, b, {"period": [period]})
    trend = api_report_trend(u, b, {"period": [period]})
    revenue = num(db.val("SELECT SUM(amount) FROM invoices WHERE period=? AND kind='销项' "
                         "AND status='正常'", (period,), 0))
    tax_total = num(typ.get("total"))
    return {
        "period": period,
        "revenue": round(revenue, 2),
        "taxTotal": round(tax_total, 2),
        "burden": round(tax_total / revenue * 100, 3) if revenue else 0,
        "byType": typ.get("list"),
        "byEntity": flow.get("list"),
        "input": {"byRate": inp.get("byRate"), "byVerify": inp.get("byVerify"),
                  "bySupplier": inp.get("bySupplier")},
        "trend": trend.get("list"),
    }


def api_report_export(u, b, q):
    """CSV 导出（UTF-8 BOM，Excel 直接打开不乱码）。"""
    need(u, "report.read")
    typ = (q.get("type") or ["declaration"])[0]
    period = (q.get("period") or [""])[0]
    if typ == "invoice":
        sql = ("SELECT no,kind,entity,invoice_type,seller_name,buyer_name,amount,"
               "tax_rate,tax,total,biz_date,period,status,verify_status "
               "FROM invoices WHERE 1=1")
        args = []
        if period:
            sql += " AND period=?"
            args.append(period)
        sql += " ORDER BY biz_date DESC"
        rows_ = db.rows(sql, tuple(args))
        head = ["发票号", "类型", "主体", "票种", "销方", "购方", "金额", "税率",
                "税额", "价税合计", "开票日期", "所属期", "状态", "认证状态"]
        keys = ["no", "kind", "entity", "invoice_type", "seller_name", "buyer_name",
                "amount", "tax_rate", "tax", "total", "biz_date", "period",
                "status", "verify_status"]
    else:
        sql = ("SELECT no,entity,tax_type,period,status,base_amount,tax_amount,"
               "paid_amount,due_date,filed_at FROM declarations WHERE 1=1")
        args = []
        if period:
            sql += " AND period=?"
            args.append(period)
        sql += " ORDER BY period DESC, entity"
        rows_ = db.rows(sql, tuple(args))
        head = ["申报单号", "主体", "税种", "所属期", "状态", "计税依据",
                "应纳税额", "已缴", "申报期限", "申报时间"]
        keys = ["no", "entity", "tax_type", "period", "status", "base_amount",
                "tax_amount", "paid_amount", "due_date", "filed_at"]
    lines = [",".join(head)]
    for r in rows_:
        lines.append(",".join('"%s"' % str(r.get(k, "") if r.get(k) is not None else "")
                              for k in keys))
    return "\ufeff" + "\n".join(lines)


# ==================================================== 风险
def api_risks(u, b, q):
    need(u, "risk.read")
    status = (q.get("status") or [""])[0]
    level = (q.get("level") or [""])[0]
    entity = (q.get("entity") or [""])[0]
    sql = "SELECT r.*,e.name AS entity_name FROM risks r LEFT JOIN entities e ON e.code=r.entity WHERE 1=1"
    args = []
    for col, v in (("r.status", status), ("r.level", level), ("r.entity", entity)):
        if v:
            sql += " AND %s=?" % col
            args.append(v)
    sql += " ORDER BY CASE r.level WHEN '险' THEN 0 WHEN '警' THEN 1 ELSE 2 END, r.weight DESC"
    rows_ = db.rows(sql, tuple(args))
    sc = T.risk_score([{"weight": r["weight"]} for r in rows_ if r["status"] == "待处理"])
    return {"list": fmt(rows_), "total": len(rows_), "count": len(rows_), "openScore": sc}


def api_risk_scan(u, b, q):
    """重新扫描：对指定期间跑一遍规则，生成/更新风险信号。"""
    need(u, "risk.read")
    b = b or {}
    period = (b.get("period") or db.val("SELECT MAX(period) FROM invoices", (), "2026-10")).strip()
    ents = db.rows("SELECT * FROM entities WHERE status='启用'")
    created = []
    for e in ents:
        # 1) 三流不一致
        bad = db.rows(
            "SELECT * FROM invoices WHERE entity=? AND period=? AND status='正常' "
            "AND contract_amount>0 AND ABS(amount-contract_amount)>0.01", (e["code"], period))
        for inv in bad:
            created.append(_mk_risk(e["code"], period, "CONTRACT_MISMATCH", "险",
                                    "进项发票金额与合同金额不一致",
                                    "发票 %s 金额 %.2f，合同 %.2f，差额 %.2f"
                                    % (inv["no"], inv["amount"], inv["contract_amount"],
                                       inv["amount"] - inv["contract_amount"]), 35))
        # 2) 销方税号缺失
        notax = db.rows(
            "SELECT * FROM invoices WHERE entity=? AND period=? AND kind='进项' "
            "AND status='正常' AND (seller_tax_no IS NULL OR seller_tax_no='')",
            (e["code"], period))
        for inv in notax:
            created.append(_mk_risk(e["code"], period, "NO_TAX_NO", "警",
                                    "进项发票销方税号为空",
                                    "发票 %s 销方纳税人识别号缺失，不得作为抵扣凭证"
                                    % inv["no"], 20))
        # 3) 进项长期未认证
        unverified = num(db.val(
            "SELECT SUM(tax) FROM invoices WHERE entity=? AND period=? AND kind='进项' "
            "AND status='正常' AND verify_status<>'已认证'", (e["code"], period), 0))
        if unverified > 100000:
            created.append(_mk_risk(e["code"], period, "UNVERIFIED_INPUT", "警",
                                    "大额进项未认证",
                                    "本期未认证进项税额 %.2f 元，逾期不得抵扣" % unverified, 20))
        # 4) 税负率异常
        rev = num(db.val("SELECT SUM(amount) FROM invoices WHERE entity=? AND period=? "
                         "AND kind='销项' AND status='正常'", (e["code"], period), 0))
        if rev > 0:
            total_tax = num(db.val(
                "SELECT SUM(tax_amount) FROM declarations WHERE entity=? AND period=? "
                "AND status<>'草稿'", (e["code"], period), 0))
            burden = total_tax / rev
            ind_avg = D("0.0285") if e["industry"] not in ("商务服务", "文化传媒") else D("0.0315")
            al = T.burden_alert(burden, ind_avg, D(db.rule("burden_tolerance", "0.30")))
            if al["alert"]:
                created.append(_mk_risk(e["code"], period, "BURDEN_DEV", "警",
                                        "税负率偏离行业均值", al["message"], 30))
        # 5) 小规模接近起征点
        if e["taxpayer_type"] == "小规模纳税人":
            sales = num(db.val("SELECT SUM(amount) FROM invoices WHERE entity=? AND period=? "
                               "AND kind='销项' AND status='正常'", (e["code"], period), 0))
            if 90000 <= sales < 100000:
                created.append(_mk_risk(e["code"], period, "SMALL_THRESHOLD", "提",
                                        "小规模纳税人接近起征点",
                                        "本期销售额 %.2f 元，距 10 万起征点仅 %.2f 元"
                                        % (sales, 100000 - sales), 10))
    db.bumpsync("risks")
    log(u, "风险扫描", period, "新增 %d 条" % len(created))
    return {"period": period, "created": len(created), "items": created}


def _mk_risk(entity, period, code, level, title, detail, weight):
    old = db.one("SELECT id FROM risks WHERE entity=? AND period=? AND code=? AND status<>'已整改'",
                 (entity, period, code))
    if old:
        return {"id": old["id"], "skipped": True, "code": code}
    db.insert("risks", {"entity": entity, "period": period, "code": code, "level": level,
                        "title": title, "detail": detail, "weight": weight,
                        "status": "待处理", "handler": "", "created_at": db.now(),
                        "closed_at": ""})
    return {"id": db.val("SELECT MAX(id) FROM risks", (), 0), "code": code, "title": title}


def api_risk_close(u, b, q, rid):
    need(u, "risk.read")
    r = db.one("SELECT * FROM risks WHERE id=?", (rid,))
    if not r:
        raise ApiError("风险记录不存在", 404)
    db.run("UPDATE risks SET status='已整改', handler=?, closed_at=? WHERE id=?",
           (u["username"], db.now(), rid))
    db.bumpsync("risks")
    log(u, "整改风险", str(rid), r["title"])
    return {"id": rid, "status": "已整改"}


# ==================================================== 凭证 / 合同
def api_vouchers(u, b, q):
    need(u, "voucher.read")
    entity = (q.get("entity") or [""])[0]
    period = (q.get("period") or [""])[0]
    tax_type = (q.get("tax_type") or [""])[0]
    sql = "SELECT * FROM vouchers WHERE 1=1"
    args = []
    for col, v in (("entity", entity), ("period", period), ("tax_type", tax_type)):
        if v:
            sql += " AND %s=?" % col
            args.append(v)
    sql += " ORDER BY period DESC, no DESC LIMIT 400"
    rows_ = db.rows(sql, tuple(args))
    return {"list": fmt(rows_), "total": len(rows_), "count": len(rows_),
            "sumDebit": round(sum(num(r["debit"]) for r in rows_), 2),
            "sumCredit": round(sum(num(r["credit"]) for r in rows_), 2)}


def api_voucher_save(u, b, q):
    need(u, "voucher.write")
    b = b or {}
    if not (b.get("entity") or "").strip():
        raise ApiError("纳税主体必填")
    no = (b.get("no") or "").strip() or db.gen_no("vouchers", "PZ")
    old = db.one("SELECT * FROM vouchers WHERE no=?", (no,))
    d = num(b.get("debit"))
    c = num(b.get("credit"))
    data = {
        "no": no, "entity": b.get("entity"), "period": b.get("period") or db.today()[:7],
        "vdate": b.get("vdate") or db.today(), "summary": b.get("summary") or "",
        "account": b.get("account") or "2221 应交税费", "debit": d, "credit": c,
        "tax_type": b.get("tax_type") or "", "src": b.get("src") or "手工",
        "memo": b.get("memo") or "",
    }
    if old:
        db.update("vouchers", "no", no, data)
    else:
        data["created_by"] = u["username"]
        data["created_at"] = db.now()
        db.insert("vouchers", data)
    db.bumpsync("vouchers")
    log(u, "保存凭证", no)
    return {"no": no, "created": not bool(old)}


def api_contracts(u, b, q):
    need(u, "voucher.read")
    entity = (q.get("entity") or [""])[0]
    sql = ("SELECT c.*,e.name AS entity_name FROM contracts c "
           "LEFT JOIN entities e ON e.code=c.entity WHERE 1=1")
    args = []
    if entity:
        sql += " AND c.entity=?"
        args.append(entity)
    sql += " ORDER BY c.sign_date DESC, c.no DESC LIMIT 300"
    rows_ = db.rows(sql, tuple(args))
    return {"list": fmt(rows_), "total": len(rows_), "count": len(rows_),
            "sumAmount": round(sum(num(r["amount"]) for r in rows_), 2),
            "sumStamp": round(sum(num(r["stamp_tax"]) for r in rows_), 2)}


def api_contract_save(u, b, q):
    need(u, "voucher.write")
    b = b or {}
    ctype = b.get("ctype") or "买卖合同"
    amt = num(b.get("amount"))
    sd = T.stamp_duty(ctype, amt, bool(b.get("vat_excluded", True)))
    no = (b.get("no") or "").strip() or db.gen_no("contracts", "HT")
    old = db.one("SELECT * FROM contracts WHERE no=?", (no,))
    data = {
        "no": no, "entity": b.get("entity") or "", "ctype": ctype,
        "title": b.get("title") or "", "party": b.get("party") or "",
        "amount": amt, "vat_excluded": 1 if b.get("vat_excluded", True) else 0,
        "sign_date": b.get("sign_date") or db.today(),
        "stamp_tax": float(sd["tax"]),
        "stamp_paid": 1 if b.get("stamp_paid") else 0,
        "status": b.get("status") or "执行中", "memo": b.get("memo") or "",
    }
    if old:
        db.update("contracts", "no", no, data)
    else:
        data["created_at"] = db.now()
        db.insert("contracts", data)
    db.bumpsync("contracts")
    log(u, "保存合同", no, ctype)
    return {"no": no, "created": not bool(old), "stampTax": float(sd["tax"])}


# ==================================================== 政策库
def api_policies(u, b, q):
    need(u, "policy.read")
    tax_type = (q.get("tax_type") or [""])[0]
    kw = (q.get("kw") or [""])[0]
    sql = "SELECT * FROM policies WHERE 1=1"
    args = []
    if tax_type:
        sql += " AND tax_type=?"
        args.append(tax_type)
    if kw:
        sql += " AND (title LIKE ? OR summary LIKE ? OR tags LIKE ?)"
        args += ["%%%s%%" % kw] * 3
    sql += " ORDER BY effect_date DESC, id DESC"
    return listwrap(fmt(db.rows(sql, tuple(args))))


def api_policy_get(u, b, q, pid):
    need(u, "policy.read")
    r = db.one("SELECT * FROM policies WHERE id=?", (pid,))
    if not r:
        raise ApiError("政策不存在", 404)
    return fmt(r)


# ==================================================== 组织
def api_depts(u, b, q):
    need(u, "tax.read")
    rows_ = db.rows("SELECT * FROM depts ORDER BY sort, code")
    for r in rows_:
        r["headcount"] = db.val("SELECT COUNT(*) FROM users WHERE dept=?", (r["code"],), 0)
        r["leaderName"] = db.val("SELECT name FROM users WHERE username=?", (r["leader"],), "")
    return listwrap(fmt(rows_))


def api_users(u, b, q):
    need(u, "org.read")
    return listwrap(fmt(db.rows(
        "SELECT u.username,u.name,u.dept,u.title,u.role,u.phone,u.email,u.status,"
        "d.name AS deptName FROM users u LEFT JOIN depts d ON d.code=u.dept "
        "ORDER BY u.dept,u.username")))


def api_user_save(u, b, q):
    need(u, "org.write")
    b = b or {}
    un = (b.get("username") or "").strip()
    nm = (b.get("name") or "").strip()
    if not un or not nm:
        raise ApiError("username 与 name 必填")
    role = b.get("role") or "reader"
    if role not in T.ROLE_PERMS:
        raise ApiError("角色不存在：%s" % role)
    old = db.one("SELECT * FROM users WHERE username=?", (un,))
    data = {"username": un, "name": nm, "dept": b.get("dept") or "",
            "title": b.get("title") or "", "role": role,
            "phone": b.get("phone") or "", "email": b.get("email") or "",
            "status": b.get("status") or "启用"}
    if old:
        db.update("users", "username", un, data)
        if b.get("password"):
            db.run("UPDATE users SET pwd=? WHERE username=?", (sha(b["password"]), un))
    else:
        data["pwd"] = sha(b.get("password") or "123456")
        data["created_at"] = db.now()
        db.insert("users", data)
    log(u, "保存用户", un)
    return {"username": un, "created": not bool(old)}


def api_roles(u, b, q):
    out = []
    for code, perms in T.ROLE_PERMS.items():
        out.append({
            "code": code, "label": ROLE_LABELS.get(code, code),
            "users": db.val("SELECT COUNT(*) FROM users WHERE role=?", (code,), 0),
            "perms": sorted(perms),
        })
    out.sort(key=lambda x: -x["users"])
    return listwrap(out)


# ==================================================== 系统
def api_rules(u, b, q):
    need(u, "tax.read")
    return db.all_rules()


def api_rule_save(u, b, q):
    need(u, "system.write")
    rules = (b or {}).get("rules") or {}
    for k, v in rules.items():
        if k in T.DEFAULT_RULES:
            db.set_rule(k, v)
    log(u, "修改规则", ",".join(rules.keys()))
    return db.all_rules()


def api_logs(u, b, q):
    need(u, "system.read")
    limit = min(500, intn((q.get("limit") or ["200"])[0], 200))
    return listwrap(fmt(db.rows("SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,))))


def api_keys_list(u, b, q):
    need(u, "system.read")
    return listwrap(fmt(db.rows("SELECT id,name,prefix,scope,owner,status,created_at,"
                       "last_used FROM api_keys ORDER BY id DESC")))


def api_keys_create(u, b, q):
    need(u, "system.write")
    b = b or {}
    name = (b.get("name") or "").strip()
    if not name:
        raise ApiError("密钥名称必填")
    scope = b.get("scope") or "read"
    if scope not in ("read", "write", "full"):
        raise ApiError("scope 应为 read / write / full")
    raw = "sk_" + os.urandom(24).hex()
    db.insert("api_keys", {"name": name, "key_hash": sha(raw), "prefix": raw[:10],
                           "scope": scope, "owner": u["username"], "status": "启用",
                           "created_at": db.now(), "last_used": ""})
    log(u, "创建密钥", name, scope)
    return {"name": name, "key": raw, "scope": scope,
            "note": "密钥仅显示一次，请立即保存"}


def api_keys_delete(u, b, q, kid):
    need(u, "system.write")
    db.run("DELETE FROM api_keys WHERE id=?", (kid,))
    log(u, "删除密钥", str(kid))
    return {"ok": True}


def api_notices(u, b, q):
    need(u, "tax.read")
    return listwrap(fmt(db.rows("SELECT * FROM notices ORDER BY top DESC, id DESC")))


def api_tax_types(u, b, q):
    need(u, "tax.read")
    return listwrap(fmt(db.rows("SELECT * FROM tax_types ORDER BY sort")))


# ==================================================== 增量同步 / 对外
SYNC_ENTITIES = {
    "entities": "SELECT * FROM entities",
    "invoices": "SELECT * FROM invoices",
    "declarations": "SELECT * FROM declarations",
    "vouchers": "SELECT * FROM vouchers",
    "contracts": "SELECT * FROM contracts",
    "risks": "SELECT * FROM risks",
    "policies": "SELECT * FROM policies",
}


def api_sync_version(u, b, q):
    return {e: db.version_of(e) for e in SYNC_ENTITIES}


def api_sync(u, b, q):
    """增量同步：?version=N&entities=invoices,declarations
    返回各实体当前版本与全量数据（版本变化时才返回数据）。"""
    ents = (q.get("entities") or [",".join(SYNC_ENTITIES.keys())])[0]
    want = (q.get("version") or ["0"])[0]
    want_map = {}
    for kv in str(want).split(","):
        if ":" in kv:
            k, v = kv.split(":", 1)
            want_map[k.strip()] = intn(v)
    out = {}
    for e in [x.strip() for x in ents.split(",") if x.strip()]:
        if e not in SYNC_ENTITIES:
            continue
        cur = db.version_of(e)
        since = want_map.get(e, 0)
        if cur <= since:
            out[e] = {"version": cur, "changed": False, "rows": []}
        else:
            out[e] = {"version": cur, "changed": True,
                      "rows": fmt(db.rows(SYNC_ENTITIES[e]))}
    return out


def api_apidoc(u, b, q):
    """返回 OpenAPI 3.0 描述（供对接方导入）。"""
    paths = {}
    for m, pat, fn, perm in ROUTES:
        p = pat.replace("^", "").replace("$", "")
        p = re.sub(r"\(\[\\w\\-\]\+\)", "{no}", p)
        p = re.sub(r"\(\\d\+\)", "{id}", p)
        if not p.startswith("/api/"):
            continue
        paths.setdefault(p, {})[m.lower()] = {
            "summary": (fn.__name__ if hasattr(fn, "__name__") else "handler"),
            "permission": perm or "public",
            "responses": {"200": {"description": "统一响应包 {code,message,data}"}},
        }
    return {
        "openapi": "3.0.3",
        "info": {"title": BRAND, "version": VERSION,
                 "description": "飞税税务管理系统对外接口，统一响应 {code,message,data}"},
        "servers": [{"url": PREFIX or "/"}],
        "components": {"securitySchemes": {
            "bearer": {"type": "http", "scheme": "bearer"},
            "apiKey": {"type": "apiKey", "in": "header", "name": "X-Tax-Key"},
        }},
        "security": [{"bearer": []}, {"apiKey": []}],
        "paths": paths,
    }


# ==================================================== 路由表
ROUTES = [
    ("GET", r"^/api/health$", api_health, None),
    ("GET", r"^/api/apidoc$", api_apidoc, None),
    ("POST", r"^/api/auth/login$", api_login, None),
    ("POST", r"^/api/auth/logout$", api_logout, None),
    ("GET", r"^/api/auth/me$", api_me, None),
    ("POST", r"^/api/auth/change-password$", api_change_pwd, None),

    ("GET", r"^/api/dashboard$", api_dashboard, "tax.read"),

    ("GET", r"^/api/entities$", api_entities, "entity.read"),
    ("GET", r"^/api/entities/([\w\-]+)$", api_entity_get, "entity.read"),
    ("POST", r"^/api/entities/save$", api_entity_save, "entity.write"),

    ("GET", r"^/api/invoices$", api_invoices, "invoice.read"),
    ("GET", r"^/api/invoices/([\w\-]+)$", api_invoice_get, "invoice.read"),
    ("POST", r"^/api/invoices/save$", api_invoice_save, "invoice.write"),
    ("POST", r"^/api/invoices/([\w\-]+)/void$", api_invoice_void, "invoice.void"),
    ("POST", r"^/api/invoices/verify$", api_invoice_verify, "input.verify"),

    ("GET", r"^/api/declarations$", api_declarations, "tax.read"),
    ("GET", r"^/api/declarations/([\w\-]+)$", api_decl_get, "tax.read"),
    ("POST", r"^/api/declarations/calc$", api_decl_calc, "tax.calc"),
    ("POST", r"^/api/declarations/save$", api_decl_save, "tax.declare"),
    ("POST", r"^/api/declarations/([\w\-]+)/file$", api_decl_file, "tax.declare"),
    ("POST", r"^/api/declarations/([\w\-]+)/pay$", api_decl_pay, "tax.declare"),
    ("POST", r"^/api/declarations/([\w\-]+)/delete$", api_decl_delete, "tax.declare"),

    ("POST", r"^/api/calc$", api_calc, "tax.read"),
    ("GET", r"^/api/calc/meta$", api_calc_meta, "tax.read"),

    ("GET", r"^/api/reports/flow$", api_report_flow, "report.read"),
    ("GET", r"^/api/reports/trend$", api_report_trend, "report.read"),
    ("GET", r"^/api/reports/type$", api_report_type, "report.read"),
    ("GET", r"^/api/reports/input$", api_report_input, "report.read"),
    ("GET", r"^/api/reports/summary$", api_report_summary, "report.read"),
    ("GET", r"^/api/reports/export$", api_report_export, "report.read"),

    ("GET", r"^/api/risks$", api_risks, "risk.read"),
    ("POST", r"^/api/risks/scan$", api_risk_scan, "risk.read"),
    ("POST", r"^/api/risks/(\d+)/close$", api_risk_close, "risk.read"),

    ("GET", r"^/api/vouchers$", api_vouchers, "voucher.read"),
    ("POST", r"^/api/vouchers/save$", api_voucher_save, "voucher.write"),
    ("GET", r"^/api/contracts$", api_contracts, "voucher.read"),
    ("POST", r"^/api/contracts/save$", api_contract_save, "voucher.write"),

    ("GET", r"^/api/policies$", api_policies, "policy.read"),
    ("GET", r"^/api/policies/(\d+)$", api_policy_get, "policy.read"),

    ("GET", r"^/api/depts$", api_depts, "tax.read"),
    ("GET", r"^/api/users$", api_users, "org.read"),
    ("POST", r"^/api/users/save$", api_user_save, "org.write"),
    ("GET", r"^/api/roles$", api_roles, None),

    ("GET", r"^/api/rules$", api_rules, "tax.read"),
    ("POST", r"^/api/rules/save$", api_rule_save, "system.write"),
    ("GET", r"^/api/logs$", api_logs, "system.read"),
    ("GET", r"^/api/api-keys$", api_keys_list, "system.read"),
    ("POST", r"^/api/api-keys/create$", api_keys_create, "system.write"),
    ("POST", r"^/api/api-keys/(\d+)/delete$", api_keys_delete, "system.write"),

    ("GET", r"^/api/notices$", api_notices, "tax.read"),
    ("GET", r"^/api/tax-types$", api_tax_types, "tax.read"),

    ("GET", r"^/api/sync$", api_sync, None),
    ("GET", r"^/api/sync/version$", api_sync_version, None),
]

COMPILED = [(m, re.compile(p), fn, perm) for m, p, fn, perm in ROUTES]
PUBLIC = {"/api/health", "/api/sync/version", "/api/auth/login", "/api/apidoc"}

MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
}


# ==================================================== Handler
class Handler(BaseHTTPRequestHandler):
    server_version = "FeiShuiTax/" + VERSION
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt_, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt_ % args))

    # ---------------- 响应
    def _send(self, code, payload, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(payload, (dict, list)):
            body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        elif isinstance(payload, bytes):
            body = payload
        else:
            body = str(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type,Authorization,"
                         "X-Tax-Token,X-Tax-Key,Idempotency-Key")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _ok(self, data, extra=None):
        self._send(200, {"code": 200, "message": "ok", "data": data}, extra=extra)

    def _err(self, code, message):
        self._send(code, {"code": code, "message": message, "data": None})

    # ---------------- 鉴权
    def _auth(self, path):
        value = self.headers.get("Authorization") or ""
        u = user_by_token(value)
        if u:
            return u
        u = user_by_token(self.headers.get("X-Tax-Token"))
        if u:
            return u
        ck = self.headers.get("Cookie") or ""
        m = re.search(r"tax_token=([^;]+)", ck)
        if m:
            u = user_by_token(urllib.parse.unquote(m.group(1)))
            if u:
                return u
        qs = urllib.parse.urlparse(self.path).query
        qv = urllib.parse.parse_qs(qs)
        if qv.get("token"):
            u = user_by_token(qv["token"][0])
            if u:
                return u
        u = user_by_apikey(self.headers.get("X-Tax-Key"))
        if u:
            return u
        return None

    def _idem(self, username, path):
        key = self.headers.get("Idempotency-Key")
        if not key:
            return None
        r = db.one("SELECT * FROM idem_keys WHERE key=?", (key,))
        if not r:
            return None
        return jloads(r["body"], {})

    def _idem_save(self, username, path, key, body):
        if not key:
            return
        db.run("INSERT OR REPLACE INTO idem_keys (key,username,path,status,body,created_at) "
               "VALUES (?,?,?,?,?,?)",
               (key, username, path, 200, jdumps(body), db.now()))

    def _dispatch(self, method):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if PREFIX and path.startswith(PREFIX):
            path = path[len(PREFIX):] or "/"
        q = urllib.parse.parse_qs(parsed.query)
        ip = self.client_address[0] if self.client_address else ""

        if path.startswith("/api/"):
            u = self._auth(path)
            if any(path == p for p in PUBLIC):
                u = u or {"username": "__anon__", "name": "匿名", "role": "reader",
                          "perms": ["tax.read"]}
            if not u:
                return self._err(401, "未登录或凭证已失效")
            body = {}
            if method == "POST":
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    raw = self.rfile.read(n) if n else b"{}"
                    body = json.loads(raw.decode("utf-8") or "{}")
                except Exception:                            # noqa: BLE001
                    return self._err(400, "请求体不是合法 JSON")

            idem_key = self.headers.get("Idempotency-Key")
            if method == "POST" and idem_key:
                cached = self._idem(u["username"], path)
                if cached:
                    return self._send(cached.get("code", 200), cached)

            for m, pat, fn, perm in COMPILED:
                if m != method:
                    continue
                mm = pat.match(path)
                if not mm:
                    continue
                try:
                    if perm:
                        need(u, perm)
                    args = mm.groups()
                    if method == "POST" and fn is api_calc:
                        data = fn(u, body, q)
                    elif method == "POST" and len(args) == 1 and \
                            fn.__name__ in ("api_invoice_void", "api_decl_file",
                                            "api_decl_pay", "api_decl_delete",
                                            "api_risk_close", "api_keys_delete"):
                        data = fn(u, body, q, args[0])
                    elif method == "GET" and args:
                        data = fn(u, body, q, args[0])
                    else:
                        data = fn(u, body, q)
                except ApiError as e:
                    return self._err(e.code, e.message)
                except T.TaxError as e:
                    return self._err(400, str(e))
                except Exception as e:                        # noqa: BLE001
                    traceback.print_exc()
                    return self._err(500, "服务器开小差了：%s" % e)

                if isinstance(data, str) and fn is api_report_export:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/csv; charset=utf-8")
                    self.send_header("Content-Disposition",
                                     'attachment; filename="export.csv"')
                    body_bytes = data.encode("utf-8")
                    self.send_header("Content-Length", str(len(body_bytes)))
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    try:
                        self.wfile.write(body_bytes)
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                    return
                payload = {"code": 200, "message": "ok", "data": data}
                if method == "POST" and idem_key:
                    self._idem_save(u["username"], path, idem_key, payload)
                return self._send(200, payload)
            return self._err(404, "接口不存在：%s %s" % (method, path))

        # 静态文件
        rel = path.lstrip("/") or "index.html"
        rel = rel.split("?")[0]
        safe = os.path.normpath(os.path.join(FRONTEND, rel))
        if not safe.startswith(os.path.normpath(FRONTEND)):
            return self._err(403, "禁止访问")
        if os.path.isdir(safe):
            safe = os.path.join(safe, "index.html")
        if os.path.isfile(safe):
            ext = os.path.splitext(safe)[1].lower()
            with open(safe, "rb") as f:
                return self._send(200, f.read(), MIME.get(ext, "application/octet-stream"))
        if rel in ("", "index.html"):
            idx = os.path.join(FRONTEND, "login.html")
            if os.path.isfile(idx):
                with open(idx, "rb") as f:
                    return self._send(200, f.read(), MIME[".html"])
        return self._send(404, "404 Not Found", "text/plain; charset=utf-8")

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_OPTIONS(self):
        self._send(200, b"", "text/plain", {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Tax-Token,"
                                            "X-Tax-Key,Idempotency-Key",
        })


def main():
    db.init()
    created = seedmod.seed()
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("%s v%s | port=%d prefix=%r db=%s seed=%s routes=%d"
          % (BRAND, VERSION, PORT, PREFIX, db.DB_PATH, created, len(ROUTES)))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
