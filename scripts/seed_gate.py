# -*- coding: utf-8 -*-
"""多种子答案稳定性门禁（P3 第 9 条 / R5 / R11 的执行体）。

为什么需要它：skill 里三条规则都写着这件事——
  R5「已分辨」要求 u ≤ Δ/3；
  R11「临界/最优/边界答案必须独立复核」；
  P3 第 9 条「≥2 个独立主种子重跑终验，按题目精度取整后答案不变」。
但没有任何机器检查。loop2-r2 判负的原话是「自报 resolved=false 却未补样本」——
规则写着、门禁不查，于是照样带着一个只在某一批随机数下成立的答案往下走。

本门禁只回答一个问题：**这个临界档答案换一批独立随机数还成立吗。**
判据（缺一 FAIL）：
  1. 独立种子族 ≥ --min-families（默认 2，与 P3 第 9 条一致）；
  2. 每个种子族都要覆盖答案点及至少一个相邻档，否则夹逼不成立；
  3. 逐族独立判定：答案 = 满足「下界 ≥ 阈值」的最小档位；
  4. 各族判出的答案必须与声明答案一致；任一族不同 = 答案未分辨，
     必须写 certificate.resolved=false 并降到下一档精度报告，不得报满精度。

输入 JSON（由分析步骤产出，脚本不猜原始 CSV 的列语义）：
{
  "question": "Q3",
  "answer": 615,              // 声明的最终答案档位
  "direction": "min",         // min = 越小越好（找满足阈值的最小档）；max 反之
  "threshold": 0.90,
  "alpha": 0.05,
  "families": {
    "1": {"614": {"k": 17982, "n": 20000}, "615": {"k": 18100, "n": 20000}, ...},
    "2": {...}, "3": {...}
  }
}

用法：
    python scripts/seed_gate.py 结果/多种子.json --out 结果/gates/G3-seed.md

退出码：0 = 各族一致且与声明答案相同；1 = 不一致或覆盖不足；2 = 用法/输入错误。
纯标准库。
"""
import argparse
import json
import math
import os
import sys

Z = {0.10: 1.2815515655446004, 0.05: 1.6448536269514722, 0.025: 1.959963984540054,
     0.01: 2.3263478740408408}


def z_for(alpha):
    """单侧下界用的 z。表里没有就按正态分位数近似（Acklam 系数，够门禁用）。"""
    if alpha in Z:
        return Z[alpha]
    p = 1.0 - alpha
    a = [-39.69683028665376, 220.9460984245205, -275.9285104469687,
         138.3577518672690, -30.66479806614716, 2.506628277459239]
    b = [-54.47609879822406, 161.5858368580409, -155.6989798598866,
         66.80131188771972, -13.28068155288572, 1.0]
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
           (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + b[5])


def wilson_lower(k, n, alpha):
    if n <= 0:
        return 0.0
    z = z_for(alpha)
    p = k / n
    den = 1.0 + z * z / n
    ctr = (p + z * z / (2.0 * n)) / den
    hw = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n)) / den
    return max(0.0, ctr - hw)


def family_answer(points, threshold, alpha, direction):
    """在一个种子族内独立判答案：下界 ≥ 阈值的最小（或最大）档位。"""
    passing = [lvl for lvl, lo in points.items() if lo >= threshold]
    if not passing:
        return None
    return min(passing) if direction == "min" else max(passing)


def main():
    ap = argparse.ArgumentParser(description="多种子答案稳定性门禁")
    ap.add_argument("spec", help="多种子结果 JSON")
    ap.add_argument("--out", default="结果/gates/G3-seed.md")
    ap.add_argument("--min-families", type=int, default=2)
    a = ap.parse_args()

    if not os.path.isfile(a.spec):
        print("找不到输入：%s" % a.spec, file=sys.stderr)
        return 2
    try:
        spec = json.load(open(a.spec, encoding="utf-8"))
        answer = int(spec["answer"])
        threshold = float(spec["threshold"])
        alpha = float(spec.get("alpha", 0.05))
        direction = spec.get("direction", "min")
        families = spec["families"]
    except (ValueError, KeyError, TypeError) as exc:
        print("输入结构不合法：%s" % exc, file=sys.stderr)
        return 2
    if direction not in ("min", "max"):
        print("direction 只能是 min 或 max", file=sys.stderr)
        return 2

    problems, rows = [], []
    if len(families) < a.min_families:
        problems.append("独立种子族只有 %d 个 < %d：单族结论可能只是这批随机数的运气"
                        % (len(families), a.min_families))

    verdicts = {}
    for fam in sorted(families):
        points, lowers = {}, {}
        for lvl_s, rec in families[fam].items():
            lvl = int(lvl_s)
            k, n = int(rec["k"]), int(rec["n"])
            lo = wilson_lower(k, n, alpha)
            points[lvl] = lo
            lowers[lvl] = (k, n, lo)
        if answer not in points:
            problems.append("种子族 %s 没有答案点 %d 的数据" % (fam, answer))
            continue
        neighbours = [lvl for lvl in points if lvl != answer]
        if not neighbours:
            problems.append("种子族 %s 只有答案点、没有相邻档：夹逼不成立" % fam)
        got = family_answer(points, threshold, alpha, direction)
        verdicts[fam] = got
        for lvl in sorted(lowers):
            k, n, lo = lowers[lvl]
            rows.append((fam, lvl, k, n, lo, "≥阈值" if lo >= threshold else "<阈值",
                         "← 本族判定" if lvl == got else ""))

    distinct = {v for v in verdicts.values()}
    if verdicts and (len(distinct) > 1 or distinct != {answer}):
        problems.append("各族独立判定为 %s，声明答案是 %d —— 答案随种子漂移即为未分辨；"
                        "必须写 certificate.resolved=false 并降到下一档精度报告"
                        % ({f: v for f, v in verdicts.items()}, answer))

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("# 多种子答案稳定性（%s）\n\n" % spec.get("question", "?"))
        fh.write("声明答案 **%d**；阈值 %g；alpha %g；方向 %s；独立种子族 %d 个\n\n"
                 % (answer, threshold, alpha, direction, len(families)))
        fh.write("| 种子族 | 档位 | k | n | Wilson 下界 | 对阈值 | |\n|---|---|---|---|---|---|---|\n")
        for fam, lvl, k, n, lo, cmp_, mark in rows:
            fh.write("| %s | %d | %d | %d | %.5f | %s | %s |\n" % (fam, lvl, k, n, lo, cmp_, mark))
        fh.write("\n逐族判定：%s\n\n" % {f: v for f, v in verdicts.items()})
        if problems:
            fh.write("## FAIL\n\n" + "\n".join("- " + p for p in problems) + "\n")
        else:
            fh.write("## PASS\n\n各独立种子族独立判出同一答案，与声明一致。\n")

    for p in problems:
        print("FAIL  " + p)
    print("种子族 %d，逐族判定 %s → %s"
          % (len(families), {f: v for f, v in verdicts.items()}, a.out))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
