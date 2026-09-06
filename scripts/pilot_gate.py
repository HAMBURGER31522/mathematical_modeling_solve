#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate pilot results against their current-round protocol."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


class PilotValidationError(ValueError):
    """Raised when a pilot result does not meet the required three checks."""


def _candidate_names(question_protocol: object) -> set[str]:
    if not isinstance(question_protocol, dict):
        return set()
    raw_candidates = question_protocol.get("candidates")
    if not isinstance(raw_candidates, list):
        return set()
    names = set()
    for candidate in raw_candidates:
        name = candidate.get("name") if isinstance(candidate, dict) else candidate
        if isinstance(name, str) and name.strip():
            names.add(name.strip().casefold())
    return names


def _canonical_split(candidate: dict[str, Any]) -> str:
    if "data_split" not in candidate:
        raise PilotValidationError("候选缺少 data_split")
    return json.dumps(
        candidate["data_split"],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def validate_pilot_results(payload: object) -> None:
    if not isinstance(payload, dict):
        raise PilotValidationError("pilot_results.json 顶层必须是 JSON 对象")
    protocol = payload.get("protocol")
    if not isinstance(protocol, dict) or not isinstance(protocol.get("questions"), dict):
        raise PilotValidationError("pilot_results.json 缺少 protocol.questions 本轮协议")
    questions = payload.get("questions")
    if not isinstance(questions, dict):
        raise PilotValidationError("pilot_results.json 缺少 questions 结果")

    errors: list[str] = []
    protocol_questions = protocol["questions"]
    for question_key, question_protocol in protocol_questions.items():
        entry = questions.get(question_key)
        if not isinstance(entry, dict):
            errors.append(f"{question_key} 缺少 pilot 结果")
            continue
        allowed_names = _candidate_names(question_protocol)
        if not allowed_names:
            errors.append(f"{question_key} 本轮协议没有候选名")
            continue
        candidates = entry.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            errors.append(f"{question_key}.candidates 必须为非空数组")
            continue

        splits: list[str] = []
        ran_ok = False
        for index, candidate in enumerate(candidates, 1):
            if not isinstance(candidate, dict):
                errors.append(f"{question_key} 候选 {index} 不是对象")
                continue
            name = str(candidate.get("name", "")).strip()
            if not name or name.casefold() not in allowed_names:
                errors.append(f"{question_key} 候选 {name or index} 不属于本轮协议")
            try:
                splits.append(_canonical_split(candidate))
            except PilotValidationError:
                errors.append(f"{question_key} 候选 {name or index} 缺少数据划分")
            if candidate.get("ran_ok") is True:
                ran_ok = True
        if splits and any(split != splits[0] for split in splits[1:]):
            errors.append(f"{question_key} 的所有候选必须使用完全相同的数据划分")
        if not ran_ok:
            errors.append(f"{question_key} 没有任何候选真实跑通")

    for question_key in questions:
        if question_key not in protocol_questions:
            errors.append(f"{question_key} 不属于本轮协议")
    if errors:
        raise PilotValidationError("\n".join(errors))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pilot 同划分、本轮协议和真实跑通门禁")
    parser.add_argument("--results", default="结果/pilot_results.json")
    args = parser.parse_args(argv)
    path = Path(args.results)
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        validate_pilot_results(payload)
    except (OSError, json.JSONDecodeError, PilotValidationError) as exc:
        print(f"FAIL：{exc}")
        return 1
    print("PASS：所有 Pilot 候选同划分、属于本轮协议，且每问至少一个真实跑通")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
