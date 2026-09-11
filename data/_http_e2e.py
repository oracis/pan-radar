# -*- coding: utf-8 -*-
"""HTTP 端到端验证：搜索 -> 再挖一次（refresh）-> 累积效果。"""
import json, os, time
import urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "http://127.0.0.1:8931"
OUT = []


def call(path, params=None, timeout=180):
    u = BASE + path
    if params:
        u += "?" + urllib.parse.urlencode(params, encoding="utf-8")
    with urllib.request.urlopen(u, timeout=timeout) as r:
        body = r.read().decode("utf-8", "replace")
    return json.loads(body)


def show(tag, r):
    st = r.get("stats", {})
    OUT.append("[%s] ok=%s total=%s shown=%s raw=%s secs=%s cached=%s"
               % (tag, r.get("ok"), st.get("total"), st.get("shown"),
                  st.get("raw"), st.get("secs"), st.get("cached")))
    for name, v in (st.get("sources") or {}).items():
        OUT.append("    - %s: ok=%s items=%s cached=%s %s"
                   % (name, v.get("ok"), v.get("items"), v.get("cached"),
                      v.get("error") or ""))
    for it in (r.get("items") or [])[:8]:
        OUT.append("      * [%s] rel=%s %s | %s"
                   % (it["cloud_label"], it.get("rel"), (it.get("title") or "")[:52],
                      it["url"][:60]))


def main():
    OUT.append("=== /api/meta")
    try:
        m = call("/api/meta")
        OUT.append("version=%s" % m.get("version"))
        for s in m.get("sources", []):
            OUT.append("    source enabled=%s %s" % (s["enabled"], s["name"]))
    except Exception as e:
        OUT.append("meta FAIL %s" % e)

    kw = "风间影月"
    OUT.append("")
    OUT.append("=== 第 1 次搜索（写缓存）")
    t0 = time.time()
    r1 = call("/api/search", {"main": kw})
    show("search#1", r1)

    OUT.append("")
    OUT.append("=== 第 2 次搜索（应命中缓存，秒回）")
    r2 = call("/api/search", {"main": kw})
    show("search#2", r2)

    OUT.append("")
    OUT.append("=== 再挖一次（refresh=1，跳过缓存并合并）")
    r3 = call("/api/search", {"main": kw, "refresh": "1"})
    show("dig", r3)

    OUT.append("")
    OUT.append("=== Vibe Coding 一人团队项目开发实战")
    r4 = call("/api/search", {"main": "Vibe Coding 一人团队项目开发实战"})
    show("vibe", r4)

    with open(os.path.join(HERE, "http_e2e.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(OUT))


if __name__ == "__main__":
    main()
