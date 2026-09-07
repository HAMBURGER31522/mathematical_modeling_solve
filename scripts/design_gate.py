# -*- coding: utf-8 -*-
"""建模详要完备性门禁（P-1）——下游能不能执行，取决于这份文件写没写到位。

为什么需要它：建模详要是整条链路最上游的产物。它写薄了，执行方拿不到细节，
只能自己重新推导——于是两方各建各的模型，说好的对抗性审查也无从谈起
（审查的对象应当是**已给出的思路**，不是自己另造一个）。
而「写薄了」肉眼极难判：标题都在、每节一句话，看起来齐全，实际不可执行。

判据：
  1. 至少有一个 `## 问题X` 小节——没有逐问展开就不算建模详要；
  2. 每个问题小节都要有全部十项 `### <小节名>`，缺一 FAIL；
  3. 每项标题下必须有实质内容（去掉空白与列表符号后 ≥ --min-chars，默认 15 字符），
     只有标题没有内容按缺项处理——这一条挡的正是「看起来齐全」。

用法：
    python scripts/design_gate.py 结果/建模详要.md --out 结果/gates/G-1-建模详要.md

退出码：0 = 逐问十项齐全且有实质内容；1 = 有缺项或空节；2 = 用法/文件错误。
纯标准库。
"""
import argparse
import os
import re
import sys

SECTIONS = (
    "题型判定",
    "形式化三要素",
    "主路线",
    "独立核验路线",
    "承重假设",
    "口径",
    "证书预告",
    "分辨率",
    "数据接口",
    "已知失败模式",
)

QUESTION = re.compile(r"^##\s+(问题\S*|Q\d+\S*)\s*$", re.M)
SUB = re.compile(r"^###\s+(.+?)\s*$", re.M)


def split_questions(text):
    """按 `## 问题X` 切分；返回 [(标题, 正文), ...]。"""
    hits = list(QUESTION.finditer(text))
    out = []
    for i, m in enumerate(hits):
        end = hits[i + 1].start() if i + 1 < len(hits) else len(text)
        out.append((m.group(1), text[m.end():end]))
    return out


def substance(block):
    """去掉标题、列表符号、表格线与空白后剩下的实义字符数。"""
    body = re.sub(r"^#{1,6}\s+.*$", "", block, flags=re.M)
    body = re.sub(r"^[\s>*\-+|]+$", "", body, flags=re.M)
    body = re.sub(r"[\s>*\-+|·。，、；：]", "", body)
    return len(body)


def audit(text, min_chars):
    problems, rows = [], []
    questions = split_questions(text)
    if not questions:
        problems.append("没有任何 `## 问题X` 小节——建模详要必须逐问展开，"
                        "总论不能替代逐问设计")
        return problems, rows

    for title, block in questions:
        subs = list(SUB.finditer(block))
        found = {}
        for j, m in enumerate(subs):
            end = subs[j + 1].start() if j + 1 < len(subs) else len(block)
            found[m.group(1).strip()] = block[m.end():end]

        for name in SECTIONS:
            match = next((k for k in found if name in k), None)
            if match is None:
                problems.append("%s 缺「%s」" % (title, name))
                rows.append((title, name, "缺项", 0))
                continue
            n = substance(found[match])
            if n < min_chars:
                problems.append("%s 的「%s」只有标题没有实质内容（%d 字符）"
                                "——看起来齐全就是这么来的" % (title, name, n))
                rows.append((title, name, "空节", n))
            else:
                rows.append((title, name, "OK", n))
    return problems, rows


def main():
    ap = argparse.ArgumentParser(description="建模详要完备性门禁")
    ap.add_argument("design", help="结果/建模详要.md")
    ap.add_argument("--out", default="结果/gates/G-1-建模详要.md")
    ap.add_argument("--min-chars", type=int, default=15,
                    help="每项的最小实义字符数，低于此按空节处理")
    a = ap.parse_args()

    if not os.path.isfile(a.design):
        print("找不到建模详要：%s" % a.design, file=sys.stderr)
        return 2
    text = open(a.design, encoding="utf-8", errors="replace").read()
    problems, rows = audit(text, a.min_chars)

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("# 建模详要完备性\n\n来源：`%s`　问题数 %d　缺项/空节 %d\n\n"
                 % (a.design, len({r[0] for r in rows}), len(problems)))
        if rows:
            fh.write("| 问题 | 小节 | 判定 | 实义字符 |\n|---|---|---|---|\n")
            for title, name, verdict, n in rows:
                fh.write("| %s | %s | %s | %d |\n" % (title, name, verdict, n))
        if problems:
            fh.write("\n## FAIL\n\n" + "\n".join("- " + p for p in problems) + "\n")
        else:
            fh.write("\n## PASS\n\n逐问十项齐全且均有实质内容。\n")

    for p in problems:
        print("FAIL  " + p)
    print("问题 %d 个，缺项/空节 %d → %s"
          % (len({r[0] for r in rows}), len(problems), a.out))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
