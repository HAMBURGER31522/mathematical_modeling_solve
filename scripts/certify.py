#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""机会约束统计证书：单侧下界、达标判定、样本量反解。只依赖标准库。

对应 references/algorithm-redlines.md R2/R5 与 computation-standards §5。
Wilson/Clopper-Pearson 均只适用于 iid Bernoulli；加权/相关/序贯场景须另给覆盖率依据。

用法：
  判定（输出 JSON，可直接作 ledger 的 certificate 块）：
    python certify.py --k 39668 --n 40000 --threshold 0.90 --delta 0.005
        [--alpha 0.05] [--m 1] [--method wilson|cp]
    · verdict  = feasible（下界 ≥ threshold）/ excluded（上界 < threshold）/ inconclusive（区间跨阈值）
    · pass     = verdict == feasible（R2 达标，不可豁免）；inconclusive 会附带所需样本量
    · u        = p̂ − 下界；resolved = (u ≤ delta/3)（R5 已分辨，可降级）
    · --m K    = 同时比较 K 项时的 Bonferroni 校正（alpha/K）
  反解样本量（证书协议是一次封存一次终验，机时按把握度 n 排，不按临界 n 排）：
    python certify.py --solve-n --p-hat 0.905 --threshold 0.90 [--power 0.90]
    · n_critical：真值恰为 p̂ 时下界贴线的最小 n（一次终验只有 ~50% 概率过线）
    · n_power  ：真值为 p̂ 时终验以 power 概率过线所需 n（通常为临界值的 ~3 倍）

退出码：判定模式 0=PASS / 1=FAIL；反解模式恒 0。
"""
import argparse
import json
import math
import sys


def z_for(conf: float) -> float:
    """标准正态分位数：对 Φ(z)=conf 用 erf 二分求逆（全区间稳健）。"""
    if not 0 < conf < 1:
        raise ValueError("conf 必须在 (0,1)")
    lo, hi = -12.0, 12.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if 0.5 * (1 + math.erf(mid / math.sqrt(2))) < conf:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def wilson_lower(k: int, n: int, alpha: float) -> float:
    """单侧 Wilson score 下界（置信水平 1-alpha）。"""
    if n <= 0:
        raise ValueError("n 必须为正")
    z = z_for(1 - alpha)
    p = k / n
    denom = 1 + z * z / n
    center = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, (center - margin) / denom)


def _betacf(a: float, b: float, x: float) -> float:
    """正则不完全贝塔的连分数（Numerical Recipes betacf）。"""
    MAXIT, EPS, FPMIN = 200, 3e-12, 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    if abs(d) < FPMIN:
        d = FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        delc = d * c
        h *= delc
        if abs(delc - 1.0) < EPS:
            return h
    raise RuntimeError("betacf 未收敛")


def betainc(a: float, b: float, x: float) -> float:
    """正则不完全贝塔函数 I_x(a, b)。"""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    ln_bt = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
             + a * math.log(x) + b * math.log(1 - x))
    bt = math.exp(ln_bt)
    if x < (a + 1) / (a + b + 2):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1 - x) / b


def cp_lower(k: int, n: int, alpha: float) -> float:
    """单侧 Clopper-Pearson 精确下界：解 P(X ≥ k | p) = alpha。"""
    if k <= 0:
        return 0.0
    if k >= n:
        return alpha ** (1.0 / n)
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        # P(X >= k | p=mid) = I_mid(k, n-k+1)
        if betainc(k, n - k + 1, mid) < alpha:
            lo = mid
        else:
            hi = mid
    return lo


def wilson_upper(k: int, n: int, alpha: float) -> float:
    """单侧 Wilson score 上界（置信水平 1-alpha）。"""
    if n <= 0:
        raise ValueError("n 必须为正")
    z = z_for(1 - alpha)
    p = k / n
    denom = 1 + z * z / n
    center = p + z * z / (2 * n)
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return min(1.0, (center + margin) / denom)


def cp_upper(k: int, n: int, alpha: float) -> float:
    """单侧 Clopper-Pearson 精确上界：解 P(X <= k | p) = alpha。"""
    if k >= n:
        return 1.0
    if k <= 0:
        return 1.0 - alpha ** (1.0 / n)
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if 1.0 - betainc(k + 1, n - k, mid) > alpha:
            lo = mid
        else:
            hi = mid
    return hi


def upper_bound(k: int, n: int, alpha: float, method: str) -> float:
    return cp_upper(k, n, alpha) if method == "cp" else wilson_upper(k, n, alpha)


def lower_bound(k: int, n: int, alpha: float, method: str) -> float:
    return cp_lower(k, n, alpha) if method == "cp" else wilson_lower(k, n, alpha)


def k_star(n: int, threshold: float, alpha: float, method: str) -> int:
    """最小 k 使下界 ≥ threshold（对 k 单调，二分）。"""
    lo, hi = 0, n
    if lower_bound(hi, n, alpha, method) < threshold:
        return n + 1  # 该 n 下即使全成功也过不了线
    while lo < hi:
        mid = (lo + hi) // 2
        if lower_bound(mid, n, alpha, method) >= threshold:
            hi = mid
        else:
            lo = mid + 1
    return lo


def binom_sf_ge(k: int, n: int, p: float) -> float:
    """P(X ≥ k)，用正则不完全贝塔精确计算。"""
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    return betainc(k, n - k + 1, p)


def solve_n(p_hat: float, threshold: float, alpha: float, method: str, power: float):
    if p_hat <= threshold:
        raise SystemExit(f"p_hat={p_hat} ≤ threshold={threshold}：任何样本量都无法认证；"
                         "该点大概率不可行，或需要更高效的估计量/更好的方案点。")

    def crit_pass(n):
        return lower_bound(round(p_hat * n), n, alpha, method) >= threshold

    hi = 8
    while not crit_pass(hi):
        hi *= 2
        if hi > 10**9:
            raise SystemExit("临界 n 超过 1e9，按不可认证处理")
    lo = hi // 2 if hi > 8 else 1
    while lo < hi:
        mid = (lo + hi) // 2
        if crit_pass(mid):
            hi = mid
        else:
            lo = mid + 1
    n_critical = lo

    def power_ok(n):
        ks = k_star(n, threshold, alpha, method)
        return binom_sf_ge(ks, n, p_hat) >= power

    hi = max(n_critical, 8)
    while not power_ok(hi):
        hi *= 2
        if hi > 10**9:
            raise SystemExit("把握度 n 超过 1e9，按不可认证处理")
    lo = n_critical
    while lo < hi:
        mid = (lo + hi) // 2
        if power_ok(mid):
            hi = mid
        else:
            lo = mid + 1
    return n_critical, lo


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="机会约束证书：下界判定 / 样本量反解")
    ap.add_argument("--k", type=int, help="成功次数")
    ap.add_argument("--n", type=int, help="试验次数")
    ap.add_argument("--threshold", type=float, required=True, help="题面阈值（如 0.90）")
    ap.add_argument("--delta", type=float, help="效应量 Δ；给了才判 R5 已分辨（u ≤ Δ/3）")
    ap.add_argument("--alpha", type=float, default=0.05, help="单侧显著性水平，默认 0.05")
    ap.add_argument("--m", type=int, default=1, help="同时比较项数 K（Bonferroni：alpha/K）")
    ap.add_argument("--method", choices=["wilson", "cp"], default="wilson")
    ap.add_argument("--solve-n", action="store_true", help="反解样本量模式")
    ap.add_argument("--p-hat", type=float, help="反解模式：预估成功率")
    ap.add_argument("--power", type=float, default=0.90, help="反解模式：终验过线的把握度")
    a = ap.parse_args(argv)

    alpha_eff = a.alpha / max(1, a.m)
    conf_label = f"{a.method}_lower_{round((1 - alpha_eff) * 100, 4):g}"

    if a.solve_n:
        if a.p_hat is None:
            ap.error("--solve-n 需要 --p-hat")
        n_crit, n_pow = solve_n(a.p_hat, a.threshold, alpha_eff, a.method, a.power)
        print(json.dumps({
            "mode": "solve-n", "p_hat": a.p_hat, "threshold": a.threshold,
            "alpha": a.alpha, "m": a.m, "alpha_effective": alpha_eff, "method": a.method,
            "n_critical": n_crit,
            "n_power": n_pow, "power": a.power,
            "note": "机时按 n_power 排；n_critical 下一次终验只有约 50% 概率过线",
        }, ensure_ascii=False, indent=2))
        return 0

    if a.k is None or a.n is None:
        ap.error("判定模式需要 --k 与 --n")
    p_hat = a.k / a.n
    bound = lower_bound(a.k, a.n, alpha_eff, a.method)
    ubound = upper_bound(a.k, a.n, alpha_eff, a.method)
    # 三态证书：把"证据不足"与"已排除"分开，别让前者被默默当成后者。
    #   feasible     下界 >= 阈值           → 已认证可行
    #   excluded     上界 <  阈值           → 已认证排除
    #   inconclusive 区间跨过阈值           → 样本量不够，不得据此下结论
    if bound >= a.threshold:
        verdict = "feasible"
    elif ubound < a.threshold:
        verdict = "excluded"
    else:
        verdict = "inconclusive"
    passed = verdict == "feasible"
    out = {
        "family": conf_label, "bound": round(bound, 6), "upper": round(ubound, 6),
        "n": a.n, "k": a.k,
        "p_hat": round(p_hat, 6), "threshold": a.threshold,
        "alpha": a.alpha, "m": a.m, "alpha_effective": alpha_eff,
        "verdict": verdict,
        "pass": passed,
    }
    if verdict == "inconclusive":
        n_crit, n_pow = solve_n(p_hat, a.threshold, alpha_eff, a.method, a.power)
        out["inconclusive_note"] = ("区间跨过阈值：既不能称可行也不能称已排除。"
                                    "要下结论请补样本或改述为『证据不足』。")
        out["n_needed_critical"] = n_crit
        out["n_needed_power"] = n_pow
    if a.delta is not None:
        u = p_hat - bound
        out.update({"delta": a.delta, "u": round(u, 6), "resolved": u <= a.delta / 3})
    else:
        out["note"] = "未传 --delta：R5（已分辨）未判定，见 SKILL.md G3"
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
