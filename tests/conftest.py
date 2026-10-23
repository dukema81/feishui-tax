# -*- coding: utf-8 -*-
"""飞税 pytest 公共夹具：临时库 + 进程内真实服务。"""
import os
import socket
import sys
import tempfile
import threading

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="session")
def svc():
    """启动一个干净的进程内服务实例，返回 (base_url, admin_token)。"""
    dbp = os.path.join(tempfile.gettempdir(), "feishui_pytest.db")
    for f in (dbp, dbp + "-wal", dbp + "-shm"):
        if os.path.exists(f):
            os.remove(f)
    os.environ["TAX_DB"] = dbp

    import db
    import seed
    import server

    db.init()
    seed.seed()

    port = _free_port()
    srv = server.ThreadingHTTPServer(("127.0.0.1", port), server.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d" % port
    yield base, _token(base)
    srv.shutdown()


def _token(base):
    import json
    import urllib.request
    req = urllib.request.Request(
        base + "/api/auth/login", method="POST",
        data=json.dumps({"username": "admin", "password": "tax@2026"}).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        j = json.loads(r.read())
    return j["data"]["token"]


@pytest.fixture()
def base(svc):
    return svc[0]


@pytest.fixture()
def token(svc):
    return svc[1]
