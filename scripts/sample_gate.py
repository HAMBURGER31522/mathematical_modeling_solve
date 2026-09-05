# -*- coding: utf-8 -*-
"""sample_gate —— 逐场景样本量门禁(refusion M7,P0)。

为什么需要
----------
loop2-r2 的教训:2 万样本在 p≈0.90 阈值附近时,单侧下界 0.8988<0.90 判"不可行",
4 万样本时 0.9016≥0.90 判"可行"——同一个物理点,样本量决定结论(mmflow 据此把
答案从 0.87% 改成 0.88%)。逐场景的样本量纪律必须可执行、有退出码,
而不是规范条文(历史证明只写规范会漏,见 degenerate.py 头注)。

输入 schema(scenarios JSON)
---------------------------
{
  "scenarios": [
    {
      "scenario_id": "Q3-phi0.87-primary",   // 语义主键(与台账 scenario_id 对应)
      "k": 36182, "n": 40000,                // 成功次数与样本量
      "threshold": 0.90,                     // 机会约束阈值;描述性场景填 null
      "resolution": 0.0001,                  // 该场景的决策粒度 Δ(小数;0.01pp=0.0001)
      "verdict": "feasible",                 // feasible / excluded / intermediate
      "adjacent_excluded": "Q3-phi0.86-primary", // 可行点必须引用相邻已排除点(夹逼)
      "analytic_proof": "结果/饱和解析证明.md",   // k=0/k=n 饱及时必须有解析证明文件
      "certify": {"k": 18100, "n": 20000}    // 独立认证批次(不同 seed 基)
    }
  ],
  "n_floor": 20000                            // 全局样本量硬下限(K9)
}

检查项(每场景)
--------------
1. n ≥ n_floor(或场景自带 n_floor 覆盖);
2. 饱和(k==0 或 k==n):verdict 必须为 intermediate,且 analytic_proof 文件存在;
3. 区间宽度:Wilson 上界 u 满足 u - p̂ ≤ Δ/3;
4. 阈值场景的夹逼:verdict=feasible 时必须有 adjacent_excluded 且该场景 verdict=excluded;
5. 独立认证批次:n ≥ n_floor/2,且 |p1-p2| ≤ 2.58·√(se1²+se2²)(2.58 合成标准误);
6. threshold/resolution/verdict 字段缺失即 FAIL。

退出码:0 全过;1 有 FAIL。报告同时写 JSON(--report)。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys

Z = 1.959963984540054
CERT_Z = 2.5758293035489004


def wilson(k: int, n: int, z: float = Z):
    p = k / n
    den = 1 + z * z / n
    ctr = (p + z * z / (2 * n)) / den
    hw = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, ctr - hw), min(1.0, ctr + hw)


def gate(scenarios: list, n_floor: int) -> tuple[list, list]:
    problems, notes = [], []
    by_id = {s.get("scenario_id"): s for s in scenarios}
    for s in scenarios:
        sid = s.get("scenario_id") or "<缺 scenario_id>"
        where = f"[{sid}]"
        k, n = s.get("k"), s.get("n")
        thr = s.get("threshold")
        res = s.get("resolution")
        verdict = s.get("verdict")
        if not sid or sid == "<缺 scenario_id>":
            problems.append(f"{where} 缺 scenario_id")
            continue
        for name, v in (("k", k), ("n", n), ("resolution", res), ("verdict", verdict)):
            if v is None:
                problems.append(f"{where} 缺 {name}")
        if None in (k, n, res, verdict):
            continue
        if n < n_floor:
            problems.append(f"{where} n={n} < 硬下限 {n_floor}")
        lo, hi = wilson(k, n)
        p_hat = k / n
        u_minus_p = hi - p_hat
        if u_minus_p > res / 3 + 1e-15:
            problems.append(f"{where} u-p̂={u_minus_p:.5f} > Δ/3={res/3:.5f}"
                            f"(Δ={res});样本量不足以分辨该粒度")
        if (k == 0 or k == n):
            proof = s.get("analytic_proof")
            if verdict != "intermediate":
                problems.append(f"{where} 全0/全1 饱和但 verdict={verdict},"
                                "未经解析证明只能进 intermediate")
            if not proof or not os.path.exists(proof):
                problems.append(f"{where} 饱和场景缺解析证明文件: {proof}")
        if thr is not None:
            if verdict == "feasible":
                if lo < thr - 1e-12:
                    problems.append(f"{where} verdict=feasible 但 Wilson 下界 {lo:.5f} < {thr}")
                adj = s.get("adjacent_excluded")
                adj_s = by_id.get(adj)
                if not adj:
                    problems.append(f"{where} feasible 缺 adjacent_excluded(无夹逼)")
                elif adj_s is None:
                    problems.append(f"{where} adjacent_excluded 引用的 {adj} 不在本批场景中")
                else:
                    ak, an = adj_s.get("k"), adj_s.get("n")
                    if ak is None or an is None:
                        problems.append(f"{where} 相邻点 {adj} 缺 k/n")
                    else:
                        alo, ahi = wilson(ak, an)
                        if not (ahi < thr + 1e-12) and adj_s.get("verdict") != "excluded":
                            problems.append(f"{where} 相邻点 {adj} 未被判 excluded"
                                            f"(hi={ahi:.5f}),夹逼不成立")
            elif verdict == "excluded":
                if hi >= thr - 1e-12 and lo <= thr + 1e-12:
                    notes.append(f"{where} hi={hi:.5f} 跨阈值:应为 intermediate"
                                 "(区间跨阈值只能称证据不足)")
        cert = s.get("certify")
        if not cert:
            problems.append(f"{where} 缺独立认证批次 certify")
        else:
            ck, cn = cert.get("k"), cert.get("n")
            if not ck or not cn or cn < n_floor / 2:
                problems.append(f"{where} certify 样本 {cn} < n_floor/2({n_floor//2})")
            else:
                p1, p2 = k / n, ck / cn
                se = math.sqrt(p1 * (1 - p1) / n + p2 * (1 - p2) / cn)
                if abs(p1 - p2) > CERT_Z * se:
                    problems.append(f"{where} 主/认证批次分歧 |{p1:.4f}-{p2:.4f}|="
                                    f"{abs(p1-p2):.4f} > 2.58·SE={CERT_Z*se:.4f}")
    return problems, notes


def selftest() -> int:
    """合成场景自检:五个构造用例各验一条规则。"""
    import tempfile
    ok = True
    proof = tempfile.NamedTemporaryFile(suffix=".md", delete=False)
    proof.write("# 饱和解析证明\n边界平移后单体不跨电极,n=1 时导通概率恒为 0。\n".encode())
    proof.close()
    good = dict(scenario_id="ok-1", k=18079, n=20000, threshold=None,
                resolution=0.02, verdict="feasible", certify={"k": 9100, "n": 10000})
    sat_bad = dict(good, scenario_id="sat-bad", k=20000, verdict="feasible",
                   certify={"k": 20000, "n": 20000})
    sat_ok = dict(good, scenario_id="sat-ok", k=20000, verdict="intermediate",
                  analytic_proof=proof.name, certify={"k": 20000, "n": 20000})
    wide = dict(good, scenario_id="wide", resolution=0.001)
    no_bracket = dict(good, scenario_id="nbrk", threshold=0.90, verdict="feasible")
    cases = [
        (dict(scenarios=[good], n_floor=10000), 0, "合格场景应过"),
        (dict(scenarios=[sat_bad], n_floor=10000), 1, "饱和判 feasible 应 FAIL"),
        (dict(scenarios=[sat_ok], n_floor=10000), 0, "饱和+证明=intermediate 应过"),
        (dict(scenarios=[wide], n_floor=10000), 1, "区间过宽应 FAIL"),
        (dict(scenarios=[no_bracket], n_floor=10000), 1, "可行点缺夹逼应 FAIL"),
    ]
    for spec, expect, note in cases:
        probs, _ = gate(spec["scenarios"], spec["n_floor"])
        got = 0 if not probs else 1
        if got != expect:
            ok = False
            print(f"SELFTEST FAIL: {note} -> problems={probs[:2]}")
        else:
            print(f"selftest ok: {note}")
    os.unlink(proof.name)
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="逐场景样本量门禁(M7)")
    ap.add_argument("--scenarios", help="场景 JSON 文件")
    ap.add_argument("--n-floor", type=int, default=20000)
    ap.add_argument("--report", help="报告 JSON 输出路径")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.scenarios or not os.path.exists(args.scenarios):
        print("FAIL 缺 --scenarios 文件")
        return 1
    spec = json.load(open(args.scenarios, encoding="utf-8"))
    scenarios = spec.get("scenarios", spec if isinstance(spec, list) else [])
    n_floor = spec.get("n_floor", args.n_floor) if isinstance(spec, dict) else args.n_floor
    problems, notes = gate(scenarios, n_floor)
    report = dict(problems=problems, notes=notes, n_scenarios=len(scenarios),
                  n_floor=n_floor)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=1)
    for p in problems:
        print("FAIL " + p)
    for nt in notes:
        print("NOTE " + nt)
    print(f"sample_gate:FAIL {len(problems)},NOTE {len(notes)},场景 {len(scenarios)}")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
