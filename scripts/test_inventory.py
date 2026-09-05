# -*- coding: utf-8 -*-
"""test_inventory —— G3 测试门的实际数量与独立 oracle 检查(refusion M10,P1)。

教训(refusion-merged M10 / L27)
--------------------------------
"92 项测试全过"曾出现在答案错 68 倍的交付物上。数量必须来自
`pytest --collect-only` 的实际收集结果,而不是论文/README 的自报;
且测试必须调用独立 oracle(参考实现/暴力对照),否则是自证清白。

用法
----
python test_inventory.py --tests-dir <交付物的测试目录> \
    [--claimed 92] [--oracle-markers 独立,oracle,brute,参考实现,对照] \
    [--report report.json]

检查
----
1. collect-only 实际收集数 == claimed(若给 --claimed);claimed 缺失时只报告数量;
2. 测试文件中存在独立 oracle 标记(至少一个文件命中任一标记);
3. 每个测试文件可被收集(收集错误 = FAIL)。

退出码:0 全过;1 有 FAIL。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys


def collect_count(tests_dir: str) -> tuple[int, str]:
    r = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", os.path.abspath(tests_dir)],
                       capture_output=True, text=True)
    out = r.stdout or ""
    m = re.search(r"(\d+) test", out)
    n = int(m.group(1)) if m else 0
    if r.returncode not in (0, 5):   # 5 = 没收集到,pytest 正常退出码
        return n, out[-400:] + (r.stderr or "")[-200:]
    return n, ""


def oracle_scan(tests_dir: str, markers: list) -> dict:
    files = [f for f in os.listdir(tests_dir) if f.startswith("test_") and f.endswith(".py")]
    hits = {}
    for f in files:
        t = open(os.path.join(tests_dir, f), encoding="utf-8", errors="ignore").read()
        hit = [m for m in markers if m.lower() in t.lower()]
        if hit:
            hits[f] = hit
    return {"files": len(files), "files_with_oracle": len(hits), "hits": hits}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="G3 测试清单与独立 oracle 检查(M10)")
    ap.add_argument("--tests-dir", required=True)
    ap.add_argument("--claimed", type=int, help="论文/README 自报的测试数量")
    ap.add_argument("--oracle-markers", default="独立,oracle,brute,参考实现,对照,reference")
    ap.add_argument("--report")
    args = ap.parse_args(argv)
    if not os.path.isdir(args.tests_dir):
        print(f"FAIL 测试目录不存在: {args.tests_dir}")
        return 1
    n, err = collect_count(args.tests_dir)
    problems = []
    if err and n == 0:
        problems.append(f"pytest --collect-only 失败: {err[:200]}")
    markers = [m for m in args.oracle_markers.split(",") if m]
    scan = oracle_scan(args.tests_dir, markers)
    if args.claimed is not None and n != args.claimed:
        problems.append(f"自报测试数 {args.claimed} != collect-only 实际 {n}(L27:自报数不作数)")
    if scan["files"] and scan["files_with_oracle"] == 0:
        problems.append("没有任何测试文件引用独立 oracle(标记: "
                        + ",".join(markers) + ")——自证清白风险")
    report = dict(collected=n, claimed=args.claimed, oracle=scan, problems=problems)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=1)
    for p in problems:
        print("FAIL " + p)
    print(f"test_inventory:collect={n} claimed={args.claimed} "
          f"oracle={scan['files_with_oracle']}/{scan['files']} FAIL {len(problems)}")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
