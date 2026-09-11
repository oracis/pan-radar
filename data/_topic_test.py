# -*- coding: utf-8 -*-
"""顺藤摸瓜（derive_topics）的边界用例 —— 场景全部来自真实搜索。"""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import panradar as P


def run(name, titles, tokens, want):
    items = [t if isinstance(t, dict) else {"title": t, "rel": 1.0} for t in titles]
    got = P.derive_topics(items, tokens)
    ok = got == want
    print("%s %-34s %r" % ("OK  " if ok else "FAIL", name, got))
    if not ok:
        print("        期望 %r" % want)
    return 0 if ok else 1


fail = 0
# 用户只知道作者名 → 从标题里挖出课程名（本项目最主要的场景）
fail += run("风间影月 -> 课程名",
            ["慕课网-体系课-Java高级工程师(风间影月 )"], ["风间影月"],
            ["Java高级工程师"])
fail += run("马老师 -> 课程名",
            ["马老师的Java高级工程师就业班"], ["马老师"],
            ["Java高级工程师就业班"])
# 反过来：已知课程名 → 挖出作者名，但「马老师的」只有 4 字，太短的泛词不提
fail += run("Java高级工程师 -> 无可用建议",
            ["马老师的Java高级工程师就业班"], ["Java高级工程师"],
            [])
# 高频优先：多门课同时出现时，出现次数多的排前面
fail += run("多结果按频次排",
            ["慕课网-体系课-Java高级工程师(风间影月 )",
             "慕课网-体系课-Java高级工程师(风间影月 )",
             "尚硅谷-SpringCloud微服务实战(风间影月)"], ["风间影月"],
            ["Java高级工程师", "SpringCloud微服务实战"])
# 泛词必须被拦住：「就业班」「合集」这种搜了也是白搜
fail += run("过滤泛词",
            ["某课程合集(张三)"], ["张三"],
            [])
# 低相关结果不参与挖掘（噪声标题里没有真信息）
fail += run("低相关不参与",
            [{"title": "擦边短剧：人间风月录", "rel": 0.1}], ["风间影月"],
            [])
# 无结果时返回空
fail += run("空输入", [], ["风间影月"], [])
# 真实脏数据：上游标题带序号前缀，剥掉序号后只剩 4 字的作者名，不提
fail += run("剥序号前缀",
            ["095.马老师的Java高级工程师就业班"], ["Java高级工程师"],
            [])
# 剥掉序号前缀后，「尚硅谷」只剩 3 字被滤掉，留下有检索价值的部分；
# 两条标题词频相同，取更具体的那个
fail += run("剥序号后仍有实质内容",
            ["003.尚硅谷Redis分布式缓存", "007.尚硅谷Redis分布式缓存实战"], ["Redis"],
            ["分布式缓存实战"])

print("=" * 60)
print("失败用例数:", fail)
