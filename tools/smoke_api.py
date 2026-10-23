# -*- coding: utf-8 -*-
"""飞税线上冒烟：python tools/smoke_api.py --base http://host:port[/tax]

不依赖 pytest，覆盖关键只读链路 + 登录 + 计算，部署后立即验证。
"""
import argparse
import json
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

PASS = []
FAIL = []


def call(base, method, path, body=None, token=None, raw=False):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = "Bearer " + token
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, context=CTX, timeout=15) as r:
            b = r.read()
            return r.status, b if raw else json.loads(b or b"{}")
    except urllib.error.HTTPError as e:
        b = e.read()
        try:
            return e.code, json.loads(b or b"{}")
        except Exception:
            return e.code, {}


def check(name, cond, extra=""):
    if cond:
        PASS.append(name)
        print("  OK   " + name)
    else:
        FAIL.append(name)
        print("  FAIL " + name + " " + str(extra)[:160])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    a = ap.parse_args()
    base = a.base.rstrip("/")

    st, r = call(base, "GET", "/api/health")
    check("health", st == 200, (st, str(r)[:120]))

    st, r = call(base, "POST", "/api/auth/login",
                 {"username": "admin", "password": "tax@2026"})
    check("login", st == 200, (st, str(r)[:120]))
    tk = (r.get("data") or {}).get("token", "")

    st, r = call(base, "GET", "/api/dashboard", token=tk)
    check("dashboard", st == 200 and (r.get("data") or {}).get("kpi"), (st, ""))

    for p in ("/api/entities", "/api/depts", "/api/users", "/api/tax-types",
              "/api/policies", "/api/notices"):
        st, r = call(base, "GET", p, token=tk)
        n = ((r.get("data") or {}).get("total")) if isinstance(r.get("data"), dict) else 0
        check(p, st == 200 and (n or 0) > 0, (st, n))

    for q, name in [("kind=%E9%94%80%E9%A1%B9", "invoices-销项"),
                    ("kind=%E8%BF%9B%E9%A1%B9", "invoices-进项")]:
        st, r = call(base, "GET", "/api/invoices?" + q, token=tk)
        d = r.get("data") or {}
        check(name, st == 200 and (d.get("total") or 0) > 0, (st, d.get("total")))

    st, r = call(base, "GET", "/api/declarations", token=tk)
    check("declarations", st == 200 and (r.get("data") or {}).get("total", 0) > 0, st)

    st, r = call(base, "GET", "/api/risks", token=tk)
    check("risks", st == 200, st)

    st, r = call(base, "GET", "/api/vouchers", token=tk)
    check("vouchers", st == 200 and (r.get("data") or {}).get("total", 0) > 0, st)

    st, r = call(base, "GET", "/api/contracts", token=tk)
    check("contracts", st == 200, st)

    calcs = [
        ("vat", {"kind": "vat", "amount": 100000, "rate": "13%"},
         lambda d: abs(d.get("tax", 0) - 13000) < 0.01),
        ("vat_small", {"kind": "vat_small", "sales": 350000},
         lambda d: abs(d.get("tax", 0) - 3500) < 1),
        ("cit", {"kind": "cit", "profit": 2800000, "small_profit": True},
         lambda d: abs(d.get("tax", 0) - 140000) < 1),
        ("iit", {"kind": "iit", "taxable_income": 200000},
         lambda d: abs(d.get("tax", 0) - 23080) < 1),
        ("stamp", {"kind": "stamp", "type": "买卖合同", "amount": 1000000},
         lambda d: abs(d.get("tax", 0) - 300) < 0.01),
        ("late_fee", {"kind": "late_fee", "tax": 10000, "days": 10},
         lambda d: abs(d.get("fee", 0) - 50) < 0.01),
    ]
    for name, payload, pred in calcs:
        st, r = call(base, "POST", "/api/calc", payload, token=tk)
        d = r.get("data") or {}
        check("calc-" + name, st == 200 and pred(d), (st, str(r)[:140]))

    for p in ("/api/reports/flow", "/api/reports/trend", "/api/reports/type",
              "/api/reports/input", "/api/reports/summary"):
        st, r = call(base, "GET", p, token=tk)
        check(p, st == 200, st)

    st, r = call(base, "GET", "/api/reports/export?type=invoice", token=tk, raw=True)
    check("export-csv", st == 200 and isinstance(r, bytes) and len(r) > 300,
          (st, len(r) if isinstance(r, bytes) else type(r)))

    st, r = call(base, "GET", "/api/apidoc")
    check("apidoc", st == 200, st)

    st, r = call(base, "GET", "/api/sync/version", token=tk)
    check("sync-version", st == 200, st)

    # 静态页
    st, r = call(base, "GET", "/index.html", raw=True)
    check("index.html", st == 200 and "飞税".encode() in r, st)
    st, r = call(base, "GET", "/login.html", raw=True)
    check("login.html", st == 200, st)

    print("\n==== 冒烟  PASS=%d  FAIL=%d ====" % (len(PASS), len(FAIL)))
    sys.exit(0 if not FAIL else 1)


if __name__ == "__main__":
    main()
