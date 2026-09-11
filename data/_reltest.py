# -*- coding: utf-8 -*-
"""验证相关度判定规则的区分力。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import panradar as P

CASES = [
    ("风间影月", "慕课网-Java高级工程师（风间影月）"),
    ("风间影月", "擦边短剧：人间风月录&浮世繁华"),
    ("风间影月", "名侦探柯南：通向天国的倒计时 (2001) 蓝光原盘REMUX"),
    ("Java高级工程师", "IT培训教程合集【网易云课堂.微专业.Java高级开发工程师】"),
    ("Java高级工程师", "马老师的Java高级工程师就业班"),
    ("Vibe Coding 一人团队项目开发实战", "Vibe Coding实战:一人团队搞定多端项目全流程"),
    ("Vibe Coding 一人团队项目开发实战", "一饭封神 第二季 更至08.13期"),
    ("Vibe Coding 一人团队项目开发实战", "一人团队项目开发实战"),
    ("Java 高级工程师", "极客时间-深入剖析 Java 新特性"),
    ("考研英语", "2024考研数学 汤家凤"),
]

lines = []
for main, title in CASES:
    toks = P.input_tokens(main, "")
    r = P.relevance({"title": title, "content": ""}, toks)
    keep = "KEEP" if r >= 0.34 else "DROP"
    lines.append("%s  rel=%.2f  tokens=%s\n      %s | %s" % (keep, r, toks, main, title))

open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_rel_out.txt"),
     "w", encoding="utf-8").write("\n".join(lines))
