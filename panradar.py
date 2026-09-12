#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PanRadar / 网盘资源雷达
=========================================================
零依赖本地 Web 应用：输入「作者名」或「课程名」，
聚合多个网盘搜索引擎，输出百度网盘 / 夸克网盘 / 阿里云盘等可下载路径。

用法:
    python panradar.py                     # 打开 http://127.0.0.1:8931
    python panradar.py --port 9000
    python panradar.py --selftest 英语      # 不开浏览器，命令行验证链路
    python panradar.py --no-cache          # 本次运行不读缓存

仅使用 Python 标准库，无需 pip install。

合规提示：本工具只聚合各搜索源已公开索引的分享链接，
请仅用于查找你有权获取的公开 / 授权内容，尊重原作者版权。
"""

import argparse
import csv
import concurrent.futures as cf
import functools
import hashlib
import io
import json
import os
import re
import socket
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:  # Windows 控制台中文输出
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

APP_DIR = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(APP_DIR, "web")
# 缓存目录可经环境变量覆盖：FC / 容器等 /code 只读场景需指向可写目录（如 /tmp/panradar）
DATA_DIR = os.environ.get("PANRADAR_DATA_DIR") or os.path.join(APP_DIR, "data")
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
DB_PATH = os.path.join(DATA_DIR, "panradar.db")
APP_VERSION = "1.4.1"
# 缓存命名空间：请求协议 / 过滤策略变了就改这里，避免旧缓存污染
# v5 = 改用 res=all 取原始结果 + 入库前宽松过滤 + 并集累积
CACHE_NS = "v5"

# --------------------------------------------------------------------------- #
# 网盘类型元数据
# --------------------------------------------------------------------------- #
CLOUDS = {
    "quark":  {"label": "夸克网盘",  "short": "夸克", "color": "#4f7cff"},
    "baidu":  {"label": "百度网盘",  "short": "百度", "color": "#2b6cff"},
    "aliyun": {"label": "阿里云盘",  "short": "阿里", "color": "#ff7a45"},
    "xunlei": {"label": "迅雷网盘",  "short": "迅雷", "color": "#1e9bff"},
    "tianyi": {"label": "天翼云盘",  "short": "天翼", "color": "#e03131"},
    "uc":     {"label": "UC 网盘",   "short": "UC",  "color": "#ff9f1c"},
    "mobile": {"label": "移动云盘",  "short": "移动", "color": "#12b886"},
    "115":    {"label": "115 网盘",  "short": "115", "color": "#0ca678"},
    "123":    {"label": "123 网盘",  "short": "123", "color": "#7950f2"},
    "pikpak": {"label": "PikPak",   "short": "PikPak", "color": "#845ef7"},
    "guangya": {"label": "光鸭云盘", "short": "光鸭", "color": "#f06595"},
    "magnet": {"label": "磁力链接",  "short": "磁力", "color": "#868e96"},
    "ed2k":   {"label": "电驴链接",  "short": "电驴", "color": "#868e96"},
    "others": {"label": "其他",      "short": "其他", "color": "#868e96"},
}
CLOUD_ORDER = list(CLOUDS.keys())

# 各源返回的网盘类型别名 -> 内部 key
_CLOUD_ALIAS = {
    "bdy": "baidu", "baidu": "baidu", "bd": "baidu",
    "aly": "aliyun", "alyun": "aliyun", "aliyun": "aliyun",
    "aliyundrive": "aliyun", "alipan": "aliyun",
    "quark": "quark", "quarkpan": "quark",
    "tianyi": "tianyi", "ty": "tianyi",
    "uc": "uc", "ucpan": "uc",
    "caiyun": "mobile", "mobile": "mobile", "139": "mobile",
    "115": "115", "115pan": "115",
    "xunlei": "xunlei", "xl": "xunlei",
    "123pan": "123", "123": "123",
    "pikpak": "pikpak", "guangya": "guangya", "gy": "guangya",
    "magnet": "magnet", "ed2k": "ed2k",
}


def _norm_cloud(raw):
    """把各源五花八门的网盘类型名归一成内部 key。"""
    c = (raw or "").strip().lower()
    c = _CLOUD_ALIAS.get(c, c)
    return c if c in CLOUDS else "others"

# 相关度阈值：>= 此值才算「真命中」，用于判断是否触发分词降级
RELEVANT_SCORE = 55.0

DEFAULT_CONFIG = {
    "config_version": 4,
    "port": 8931,
    "cache_ttl": 1800,
    "request_timeout": 35,
    "max_concurrency": 6,
    "max_requests": 14,
    "auto_degrade": True,
    # 相关度低于此值直接丢弃（LCS 占查询串的比例）。噪声源单字模糊匹配通常 < 0.35
    "drop_below": 0.34,
    "cloud_priority": ["quark", "baidu", "aliyun", "uc", "xunlei", "tianyi",
                       "mobile", "115", "123", "pikpak", "guangya"],
    "sources": [
        {"name": "PanSou · so.252035.xyz", "type": "pansou",
         "search_url": "https://so.252035.xyz/api/search", "enabled": True},
        {"name": "PanSou · pansou.app", "type": "pansou",
         "search_url": "https://pansou.app/api/search", "enabled": True},
        {"name": "混合盘搜索", "type": "disksearch_slim",
         "search_url": "https://hunhepan.com/open/search/disk",
         "referer": "https://hunhepan.com/search", "pages": 3, "enabled": True},
        {"name": "Misoso 夸克搜索", "type": "disksearch",
         "search_url": "https://www.misoso.cc/v1/search/disk",
         "referer": "https://www.misoso.cc/search",
         "origin": "https://www.misoso.cc", "enabled": True},
        {"name": "自建 PanSou (Docker)", "type": "pansou",
         "search_url": "http://127.0.0.1:8888/api/search", "enabled": False},
    ],
}


def _save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def load_config():
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    user_version = None
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                user = json.load(f)
            user_version = user.get("config_version")
            for k, v in user.items():
                if k == "sources" and isinstance(v, list) and v:
                    cfg["sources"] = v
                else:
                    cfg[k] = v
        except Exception as e:
            log("配置读取失败，使用默认配置: %s" % e)
    else:
        _save_config(cfg)

    # 版本迁移：数据源清单随版本更新；用户自加的源（不在默认清单里）保留
    if user_version != DEFAULT_CONFIG["config_version"]:
        known = {s.get("search_url") for s in DEFAULT_CONFIG["sources"]}
        extra = [s for s in cfg.get("sources", [])
                 if isinstance(s, dict) and s.get("search_url") not in known]
        cfg["sources"] = DEFAULT_CONFIG["sources"] + extra
        for k in ("request_timeout", "max_concurrency", "max_requests", "auto_degrade"):
            cfg[k] = DEFAULT_CONFIG[k]
        cfg["config_version"] = DEFAULT_CONFIG["config_version"]
        _save_config(cfg)
        log("配置已迁移到 v%d，数据源 %d 个（含自定义 %d 个）"
            % (cfg["config_version"], len(cfg["sources"]), len(extra)))
    return cfg


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    try:
        print("[%s] %s" % (ts, msg), flush=True)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# HTTP：显式绕过系统代理（本地代理会破坏 TLS / 返回 502）
# --------------------------------------------------------------------------- #
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_OPENER.addheaders = [
    ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    ("Accept", "application/json, text/plain, */*"),
    ("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8"),
]


def _do(req, timeout, retries=2):
    """带重试 / 退避的请求。每次重试换一次连接，规避偶发 403。"""
    last = None
    for attempt in range(retries + 1):
        try:
            with _OPENER.open(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            last = "HTTP %s" % e.code
            if e.code in (400, 401, 403, 414, 500, 502, 503):
                time.sleep(1.2 * (attempt + 1))
                continue
            if e.code == 429:
                # 限流不重试：对端已经记账，退避再打只会把这台机器钉得更死，
                # 还白白拖慢整次搜索（实测 hunhepan 被 429 后 3 次重试要等 9 秒）。
                # 直接交给上层做「分级冷却」，10 分钟后再见。
                break
            break
        except Exception as e:
            last = "%s: %s" % (type(e).__name__, e)
            time.sleep(0.8 * (attempt + 1))
    raise RuntimeError(last or "unknown error")


def http_json(url, timeout=60, retries=2):
    return _do(urllib.request.Request(url), timeout, retries)


def http_post_json(url, payload, headers=None, timeout=60, retries=2):
    body = json.dumps(payload).encode("utf-8")
    h = {"Content-Type": "application/json"}
    h.update(headers or {})
    return _do(urllib.request.Request(url, data=body, headers=h, method="POST"),
               timeout, retries)


# --------------------------------------------------------------------------- #
# 查询扩展
# --------------------------------------------------------------------------- #
_SEP_RE = re.compile(r"[|｜/／·・,，;；\-—_]+")


def _variants(text):
    """生成关键词变体：原串 / 去空格 / 分隔符转空格。"""
    out = []
    t = text.strip()
    for candidate in (t, re.sub(r"\s+", "", t), _SEP_RE.sub(" ", t)):
        c = re.sub(r"\s+", " ", candidate).strip()
        if c and c not in out:
            out.append(c)
    return out


def build_queries(main, author, deep=False):
    """按优先级生成查询词列表：作者+课程 > 课程 > 作者。"""
    main = (main or "").strip()
    author = (author or "").strip()
    seeds = []
    if main and author:
        seeds += ["%s %s" % (author, main), main, author]
    elif main:
        seeds += [main]
    elif author:
        seeds += [author]

    queries = []
    primaries = list(seeds)
    for s in primaries:
        for v in _variants(s):
            if v not in queries:
                queries.append(v)
    if deep:
        for s in primaries:
            for extra in ("教程", "课程", "全集", "资料", "实战"):
                q = "%s %s" % (s, extra)
                if q not in queries:
                    queries.append(q)
    return queries[:8 if deep else 3]


def token_queries(main, author):
    """空结果降级用：把输入拆成独立词（>=2 字符），逐词再搜。"""
    text = " ".join(x for x in (main, author) if x and x.strip()).strip()
    toks, seen = [], set()
    for t in re.split(r"[\s|｜/／,，;；、，]+", text):
        t = t.strip()
        if len(t) >= 2 and t not in seen:
            seen.add(t)
            toks.append(t)
    return toks


def input_tokens(main, author):
    """本地相关度判定用的 token 集（含分隔符切分，比 token_queries 更细）。"""
    text = " ".join(x for x in (main, author) if x and x.strip()).strip()
    toks, seen = [], set()
    for t in re.split(r"[\s|｜/／,，;；、·・\-—_]+", text):
        t = t.strip()
        if len(t) >= 2 and t.lower() not in seen:
            seen.add(t.lower())
            toks.append(t)
    if not toks and text:
        toks = [text]
    return toks


# --------------------------------------------------------------------------- #
# 数据源适配（PanSou 协议）
# --------------------------------------------------------------------------- #
_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(s):
    s = _TAG_RE.sub("", s or "")
    return re.sub(r"\s+", " ", s).strip()


def query_source(source, query, timeout):
    stype = (source.get("type") or "pansou").lower()
    if stype == "pansou":
        return _query_pansou(source, query, timeout)
    if stype == "disksearch":
        return _query_disksearch(source, query, timeout)
    if stype == "disksearch_slim":
        return _query_disksearch_slim(source, query, timeout)
    raise RuntimeError("未知数据源类型: %s" % stype)


def _query_pansou(source, query, timeout):
    """PanSou 协议：GET /api/search?kw=&res=all&src=all

    ⚠ 千万不要用 res=merge。实测同一个关键词：res=all 返回 324 条原始结果
    （3048 个链接），而 res=merge 只合并出 2 条 —— 会丢掉 97% 的结果，
    这是「明明有资源却搜不到」的首要原因。必须取原始 results[]，
    每条自带 links[]，再在本地按相关度过滤。
    """
    url = source["search_url"] + "?" + urllib.parse.urlencode(
        {"kw": query, "res": "all", "src": "all"}, encoding="utf-8")
    j = http_json(url, timeout=timeout)
    if j.get("code") not in (0, None) and not j.get("data"):
        raise RuntimeError(j.get("message") or "源返回异常")
    data = j.get("data") or {}
    results = data.get("results")
    items = []

    if isinstance(results, list) and results:
        for r in results:
            if not isinstance(r, dict):
                continue
            title = strip_html(r.get("title"))
            content = strip_html(r.get("content"))
            channel = r.get("channel") or ""
            for lk in (r.get("links") or []):
                if not isinstance(lk, dict):
                    continue
                u = (lk.get("url") or "").strip()
                if not u:
                    continue
                items.append({
                    "cloud": _norm_cloud(lk.get("type")),
                    "url": u,
                    "pwd": (lk.get("password") or "").strip(),
                    "title": title,
                    "content": content[:300],
                    "dt": r.get("datetime") or "",
                    "source": channel or "tg",
                    "images": r.get("images") or [],
                })

    # 同一响应里还带一份 merged_by_type —— 那是上游自己归类去重后的高精度结果
    # （数量很少但往往正是最精准的几条）。一并收下，去重交给后面统一处理。
    for cloud, arr in (data.get("merged_by_type") or {}).items():
        for it in (arr or []):
            if not isinstance(it, dict):
                continue
            u = (it.get("url") or "").strip()
            if not u:
                continue
            items.append({
                "cloud": _norm_cloud(cloud),
                "url": u,
                "pwd": (it.get("password") or "").strip(),
                "title": strip_html(it.get("note")),
                "content": "",
                "dt": it.get("datetime") or "",
                "source": it.get("source") or "",
                "images": it.get("images") or [],
            })
    return items


# disksearch 协议（hunhepan / misoso 等站共用）的网盘类型映射
_DISK_TYPE_MAP = {"BDY": "baidu", "ALY": "aliyun", "ALYUN": "aliyun", "QUARK": "quark",
                  "TIANYI": "tianyi", "UC": "uc", "CAIYUN": "mobile", "115": "115",
                  "XUNLEI": "xunlei", "123PAN": "123", "PIKPAK": "pikpak"}


def _query_disksearch(source, query, timeout):
    """misoso 系：POST 完整参数体，返回 data.list[]。"""
    headers = {"Referer": source.get("referer") or source["search_url"]}
    if source.get("origin"):
        headers["Origin"] = source["origin"]
    j = http_post_json(source["search_url"], {
        "page": 1, "q": query, "user": "", "exact": False, "format": [],
        "share_time": "", "size": 30, "type": "", "exclude_user": [],
        "adv_params": {"wechat_pwd": "", "platform": "pc"},
    }, headers=headers, timeout=timeout)
    code = j.get("code")
    if code == 417:          # 该站业务码：没有搜索结果，不算错误
        return []
    if code not in (200, 0, None):
        raise RuntimeError("code=%s %s" % (code, j.get("msg") or ""))
    data = j.get("data") or {}
    return _disk_items(data.get("list") or [], source)


def _query_disksearch_slim(source, query, timeout):
    """hunhepan 系：只吃 {q,page,size} 三个字段（多传就报「参数错误」）。

    该接口忽略 size，每页固定返回 10 条，必须翻页才拿得到更多。
    实测 total 可达 300，翻 3 页约 30 条、命中率可观。
    """
    pages = max(1, min(int(source.get("pages", 3)), 8))
    referer = source.get("referer") or source["search_url"]
    netloc = urllib.parse.urlparse(source["search_url"]).netloc
    headers = {"Referer": referer, "Origin": source.get("origin") or
               ("https://" + netloc)}
    items = []
    for page in range(1, pages + 1):
        try:
            j = http_post_json(source["search_url"],
                               {"q": query, "page": page, "size": 30},
                               headers=headers, timeout=timeout)
        except Exception:
            if page == 1:
                raise
            break                      # 后续页失败就算了，前面的照常返回
        code = j.get("code")
        if code not in (200, 0, None):
            if page == 1:
                return []              # 业务码 0/414 等都视为「无结果」
            break
        lst = (j.get("data") or {}).get("list") or []
        if not lst:
            break
        items.extend(_disk_items(lst, source))
    return items


def _disk_items(lst, source):
    """把 disksearch 系返回的 list[] 归一成内部 item。"""
    items = []
    netloc = urllib.parse.urlparse(source["search_url"]).netloc
    for it in lst:
        if not isinstance(it, dict):
            continue
        u = (it.get("link") or "").strip()
        if not u:
            continue
        raw_t = (it.get("disk_type") or "").strip()
        cloud = _DISK_TYPE_MAP.get(raw_t.upper(), _norm_cloud(raw_t))
        shared = it.get("shared_time") or it.get("create_time") or ""
        items.append({
            "cloud": cloud,
            "url": u,
            "pwd": (it.get("disk_pass") or "").strip(),
            "title": strip_html(it.get("disk_name")),
            "content": strip_html(it.get("files"))[:300],
            "dt": (shared.replace(" ", "T") + "Z") if shared else "",
            "source": it.get("share_user") or ("disk:" + netloc),
            "size": it.get("size") or 0,
            "images": [],
        })
    return items


# --------------------------------------------------------------------------- #
# 归一化 / 去重 / 打分
# --------------------------------------------------------------------------- #
_PWD_PATTERNS = [
    re.compile(r"(?:提取码|访问码|密码|pwd|password)\s*[:：=]\s*([A-Za-z0-9]{4,8})"),
    re.compile(r"[?&]pwd=([A-Za-z0-9]{4,8})"),
]
_ALIYUN_HOSTS = {"www.aliyundrive.com", "aliyundrive.com", "www.alipan.com",
                 "alipan.com", "www.alipan.com"}


def extract_pwd(item):
    if item.get("pwd"):
        return item["pwd"]
    for pat in _PWD_PATTERNS:
        m = pat.search(item.get("url", "")) or pat.search(item.get("title", ""))
        if m:
            return m.group(1)
    return ""


def dedupe_key(item):
    u = urllib.parse.urlparse(item["url"])
    host = u.netloc.lower()
    if item["cloud"] == "aliyun" or host in _ALIYUN_HOSTS:
        host = "alipan.com"
    if item["cloud"] == "magnet" or item["url"].startswith("magnet:"):
        xt = urllib.parse.parse_qs(u.query).get("xt", [""])[0]
        return "magnet|" + xt.lower()
    path = u.path.rstrip("/").lower()
    return "%s|%s%s" % (item["cloud"], host, path)


def _age_days(dt_str):
    if not dt_str:
        return None
    try:
        s = dt_str.replace("Z", "+00:00")
        d = datetime.fromisoformat(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        if d.year < 2000:
            return None
        return max(0.0, (datetime.now(timezone.utc) - d).total_seconds() / 86400.0)
    except Exception:
        return None


def _pick_title(a, b, tokens=None):
    """同一分享链接可能有多个来源给出不同标题，挑信息量最大的那个。

    踩过的坑：早先按「标题更短更干净」合并，结果把
    「马老师的Java高级工程师就业班」换成了别的源给出的「马老师的」，
    课程名整个丢失。改为：命中查询词多的优先，其次长度合理的优先。
    """
    def rank(t):
        tl = (t or "").lower()
        hits = sum(1 for k in (tokens or []) if k.lower() in tl)
        n = len(t or "")
        return (hits, 1 if 4 <= n <= 120 else 0, min(n, 120))
    return a if rank(a) > rank(b) else b


def _lcs_len(a, b):
    """最长公共子串长度（连续）。用于判断标题跟查询到底沾了多少真关系。"""
    if not a or not b:
        return 0
    if len(a) > len(b):
        a, b = b, a
    prev = [0] * (len(b) + 1)
    best = 0
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        ai = a[i - 1]
        for j in range(1, len(b) + 1):
            if ai == b[j - 1]:
                v = prev[j - 1] + 1
                cur[j] = v
                if v > best:
                    best = v
        prev = cur
    return best


def relevance(item, tokens):
    """0~1：查询 token 与「标题+文件列表」的最长公共子串占 token 的比例，取最大。

    这是本项目过滤噪声的关键指标。按「命中词数」判定会放过大量单字模糊匹配
    （搜「风间影月」返回《人间风月录》），而最长公共子串能区分：
      「风间影月」vs「慕课网Java高级工程师(风间影月)」-> 4/4 = 1.00  ✓
      「风间影月」vs「擦边短剧：人间风月录」        -> 1/4 = 0.25  ✗
    """
    if not tokens:
        return 1.0
    hay = ((item.get("title") or "") + " " + (item.get("content") or ""))[:600].lower()
    if not hay.strip():
        return 0.0
    vals, weights = [], []
    for t in tokens:
        tl = t.lower().strip()
        if len(tl) < 2:
            continue
        if tl in hay:
            vals.append(1.0)
        else:
            n = _lcs_len(tl, hay)
            # 只沾一两个字不算关系：搜「风间影月」返回《人间风月录》《名侦探柯南》
            # 都是这种巧合。长查询词要求至少连续命中 3 个字。
            need = 2 if len(tl) <= 3 else 3
            vals.append(n / len(tl) if n >= need else 0.0)
        weights.append(len(tl))
    if not vals:
        return 1.0
    # 按词长加权：长词信息量大。这样「Vibe Coding 一人团队项目开发实战」只命中
    # 后半段（标题写作「一人团队项目开发实战」）也能保住，不会因为漏了 Vibe/Coding 被丢
    return sum(v * w for v, w in zip(vals, weights)) / sum(weights)


_EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u2190-\u21FF]")


def _clean_title(t):
    """TG 频道来的标题常带营销前缀/emoji/话题标签，洗成干净的名字。

    例：'🗣名称：慕课网-Java高级工程师（风间影月）🏷 标签：#夸克网盘 #教程👉 链接：https://…'
      -> '慕课网-Java高级工程师（风间影月）'
    """
    t = _EMOJI_RE.sub(" ", t or "")
    m = re.search(r"(?:名称|资源名称|标题|课程)\s*[:：]\s*(.{2,90}?)"
                  r"(?=\s*(?:标签|亮点|链接|地址|简介|👉|$))", t)
    if m:
        t = m.group(1)
    t = re.sub(r"(?:链接|地址|URL|网址)\s*[:：]?\s*https?://\S+", " ", t, flags=re.I)
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"#\S+", " ", t)
    t = re.sub(r"\b(?:file|dir|folder)\s*[:：]", " ", t, flags=re.I)
    t = re.sub(r"\s+", " ", t).strip(" -—·|｜,，:：")
    return _trim_dangling(t)[:100]


def _trim_dangling(t):
    """裁掉上游字节截断留在末尾的半个括号。

    实测 title 字段会被硬截断成「慕课网-体系课-Java高级工程师(」这种样子，
    末尾挂着一个永远配不上的左括号。只在左括号出现在结尾 12 字内且不配对时
    才裁，避免误伤「超级工程 (2012) 1080P」「马老师的Java就业班（完结）」。
    """
    for op, cl in (("(", ")"), ("（", "）"), ("[", "]"), ("【", "】")):
        if t.count(op) > t.count(cl):
            i = t.rfind(op)
            if i >= 0 and len(t) - i <= 12:
                t = t[:i].strip(" -—·|｜,，:：")
    return t


# content 里「名称：」字段带的是完整名字，而 title 字段常被上游截断。
# 这是补全标题唯一可靠的来源，字段名各式各样，都收下。
_NAME_RE = re.compile(
    r"(?:资源名称|名称|标题|课程名|课程名?)\s*[:：]\s*(.{2,90}?)"
    r"(?=\s*(?:描述|简介|介绍|标签|亮点|链接|地址|大小|类型|提取码|\U0001F4DC|$))")

_KEY_PUNC_RE = re.compile(r"[\s()（）\[\]【】<>,，。.·\-—_+*:：&|｜/／\"'“”]+")


def _name_key(s):
    """标题归一化：去掉空格/括号/标点，只留内容，用于判断「谁是谁的前缀」。"""
    return _KEY_PUNC_RE.sub("", (s or "").lower())


def _name_from_content(content):
    """从 content 的「名称：xxx」字段抠出完整名字；没有就返回空串。"""
    c = re.sub(r"\s+", " ", _EMOJI_RE.sub(" ", content or "")).strip()
    if not c:
        return ""
    m = _NAME_RE.search(c)
    if not m:
        return ""
    return m.group(1).strip(" -—·|｜,，:：")


def _enrich_title(title, content):
    """把被上游截断的标题补全 —— 这是「明明搜到课程却显示成『马老师的』」的根因。

    上游 title 字段经常被按字节硬截断：
        '马老师的' / '慕课网-体系课-' / '慕课网-体系课-Java高级工程师('
    光看 title 根本认不出是什么课。而 content 的「名称：」字段是完整名。
    判定规则：title 归一化后是「名称」的前缀，且只少几个字 —— 那必然是截断。
    多出几十个字的不算（那种是标题里塞了整段描述，例如「IT培训教程合集【网易
    云课堂…23.8G】…」，用了反而更糟）。
    """
    t = _clean_title(title)
    cand = _name_from_content(content)
    if cand:
        a, b = _name_key(t), _name_key(cand)
        gap = len(b) - len(a)
        if b and b.startswith(a) and 0 < gap <= 25 and len(cand) > len(t):
            return cand
        if a and gap > 0 and gap <= 25 and _lcs_len(a, b) >= max(2, len(a) - 1):
            return cand
    # 没有「名称：」字段时，退回「文件列表首行是标题延续」的老办法
    c = (content or "").strip()
    if not c:
        return t
    first = re.split(r"[\n\r|]+", c)[0].strip()
    first = re.sub(r"^(file|dir|folder|文件|目录)\s*[:：]\s*", "", first, flags=re.I).strip()
    first = re.sub(r"^[\-—·\s]+", "", first).strip()
    if len(first) > len(t) + 3 and (not t or first.lower().startswith(t.lower())):
        return first[:90]
    return t


# 抽词组时的切分符。注意要切开空格，否则「马老师的 Java就业班」会被当成一个词组
_TOPIC_SPLIT_RE = re.compile(
    r"[|｜/／·・,，;；\-—_+*()（）\[\]【】<>《》\"'“”]+|\s+")
# 上游标题常带「095.」「3、」这类序号前缀，剥掉后「095.马老师的」才能还原成「马老师的」
_TOPIC_NUM_RE = re.compile(r"^\s*\d{1,4}\s*[.、)）\]】\-—_]\s*")
_TOPIC_JUNK = re.compile(r"^[的之了和与]+|(?:合集|全集|完结|无秘|最新|更新)$")


def derive_topics(items, tokens, limit=3):
    """从已搜到的标题里挖出「查询词之外的高频词组」，供二次搜索用。

    解决本项目最实际的场景：用户只知道**作者名**，而资源是按**课程名**索引的。
    搜「风间影月」只出 2 条，但这 2 条标题里写着
    「慕课网-体系课-Java高级工程师(风间影月)」—— 把「Java高级工程师」抠出来
    再搜一次，同一门课的其它分享能捞出 42 条。作者的其它课程同理。

    只在第一轮有高相关结果时才挖；词组要求足够长（归一化后 >=5 字），
    否则会挖出「就业班」「合集」这类没有区分度的泛词，搜了也是白搜。
    """
    if not items:
        return []
    toks = [t for t in (tokens or []) if len(t) >= 2]
    tok_keys = [_name_key(t) for t in toks]
    cnt = {}
    for it in items[:40]:
        if (it.get("rel") or 0) < 0.6:          # 只信高相关的标题
            continue
        frag = _clean_title(it.get("title") or "")
        for t in toks:                          # 先把查询词抠掉，剩下的是额外信息
            # 用分隔符顶替而不是空格：「马老师的Java高级工程师就业班」去掉中段的
            # 「Java高级工程师」后会粘成「马老师的就业班」这种无意义词组
            frag = re.sub(re.escape(t), "|", frag, flags=re.I)
        for p in _TOPIC_SPLIT_RE.split(frag):
            p = p.strip(" -—·|｜,，:：").strip()
            p = _TOPIC_NUM_RE.sub("", p)          # 剥掉「095.」这类序号前缀
            p = _TOPIC_JUNK.sub("", p).strip()
            p = p.strip(" -—·|｜,，:：")
            k = _name_key(p)
            if len(k) < 5:
                continue
            if not re.search(r"[\u4e00-\u9fff]{3,}|[A-Za-z]{3,}", p):
                continue                        # 纯数字/纯符号不要
            if any(k == tk or k in tk for tk in tok_keys):
                continue                        # 别把查询词又提一遍
            cnt[p] = cnt.get(p, 0) + 1
    ranked = sorted(cnt.items(), key=lambda kv: (-kv[1], -len(_name_key(kv[0]))))
    out = []
    for p, _ in ranked:
        kp = _name_key(p)
        if any(kp in _name_key(o) or _name_key(o) in kp for o in out):
            continue                            # 去掉互相包含的重复词组
        out.append(p)
        if len(out) >= limit:
            break
    return out


def score_item(item, query_list, cloud_bonus, tokens=None):
    title = (item.get("title") or "")
    hay = (title + " " + (item.get("content") or "")[:150]).lower()
    score = 0.0
    for q in query_list:
        ql = q.lower().strip()
        if not ql:
            continue
        if ql in hay:
            score += 55
            score += 25 * (len(ql) / max(len(title), 1))      # 短标题命中更精准
        else:
            score += 45 * (_lcs_len(ql, hay) / len(ql))
    if tokens:
        score += 30 * relevance(item, tokens)
    score += cloud_bonus.get(item["cloud"], 0)
    if item.get("pwd"):
        score += 4                       # 有提取码更可直接使用
    if item.get("images"):
        score += 1
    age = _age_days(item.get("dt"))
    if age is not None:
        score += max(0.0, 26.0 - age / 12.0)
    if len(title) > 160:
        score -= 6                       # 超长标题通常是乱码合集
    if item.get("size"):
        score += min(4.0, float(item["size"]) / (4 * 1024 ** 3))   # 体积大更像完整课程
    src = item.get("source") or ""
    if any(k in src for k in ("pansearch", "panta", "qupansou", "hunhepan",
                              "jikepan", "pan666", "xuexizhinan", "duoduo", "labi")):
        score += 3
    return round(score, 2)


# --------------------------------------------------------------------------- #
# 质量标签：把标题 / 文件列表里的结构化信息抽成徽章
# --------------------------------------------------------------------------- #
# 同一类别只取第一条命中的规则，避免「1080P 高清 超清」刷一排同义标签。
# 但「有没有源码」「有没有课件」是两件独立的事，所以拆成不同类别。
_TAG_RULES = [
    ("清晰度", re.compile(r"4K|2160P|蓝光原盘", re.I), "4K", "good"),
    ("清晰度", re.compile(r"1080P|FHD", re.I), "1080P", "good"),
    ("清晰度", re.compile(r"720P|高清|超清", re.I), "高清", "info"),
    ("状态", re.compile(r"完结|完整版|全集"), "完结", "good"),
    ("状态", re.compile(r"更新中|连载|持续更新"), "更新中", "warn"),
    ("源码", re.compile(r"源码|源代码|含代码"), "含源码", "good"),
    ("课件", re.compile(r"课件|讲义|教案|PPT", re.I), "含课件", "info"),
    ("资料", re.compile(r"面试题|题库|习题|笔记|(?:附|含|送|带|配套)\s*资料|资料包"),
     "含资料", "info"),
    ("文档", re.compile(r"PDF|电子书", re.I), "含文档", "info"),
    ("规模", re.compile(r"(\d{2,4})\s*[集讲期]"), None, "info"),
    ("便利", re.compile(r"无密|无秘|无提取码|免提取码|不要密码"), "无提取码", "good"),
]


def _extract_tags(item, limit=5):
    """把「这条值不值得点」的判断依据直接摆到列表上。

    原先「1080P 完结 含源码的完整课」和「只有三条的残缺搬运」在列表里长得一样，
    用户只能逐条点开试。这里用正则从标题 + 文件列表里抽出结构化徽章，
    纯本地零请求，抽出的是上游数据里本来就有的信息。
    """
    hay = (item.get("title") or "") + " " + (item.get("content") or "")[:400]
    found, seen = [], set()
    for cat, rx, text, kind in _TAG_RULES:
        if cat in seen:
            continue
        m = rx.search(hay)
        if not m:
            continue
        seen.add(cat)
        found.append({"t": text if text is not None else "%s集" % m.group(1),
                      "k": kind})
    # good 排前面：用户判断「能不能用」主要看清晰度 / 完结 / 有无源码
    found.sort(key=lambda t: 0 if t["k"] == "good" else
               (1 if t["k"] == "info" else 2))
    return found[:limit]


# --------------------------------------------------------------------------- #
# 跨网盘聚合：把「同一份资源在不同网盘的分享」并成一组
# --------------------------------------------------------------------------- #
@functools.lru_cache(maxsize=8192)
def _bigrams(s):
    """字符二元组集合。中文没有分词库，bigram 是最稳的免词典相似度底座。"""
    s = _name_key(s)
    if len(s) < 2:
        return frozenset([s]) if s else frozenset()
    return frozenset(s[i:i + 2] for i in range(len(s) - 1))


def _same_resource(a, b):
    """两个归一化标题是不是同一份资源。

    判据一：一个是另一个的连续子串 —— 大多数情况就是「课程名 + 【完结】
            【1080P】」这类后缀差异，直接算同一份。
    判据二：bigram Dice 系数 >= 0.75 —— 兜住「…(风间影月)」与「…(风间影月 )」
            这种中间插了字、不等于子串的情况。

    为什么不直接用编辑距离：「尚硅谷Redis」和「尚硅谷MySQL」只差 4 个字符，
    编辑距离会判成很像；而 bigram 能看出它们的交集只有「尚硅谷」，Dice 仅 0.29。
    """
    if not a or not b:
        return False
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > max(la, lb) * 0.6:
        return False                       # 长度差太多，先快速排除
    if a in b or b in a:
        return True
    ga, gb = _bigrams(a), _bigrams(b)
    if not ga or not gb:
        return False
    return (2.0 * len(ga & gb) / (len(ga) + len(gb))) >= 0.75


def cluster_items(items, keys_per_cluster=6):
    """把同一份资源跨网盘的多个分享聚成一组。

    搜到 42 条不等于有 42 份资源 —— 同一门课常被转存到百度 / 夸克 / 阿里，
    原本散在三个网盘分组里，用户得自己认出「这是同一个东西」。
    聚完从「42 条列表」变成「十几份资源、每份列出可用的网盘」。

    贪心聚类，复杂度 O(n²) 但 n 通常几十条；每个簇最多记 6 个 key，
    防止簇变大后比较次数失控。
    """
    clusters = []
    for it in items:
        key = _name_key(it.get("title") or "")
        if not key:
            key = "\x00%d" % len(clusters)          # 没标题的各自成组
        hit = None
        for c in clusters:
            if any(_same_resource(key, k) for k in c["keys"]):
                hit = c
                break
        if hit is None:
            hit = {"keys": [], "items": []}
            clusters.append(hit)
        hit["items"].append(it)
        if key not in hit["keys"] and len(hit["keys"]) < keys_per_cluster:
            hit["keys"].append(key)

    out = []
    for c in clusters:
        its = c["items"]
        best = its[0]                    # items 已按 score 降序，第一条最典型
        labels, colors = [], []
        for cl in CLOUD_ORDER:
            if any(i["cloud"] == cl for i in its):
                labels.append(CLOUDS[cl]["short"])
                colors.append(CLOUDS[cl]["color"])
        tag_map = {}
        for i in its:                    # 组级标签取成员并集，good 优先
            for t in (i.get("tags") or []):
                tag_map.setdefault(t["t"], t)
        tags = sorted(tag_map.values(),
                      key=lambda t: 0 if t["k"] == "good" else 1)[:5]
        out.append({
            "title": best.get("title") or "(无标题)",
            "items": its,
            "n": len(its),
            "cloud_labels": labels,
            "cloud_colors": colors,
            "tags": tags,
            "rel": best.get("rel"),
            "score": best.get("score") or 0,
        })
    out.sort(key=lambda c: (-c["score"], -c["n"]))
    return out


# --------------------------------------------------------------------------- #
# 缓存 / 历史（sqlite）
# --------------------------------------------------------------------------- #
class Store:
    def __init__(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._lock = threading.Lock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS cache("
                        "k TEXT PRIMARY KEY, ts REAL, payload TEXT)")
        self.db.execute("CREATE TABLE IF NOT EXISTS history("
                        "id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, main TEXT, "
                        "author TEXT, hits INTEGER, secs REAL)")
        self.db.commit()

    def get_cache(self, key, ttl):
        with self._lock:
            row = self.db.execute("SELECT ts,payload FROM cache WHERE k=?", (key,)).fetchone()
        if not row:
            return None
        ts, payload = row
        if ttl > 0 and time.time() - ts > ttl:
            return None
        try:
            return json.loads(payload)
        except Exception:
            return None

    def put_cache(self, key, value):
        with self._lock:
            self.db.execute("INSERT OR REPLACE INTO cache(k,ts,payload) VALUES(?,?,?)",
                            (key, time.time(), json.dumps(value, ensure_ascii=False)))
            self.db.commit()

    def merge_cache(self, key, items, cap=1500):
        """把新抓到的结果**并入**缓存（按 url 去重），而不是覆盖。

        上游每次返回的结果集都不一样：同一个关键词实测出现过 145 条和 3196 条
        两种响应，真命中分散在不同批次里。并集累积让「同一关键词多搜几次」
        越搜越全，而不是每次都随机抽中一批。
        """
        with self._lock:
            row = self.db.execute("SELECT payload FROM cache WHERE k=?", (key,)).fetchone()
            merged, seen = [], set()
            if row:
                try:
                    for it in json.loads(row[0]):
                        u = it.get("url") or ""
                        if u and u not in seen:
                            seen.add(u)
                            merged.append(it)
                except Exception:
                    pass
            for it in items:
                u = it.get("url") or ""
                if u and u not in seen:
                    seen.add(u)
                    merged.append(it)
            if len(merged) > cap:
                merged = merged[-cap:]        # 超量时丢最旧的
            self.db.execute("INSERT OR REPLACE INTO cache(k,ts,payload) VALUES(?,?,?)",
                            (key, time.time(), json.dumps(merged, ensure_ascii=False)))
            self.db.commit()
        return merged

    def clear_cache(self):
        with self._lock:
            self.db.execute("DELETE FROM cache")
            self.db.commit()

    def add_history(self, main, author, hits, secs):
        with self._lock:
            self.db.execute("INSERT INTO history(ts,main,author,hits,secs) VALUES(?,?,?,?,?)",
                            (time.time(), main, author, hits, secs))
            self.db.execute("DELETE FROM history WHERE id NOT IN "
                            "(SELECT id FROM history ORDER BY id DESC LIMIT 50)")
            self.db.commit()

    def history(self, limit=12):
        with self._lock:
            rows = self.db.execute(
                "SELECT main,author,hits,secs,ts FROM history ORDER BY id DESC LIMIT ?",
                (limit,)).fetchall()
        seen, out = set(), []
        for main, author, hits, secs, ts in rows:
            k = "%s|%s" % (main, author)
            if k in seen:
                continue
            seen.add(k)
            out.append({"main": main, "author": author, "hits": hits,
                        "secs": round(secs, 2),
                        "time": datetime.fromtimestamp(ts).strftime("%m-%d %H:%M")})
        return out


# --------------------------------------------------------------------------- #
# 搜索引擎
# --------------------------------------------------------------------------- #
class Engine:
    def __init__(self, cfg, store):
        self.cfg = cfg
        self.store = store
        self.last_source_status = {}
        self._cool = {}          # 源名 -> (冷却截止时间戳, 原因)

    # ---- 任务编排：主源跑全部查询，其余源只跑前 N 个查询；总量封顶 ----
    def _tasks(self, sources, queries, cap, extra_per_source=1):
        tasks = []
        for i, src in enumerate(sources):
            for q in (queries if i == 0 else queries[:extra_per_source]):
                tasks.append((src, q))
        return tasks[:cap]

    # ---- 并发执行：命中缓存直接用，未命中才发请求 ----
    def _fanout(self, tasks, use_cache, timeout, force=False):
        raw, status, pending = [], {}, []
        ttl = 0 if not use_cache else int(self.cfg.get("cache_ttl", 1800))
        for src, q in tasks:
            key = "%s|%s|%s" % (CACHE_NS, src["search_url"], q)
            cached = None if force else (self.store.get_cache(key, ttl) if use_cache else None)
            if cached is not None:
                raw.extend(cached)
                st = status.setdefault(src["name"], {"ok": True, "items": 0, "cached": True})
                st["items"] += len(cached)
            else:
                pending.append((src, q, key))
        if pending:
            workers = max(1, min(int(self.cfg.get("max_concurrency", 6)), len(pending)))
            # 单源可容忍 timeout 秒，但整体设一个更紧的上限，避免一个源挂起拖死整次搜索
            deadline = min(timeout, 30) + 5
            with cf.ThreadPoolExecutor(max_workers=workers) as ex:
                futs = {ex.submit(query_source, s, q, timeout): (s, q, k)
                        for s, q, k in pending}
                done = set()
                try:
                    for fut in cf.as_completed(futs, timeout=deadline):
                        src, q, key = futs[fut]
                        done.add(fut)
                        st = status.setdefault(src["name"],
                                               {"ok": True, "items": 0, "cached": False})
                        try:
                            items = fut.result()
                            # 入库前先按本条查询做一次宽松过滤：上游的 TG 频道
                            # 有时会涌出 3000+ 条只沾一个字的模糊匹配，不过滤
                            # 会把缓存撑爆，也会拖慢后续所有合并
                            items = [i for i in items if relevance(i, [q]) >= 0.25]
                            if use_cache:
                                items = self.store.merge_cache(key, items)   # 并集累积
                            raw.extend(items)
                            st["items"] += len(items)
                            st["ok"] = True
                            st.pop("error", None)
                        except Exception as e:
                            st["ok"] = False
                            st["error"] = str(e)[:160]
                except cf.TimeoutError:
                    pass
                for fut, (src, q, key) in futs.items():
                    if fut in done or fut.done():
                        continue
                    fut.cancel()
                    st = status.setdefault(src["name"], {"ok": True, "items": 0})
                    if st.get("items", 0) > 0:
                        # 已经拿到部分结果就不要标记成失败，否则界面会误导用户
                        st["ok"] = True
                        st["error"] = "部分查询超时（%ds）" % deadline
                    else:
                        st["ok"] = False
                        st["error"] = "超时（%ds 无响应）" % deadline
        return raw, status

    # ---- 归一化 -> 去重 -> 相关度过滤 -> 打分 -> 分组 ----
    def _finalize(self, raw, query_list, clouds, sort, limit, tokens=None):
        bonus = {}
        for idx, c in enumerate(self.cfg.get("cloud_priority", [])):
            bonus[c] = max(0, 18 - idx * 2)

        merged = {}
        for it in raw:
            it["pwd"] = extract_pwd(it)
            it["title"] = _enrich_title(_clean_title(it.get("title")), it.get("content"))
            k = dedupe_key(it)
            prev = merged.get(k)
            if prev is None:
                merged[k] = it
            else:
                if not prev.get("pwd") and it.get("pwd"):
                    prev["pwd"] = it["pwd"]
                prev["title"] = _pick_title(it.get("title"), prev.get("title"), tokens)
                if it.get("images") and not prev.get("images"):
                    prev["images"] = it["images"]
                if len(it.get("content") or "") > len(prev.get("content") or ""):
                    prev["content"] = it["content"]
                if it.get("size") and not prev.get("size"):
                    prev["size"] = it["size"]

        drop_below = float(self.cfg.get("drop_below", 0.34))
        items = []
        for k, it in merged.items():
            rel = relevance(it, tokens)
            if rel < drop_below:
                continue        # 纯字面巧合的模糊匹配（如搜作者名却返回无关剧集）
            it["id"] = hashlib.md5(k.encode("utf-8")).hexdigest()[:12]
            it["cloud_label"] = CLOUDS[it["cloud"]]["label"]
            it["rel"] = round(rel, 2)
            it["score"] = score_item(it, query_list, bonus, tokens)
            it["low"] = rel < 0.6
            it["tags"] = _extract_tags(it)
            age = _age_days(it.get("dt"))
            it["age_days"] = None if age is None else round(age, 1)
            it["dt_display"] = (it["dt"][:10] if it.get("dt") else "")
            items.append(it)

        relevant = sum(1 for i in items if not i["low"])

        if clouds:
            wanted = {c for c in clouds if c}
            if wanted:
                items = [i for i in items if i["cloud"] in wanted]

        if sort == "time":
            items.sort(key=lambda x: (x.get("age_days") is None, x.get("age_days") or 1e9))
        elif sort == "size":
            items.sort(key=lambda x: -len(x.get("title") or ""))
        else:
            items.sort(key=lambda x: (-x["score"], x.get("age_days") or 1e9))

        total = len(items)
        items = items[:limit]
        groups = []
        for c in CLOUD_ORDER:
            sub = [i for i in items if i["cloud"] == c]
            if sub:
                groups.append({"cloud": c, "label": CLOUDS[c]["label"],
                               "color": CLOUDS[c]["color"], "items": sub})
        groups.sort(key=lambda g: (-len(g["items"]), CLOUD_ORDER.index(g["cloud"])))
        clusters = cluster_items(items)
        return total, relevant, items, groups, clusters

    def search(self, main, author, deep=False, clouds=None, use_cache=True,
               sort="relevance", limit=400, refresh=False):
        t0 = time.time()
        phrases = build_queries(main, author, deep=deep)
        if not phrases:
            return {"ok": False, "error": "请输入课程名或作者名", "items": [],
                    "groups": [], "clusters": [], "stats": {}}

        enabled = [s for s in self.cfg.get("sources", []) if s.get("enabled")]
        if not enabled:
            return {"ok": False, "error": "没有启用任何数据源，请检查 config.json",
                    "items": [], "groups": [], "clusters": [], "stats": {}}

        # 刚失败的源先冷却一会儿再试：被限流（429）的源每次重试要等十几秒，
        # 不跳过会把每次搜索都拖慢。全部冷却时仍然放行，避免无源可用。
        now = time.time()
        sources, cooling = [], []
        for s in enabled:
            until, reason = self._cool.get(s["name"], (0.0, ""))
            if until > now:
                cooling.append((s, reason))
            else:
                sources.append(s)
        if not sources:                       # 全在冷却就别死守，放行全部
            sources = [s for s, _ in cooling]
            cooling = []
        if cooling:
            for s, reason in cooling:
                self.last_source_status[s["name"]] = {
                    "ok": False, "items": 0, "cached": False,
                    "error": "冷却中，本次跳过"}
        else:
            self.last_source_status = {}

        cap = int(self.cfg.get("max_requests", 12))
        timeout = int(self.cfg.get("request_timeout", 60))
        degrade_on = bool(self.cfg.get("auto_degrade", True))

        used = list(phrases)
        tokens = input_tokens(main, author)
        cache_only = True
        # refresh（界面上的「再挖一次」）不吃缓存，把新一批结果并进缓存，越挖越全
        raw, status = self._fanout(
            self._tasks(sources, phrases, cap), use_cache, timeout, force=bool(refresh))
        if refresh:
            cache_only = False
        for st in status.values():
            if not st.get("cached"):
                cache_only = False

        total, relevant, items, groups, clusters = self._finalize(
            raw, used, clouds, sort, limit, tokens)

        # 「相关」结果为 0 才降级，避免被模糊匹配源的噪声挡住
        degraded, token_list = False, []
        if relevant == 0 and degrade_on:
            token_list = [t for t in token_queries(main, author) if t not in used]
            if token_list:
                degraded = True
                raw2, st2 = self._fanout(
                    self._tasks(sources, token_list, cap, extra_per_source=3),
                    use_cache, timeout)
                for name, st in st2.items():
                    cur = status.setdefault(name, {"ok": True, "items": 0})
                    cur["items"] += st.get("items", 0)
                    cur["cached"] = bool(cur.get("cached")) and bool(st.get("cached"))
                    if st.get("error"):
                        cur["error"] = st["error"]
                        cur["ok"] = False
                raw.extend(raw2)
                used += token_list
                tokens = token_list or tokens     # 拆词后按拆分粒度判定相关度
                for st in st2.values():
                    if not st.get("cached"):
                        cache_only = False
                total, relevant, items, groups, clusters = self._finalize(
                    raw, used, clouds, sort, limit, tokens)

        # 记录失败源的冷却：下一次搜索先跳过它，别让重试拖慢整体。
        # 限流（429/403）是被对端记了账，短时间再试只会继续吃闭门羹，
        # 所以按错误类型分级冷却：限流 10 分钟，其它错误 2 分钟。
        now2 = time.time()
        for name, st in status.items():
            if not st.get("ok") and st.get("items", 0) == 0:
                err = st.get("error") or ""
                throttled = any(k in err for k in ("429", "403", "Too Many"))
                self._cool[name] = (now2 + (600.0 if throttled else 120.0), err)
        for s, reason in cooling:             # 冷却中的源并回状态，界面能看到
            status[s["name"]] = {"ok": False, "items": 0, "cached": False,
                                 "error": "冷却中，本次跳过"}

        self.last_source_status = status

        secs = round(time.time() - t0, 2)
        if total:
            self.store.add_history(main, author, total, secs)

        return {
            "ok": True,
            "queries": used,
            "items": items,
            "groups": groups,
            "clusters": clusters,
            "suggest": derive_topics(items, tokens),
            "stats": {
                "total": total,
                "shown": len(items),
                "raw": len(raw),
                "secs": secs,
                "queries": len(used),
                "degraded": degraded,
                "tokens": token_list,
                "sources": status,
                "cached": cache_only and bool(raw),
            },
        }


# --------------------------------------------------------------------------- #
# HTTP 服务
# --------------------------------------------------------------------------- #
class Handler(BaseHTTPRequestHandler):
    server_version = "PanRadar/" + APP_VERSION
    engine = None
    cfg = None
    store = None

    def log_message(self, fmt, *args):
        # 只记非正常响应，正常 200 不刷屏。没有这条，出错时完全无从查证。
        try:
            code = str(args[1]) if len(args) > 1 else ""
            if code not in ("200", "304"):
                log("HTTP %s" % (fmt % args))
        except Exception:
            pass

    # ---------- helpers ----------
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        # HEAD 只发头：Content-Length 仍要给真实长度（探测方会看这个数），
        # 但不写 body —— 写了会破坏连接复用，探测方可能因此判定响应异常。
        head_only = getattr(self, "_head_only", False)
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._emit_cors()
        self.end_headers()
        if head_only:
            return
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def _json(self, obj, code=200):
        # default=str：万一某个字段混进 set / datetime 之类不可序列化的对象，
        # 让它降级成字符串继续返回，而不是抛异常把整个响应炸成空 body
        # （前端拿到空 body 只会看到 "Unexpected end of JSON input"）。 
        try:
            body = json.dumps(obj, ensure_ascii=False, default=str)
        except Exception as e:
            log("响应序列化失败: %s" % e)
            body = json.dumps({"ok": False, "error": "响应序列化失败: %s" % e,
                               "items": [], "groups": [], "clusters": [], "stats": {}},
                              ensure_ascii=False)
            code = 500
        self._send(code, body)

    def _params(self):
        return {k: v[0] for k, v in
                urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).items()}

    # ---------- routes ----------
    def do_GET(self):
        # 保证任何异常都回一个 JSON body：异常冒泡出 BaseHTTPRequestHandler 会
        # 直接关掉连接，前端只收到空响应 —— 那正是 "Unexpected end of JSON input" 的来源。
        try:
            self._route_get()
        except (BrokenPipeError, ConnectionResetError):
            pass                       # 客户端自己断开，无需处理
        except Exception as e:
            log("GET %s 处理异常: %r" % (self.path, e))
            try:
                self._json({"ok": False, "error": "服务内部错误: %s" % e,
                            "items": [], "groups": [], "clusters": [], "stats": {}}, 500)
            except Exception:
                pass

    def do_HEAD(self):
        """可达性探测。**不支持 HEAD 会让服务被误判为不可用。**

        BaseHTTPRequestHandler 默认对 HEAD 回 501。而预览面板 / 监控 / `curl -I`
        常拿 HEAD 探活：拿到 501 就认为"服务没起来"，转而用内置静态服务渲染
        index.html —— 页面看着正常，但页面里所有 `/api/*` 都会 404
        （表现：报错「后端返回了空响应（HTTP 404）」）。必须自己实现。
        """
        self._head_only = True
        path = urllib.parse.urlparse(self.path).path
        try:
            if path == "/api/search":
                # 探测不该真触发一次搜索（要打 5 个上游、几十秒）
                return self._send(200, b"")
            self._route_get()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            log("HEAD %s 处理异常: %r" % (self.path, e))
            try:
                self._send(500, b"")
            except Exception:
                pass

    def _emit_cors(self):
        # 跨域支持：OSS 静态前端跨域调用 FC 的 /api/* 时，响应必须带 CORS 头，否则浏览器拦截。
        # 仅对 /api/ 路径开放，静态资源不带。需要更强约束时可改成固定域名白名单。
        try:
            if urllib.parse.urlparse(self.path).path.startswith("/api/"):
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
                self.send_header("Access-Control-Max-Age", "86400")
        except Exception:
            pass

    def do_OPTIONS(self):
        # 浏览器跨域预检（CORS preflight）。必须返回 204 + CORS 头，否则实际请求被拦。
        self.send_response(204)
        self._emit_cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _route_get(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._serve_file(os.path.join(WEB_DIR, "index.html"), "text/html; charset=utf-8")
        if path == "/api/search":
            return self._api_search()
        if path == "/api/meta":
            return self._json({
                "clouds": [{"key": k, "label": CLOUDS[k]["label"], "color": CLOUDS[k]["color"]}
                           for k in CLOUD_ORDER if k != "others"],
                "sources": [{"name": s["name"], "url": s["search_url"],
                             "enabled": bool(s.get("enabled"))}
                            for s in self.cfg.get("sources", [])],
                "version": APP_VERSION,
                "cloud_priority": self.cfg.get("cloud_priority", []),
            })
        if path == "/api/history":
            return self._json({"ok": True, "history": self.store.history()})
        if path == "/api/cache/clear":
            self.store.clear_cache()
            return self._json({"ok": True})
        if path.startswith("/static/"):
            name = os.path.basename(path)
            return self._serve_file(os.path.join(WEB_DIR, name), self._guess_type(name))
        return self._send(404, "not found", "text/plain; charset=utf-8")

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/export":
            length = int(self.headers.get("Content-Length") or 0)
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            except Exception:
                payload = {}
            return self._api_export(payload)
        return self._send(404, "not found", "text/plain; charset=utf-8")

    _CT = {
        ".html": "text/html; charset=utf-8",
        ".js":   "text/javascript; charset=utf-8",
        ".css":  "text/css; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".svg":  "image/svg+xml",
        ".png":  "image/png",
        ".jpg":  "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif":  "image/gif",
        ".ico":  "image/x-icon",
        ".txt":  "text/plain; charset=utf-8",
    }

    def _guess_type(self, name):
        ext = os.path.splitext(name)[1].lower()
        return self._CT.get(ext, "application/octet-stream")

    def _serve_file(self, full, ctype):
        if not os.path.isfile(full):
            return self._send(404, "file not found", "text/plain; charset=utf-8")
        with open(full, "rb") as f:
            data = f.read()
        self._send(200, data, ctype or "application/octet-stream")

    def _api_search(self):
        p = self._params()
        main = p.get("main", "")
        author = p.get("author", "")
        deep = p.get("deep") in ("1", "true", "yes")
        refresh = p.get("refresh") in ("1", "true", "yes")
        clouds = [c for c in (p.get("clouds") or "").split(",") if c]
        sort = p.get("sort") or "relevance"
        try:
            res = self.engine.search(main, author, deep=deep, clouds=clouds, sort=sort,
                                     refresh=refresh)
        except Exception as e:
            log("搜索异常: %s" % e)
            res = {"ok": False, "error": "搜索失败: %s" % e, "items": [],
                   "groups": [], "clusters": [], "stats": {}}
        self._json(res)

    def _api_export(self, payload):
        items = payload.get("items") or []
        fmt = (payload.get("fmt") or "md").lower()
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        if fmt == "csv":
            buf = io.StringIO()
            w = csv.writer(buf)
            w.writerow(["网盘", "标题", "链接", "提取码", "日期", "来源", "相关度"])
            for i in items:
                w.writerow([i.get("cloud_label", ""), i.get("title", ""), i.get("url", ""),
                            i.get("pwd", ""), i.get("dt_display", ""),
                            i.get("source", ""), i.get("score", "")])
            body, ctype, ext = buf.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8", "csv"
        else:
            lines = ["# 网盘资源搜索结果", "",
                     "- 生成时间：%s" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                     "- 命中条数：%d" % len(items), ""]
            cur = None
            for i in items:
                if i.get("cloud_label") != cur:
                    cur = i.get("cloud_label")
                    lines += ["", "## %s" % cur, ""]
                pwd = (" 提取码 `%s`" % i["pwd"]) if i.get("pwd") else ""
                lines.append("- **%s**%s  \n  %s  \n  <sub>%s · %s · 相关度 %s</sub>" % (
                    (i.get("title") or "(无标题)").replace("*", ""), pwd,
                    i.get("url", ""), i.get("dt_display") or "日期未知",
                    i.get("source") or "未知来源", i.get("score", "")))
            body, ctype, ext = ("\n".join(lines) + "\n").encode("utf-8"), "text/markdown; charset=utf-8", "md"
        self.send_response(200)
        self._emit_cors()
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Disposition",
                         'attachment; filename="panradar-%s.%s"' % (stamp, ext))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# 自测（命令行验证链路，不开浏览器）
# --------------------------------------------------------------------------- #
def selftest(cfg, store, args):
    eng = Engine(cfg, store)
    main = args.selftest if isinstance(args.selftest, str) else ""
    author = args.author or ""
    log("自测查询: main=%r author=%r deep=%s" % (main, author, args.deep))
    res = eng.search(main, author, deep=args.deep, use_cache=not args.no_cache)
    lines = []
    lines.append("ok=%s  error=%s" % (res.get("ok"), res.get("error")))
    lines.append("queries=%s" % res.get("queries"))
    lines.append("stats=%s" % json.dumps(res.get("stats", {}), ensure_ascii=False))
    for g in res.get("groups", []):
        lines.append("\n### %s (%d)" % (g["label"], len(g["items"])))
        for it in g["items"][:8]:
            lines.append("  [score=%s rel=%s] %s | pwd=%s | %s" % (
                it["score"], it.get("rel"), (it["title"] or "")[:70], it["pwd"] or "-",
                it["url"][:80]))
    out = os.path.join(DATA_DIR, "selftest.txt")
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    log("自测结果已写入 %s" % out)
    print("\n".join(lines))
    return 0 if res.get("ok") else 1


# --------------------------------------------------------------------------- #
def find_free_port(start, host="127.0.0.1"):
    for p in range(start, start + 40):
        with socket.socket() as s:
            try:
                s.bind((host, p))
                return p
            except OSError:
                continue
    return start


def main():
    # 输出被重定向到文件时 Python 默认块缓冲（8KB）：日志会一直卡在内存里。
    # 之前 data/_srv.log 长期 0 字节、服务端异常完全无从查证，就是因为它。
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(line_buffering=True)
        except Exception:
            pass

    ap = argparse.ArgumentParser(description="PanRadar 网盘资源雷达")
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--host", default=None,
                    help="bind host (default 127.0.0.1; use 0.0.0.0 behind CDN/SLB)")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--deep", action="store_true")
    ap.add_argument("--author", default="")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--selftest", nargs="?", const="英语", default=None)
    args = ap.parse_args()

    os.makedirs(DATA_DIR, exist_ok=True)
    cfg = load_config()
    store = Store(DB_PATH)

    if args.selftest is not None:
        return selftest(cfg, store, args)

    host = args.host or cfg.get("host", "127.0.0.1")
    port = args.port or int(cfg.get("port", 8931))
    port = find_free_port(port, host)

    Handler.cfg = cfg
    Handler.store = store
    Handler.engine = Engine(cfg, store)

    httpd = ThreadingHTTPServer((host, port), Handler)
    url = "http://%s:%d/" % (host, port)
    print("=" * 58)
    print("  PanRadar / 网盘资源雷达  v%s" % APP_VERSION)
    print("  地址: %s   (Ctrl+C 退出)" % url)
    print("  数据源: %s" % ", ".join(
        "%s%s" % (s["name"], "" if s.get("enabled") else "(停用)")
        for s in cfg.get("sources", [])))
    print("=" * 58)
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
