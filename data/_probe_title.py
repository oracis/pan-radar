# -*- coding: utf-8 -*-
"""只看真命中的那些条目，弄明白标题为什么会以 "(" 结尾。"""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import panradar as P

cfg = P.load_config()
srcs = cfg["sources"]
print("源:", [s["name"] for s in srcs])

for q in ["风间影月", "Java高级工程师"]:
    for src in srcs:
        print("=" * 72)
        print("查询: %s  @ %s" % (q, src["name"]))
        try:
            items = P.query_source(src, q, 45)
        except Exception as e:
            print("  失败:", e)
            continue
        print("  原始条数:", len(items))
        seen, n = set(), 0
        for it in items:
            if P.relevance(it, [q]) < 0.34:
                continue
            t = it.get("title") or ""
            if t in seen:
                continue
            seen.add(t)
            c = it.get("content") or ""
            print("  --- rel=%.2f" % P.relevance(it, [q]))
            print("  raw  :", repr(t[:140]))
            print("  clean:", repr(P._clean_title(t)))
            print("  ench :", repr(P._enrich_title(P._clean_title(t), c)))
            print("  cont :", repr(c[:140]))
            n += 1
            if n >= 5:
                break
        if n == 0:
            print("  （无真命中）")
