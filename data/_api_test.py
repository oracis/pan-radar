# -*- coding: utf-8 -*-
"""后端响应健壮性测试。

核心断言：**任何情况下都不能返回空 body**。
之前前端报 "Unexpected end of JSON input"，根源就是异常冒泡出
BaseHTTPRequestHandler → 连接被直接关掉 → 前端收到 0 字节。
"""
import os
import sys
import json
import time
import threading
import traceback
import urllib.request
import http.client

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import panradar as P                                    # noqa: E402

OUT = []
FAIL = 0


def chk(name, cond, extra=""):
    global FAIL
    if not cond:
        FAIL += 1
        OUT.append("FAIL %s%s" % (name, ("  ->  " + str(extra)) if extra else ""))
    else:
        OUT.append("OK   %s" % name)


def get(port, path, timeout=180):
    req = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()                          # 错误码也要读 body


def main():
    cfg = P.load_config()
    store = P.Store(P.DB_PATH)

    class BoomStore:
        """history() 必炸，其余转发 —— 模拟路由内部抛异常。"""
        def history(self):
            raise RuntimeError("模拟内部错误")

        def __getattr__(self, k):
            return getattr(store, k)

    orig_store = P.Handler.store
    P.Handler.cfg = cfg
    P.Handler.store = BoomStore()
    P.Handler.engine = P.Engine(cfg, store)

    httpd = P.ThreadingHTTPServer(("127.0.0.1", 0), P.Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    OUT.append("测试服务端口: %d" % port)

    # 1) 路由内部抛异常 —— 必须回 JSON 500，而不是空响应
    try:
        code, body = get(port, "/api/history")
        chk("路由异常返回 500", code == 500, code)
        chk("路由异常仍返回非空 body", len(body) > 0, "%d 字节" % len(body))
        d = json.loads(body.decode("utf-8"))             # 能解析成 JSON 才算数
        chk("异常响应是合法 JSON 且 ok=false", d.get("ok") is False)
        chk("异常响应说明是服务内部错误",
            "服务内部错误" in (d.get("error") or ""), d.get("error"))
        chk("异常响应仍带 items/groups/clusters 空壳",
            d.get("items") == [] and d.get("groups") == [] and d.get("clusters") == [])
    except Exception as e:
        chk("路由异常场景整体", False, "%r" % e)

    # 2) 未知路径 404 也必须带 body
    try:
        code, body = get(port, "/api/nope")
        chk("未知路径返回 404", code == 404, code)
        chk("404 有 body", len(body) > 0, "%d 字节" % len(body))
    except Exception as e:
        chk("404 场景整体", False, "%r" % e)

    # 3) 响应里混进不可序列化对象（set）也不能炸 —— default=str 兜底
    orig_search = P.Engine.search
    try:
        def fake_search(self, *a, **k):
            return {"ok": True, "queries": [], "items": [], "groups": [],
                    "clusters": [], "suggest": [],
                    "stats": {"total": 0, "bad": {"x", "y"}}}   # set 不可 JSON 序列化
        P.Engine.search = fake_search
        code, body = get(port, "/api/search?main=x")
        chk("含 set 的响应返回 200（未炸成空 body）", code == 200, code)
        chk("含 set 的响应 body 非空", len(body) > 0, "%d 字节" % len(body))
        d = json.loads(body.decode("utf-8"))
        chk("不可序列化字段降级成字符串",
            isinstance(d["stats"]["bad"], str), repr(d["stats"]["bad"]))
    except Exception as e:
        chk("序列化兜底场景整体", False, "%r" % e)
    finally:
        P.Engine.search = orig_search

    # 4) 正常路由不受影响
    try:
        code, body = get(port, "/api/meta")
        chk("/api/meta 返回 200", code == 200, code)
        d = json.loads(body.decode("utf-8"))
        chk("/api/meta 带 version", bool(d.get("version")), d.get("version"))
    except Exception as e:
        chk("meta 场景整体", False, "%r" % e)

    # 5) HEAD 必须支持 —— 不支持会让探测方误判为不可用，回退到内置静态服务
    #    渲染 index.html，导致所有 /api/* 404（截图中的「后端返回了空响应
    #    （HTTP 404）」的真因）。
    def head(port, path, timeout=10):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
        try:
            c.request("HEAD", path)
            r = c.getresponse()
            return r.status, r.read(), dict(r.getheaders())
        finally:
            c.close()

    try:
        # 先量一下 GET / 的 body 长度，用来跟 HEAD 的 Content-Length 对齐
        gcode, gbody = get(port, "/")
        length_get = len(gbody)
        code, body, hdr = head(port, "/")
        chk("HEAD / 不再是 501（关键回归）", code == 200, code)
        chk("HEAD / 头里 Content-Type 是 html",
            "html" in hdr.get("Content-Type", "").lower(),
            hdr.get("Content-Type"))
        chk("HEAD / Content-Length 等于 GET / body 长度",
            int(hdr.get("Content-Length", "0")) == length_get,
            "HEAD=%s GET=%d" % (hdr.get("Content-Length"), length_get))
        chk("HEAD / body 为空（HEAD 不该带 body）",
            len(body) == 0, "%d 字节" % len(body))
    except Exception as e:
        chk("HEAD / 整体", False, "%r" % e)

    try:
        code, body, hdr = head(port, "/api/meta")
        chk("HEAD /api/meta -> 200", code == 200, code)
        chk("HEAD /api/meta Content-Type 是 JSON",
            "json" in hdr.get("Content-Type", "").lower())
        chk("HEAD /api/meta body 为空", len(body) == 0)
    except Exception as e:
        chk("HEAD /api/meta 整体", False, "%r" % e)

    try:
        code, body, hdr = head(port, "/api/nope")
        chk("HEAD /api/nope -> 404", code == 404, code)
    except Exception as e:
        chk("HEAD /api/nope 整体", False, "%r" % e)

    # 探测对 /api/search 不该触发真实搜索（很贵：会打 5 个上游）
    orig_search2 = P.Engine.search
    try:
        search_calls = []
        def fake_search(self, *a, **k):
            search_calls.append((a, k))
            return {"ok": True, "items": [], "groups": [], "clusters": [],
                    "suggest": [], "stats": {"total": 0}}
        P.Engine.search = fake_search
        t0 = time.time()
        code, body, hdr = head(port, "/api/search?main=test")
        cost = time.time() - t0
        chk("HEAD /api/search -> 200", code == 200, code)
        chk("HEAD /api/search 不调用真实搜索",
            len(search_calls) == 0, "calls=%d" % len(search_calls))
        chk("HEAD /api/search 快速返回（< 0.3s）",
            cost < 0.3, "%.3fs" % cost)
    except Exception as e:
        chk("HEAD /api/search 整体", False, "%r" % e)
    finally:
        P.Engine.search = orig_search2

    P.Handler.store = orig_store
    httpd.shutdown()

    OUT.append("-" * 60)
    OUT.append("失败用例数: %d" % FAIL)
    with open(os.path.join(HERE, "_api_test.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(OUT))
    return 1 if FAIL else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        with open(os.path.join(HERE, "_api_test.txt"), "w", encoding="utf-8") as f:
            f.write("脚本异常:\n" + traceback.format_exc())
        sys.exit(2)
