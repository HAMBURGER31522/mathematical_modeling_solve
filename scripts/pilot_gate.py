#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate pilot results against their current-round protocol."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


class PilotValidationError(ValueError):
    """Raised when a pilot result lacks comparable, truthful pilot evidence."""


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


def validate_pilot_results(payload: object) -> list[str]:
    if not isinstance(payload, dict):
        raise PilotValidationError("pilot_results.json 顶层必须是 JSON 对象")
    protocol = payload.get("protocol")
    if not isinstance(protocol, dict) or not isinstance(protocol.get("questions"), dict):
        raise PilotValidationError("pilot_results.json 缺少 protocol.questions 本轮协议")
    questions = payload.get("questions")
    if not isinstance(questions, dict):
        raise PilotValidationError("pilot_results.json 缺少 questions 结果")

    errors: list[str] = []
    notes: list[str] = []
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
        if len(candidates) < 2:
            errors.append(f"{question_key}.candidates 至少 2 个，不能只拿一个方案定案")

        budget = question_protocol.get("budget_seconds")
        if budget is None:
            notes.append(f"{question_key} 时间预算未声明：跳过 budget_seconds 核验")
        elif isinstance(budget, bool) or not isinstance(budget, (int, float)) or budget < 0:
            errors.append(f"{question_key}.protocol.budget_seconds 必须是非负数字")
            budget = None

        splits: list[str] = []
        metric_names: list[str] = []
        has_baseline = False
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
            metric_name = candidate.get("metric_name")
            if not isinstance(metric_name, str) or not metric_name.strip():
                errors.append(f"{question_key} 候选 {name or index} 缺少 metric_name")
            else:
                metric_names.append(metric_name.strip().casefold())
            if candidate.get("is_baseline") is True:
                has_baseline = True
            seconds = candidate.get("seconds")
            if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or seconds < 0:
                errors.append(f"{question_key} 候选 {name or index} 的 seconds 必须是非负数字")
            elif budget is not None and seconds > budget:
                errors.append(f"{question_key} 候选 {name or index} 的 seconds={seconds} "
                              f"> budget_seconds={budget}")
            status = candidate.get("ran_ok")
            if not isinstance(status, bool):
                errors.append(f"{question_key} 候选 {name or index} 的 ran_ok 必须是 true 或 false")
            elif status:
                ran_ok = True
            else:
                failure = candidate.get("failure")
                if not isinstance(failure, str) or not failure.strip():
                    errors.append(f"{question_key} 候选 {name or index} ran_ok=false 时必须记录 failure")
        if splits and any(split != splits[0] for split in splits[1:]):
            errors.append(f"{question_key} 的所有候选必须使用完全相同的数据划分")
        if not has_baseline:
            errors.append(f"{question_key} 必须有一个候选标记 is_baseline: true")
        if metric_names and any(metric != metric_names[0] for metric in metric_names[1:]):
            errors.append(f"{question_key} 的所有候选必须报告同一个 metric_name")
        if not ran_ok:
            errors.append(f"{question_key} 没有任何候选真实跑通")

    for question_key in questions:
        if question_key not in protocol_questions:
            errors.append(f"{question_key} 不属于本轮协议")
    if errors:
        raise PilotValidationError("\n".join(errors))
    return notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pilot 同划分、本轮协议和真实跑通门禁")
    parser.add_argument("--results", default="结果/pilot_results.json")
    args = parser.parse_args(argv)
    path = Path(args.results)
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        notes = validate_pilot_results(payload)
    except (OSError, json.JSONDecodeError, PilotValidationError) as exc:
        print(f"FAIL：{exc}")
        return 1
    for note in notes:
        print(f"NOTE：{note}")
    print("PASS：所有 Pilot 候选已比较候选数、baseline、数据划分、指标、时间与真实运行记录")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
