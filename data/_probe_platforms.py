# -*- coding: utf-8 -*-
"""探测：搜狗微信文章搜索 / 其他内容平台能否作为网盘链接来源。"""
import json, os, re, sys, time
import urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))
OP.addheaders = [("User-Agent", UA), ("Accept-Language", "zh-CN,zh;q=0.9")]

OUT = []
DISK_RE = re.compile(
    r"https?://(?:pan\.quark\.cn|pan\.baidu\.com|(?:www\.)?aliyundrive\.com|"
    r"(?:www\.)?alipan\.com|cloud\.189\.cn|www\.123pan\.com|115\.com|"
    r"www\.lanzou[a-z]\.com|pan\.xunlei\.com|share\.weiyun\.com|caiyun\.139\.com)"
    r"[/\w\-.?=&%#+]{2,140}", re.I)


def fetch(url, timeout=25, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    req.add_header("User-Agent", UA)
    req.add_header("Accept-Language", "zh-CN,zh;q=0.9")
    with OP.open(req, timeout=timeout) as resp:
        raw = resp.read()
    for enc in ("utf-8", "gbk", "gb18030"):
        try:
            return raw.decode(enc)
        except Exception:
            pass
    return raw.decode("utf-8", "replace")


def scan(name, url):
    t0 = time.time()
    try:
        html = fetch(url)
    except Exception as e:
        OUT.append("[FAIL] %-16s %s: %s" % (name, type(e).__name__, str(e)[:90]))
        return
    hits, seen = [], set()
    for m in DISK_RE.finditer(html):
        u = m.group(0).rstrip(".,;、")
        k = u.split("?")[0]
        if k not in seen:
            seen.add(k)
            hits.append(u)
    OUT.append("[%s] %-16s len=%d  %.1fs  disklinks=%d"
               % ("OK  " if hits else "NONE", name, len(html), time.time() - t0, len(hits)))
    for u in hits[:10]:
        OUT.append("      %s" % u[:130])
    if not hits:
        OUT.append("      head: %s" % re.sub(r"\s+", " ", html[:180]))


def main():
    kw = sys.argv[1] if len(sys.argv) > 1 else "风间影月"
    q = urllib.parse.quote(kw)
    cases = [
        ("weixin-sogou", "https://weixin.sogou.com/weixin?type=2&query=%s" % q),
        ("weixin-sogou2", "https://weixin.sogou.com/weixin?type=2&query=%s"
         % urllib.parse.quote(kw + " 夸克")),
        ("zhihu", "https://www.zhihu.com/search?type=content&q=%s" % q),
        ("juejin", "https://juejin.cn/search?query=%s" % q),
        ("csdn", "https://so.csdn.net/so/search?q=%s" % q),
        ("douban-g", "https://www.douban.com/search?q=%s" % q),
        ("smzdm", "https://search.smzdm.com/?c=home&s=%s" % q),
        ("52pojie", "https://www.52pojie.cn/search.php?mod=forum&srchtxt=%s" % q),
        ("tieba", "https://tieba.baidu.com/f/search/res?qw=%s" % q),
    ]
    for n, u in cases:
        scan(n, u)
        time.sleep(0.2)
    with open(os.path.join(HERE, "probe_platforms.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(OUT))


if __name__ == "__main__":
    main()
