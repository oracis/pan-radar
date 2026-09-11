# -*- coding: utf-8 -*-
"""验证 PanSou 的 channels / src 参数（用实例 health 里真实存在的频道名）。"""
import json, os, time
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


def run(tag, base, qs):
    u = base + "?" + urllib.parse.urlencode(qs, encoding="utf-8")
    t0 = time.time()
    try:
        j = json.loads(get(u))
        d = j.get("data") or {}
        res = d.get("results")
        n = len(res) if isinstance(res, list) else 0
        mbt = d.get("merged_by_type") or {}
        mn = sum(len(v or []) for v in mbt.values()) if isinstance(mbt, dict) else 0
        OUT.append("[OK   ] %-34s %.1fs  total=%-5s results=%-5s merged=%s"
                   % (tag, time.time() - t0, d.get("total"), n, mn))
    except Exception as e:
        OUT.append("[FAIL ] %-34s %s: %s" % (tag, type(e).__name__, str(e)[:80]))


def main():
    base = "https://so.252035.xyz/api/search"
    OUT.append("### so.252035.xyz   kw=考研")
    run("baseline res=all src=all", base, {"kw": "考研", "res": "all", "src": "all"})
    run("src=tg", base, {"kw": "考研", "res": "all", "src": "tg"})
    run("src=plugin", base, {"kw": "考研", "res": "all", "src": "plugin"})
    run("channels=tgsearchers6", base,
        {"kw": "考研", "res": "all", "src": "all", "channels": "tgsearchers6"})
    run("channels=3 real ones", base,
        {"kw": "考研", "res": "all", "src": "all",
         "channels": "tgsearchers6,bdwpzhpd,leoziyuan"})
    run("channels=head1 bdwpzhpd", base,
        {"kw": "考研", "res": "all", "src": "all", "channels": "bdwpzhpd"})

    OUT.append("")
    OUT.append("### pansou.app   kw=考研")
    b2 = "https://pansou.app/api/search"
    run("baseline res=all src=all", b2, {"kw": "考研", "res": "all", "src": "all"})
    run("src=plugin", b2, {"kw": "考研", "res": "all", "src": "plugin"})

    with open(os.path.join(HERE, "probe_channels.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(OUT))


if __name__ == "__main__":
    main()
