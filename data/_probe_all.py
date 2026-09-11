# -*- coding: utf-8 -*-
"""拆解 PanSou 的 res=all 结构：results 里是否有 merge 漏掉的链接。"""
import json, os, re, time
import urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))
OP.addheaders = [("User-Agent", UA), ("Accept-Language", "zh-CN,zh;q=0.9")]

OUT = []


def get(url, timeout=60):
    r = urllib.request.Request(url, headers={"User-Agent": UA,
                                             "Accept": "application/json"})
    with OP.open(r, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def analyze(base, kw, tag):
    OUT.append("=" * 70)
    OUT.append("%s  kw=%s" % (tag, kw))
    for res in ("all", "merge"):
        u = base + "?" + urllib.parse.urlencode(
            {"kw": kw, "res": res, "src": "all"}, encoding="utf-8")
        t0 = time.time()
        try:
            txt = get(u)
            j = json.loads(txt)
        except Exception as e:
            OUT.append("  res=%-6s FAIL %s: %s" % (res, type(e).__name__, str(e)[:90]))
            continue
        d = j.get("data") or {}
        results = d.get("results") or []
        mbt = d.get("merged_by_type") or {}
        n_links = 0
        empty = 0
        cloud_ct = {}
        samples = []
        for r in results:
            links = r.get("links") or r.get("Links") or []
            if not links:
                empty += 1
            n_links += len(links)
            for lk in links:
                t = (lk.get("type") or "").lower()
                cloud_ct[t] = cloud_ct.get(t, 0) + 1
            if links and len(samples) < 4:
                samples.append(((r.get("title") or "")[:40],
                                links[0].get("url", "")[:60]))
        merged_n = sum(len(v or []) for v in mbt.values()) if isinstance(mbt, dict) else 0
        OUT.append("  res=%-6s  %.1fs  totals: total=%s results=%s links=%s empty_results=%s merged_by_type=%s"
                   % (res, time.time() - t0, d.get("total"), len(results),
                      n_links, empty, merged_n))
        OUT.append("           cloud_ct=%s" % json.dumps(cloud_ct, ensure_ascii=False))
        for t, u2 in samples:
            OUT.append("           * %s | %s" % (t, u2))
        if res == "all" and results:
            # 看第一条 result 的完整结构
            OUT.append("           keys of result[0]: %s"
                       % list(results[0].keys())[:20])
    return


def hp_pages():
    OUT.append("")
    OUT.append("=" * 70)
    OUT.append("hunhepan 翻页 (slim) kw=考研")
    titles = {}
    for page in range(1, 9):
        try:
            body = json.dumps({"q": "考研", "page": page, "size": 30}).encode()
            req = urllib.request.Request(
                "https://hunhepan.com/open/search/disk", data=body,
                headers={"Content-Type": "application/json", "User-Agent": UA,
                         "Referer": "https://hunhepan.com/search",
                         "Accept": "application/json, text/plain, */*"})
            with OP.open(req, timeout=20) as resp:
                j = json.loads(resp.read().decode("utf-8", "replace"))
            d = j.get("data") or {}
            lst = d.get("list") or []
            names = [re.sub(r"<[^>]+>", "", x.get("disk_name", "")) for x in lst]
            for nm in names:
                titles[nm] = titles.get(nm, 0) + 1
            OUT.append("  page=%-2s n=%-3s total=%-5s | %s"
                       % (page, len(lst), d.get("total"), " ; ".join(names[:2])[:70]))
            if not lst:
                break
            time.sleep(0.25)
        except Exception as e:
            OUT.append("  page=%-2s FAIL %s: %s" % (page, type(e).__name__, str(e)[:80]))
    OUT.append("  跨页唯一标题数=%d" % len(titles))


def main():
    analyze("https://so.252035.xyz/api/search", "风间影月", "so.252035.xyz")
    analyze("https://pansou.app/api/search", "风间影月", "pansou.app")
    hp_pages()
    with open(os.path.join(HERE, "probe_all.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(OUT))


if __name__ == "__main__":
    main()
