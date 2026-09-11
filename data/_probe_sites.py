# -*- coding: utf-8 -*-
"""从独立聚合站的前端产物里挖出真实 API 端点。"""
import json, os, re, time
import urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))
OP.addheaders = [("User-Agent", UA), ("Accept-Language", "zh-CN,zh;q=0.9")]

OUT = []
SITES = [
    ("lzpanx", "https://www.lzpanx.com/"),
    ("pansousou", "https://www.pansousou.org/"),
    ("qkpanso", "https://www.qkpanso.com/"),
    ("panws", "https://panws.net/"),
    ("xiaomapan", "https://www.xiaomapan.com/"),
]
API_RE = re.compile(r"""["'`]((?:https?:)?//[^"'`\s]{0,60}|/)[a-zA-Z0-9_\-./]{0,50}
                          (?:api|search|so|query)[a-zA-Z0-9_\-./]{0,40}["'`]""", re.X | re.I)
PLAIN_RE = re.compile(r"""["'`](/[a-zA-Z0-9_\-./]*(?:api|search|query)[a-zA-Z0-9_\-./]*)["'`]""", re.I)
ABS_RE = re.compile(r"""["'`](https?://[a-zA-Z0-9_\-.]{4,60}/[a-zA-Z0-9_\-./]*
                          (?:api|search|query)[a-zA-Z0-9_\-./]*)["'`]""", re.X | re.I)


def fetch(url, timeout=20):
    r = urllib.request.Request(url, headers={"User-Agent": UA})
    with OP.open(r, timeout=timeout) as resp:
        raw = resp.read()
    for enc in ("utf-8", "gbk"):
        try:
            return raw.decode(enc)
        except Exception:
            pass
    return raw.decode("utf-8", "replace")


def dig(name, home):
    OUT.append("=" * 66)
    OUT.append("%s  %s" % (name, home))
    try:
        html = fetch(home)
    except Exception as e:
        OUT.append("  home FAIL %s: %s" % (type(e).__name__, str(e)[:100]))
        return
    OUT.append("  home len=%d" % len(html))

    scripts = re.findall(r"""<script[^>]+src=["']([^"']+)["']""", html, re.I)
    OUT.append("  scripts=%d" % len(scripts))

    found = set()
    for m in PLAIN_RE.finditer(html):
        found.add(m.group(1))
    for m in ABS_RE.finditer(html):
        found.add(m.group(1))

    # 抓主要 JS 包再找
    cands = [s for s in scripts if s.endswith(".js")][:6]
    for s in cands:
        u = s if s.startswith("http") else urllib.parse.urljoin(home, s)
        try:
            js = fetch(u)
        except Exception as e:
            OUT.append("    js FAIL %s (%s)" % (u[:60], str(e)[:50]))
            continue
        got = []
        for m in PLAIN_RE.finditer(js):
            got.append(m.group(1))
        for m in ABS_RE.finditer(js):
            got.append(m.group(1))
        got = sorted(set(got))[:12]
        if got:
            OUT.append("    %s -> %s" % (u.split("/")[-1][:34], json.dumps(got, ensure_ascii=False)))
        for g in got:
            found.add(g)

    OUT.append("  --- endpoints ---")
    for f in sorted(found)[:24]:
        OUT.append("    %s" % f)
    if not found:
        OUT.append("    (none; html head: %s)"
                   % re.sub(r"\s+", " ", html[:200]))


def main():
    for n, h in SITES:
        try:
            dig(n, h)
        except Exception as e:
            OUT.append("%s CRASH %s" % (n, str(e)[:100]))
        time.sleep(0.3)
    with open(os.path.join(HERE, "probe_sites.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(OUT))


if __name__ == "__main__":
    main()
