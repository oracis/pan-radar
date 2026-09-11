# -*- coding: utf-8 -*-
"""探测：搜索引擎能否作为网盘链接的兜底通道。"""
import json, os, re, sys, time
import urllib.parse, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = []
DISK_RE = re.compile(
    r"https?://(?:pan\.quark\.cn|pan\.baidu\.com|www\.aliyundrive\.com|alipan\.com|"
    r"cloud\.189\.cn|www\.123pan\.com|115\.com|www\.lanzou[a-z]\.com|pan\.xunlei\.com)"
    r"/[^\s\"'<>\\]{3,}", re.I)


def opener():
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    op.addheaders = [
        ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
        ("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8"),
    ]
    return op


OP = opener()


def fetch(url, timeout=25, extra=None):
    req = urllib.request.Request(url)
    for k, v in (extra or {}).items():
        req.add_header(k, v)
    with OP.open(req, timeout=timeout) as r:
        raw = r.read()
    for enc in ("utf-8", "gbk", "gb18030"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", "replace")


def try_engine(name, url, enc_hint=""):
    t0 = time.time()
    try:
        html = fetch(url)
        secs = round(time.time() - t0, 1)
        links = []
        for m in DISK_RE.finditer(html):
            links.append(m.group(0))
        # 去重保序
        seen, uniq = set(), []
        for l in links:
            if l not in seen:
                seen.add(l)
                uniq.append(l)
        OUT.append("-- %s -> %s  len=%d  secs=%s  disklinks=%d"
                   % (name, "OK", len(html), secs, len(uniq)))
        for l in uniq[:12]:
            OUT.append("     %s" % l[:130])
        if not uniq:
            OUT.append("     (no direct disk link in html; sample: %s)"
                       % re.sub(r"\s+", " ", html[:300]))
    except Exception as e:
        OUT.append("-- %s -> FAIL %s: %s" % (name, type(e).__name__, str(e)[:180]))


def main():
    kw = sys.argv[1] if len(sys.argv) > 1 else "风间影月"
    q = urllib.parse.quote(kw)
    qd = urllib.parse.quote(kw + " 夸克网盘")
    cases = [
        ("bing.com", "https://www.bing.com/search?q=%s&setlang=zh-CN" % qd),
        ("cn.bing.com", "https://cn.bing.com/search?q=%s" % qd),
        ("ddg-html", "https://html.duckduckgo.com/html/?q=%s" % qd),
        ("sogou", "https://www.sogou.com/web?query=%s" % qd),
        ("so.com(360)", "https://www.so.com/s?q=%s" % qd),
        ("baidu", "https://www.baidu.com/s?wd=%s" % qd),
        ("quark-so", "https://quark.sm.cn/s?q=%s" % qd),
        ("bilibili-so", "https://search.bilibili.com/all?keyword=%s" % q),
    ]
    for name, url in cases:
        try_engine(name, url)
    OUT.append("")
    OUT.append("DISK_LINK_SAMPLE for kw=%s" % kw)
    with open(os.path.join(HERE, "probe_engine.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(OUT))


if __name__ == "__main__":
    main()
