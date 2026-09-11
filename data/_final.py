# -*- coding: utf-8 -*-
"""最终验收：示例关键词能否搜到 + 页面可访问。"""
import json, os, time
import urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "http://127.0.0.1:8931"
OUT = []


def call(path, params=None, timeout=180):
    u = BASE + path
    if params:
        u += "?" + urllib.parse.urlencode(params, encoding="utf-8")
    with urllib.request.urlopen(u, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def page(path):
    with urllib.request.urlopen(BASE + path, timeout=20) as r:
        return r.status, len(r.read())


def report(kw, label):
    OUT.append("=" * 70)
    OUT.append("## %s   「%s」" % (label, kw))
    t0 = time.time()
    try:
        r = call("/api/search", {"main": kw})
    except Exception as e:
        OUT.append("  FAIL %s" % e)
        return
    st = r.get("stats", {})
    OUT.append("  ok=%s  命中 %s 条 / 展示 %s / 原始 %s / %.1fs"
               % (r.get("ok"), st.get("total"), st.get("shown"),
                  st.get("raw"), time.time() - t0))
    for name, v in (st.get("sources") or {}).items():
        OUT.append("    · %-22s %s %s条%s" % (
            name, "OK " if v.get("ok") else "ERR",
            v.get("items"), "  " + (v.get("error") or "") if v.get("error") else ""))
    if st.get("degraded"):
        OUT.append("    (自动降级分词: %s)" % " / ".join(st.get("tokens") or []))
    sug = r.get("suggest") or []
    OUT.append("  顺藤摸瓜建议: %s" % (" / ".join(sug) if sug else "（无）"))
    for it in (r.get("items") or [])[:10]:
        OUT.append("      [%s] 匹配%d%%%s %s" % (
            it["cloud_label"], round((it.get("rel") or 0) * 100),
            " (弱)" if it.get("low") else "", it.get("title") or ""))
        OUT.append("          %s%s" % (it["url"][:78],
                                       "  提取码 " + it["pwd"] if it.get("pwd") else ""))


def main():
    try:
        OUT.append("页面 / -> %s" % (page("/"),))
        OUT.append("meta  -> %s" % json.dumps(call("/api/meta", timeout=20).get("version")))
    except Exception as e:
        OUT.append("页面检查失败: %s" % e)

    report("风间影月", "作者名")
    report("Vibe Coding 一人团队项目开发实战", "课程名（用户原案例）")
    report("Java高级工程师", "课程名")
    report("一人团队项目开发实战", "课程名（不带英文前缀）")
    report("马老师 Java高级工程师", "作者 + 课程 组合")

    # 顺藤摸瓜的实际效果：拿「风间影月」给出的建议词再搜一次，看能否大幅增量
    OUT.append("=" * 70)
    OUT.append("## 顺藤摸瓜闭环验证（用户只给作者名的真实场景）")
    try:
        r1 = call("/api/search", {"main": "风间影月"})
        n1 = r1.get("stats", {}).get("total")
        sug = r1.get("suggest") or []
        OUT.append("  第 1 轮 搜「风间影月」-> %s 条；认出：%s" % (n1, sug or "无"))
        for topic in sug[:2]:
            r2 = call("/api/search", {"main": topic})
            st2 = r2.get("stats", {})
            OUT.append("  第 2 轮 搜「%s」-> %s 条（原始 %s）"
                       % (topic, st2.get("total"), st2.get("raw")))
            for it in (r2.get("items") or [])[:5]:
                OUT.append("      [%s] %s" % (it["cloud_label"], it.get("title") or ""))
                OUT.append("          %s%s" % (it["url"][:78],
                                               "  提取码 " + it["pwd"] if it.get("pwd") else ""))
    except Exception as e:
        OUT.append("  失败: %s" % e)

    with open(os.path.join(HERE, "final_check.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(OUT))


if __name__ == "__main__":
    main()
