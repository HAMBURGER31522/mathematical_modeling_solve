#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""交付清单门禁：验证比赛论文 PDF 与支撑材料之间可观察的关系。

这不是论文真伪证明器。它检查声明、包边界和可复现入口是否存在，
并把科学有效性、真实 AI 披露、匿名性和完整复现留给明确的人工作业。

用法：
    python scripts/delivery_gate.py 交付/ \
      --appendix-source 论文/10.附录.tex \
      --out 结果/gates/G7-交付清单.json

退出码：0 = 结构通过；1 = 存在阻断项；2 = 被检目录或清单无法读取。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path


SCHEMA_VERSION = 1
HUMAN_AUDIT_REQUIRED = [
    "核对论文结论、数据来源和模型解释是否真实且有科学证据支撑。",
    "核对 AI 工具使用声明、AI工具使用详情.pdf 与实际交互记录是否一致。",
    "解包后按实际环境执行 reproduce.py，确认完整源码而非核心节选能够重现声明的结果。",
    "核对论文、附件文件名、PDF 元数据、代码注释、路径和截图不含队员身份信息。",
    "核对支撑材料中的数据许可、来源和脱敏边界；不得复制竞赛已提供的原始数据。",
]


def add_issue(items, layer, code, message):
    items.append({"layer": layer, "code": code, "message": message})


def safe_relative(value, field, blocking, layer):
    """Return a normalized package-relative path, or None after recording a block."""
    if not isinstance(value, str) or not value.strip():
        add_issue(blocking, layer, "PATH_REQUIRED", f"{field} 必须是非空相对路径")
        return None
    if value != value.strip() or "\\" in value:
        add_issue(blocking, layer, "PATH_FORMAT", f"{field} 必须使用无首尾空格的 / 相对路径")
        return None
    if value.startswith(("/", "~")) or re.match(r"^[A-Za-z]:", value):
        add_issue(blocking, layer, "PATH_OUTSIDE_PACKAGE", f"{field} 不得使用绝对路径：{value}")
        return None
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        add_issue(blocking, layer, "PATH_TRAVERSAL", f"{field} 不得包含空段、. 或 ..：{value}")
        return None
    return value


def is_within(path, parent):
    return path == parent or path.startswith(parent + "/")


def package_path(root, relative):
    return root.joinpath(*relative.split("/"))


def check_existing_path(root, relative, field, blocking, layer, want_directory=None):
    """Check existence and reject symlinks that escape the package root."""
    target = package_path(root, relative)
    try:
        target.resolve().relative_to(root.resolve())
    except ValueError:
        add_issue(blocking, layer, "SYMLINK_ESCAPE", f"{field} 解析到交付包外：{relative}")
        return None
    if not target.exists():
        add_issue(blocking, layer, "ARTIFACT_MISSING", f"{field} 不存在：{relative}")
        return None
    if want_directory is True and not target.is_dir():
        add_issue(blocking, layer, "DIRECTORY_REQUIRED", f"{field} 必须是目录：{relative}")
        return None
    if want_directory is False and not target.is_file():
        add_issue(blocking, layer, "FILE_REQUIRED", f"{field} 必须是文件：{relative}")
        return None
    return target


def read_manifest(path):
    try:
        with path.open(encoding="utf-8-sig") as stream:
            return json.load(stream), None
    except (OSError, ValueError) as exc:
        return None, str(exc)


def validate_appendix(path, labels, source_entrypoints, blocking, warnings):
    if not path:
        add_issue(
            warnings,
            "cross-artifact",
            "APPENDIX_NOT_CHECKED",
            "未提供 --appendix-source；未机械核对附录标签和支撑材料指路句。",
        )
        return
    if not path.is_file():
        add_issue(blocking, "cross-artifact", "APPENDIX_MISSING", f"附录源不存在：{path}")
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        add_issue(blocking, "cross-artifact", "APPENDIX_UNREADABLE", f"附录源无法读取：{exc}")
        return

    for label in labels:
        if f"\\label{{{label}}}" not in text:
            add_issue(
                blocking,
                "cross-artifact",
                "APPENDIX_LABEL_MISSING",
                f"附录源缺少 manifest 声明的标签：{label}",
            )
    for entrypoint in source_entrypoints:
        if entrypoint not in text:
            add_issue(
                blocking,
                "cross-artifact",
                "SOURCE_ENTRYPOINT_UNREFERENCED",
                f"附录没有指向完整源码入口：{entrypoint}",
            )


def validate(root, manifest, appendix_source=None):
    blocking, warnings = [], []
    layer = "declared-constraints"

    if not isinstance(manifest, dict):
        add_issue(blocking, layer, "MANIFEST_OBJECT", "delivery-manifest.json 顶层必须是对象")
        return blocking, warnings

    if manifest.get("schema_version") != SCHEMA_VERSION:
        add_issue(
            blocking,
            layer,
            "SCHEMA_VERSION",
            f"schema_version 必须为 {SCHEMA_VERSION}",
        )

    paper_pdf = safe_relative(manifest.get("paper_pdf"), "paper_pdf", blocking, layer)
    support_root = safe_relative(manifest.get("support_root"), "support_root", blocking, layer)
    if paper_pdf and not paper_pdf.lower().endswith(".pdf"):
        add_issue(blocking, layer, "PAPER_NOT_PDF", "paper_pdf 必须指向 PDF 文件")
    if paper_pdf:
        check_existing_path(root, paper_pdf, "paper_pdf", blocking, "package-boundary", want_directory=False)
    if support_root:
        check_existing_path(root, support_root, "support_root", blocking, "package-boundary", want_directory=True)

    if (root / "tmp").exists():
        add_issue(
            blocking,
            "package-boundary",
            "TEMPORARY_ARTIFACT",
            "交付包内不得包含 tmp/；临时编译和渲染产物必须留在交付边界外。",
        )

    ai_use = manifest.get("ai_use")
    if not isinstance(ai_use, dict) or not isinstance(ai_use.get("used"), bool):
        add_issue(blocking, layer, "AI_USE_REQUIRED", "ai_use.used 必须是布尔值")
        ai_used = None
    else:
        ai_used = ai_use["used"]

    items = manifest.get("support_items")
    if not isinstance(items, list) or not items:
        add_issue(blocking, layer, "SUPPORT_ITEMS_REQUIRED", "support_items 必须是非空数组")
        items = []

    source_entrypoints = []
    source_item_seen = False
    ai_item_paths = []
    for number, item in enumerate(items, 1):
        item_layer = "package-boundary"
        if not isinstance(item, dict):
            add_issue(blocking, item_layer, "SUPPORT_ITEM_OBJECT", f"support_items[{number}] 必须是对象")
            continue
        kind = item.get("kind")
        if not isinstance(kind, str) or not kind.strip():
            add_issue(blocking, layer, "SUPPORT_ITEM_KIND", f"support_items[{number}].kind 必须非空")
            continue
        rel = safe_relative(item.get("path"), f"support_items[{number}].path", blocking, item_layer)
        paper_location = item.get("paper_location")
        if kind == "ai_tool_use_details":
            if paper_location not in (None, ""):
                add_issue(
                    blocking,
                    "cross-artifact",
                    "AI_DETAILS_PAPER_LOCATION_FORBIDDEN",
                    f"support_items[{number}] 的 AI 详情是独立支撑材料，不得声明论文或附录位置。",
                )
        elif not isinstance(paper_location, str) or not paper_location.strip():
            add_issue(
                blocking,
                "cross-artifact",
                "PAPER_LOCATION_REQUIRED",
                f"support_items[{number}] 必须说明它在论文/附录中的位置",
            )
        if rel and support_root and not is_within(rel, support_root):
            add_issue(
                blocking,
                item_layer,
                "SUPPORT_PATH_OUTSIDE_ROOT",
                f"支撑材料条目必须位于 {support_root}/ 下：{rel}",
            )
        if rel:
            target = check_existing_path(root, rel, f"support_items[{number}].path", blocking, item_layer)
        else:
            target = None

        if kind == "contest_raw_data":
            add_issue(
                blocking,
                layer,
                "CONTEST_RAW_DATA_INCLUDED",
                "竞赛已提供的原始数据不应作为支撑材料重复提交。",
            )
        if kind == "data" and item.get("origin") != "self_obtained":
            add_issue(
                blocking,
                layer,
                "DATA_ORIGIN_REQUIRED",
                f"support_items[{number}] 的数据必须明确标为 self_obtained。",
            )

        if kind == "ai_tool_use_details" and rel:
            ai_item_paths.append(rel)

        if kind != "source_code":
            continue
        source_item_seen = True
        if item.get("coverage") != "complete_runnable_source":
            add_issue(
                blocking,
                layer,
                "SOURCE_COVERAGE_REQUIRED",
                "source_code 条目必须声明 coverage=complete_runnable_source。",
            )
        if target is not None and not target.is_dir():
            add_issue(
                blocking,
                item_layer,
                "SOURCE_DIRECTORY_REQUIRED",
                "完整源码条目必须是目录，不能只声明核心代码节选。",
            )
        entrypoints = item.get("entrypoints")
        if not isinstance(entrypoints, list) or not entrypoints:
            add_issue(
                blocking,
                layer,
                "SOURCE_ENTRYPOINT_REQUIRED",
                "source_code 条目必须给出至少一个可运行入口。",
            )
            continue
        for entry_number, entrypoint in enumerate(entrypoints, 1):
            entry = safe_relative(
                entrypoint,
                f"support_items[{number}].entrypoints[{entry_number}]",
                blocking,
                item_layer,
            )
            if not entry:
                continue
            if rel and not is_within(entry, rel):
                add_issue(
                    blocking,
                    item_layer,
                    "SOURCE_ENTRYPOINT_OUTSIDE_SOURCE",
                    f"源码入口必须位于声明的 source_code 目录内：{entry}",
                )
            check_existing_path(root, entry, f"源码入口 {entry_number}", blocking, item_layer, want_directory=False)
            source_entrypoints.append(entry)

    if not source_item_seen:
        add_issue(
            blocking,
            layer,
            "COMPLETE_SOURCE_REQUIRED",
            "支撑材料必须声明一个完整可运行源码目录；附录核心代码不能替代它。",
        )

    reproduction = manifest.get("reproduction")
    if not isinstance(reproduction, dict):
        add_issue(blocking, layer, "REPRODUCTION_REQUIRED", "reproduction 必须是对象")
    else:
        entrypoint = safe_relative(reproduction.get("entrypoint"), "reproduction.entrypoint", blocking, layer)
        if entrypoint:
            check_existing_path(root, entrypoint, "reproduction.entrypoint", blocking, "package-boundary", False)
        command = reproduction.get("command")
        if not isinstance(command, str) or not command.strip():
            add_issue(
                blocking,
                layer,
                "REPRODUCTION_COMMAND_REQUIRED",
                "reproduction.command 必须记录实际可执行的复现命令；门禁不会替你运行它。",
            )

    ai_details = None
    if ai_used is True:
        ai_details = safe_relative(ai_use.get("details_pdf"), "ai_use.details_pdf", blocking, layer)
        if ai_details:
            if not ai_details.lower().endswith(".pdf"):
                add_issue(blocking, layer, "AI_DETAILS_NOT_PDF", "AI 详情必须是 PDF 文件")
            if support_root and not is_within(ai_details, support_root):
                add_issue(
                    blocking,
                    "package-boundary",
                    "AI_DETAILS_OUTSIDE_SUPPORT",
                    f"AI 详情 PDF 必须放在 {support_root}/ 下。",
                )
            check_existing_path(root, ai_details, "ai_use.details_pdf", blocking, "package-boundary", False)
            if ai_details not in ai_item_paths:
                add_issue(
                    blocking,
                    "cross-artifact",
                    "AI_DETAILS_NOT_IN_INVENTORY",
                    "AI 详情 PDF 必须作为 ai_tool_use_details 出现在 support_items 中。",
                )
    elif ai_used is False:
        if ai_use.get("details_pdf") not in (None, ""):
            add_issue(
                blocking,
                layer,
                "AI_DETAILS_WHEN_UNUSED",
                "ai_use.used=false 时不得声明或提交 AI工具使用详情.pdf。",
            )
        if ai_item_paths:
            add_issue(
                blocking,
                layer,
                "AI_DETAIL_ITEM_WHEN_UNUSED",
                "未使用 AI 时 support_items 不得包含 ai_tool_use_details。",
            )
        if support_root:
            conventional_detail = package_path(root, support_root) / "AI工具使用详情.pdf"
            if conventional_detail.exists():
                add_issue(
                    blocking,
                    "package-boundary",
                    "AI_DETAIL_FILE_WHEN_UNUSED",
                    "未使用 AI 时支撑材料中不得保留 AI工具使用详情.pdf。",
                )

    labels = manifest.get("appendix_labels")
    if not isinstance(labels, list) or not labels:
        add_issue(
            blocking,
            "cross-artifact",
            "APPENDIX_LABELS_REQUIRED",
            "appendix_labels 必须列出附录中用于支撑材料、核心代码和复现说明的标签。",
        )
        labels = []
    else:
        invalid_labels = [label for label in labels if not isinstance(label, str) or not label.strip()]
        if invalid_labels:
            add_issue(
                blocking,
                "cross-artifact",
                "APPENDIX_LABEL_FORMAT",
                "appendix_labels 只能包含非空标签名。",
            )
        labels = [label for label in labels if isinstance(label, str) and label.strip()]

    validate_appendix(
        appendix_source,
        labels,
        source_entrypoints,
        blocking,
        warnings,
    )
    return blocking, warnings


def main(argv=None):
    parser = argparse.ArgumentParser(description="比赛交付清单门禁")
    parser.add_argument("root", help="交付包根目录")
    parser.add_argument(
        "--manifest",
        default="delivery-manifest.json",
        help="相对交付根目录的清单路径（默认 delivery-manifest.json）",
    )
    parser.add_argument(
        "--appendix-source",
        default=None,
        help="可选的附录 TeX 源；提供后核验标签、完整源码入口和 AI 详情指路。",
    )
    parser.add_argument(
        "--out",
        default="结果/gates/G7-交付清单.json",
        help="结构化检查报告路径（默认写在工作区结果目录，非交付包内）。",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"交付目录不存在：{root}", file=sys.stderr)
        return 2

    manifest_rel = safe_relative(args.manifest, "--manifest", [], "declared-constraints")
    if not manifest_rel:
        print("--manifest 必须是交付包内的相对路径", file=sys.stderr)
        return 2
    manifest_path = package_path(root, manifest_rel)
    manifest, error = read_manifest(manifest_path)
    if error:
        print(f"清单无法读取：{manifest_path}：{error}", file=sys.stderr)
        return 2

    appendix_source = Path(args.appendix_source) if args.appendix_source else None
    blocking, warnings = validate(root, manifest, appendix_source)
    report = {
        "schema_version": SCHEMA_VERSION,
        "root": str(root),
        "manifest": str(manifest_path),
        "n_blocking": len(blocking),
        "n_warnings": len(warnings),
        "blocking": blocking,
        "warnings": warnings,
        "human_audit_required": HUMAN_AUDIT_REQUIRED,
        "verdict": "FAIL" if blocking else "PASS",
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")

    for issue in blocking[:20]:
        print(f"  [阻断][{issue['layer']}] {issue['code']}：{issue['message']}")
    for issue in warnings[:10]:
        print(f"  [提示][{issue['layer']}] {issue['code']}：{issue['message']}")
    print(f"交付清单门禁：阻断 {len(blocking)}，提示 {len(warnings)} → {out}")
    print("人工作业仍必需：科学性、真实 AI 披露、完整复现、匿名性与数据来源。")
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
