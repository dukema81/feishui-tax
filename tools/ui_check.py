# -*- coding: utf-8 -*-
"""飞税前端 UI 巡检：起干净实例 + Playwright 逐页访问，抓控制台异常与失败请求。"""
import os
import sys
import subprocess
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DBP = os.path.join(tempfile.gettempdir(), "feishui_ui.db")
for f in (DBP, DBP + "-wal", DBP + "-shm"):
    if os.path.exists(f):
        os.remove(f)

PORT = 8047
env = dict(os.environ)
env["TAX_DB"] = DBP
env["TAX_PORT"] = str(PORT)

proc = subprocess.Popen([sys.executable, os.path.join(ROOT, "backend", "server.py")],
                        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
BASE = "http://127.0.0.1:%d" % PORT

import urllib.request  # noqa: E402


def wait_ready(n=60):
    for _ in range(n):
        try:
            with urllib.request.urlopen(BASE + "/api/health", timeout=1) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.4)
    return False


ok = wait_ready()
print("server ready:", ok, BASE)
if not ok:
    proc.kill()
    sys.exit(1)

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("SKIP: playwright 未安装")
    proc.kill()
    sys.exit(0)

PAGES = [
    ("dash", "工作台"), ("invoice", "发票管理"), ("input", "进项抵扣"),
    ("declare", "纳税申报"), ("calc", "税种计算器"), ("reports", "税负分析"),
    ("risk", "风险预警"), ("entity", "纳税主体"), ("voucher", "凭证台账"),
    ("policy", "政策法规"), ("system", "系统管理"),
]

errors = []
failed_req = []
shots = os.path.join(ROOT, "reports")
os.makedirs(shots, exist_ok=True)

with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()

    page.on("console", lambda m: errors.append("%s: %s" % (m.type, m.text))
            if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append("pageerror: %s" % e))
    page.on("requestfailed",
            lambda r: failed_req.append("%s %s" % (r.url, r.failure)))

    # 登录
    page.goto(BASE + "/login.html", wait_until="networkidle")
    page.fill("#u", "admin")
    page.fill("#p", "tax@2026")
    page.click("#go")
    page.wait_for_url("**/index.html", timeout=15000)
    page.wait_for_load_state("networkidle")
    print("logged in")

    passed = 0
    for key, name in PAGES:
        page.goto(BASE + "/index.html#/" + key, wait_until="networkidle")
        page.wait_for_timeout(700)
        body = page.inner_text("#main")
        bad = ("加载失败" in body) or ("加载中" in body and len(body) < 40)
        has_err = "加载失败" in body
        if has_err:
            print("  FAIL %-10s %s" % (key, body[:110].replace("\n", " ")))
        else:
            passed += 1
            print("  OK   %-10s %s" % (key, name))
        page.screenshot(path=os.path.join(shots, "tax-%s.png" % key), full_page=False)

    br.close()

print("\n==== UI 巡检: %d/%d 通过 ====" % (passed, len(PAGES)))
if errors:
    print("控制台异常 %d 条：" % len(errors))
    for e in errors[:20]:
        print("  !", e[:200])
if failed_req:
    print("失败请求 %d 条：" % len(failed_req))
    for e in failed_req[:20]:
        print("  !", e[:200])

proc.kill()
sys.exit(0 if passed == len(PAGES) and not errors else 1)
