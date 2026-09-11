# -*- coding: utf-8 -*-
"""质量标签 + 跨网盘聚类的边界用例测试。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import panradar as P

OUT = []
FAIL = [0]


def chk(name, got, want):
    ok = got == want
    if not ok:
        FAIL[0] += 1
    OUT.append("%s %s\n     得到: %r\n     期望: %r" % (
        "OK  " if ok else "FAIL", name, got, want))


def tags(title, content=""):
    return [t["t"] for t in P._extract_tags({"title": title, "content": content})]


OUT.append("=== 一、质量标签 _extract_tags ===")

r = tags("马老师的Java高级工程师就业班【1080P 完结 含源码】128集")
chk("完整信息全抽出", set(r) >= {"1080P", "完结", "含源码", "128集"}, True)
chk("good 类型排最前", r[0] in ("1080P", "完结", "含源码"), True)

chk("4K 优先于 1080P", tags("某课程 4K 2160P 蓝光原盘"), ["4K"])
chk("同一类别不重复", tags("1080P 高清 超清 蓝光"), ["1080P"])
chk("更新中标记为 warn", tags("某某课程更新中"), ["更新中"])
chk("无提取码识别", tags("课程资料 无密分享"), ["无提取码"])
chk("「无秘」也识别（网盘圈写法）",
    sorted(tags("某某课程完结无秘")) == sorted(["完结", "无提取码"]), True)
chk("裸「资料」二字不误标", "含资料" not in tags("某某课程资料大全 无密"), True)
chk("配套资料算含资料", tags("课程 配套资料齐全"), ["含资料"])
chk("课件与源码是两个独立标签",
    set(tags("课程 含源码 附课件")) >= {"含源码", "含课件"}, True)
chk("面试题算含资料", tags("Java面试题库 大厂真题"), ["含资料"])
chk("纯标题无标签", tags("Java高级工程师就业班"), [])
chk("标签取自 content", tags("被截断的", "名称：某某课 1080P完结"), ["1080P", "完结"])
chk("最多 5 个", len(tags("a 4K 完结 源码 课件 题库 PDF 128集 无密")), 5)
chk("两位以下数字不算集数", tags("第1集 试看"), [])

OUT.append("")
OUT.append("=== 二、跨网盘聚合 _same_resource ===")

chk("同课后缀差异（子串）",
    P._same_resource(P._name_key("马老师的Java高级工程师就业班"),
                     P._name_key("马老师的Java高级工程师就业班【完整】")), True)
chk("短名是长名前缀",
    P._same_resource(P._name_key("Java高级工程师"),
                     P._name_key("Java高级工程师就业班")), True)
chk("作者后缀差异",
    P._same_resource(P._name_key("慕课网Java高级工程师(风间影月)"),
                     P._name_key("慕课网Java高级工程师(风间影月 )")), True)
chk("完全一致", P._same_resource(P._name_key("Redis实战"), P._name_key("Redis实战")), True)
chk("不同课程不能聚（尚硅谷 Redis vs MySQL）",
    P._same_resource(P._name_key("尚硅谷Redis分布式缓存"),
                     P._name_key("尚硅谷MySQL高级")), False)
chk("噪声标题不能聚（风间影月 vs 人间风月录）",
    P._same_resource(P._name_key("风间影月"), P._name_key("人间风月录")), False)
chk("空标题返回 False", P._same_resource("", "abc"), False)
chk("长度差过大快速排除",
    P._same_resource(P._name_key("Redis"), P._name_key("Redis实战全流程从入门到精通课程")), False)

OUT.append("")
OUT.append("=== 三、聚类分组 cluster_items ===")


def mk(title, cloud, score, pwd=None):
    it = {"title": title, "cloud": cloud, "score": score, "pwd": pwd,
          "content": "", "url": "https://x/" + title}
    it["tags"] = P._extract_tags(it)
    return it


items = [
    mk("马老师的Java高级工程师就业班", "baidu", 90, "rb2v"),
    mk("马老师的Java高级工程师就业班【完整版】", "quark", 80),
    mk("马老师的Java高级工程师就业班", "aliyun", 70),
    mk("尚硅谷Redis分布式缓存", "baidu", 60),
    mk("尚硅谷MySQL高级", "quark", 50),
]
cls = P.cluster_items(items)
chk("5 条聚成 3 组", len(cls), 3)
top = cls[0]
chk("最高分组是那门课", top["title"], "马老师的Java高级工程师就业班")
chk("该组含 3 个分享", top["n"], 3)
chk("组内列出 3 个网盘", sorted(top["cloud_labels"]),
    sorted(["百度", "夸克", "阿里"]))
chk("组内 items 数量一致", len(top["items"]), 3)
chk("组名取最高分那条的标题", top["score"], 90)
chk("尚硅谷两门课各自成组",
    sorted(c["title"] for c in cls[1:]), ["尚硅谷MySQL高级", "尚硅谷Redis分布式缓存"])

cls2 = P.cluster_items([mk("(无标题)", "baidu", 10), mk("", "quark", 9)])
chk("无标题不互相聚", len(cls2), 2)

cls3 = P.cluster_items([])
chk("空输入返回空", cls3, [])

OUT.append("")
OUT.append("=" * 46)
OUT.append("失败 %d 项" % FAIL[0])
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "_feat_test.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(OUT))
print("\n".join(OUT))
