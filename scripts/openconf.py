#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read the user-owned opening configuration from ``开题.md``."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


CONFIG_PATH = Path(__file__).resolve().parent.parent / "开题.md"
_INTEGER = re.compile(r"[+-]?\d+")
_DECIMAL = re.compile(r"[+-]?(?:\d+\.\d*|\d*\.\d+)")


def _strip_comment(value: str) -> str:
    quote = None
    escaped = False
    kept: list[str] = []
    for char in value:
        if escaped:
            kept.append(char)
            escaped = False
            continue
        if char == "\\" and quote == '"':
            kept.append(char)
            escaped = True
            continue
        if char in {"'", '"'}:
            if quote is None:
                quote = char
            elif quote == char:
                quote = None
            kept.append(char)
            continue
        if char == "#" and quote is None:
            break
        kept.append(char)
    return "".join(kept).strip()


def _parse_value(value: str) -> Any:
    value = _strip_comment(value)
    if not value:
        return ""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    if _INTEGER.fullmatch(value):
        return int(value)
    if _DECIMAL.fullmatch(value):
        return float(value)
    return value


def load_all() -> dict[str, Any]:
    """Return all non-empty keys from the flat YAML mapping in ``开题.md``.

    ``开题.md`` 是给人读的：参数放在围栏代码块里，块外是说明文字。
    有围栏就只读第一个围栏块的内容；没有围栏就退回整篇按裸 ``key: value`` 读，
    兼容早期只有配置行、没有说明的写法。
    """
    text = CONFIG_PATH.read_text(encoding="utf-8-sig")
    fenced = re.search(r"^```[^\n]*\n(.*?)^```", text, re.S | re.M)
    body = fenced.group(1) if fenced else text
    offset = text[: fenced.start(1)].count("\n") if fenced else 0

    config: dict[str, Any] = {}
    for index, raw_line in enumerate(body.splitlines(), 1):
        line_number = index + offset
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise ValueError(f"开题.md 第 {line_number} 行不是 key: value")
        key, raw_value = line.split(":", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"开题.md 第 {line_number} 行缺少键名")
        if key in config:
            raise ValueError(f"开题.md 重复键: {key}")
        config[key] = _parse_value(raw_value)
    return config


def load(key: str) -> Any:
    """Load one required value without any fallback or default."""
    config = load_all()
    if key not in config or config[key] == "":
        raise KeyError(key)
    return config[key]


def main() -> int:
    print(json.dumps(load_all(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
