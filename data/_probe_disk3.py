# -*- coding: utf-8 -*-
"""按 hunhepan 插件源码精确校准 4 个上游：URL/Referer/参数体/翻页。"""
import json, os, time
import urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))
OP.addheaders = [("User-Agent", UA), ("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8")]

OUT = []

UPSTREAMS = [
    ("hunhepan", "https://hunhepan.com/open/search/disk", "https://hunhepan.com/search", None),
    ("qkpanso",  "https://qkpanso.com/v1/search/disk",    "https://qkpanso.com/search",  None),
    ("kuake8",   "https://kuake8.com/v1/search/disk",     "https://kuake8.com/search",   None),
    ("misoso",   "https://www.misoso.cc/v1/search/disk",  "https://www.misoso.cc/search",
     "https://www.misoso.cc"),
]

FULL = {"page": 1, "q": "", "user": "", "exact": False, "format": [],
        "share_time": "", "size": 30, "type": "", "exclude_user": [],
        "adv_params": {"wechat_pwd": "", "platform": "pc"}}
SLIM = {"q": "", "page": 1, "size": 30}


def post(url, obj, referer, origin=None, timeout=20):
    body = json.dumps(obj).encode("utf-8")
    h = {"Content-Type": "application/json", "User-Agent": UA,
         "Referer": referer, "Accept": "application/json, text/plain, */*",
         "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}
    if origin:
        h["Origin"] = origin
    r = urllib.request.Request(url, data=body, headers=h)
    with OP.open(r, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def summarize(txt):
    try:
        j = json.loads(txt)
    except Exception:
        return None
    d = j.get("data") or {}
    lst = d.get("list") if isinstance(d, dict) else None
    return {"code": j.get("code"), "msg": str(j.get("msg") or "")[:30],
            "total": d.get("total") if isinstance(d, dict) else None,
            "n": len(lst) if isinstance(lst, list) else 0,
            "sample": (lst[0].get("disk_name") if isinstance(lst, list) and lst else "")}


def try_one(tag, url, ref, origin, body, q):
    b = dict(body)
    b["q"] = q
    t0 = time.time()
    try:
        txt = post(url, b, ref, origin)
        s = summarize(txt)
        if s is None:
            OUT.append("[HTML ] %-22s len=%d" % (tag, len(txt)))
        else:
            OUT.append("[%s] %-22s n=%-4s total=%-6s code=%s msg=%s | %s"
                       % ("OK    " if s["n"] else "EMPTY ", tag, s["n"], s["total"],
                          s["code"], s["msg"], s["sample"][:36]))
    except urllib.error.HTTPError as e:
        OUT.append("[HTTP ] %-22s -> %s" % (tag, e.code))
    except Exception as e:
        OUT.append("[FAIL ] %-22s -> %s: %s" % (tag, type(e).__name__, str(e)[:70]))
    OUT.append("          %.1fs" % (time.time() - t0))


def main():
    q = "考研"
    for name, url, ref, origin in UPSTREAMS:
        OUT.append("==== %s  %s" % (name, url))
        try_one(name + "/full", url, ref, origin, FULL, q)
        try_one(name + "/slim", url, ref, origin, SLIM, q)
    OUT.append("")
    OUT.append("==== hunhepan size 上限探测")
    for size in (30, 50, 100, 200):
        try_one("hunhepan size=%d" % size, UPSTREAMS[0][1], UPSTREAMS[0][2], None,
                dict(FULL, size=size), q)
    OUT.append("")
    OUT.append("==== 翻页验证 (hunhepan FULL)")
    for page in (1, 2, 3):
        try_one("hunhepan page=%d" % page, UPSTREAMS[0][1], UPSTREAMS[0][2], None,
                dict(FULL, page=page), q)
    with open(os.path.join(HERE, "probe_disk3.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(OUT))


if __name__ == "__main__":
    main()
