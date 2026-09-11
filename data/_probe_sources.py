# -*- coding: utf-8 -*-
"""逐源探测：看每个源对目标关键词到底返回什么。"""
import os, sys, json, time, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import panradar as P

OUT = []


def probe(source, kw):
    t0 = time.time()
    try:
        items = P.query_source(source, kw, 40)
        secs = round(time.time() - t0, 1)
        rows = []
        for it in items[:6]:
            rows.append({
                "cloud": it.get("cloud"),
                "title": (it.get("title") or "")[:70],
                "pwd": it.get("pwd"),
                "url": (it.get("url") or "")[:90],
            })
        return {"ok": True, "n": len(items), "secs": secs, "rows": rows}
    except Exception as e:
        return {"ok": False, "secs": round(time.time() - t0, 1),
                "err": "%s: %s" % (type(e).__name__, str(e)[:200])}


def main():
    cfg = P.load_config()
    kws = sys.argv[1:] or ["风间影月"]
    for kw in kws:
        OUT.append("=" * 70)
        OUT.append("KEYWORD: %s" % kw)
        OUT.append("=" * 70)
        for src in cfg["sources"]:
            if not src.get("enabled"):
                continue
            r = probe(src, kw)
            OUT.append("")
            OUT.append("-- %s [%s]" % (src["name"], src.get("type")))
            OUT.append("   %s" % json.dumps({k: v for k, v in r.items() if k != "rows"},
                                            ensure_ascii=False))
            for row in r.get("rows", []):
                OUT.append("     * [%s] %s | pwd=%s" % (row["cloud"], row["title"], row["pwd"]))
                OUT.append("       %s" % row["url"])
    with open(os.path.join(HERE, "probe_sources.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(OUT))


if __name__ == "__main__":
    main()
