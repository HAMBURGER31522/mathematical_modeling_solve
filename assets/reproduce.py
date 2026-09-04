# -*- coding: utf-8 -*-
"""交付包复现入口（模板）。放在交付目录根，解包后一条命令跑通：

    python reproduce.py            # 只读复核：校验台账、证书、图与论文数字的一致性
    python reproduce.py --recompute  # 重算最小可核子集（默认小样本，几分钟内）

【为什么必须有这个文件】评分含 repro 维；只在 README 里写命令不够——
解包的人不看论文也要能跑起来。横比中我方是唯一没有可执行入口的一份。

改造要点：把 CHECKS 里的路径与命令换成本次交付的真实内容，其余逻辑不用动。
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# 只读复核项：(说明, 相对路径) —— 缺一个即 fail
REQUIRED = [
    ("论文 PDF", "论文/main.pdf"),
    ("论文源", "论文/main.tex"),
    ("数值宏", "论文/numbers.tex"),
    ("结果台账", "结果/results_ledger.json"),
    ("图目录", "图"),
    ("求解代码", "求解"),
]

# 重算项：(说明, 命令) —— 每条应在数分钟内跑完，且写回可比对的结果文件
RECOMPUTE = [
    # ("Q1 判定（附件全量，秒级）", [sys.executable, "求解/q1_solve.py"]),
]


def check_exists():
    bad = []
    for label, rel in REQUIRED:
        p = os.path.join(HERE, rel)
        ok = os.path.exists(p)
        print(("  OK   " if ok else "  MISS ") + f"{label}: {rel}")
        if not ok:
            bad.append(rel)
    return bad


def check_ledger():
    """台账自洽 + 论文宏与台账逐条比对。"""
    lp = os.path.join(HERE, "结果/results_ledger.json")
    np_ = os.path.join(HERE, "论文/numbers.tex")
    if not (os.path.exists(lp) and os.path.exists(np_)):
        return ["台账或 numbers.tex 缺失，跳过一致性比对"]
    led = json.load(open(lp, encoding="utf-8"))
    tex = open(np_, encoding="utf-8").read()
    problems = []
    for key, e in led.items():
        if e.get("role") == "intermediate":
            continue
        disp = str(e.get("display", ""))
        if disp and disp not in tex:
            problems.append(f"台账条目 {key} 的值 {disp} 未出现在 numbers.tex")
        if e.get("status") == "stale":
            problems.append(f"台账条目 {key} 状态为 stale，不得被论文引用")
    print(f"  台账条目 {len(led)} 条，比对问题 {len(problems)} 条")
    return problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recompute", action="store_true", help="重算最小可核子集")
    a = ap.parse_args()

    print("== 1. 交付物完整性 ==")
    bad = check_exists()
    print("== 2. 台账与论文数字一致性 ==")
    problems = check_ledger()

    if a.recompute:
        print("== 3. 重算最小可核子集 ==")
        for label, cmd in RECOMPUTE:
            print(f"  -> {label}")
            r = subprocess.run(cmd, cwd=HERE)
            if r.returncode != 0:
                problems.append(f"重算失败：{label}")
        if not RECOMPUTE:
            print("  （未配置重算项：交付前必须填 RECOMPUTE，否则 repro 维不完整）")
            problems.append("RECOMPUTE 为空")

    print("\n== 结论 ==")
    if bad or problems:
        for x in bad:
            print("  FAIL 缺文件:", x)
        for x in problems:
            print("  FAIL", x)
        return 1
    print("  PASS 交付物自洽")
    return 0


if __name__ == "__main__":
    sys.exit(main())
