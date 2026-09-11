# -*- coding: utf-8 -*-
"""对比 res=all 与 res=merge：all 里是否存在被 merge 漏掉的真命中。"""
import json, os, re, time
import urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))
OP.addheaders = [("User-Agent", UA), ("Accept-Language", "zh-CN,zh;q=0.9")]

OUT = []


def get(url, timeout=70):
    r = urllib.request.Request(url, headers={"User-Agent": UA,
                                             "Accept": "application/json"})
    with OP.open(r, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def dump(base, kw, tag, tokens):
    OUT.append("=" * 72)
    OUT.append("%s   kw=%s   tokens=%s" % (tag, kw, tokens))
    u = base + "?" + urllib.parse.urlencode(
        {"kw": kw, "res": "all", "src": "all"}, encoding="utf-8")
    t0 = time.time()
    try:
        j = json.loads(get(u))
    except Exception as e:
        OUT.append("  FAIL %s: %s" % (type(e).__name__, str(e)[:100]))
        return
    d = j.get("data") or {}
    results = d.get("results") or []
    OUT.append("  %.1fs  results=%d" % (time.time() - t0, len(results)))

    # 本地按 token 过滤（标题/内容任一命中全部 token 才算强命中）
    strong, weak = [], []
    for r in results:
        title = (r.get("title") or "")
        content = (r.get("content") or "")[:400]
        hay = title + " " + content
        hit = sum(1 for t in tokens if t in hay)
        links = r.get("links") or []
        if not links:
            continue
        if hit == len(tokens):
            strong.append((title[:56], links[0].get("type"), links[0].get("url", "")[:60],
                           r.get("channel") or ""))
        elif hit >= 1 and len(tokens) > 1:
            weak.append((title[:56], links[0].get("type"), hit))

    OUT.append("  local-filter: strong=%d  weak=%d" % (len(strong), len(weak)))
    OUT.append("  --- strong samples ---")
    seen = set()
    for t, ty, u2, ch in strong:
        k = u2.split("?")[0]
        if k in seen:
            continue
        seen.add(k)
        OUT.append("     [%s] %s | %s  (ch=%s)" % (ty, t, u2, ch[:22]))
        if len(seen) >= 25:
            break
    OUT.append("  --- weak samples ---")
    seen2 = set()
    for t, ty, hit in weak:
        if t in seen2:
            continue
        seen2.add(t)
        OUT.append("     hit=%d [%s] %s" % (hit, ty, t))
        if len(seen2) >= 12:
            break


def main():
    dump("https://so.252035.xyz/api/search", "风间影月", "so.252035.xyz",
         ["风间影月"])
    dump("https://so.252035.xyz/api/search", "Java高级工程师", "so.252035.xyz",
         ["Java", "高级工程师"])
    dump("https://pansou.app/api/search", "Vibe Coding 一人团队", "pansou.app",
         ["Vibe", "Coding"])
    with open(os.path.join(HERE, "probe_filter.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(OUT))


if __name__ == "__main__":
    main()
