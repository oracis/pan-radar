# -*- coding: utf-8 -*-
"""验证：从 Bing / 360 搜索结果中解码出真实网盘链接。"""
import base64, json, os, re, sys, time
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
    r"www\.lanzou[a-z]\.com|pan\.xunlei\.com|share\.weiyun\.com|"
    r"caiyun\.139\.com|www\.aliyundrive\.com)[/\w\-.?=&%#]{0,120}", re.I)


def fetch(url, timeout=20):
    req = urllib.request.Request(url)
    req.add_header("User-Agent", UA)
    req.add_header("Accept-Language", "zh-CN,zh;q=0.9")
    with OP.open(req, timeout=timeout) as r:
        raw = r.read()
    for enc in ("utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except Exception:
            pass
    return raw.decode("utf-8", "replace")


def b64_url(tok):
    """Bing 的 u=a1<base64url> 还原为真实 URL。"""
    if tok.startswith("a1"):
        tok = tok[2:]
    pad = "=" * (-len(tok) % 4)
    try:
        return base64.urlsafe_b64decode(tok + pad).decode("utf-8", "replace")
    except Exception:
        return ""


def scan(html, label):
    found = []
    # 1) 明文链接
    for m in DISK_RE.finditer(html):
        found.append(("plain", m.group(0)))
    # 2) Bing 重定向
    for m in re.finditer(r"[?&]u=(a1[A-Za-z0-9_\-]+)", html):
        real = b64_url(m.group(1))
        if DISK_RE.match(real):
            found.append(("b64", real))
    # 3) 通用 URL 编码的链接
    for m in re.finditer(r"https?%3A%2F%2F(?:pan\.quark\.cn|pan\.baidu\.com)[^\"'&\s]{5,120}", html, re.I):
        found.append(("urlenc", urllib.parse.unquote(m.group(0))))
    # 去重
    seen, uniq = set(), []
    for k, v in found:
        v = v.rstrip(".,;、")
        key = v.split("?")[0] + "|" + (v.split("pwd=")[-1] if "pwd=" in v else "")
        if key not in seen:
            seen.add(key)
            uniq.append((k, v))
    return uniq


def run(name, url):
    try:
        html = fetch(url)
        u = scan(html, name)
        OUT.append("-- %s  len=%d  hits=%d" % (name, len(html), len(u)))
        for k, v in u[:15]:
            OUT.append("     [%s] %s" % (k, v[:140]))
    except Exception as e:
        OUT.append("-- %s  FAIL %s: %s" % (name, type(e).__name__, str(e)[:150]))


def main():
    kws = sys.argv[1:] or ["风间影月", "Vibe Coding 一人团队项目开发实战"]
    for kw in kws:
        OUT.append("=" * 68)
        OUT.append("KW: %s" % kw)
        q1 = urllib.parse.quote(kw)
        q2 = urllib.parse.quote(kw + " 网盘")
        q3 = urllib.parse.quote(kw + " 夸克")
        run("Bing", "https://www.bing.com/search?q=%s&count=30" % q2)
        run("Bing-quark", "https://www.bing.com/search?q=%s&count=30" % q3)
        run("360", "https://www.so.com/s?q=%s" % q2)
        run("360-quark", "https://www.so.com/s?q=%s" % q3)
        run("Bing/site-quark", "https://www.bing.com/search?q=%s&count=30"
            % urllib.parse.quote("site:pan.quark.cn " + kw))
    with open(os.path.join(HERE, "probe_engine2.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(OUT))


if __name__ == "__main__":
    main()
