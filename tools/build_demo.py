# -*- coding: utf-8 -*-
"""飞税税务管理系统 · 离线 DEMO 构建器

从进程内实例抓取真实接口快照，内联前端资源，fetch 拦截读快照，
产出双击即开的单文件 HTML。
"""
import io
import json
import os
import sys
import urllib.parse
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "demo")
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
TOK = ""
SRV = None
BASE = ""


def free_port():
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def boot_inproc():
    global SRV, BASE
    import threading
    dbp = os.path.join(OUT, "_snap.db")
    for f in (dbp, dbp + "-wal", dbp + "-shm"):
        if os.path.exists(f):
            os.remove(f)
    os.environ["TAX_DB"] = dbp
    sys.path.insert(0, os.path.join(ROOT, "backend"))
    import db
    import seed as seedmod
    import server as srvmod

    srvmod.PORT = free_port()
    db.init()
    seedmod.seed()
    SRV = srvmod.ThreadingHTTPServer(("127.0.0.1", srvmod.PORT), srvmod.Handler)
    threading.Thread(target=SRV.serve_forever, daemon=True).start()
    BASE = "http://127.0.0.1:%d" % srvmod.PORT
    print("in-proc server on", BASE)


def login(as_user="admin", pwd=None):
    global TOK
    pwd = pwd or ("tax@2026" if as_user == "admin" else "123456")
    body = json.dumps({"username": as_user, "password": pwd}).encode()
    req = urllib.request.Request(BASE + "/api/auth/login", data=body,
                                 headers={"Content-Type": "application/json"})
    with OPENER.open(req, timeout=20) as r:
        TOK = json.loads(r.read().decode("utf-8"))["data"]["token"]
    print("login ->", BASE, "@", as_user)


def get(path):
    req = urllib.request.Request(BASE + path)
    req.add_header("Authorization", "Bearer " + TOK)
    try:
        with OPENER.open(req, timeout=60) as r:
            js = json.loads(r.read().decode("utf-8"))
            if isinstance(js, dict) and "data" in js:
                return js["data"]
            return js
    except Exception as e:                                    # noqa: BLE001
        print("  !! %-46s %s" % (path, e))
        return None


def collect():
    """按前端 11 个页面的真实调用顺序抓快照。"""
    paths = (
        ["/api/auth/me", "/api/dashboard", "/api/notices"]
        + ["/api/entities", "/api/depts", "/api/users", "/api/roles",
           "/api/tax-types", "/api/policies", "/api/policies/1"]
        + ["/api/invoices?kind=" + urllib.parse.quote(k)
           for k in ("销项", "进项")]
        + ["/api/declarations"]
        + ["/api/declarations?status=" + urllib.parse.quote(s)
           for s in ("草稿", "待申报", "已申报", "已缴款")]
        + ["/api/risks", "/api/risks?status=" + urllib.parse.quote("待处理")]
        + ["/api/vouchers", "/api/contracts", "/api/logs",
           "/api/rules", "/api/api-keys", "/api/calc/meta",
           "/api/reports/flow", "/api/reports/trend", "/api/reports/type",
           "/api/reports/input", "/api/reports/summary",
           "/api/health", "/api/sync/version"]
    )
    snap = {}
    for p in paths:
        snap[p] = get(p)

    # 抽样详情
    inv = (snap.get("/api/invoices?kind=" + urllib.parse.quote("销项")) or {}).get("list") or []
    decl = (snap.get("/api/declarations") or {}).get("list") or []
    for v in inv[:6]:
        snap["/api/invoices/" + v["no"]] = get("/api/invoices/" + v["no"])
    for d in decl[:6]:
        snap["/api/declarations/" + d["no"]] = get("/api/declarations/" + d["no"])
    return snap


DEMO_JS = r"""
/* ============ 离线演示运行时：拦截 fetch 改读快照 ============ */
var SNAP = __SNAP__;
var DEMO_USERS = __USERS__;
var DEMO_ME = (function () {
  var q = (location.search || '') + '&' + (location.hash || '');
  var m = q.match(/[?&#]as=([\w\-]+)/);
  var who = m ? decodeURIComponent(m[1]) : '';
  if (who && DEMO_USERS[who]) return DEMO_USERS[who];
  try {
    var saved = sessionStorage.getItem('demo_as');
    if (saved && DEMO_USERS[saved]) return DEMO_USERS[saved];
  } catch (e) { /* ignore */ }
  return __ME__;
})();

function normPath(p) {
  p = String(p || '').replace(PREFIX, '');
  if (p.charAt(0) !== '/') p = '/' + p;
  return p;
}
function lookup(p) {
  p = normPath(p);
  if (p === '/api/auth/me') return DEMO_ME;
  if (SNAP[p] !== undefined && SNAP[p] !== null) return SNAP[p];
  var bare = p.split('?')[0];
  if (SNAP[bare] !== undefined && SNAP[bare] !== null) return SNAP[bare];
  /* 带筛选参数的列表：回退到无参数版本 */
  var m = p.match(/^\/api\/invoices\?/);
  if (m) return SNAP['/api/invoices?kind=' + encodeURIComponent('\u9500\u9879')]
    || (SNAP['/api/invoices?kind=' + encodeURIComponent('\u8fdb\u9879')] || {});
  m = p.match(/^\/api\/declarations\?/);
  if (m) return SNAP['/api/declarations'] || {};
  m = p.match(/^\/api\/risks\?/);
  if (m) return SNAP['/api/risks'] || {};
  m = p.match(/^\/api\/policies\?/);
  if (m) return SNAP['/api/policies'] || {};
  /* 详情：/api/invoices/XX0001 */
  m = p.match(/^\/api\/invoices\/([\w\-]+)$/);
  if (m) {
    var hit = ((SNAP['/api/invoices?kind=' + encodeURIComponent('\u9500\u9879')] || {}).list || [])
      .concat((SNAP['/api/invoices?kind=' + encodeURIComponent('\u8fdb\u9879')] || {}).list || [])
      .filter(function (x) { return x.no === m[1]; })[0];
    if (hit) return Object.assign({}, hit, {risks: []});
  }
  m = p.match(/^\/api\/declarations\/([\w\-]+)$/);
  if (m) {
    var dd = ((SNAP['/api/declarations'] || {}).list || [])
      .filter(function (x) { return x.no === m[1]; })[0];
    if (dd) return Object.assign({}, dd, {vouchers: []});
  }
  m = p.match(/^\/api\/entities\/([\w\-]+)$/);
  if (m) {
    var ee = ((SNAP['/api/entities'] || {}).list || [])
      .filter(function (x) { return x.code === m[1]; })[0];
    if (ee) return Object.assign({}, ee, {stats: {period: '2026-10',
      outputTax: 0, inputTax: 0, vatPayable: 0, invoices: 0, declarations: 0}});
  }
  return null;
}

window.fetch = function (url, opt) {
  var method = (opt && opt.method) || 'GET';
  var path = String(url).replace(location.origin, '');
  var status = 200, body;
  if (method !== 'GET') {
    body = {code: 200, message: '\u6f14\u793a\u73af\u5883\u53ea\u8bfb\uff0c\u5199\u64cd\u4f5c\u672a\u6267\u884c',
            data: {}};
  } else {
    var data = lookup(path);
    if (data === null || data === undefined) {
      body = {code: 200, message: 'ok', data: []};
    } else {
      body = {code: 200, message: 'ok', data: data};
    }
  }
  return Promise.resolve({
    status: status, ok: true,
    json: function () { return Promise.resolve(body); },
    text: function () { return Promise.resolve(JSON.stringify(body)); }
  });
};
window.CSV = function () { return Promise.reject(new Error('\u6f14\u793a\u73af\u5883\u4e0d\u652f\u6301\u5bfc\u51fa')); };

try {
  localStorage.setItem('tax_token', 'demo');
  localStorage.setItem('tax_user', JSON.stringify(DEMO_ME));
} catch (e) { /* ignore */ }

window.demoAs = function (who) {
  var m = DEMO_USERS[who];
  if (!m) return;
  try {
    localStorage.setItem('tax_user', JSON.stringify(m));
    localStorage.setItem('tax_token', 'demo');
    sessionStorage.setItem('demo_as', who);
  } catch (e) { /* ignore */ }
  location.hash = '#/dash';
  location.reload();
};

document.addEventListener('DOMContentLoaded', function () {
  var bar = document.createElement('div');
  bar.className = 'demo-bar';
  var opts = Object.keys(DEMO_USERS).map(function (k) {
    return '<option value="' + k + '"' + (k === DEMO_ME.username ? ' selected' : '') + '>'
      + DEMO_USERS[k].name + '\uff08' + DEMO_USERS[k].roleLabel + '\uff09</option>';
  }).join('');
  bar.innerHTML = '<b>\u79bb\u7ebf\u6f14\u793a</b> \u6570\u636e\u53d6\u81ea\u98de\u7a0e\u6f14\u793a\u5b9e\u4f8b\u7684\u771f\u5b9e\u5feb\u7167\uff0c\u53ea\u8bfb\u6d4f\u89c8\uff0c\u5199\u64cd\u4f5c\u4e0d\u4f1a\u771f\u6b63\u6267\u884c\u3002'
    + '<span class="who">\u5f53\u524d\u89c6\u89d2 <select onchange="demoAs(this.value)">' + opts + '</select></span>';
  document.body.insertBefore(bar, document.body.firstChild);
});
"""

DEMO_CSS = r"""
.demo-bar{position:fixed;left:0;right:0;top:0;z-index:99;background:#fff8e6;color:#7a5b12;
  border-bottom:1px solid #f0d9a8;font-size:12.5px;padding:7px 16px;text-align:center;
  box-shadow:0 1px 4px rgba(0,0,0,.06)}
.demo-bar b{color:#b8791b}
.demo-bar .who{margin-left:12px;padding-left:12px;border-left:1px solid #f0d9a8}
.demo-bar select{font-size:12.5px;padding:2px 6px;border:1px solid #e0c98f;border-radius:4px;
  background:#fff;color:#7a5b12}
body{padding-top:34px}
"""


def build():
    if not BASE:
        boot_inproc()
    login("admin")
    snap = collect()
    me = get("/api/auth/me") or {}
    me["perms"] = ["*"]

    # 多视角：admin + 税务会计 + 内审 + 报表使用者
    viewers = {"admin": me}
    for who, role in (("liyan", "tax_accountant"), ("hejun", "auditor"),
                      ("reader01", "reader")):
        login(who)
        m = get("/api/auth/me") or {}
        if m.get("username"):
            viewers[who] = m
    login("admin")

    filled = sum(1 for v in snap.values() if v not in (None, [], {}))
    print("snapshot paths: %d / %d 有数据" % (filled, len(snap)))

    fx = os.path.join(ROOT, "frontend")
    css = io.open(os.path.join(fx, "style.css"), encoding="utf-8").read()
    app = io.open(os.path.join(fx, "app.js"), encoding="utf-8").read()
    pages = io.open(os.path.join(fx, "pages.js"), encoding="utf-8").read()
    tpl = io.open(os.path.join(ROOT, "tools", "demo_template.html"), encoding="utf-8").read()

    data = json.dumps(snap, ensure_ascii=False, separators=(",", ":"))
    me_json = json.dumps(me, ensure_ascii=False, separators=(",", ":"))
    users_json = json.dumps(viewers, ensure_ascii=False, separators=(",", ":"))
    runtime = (DEMO_JS.replace("__SNAP__", data)
               .replace("__USERS__", users_json)
               .replace("__ME__", me_json))

    html = (tpl
            .replace("__STYLE__", css + "\n" + DEMO_CSS)
            .replace("__APP_JS__", app)
            .replace("__PAGES_JS__", pages)
            .replace("__RUNTIME_JS__", runtime))

    os.makedirs(OUT, exist_ok=True)
    name = "飞税税务管理系统Demo.html"
    out_html = os.path.join(OUT, name)
    io.open(out_html, "w", encoding="utf-8").write(html)
    print("html: %.1f KB -> %s" % (len(html.encode("utf-8")) / 1024.0, out_html))

    out_zip = os.path.join(OUT, "feishui-tax-demo.zip")
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(out_html, name)
        z.writestr("使用说明.txt",
                   "飞税税务管理系统 · 离线演示\r\n"
                   "1. 解压后双击「飞税税务管理系统Demo.html」，用浏览器打开即可，无需安装、无需联网。\r\n"
                   "2. 数据为演示实例真实快照：8 纳税主体 / 13 用户 / 408 张发票 / 112 张申报单 /"
                   " 98 凭证 / 24 合同 / 8 风险 / 8 政策。\r\n"
                   "3. 11 个页签：工作台 / 发票管理 / 进项抵扣 / 纳税申报 / 税种计算器 / 税负分析 /\r\n"
                   "   风险预警 / 纳税主体 / 凭证台账 / 政策法规 / 系统管理。\r\n"
                   "4. 本页为只读快照，申报、缴款等写操作不会真正执行；税种计算器因需实时计算亦不可用。\r\n"
                   "5. 完整版本请部署源码包（backend/ + frontend/，Python 标准库即可运行）。\r\n")
    print("zip : %.1f KB" % (os.path.getsize(out_zip) / 1024.0))
    return out_html


if __name__ == "__main__":
    build()
