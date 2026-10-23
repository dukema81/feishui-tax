# -*- coding: utf-8 -*-
"""飞税税务管理系统 · 数据层（sqlite3 + WAL）

约定：
  - 每个请求独立连接（线程安全），只在 init 时设一次 journal_mode=WAL
  - 所有写操作经 run()，读经 rows() / one() / val()
  - 单号生成 gen_no()：MAX 尾号递增 + 空号优先复用
"""
import os
import re
import sqlite3
import threading
import time

DB_PATH = os.environ.get("TAX_DB") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "feishui.db")
_LOCK = threading.RLock()
_INITED = False

SCHEMA = [
    # ---------------- 组织域
    """CREATE TABLE IF NOT EXISTS depts (
        code TEXT PRIMARY KEY, name TEXT NOT NULL, parent TEXT DEFAULT '',
        leader TEXT DEFAULT '', sort INTEGER DEFAULT 0, memo TEXT DEFAULT '')""",
    """CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY, name TEXT NOT NULL, dept TEXT DEFAULT '',
        title TEXT DEFAULT '', role TEXT DEFAULT 'reader', phone TEXT DEFAULT '',
        email TEXT DEFAULT '', pwd TEXT DEFAULT '', status TEXT DEFAULT '启用',
        created_at TEXT DEFAULT '')""",
    """CREATE TABLE IF NOT EXISTS tokens (
        token TEXT PRIMARY KEY, username TEXT NOT NULL, created_at TEXT DEFAULT '')""",
    """CREATE TABLE IF NOT EXISTS api_keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
        key_hash TEXT NOT NULL, prefix TEXT DEFAULT '', scope TEXT DEFAULT 'read',
        owner TEXT DEFAULT '', status TEXT DEFAULT '启用', created_at TEXT DEFAULT '',
        last_used TEXT DEFAULT '')""",

    # ---------------- 纳税主体
    """CREATE TABLE IF NOT EXISTS entities (
        code TEXT PRIMARY KEY, name TEXT NOT NULL, tax_no TEXT DEFAULT '',
        taxpayer_type TEXT DEFAULT '一般纳税人', industry TEXT DEFAULT '',
        city_type TEXT DEFAULT '市区', region TEXT DEFAULT '东部',
        legal_person TEXT DEFAULT '', contact TEXT DEFAULT '', phone TEXT DEFAULT '',
        reg_address TEXT DEFAULT '', reg_capital REAL DEFAULT 0,
        staff_count INTEGER DEFAULT 0, asset_total REAL DEFAULT 0,
        small_profit INTEGER DEFAULT 1, high_tech INTEGER DEFAULT 0,
        status TEXT DEFAULT '启用', created_at TEXT DEFAULT '')""",

    # ---------------- 发票域
    """CREATE TABLE IF NOT EXISTS invoices (
        no TEXT PRIMARY KEY, kind TEXT DEFAULT '销项', code TEXT DEFAULT '',
        number TEXT DEFAULT '', invoice_type TEXT DEFAULT '增值税专用发票',
        entity TEXT DEFAULT '', seller_name TEXT DEFAULT '', seller_tax_no TEXT DEFAULT '',
        buyer_name TEXT DEFAULT '', buyer_tax_no TEXT DEFAULT '',
        amount REAL DEFAULT 0, tax_rate TEXT DEFAULT '13%', tax REAL DEFAULT 0,
        total REAL DEFAULT 0, biz_date TEXT DEFAULT '', period TEXT DEFAULT '',
        status TEXT DEFAULT '正常', verify_status TEXT DEFAULT '未认证',
        category TEXT DEFAULT '', contract_no TEXT DEFAULT '',
        contract_amount REAL DEFAULT 0, paid_amount REAL DEFAULT 0,
        contract_party TEXT DEFAULT '', remark TEXT DEFAULT '',
        created_by TEXT DEFAULT '', created_at TEXT DEFAULT '')""",
    """CREATE TABLE IF NOT EXISTS invoice_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT, invoice TEXT NOT NULL,
        goods TEXT DEFAULT '', spec TEXT DEFAULT '', unit TEXT DEFAULT '',
        qty REAL DEFAULT 0, price REAL DEFAULT 0, amount REAL DEFAULT 0,
        tax_rate TEXT DEFAULT '13%', tax REAL DEFAULT 0)""",

    # ---------------- 申报域
    """CREATE TABLE IF NOT EXISTS declarations (
        no TEXT PRIMARY KEY, entity TEXT DEFAULT '', tax_type TEXT DEFAULT '',
        period TEXT DEFAULT '', status TEXT DEFAULT '草稿',
        base_amount REAL DEFAULT 0, tax_amount REAL DEFAULT 0,
        relief_amount REAL DEFAULT 0, paid_amount REAL DEFAULT 0,
        carry_forward REAL DEFAULT 0, due_date TEXT DEFAULT '',
        filed_at TEXT DEFAULT '', paid_at TEXT DEFAULT '',
        detail TEXT DEFAULT '{}', memo TEXT DEFAULT '',
        created_by TEXT DEFAULT '', created_at TEXT DEFAULT '')""",
    """CREATE TABLE IF NOT EXISTS tax_types (
        code TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT DEFAULT '',
        period_rule TEXT DEFAULT '月', shared INTEGER DEFAULT 0,
        rate_desc TEXT DEFAULT '', sort INTEGER DEFAULT 0, memo TEXT DEFAULT '')""",

    # ---------------- 凭证/台账域
    """CREATE TABLE IF NOT EXISTS vouchers (
        no TEXT PRIMARY KEY, entity TEXT DEFAULT '', period TEXT DEFAULT '',
        vdate TEXT DEFAULT '', summary TEXT DEFAULT '', account TEXT DEFAULT '',
        debit REAL DEFAULT 0, credit REAL DEFAULT 0,
        tax_type TEXT DEFAULT '', src TEXT DEFAULT '手工', memo TEXT DEFAULT '',
        created_by TEXT DEFAULT '', created_at TEXT DEFAULT '')""",
    """CREATE TABLE IF NOT EXISTS contracts (
        no TEXT PRIMARY KEY, entity TEXT DEFAULT '', ctype TEXT DEFAULT '买卖合同',
        title TEXT DEFAULT '', party TEXT DEFAULT '', amount REAL DEFAULT 0,
        vat_excluded INTEGER DEFAULT 1, sign_date TEXT DEFAULT '',
        stamp_tax REAL DEFAULT 0, stamp_paid INTEGER DEFAULT 0,
        status TEXT DEFAULT '执行中', memo TEXT DEFAULT '', created_at TEXT DEFAULT '')""",

    # ---------------- 风险/政策
    """CREATE TABLE IF NOT EXISTS risks (
        id INTEGER PRIMARY KEY AUTOINCREMENT, entity TEXT DEFAULT '',
        period TEXT DEFAULT '', code TEXT DEFAULT '', level TEXT DEFAULT '提',
        title TEXT DEFAULT '', detail TEXT DEFAULT '', weight INTEGER DEFAULT 10,
        status TEXT DEFAULT '待处理', handler TEXT DEFAULT '',
        created_at TEXT DEFAULT '', closed_at TEXT DEFAULT '')""",
    """CREATE TABLE IF NOT EXISTS policies (
        id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
        doc_no TEXT DEFAULT '', tax_type TEXT DEFAULT '', category TEXT DEFAULT '',
        effect_date TEXT DEFAULT '', expire_date TEXT DEFAULT '',
        summary TEXT DEFAULT '', content TEXT DEFAULT '',
        tags TEXT DEFAULT '', status TEXT DEFAULT '有效', created_at TEXT DEFAULT '')""",

    # ---------------- 平台域
    """CREATE TABLE IF NOT EXISTS notices (
        id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
        body TEXT DEFAULT '', author TEXT DEFAULT '', top INTEGER DEFAULT 0,
        created_at TEXT DEFAULT '')""",
    """CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT DEFAULT '',
        username TEXT DEFAULT '', action TEXT DEFAULT '', target TEXT DEFAULT '',
        detail TEXT DEFAULT '', ip TEXT DEFAULT '')""",
    """CREATE TABLE IF NOT EXISTS idem_keys (
        key TEXT PRIMARY KEY, username TEXT DEFAULT '', path TEXT DEFAULT '',
        status INTEGER DEFAULT 200, body TEXT DEFAULT '', created_at TEXT DEFAULT '')""",
    """CREATE TABLE IF NOT EXISTS sync_state (
        entity TEXT PRIMARY KEY, version INTEGER DEFAULT 0, updated_at TEXT DEFAULT '')""",
    """CREATE TABLE IF NOT EXISTS tax_rules (
        key TEXT PRIMARY KEY, value TEXT DEFAULT '')""",
]

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_inv_entity ON invoices(entity, period)",
    "CREATE INDEX IF NOT EXISTS idx_inv_kind ON invoices(kind, status)",
    "CREATE INDEX IF NOT EXISTS idx_decl_entity ON declarations(entity, period)",
    "CREATE INDEX IF NOT EXISTS idx_decl_status ON declarations(status)",
    "CREATE INDEX IF NOT EXISTS idx_vou_period ON vouchers(entity, period)",
    "CREATE INDEX IF NOT EXISTS idx_risk_entity ON risks(entity, status)",
    "CREATE INDEX IF NOT EXISTS idx_log_ts ON logs(ts)",
    "CREATE INDEX IF NOT EXISTS idx_item_inv ON invoice_items(invoice)",
]


def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def today():
    return time.strftime("%Y-%m-%d")


def connect():
    d = os.path.dirname(DB_PATH)
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=15)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout=15000")
    c.execute("PRAGMA foreign_keys=ON")
    return c


def init():
    """建表 + 索引 + 只在首次设 WAL（重复设 journal_mode 会与并发连接冲突）。"""
    global _INITED
    with _LOCK:
        c = connect()
        if not _INITED:
            c.execute("PRAGMA journal_mode=WAL")
            _INITED = True
        for sql in SCHEMA:
            c.execute(sql)
        for sql in INDEXES:
            c.execute(sql)
        c.commit()
        c.close()


def rows(sql, args=()):
    with _LOCK:
        c = connect()
        try:
            return [dict(r) for r in c.execute(sql, args).fetchall()]
        finally:
            c.close()


def one(sql, args=()):
    with _LOCK:
        c = connect()
        try:
            r = c.execute(sql, args).fetchone()
            return dict(r) if r else None
        finally:
            c.close()


def val(sql, args=(), default=None):
    r = one(sql, args)
    if r is None:
        return default
    v = list(r.values())[0]
    return default if v is None else v


def run(sql, args=()):
    with _LOCK:
        c = connect()
        try:
            cur = c.execute(sql, args)
            c.commit()
            return cur.rowcount
        finally:
            c.close()


def run_many(sql, seq):
    with _LOCK:
        c = connect()
        try:
            cur = c.executemany(sql, seq)
            c.commit()
            return cur.rowcount
        finally:
            c.close()


def insert(table, data):
    keys = list(data.keys())
    sql = "INSERT INTO %s (%s) VALUES (%s)" % (
        table, ",".join(keys), ",".join("?" * len(keys)))
    run(sql, tuple(data[k] for k in keys))
    return data


def update(table, key_field, key_value, data):
    keys = [k for k in data if k != key_field]
    if not keys:
        return 0
    sql = "UPDATE %s SET %s WHERE %s=?" % (
        table, ",".join("%s=?" % k for k in keys), key_field)
    return run(sql, tuple(data[k] for k in keys) + (key_value,))


def gen_no(table, prefix, col="no"):
    """单号生成：MAX 尾号 +1，空号优先复用。"""
    pat = re.compile(r"^%s(\d+)$" % re.escape(prefix))
    used = set()
    for r in rows("SELECT %s AS c FROM %s" % (col, table)):
        m = pat.match(str(r["c"] or ""))
        if m:
            used.add(int(m.group(1)))
    n = 1
    while n in used:
        n += 1
    return "%s%04d" % (prefix, n)


def bumpsync(*entities):
    """递增实体同步版本，供增量同步接口使用。"""
    ts = now()
    for e in entities:
        if val("SELECT 1 FROM sync_state WHERE entity=?", (e,)):
            run("UPDATE sync_state SET version=version+1, updated_at=? WHERE entity=?", (ts, e))
        else:
            run("INSERT INTO sync_state (entity,version,updated_at) VALUES (?,1,?)", (e, ts))


def version_of(entity):
    return int(val("SELECT version FROM sync_state WHERE entity=?", (entity,), 0) or 0)


def rule(key, default=""):
    v = val("SELECT value FROM tax_rules WHERE key=?", (key,), None)
    return default if v is None else v


def set_rule(key, value):
    if val("SELECT 1 FROM tax_rules WHERE key=?", (key,)):
        run("UPDATE tax_rules SET value=? WHERE key=?", (str(value), key))
    else:
        run("INSERT INTO tax_rules (key,value) VALUES (?,?)", (key, str(value)))


def all_rules():
    return {r["key"]: r["value"] for r in rows("SELECT key,value FROM tax_rules")}
