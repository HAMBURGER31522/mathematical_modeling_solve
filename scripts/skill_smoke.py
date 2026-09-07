# -*- coding: utf-8 -*-
"""skill 自身的自检——防的是「遗忘型错误」，不是「理解型错误」。

设计依据：skill-based-architecture 的 `templates/skill/scripts/smoke-test.sh`
（1356 行 bash，9 类约 50 项）。**本脚本没有整体移植那份**：上游假定
`skills/<name>/` 布局、带 Cursor 注册入口与上游同步清单，与本仓（SKILL.md 在根、
无 Cursor 入口、单 skill）差异过大，硬移植会得到大量恒真检查。
这里只保留在本仓真正可判的项，阈值沿用上游：
description ≤25 行、SKILL.md 正文 ≤90 行、薄壳 ≤60 行、路由 ≤10 条、gotchas ≤400 行。

用法：python scripts/skill_smoke.py
退出码：0 = 全过；1 = 有 FAIL。WARN 不影响退出码。
纯标准库。
"""
import io
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
FAILS, WARNS = [], []


def read(rel):
    path = os.path.join(ROOT, rel)
    if not os.path.isfile(path):
        return None
    return io.open(path, encoding="utf-8", errors="replace").read()


def check(cond, msg):
    (FAILS if not cond else []).append(msg) if not cond else None


def warn(cond, msg):
    if not cond:
        WARNS.append(msg)


def split_frontmatter(text):
    """返回 (frontmatter 行数, 正文行数)。没有 frontmatter 时前者为 0。"""
    lines = text.split("\n")
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return i - 1, len(lines) - i - 1
    return 0, len(lines)


def main():
    global ROOT
    import argparse
    ap = argparse.ArgumentParser(description="skill 自检")
    ap.add_argument("--root", default=ROOT, help="被检 skill 根目录（默认为本脚本上级）")
    ROOT = os.path.abspath(ap.parse_args().root)
    del FAILS[:], WARNS[:]

    # ── 1. 结构：入口文件必须存在
    skill = read("SKILL.md")
    check(skill is not None, "SKILL.md 不存在")
    if skill is None:
        report()
        return 1
    routing = read("routing.yaml")
    check(routing is not None, "routing.yaml 不存在")

    # ── 2. 行数预算（阈值取自上游 smoke-test.sh）
    desc_lines, body_lines = split_frontmatter(skill)
    check(desc_lines <= 25, "SKILL.md frontmatter %d 行 > 25" % desc_lines)
    check(body_lines <= 90, "SKILL.md 正文 %d 行 > 90" % body_lines)
    for shell in ("CLAUDE.md", "CODEX.md"):
        text = read(shell)
        if text is None:
            WARNS.append("%s 缺失——该 harness 读不到本 skill" % shell)
            continue
        n = len(text.split("\n"))
        check(n <= 60, "%s %d 行 > 60（薄壳超长会导致协议碎片化）" % (shell, n))
    gotchas = read("references/gotchas.md")
    if gotchas is not None:
        n = len(gotchas.split("\n"))
        check(n <= 400, "gotchas.md %d 行 > 400" % n)
        heads = re.findall(r"^##\s+(.+)$", gotchas, re.M)
        check(len(heads) == len(set(heads)), "gotchas.md 有重复的 ## 标题：%s" %
              [h for h in heads if heads.count(h) > 1])

    # ── 3. 占位符残留
    for rel in ("SKILL.md", "routing.yaml", "CLAUDE.md", "CODEX.md"):
        text = read(rel)
        if text is None:
            continue
        check("{{" not in text, "%s 残留 {{...}} 占位符" % rel)
        check("<!-- FILL" not in text, "%s 残留 <!-- FILL --> 标记" % rel)

    # ── 4. description 质量：模型天然 undertrigger，触发短语必须够
    fm = skill.split("---")[1] if skill.startswith("---") else ""
    desc = re.sub(r"^\s*description\s*:\s*>?\s*", "", fm, flags=re.M | re.S)
    cjk = len(re.findall(r"[一-鿿]", desc))
    words = len(re.findall(r"[A-Za-z]+", desc))
    check(cjk >= 40 or words >= 20, "description 过短（中文字 %d / 英文词 %d）" % (cjk, words))
    quoted = re.findall(r"[「\"'“]([^」\"'”]{2,30})[」\"'”]", desc)
    check(len(quoted) >= 2, "description 引号触发短语少于 2 条，命中率会掉")
    warn(len(quoted) <= 12, "description 触发短语 %d 条，疑似关键词堆砌" % len(quoted))

    # ── 5. 路由完整性：每条 workflow 必须真实存在，且要有兜底
    if routing:
        wfs = re.findall(r"^\s*workflow:\s*(\S+)\s*$", routing, re.M)
        ids = re.findall(r"^\s*-\s*id:\s*(\S+)\s*$", routing, re.M)
        check(len(ids) <= 10, "路由 %d 条 > 10，超出后命中率下降" % len(ids))
        check("other" in ids, "routing.yaml 缺 other 兜底行——未列出的任务会乱跑")
        for wf in wfs:
            check(os.path.isfile(os.path.join(ROOT, wf)), "routing.yaml 指向的 %s 不存在" % wf)

    # ── 6. 本地引用完整性：正文提到的仓内路径必须存在
    corpus = []
    for dirpath, _dirnames, filenames in os.walk(ROOT):
        if ".git" in dirpath:
            continue
        for name in filenames:
            if name.endswith(".md"):
                rel = os.path.relpath(os.path.join(dirpath, name), ROOT).replace("\\", "/")
                corpus.append((rel, read(rel) or ""))
    for rel, text in corpus:
        for ref in set(re.findall(r"`((?:references|workflows|rules|scripts|assets)/[^`\s]+)`", text)):
            check(os.path.exists(os.path.join(ROOT, ref)), "%s 引用了不存在的 %s" % (rel, ref))

    # ── 7. 激活优于存储：坑点必须出现在任务路径上，不能只躺在 references
    check("gotchas" in skill.lower() or "Gotchas" in skill,
          "SKILL.md 没有 Known Gotchas 板块——坑点只存不激活等于没捕获")

    report()
    return 1 if FAILS else 0


def report():
    for msg in FAILS:
        print("FAIL  " + msg)
    for msg in WARNS:
        print("WARN  " + msg)
    print("\nskill 自检：FAIL %d，WARN %d" % (len(FAILS), len(WARNS)))


if __name__ == "__main__":
    sys.exit(main())
