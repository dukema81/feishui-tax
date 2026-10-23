# 飞税税务管理系统 · API 接口契约

**Base URL**：`http://<host>:8024`（nginx 部署时为 `http://<host>/tax`）
**版本**：v1.0　**协议**：REST + JSON
**OpenAPI**：`GET /api/apidoc` 返回 OpenAPI 3.0 描述，可直接导入 Postman / Apifox

---

## 1. 通用约定

### 1.1 统一响应包

所有接口返回：

```json
{ "code": 200, "message": "ok", "data": { } }
```

`code` 与 HTTP 状态码一致：200 成功 / 400 参数错误 / 401 未认证 / 403 无权限 / 404 不存在 / 409 状态冲突 / 500 服务器异常。

### 1.2 鉴权（五通道任选其一）

```
Authorization: Bearer <token>
X-Tax-Token: <token>
Cookie: tax_token=<token>
?token=<token>            # URL 参数
X-Tax-Key: <api-key>      # 系统对接
```

- Token：登录获取（`POST /api/auth/login`），SHA-256 落库；
- API Key：系统管理页创建，作用域 `read` / `write` / `full`，仅显示一次。

### 1.3 幂等

所有写接口支持 `Idempotency-Key` 请求头。同一 Key 重复提交，返回首次结果（不重复执行）。

```
Idempotency-Key: ERP-PO-2026-0001
```

### 1.4 增量同步

```
GET /api/sync/version                       → {"invoices": 35, "declarations": 42, ...}
GET /api/sync?version=invoices:35&entities=invoices,declarations
```

版本号一致时该实体不返回数据；变化时返回全量行。对接方按实体本地保存版本号即可实现准实时同步。

### 1.5 命名兼容

计算器入参同时接受 `snake_case` 与 `camelCase`（如 `tax_rate` / `taxRate`）。

### 1.6 分页与筛选

列表接口统一返回 `{list, total}`；发票、申报等大表额外返回汇总字段（`sumAmount` / `sumTax` 等）。筛选参数直接拼 Query，如：

```
GET /api/invoices?kind=销项&period=2026-10&entity=E01&kw=武汉
```

---

## 2. 认证接口

### 2.1 登录

`POST /api/auth/login`

```json
// 请求
{ "username": "admin", "password": "tax@2026" }

// 响应 data
{
  "token": "a1b2c3...",
  "user": {
    "username": "admin", "name": "系统管理员", "role": "admin",
    "roleLabel": "系统管理员", "dept": "D100", "deptName": "集团总部",
    "perms": ["*"]
  }
}
```

### 2.2 当前用户

`GET /api/auth/me` → data 为用户对象（同上 user）。

### 2.3 登出 / 改密

- `POST /api/auth/logout`
- `POST /api/auth/change-password`　`{ "old": "...", "new": "..." }`

---

## 3. 计算引擎（核心对接点）

### 3.1 通用计算

`POST /api/calc`（权限 tax.read）　请求带 `kind` 字段，**不入库**。

| kind | 说明 | 关键入参 | 关键出参 |
| --- | --- | --- | --- |
| vat | 增值税单票 | amount, rate, inclusive | net / tax / gross |
| vat_general | 一般计税 | outputs[], inputs[], prior_credit, transfer_out, additional | out_tax / in_tax / payable / carry_forward |
| vat_small | 小规模简易 | sales, quarterly, has_realestate | exempt / rate / tax |
| surtax | 附加税费 | vat_payable, city_type, halve | items[] / total |
| cit | 企税年度 | profit, small_profit, rate, adjust_add/less, loss_carry | taxable / tax |
| cit_q | 企税季度 | profit, prior_paid | tax |
| iit | 个税综合所得 | taxable_income | rate / quick / tax |
| iit_salary | 个税工资 | gross, social_insurance, special_deduct | taxable / tax |
| iit_bonus | 年终奖 | bonus, mode(separate/merge/best), salary_taxable | separate / merge / best |
| stamp | 印花税 | type(税目), amount, vat_excluded, vat_rate | base / rate / tax |
| house | 房产税 | mode(value/rent), original_value, rent, deduct_ratio | tax / note |
| land | 土地使用税 | area, grade(1~6), unit_rate | unit_rate / tax |
| burden | 综合税负率 | revenue, vat, surtax, cit, stamp... | items[] / burden |
| three_flow | 三流一致 | invoice{amount, contract_amount, seller_name...} | ok / issues[] |
| late_fee | 滞纳金 | tax, days | fee / rate |

示例（企税小微）：

```
POST /api/calc
{ "kind": "cit", "profit": 2800000, "small_profit": true }

→ data: { "taxable": 2800000.0, "rate": "0.05", "tax": 140000.0,
          "note": "小型微利企业：减按 25% 计入 × 20%" }
```

### 3.2 计算元数据

`GET /api/calc/meta` → 增值税税率表、附加税率、城建税档、印花税税目、个税级距、年终奖级距、土地等级、小微标准。前端下拉与外部系统校验共用。

---

## 4. 发票

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | /api/invoices | invoice.read | 列表：kind / period / entity / status / verify / kw |
| GET | /api/invoices/{no} | invoice.read | 详情：含明细行、风险提示、三流校验 |
| POST | /api/invoices/save | invoice.write | 新增 / 编辑（自动算税） |
| POST | /api/invoices/{no}/void | invoice.void | 作废 |
| POST | /api/invoices/verify | input.verify | 进项认证，`{nos:[...]}` 或 `{no:"..."}` |

开票请求示例：

```
POST /api/invoices/save
Idempotency-Key: ERP-INV-2026-0777

{
  "kind": "销项",
  "entity": "E01",
  "invoice_type": "增值税专用发票",
  "rate": "13%",
  "amount": 113000,
  "inclusive": true,
  "buyer_name": "武汉智能制造股份有限公司",
  "buyer_tax_no": "91420100000099999F",
  "biz_date": "2026-10-22",
  "contract_no": "HT0001",
  "contract_amount": 113000,
  "items": [{"goods": "软件服务", "qty": 1, "amount": 100000}]
}

→ data: { "no": "XX0409", "created": true,
          "amount": 100000.0, "tax": 13000.0, "total": 113000.0 }
```

---

## 5. 纳税申报

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | /api/declarations | tax.read | 列表：entity / tax_type / period / status / kw |
| GET | /api/declarations/{no} | tax.read | 详情：含计税明细、关联凭证 |
| POST | /api/declarations/calc | tax.calc | 试算（不落库）：entity + tax_type + period |
| POST | /api/declarations/save | tax.declare | 新建 / 更新申报单 |
| POST | /api/declarations/{no}/file | tax.declare | 申报（→已申报） |
| POST | /api/declarations/{no}/pay | tax.declare | 缴款（→已缴款，自动生成凭证） |
| POST | /api/declarations/{no}/delete | tax.declare | 删除（仅草稿/待申报） |

状态机：`草稿 → 待申报 → 已申报 → 已缴款`；file 后不可删，409 保护。

试算响应（增值税）示例：

```
POST /api/declarations/calc
{ "entity": "E01", "tax_type": "增值税", "period": "2026-10" }

→ data: { "mode": "一般计税", "out_tax": 214327.56, "in_tax": 131810.63,
          "payable": 82516.93, "surtax": 9902.03, "total": 92418.96 }
```

---

## 6. 报表分析

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | /api/reports/flow?period=&entity= | 按主体税负率排行 |
| GET | /api/reports/trend | 近 6 期销项 / 进项 / 应纳 / 申报 |
| GET | /api/reports/type?period= | 按税种汇总（含占比） |
| GET | /api/reports/input?period= | 进项结构：税率 / 认证 / 供应商 Top10 |
| GET | /api/reports/summary?period= | 四合一总览（大屏推荐） |
| GET | /api/reports/export?type=invoice\|declaration&period= | CSV（UTF-8 BOM） |

---

## 7. 风险

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | /api/risks?status=&level=&entity= | 风险清单 + openScore |
| POST | /api/risks/scan | 按期间重扫规则，data.created 为新增列表 |
| POST | /api/risks/{id}/close | `{status:"已处理"/"已忽略", memo:"..."}` |

---

## 8. 主数据

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | /api/entities　GET /api/entities/{code} | 纳税主体（详情含当期统计） |
| POST | /api/entities/save | 新增 / 编辑主体 |
| GET | /api/tax-types | 8 大税种定义 |
| GET | /api/policies?tax_type=&kw=　GET /api/policies/{id} | 政策库 |
| GET | /api/depts　GET /api/users　POST /api/users/save | 组织与用户 |
| GET | /api/roles | 角色权限矩阵 |
| GET | /api/vouchers　POST /api/vouchers/save | 涉税凭证 |
| GET | /api/contracts　POST /api/contracts/save | 合同（自动算印花税） |
| GET | /api/notices | 公告 |

---

## 9. 系统

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | /api/health | 公开 | 健康检查 |
| GET | /api/apidoc | 公开 | OpenAPI 3.0 |
| GET | /api/rules　POST /api/rules/save | tax.read / system.write | 税务参数（城建税档、减半开关、滞纳金率等） |
| GET | /api/api-keys　POST /api/api-keys/create　POST /api/api-keys/{id}/delete | system.* | 接口密钥管理 |
| GET | /api/logs | system.read | 审计日志 |
| GET | /api/sync/version　GET /api/sync | 公开/token | 增量同步 |
| GET | /api/dashboard | tax.read | 工作台 KPI + 趋势 + 待办 |

---

## 10. 错误码表

| code | 场景 | 示例 message |
| --- | --- | --- |
| 400 | 参数错误 / 业务校验 | 未知计算类型：xxx / 金额必须大于 0 |
| 401 | 未登录 / token 失效 | 未认证 |
| 403 | 权限不足 | 无权限：invoice.void |
| 404 | 资源不存在 | 发票不存在：XX9999 |
| 409 | 状态冲突 | 已申报或已缴款的单据不可删除 |
| 500 | 服务器异常 | 服务器开小差了：... |

---

## 11. 对接示例（Python）

```python
import requests

BASE = "http://10.0.0.8:8024"
KEY = {"X-Tax-Key": "sk_xxxxxxxxxxxxxxxx"}        # API Key 通道

# 1) ERP 推送采购发票（幂等）
r = requests.post(BASE + "/api/invoices/save", headers={
    **KEY, "Idempotency-Key": "ERP-INV-2026-0777"
}, json={
    "kind": "进项", "entity": "E02", "rate": "13%",
    "amount": 904000, "inclusive": False,
    "seller_name": "某商贸有限公司", "seller_tax_no": "91320500MA1XX0XX0X",
    "biz_date": "2026-10-21", "contract_no": "HT0012", "contract_amount": 700000
})
print(r.json())   # code=200, data.no=XX0410

# 2) 财务系统每小时拉申报增量
ver = requests.get(BASE + "/api/sync/version", headers=KEY).json()["data"]
delta = requests.get(BASE + "/api/sync",
                     params={"version": f"declarations:{ver['declarations']}"},
                     headers=KEY).json()["data"]

# 3) 试算小微企税
r = requests.post(BASE + "/api/calc", headers=KEY,
                  json={"kind": "cit", "profit": 2800000, "small_profit": True})
assert r.json()["data"]["tax"] == 140000.0
```
