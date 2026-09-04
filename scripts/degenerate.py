# -*- coding: utf-8 -*-
"""退化规模检验（R13）：把规模参数降到物理上不可能成立的值，检查结果是不是不可能值。

为什么需要这个脚本
------------------
2026-09-04 的实测事故：一份 50 页论文、92 项测试全过、G0-G7 全绿的交付物，
四问答案错了近 70 倍。根因是生成的每个个体被边界规则切成的碎片共享同一个节点，
于是**单个个体自己就把两个电极短接了**——实测单体自导通率 25.2%。

所有统计证书都拦不住它（样本量再大也救不了错的物理），
而 `n=1` 这一行只要跑过，30 秒就能发现。

把这条检查写成规范条文是不够的——历史上"图未被正文引用"也写在规范里，
但因为只记 WARN 而不是 FAIL，照样漏过去了。**检查必须可执行、有退出码。**

用法
----
被测代码需提供一个可导入的判定函数：

    def conducts(n: int, threshold: float, seed: int) -> bool
        构造 n 个个体的随机构型，返回是否两端导通。

然后：

    python scripts/degenerate.py --fn 求解.core.simulation:conducts \\
        --trials 300 --threshold 1.8 --out 结果/gates/G3-退化检验.json

    # 若单个个体在几何上确实可能连通两端（例如个体尺度 >= 跨度），加 --allow-single
    #   并在论文中说明理由；否则单体自导通即判 FAIL。

退出码：0 全部通过；1 有 FAIL。
"""
from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
import sys


def load_callable(spec: str):
    """'包.模块:函数' 或 '路径/文件.py:函数'。"""
    if ":" not in spec:
        raise SystemExit("--fn 需写成 模块:函数 或 文件.py:函数")
    mod_part, fn_name = spec.rsplit(":", 1)
    if mod_part.endswith(".py") or os.path.sep in mod_part or "/" in mod_part:
        path = os.path.abspath(mod_part)
        name = os.path.splitext(os.path.basename(path))[0]
        spec_obj = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec_obj)
        sys.modules[name] = module
        spec_obj.loader.exec_module(module)
    else:
        module = importlib.import_module(mod_part)
    if not hasattr(module, fn_name):
        raise SystemExit(f"{mod_part} 中没有 {fn_name}")
    return getattr(module, fn_name)


def rate(fn, n: int, threshold: float, trials: int, seed0: int) -> float:
    hit = 0
    for i in range(trials):
        try:
            if fn(n, threshold, seed0 + i):
                hit += 1
        except Exception as exc:  # 让实现错误显性化，不要静默当成 False
            raise SystemExit(f"判定函数在 n={n}, threshold={threshold} 处抛异常：{exc!r}")
    return hit / trials if trials else 0.0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fn", required=True, help="判定函数：模块:函数，签名 (n, threshold, seed) -> bool")
    ap.add_argument("--threshold", type=float, required=True, help="题面判定阈值（正常值）")
    ap.add_argument("--trials", type=int, default=300)
    ap.add_argument("--seed0", type=int, default=20260904)
    ap.add_argument("--n-probe", type=int, default=None,
                    help="额外探针规模：给一个题面档位的个体数，用于量级自洽检查（R14）")
    ap.add_argument("--allow-single", action="store_true",
                    help="单个个体在几何上确实可能连通两端时才可加；必须在论文中说明理由")
    ap.add_argument("--out", default="结果/gates/G3-退化检验.json")
    a = ap.parse_args(argv)

    fn = load_callable(a.fn)
    checks = []

    def add(name, value, ok, expect, note=""):
        checks.append({"检查": name, "实测": value, "期望": expect,
                       "判定": "PASS" if ok else "FAIL", "说明": note})

    # 1) n = 0：空构型不得有任何"存在性"结论
    r0 = rate(fn, 0, a.threshold, min(a.trials, 50), a.seed0)
    add("n=0 导通率", r0, r0 == 0.0, "0",
        "空构型出结论 = 图/并查集有幽灵节点或初始化把两极直接相连")

    # 2) n = 1：单体自导通（本次事故的拦截点）
    r1 = rate(fn, 1, a.threshold, a.trials, a.seed0 + 10_000)
    ok1 = (r1 == 0.0) or a.allow_single
    add("n=1 导通率", r1, ok1, "0（除非 --allow-single）",
        "单体自导通 = 存在短路通道：折回/镜像碎片共享节点、判据尺度错、边界条件写反")

    # 3) 阈值 → 0：连接应趋于最小
    r_lo = rate(fn, max(a.n_probe or 50, 2), 0.0, min(a.trials, 100), a.seed0 + 20_000)
    # 4) 阈值 → 很大：连接应趋于饱和
    big = max(a.threshold * 1e6, 1e6)
    r_hi = rate(fn, max(a.n_probe or 50, 2), big, min(a.trials, 100), a.seed0 + 30_000)
    add("阈值→0 导通率", r_lo, True, "应显著低于阈值→大", "阈值归零仍大量连通 = 距离函数符号或量纲错")
    add("阈值→大 导通率", r_hi, True, "应显著高于阈值→0", "")
    add("阈值单调性", f"{r_lo} -> {r_hi}", r_lo <= r_hi, "单调不减",
        "不单调 = 判据实现有分支错误")
    # 阈值敏感性：把阈值从 0 拉到极大，结果必须**看得出差别**。
    # 两端相同 = 阈值根本没参与判定，或存在与阈值无关的短路通道（本次事故的第二个独立探测器）。
    add("阈值敏感性", round(r_hi - r_lo, 4), (r_hi - r_lo) >= 0.05, "两端差 >= 0.05",
        "判据对阈值不敏感 = 阈值未真正进入判定，或有与阈值无关的短路通道（折回共享节点、幽灵边）")

    if a.n_probe:
        rp = rate(fn, a.n_probe, a.threshold, min(a.trials, 200), a.seed0 + 40_000)
        add(f"题面档位探针 n={a.n_probe} 导通率", rp, True,
            "与题面对该档的预期同量级（人工核对，R14）",
            "若远高/远低于题面档位的合理预期，先查口径不要先信自己的数")

    n_fail = sum(1 for c in checks if c["判定"] == "FAIL")
    report = {"函数": a.fn, "阈值": a.threshold, "试验次数": a.trials,
              "FAIL 数": n_fail, "检查": checks,
              "口径": "R13 退化规模检验；FAIL 即 G3 不通过，必须回查口径而不是加样本量"}

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")

    for c in checks:
        print(f"  [{c['判定']}] {c['检查']} = {c['实测']}（期望 {c['期望']}）"
              + (f"  ← {c['说明']}" if c["判定"] == "FAIL" and c["说明"] else ""))
    print(f"退化规模检验：FAIL {n_fail} → {a.out}")
    if n_fail:
        print("！！口径有问题。加样本量不会让它变对——回到 P1 重新审口径。", file=sys.stderr)
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
