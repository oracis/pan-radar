# -*- coding: utf-8 -*-
"""批量探测候选数据源：自动识别协议、测试是否可用且能返回结果。"""
import json, os, re, sys, time
import urllib.parse, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
KW = "考研"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))
OP.addheaders = [("User-Agent", UA), ("Accept-Language", "zh-CN,zh;q=0.9")]

# (name, kind, url, extra_headers)
TARGETS = [
    # ---- PanSou 协议候选 ----
    ("pansou.us",        "pansou", "https://pansou.us/api/search", {}),
    ("pansou.cc",        "pansou", "https://pansou.cc/api/search", {}),
    ("api.pansou.cc",    "pansou", "https://api.pansou.cc/api/search", {}),
    ("pansou.252035",    "pansou", "http://pansou.252035.xyz/api/search", {}),
    ("so.pansou.cc",     "pansou", "https://so.pansou.cc/api/search", {}),
    ("panws.net",        "pansou", "https://panws.net/api/search", {}),
    ("pansousou.org",    "pansou", "https://www.pansousou.org/api/search", {}),
    ("panyq.com",        "pansou", "https://www.panyq.com/api/search", {}),
    ("dalipan.com",      "pansou", "https://www.dalipan.com/api/search", {}),
    ("xiaomapan.com",    "pansou", "https://www.xiaomapan.com/api/search", {}),
    ("lzpanx.com",       "pansou", "https://www.lzpanx.com/api/search", {}),
    ("pan666.net",       "pansou", "https://pan666.net/api/search", {}),
    ("qupansou.com",     "pansou", "https://qupansou.com/api/search", {}),
    ("jupansou",         "pansou", "https://www.jupansou.com/api/search", {}),
    # ---- disksearch 协议候选 ----
    ("hunhepan",   "disksearch", "https://hunhepan.com/open/search/disk",
     {"Referer": "https://hunhepan.com/search", "Origin": "https://hunhepan.com"}),
    ("qkpanso",    "disksearch", "https://www.qkpanso.com/v1/search/disk",
     {"Referer": "https://www.qkpanso.com/search", "Origin": "https://www.qkpanso.com"}),
    ("kuake8",     "disksearch", "https://kuake8.com/v1/search/disk",
     {"Referer": "https://kuake8.com/search", "Origin": "https://kuake8.com"}),
    ("yunpanx",    "disksearch", "https://www.yunpanx.com/api/search/disk",
     {"Referer": "https://www.yunpanx.com/", "Origin": "https://www.yunpanx.com"}),
    ("mypikpak",   "disksearch", "https://www.mypikpak.com/api/search/disk", {}),
    # ---- 其他已知站点 ----
    ("pansearch.me", "pansou", "https://www.pansearch.me/api/search", {}),
    ("panta(HTML)",  "html",   "https://www.91panta.cn/search?keyword=", {}),
]


def req(url, data=None, headers=None, timeout=20):
    h = dict(headers or {})
    if data is not None and "Content-Type" not in h:
        h["Content-Type"] = "application/json"
    r = urllib.request.Request(url, data=data, headers=h)
    with OP.open(r, timeout=timeout) as resp:
        return resp.read()


def probe(kind, url, headers):
    t0 = time.time()
    try:
        if kind == "pansou":
            u = url + "?" + urllib.parse.urlencode(
                {"kw": KW, "res": "merge", "src": "all"}, encoding="utf-8")
            raw = req(u, headers=headers)
        elif kind == "disksearch":
            body = json.dumps({
                "page": 1, "q": KW, "user": "", "exact": False, "format": [],
                "share_time": "", "size": 30, "type": "", "exclude_user": [],
                "adv_params": {"wechat_pwd": "", "platform": "pc"},
            }).encode("utf-8")
            raw = req(url, data=body, headers=headers)
        else:
            u = url + urllib.parse.quote(KW)
            raw = req(u, headers=headers)
        secs = round(time.time() - t0, 1)
        txt = raw.decode("utf-8", "replace")
        n, note = 0, ""
        try:
            j = json.loads(txt)
            if isinstance(j, dict):
                if j.get("data") and isinstance(j["data"], dict):
                    mbt = j["data"].get("merged_by_type")
                    if isinstance(mbt, dict):
                        n = sum(len(v or []) for v in mbt.values())
                    lst = j["data"].get("list")
                    if isinstance(lst, list):
                        n = len(lst)
                note = "code=%s msg=%s" % (j.get("code"), str(j.get("msg") or j.get("message"))[:40])
        except Exception:
            n = len(re.findall(r"https?://pan\.(?:quark|baidu)", txt, re.I))
            note = "html len=%d" % len(txt)
        return {"ok": True, "n": n, "secs": secs, "note": note}
    except urllib.error.HTTPError as e:
        return {"ok": False, "n": 0, "secs": round(time.time() - t0, 1),
                "note": "HTTP %s" % e.code}
    except Exception as e:
        return {"ok": False, "n": 0, "secs": round(time.time() - t0, 1),
                "note": "%s: %s" % (type(e).__name__, str(e)[:90])}


def main():
    out = ["# batch probe keyword=%s  %s" % (KW, time.strftime("%Y-%m-%d %H:%M"))]
    for name, kind, url, headers in TARGETS:
        r = probe(kind, url, headers)
        flag = "OK " if (r["ok"] and r["n"] > 0) else ("REACH" if r["ok"] else "FAIL")
        out.append("[%s] %-14s %-11s n=%-4s %-5ss  %s"
                   % (flag, name, kind, r["n"], r["secs"], r["note"]))
        out.append("       %s" % url)
    with open(os.path.join(HERE, "probe_batch.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(out))


if __name__ == "__main__":
    main()
