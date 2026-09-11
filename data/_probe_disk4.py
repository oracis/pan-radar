# -*- coding: utf-8 -*-
"""1) hunhepan 翻页上限  2) PanSou 实例的 channels/src 参数能否扩大结果。"""
import json, os, time
import urllib.parse, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))
OP.addheaders = [("User-Agent", UA), ("Accept-Language", "zh-CN,zh;q=0.9")]

OUT = []


def post(url, obj, referer, timeout=20):
    body = json.dumps(obj).encode("utf-8")
    h = {"Content-Type": "application/json", "User-Agent": UA, "Referer": referer,
         "Accept": "application/json, text/plain, */*"}
    r = urllib.request.Request(url, data=body, headers=h)
    with OP.open(r, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def get(url, timeout=45):
    r = urllib.request.Request(url, headers={"User-Agent": UA,
                                             "Accept": "application/json"})
    with OP.open(r, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def hp_pages():
    OUT.append("==== hunhepan 翻页 (slim) kw=考研")
    seen_total, per = 0, {}
    for page in range(1, 11):
        try:
            txt = post("https://hunhepan.com/open/search/disk",
                       {"q": "考研", "page": page, "size": 30},
                       "https://hunhepan.com/search")
            j = json.loads(txt)
            d = j.get("data") or {}
            lst = d.get("list") or []
            names = [re.sub(r"<[^>]+>", "", x.get("disk_name", ""))[:26] for x in lst]
            OUT.append("  page=%-2s n=%-3s total=%-5s  %s"
                       % (page, len(lst), d.get("total"), " | ".join(names[:3])))
            for nm in names:
                per[nm] = per.get(nm, 0) + 1
            if not lst:
                break
            time.sleep(0.3)
        except Exception as e:
            OUT.append("  page=%-2s FAIL %s: %s" % (page, type(e).__name__, str(e)[:80]))
    OUT.append("  唯一标题数=%d" % len(per))


def hp_sizes():
    OUT.append("")
    OUT.append("==== hunhepan size 变体 (slim) kw=考研")
    for size in (5, 10, 15, 20, 30, 50, 100):
        try:
            txt = post("https://hunhepan.com/open/search/disk",
                       {"q": "考研", "page": 1, "size": size},
                       "https://hunhepan.com/search")
            j = json.loads(txt)
            d = j.get("data") or {}
            OUT.append("  size=%-4s -> n=%s" % (size, len(d.get("list") or [])))
        except Exception as e:
            OUT.append("  size=%-4s FAIL %s" % (size, str(e)[:60]))


def pansou_params():
    OUT.append("")
    OUT.append("==== PanSou 实例参数探测 (kw=风间影月)")
    base = "https://so.252035.xyz/api/search"
    cases = [
        ("default", {"kw": "风间影月", "res": "merge", "src": "all"}),
        ("src=all+cloud", {"kw": "风间影月", "res": "all", "src": "all"}),
        ("src=tg", {"kw": "风间影月", "res": "merge", "src": "tg"}),
        ("src=plugin", {"kw": "风间影月", "res": "merge", "src": "plugin"}),
        ("channels", {"kw": "风间影月", "res": "merge", "src": "all",
                      "channels": "tgsearchers3,tgsearchers4,Aliyun_4K_Movies"}),
        ("refresh", {"kw": "风间影月", "res": "merge", "src": "all", "refresh": "true"}),
    ]
    for tag, qs in cases:
        u = base + "?" + urllib.parse.urlencode(qs, encoding="utf-8")
        try:
            txt = get(u)
            j = json.loads(txt)
            d = j.get("data") or {}
            mbt = d.get("merged_by_type") or {}
            n = sum(len(v or []) for v in mbt.values()) if isinstance(mbt, dict) else 0
            res = d.get("results")
            OUT.append("  %-14s code=%s total=%-5s merged=%-4s results=%s"
                       % (tag, j.get("code"), d.get("total"), n,
                          len(res) if isinstance(res, list) else "-"))
        except Exception as e:
            OUT.append("  %-14s FAIL %s: %s" % (tag, type(e).__name__, str(e)[:90]))
    OUT.append("")
    OUT.append("==== health")
    try:
        OUT.append(get("https://so.252035.xyz/api/health")[:700])
    except Exception as e:
        OUT.append("FAIL " + str(e)[:100])
    try:
        OUT.append(get("https://pansou.app/api/health")[:700])
    except Exception as e:
        OUT.append("pansou.app health FAIL " + str(e)[:100])


def main():
    hp_pages()
    hp_sizes()
    pansou_params()
    with open(os.path.join(HERE, "probe_disk4.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(OUT))


if __name__ == "__main__":
    main()
