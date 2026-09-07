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
_PLACEHOLDER = re.compile(r"^<[^<>]+>$")
REQUIRED_KEYS = (
    "赛事", "正文页数上限", "总页数下限", "图总数下限", "正文引用图下限",
    "摘要页数", "论文模板", "目标图样例目录", "总时限", "主计算机时上限", "本机核数",
)
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp", ".svg"}


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


def _is_unfilled(value: object) -> bool:
    return value == "" or (isinstance(value, str) and bool(_PLACEHOLDER.fullmatch(value.strip())))


def _is_readable_image(path: Path) -> bool:
    """Check a common image signature after opening the candidate for reading."""
    if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
        return False
    try:
        header = path.read_bytes()[:64]
    except OSError:
        return False
    suffix = path.suffix.lower()
    signatures = {
        ".png": header.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": header.startswith(b"\xff\xd8\xff"),
        ".jpeg": header.startswith(b"\xff\xd8\xff"),
        ".gif": header.startswith((b"GIF87a", b"GIF89a")),
        ".bmp": header.startswith(b"BM"),
        ".tif": header.startswith((b"II*\x00", b"MM\x00*")),
        ".tiff": header.startswith((b"II*\x00", b"MM\x00*")),
        ".webp": header.startswith(b"RIFF") and header[8:12] == b"WEBP",
        ".svg": b"<svg" in header.lower(),
    }
    return signatures[suffix]


def validate_opening_config(config: dict[str, Any]) -> None:
    """Reject unfilled template fields and an unusable figure-sample directory."""
    missing = [key for key in REQUIRED_KEYS if key not in config or _is_unfilled(config[key])]
    if missing:
        raise ValueError("请在 开题.md 填写 " + "、".join(missing))
    sample_dir = Path(str(config["目标图样例目录"])).expanduser()
    if not sample_dir.is_dir():
        raise ValueError(f"目标图样例目录不存在或不是目录：{sample_dir}")
    if not any(_is_readable_image(path) for path in sample_dir.iterdir()):
        raise ValueError(f"目标图样例目录没有可读图片文件：{sample_dir}")


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
    if key not in config or _is_unfilled(config[key]):
        raise KeyError(key)
    return config[key]


def main() -> int:
    try:
        config = load_all()
        validate_opening_config(config)
    except (OSError, ValueError, KeyError) as exc:
        print(f"FAIL：{exc}")
        return 1
    print(json.dumps(config, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
