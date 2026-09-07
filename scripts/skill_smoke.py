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


def anchors_of(rel):
    """目标文件里所有 ## 标题的 GitHub 式锚点（小写、空格转连字符、去其余标点）。"""
    out = set()
    for heading in re.findall(r"^#{1,6}\s+(.+?)\s*$", read(rel) or "", re.M):
        slug = heading.lower().replace(" ", "-")
        out.add("".join(ch for ch in slug if ch.isalnum() or ch in "-_"))
    return out


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

    # ── 3. 占位符残留：指令目录整棵扫，不能只看根部几个文件
    # 上游的判据是 `grep -rn 'FILL:' skills/<name>/`，任何命中都是必填项没填完。
    # 排除 assets/（LaTeX 的 {{ }} 是合法语法）与 tests/（fixture 会故意造残留）。
    placeholder_files = ["SKILL.md", "routing.yaml", "CLAUDE.md", "CODEX.md"]
    for sub in ("rules", "workflows", "references"):
        base = os.path.join(ROOT, sub)
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in ("tests", "__pycache__")]
            for name in filenames:
                if name.endswith((".md", ".yaml")):
                    placeholder_files.append(
                        os.path.relpath(os.path.join(dirpath, name), ROOT).replace("\\", "/"))
    for rel in placeholder_files:
        text = read(rel)
        if text is None:
            continue
        for token in ("{{NAME}}", "{{SUMMARY}}", "<!-- FILL:"):
            check(token not in text, "%s 残留占位符 %s（必填项，不是可选项）" % (rel, token))

    # ── 3b. 薄壳的承重结构不能被悄悄删掉
    # 压缩后只剩薄壳，所以它的三块（XML 标签 / Auto-Triggers / Red Flags）与路由一致性
    # 必须被机器守住——否则删掉标签仍然「自检全绿」。
    route_wfs = set(re.findall(r"^\s*workflow:\s*(\S+)\s*$", routing or "", re.M))
    for shell in ("CLAUDE.md", "CODEX.md"):
        text = read(shell)
        if text is None:
            continue
        for tag in ("<always-applicable>", "</always-applicable>",
                    "<task-routing>", "</task-routing>"):
            check(text.count(tag) == 1,
                  "%s 的承重标签 %s 出现 %d 次（应恰好 1 次）" % (shell, tag, text.count(tag)))
        if "<always-applicable>" in text and "<task-routing>" in text:
            check(text.index("</always-applicable>") < text.index("<task-routing>"),
                  "%s 的 always-applicable 必须闭合在 task-routing 之前" % shell)
        check("## Auto-Triggers" in text, "%s 缺 Auto-Triggers 板块" % shell)
        check("Red Flags" in text, "%s 缺 Red Flags — STOP 板块" % shell)
        first = re.search(r"##\s*Auto-Triggers\s*\n\s*-\s*(.+)", text)
        check(bool(first) and "重走路由" in first.group(1),
              "%s 的第一条 Auto-Trigger 必须是「同会话新任务重走路由」" % shell)
        shell_wfs = set(re.findall(r"`(workflows/[^`]+\.md)`", text))
        check(shell_wfs == route_wfs,
              "%s 的 Quick Routing 与 routing.yaml 不一致：只在薄壳 %s；只在路由 %s"
              % (shell, sorted(shell_wfs - route_wfs), sorted(route_wfs - shell_wfs)))

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
    # .md 用反引号包路径；.py/.sh 的路径散在 docstring 与注释里，两种都要查——
    # 只查 .md 会漏掉脚本头注指向已删 reference 的情况（v3.3 迁移时真实发生过）。
    SKILL_DIRS = r"(?:references|workflows|rules|scripts|assets)"
    PAT_MD = re.compile("`(" + SKILL_DIRS + r"/[^`\s]+)`")
    PAT_SRC = re.compile(r"(?<![\w/])(" + SKILL_DIRS + r"/[\w./\u4e00-\u9fff-]+\.\w+)")
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames
                       if d not in (".git", "__pycache__", "fonts", "tests")]
        for name in filenames:
            ext = os.path.splitext(name)[1]
            if ext not in (".md", ".py", ".sh", ".yaml"):
                continue
            rel = os.path.relpath(os.path.join(dirpath, name), ROOT).replace("\\", "/")
            text = read(rel) or ""
            pat = PAT_MD if ext == ".md" else PAT_SRC
            for ref in set(pat.findall(text)):
                target, _, fragment = ref.partition("#")
                if not os.path.exists(os.path.join(ROOT, target)):
                    FAILS.append("%s 引用了不存在的 %s" % (rel, target))
                    continue
                # 悬空锚点和失效路径一样是断链：坑点指过去却落不到条目上，
                # Agent 走到那一步读不到东西，等于没激活。
                if fragment:
                    check(fragment in anchors_of(target),
                          "%s 引用了 %s 里不存在的锚点 #%s" % (rel, target, fragment))

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
