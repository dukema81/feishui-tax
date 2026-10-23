# -*- coding: utf-8 -*-
"""API 集成测试：登录、权限、幂等、计算引擎、申报流程。"""
import json
import urllib.error
import urllib.request


def call(base, method, path, body=None, token=None, headers=None):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = "Bearer " + token
    if headers:
        h.update(headers)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read().decode()
            return r.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {}


class TestAuth:
    def test_login_ok(self, base):
        st, r = call(base, "POST", "/api/auth/login",
                     {"username": "admin", "password": "tax@2026"})
        assert st == 200 and r["data"]["token"]

    def test_login_bad(self, base):
        st, r = call(base, "POST", "/api/auth/login",
                     {"username": "admin", "password": "x"})
        assert st == 401

    def test_me(self, base, token):
        st, r = call(base, "GET", "/api/auth/me", token=token)
        assert st == 200 and r["data"]["role"] == "admin"

    def test_no_token_401(self, base):
        st, r = call(base, "GET", "/api/entities")
        assert st == 401

    def test_health_public(self, base):
        st, r = call(base, "GET", "/api/health")
        assert st == 200


class TestRbac:
    def test_reader_cannot_declare(self, base):
        st, r = call(base, "POST", "/api/auth/login",
                     {"username": "reader01", "password": "123456"})
        assert st == 200
        tk = r["data"]["token"]
        st, r = call(base, "POST", "/api/declarations/save",
                     {"entity": "E01", "tax_type": "增值税", "period": "2026-11"},
                     token=tk)
        assert st == 403

    def test_reader_can_read(self, base):
        st, r = call(base, "POST", "/api/auth/login",
                     {"username": "reader01", "password": "123456"})
        tk = r["data"]["token"]
        st, r = call(base, "GET", "/api/invoices", token=tk)
        assert st == 200

    def test_auditor_cannot_write_invoice(self, base):
        st, r = call(base, "POST", "/api/auth/login",
                     {"username": "hejun", "password": "123456"})
        tk = r["data"]["token"]
        st, r = call(base, "POST", "/api/invoices/save",
                     {"entity": "E01", "kind": "销项", "amount": 100, "rate": "13%"},
                     token=tk)
        assert st == 403


class TestCalc:
    def test_vat(self, base, token):
        st, r = call(base, "POST", "/api/calc",
                     {"kind": "vat", "amount": 100000, "rate": "13%"}, token=token)
        assert st == 200 and abs(r["data"]["tax"] - 13000) < 0.01

    def test_alias(self, base, token):
        st, r = call(base, "POST", "/api/calc",
                     {"kind": "vat_invoice", "amount": 113000, "rate": "13%",
                      "inclusive": True}, token=token)
        assert st == 200 and abs(r["data"]["tax"] - 13000) < 0.02

    def test_unknown_kind(self, base, token):
        st, r = call(base, "POST", "/api/calc", {"kind": "nope"}, token=token)
        assert st == 400

    def test_cit_small_profit(self, base, token):
        st, r = call(base, "POST", "/api/calc",
                     {"kind": "cit", "profit": 2800000, "small_profit": True},
                     token=token)
        assert abs(r["data"]["tax"] - 140000) < 1

    def test_iit_bonus(self, base, token):
        st, r = call(base, "POST", "/api/calc",
                     {"kind": "iit_bonus", "bonus": 100000, "mode": "separate"},
                     token=token)
        assert st == 200

    def test_meta(self, base, token):
        st, r = call(base, "GET", "/api/calc/meta", token=token)
        assert st == 200 and r["data"]["vatRates"]


class TestInvoiceFlow:
    def test_create_and_void(self, base, token):
        st, r = call(base, "POST", "/api/invoices/save",
                     {"kind": "销项", "entity": "E01", "amount": 1130,
                      "rate": "13%", "inclusive": True,
                      "buyer_name": "pytest 客户",
                      "biz_date": "2026-10-22"}, token=token)
        assert st == 200
        no = r["data"]["no"]
        assert abs(r["data"]["tax"] - 130) < 0.01

        st, r = call(base, "GET", "/api/invoices/" + no, token=token)
        assert st == 200 and r["data"]["no"] == no

        st, r = call(base, "POST", "/api/invoices/%s/void" % no, {}, token=token)
        assert st == 200

        st, r = call(base, "GET", "/api/invoices/" + no, token=token)
        assert r["data"]["status"] == "作废"

    def test_verify_input(self, base, token):
        st, r = call(base, "GET", "/api/invoices?kind=%E8%BF%9B%E9%A1%B9", token=token)
        rows = r["data"]["list"]
        target = next(v for v in rows if v["verify_status"] == "未认证"
                      and v["status"] == "正常")
        st, r = call(base, "POST", "/api/invoices/verify", {"no": target["no"]},
                     token=token)
        assert st == 200

    def test_idempotency(self, base, token):
        body = {"kind": "销项", "entity": "E01", "amount": 2260, "rate": "13%",
                "inclusive": True, "buyer_name": "幂等测试", "biz_date": "2026-10-22",
                "no": "IDEM-PY-001"}
        h = {"Idempotency-Key": "pytest-idem-001"}
        s1, r1 = call(base, "POST", "/api/invoices/save", body, token, h)
        s2, r2 = call(base, "POST", "/api/invoices/save", body, token, h)
        assert s1 == s2 == 200
        assert r1["data"]["no"] == r2["data"]["no"]


class TestDeclarationFlow:
    def test_list_and_detail(self, base, token):
        st, r = call(base, "GET", "/api/declarations", token=token)
        assert st == 200 and r["data"]["total"] > 0
        no = r["data"]["list"][0]["no"]
        st, r = call(base, "GET", "/api/declarations/" + no, token=token)
        assert st == 200 and r["data"]["no"] == no

    def test_calc_draft(self, base, token):
        st, r = call(base, "POST", "/api/declarations/calc",
                     {"entity": "E01", "tax_type": "增值税", "period": "2026-10"},
                     token=token)
        assert st == 200 and r["data"]

    def test_save_file_pay(self, base, token):
        st, r = call(base, "POST", "/api/declarations/save",
                     {"entity": "E03", "tax_type": "印花税", "period": "2026-11"},
                     token=token)
        assert st == 200, r
        no = r["data"]["no"]

        st, r = call(base, "POST", "/api/declarations/%s/file" % no, {}, token=token)
        assert st == 200

        st, r = call(base, "POST", "/api/declarations/%s/pay" % no,
                     {"amount": None}, token=token)
        assert st == 200

        st, r = call(base, "GET", "/api/declarations/" + no, token=token)
        assert r["data"]["status"] == "已缴款"

    def test_delete_protected(self, base, token):
        st, r = call(base, "GET",
                     "/api/declarations?status=%E5%B7%B2%E7%94%B3%E6%8A%A5",
                     token=token)
        no = r["data"]["list"][0]["no"]
        st, r = call(base, "POST", "/api/declarations/%s/delete" % no, {}, token=token)
        assert st == 409


class TestReports:
    def test_all(self, base, token):
        for p in ("/api/reports/flow", "/api/reports/trend", "/api/reports/type",
                  "/api/reports/input", "/api/reports/summary"):
            st, r = call(base, "GET", p, token=token)
            assert st == 200, p

    def test_export_csv_bom(self, base, token):
        req = urllib.request.Request(
            base + "/api/reports/export?type=invoice",
            headers={"Authorization": "Bearer " + token})
        with urllib.request.urlopen(req) as r:
            raw = r.read()
        assert raw[:3] == b"\xef\xbb\xbf"


class TestRiskAndSync:
    def test_risks_list(self, base, token):
        st, r = call(base, "GET", "/api/risks", token=token)
        assert st == 200 and r["data"]["total"] > 0

    def test_scan(self, base, token):
        st, r = call(base, "POST", "/api/risks/scan", {}, token=token)
        assert st == 200

    def test_close(self, base, token):
        st, r = call(base, "GET", "/api/risks?status=%E5%BE%85%E5%A4%84%E7%90%86",
                     token=token)
        rid = r["data"]["list"][0]["id"]
        st, r = call(base, "POST", "/api/risks/%s/close" % rid,
                     {"status": "已处理", "memo": "pytest"}, token=token)
        assert st == 200

    def test_sync_version(self, base, token):
        st, r = call(base, "GET", "/api/sync/version", token=token)
        assert st == 200 and "invoices" in r["data"]

    def test_sync_delta(self, base, token):
        st, r = call(base, "GET", "/api/sync/version", token=token)
        ver = r["data"]["invoices"]
        st, r = call(base, "GET",
                     "/api/sync?version=invoices:%d&entities=invoices" % ver,
                     token=token)
        assert st == 200
        # 版本一致时不返回数据
        assert not (r["data"].get("invoices") or {}).get("rows")


class TestApiDoc:
    def test_apidoc(self, base):
        st, r = call(base, "GET", "/api/apidoc")
        assert st == 200 and r["data"]["paths"]
