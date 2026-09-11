# -*- coding: utf-8 -*-
"""从 ReMan 系站点前端包里挖出搜索请求的签名/加密逻辑。"""
import os, re
import urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))
OP.addheaders = [("User-Agent", UA), ("Accept-Language", "zh-CN,zh;q=0.9")]

OUT = []


def fetch(url, timeout=30):
    r = urllib.request.Request(url, headers={"User-Agent": UA})
    with OP.open(r, timeout=timeout) as resp:
        raw = resp.read()
    return raw.decode("utf-8", "replace")


def snip(js, pat, label, width=260, limit=8):
    OUT.append("---- %s" % label)
    n = 0
    for m in re.finditer(pat, js, re.I):
        s = max(0, m.start() - width // 2)
        seg = js[s:m.start() + width]
        OUT.append("  ..." + seg.replace("\n", " ") + "...")
        n += 1
        if n >= limit:
            break
    if n == 0:
        OUT.append("  (no match)")


def main():
    base = "https://www.qkpanso.com"
    html = fetch(base + "/")
    scripts = re.findall(r"""<script[^>]+src=["']([^"']+\.js)["']""", html, re.I)
    OUT.append("scripts: %s" % scripts)

    # 找出主包与含 search/disk 的包
    targets = []
    for s in scripts:
        u = s if s.startswith("http") else urllib.parse.urljoin(base + "/", s)
        if "/assets/" in u:
            targets.append(u)
    OUT.append("targets: %s" % targets)

    alljs = []
    for u in targets[:14]:
        try:
            js = fetch(u)
        except Exception as e:
            OUT.append("FAIL %s %s" % (u, str(e)[:60]))
            continue
        name = u.split("/")[-1]
        if re.search(r"disk|search|sign|encrypt|md5|sha", js, re.I):
            OUT.append("=== %s (len=%d)  <== 命中关键字" % (name, len(js)))
            alljs.append((name, js))
        else:
            OUT.append("=== %s (len=%d)" % (name, len(js)))

    for name, js in alljs:
        OUT.append("")
        OUT.append("############ %s" % name)
        snip(js, r"v1/search/disk", "search/disk 端点")
        snip(js, r"[Ss]ign\s*[:=]|signature|x-sign|nonce|timestamp", "签名相关")
        snip(js, r"\bmd5\b|\bsha256\b|\bhmac\b|crypto", "哈希相关")
        snip(js, r"headers\s*[:=]\s*\{", "请求头构造")
        snip(js, r"adv_params", "adv_params")
        snip(js, r"aes|encrypt|decrypt|base64", "加解密")

    with open(os.path.join(HERE, "probe_sign.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(OUT))


if __name__ == "__main__":
    main()
