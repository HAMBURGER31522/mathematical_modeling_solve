# -*- coding: utf-8 -*-
"""长批次可恢复性门禁（P3）——把「长计算是可恢复状态机」从散文变成退出码。

为什么需要它：skill 里早就白纸黑字写着「长批次不得用一次性 pool.map 赌全量」，
但没有任何机器检查去拦。2026-09-06 实测后果：一个 18 万单元的多种子批用一次性
pool.map 写成，无分块落盘，**从未跑完过**；工程记录里却写着「批次仍在跑，预计还需
3 小时，不可杀」，实际进程早已退出。规范写了没人执行，等于没写。

判据（对每个使用了进程/线程池 map 的脚本）：
  1. 必须有原子落盘——出现 os.replace(（写临时文件再改名），否则崩溃点之前的机时全丢；
  2. 必须有续跑扫描——启动时列目录/判存在以跳过已完成块，否则重跑等于从零开始。
两条缺一即 FAIL。只用池做短计算（无落盘需求）的脚本用 --skip 显式豁免并写明理由。

用法：
    python scripts/batch_gate.py 求解/*.py --out 结果/gates/G3-batch.md
    python scripts/batch_gate.py 求解/run_x.py --skip run_probe.py=探针,单次<60s

退出码：0 = 全过或全部合法豁免；1 = 存在不可恢复的长批脚本；2 = 用法错误。
纯标准库。
"""
import argparse
import glob
import os
import re
import sys

POOL = re.compile(r"\b(?:pool|executor|ex|p)\s*\.\s*(?:i?map(?:_unordered)?|starmap)\s*\(", re.I)
POOL_CTOR = re.compile(r"\b(?:Pool|ProcessPoolExecutor|ThreadPoolExecutor)\s*\(\s*(\d+)?")
ATOMIC = re.compile(r"os\.replace\s*\(")
RESUME = re.compile(r"os\.listdir\s*\(|glob\.glob\s*\(|os\.scandir\s*\(|os\.path\.isfile\s*\(")


def audit(path):
    """返回 (verdict, 说明列表)。verdict ∈ {PASS, FAIL, N/A}。"""
    try:
        src = open(path, encoding="utf-8", errors="replace").read()
    except OSError as exc:
        return "FAIL", ["读不到：%s" % exc]
    if not POOL.search(src):
        return "N/A", ["未使用池 map，不属长批脚本"]

    notes, bad = [], False
    if ATOMIC.search(src):
        notes.append("原子落盘 ✓ os.replace")
    else:
        notes.append("**无原子落盘**：崩溃点之前的机时会全部丢失")
        bad = True
    if RESUME.search(src):
        notes.append("续跑扫描 ✓")
    else:
        notes.append("**无续跑扫描**：重跑从零开始，无法接着算")
        bad = True

    m = POOL_CTOR.search(src)
    if m and m.group(1) and int(m.group(1)) > 14 and sys.platform.startswith("win"):
        notes.append("WARN worker=%s > 14（Windows 单路上限；多路时按路数均分）" % m.group(1))
    return ("FAIL" if bad else "PASS"), notes


def main():
    ap = argparse.ArgumentParser(description="长批次可恢复性门禁")
    ap.add_argument("paths", nargs="+", help="待检脚本（支持通配）")
    ap.add_argument("--out", default="结果/gates/G3-batch.md")
    ap.add_argument("--skip", action="append", default=[],
                    help="显式豁免，格式 文件名=理由；理由不得为空")
    a = ap.parse_args()

    exempt = {}
    for item in a.skip:
        if "=" not in item or not item.split("=", 1)[1].strip():
            print("--skip 必须写成 文件名=理由，且理由不得为空：%s" % item, file=sys.stderr)
            return 2
        name, reason = item.split("=", 1)
        exempt[name.strip()] = reason.strip()

    files = []
    for pattern in a.paths:
        files.extend(glob.glob(pattern))
    files = sorted(set(files))
    if not files:
        print("没有匹配到任何脚本——空检查记 fail，不是通过", file=sys.stderr)
        return 1

    rows, failed = [], 0
    for path in files:
        base = os.path.basename(path)
        if base in exempt:
            rows.append(("SKIP", path, "豁免：" + exempt[base]))
            continue
        verdict, notes = audit(path)
        rows.append((verdict, path, "；".join(notes)))
        if verdict == "FAIL":
            failed += 1

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("# 长批次可恢复性门禁\n\n检 %d 个脚本，FAIL %d\n\n" % (len(rows), failed))
        fh.write("| 判定 | 脚本 | 说明 |\n|---|---|---|\n")
        for verdict, path, note in rows:
            fh.write("| %s | `%s` | %s |\n" % (verdict, path.replace("\\", "/"), note))
    for verdict, path, note in rows:
        if verdict in ("FAIL", "SKIP"):
            print("%-4s %s  %s" % (verdict, path, note))
    print("检 %d 个脚本，FAIL %d → %s" % (len(rows), failed, a.out))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
