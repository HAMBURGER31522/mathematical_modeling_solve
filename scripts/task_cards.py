#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate the nine required fields in ``结果/拆问卡.md``."""

from __future__ import annotations

import argparse
import hashlib
import json
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
META_KEY = "__meta__"


def _normalized_requirement(value: object) -> str:
    """Normalize line endings and whitespace without changing requirement text."""
    return " ".join(str(value or "").split())


def task_cards_hash(cards: list[dict[str, object]]) -> str:
    """Hash question labels and validation requirements deterministically."""
    payload = []
    for card in cards:
        fields = card.get("fields", {})
        requirements = fields.get("validation_requirements", "") if isinstance(fields, dict) else ""
        payload.append({
            "label": str(card.get("label", "")).strip(),
            "validation_requirements": _normalized_requirement(requirements),
        })
    payload.sort(key=lambda item: item["label"])
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
    # Do not stamp a ledger when the specification itself is incomplete.
    if errors:
        return errors
    try:
        ledger = json.loads(ledger_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return errors + [f"无法读取结果台账：{exc}"]
    if not isinstance(ledger, dict):
        return errors + ["结果台账顶层必须是 JSON 对象"]
    digest = task_cards_hash(cards)
    metadata = ledger.get(META_KEY)
    if not ledger:
        ledger[META_KEY] = {
            "task_cards_sha256": digest,
            "canonicalization": "sorted question label + normalized validation_requirements",
        }
        try:
            ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n",
                                   encoding="utf-8")
        except OSError as exc:
            errors.append(f"无法写入结果台账元数据：{exc}")
    elif not isinstance(metadata, dict) or not metadata.get("task_cards_sha256"):
        errors.append("结果台账缺少拆问卡内容哈希；这是旧格式，请先迁移并重新运行门禁")
    elif metadata.get("task_cards_sha256") != digest:
        errors.append("validation_requirements 内容哈希已变化，拆问卡规格失效；请重新冻结台账")
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
    print("PASS：所有问题均有九字段，且 validation_requirements 内容哈希与台账一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
