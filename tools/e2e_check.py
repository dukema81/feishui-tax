# -*- coding: utf-8 -*-
"""飞税后端端到端连通性验证（进程内起服务，不依赖子进程）"""
import json
import os
import sys
import tempfile
import threading
import urllib.request
import urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

DBP = os.path.join(tempfile.gettempdir(), "feishui_e2e.db")
for f in (DBP, DBP + "-wal", DBP + "-shm"):
    if os.path.exists(f):
        os.remove(f)
os.environ["TAX_DB"] = DBP

import db          # noqa: E402
import seed        # noqa: E402
import server      # noqa: E402

db.init()
seed.seed()

SRV = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
PORT = SRV.server_address[1]
threading.Thread(target=SRV.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:%d" % PORT
print("server on", BASE)

PASS = []
FAIL = []


def call(method, path, body=None, token=None, headers=None):
    url = BASE + path
    data = None
    h = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    if token:
        h["Authorization"] = "Bearer " + token
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read().decode()
            return r.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw[:200]}


def call_raw(method, path, token=None):
    """返回原始字节，用于 CSV 等非 JSON 响应。"""
    h = {}
    if token:
        h["Authorization"] = "Bearer " + token
    req = urllib.request.Request(BASE + path, headers=h, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def check(name, cond, extra=""):
    if cond:
        PASS.append(name)
        print("  OK   " + name)
    else:
        FAIL.append(name + " " + str(extra)[:200])
        print("  FAIL " + name + " " + str(extra)[:200])


# ---- 1. health
st, r = call("GET", "/api/health")
check("health", st == 200 and r.get("code") == 200, r)

# ---- 2. login
st, r = call("POST", "/api/auth/login", {"username": "admin", "password": "tax@2026"})
check("login", st == 200 and r.get("data", {}).get("token"), r)
TOKEN = r["data"]["token"] if r.get("data") else ""

st, r = call("POST", "/api/auth/login", {"username": "admin", "password": "bad"})
check("login-bad", st == 401, (st, r))

# ---- 3. me
st, r = call("GET", "/api/auth/me", token=TOKEN)
_me = r.get("data") or {}
if isinstance(_me, dict) and "user" in _me:
    _me = _me["user"]
check("me", st == 200 and _me.get("role") == "admin", str(r)[:200])

# ---- 4. dashboard
st, r = call("GET", "/api/dashboard", token=TOKEN)
check("dashboard", st == 200 and isinstance(r.get("data"), dict), r)
dash = r.get("data") or {}

# ---- 5. 主数据
for p, key in [("/api/depts", "list"), ("/api/users", "list"), ("/api/entities", "list"),
               ("/api/tax-types", "list"), ("/api/policies", "list")]:
    st, r = call("GET", p, token=TOKEN)
    dd = r.get("data") or {}
    n = dd.get("total", 0) if isinstance(dd, dict) else 0
    check("GET " + p + " (n=%d)" % n, st == 200 and n > 0, str(r)[:160])

# ---- 6. 发票
st, r = call("GET", "/api/invoices?kind=%E9%94%80%E9%A1%B9", token=TOKEN)
d = r.get("data") or {}
check("invoices-销项", st == 200 and (d.get("total") or 0) > 0, d.get("total"))
INV_ID = (d.get("list") or [{}])[0].get("no")

st, r = call("GET", "/api/invoices?kind=%E8%BF%9B%E9%A1%B9", token=TOKEN)
check("invoices-进项", st == 200 and (r.get("data") or {}).get("total", 0) > 0, r)

st, r = call("GET", "/api/invoices/%s" % INV_ID, token=TOKEN)
check("invoice-detail", st == 200 and (r.get("data") or {}).get("no") == INV_ID, str(r)[:160])

st, r = call("GET", "/api/invoices?q=90000001", token=TOKEN)
check("invoice-search", st == 200 and (r.get("data") or {}).get("total", 0) >= 1, r)

# ---- 7. 申报单
st, r = call("GET", "/api/declarations", token=TOKEN)
check("declarations", st == 200 and (r.get("data") or {}).get("total", 0) > 0, str(r)[:160])
DECL_ID = ((r.get("data") or {}).get("list") or [{}])[0].get("no")

st, r = call("GET", "/api/declarations/%s" % DECL_ID, token=TOKEN)
check("declaration-detail", st == 200 and (r.get("data") or {}).get("no") == DECL_ID, str(r)[:160])

# ---- 8. 计算引擎（经 API）
calcs = [
    ("vat", {"kind": "vat", "amount": "100000", "taxRate": "13%", "inclusive": False},
     lambda d: abs(d.get("tax", 0) - 13000) < 0.01),
    ("vat-别名", {"kind": "vat_invoice", "amount": "113000", "taxRate": "13%",
                  "inclusive": True}, lambda d: abs(d.get("tax", 0) - 13000) < 0.02),
    ("vat_small-免征", {"kind": "vat_small", "sales": "250000", "quarterly": True},
     lambda d: d.get("tax", -1) == 0),
    ("vat_small-1%", {"kind": "vat_small", "sales": "350000", "quarterly": True},
     lambda d: abs(d.get("tax", 0) - 3500) < 1),
    ("vat_general", {"kind": "vat_general",
                     "outputs": [{"amount": 1000000, "rate": "13%"}],
                     "inputs": [{"amount": 500000, "rate": "13%"}]},
     lambda d: abs(d.get("payable", d.get("tax", 0)) - 65000) < 1),
    ("surtax", {"kind": "surtax", "vat_payable": "100000", "city_type": "市区",
                "small": True}, lambda d: abs(d.get("total", 0) - 6000) < 1),
    ("cit", {"kind": "cit", "profit": "2800000", "small_profit": True},
     lambda d: abs(d.get("tax", 0) - 140000) < 1),
    ("iit", {"kind": "iit", "taxable_income": "200000"},
     lambda d: abs(d.get("tax", 0) - 23080) < 1),
    ("iit_bonus", {"kind": "iit_bonus", "bonus": "100000", "mode": "separate"},
     lambda d: d.get("tax") is not None or isinstance(d.get("separate"), dict)),
    ("stamp", {"kind": "stamp", "type": "买卖合同", "amount": "1000000"},
     lambda d: abs(d.get("tax", 0) - 300) < 0.01),
    ("house", {"kind": "house", "mode": "value", "original_value": "5000000"},
     lambda d: abs(d.get("tax", 0) - 42000) < 1),
    ("land", {"kind": "land", "area": "1000", "grade": 3},
     lambda d: abs(d.get("tax", 0) - 18000) < 1),
    ("burden", {"kind": "burden", "revenue": "4000000", "vat": "120000"},
     lambda d: d.get("burden") is not None or d.get("rate") is not None),
    ("three_flow", {"kind": "three_flow", "invoice": {"no": "X1", "seller_name": "A",
                                                      "buyer_name": "B", "amount": "100",
                                                      "contract_party": "C"}},
     lambda d: "ok" in d),
    ("late_fee", {"kind": "late_fee", "tax": "10000", "days": 10},
     lambda d: abs(d.get("fee", 0) - 50) < 0.01),
]
for item in calcs:
    name, payload = item[0], item[1]
    pred = item[2] if len(item) > 2 else (lambda d: True)
    st, r = call("POST", "/api/calc", payload, token=TOKEN)
    dd = r.get("data") or {}
    ok = st == 200 and isinstance(dd, dict) and bool(pred(dd))
    check("calc-" + name, ok, (st, str(r)[:200]))

st, r = call("GET", "/api/calc/meta", token=TOKEN)
check("calc-meta", st == 200 and isinstance(r.get("data"), dict), r)

# ---- 9. 报表
for p in ["/api/reports/flow", "/api/reports/trend", "/api/reports/type",
          "/api/reports/input", "/api/reports/summary"]:
    st, r = call("GET", p, token=TOKEN)
    check("GET " + p, st == 200, (st, str(r)[:160]))

st, raw = call_raw("GET", "/api/reports/export?type=invoice", token=TOKEN)
check("reports-export-csv", st == 200 and raw[:3] == b"\xef\xbb\xbf" and len(raw) > 500,
      (st, len(raw)))
st, raw = call_raw("GET", "/api/reports/export?type=declaration", token=TOKEN)
check("reports-export-decl", st == 200 and b"\xef\xbb\xbf" == raw[:3], (st, len(raw)))

# ---- 10. 风险
st, r = call("GET", "/api/risks", token=TOKEN)
risks = (r.get("data") or {}).get("list") or []
check("risks (n=%d)" % len(risks), st == 200 and len(risks) > 0, r)

st, r = call("POST", "/api/risks/scan", {}, token=TOKEN)
check("risks-scan", st == 200, (st, str(r)[:200]))

# ---- 11. 凭证 / 合同
for p in ["/api/vouchers", "/api/contracts", "/api/notices", "/api/logs"]:
    st, r = call("GET", p, token=TOKEN)
    n = (r.get("data") or {}).get("total", 0)
    check("GET %s (total=%d)" % (p, n), st == 200, (st, str(r)[:160]))

# ---- 12. apidoc / sync
st, r = call("GET", "/api/apidoc")
_ad = r.get("data") or {}
check("apidoc", st == 200 and (_ad.get("paths") or _ad.get("routes")),
      (st, list(_ad.keys())[:8]))

st, r = call("GET", "/api/sync/version", token=TOKEN)
check("sync-version", st == 200, r)

st, r = call("GET", "/api/sync", token=TOKEN)
check("sync", st == 200 and isinstance(r.get("data"), dict), (st, str(r)[:160]))

# ---- 13. 权限：reader 不能申报
st, r = call("POST", "/api/auth/login", {"username": "reader01", "password": "123456"})
RT = (r.get("data") or {}).get("token") if st == 200 else None
if not RT:
    st2, r2 = call("GET", "/api/users", token=TOKEN)
    users = (r2.get("data") or {}).get("list") or [] if isinstance(r2.get("data"), dict) else []
    rd = [u for u in users if u.get("role") == "reader"]
    if rd:
        st, r = call("POST", "/api/auth/login", {"username": rd[0]["username"], "password": "123456"})
        RT = (r.get("data") or {}).get("token")
if RT:
    st, r = call("POST", "/api/declarations/save",
                 {"entity": "E01", "tax_type": "增值税", "period": "2026-11"}, token=RT)
    check("reader-denied-declare", st == 403, (st, str(r)[:120]))
    st, r = call("GET", "/api/invoices?page=1&size=1", token=RT)
    check("reader-can-read", st == 200, (st, str(r)[:120]))
else:
    check("reader-login", False, "no reader user")

# ---- 14. 幂等
st, r1 = call("POST", "/api/invoices", {"kind": "销项", "entityId": 1, "no": "IDEM-TEST-001",
                                        "buyer": "测试客户", "amount": "1130", "taxRate": "13%",
                                        "inclusive": True, "date": "2026-10-20"}, token=TOKEN,
              headers={"Idempotency-Key": "k-e2e-0001"})
st2, r2 = call("POST", "/api/invoices", {"kind": "销项", "entityId": 1, "no": "IDEM-TEST-001",
                                         "buyer": "测试客户", "amount": "1130", "taxRate": "13%",
                                         "inclusive": True, "date": "2026-10-20"}, token=TOKEN,
               headers={"Idempotency-Key": "k-e2e-0001"})
check("idempotency", st == st2 and r1.get("data") == r2.get("data"), (st, st2))

# ---- 15. api key 通道
st, r = call("POST", "/api/api-keys/create", {"name": "e2e-key"}, token=TOKEN)
ak = (r.get("data") or {}).get("key")
check("apikey-create", st == 200 and ak, (st, str(r)[:160]))
if ak:
    st, r = call("GET", "/api/entities", headers={"X-Tax-Key": ak})
    check("apikey-auth", st == 200, (st, str(r)[:160]))

print("\n==== RESULT  PASS=%d  FAIL=%d ====" % (len(PASS), len(FAIL)))
if FAIL:
    for f in FAIL:
        print("  ! " + f)
sys.exit(0 if not FAIL else 1)
