# -*- coding: utf-8 -*-
"""探测 pansou.us / hunhepan 的正确参数格式。"""
import json, os, time
import urllib.parse, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))
OP.addheaders = [("User-Agent", UA), ("Accept-Language", "zh-CN,zh;q=0.9")]

OUT = []


def post(url, obj, headers=None, timeout=20):
    h = {"Content-Type": "application/json"}
    h.update(headers or {})
    data = json.dumps(obj).encode("utf-8")
    r = urllib.request.Request(url, data=data, headers=h)
    with OP.open(r, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def get(url, headers=None, timeout=20):
    r = urllib.request.Request(url, headers=headers or {})
    with OP.open(r, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def mark(label, fn):
    t0 = time.time()
    try:
        t = fn()
        OUT.append("[OK  ] %s (%.1fs) len=%d" % (label, time.time() - t0, len(t)))
        OUT.append("       " + t[:600].replace("\n", " "))
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            body = ""
        OUT.append("[HTTP] %s -> %s  body=%s" % (label, e.code, body))
    except Exception as e:
        OUT.append("[FAIL] %s -> %s: %s" % (label, type(e).__name__, str(e)[:150]))


def main():
    # --- pansou.us 各种参数 ---
    base = "https://pansou.us/api/search"
    for qs in [
        {"kw": "考研", "res": "merge", "src": "all"},
        {"kw": "英语"},
        {"q": "考研"},
        {"kw": "考研", "res": "merge"},
        {"kw": "test"},
    ]:
        u = base + "?" + urllib.parse.urlencode(qs, encoding="utf-8")
        mark("pansou.us GET %s" % qs, lambda u=u: get(u))
    mark("pansou.us POST", lambda: post(base, {"kw": "考研", "res": "merge", "src": "all"}))
    mark("pansou.us health", lambda: get("https://pansou.us/api/health"))

    # --- hunhepan 参数探测 ---
    hp = "https://hunhepan.com/open/search/disk"
    hh = {"Referer": "https://hunhepan.com/search", "Origin": "https://hunhepan.com",
          "User-Agent": UA, "Accept": "application/json, text/plain, */*"}
    variants = [
        {"q": "考研", "page": 1, "size": 30},
        {"keyword": "考研", "page": 1, "size": 30},
        {"q": "考研", "p": 1, "size": 30, "type": ""},
        {"q": "考研", "page": 1, "size": 30, "exact": False, "format": [],
         "share_time": "", "type": "", "exclude_user": [], "adv_params": {}},
        {"q": "考研", "page": 1, "size": 30, "type": "all", "order": "default"},
    ]
    for v in variants:
        mark("hunhepan POST %s" % list(v.keys()), lambda v=v: post(hp, v, hh))

    # --- qkpanso 参数探测 ---
    qk = "https://www.qkpanso.com/v1/search/disk"
    qh = {"Referer": "https://www.qkpanso.com/search", "Origin": "https://www.qkpanso.com",
          "User-Agent": UA}
    for v in [
        {"q": "考研", "page": 1, "size": 30},
        {"keyword": "考研"},
        {"q": "考研", "page": 1, "size": 30, "exact": False, "format": [],
         "share_time": "", "type": "", "exclude_user": [], "adv_params": {}},
    ]:
        mark("qkpanso POST %s" % list(v.keys()), lambda v=v: post(qk, v, qh))

    with open(os.path.join(HERE, "probe_params.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(OUT))


if __name__ == "__main__":
    main()
