#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E/V/A 证据矩阵的交付契约门禁。

该脚本只验证证据包的机器可读完整性：每个检查项必须有工件、命令、
实际退出码、数字、适用性和判定，并且工件路径必须在交付根目录内存在。
它不替代对数字、模型独立性或理论正确性的人工/代码审查。

用法：
  python scripts/eva_gate.py 结果/审查/P3-EVA-证据矩阵.md \
      --review 结果/审查/EVA-检查表.md --root . --out 结果/gates/EVA.md

退出码：0 = 两份矩阵均完整且所有适用项 PASS；1 = 缺项、伪空值、路径/退出码
不合法或存在 FAIL；2 = 命令行/输入错误。
"""
from __future__ import annotations

import argparse
import os
import re
import sys


REQUIRED = {
    "E1": ("E", "三路独立估计路径"),
    "E2": ("E", "外部理论量级"),
    "E3": ("E", "解析算例与暴力对照"),
    "E4": ("E", "误差传导"),
    "E5": ("E", "多种子临界扫描"),
    "V1": ("V", "有限尺寸/胞元形状"),
    "V2": ("V", "阈值灵敏度系数"),
    "V3": ("V", "全前沿价格灵敏度"),
    "A1": ("A", "上下界夹逼偏差方向"),
    "A2": ("A", "单位步长整数前沿"),
    "A3": ("A", "病态切换记录"),
    "A4": ("A", "细长胞元结构反推"),
}
HEADER = ("id", "dimension", "criterion", "artifact", "command", "exit_code",
          "numbers", "applicability", "verdict")
NA = {"n/a", "na", "不适用", "不适用（n/a）"}


def _cells(line: str):
    if "|" not in line:
        return []
    body = line.strip()
    if not body.startswith("|"):
        return []
    return [part.strip() for part in body.strip("|").split("|")]


def _separator(cells):
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", ""))
                                    for cell in cells)


def _read_table(path):
    errors = []
    try:
        with open(path, encoding="utf-8-sig") as f:
            lines = f.readlines()
    except OSError as exc:
        return {}, [f"无法读取 {path}: {exc}"]

    header_index = None
    header = None
    for i, line in enumerate(lines):
        cells = [c.lower() for c in _cells(line)]
        if all(name in cells for name in HEADER):
            header_index = i
            header = {name: cells.index(name) for name in HEADER}
            break
    if header is None:
        return {}, [f"{path} 缺 canonical 表头：{' | '.join(HEADER)}"]

    rows = {}
    for line_no, line in enumerate(lines[header_index + 1:], header_index + 2):
        cells = _cells(line)
        if not cells:
            if rows:
                break
            continue
        if _separator(cells):
            continue
        if len(cells) <= max(header.values()):
            errors.append(f"{path}:{line_no} 表格列数不足")
            continue
        row = {name: cells[index].strip() for name, index in header.items()}
        ident = row["id"]
        if not ident:
            continue
        if ident in rows:
            errors.append(f"{path}:{line_no} 重复 ID {ident}")
        rows[ident] = row
    return rows, errors


def _is_blank(value):
    return not value.strip() or value.strip().lower() in {"-", "none", "null"}


def _is_na(value):
    normalized = value.strip().lower()
    if normalized in NA:
        return True
    return bool(re.match(r"^(?:n/a|na|不适用)(?:\s*[:：;,(（-]|$)", normalized))


def _artifact_paths(value):
    return [part.strip().strip("`") for part in re.split(r";|<br\s*/?>", value)
            if part.strip()]


def _inside(root, path):
    root = os.path.abspath(root)
    candidate = os.path.abspath(os.path.join(root, path))
    try:
        return os.path.commonpath([root, candidate]) == root
    except ValueError:
        return False


def _check_matrix(path, root, label):
    rows, errors = _read_table(path)
    for ident, (dimension, criterion) in REQUIRED.items():
        row = rows.get(ident)
        if row is None:
            errors.append(f"{label} 缺少 {ident}：{dimension}/{criterion}")
            continue
        if row["dimension"] != dimension:
            errors.append(f"{label} {ident} dimension 应为 {dimension}，实际 {row['dimension']!r}")
        if criterion not in row["criterion"]:
            errors.append(f"{label} {ident} criterion 未包含 {criterion!r}")
        if _is_blank(row["command"]):
            errors.append(f"{label} {ident} command 为空")
        if not re.fullmatch(r"-?\d+", row["exit_code"].strip()):
            errors.append(f"{label} {ident} exit_code 必须是整数，实际 {row['exit_code']!r}")
        if _is_blank(row["applicability"]):
            errors.append(f"{label} {ident} applicability 为空")

        artifacts = _artifact_paths(row["artifact"])
        if not artifacts or any(_is_blank(artifact) for artifact in artifacts):
            errors.append(f"{label} {ident} artifact 为空")
        for artifact in artifacts:
            if os.path.isabs(artifact) or not _inside(root, artifact):
                errors.append(f"{label} {ident} artifact 必须是交付根内相对路径：{artifact!r}")
            elif not os.path.exists(os.path.join(root, artifact)):
                errors.append(f"{label} {ident} artifact 不存在：{artifact}")

        na = _is_na(row["applicability"]) or _is_na(row["verdict"])
        if na:
            if not _is_na(row["applicability"]) or not _is_na(row["verdict"]):
                errors.append(f"{label} {ident} N/A 必须同时写在 applicability 和 verdict")
            if not re.search(r"\d", row["applicability"] + row["numbers"]):
                errors.append(f"{label} {ident} N/A 缺定量理由/数字")
            continue

        if _is_blank(row["numbers"]) or not re.search(r"\d", row["numbers"]):
            errors.append(f"{label} {ident} numbers 缺数字")
        if row["verdict"].strip().upper() != "PASS":
            errors.append(f"{label} {ident} verdict 必须为 PASS 或有适用性 N/A，实际 {row['verdict']!r}")
    return errors, len(rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description="E/V/A 证据矩阵完整性门禁")
    ap.add_argument("matrix", help="P3-EVA-证据矩阵.md")
    ap.add_argument("--review", required=True, help="EVA-检查表.md")
    ap.add_argument("--root", default=".", help="交付根目录，默认当前目录")
    ap.add_argument("--out", help="可选的门禁报告路径")
    args = ap.parse_args(argv)

    root = os.path.abspath(args.root)
    all_errors = []
    details = []
    for label, path in (("P3", args.matrix), ("P4", args.review)):
        errors, count = _check_matrix(path, root, label)
        all_errors.extend(errors)
        details.append((label, path, count, errors))

    status = "PASS" if not all_errors else "FAIL"
    lines = ["# E/V/A 证据矩阵门禁", "", f"结论：**{status}**", ""]
    for label, path, count, errors in details:
        lines.append(f"- {label}: `{path}`，解析 {count} 行，错误 {len(errors)}")
    if all_errors:
        lines.extend(["", "## FAIL", ""])
        lines.extend(f"- {error}" for error in all_errors)
    else:
        lines.extend(["", "两份矩阵均具备 E1-E5、V1-V3、A1-A4 的工件、命令、退出码、数字、适用性和判定。"])

    if args.out:
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0 if not all_errors else 1


if __name__ == "__main__":
    sys.exit(main())
