#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""冻结账本工具：结构校验、stale 传播、numbers.tex 宏生成。

schema 见 references/computation-standards.md §7。只依赖标准库。

用法：
  python ledger.py --validate 结果/results_ledger.json
  python ledger.py --freeze   结果/results_ledger.json      # 记录依赖哈希并置 frozen
  python ledger.py --stale-check 结果/results_ledger.json [--write]
  python ledger.py --emit-tex 结果/results_ledger.json -o 论文/numbers.tex

退出码：0 全过；1 有 FAIL（校验不过 / 存在 stale 条目）。
"""
import argparse
import hashlib
import json
import os
import re
import sys

REQUIRED = ["value", "unit", "display", "role", "source", "status"]
ROLES = {"authoritative", "cross_check", "intermediate"}
DIGITS = {"0": "Zero", "1": "One", "2": "Two", "3": "Three", "4": "Four",
          "5": "Five", "6": "Six", "7": "Seven", "8": "Eight", "9": "Nine"}


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path: str) -> dict:
    # utf-8-sig：Windows 下 PowerShell/记事本写的 JSON 常带 BOM
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def save(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def macro_name(key: str, entry: dict) -> str:
    """由 macro 字段或键名派生合法 LaTeX 宏名（纯字母）。"""
    m = entry.get("macro")
    if m:
        return m.lstrip("\\")
    parts = [p for p in re.split(r"[^0-9A-Za-z]+", key) if p]
    out = []
    for i, p in enumerate(parts):
        p = "".join(DIGITS.get(ch, ch) for ch in p)
        out.append(p if i == 0 else p[:1].upper() + p[1:])
    name = "".join(out)
    return name if name and name[0].isalpha() else "num" + name


def tex_escape(s: str) -> str:
    return (str(s).replace("\\", r"\textbackslash{}").replace("%", r"\%")
            .replace("&", r"\&").replace("#", r"\#").replace("_", r"\_"))


def validate(led: dict, warnings: list = None) -> list:
    """返回 FAIL 级问题列表（空 = 通过）；R5 相关的可降级项写进 warnings。"""
    problems = []
    if warnings is None:
        warnings = []
    seen_authoritative = {}
    for key, e in led.items():
        where = f"[{key}]"
        if not isinstance(e, dict):
            problems.append(f"{where} 不是对象"); continue
        for f in REQUIRED:
            if f not in e:
                problems.append(f"{where} 缺必填字段 {f}")
        role = e.get("role")
        if role not in ROLES:
            problems.append(f"{where} role 必须是 {sorted(ROLES)} 之一，当前 {role!r}")
        src = e.get("source", {})
        if isinstance(src, dict):
            for f in ("script", "params"):
                if not src.get(f):
                    problems.append(f"{where} source.{f} 为空（数字必须可追溯到脚本与参数）")
            # file/field 是三向审计能真正回读复算的前提；缺了审计会退化成"只比宏和账本"
            if role in ("authoritative", "cross_check") and not src.get("file"):
                problems.append(f"{where} source.file 为空：审计无法从磁盘结果文件回读复算，"
                                "三向审计退化为两向（R6）")
            if role == "authoritative" and not src.get("field"):
                problems.append(f"{where} source.field 为空：无法定位该数字在结果文件中的位置（R6）")
            elif role == "cross_check" and not src.get("field"):
                warnings.append(f"{where} source.field 为空，互证值只能人工核对")
        else:
            problems.append(f"{where} source 必须是对象")
        if e.get("status") not in {"frozen", "stale", "draft"}:
            problems.append(f"{where} status 必须是 frozen/stale/draft")
        if role == "authoritative":
            q = e.get("quantity", key)
            if q in seen_authoritative:
                problems.append(f"{where} 与 [{seen_authoritative[q]}] 对同一被问量 {q!r} 都标了 authoritative"
                                "（唯一权威答案：只能留一条，其余标 cross_check）")
            seen_authoritative[q] = key
        cert = e.get("certificate")
        if cert is None and role == "authoritative":
            warnings.append(f"{where} 权威答案没有 certificate 块：R2 未判定。若该结论含"
                            "「满足/可行/达标/最优」主张，按 R2 判 fail；纯描述性数字才可无证书")
        if cert is not None:
            if "pass" not in cert:
                problems.append(f"{where} certificate 缺 pass 字段")
            elif cert.get("pass") is not True and role == "authoritative":
                problems.append(f"{where} 证书未达标（pass=false）却作为权威答案——不得进论文")
            if not cert.get("family"):
                problems.append(f"{where} certificate.family 未写（须与 R2 家族映射表对齐）")
            # R5「已分辨」是可降级项：缺字段或未分辨都不判 fail，但必须被看见
            if role == "authoritative":
                if "resolved" not in cert:
                    warnings.append(f"{where} certificate 缺 delta/u/resolved：R5 的 u ≤ Δ/3 未做判定"
                                    "（跑 certify.py 时带上 --delta）")
                elif cert.get("resolved") is not True:
                    warnings.append(f"{where} 证书达标但**未分辨**（u > Δ/3）：结论必须降到下一档精度，"
                                    "并在 结果/降级声明.md 记录，禁止报满精度")
        # display 与 value 的一致性：display 里的第一个数应与 value 四舍五入一致
        d = str(e.get("display", ""))
        m = re.search(r"-?\d+(?:\.\d+)?", d.replace(",", ""))
        v = e.get("value")
        if m and isinstance(v, (int, float)):
            shown = float(m.group())
            dec = len(m.group().split(".")[1]) if "." in m.group() else 0
            # display 带 % 时，value 可能已是百分数（unit="%"）或仍是比例（unit="1"）。
            # 只有后者才需要乘 100——按 unit 判，别一律缩放。
            unit = str(e.get("unit", "")).strip()
            scale = 100.0 if ("%" in d and unit not in ("%", "percent", "pct")) else 1.0
            if abs(round(v * scale, dec) - shown) > 10 ** (-dec) / 2 + 1e-12:
                problems.append(f"{where} display {d!r} 与 value {v} 对不上（显示精度只由 display 决定，"
                                "但不得与 value 矛盾）")
    return problems


def depends_state(entry: dict, base: str):
    """返回 (当前哈希字典, 变化说明列表)。"""
    cur, notes = {}, []
    for dep in entry.get("depends_on", []) or []:
        p = dep if os.path.isabs(dep) else os.path.join(base, dep)
        if not os.path.exists(p):
            notes.append(f"依赖不存在：{dep}")
            cur[dep] = None
        else:
            cur[dep] = sha256(p)
    return cur, notes


def cmd_freeze(path: str) -> int:
    led = load(path)
    base = os.path.dirname(os.path.abspath(path)) or "."
    base = os.path.dirname(base) if os.path.basename(base) == "结果" else base
    missing = 0
    for key, e in led.items():
        cur, notes = depends_state(e, base)
        for n in notes:
            print(f"[{key}] {n}"); missing += 1
        e["depends_hash"] = cur
        e["status"] = "frozen"
    save(path, led)
    print(f"已冻结 {len(led)} 条；依赖缺失 {missing} 项")
    return 1 if missing else 0


def cmd_stale(path: str, write: bool) -> int:
    led = load(path)
    base = os.path.dirname(os.path.abspath(path)) or "."
    base = os.path.dirname(base) if os.path.basename(base) == "结果" else base
    stale = []
    for key, e in led.items():
        cur, notes = depends_state(e, base)
        old = e.get("depends_hash")
        if old is None and e.get("depends_on"):
            stale.append((key, "未记录依赖哈希（先跑 --freeze）"))
        elif old is not None and cur != old:
            changed = [d for d in set(list(cur) + list(old)) if cur.get(d) != old.get(d)]
            stale.append((key, "依赖已变更：" + ", ".join(changed)))
        for n in notes:
            stale.append((key, n))
    for key, why in stale:
        print(f"STALE [{key}] {why}")
        if write:
            led[key]["status"] = "stale"
    if write and stale:
        save(path, led)
    print(f"stale 条目 {len(stale)} / {len(led)}")
    return 1 if stale else 0


def cmd_emit_tex(path: str, out: str) -> int:
    led = load(path)
    lines = ["% 本文件由 scripts/ledger.py --emit-tex 从 results_ledger.json 生成，请勿手改。",
             "% 正文只引用这里的宏；改数字请改账本后重新生成。", ""]
    used = {}
    for key, e in sorted(led.items()):
        if e.get("role") == "intermediate":
            continue
        name = macro_name(key, e)
        if name in used:
            print(f"宏名冲突：{key} 与 {used[name]} 都派生出 \\{name}，请显式写 macro 字段", file=sys.stderr)
            return 1
        used[name] = key
        stale_mark = "  % STALE：不得引用" if e.get("status") == "stale" else ""
        lines.append(f"\\newcommand{{\\{name}}}{{{tex_escape(e.get('display'))}}}{stale_mark}")
        cert = e.get("certificate") or {}
        for suffix, field in (("Bound", "bound"), ("Upper", "upper"), ("N", "n"),
                              ("Threshold", "threshold"), ("Gap", "gap"),
                              ("Seed", "seed"), ("Verdict", "verdict"),
                              ("Alpha", "alpha"), ("Method", "method")):
            if field in cert and cert[field] is not None:
                lines.append(f"\\newcommand{{\\{name}{suffix}}}{{{tex_escape(cert[field])}}}")
        # 整段证书宏：正文写 \qOneThresholdCert 即可带出「n=… ，方法 95% 下界 … ≥ 阈值」，
        # 免得作者只贴点估计而把证书忘在结果目录里（历史上摘要漏下界就是这么来的）。
        if cert.get("bound") is not None and cert.get("threshold") is not None:
            _v = {"feasible": "达标", "excluded": "已排除", "inconclusive": "证据不足"}.get(
                str(cert.get("verdict", "")), "")
            _parts = []
            if cert.get("n") is not None:
                _parts.append(f"n={tex_escape(cert['n'])}")
            _m = str(cert.get("method", "")) or "单侧"
            _parts.append(f"{tex_escape(_m)} 下界 {tex_escape(cert['bound'])}")
            _parts.append(f"阈值 {tex_escape(cert['threshold'])}")
            if _v:
                _parts.append(_v)
            lines.append(f"\\newcommand{{\\{name}Cert}}{{（{'，'.join(_parts)}）}}")
        if e.get("unit") and e["unit"] != "1":
            lines.append(f"\\newcommand{{\\{name}Unit}}{{{tex_escape(e['unit'])}}}")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"已写出 {out}：{len(used)} 个主宏")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="results_ledger.json 校验 / 冻结 / stale / 宏生成")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--validate", metavar="LEDGER")
    g.add_argument("--freeze", metavar="LEDGER")
    g.add_argument("--stale-check", metavar="LEDGER")
    g.add_argument("--emit-tex", metavar="LEDGER")
    ap.add_argument("-o", "--out", default="论文/numbers.tex")
    ap.add_argument("--write", action="store_true", help="stale-check 时把状态写回账本")
    a = ap.parse_args(argv)

    if a.validate:
        warns = []
        problems = validate(load(a.validate), warns)
        for p in problems:
            print("FAIL " + p)
        for w in warns:
            print("WARN " + w)
        print(f"校验完成：FAIL {len(problems)}，WARN {len(warns)}"
              "（FAIL 必须清零；WARN 是可降级或须人工处置项，进 P6 前逐条给处置结论）")
        return 1 if problems else 0
    if a.freeze:
        return cmd_freeze(a.freeze)
    if a.stale_check:
        return cmd_stale(a.stale_check, a.write)
    return cmd_emit_tex(a.emit_tex, a.out)


if __name__ == "__main__":
    sys.exit(main())
