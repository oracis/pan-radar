# -*- coding: utf-8 -*-
"""标题补全规则的边界用例 —— 数据全部取自真实上游响应。"""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import panradar as P

# (title, content, 期望的最终标题)
CASES = [
    # ------- 必须补全：上游 title 被字节截断，content 的「名称：」是全名 -------
    ("马老师的",
     "名称：马老师的Java高级工程师 就业班 描述：本课程由资深Java专家马老师授课…",
     "马老师的Java高级工程师 就业班"),
    ("慕课网-体系课-",
     "名称：慕课网-体系课-Java高级工程师 (风间影月) 描述：该项目是一个全面的微服务…",
     "慕课网-体系课-Java高级工程师 (风间影月)"),
    ("慕课网-体系课-Java高级工程师(",
     "名称：慕课网-体系课-Java高级工程师(风间影月 ) 描述：该项目是一个全面的微服务…",
     "慕课网-体系课-Java高级工程师(风间影月 )"),
    ("🗄 慕课网-体系课-",
     "📜介绍：名称：慕课网-体系课-Java高级工程师(风间影月) 📁 大小：12G",
     "慕课网-体系课-Java高级工程师(风间影月)"),

    # ------- 必须保留：标题是描述性长句，不能用「名称」字段替换 -------
    ("IT培训教程合集",
     "名称：IT培训教程合集【网易云课堂.微专业.Java高级开发工程师】【23.8G】总体文件超过分享限制，"
     "下面是分包分享内容「阶段1：高性能编程专题」链接：https://www.aliyundrive.com/s/QuQyvYn47h1",
     "IT培训教程合集"),

    # ------- 必须不动：本来就完整 -------
    ("慕课网-Java架构师-十项全能40周对标阿里p8完结无秘",
     "名称：慕课网-Java架构师-十项全能40周对标阿里p8完结无秘描述：《慕课网-Java架构师…》是一套体系庞大",
     "慕课网-Java架构师-十项全能40周对标阿里p8完结无秘"),
    ("超级工程 (2012) 1080P 全5集", "名称：超级工程 (2012) 1080P 全5集描述：中央电视台纪录频道…",
     "超级工程 (2012) 1080P 全5集"),
    ("马老师的Java就业班（完结）", "无名称字段",
     "马老师的Java就业班（完结）"),

    # ------- 悬空括号：没有「名称」字段时也要把末尾的半个括号裁掉 -------
    ("慕课网-体系课-Java高级工程师(", "", "慕课网-体系课-Java高级工程师"),

    # ------- 噪声照旧 -------
    ("擦边短剧：人间风月录&浮世繁华（完整版）",
     "名称：擦边短剧：人间风月录&浮世繁华（完整版）描述：喜欢就存每日更新",
     "擦边短剧：人间风月录&浮世繁华（完整版）"),
]

fail = 0
for raw, cont, want in CASES:
    got = P._enrich_title(P._clean_title(raw), cont)
    ok = got == want
    fail += 0 if ok else 1
    print("%s  期望 %r" % ("OK  " if ok else "FAIL", want))
    if not ok:
        print("       实得 %r" % got)
        print("       raw=%r" % raw)

print("-" * 60)
print("相关度规则复查")
REL = [
    ("风间影月", "慕课网-体系课-Java高级工程师(风间影月 )", "名称：慕课网-体系课-Java高级工程师(风间影月 ) 描述：…", True),
    ("风间影月", "擦边短剧：人间风月录&浮世繁华（完整版）", "名称：擦边短剧：人间风月录…", False),
    ("风间影月", "兵自风中来 4K 杜比 60帧", "影视资源合集 更至第30集 兵自风中来 更新至30集", False),
    ("Java高级工程师", "马老师的Java高级工程师 就业班", "名称：马老师的Java高级工程师 就业班 描述：…", True),
    ("一人团队项目开发实战", "mksz989-Vibe Coding 一人团队项目开发实战", "", True),
    ("一人团队项目开发实战", "名侦探柯南 剧场版合集", "全部剧场版 1080P", False),
]
db = float(P.DEFAULT_CONFIG.get("drop_below", 0.34))
for q, t, c, want_keep in REL:
    it = {"title": t, "content": c}
    r = P.relevance(it, [q])
    keep = r >= db
    ok = keep == want_keep
    fail += 0 if ok else 1
    print("%s  rel=%.2f  %s  %r" % ("OK  " if ok else "FAIL", r,
                                    "保留" if keep else "丢弃", t[:40]))

print("=" * 60)
print("失败用例数:", fail)
