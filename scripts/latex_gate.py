#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LaTeX 编译门禁：把 .log 分成阻断项与非阻断项，核实页数与摘要页。

对应 assets/paper/ 各分节顶部的写作合同与 workflows/latex-fix.md。只依赖标准库。

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

from openconf import load

BLOCKING_PATTERNS = [
    (r"^! (.+)$", "真实错误"),
    (r"LaTeX Error: (.+)$", "LaTeX Error"),
    (r"Undefined control sequence", "未定义命令"),
    (r"Reference `([^']+)' on page \d+ undefined", "未定义引用"),
    (r"Citation `([^']+)' on page \d+ undefined", "未定义引文"),
    (r"There were undefined (?:references|citations)", "存在未定义引用/引文（汇总行）"),
    (r"File `([^']+)' not found", "缺文件"),
    (r"\[NUMBERS-MISSING\]", "数字宏未注入：先跑 ledger.py --emit-tex 生成 numbers.tex"),
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
    import os as _os
    if not _os.path.exists(path):
        return [], [], None
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


def pdf_page_count(pdf_path):
    """直接数 PDF 页数。比解析日志可靠——日志格式随引擎/latexmk 版本变。"""
    if not pdf_path or not os.path.exists(pdf_path):
        return None
    try:
        import pypdf
        return len(pypdf.PdfReader(pdf_path).pages)
    except Exception:
        pass
    try:
        from PyPDF2 import PdfReader
        return len(PdfReader(pdf_path).pages)
    except Exception:
        return None


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


def bib_missing(tex_path):
    """参考文献节存在性(实测:交付物可以整篇没有参考文献)。

    沿 \\input/\\include 递归收集源文本,查
    \\bibliography / \\thebibliography / 参考文献 任一出现即算有。
    """
    import os as _os
    seen, texts = set(), []
    base = _os.path.dirname(_os.path.abspath(tex_path))

    def walk(p):
        ap = _os.path.abspath(p)
        if ap in seen or not _os.path.exists(ap):
            return
        seen.add(ap)
        try:
            t = open(ap, encoding="utf-8", errors="replace").read()
        except OSError:
            return
        texts.append(t)
        for m in re.finditer(r"\\(?:input|include)\{([^}]+)\}", t):
            cand = m.group(1)
            for ext in ("", ".tex"):
                walk(_os.path.join(base, cand + ext))

    walk(tex_path)
    blob = "\n".join(texts).replace("\\n", "")
    # 子串判定,不用正则:thebibliography 在 \begin{thebibliography} 里前面是 {,
    # 对带反斜杠前缀的命令做子串判定，避免正则转义造成假阳性。
    has_bib = ("thebibliography" in blob
               or "参考文献" in blob
               or "bibliography{" in blob
               or "\\bibliography{" in blob)
    return not has_bib


def opening_config_int(explicit_value, key):
    if explicit_value is not None:
        return explicit_value
    try:
        value = load(key)
        if isinstance(value, bool):
            raise ValueError(key)
        return int(value)
    except (OSError, ValueError, TypeError, KeyError):
        raise SystemExit(f"请在 开题.md 填写 {key}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="LaTeX 编译日志门禁")
    ap.add_argument("log")
    ap.add_argument("--aux")
    ap.add_argument("--abstract-label", default=None)
    ap.add_argument("--whitelist")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--pdf", default=None,
                    help="编译出的 PDF。给了就以它为页数权威来源（日志格式不可靠）。")
    ap.add_argument("--min-pages", type=int, default=None,
                    help="总页数下限。未传参时读取 开题.md 的“总页数下限”。")
    ap.add_argument("--appendix-label", default=None,
                    help="附录起始处的 \\label 名。给了就据此算正文页数并检查 --max-body-pages。")
    ap.add_argument("--max-body-pages", type=int, default=None,
                    help="正文页数上限。未传参时读取 开题.md 的“正文页数上限”；"
                         "仅在给了 --appendix-label 时生效。")
    ap.add_argument("--tex", default=None,
                    help="主 tex 源路径。给了就做结构检查：参考文献节存在性"
                         "（实测：整篇交付可以零参考文献）。")
    a = ap.parse_args(argv)
    a.min_pages = opening_config_int(a.min_pages, "总页数下限")
    a.max_body_pages = opening_config_int(a.max_body_pages, "正文页数上限")
    a.abstract_pages = (opening_config_int(None, "摘要页数")
                        if a.abstract_label else None)

    blocking, nonblocking, pages = parse_log(a.log)
    pages_src = "log"
    n_pdf = pdf_page_count(a.pdf)
    if n_pdf is not None:
        if pages is not None and pages != n_pdf:
            blocking.append({"line": 0, "kind": "volume",
                             "text": f"日志说 {pages} 页、PDF 实为 {n_pdf} 页：日志与产物不符，"
                                     "多半是拿旧日志配新 PDF（或反之），门禁失去意义"})
        pages, pages_src = n_pdf, "pdf"
    aux = aux_pages(a.aux, a.abstract_label)
    if a.tex:
        if bib_missing(a.tex):
            blocking.append({"line": 0, "kind": "no-bib",
                             "text": "全文无参考文献节——赛制硬要求"
                                     "（实测：整篇交付零参考文献）"})
    wl = load_whitelist(a.whitelist)

    # ---- 体量地板：写成散文的「要丰富」无效，只有退出码算数 ----
    volume = []
    if pages is None:
        volume.append("页数无法判定：日志里没有 \"Output written on … (N pages)\" 行，"
                      "也没给 --pdf。门禁核不到要核的量就不能算通过——"
                      "请补 --pdf 论文/main.pdf")
    elif pages < a.min_pages:
        volume.append(f"总页数 {pages} < 下限 {a.min_pages}：附录没做够。"
                      f"竞赛规范不限附录页数，补充图表/源程序/附件说明/推导细节都该进去。")
    body_pages = None
    if a.appendix_label:
        lab = aux.get("labels", {}).get(a.appendix_label)
        if lab:
            try:
                body_pages = int(str(lab).strip())
            except ValueError:
                body_pages = None
        if body_pages is None:
            volume.append(f"给了 --appendix-label {a.appendix_label} 但 .aux 里取不到其页码，"
                          "正文页数未核实")
        elif body_pages - 1 > a.max_body_pages:
            volume.append(f"正文 {body_pages - 1} 页 > 上限 {a.max_body_pages}："
                          "超出竞赛格式规范，把明细表/长推导移进附录")
    if a.abstract_label:
        abstract_page = aux.get("labels", {}).get(a.abstract_label)
        if abstract_page is None:
            volume.append(f"给了 --abstract-label {a.abstract_label} 但 .aux 里找不到该 label，"
                          "摘要页数未核实")
        else:
            try:
                abstract_page_number = int(str(abstract_page).strip())
            except ValueError:
                volume.append(f"摘要 label {a.abstract_label} 的页码无效：{abstract_page!r}")
            else:
                if abstract_page_number != a.abstract_pages:
                    volume.append(f"摘要页数 {abstract_page_number} != 开题.md 声明的 "
                                  f"{a.abstract_pages}（label {a.abstract_label}）")
    blocking = blocking + [{"line": 0, "kind": "volume", "text": m} for m in volume]
    res = {"log": a.log, "pages": pages, "body_pages": body_pages,
           "min_pages": a.min_pages, "max_body_pages": a.max_body_pages,
           "abstract_pages": a.abstract_pages,
           "n_blocking": len(blocking), "n_nonblocking": len(nonblocking),
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
