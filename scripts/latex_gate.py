#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LaTeX 编译门禁：把 .log 分成阻断项与非阻断项，核实页数与摘要页。

对应 references/paper-latex.md「编译契约与编译链」。只依赖标准库。

用法：
  python latex_gate.py 论文/main.log [--aux 论文/main.aux] [--whitelist 结果/编译白名单.md]
                       [--abstract-label abstract] [--json]

阻断项（退出码 1）：真实错误 `^!`、LaTeX Error、Undefined control sequence、
未定义引用/引文、缺文件/缺图、Float too large、Overfull \\hbox。
非阻断项：Underfull \\hbox、其他 warning —— 打印出来供白名单裁定。
"""
import argparse
import json
import os
import re
import sys

BLOCKING_PATTERNS = [
    (r"^! (.+)$", "真实错误"),
    (r"LaTeX Error: (.+)$", "LaTeX Error"),
    (r"Undefined control sequence", "未定义命令"),
    (r"Reference `([^']+)' on page \d+ undefined", "未定义引用"),
    (r"Citation `([^']+)' on page \d+ undefined", "未定义引文"),
    (r"There were undefined (?:references|citations)", "存在未定义引用/引文（汇总行）"),
    (r"File `([^']+)' not found", "缺文件"),
    (r"Missing character", "缺字形（字体未覆盖该字符）"),
    (r"Float too large", "浮动体过大"),
    (r"Overfull \\hbox \(([\d.]+)pt too wide\)", "Overfull hbox"),
]
NONBLOCKING_PATTERNS = [
    (r"Underfull \\hbox \(badness (\d+)\)", "Underfull hbox"),
    (r"LaTeX Warning: (.+)$", "LaTeX Warning"),
    (r"Package (\w+) Warning: (.+)$", "宏包 Warning"),
]


def parse_log(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    blocking, nonblocking = [], []
    for i, line in enumerate(lines, 1):
        for pat, kind in BLOCKING_PATTERNS:
            if re.search(pat, line):
                blocking.append({"line": i, "kind": kind, "text": line.strip()[:200]})
                break
        else:
            for pat, kind in NONBLOCKING_PATTERNS:
                if re.search(pat, line):
                    nonblocking.append({"line": i, "kind": kind, "text": line.strip()[:200]})
                    break
    pages = None
    m = re.search(r"Output written on .*?\((\d+) pages?", "\n".join(lines))
    if m:
        pages = int(m.group(1))
    return blocking, nonblocking, pages


def aux_pages(aux_path, abstract_label=None):
    """从 .aux 取标签页码，用于程序化核实摘要页数/正文起始页。"""
    if not aux_path or not os.path.exists(aux_path):
        return {}
    with open(aux_path, encoding="utf-8", errors="replace") as f:
        txt = f.read()
    labels = {}
    for m in re.finditer(r"\\newlabel\{([^}]+)\}\{\{([^}]*)\}\{([^}]*)\}", txt):
        labels[m.group(1)] = m.group(3)
    out = {"labels": labels}
    if abstract_label and abstract_label in labels:
        out["abstract_page"] = labels[abstract_label]
    return out


def load_whitelist(path):
    if not path or not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", errors="replace") as f:
        return [l.strip() for l in f if l.strip().startswith("-")]


def main(argv=None):
    ap = argparse.ArgumentParser(description="LaTeX 编译日志门禁")
    ap.add_argument("log")
    ap.add_argument("--aux")
    ap.add_argument("--abstract-label", default=None)
    ap.add_argument("--whitelist")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    blocking, nonblocking, pages = parse_log(a.log)
    aux = aux_pages(a.aux, a.abstract_label)
    wl = load_whitelist(a.whitelist)
    res = {"log": a.log, "pages": pages, "n_blocking": len(blocking), "n_nonblocking": len(nonblocking),
           "blocking": blocking, "nonblocking": nonblocking[:80],
           "whitelist_entries": len(wl), "aux": aux,
           "verdict": "FAIL" if blocking else "PASS"}
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(f"{a.log}: 阻断项 {len(blocking)}，非阻断项 {len(nonblocking)}，PDF 页数 {pages}")
        for b in blocking[:40]:
            print(f"  BLOCK L{b['line']} [{b['kind']}] {b['text']}")
        if len(blocking) > 40:
            print(f"  …其余 {len(blocking) - 40} 条")
        for b in nonblocking[:15]:
            print(f"  warn  L{b['line']} [{b['kind']}] {b['text']}")
        if len(nonblocking) > 15:
            print(f"  …其余 {len(nonblocking) - 15} 条非阻断项，逐条裁定后写入白名单")
        if "abstract_page" in aux:
            print(f"  摘要标签所在页：{aux['abstract_page']}（章程要求一页时据此核实）")
        print(f"判定：{res['verdict']}")
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
