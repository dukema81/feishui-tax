# -*- coding: utf-8 -*-
"""飞税税务管理系统 · 文档与DEMO批量上传知识库（分类 33 企业管理系统）"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = r"C:/Users/maxl/WorkBuddy/Claw/feishui-tax"
BASE = "http://42.193.158.63"
CAT = 33
PASSWORD = "YCSpyVwt@J2UByom3#n6gb"
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))
TOKEN = None
REPLACE = "--replace" in sys.argv

DOCS = [
    ("docs/feishui_design_v1.docx", "飞税税务管理系统建设方案",
     "「飞税税务管理系统」完整建设方案 V1.0：8 家纳税主体税务管理痛点与建设目标、"
     "2026 现行税法口径（增值税法 13%/9%/6%/0% 与征收率 3%、小规模 10 万/30 万起征点与 3% 减按 1%、"
     "附加税费市区 7% 三档与六税两费减半、小微企税实际 5%、个税七级累进与年终奖单独计税、"
     "印花税 17 税目 5 档、房产税从价从租、土地使用税 6 级、滞纳金万分之五）、"
     "总体架构与零依赖技术选型（Python 标准库 http.server + SQLite WAL，Decimal 精确到分）、"
     "19 表数据模型、发票管理（三流一致校验）、纳税申报状态机（试算/填报/申报/缴款/自动凭证）、"
     "14 模型计算器、税负分析、7 类风险规则引擎、6 角色权限矩阵、对外集成方案、6 阶段实施里程碑。",
     "飞税,税务管理,增值税,企业所得税,个人所得税,印花税,申报,建设方案"),
    ("docs/feishui_api_v1.docx", "飞税税务管理系统 REST 接口契约",
     "54 端点分组契约：统一响应包 {code,message,data} 与 HTTP 状态一致、鉴权五通道"
     "（Bearer / X-Tax-Token / Cookie / ?token= / X-Tax-Key，SHA-256 存储）、"
     "Idempotency-Key 幂等、增量同步协议（版本号 + 实体过滤）、snake_case/camelCase 双命名兼容、"
     "认证接口、15 类通用计算引擎入参出参表（增值税/附加/企税/个税/印花/房产/土地/税负/三流/滞纳金）、"
     "发票五接口与开票示例、申报七接口与状态机、六张报表、风险三接口、主数据接口、"
     "系统管理接口、错误码表、Python 对接三示例（ERP 推票/财务拉增量/试算）。",
     "飞税,API,接口契约,REST,幂等,增量同步,税务系统对接"),
    ("docs/feishui_test_v1.docx", "飞税税务管理系统测试报告",
     "三道质量门禁全部通过：pytest 70 条（税内核 34：增值税 9 / 附加 3 / 企税 4 / 个税 5 /"
     " 财产行为税 6 / 风险工具 7，API 集成 36：认证 5 / RBAC 3 / 计算 6 / 发票流 4 / 申报流 5 /"
     " 报表 2 / 风险同步 5）；端到端 53 项（进程内真实服务全链路含 15 组精确金额断言）；"
     "UI 巡检 Playwright 11 页面 0 控制台异常。测试中发现并修复 11 项缺陷"
     "（dashboard 主键错位、列表结构不统一、计算器命名兼容、进项列表形态、滞纳金费率兜底、"
     "个税起征常量、Decimal 别名、认证入参、风险指数显示、HTML 拼接优先级、reader 账号缺失）。",
     "飞税,测试报告,pytest,Playwright,质量门禁,税务计算"),
    ("docs/feishui_manual_v1.docx", "飞税税务管理系统使用手册",
     "面向全部 6 角色的操作手册：系统定位与账号表（admin 密码 tax@2026，其余 123456）、"
     "11 页面逐页说明（工作台 8 KPI 与趋势图、发票管理与三流校验详情、进项认证规则、"
     "纳税申报四步闭环与试算、14 模型税种计算器、税负分析五视图、风险处置与扫描、"
     "纳税主体档案、凭证台账与印花税、政策库与税率速查、系统管理五页签）、"
     "6 条常见问题（申报期限、缴款凭证、认证拒绝原因、三流不一致、小微税率、外部对接）、操作技巧。",
     "飞税,使用手册,操作指南,税务管理"),
    ("demo/feishui-tax-demo.zip", "飞税税务管理系统离线演示（DEMO）",
     "单文件离线演示：解压后双击 HTML 即可用浏览器打开，无需服务与网络。"
     "数据取自演示实例真实快照：8 纳税主体 / 13 用户 / 408 张发票 / 112 张申报单 /"
     " 98 凭证 / 24 合同 / 8 风险 / 8 政策。11 个页签覆盖工作台、发票管理、进项抵扣、"
     "纳税申报、税种计算器、税负分析、风险预警、纳税主体、凭证台账、政策法规、系统管理。"
     "支持顶部切换 4 个真实视角（系统管理员 / 税务主管 / 内审 / 报表使用者）。"
     "本页为只读快照，写操作不会真正执行。",
     "飞税,DEMO,离线演示,税务管理,纳税申报"),
]


def req(path, method="GET", data=None, token=None):
    r = urllib.request.Request(BASE + path, method=method)
    if data is not None:
        r.data = json.dumps(data).encode("utf-8")
        r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", "Bearer " + token)
    try:
        with OP.open(r, timeout=90) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:                                     # noqa: BLE001
            return e.code, {}


def curl_upload(path, title, desc, tags):
    full = os.path.join(ROOT, path)
    mime = "application/zip" if full.endswith(".zip") else \
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    cmd = ["curl", "-s", "--noproxy", "*",
           "-H", "Authorization: Bearer " + TOKEN,
           "-F", "file=@%s;type=%s" % (full, mime),
           "-F", "title=" + title,
           "-F", "description=" + desc,
           "-F", "categoryId=%d" % CAT,
           "-F", "tags=" + tags,
           BASE + "/api/documents/upload"]
    out = subprocess.run(cmd, capture_output=True, timeout=300)
    try:
        return json.loads(out.stdout.decode("utf-8", "ignore"))
    except Exception:                                         # noqa: BLE001
        return {"code": -1, "raw": out.stdout.decode("utf-8", "ignore")[:400],
                "err": out.stderr.decode("utf-8", "ignore")[:200]}


def existing(cat=CAT):
    st, j = req("/api/documents?categoryId=%d&pageNum=1&pageSize=200" % cat, token=TOKEN)
    data = j.get("data") or {}
    if isinstance(data, list):
        return data
    return data.get("records") or data.get("list") or []


def delete_doc(doc_id):
    return req("/api/documents/%s" % doc_id, "DELETE", token=TOKEN)


def main():
    global TOKEN
    st, j = req("/api/auth/login", "POST", {"username": "admin", "password": PASSWORD})
    assert j.get("code") == 200, j
    TOKEN = j["data"]["token"]
    print("login ok")

    if REPLACE:
        want = {t for _, t, _, _ in DOCS}
        for r in existing():
            if r.get("title") in want:
                st, j = delete_doc(r.get("id"))
                print("删除旧文档 %s id=%s -> %s" % (r.get("title"), r.get("id"), st))
                time.sleep(0.4)

    results = []
    for path, title, desc, tags in DOCS:
        j = curl_upload(path, title, desc, tags)
        code = j.get("code")
        doc_id = (j.get("data") or {}).get("id") if isinstance(j.get("data"), dict) else j.get("data")
        size = os.path.getsize(os.path.join(ROOT, path))
        print("%-28s code=%s id=%s %.1fKB" % (os.path.basename(path), code, doc_id, size / 1024.0))
        if code != 200:
            print("   !!", str(j)[:300])
        results.append((path, title, code, doc_id))
        time.sleep(1.2)

    ok = [r for r in results if r[2] == 200]
    print("\n上传成功 %d / %d" % (len(ok), len(results)))
    os.makedirs(os.path.join(ROOT, "reports"), exist_ok=True)
    with open(os.path.join(ROOT, "reports", "kb_upload_result.json"), "w", encoding="utf-8") as f:
        json.dump([{"file": r[0], "title": r[1], "code": r[2], "id": r[3]} for r in results],
                  f, ensure_ascii=False, indent=2)
    st, j = req("/api/document-categories", token=TOKEN)
    for c in (j.get("data") or []):
        if isinstance(c, dict) and c.get("id") == CAT:
            print("cat%d docCount:" % CAT, c.get("docCount"))


if __name__ == "__main__":
    main()
