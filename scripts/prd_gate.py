# -*- coding: utf-8 -*-
"""PRD 可执行规格门禁。

检查 PRD 的待定项、编号和完成标准命令，避免规格只能靠人工口头确认。
退出码：0=通过，1=规格不合格，2=用法或文件错误。
"""
from __future__ import annotations

import argparse
import os
import re
import sys


COMMAND = re.compile(r"`([^`\r\n]+)`")
HEADING = re.compile(r"^##\s+(.+?)\s*$", re.M)


def _section(text: str, title: str) -> str | None:
    """Return the body of an exact level-two Markdown section."""
    matches = list(HEADING.finditer(text))
    for index, match in enumerate(matches):
        if match.group(1).strip() != title:
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        return text[match.end():end]
    return None


def _table_rows(body: str) -> tuple[list[str], list[list[str]]]:
    lines = [line.strip() for line in body.splitlines() if line.strip().startswith("|")]
    if not lines:
        return [], []
    cells = lambda line: [part.strip() for part in line.strip().strip("|").split("|")]
    header = cells(lines[0])
    rows: list[list[str]] = []
    for line in lines[1:]:
        row = cells(line)
        if row and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in row):
            continue
        rows.append(row)
    return header, rows


def audit(text: str) -> list[str]:
    errors: list[str] = []
    pending = _section(text, "待定项")
    if pending is None:
        errors.append("缺少「## 待定项」小节")
    else:
        meaningful = [line.strip() for line in pending.splitlines()
                      if line.strip() and not re.fullmatch(r"[-*_`\s。．.]+", line.strip())]
        if meaningful and not all(re.fullmatch(r"(?:无|无。|暂无|暂无。)", line) for line in meaningful):
            errors.append("「待定项」仍有未清零条目")

    criteria = _section(text, "完成标准")
    if criteria is None:
        errors.append("缺少「## 完成标准」小节")
        return errors
    header, rows = _table_rows(criteria)
    if not header or not rows:
        errors.append("「完成标准」必须包含带编号和判定命令的 Markdown 表")
        return errors
    id_index = next((i for i, value in enumerate(header) if value in ("编号", "ID", "id")), None)
    command_index = next((i for i, value in enumerate(header)
                          if "判定命令" in value or "command" in value.casefold()), None)
    if id_index is None:
        errors.append("完成标准表缺少「编号」列")
    if command_index is None:
        errors.append("完成标准表缺少「判定命令」列")
    if id_index is None or command_index is None:
        return errors
    for number, row in enumerate(rows, 1):
        if len(row) <= max(id_index, command_index):
            errors.append(f"完成标准第 {number} 行列数不足")
            continue
        ident = row[id_index].strip()
        if not ident or re.fullmatch(r"[-–—]+", ident):
            errors.append(f"完成标准第 {number} 行缺少编号")
        command = row[command_index]
        match = COMMAND.search(command)
        if not match or not match.group(1).strip():
            errors.append(f"完成标准第 {number} 行缺少反引号包裹的可执行命令")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PRD 可执行规格门禁")
    parser.add_argument("prd", help="PRD Markdown 文件")
    parser.add_argument("--out", default="结果/gates/G-0-PRD.md")
    args = parser.parse_args(argv)
    if not os.path.isfile(args.prd):
        print(f"找不到 PRD：{args.prd}", file=sys.stderr)
        return 2
    try:
        text = open(args.prd, encoding="utf-8-sig").read()
    except OSError as exc:
        print(f"无法读取 PRD：{exc}", file=sys.stderr)
        return 2
    errors = audit(text)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="\n") as report:
        report.write("# PRD 规格门禁\n\n")
        report.write(f"来源：`{args.prd}`　FAIL {len(errors)}\n\n")
        if errors:
            report.write("## FAIL\n\n" + "\n".join(f"- {error}" for error in errors) + "\n")
        else:
            report.write("## PASS\n\n待定项已清零，完成标准均有编号和可执行命令。\n")
    for error in errors:
        print("FAIL  " + error)
    print(f"PRD gate:FAIL {len(errors)} → {args.out}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
