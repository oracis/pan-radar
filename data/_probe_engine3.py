# -*- coding: utf-8 -*-
"""深度分析 360/搜狗 搜索结果里的网盘链接提取率。"""
import json, os, re, sys, time
import urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))
OP.addheaders = [("User-Agent", UA), ("Accept-Language", "zh-CN,zh;q=0.9")]

OUT = []


def fetch(url, timeout=20):
    r = urllib.request.Request(url, headers={"User-Agent": UA,
                                             "Accept-Language": "zh-CN,zh;q=0.9"})
    with OP.open(r, timeout=timeout) as resp:
        raw = resp.read()
    for enc in ("utf-8", "gbk", "gb18030"):
        try:
            return raw.decode(enc)
        except Exception:
            pass
    return raw.decode("utf-8", "replace")


HOST_RE = re.compile(
    r"(pan\.quark\.cn|pan\.baidu\.com|aliyundrive\.com|alipan\.com|cloud\.189\.cn|"
    r"123pan\.com|115\.com|lanzou[a-z]\.com|pan\.xunlei\.com|caiyun\.139\.com|"
    r"weiyun\.com|aliyundrive\.com)", re.I)

FULL_RE = re.compile(
    r"https?://(?:pan\.quark\.cn|pan\.baidu\.com|(?:www\.)?aliyundrive\.com|"
    r"(?:www\.)?alipan\.com|cloud\.189\.cn|www\.123pan\.com|115\.com|"
    r"www\.lanzou[a-z]\.com|pan\.xunlei\.com|share\.weiyun\.com|caiyun\.139\.com)"
    r"[/\w\-.?=&%#+]{2,140}", re.I)


def analyze(name, url):
    try:
        html = fetch(url)
    except Exception as e:
        OUT.append("[FAIL] %s %s" % (name, str(e)[:120]))
        return
    hosts = {}
    for m in HOST_RE.finditer(html):
        h = m.group(1).lower()
        hosts[h] = hosts.get(h, 0) + 1
    fulls = []
    seen = set()
    for m in FULL_RE.finditer(html):
        u = m.group(0).rstrip(".,;、")
        if u not in seen:
            seen.add(u)
            fulls.append(u)
    OUT.append("[%s] len=%d  host-mentions=%s" % (name, len(html), json.dumps(hosts, ensure_ascii=False)))
    for u in fulls[:20]:
        OUT.append("     %s" % u[:150])
    if not fulls:
        # 看有没有被编码/转义的痕迹
        esc = re.findall(r"pan\.(?:quark|baidu)\.(?:cn|com)", html)
        OUT.append("     (no full url; raw host tokens=%d)" % len(esc))


def main():
    kws = sys.argv[1:] or ["风间影月"]
    for kw in kws:
        OUT.append("=" * 68)
        OUT.append("KW: %s" % kw)
        for suffix in ["", " 网盘", " 夸克网盘", " 百度网盘", " 提取码"]:
            q = urllib.parse.quote(kw + suffix)
            analyze("360 " + (suffix or "(bare)"), "https://www.so.com/s?q=%s" % q)
        analyze("sogou", "https://www.sogou.com/web?query=%s"
                % urllib.parse.quote(kw + " 网盘"))
        analyze("bing", "https://cn.bing.com/search?q=%s&count=30"
                % urllib.parse.quote(kw + " 网盘 提取码"))
    with open(os.path.join(HERE, "probe_engine3.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(OUT))


if __name__ == "__main__":
    main()
