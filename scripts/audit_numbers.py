#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""三向一致性审计：论文 tex <-> results_ledger.json <-> 磁盘结果文件。

对应 references/algorithm-redlines.md R6 与 computation-standards §7。只依赖标准库。

用法：
  python audit_numbers.py --ledger 结果/results_ledger.json --numbers 论文/numbers.tex \
      --tex 论文/main.tex --root . --out 结果/审计报告.md

逐条检查（FAIL 会让退出码为 1）：
  1. status 必须 frozen（stale 条目不得回填论文）
  2. certificate.pass 为 false 的条目不得作为权威答案
  3. source.file 必须存在；能解析 source.field 时回读原始文件复算比对
  4. 每条非 intermediate 记录必须在 numbers.tex 里有宏
  5. authoritative 宏未被正文引用 → WARN（数字白算了或论文漏引）
  6. 正文中未走宏的可疑数字 → WARN 清单，逐条人工裁定（应改宏 / 已核对无误）

source.field 支持的写法：
  JSON: "a.b.c"、"a.b[2].c"
  CSV : "列名@行号(0基)"、"列名[键列=键值]"
"""
import argparse
import csv
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ledger import macro_name  # noqa: E402  # 与 --emit-tex 共用宏名派生规则

SKIP_CMDS = r"(?:label|ref|eqref|cite|includegraphics|newcommand|renewcommand|input|include|usepackage|documentclass|setlength|hspace|vspace|url|href|pageref|autoref|caption\*?)"


def load_json(path):
    # utf-8-sig：兼容 Windows 工具链写出的带 BOM JSON
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def read_text(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def lookup_json(obj, field):
    cur = obj
    for tok in re.findall(r"[^.\[\]]+|\[\d+\]", field):
        if tok.startswith("["):
            cur = cur[int(tok[1:-1])]
        else:
            cur = cur[tok]
    return cur


def lookup_csv(path, field):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    m = re.fullmatch(r"([^@\[]+)@(\d+)", field)
    if m:
        return rows[int(m.group(2))][m.group(1).strip()]
    m = re.fullmatch(r"([^\[]+)\[([^=]+)=([^\]]+)\]", field)
    if m:
        col, kcol, kval = (s.strip() for s in m.groups())
        for r in rows:
            if str(r.get(kcol, "")).strip() == kval:
                return r[col]
        raise KeyError(f"找不到 {kcol}={kval}")
    raise ValueError("无法解析 source.field")


def reread_value(root, src):
    """回读原始结果文件里的值；返回 (值 or None, 说明)。"""
    f = src.get("file")
    if not f:
        return None, "source.file 未写，无法回读"
    p = f if os.path.isabs(f) else os.path.join(root, f)
    if not os.path.exists(p):
        return None, f"FAIL 结果文件不存在：{f}"
    field = src.get("field")
    if not field:
        return None, "source.field 未写，只核实了文件存在"
    try:
        raw = lookup_json(load_json(p), field) if p.lower().endswith(".json") else lookup_csv(p, field)
        return float(raw), ""
    except Exception as exc:  # noqa: BLE001 - 回读失败降级为人工核对
        return None, f"回读失败（{type(exc).__name__}: {exc}），需人工核对"


def macros_defined(numbers_tex):
    if not os.path.exists(numbers_tex):
        return {}
    txt = read_text(numbers_tex)
    return {m.group(1): m.group(2) for m in
            re.finditer(r"\\newcommand\{\\([A-Za-z]+)\}\{(.*?)\}\s*(?:%.*)?$", txt, re.M)}


INPUT_RE = None  # 延迟编译，见 expand_inputs


def expand_inputs(paths, seen=None, depth=0):
    """把 \\input / \\include 递归展开成实际文件列表。

    分节论文的 main.tex 里几乎只有 \\input，不展开就等于什么都没审——
    这是分节结构下最容易出现的假阴性（loop2-r1 跑题者实测反馈）。
    """
    import re as _re
    global INPUT_RE
    if INPUT_RE is None:
        INPUT_RE = _re.compile(r"(?<!%)" + "\\\\" + r"(?:input|include)\s*\{([^}]+)\}")
    if seen is None:
        seen = []
    if depth > 8:
        return seen
    for path in paths:
        path = os.path.normpath(path)
        if path in seen or not os.path.exists(path):
            if path not in seen and not os.path.exists(path):
                print(f"警告：{path} 不存在，已跳过", file=sys.stderr)
            continue
        seen.append(path)
        try:
            txt = read_text(path)
        except Exception:
            continue
        base = os.path.dirname(path)
        children = []
        for m in INPUT_RE.finditer(strip_comments(txt)):
            name = m.group(1).strip()
            cand = name if name.endswith(".tex") else name + ".tex"
            children.append(os.path.join(base, cand))
        expand_inputs(children, seen, depth + 1)
    return seen


def strip_comments(tex):
    return re.sub(r"(?<!\\)%.*", "", tex)


def suspicious_numbers(tex_files, macro_names):
    """正文里未走宏的可疑数字（有小数点或 ≥3 位整数），排除年份、命令参数、numbers 宏。"""
    hits = []
    for path in tex_files:
        txt = strip_comments(read_text(path))
        txt = re.sub(r"\\" + SKIP_CMDS + r"\s*(\[[^\]]*\])?\s*\{[^{}]*\}", " ", txt)
        for i, line in enumerate(txt.splitlines(), 1):
            if re.search(r"\\(?:begin|end)\{", line):
                continue
            for m in re.finditer(r"(?<![\\A-Za-z0-9._-])(\d+\.\d+|\d{3,})(?![0-9])", line):
                tok = m.group(1)
                if re.fullmatch(r"(19|20)\d{2}", tok):
                    continue
                hits.append((path, i, tok, line.strip()[:110]))
    return hits


def audit(ledger_path, numbers_tex, tex_files, root, out_path, tol=1e-6):
    led = load_json(ledger_path)
    macros = macros_defined(numbers_tex)
    body = "\n".join(read_text(p) for p in tex_files)
    rows, n_fail, n_warn = [], 0, 0

    for key, e in sorted(led.items()):
        if e.get("role") == "intermediate":
            continue
        verdict, notes = "PASS", []
        if e.get("status") != "frozen":
            verdict = "FAIL"; notes.append(f"status={e.get('status')}（stale/draft 不得进论文）")
        cert = e.get("certificate")
        if cert is not None and cert.get("pass") is not True and e.get("role") == "authoritative":
            verdict = "FAIL"; notes.append("证书未达标却作为权威答案")
        if cert is not None and e.get("role") == "authoritative":
            if "resolved" not in cert:
                notes.append("WARN R5 未判：certificate 缺 delta/u/resolved"); n_warn += 1
            elif cert.get("resolved") is not True:
                notes.append("WARN 达标但未分辨（u > Δ/3）：正文措辞必须降到下一档精度并记入降级声明")
                n_warn += 1
        val, note = reread_value(root, e.get("source", {}) or {})
        if val is None:
            # 回读没发生 = 这条没被真正审计过；权威答案不许这样蒙混
            reason = note[5:] if note.startswith("FAIL") else (note or "未回读")
            if e.get("role") == "authoritative":
                verdict = "FAIL"
                notes.append(f"无法回读复算（{reason}）：三向审计对该条退化为两向，R6 不接受")
            else:
                notes.append(f"WARN 无法回读复算（{reason}），须人工核对"); n_warn += 1
        else:
            v = e.get("value")
            if isinstance(v, (int, float)) and abs(val - v) > max(tol, abs(v) * tol):
                verdict = "FAIL"; notes.append(f"回读值 {val} ≠ 账本值 {v}")
            else:
                notes.append("回读值一致")
        name = (e.get("macro") or "").lstrip("\\") or macro_name(key, e)
        if name not in macros:
            verdict = "FAIL"; notes.append(f"numbers.tex 缺宏 \\{name}（论文数字未走单向流）")
        elif not re.search(r"\\" + re.escape(name) + r"(?![A-Za-z])", body):
            if e.get("role") == "authoritative":
                notes.append("宏已定义但正文未引用")
                n_warn += 1
        rows.append((key, e.get("role"), e.get("display"), verdict, "；".join(notes) or "-"))
        if verdict == "FAIL":
            n_fail += 1

    sus = suspicious_numbers(tex_files, set(macros))
    lines = ["# 三向一致性审计报告", "",
             f"- 账本：`{ledger_path}`；宏文件：`{numbers_tex}`；正文：{', '.join('`%s`' % t for t in tex_files)}",
             f"- 结论：**{'FAIL' if n_fail else 'PASS'}**（FAIL {n_fail} 条，WARN {n_warn} 条，待裁定裸数字 {len(sus)} 处）",
             "", "## 逐条判定", "",
             "| ledger 键 | role | 论文显示值 | 判定 | 说明 |", "|---|---|---|---|---|"]
    for r in rows:
        lines.append("| " + " | ".join(str(x) for x in r) + " |")
    lines += ["", "## 正文中未走宏的数字（逐条裁定：应改宏 / 已核对无误 / 非结果数字）", ""]
    if not sus:
        lines.append("无。")
    else:
        lines.append("| 文件 | 行 | 数字 | 上下文 |")
        lines.append("|---|---|---|---|")
        for path, i, tok, ctx in sus[:60]:
            safe_ctx = ctx.replace("|", r"\|")
            lines.append(f"| {os.path.basename(path)} | {i} | {tok} | `{safe_ctx}` |")
        if len(sus) > 60:
            lines.append(f"| … | | | 其余 {len(sus) - 60} 处见脚本重跑输出 |")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"审计完成：FAIL {n_fail}，WARN {n_warn}，待裁定裸数字 {len(sus)} → {out_path}")
    return 1 if n_fail else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="论文 <-> 账本 <-> 结果文件 三向审计")
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--numbers", default="论文/numbers.tex")
    ap.add_argument("--tex", nargs="+", required=True)
    ap.add_argument("--no-expand", action="store_true",
                    help="不递归展开 input/include（默认展开；分节论文必须展开）")
    ap.add_argument("--root", default=".", help="source.file 的相对路径根目录")
    ap.add_argument("--out", default="结果/审计报告.md")
    a = ap.parse_args(argv)
    tex_files = a.tex if a.no_expand else expand_inputs(a.tex)
    if not a.no_expand and len(tex_files) > len(a.tex):
        print(f"已递归展开 input/include：{len(a.tex)} -> {len(tex_files)} 个 tex 文件")
    return audit(a.ledger, a.numbers, tex_files, a.root, a.out)


if __name__ == "__main__":
    sys.exit(main())
