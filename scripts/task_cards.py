#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate the nine required fields in ``结果/拆问卡.md``."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


REQUIRED_FIELDS = (
    "objective",
    "input_data",
    "decision_variables",
    "constraints",
    "expected_outputs",
    "dependencies",
    "risks",
    "validation_requirements",
    "data_evidence",
)
QUESTION_HEADING = re.compile(
    r"^\s{0,3}#{1,6}\s+(?:问题|小问|question|ques|q)\s*[:：#-]?\s*([^\s#]*)",
    re.IGNORECASE,
)
FIELD_LINE = re.compile(
    r"^\s*(?:[-*+]\s*)?\|?\s*(?:\*\*)?`?("
    + "|".join(REQUIRED_FIELDS)
    + r")`?(?:\*\*)?\s*(?::|：|\|)\s*(.*?)\s*\|?\s*$",
    re.IGNORECASE,
)


def parse_cards(path: Path) -> list[dict[str, object]]:
    cards: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        heading = QUESTION_HEADING.match(raw_line)
        if heading:
            if current is not None:
                cards.append(current)
            label = heading.group(1).strip() or str(len(cards) + 1)
            current = {"label": label, "fields": {}, "last_field": None}
            continue
        if current is None:
            continue
        field = FIELD_LINE.match(raw_line)
        if field:
            name = field.group(1).casefold()
            value = field.group(2).strip()
            fields = current["fields"]
            assert isinstance(fields, dict)
            fields[name] = value
            current["last_field"] = name
            continue
        last_field = current["last_field"]
        text = raw_line.strip()
        if text and isinstance(last_field, str):
            fields = current["fields"]
            assert isinstance(fields, dict)
            fields[last_field] = f"{fields[last_field]}\n{text}".strip()
    if current is not None:
        cards.append(current)
    return cards


def validate(cards_path: Path, ledger_path: Path) -> list[str]:
    errors: list[str] = []
    if not cards_path.is_file():
        return [f"缺少拆问卡：{cards_path}"]
    if not ledger_path.is_file():
        return [f"缺少结果台账：{ledger_path}"]
    try:
        cards = parse_cards(cards_path)
    except (OSError, UnicodeError) as exc:
        return [f"无法读取拆问卡：{exc}"]
    if not cards:
        errors.append("拆问卡中没有任何问题标题")
    for card in cards:
        label = str(card["label"])
        fields = card["fields"]
        assert isinstance(fields, dict)
        missing = [field for field in REQUIRED_FIELDS if not str(fields.get(field, "")).strip()]
        if missing:
            errors.append(f"问题 {label} 缺少字段：{', '.join(missing)}")
    if cards_path.stat().st_mtime >= ledger_path.stat().st_mtime:
        errors.append(
            "拆问卡中的 validation_requirements 必须在 results_ledger.json 首次写入前落盘（拆问卡 mtime 必须早于 ledger mtime）"
        )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="拆问卡九字段与预先验证要求门禁")
    parser.add_argument("--cards", default="结果/拆问卡.md")
    parser.add_argument("--ledger", default="结果/results_ledger.json")
    args = parser.parse_args(argv)
    errors = validate(Path(args.cards), Path(args.ledger))
    if errors:
        print("FAIL")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("PASS：所有问题均有九字段，且验证要求早于 results_ledger.json 落盘")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
