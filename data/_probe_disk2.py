# -*- coding: utf-8 -*-
"""用精简参数 {q,page,size} 重测 disksearch 系站点，并探测分页上限。"""
import json, os, time
import urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))
OP.addheaders = [("User-Agent", UA), ("Accept-Language", "zh-CN,zh;q=0.9")]

OUT = []

CANDIDATES = [
    ("hunhepan", "https://hunhepan.com/open/search/disk", "https://hunhepan.com/search"),
    ("qkpanso", "https://www.qkpanso.com/open/search/disk", "https://www.qkpanso.com/search"),
    ("kuake8", "https://kuake8.com/open/search/disk", "https://kuake8.com/search"),
    ("80691", "https://www.80691.com/open/search/disk", "https://www.80691.com/search"),
    ("pansou.pro", "https://pansou.pro/open/search/disk", "https://pansou.pro/search"),
    ("so51", "https://www.so51.cn/open/search/disk", "https://www.so51.cn/search"),
    ("vfan", "https://www.vfan.tv/open/search/disk", "https://www.vfan.tv/search"),
    ("romkow", "https://www.romkow.com/open/search/disk", "https://www.romkow.com/search"),
    ("panyq", "https://www.panyq.com/open/search/disk", "https://www.panyq.com/search"),
    ("xiaomapan", "https://www.xiaomapan.com/open/search/disk", "https://www.xiaomapan.com/search"),
]


def post(url, obj, referer, timeout=20):
    body = json.dumps(obj).encode("utf-8")
    h = {"Content-Type": "application/json", "User-Agent": UA,
         "Referer": referer, "Origin": referer.rsplit("/", 1)[0],
         "Accept": "application/json, text/plain, */*"}
    r = urllib.request.Request(url, data=body, headers=h)
    with OP.open(r, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def summarize(txt):
    try:
        j = json.loads(txt)
    except Exception:
        return None
    code = j.get("code")
    data = j.get("data") or {}
    lst = data.get("list") if isinstance(data, dict) else None
    return {"code": code, "msg": str(j.get("msg") or "")[:40],
            "total": data.get("total") if isinstance(data, dict) else None,
            "n": len(lst) if isinstance(lst, list) else 0,
            "sample": (lst[0].get("disk_name") if isinstance(lst, list) and lst else "")}


def main():
    q = "考研"
    for name, url, ref in CANDIDATES:
        for size in (30, 100):
            t0 = time.time()
            try:
                txt = post(url, {"q": q, "page": 1, "size": size}, ref)
                s = summarize(txt)
                if s is None:
                    OUT.append("[HTML] %-12s size=%-4s len=%d  (not json)"
                               % (name, size, len(txt)))
                else:
                    OUT.append("[%s] %-12s size=%-4s total=%-6s n=%-4s code=%s msg=%s | %s"
                               % ("OK   " if s["n"] else "EMPTY", name, size,
                                  s["total"], s["n"], s["code"], s["msg"], s["sample"][:40]))
            except urllib.error.HTTPError as e:
                OUT.append("[HTTP] %-12s size=%-4s -> %s" % (name, size, e.code))
            except Exception as e:
                OUT.append("[FAIL] %-12s size=%-4s -> %s: %s"
                           % (name, size, type(e).__name__, str(e)[:70]))
            OUT.append("        %s  (%.1fs)" % (url, time.time() - t0))
    with open(os.path.join(HERE, "probe_disk2.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(OUT))


if __name__ == "__main__":
    main()
