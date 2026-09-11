# -*- coding: utf-8 -*-
"""真实数据验收：质量标签 + 跨网盘聚合。"""
import json
import os
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
B = "http://127.0.0.1:8931"
OUT = []


def gj(p, q=None, t=200):
    u = B + p + ("?" + urllib.parse.urlencode(q, encoding="utf-8") if q else "")
    with urllib.request.urlopen(u, timeout=t) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


try:
    with urllib.request.urlopen(B + "/", timeout=20) as r:
        html = r.read().decode("utf-8", "replace")
    OUT.append("页面 / -> %s  %d 字节 | 含视图切换: %s | 含标签样式: %s"
               % (r.status, len(html), "viewbar" in html, ".tag.good" in html))
    m = gj("/api/meta")
    OUT.append("版本 -> %s" % m["version"])
except Exception as e:
    OUT.append("启动检查失败: %s" % e)

KW = ["Java高级工程师", "风间影月", "Vibe Coding 一人团队项目开发实战"]
for kw in KW:
    try:
        r = gj("/api/search", {"main": kw})
    except Exception as e:
        OUT.append("\n== 搜「%s」失败: %s" % (kw, e))
        continue
    if not r.get("ok"):
        OUT.append("\n== 搜「%s」返回失败: %s" % (kw, r.get("error")))
        continue
    st = r["stats"]
    cls = r.get("clusters") or []
    OUT.append("")
    OUT.append("=" * 74)
    OUT.append("搜「%s」-> 命中 %s 条（原始 %s）-> 聚成 %s 组"
               % (kw, st["total"], st["raw"], len(cls)))
    OUT.append("-" * 74)
    for c in cls[:8]:
        tags = " ".join("[%s]" % t["t"] for t in (c.get("tags") or []))
        OUT.append("  %s" % c["title"][:62])
        OUT.append("      %d 个分享 · %s%s"
                   % (c["n"], " / ".join(c.get("cloud_labels") or []),
                      "   " + tags if tags else ""))
        for it in c["items"][:3]:
            OUT.append("        · %-8s %s%s"
                       % (it["cloud_label"], it["url"][:64],
                          "  提取码 " + it["pwd"] if it.get("pwd") else ""))
    if cls:
        multi = [c for c in cls if c["n"] > 1]
        OUT.append("  --> %d/%d 组含多个分享（原本要逐条对比才能发现是同一份）"
                   % (len(multi), len(cls)))
        cnt = {}
        for c in cls:
            for t in (c.get("tags") or []):
                cnt[t["t"]] = cnt.get(t["t"], 0) + 1
        OUT.append("  --> 标签分布: %s"
                   % ("、".join("%s×%d" % kv for kv in
                                sorted(cnt.items(), key=lambda x: -x[1])) or "无"))
        best = cls[0]
        OUT.append("  --> 首组标签: %s"
                   % ("、".join(t["t"] for t in (best.get("tags") or [])) or "无"))

with open(os.path.join(HERE, "_feat_final.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(OUT))
print("\n".join(OUT))
