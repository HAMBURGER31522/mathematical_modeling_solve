#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图面自动质检 + contact sheet 导出（G5 硬项的可执行部分）。

对应 references/figure-style.md 与 workflows/solve-full.md P5。位图检查需要 Pillow（缺失时自动降级为
文件级检查并在报告里写明，不静默跳过）；矢量图（PDF/SVG）只做文件级与引用检查。

用法：
  python figqa.py 图/ --tex 论文/main.tex --out 结果/figqa.json --contact 图/_contact.png

检查项：
  - 空图/近空白（像素标准差过低）
  - 重复图（内容哈希相同）
  - 位图分辨率与最小边像素数、文件体积异常（过小=可能是空框）
  - 是否被正文 \\includegraphics 引用（未引用 → 必须移附录或删）
  - 导出 contact sheet 供一屏目检（人工逐张记录仍是 G5 必需）
退出码：0 无 FAIL；1 有 FAIL。
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sys

from openconf import load

RASTER = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
VECTOR = {".pdf", ".svg", ".eps"}
MIN_BYTES = 3000          # 小于此体积的图基本是空框
MIN_SIDE = 600            # 位图最小边像素（约 300dpi 下 2 英寸）
BLANK_STD = 2.0           # 灰度标准差低于此值判近空白


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _expand_inputs(paths, seen=None, depth=0):
    """递归展开 \\input / \\include。

    分节论文的 main.tex 里几乎只有 \\input，不展开就会一张图都找不到，
    于是"正文一张图都没引用"这条硬门禁会对完全正常的交付物误判（CR 实测指出）。
    """
    if seen is None:
        seen = []
    if depth > 8:
        return seen
    for path in paths:
        path = os.path.normpath(path)
        if path in seen or not os.path.exists(path):
            continue
        seen.append(path)
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                txt = f.read()
        except Exception:
            continue
        txt = re.sub(r"(?<!\\)%.*", "", txt)
        base = os.path.dirname(path)
        kids = []
        for m in re.finditer(r"\\(?:input|include)\s*\{([^}]+)\}", txt):
            name = m.group(1).strip()
            kids.append(os.path.join(base, name if name.endswith(".tex") else name + ".tex"))
        _expand_inputs(kids, seen, depth + 1)
    return seen


def referenced_figures(tex_paths):
    tex_paths = expand_tex_paths(tex_paths)
    used = set()
    for p in _expand_inputs(list(tex_paths)):
        with open(p, encoding="utf-8", errors="replace") as f:
            txt = f.read()
        txt = re.sub(r"(?<!\\)%.*", "", txt)
        for m in re.finditer(r"\\includegraphics\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}", txt):
            used.add(os.path.basename(m.group(1).strip()).lower())
    return used


def expand_tex_paths(paths):
    """Expand wildcard and directory arguments on every shell, including PowerShell."""
    expanded = []
    for raw in paths:
        if os.path.isdir(raw):
            matches = glob.glob(os.path.join(raw, "*.tex"))
        else:
            matches = glob.glob(raw)
        expanded.extend(matches or [raw])
    seen = set()
    result = []
    for path in expanded:
        path = os.path.normpath(path)
        if path not in seen:
            seen.add(path)
            result.append(path)
    return result


def raster_stats(path):
    """返回 (宽, 高, 灰度标准差) 或 None（Pillow 不可用/读失败）。"""
    try:
        from PIL import Image, ImageStat
    except ImportError:
        return None
    try:
        with Image.open(path) as im:
            w, h = im.size
            stat = ImageStat.Stat(im.convert("L"))
            return w, h, stat.stddev[0]
    except Exception:  # noqa: BLE001
        return None


def contact_sheet(images, out_path, cols=4, thumb=320):
    try:
        from PIL import Image
    except ImportError:
        return "Pillow 不可用，contact sheet 未导出——必须改为人工逐张目检并在图面质检.md 记录"
    if not images:
        return "无位图可拼"
    thumbs = []
    for p in images:
        try:
            with Image.open(p) as im:
                im = im.convert("RGB")
                im.thumbnail((thumb, thumb))
                thumbs.append((os.path.basename(p), im.copy()))
        except Exception:  # noqa: BLE001
            continue
    if not thumbs:
        return "位图全部读取失败"
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * thumb, rows * thumb), "white")
    for i, (_, im) in enumerate(thumbs):
        x = (i % cols) * thumb + (thumb - im.width) // 2
        y = (i // cols) * thumb + (thumb - im.height) // 2
        sheet.paste(im, (x, y))
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    sheet.save(out_path)
    return f"已导出 {len(thumbs)} 张缩略图 → {out_path}"


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
    ap = argparse.ArgumentParser(description="图面自动质检与 contact sheet")
    ap.add_argument("figdir")
    ap.add_argument("--tex", nargs="*", default=[], help="正文 tex，用于检查图是否被引用")
    ap.add_argument("--out", default="结果/figqa.json")
    ap.add_argument("--contact", default="图/_contact.png")
    ap.add_argument("--draft", action="store_true",
                    help="骨架阶段：把图未被正文引用与体量地板降级为 WARN；成稿与 G5 门禁不得加此开关")
    ap.add_argument("--min-figures", type=int, default=None,
                    help="图总数下限。未传参时读取 开题.md 的“图总数下限”。")
    ap.add_argument("--min-body-figures", type=int, default=None,
                    help="正文（\\includegraphics 实际引用）图数下限。未传参时读取"
                         " 开题.md 的“正文引用图下限”。")
    a = ap.parse_args(argv)
    a.min_figures = opening_config_int(a.min_figures, "图总数下限")
    a.min_body_figures = opening_config_int(a.min_body_figures, "正文引用图下限")

    used = referenced_figures(a.tex) if a.tex else set()
    contact_abs = os.path.abspath(a.contact)
    files, skipped = [], []
    for root, _dirs, names in os.walk(a.figdir):
        for n in sorted(names):
            ext = os.path.splitext(n)[1].lower()
            if ext not in RASTER | VECTOR:
                continue
            p = os.path.join(root, n)
            if os.path.abspath(p) == contact_abs:   # 只跳过本脚本自己生成的 contact sheet
                skipped.append(os.path.relpath(p, a.figdir).replace("\\", "/"))
                continue
            files.append(p)

    by_hash, results, n_fail, n_warn = {}, [], 0, 0
    for p in files:
        ext = os.path.splitext(p)[1].lower()
        size = os.path.getsize(p)
        rec = {"file": os.path.relpath(p, a.figdir).replace("\\", "/"), "bytes": size,
               "kind": "raster" if ext in RASTER else "vector", "checks": {}, "fail": [], "warn": []}
        if size < MIN_BYTES:
            rec["fail"].append(f"文件仅 {size} 字节，疑似空图/空框")
        h = sha256_file(p)
        rec["sha256"] = h[:16]
        if h in by_hash:
            rec["fail"].append(f"与 {by_hash[h]} 内容完全相同（重复图）")
        else:
            by_hash[h] = rec["file"]
        if ext in RASTER:
            st = raster_stats(p)
            if st is None:
                rec["warn"].append("Pillow 不可用或读取失败：分辨率/空白检查未执行，须人工目检")
            else:
                w, hgt, std = st
                rec["checks"].update({"width": w, "height": hgt, "gray_std": round(std, 3)})
                if min(w, hgt) < MIN_SIDE:
                    rec["fail"].append(f"最小边 {min(w, hgt)}px < {MIN_SIDE}px（印刷会糊）")
                if std < BLANK_STD:
                    rec["fail"].append(f"灰度标准差 {std:.2f} 过低，疑似空白图")
        if a.tex and os.path.basename(p).lower() not in used and \
                os.path.splitext(os.path.basename(p))[0].lower() not in {os.path.splitext(u)[0] for u in used}:
            msg = ("未被正文 \\includegraphics 引用：图做出来却没进论文＝论证链断了。"
                   "要么在正文引用并配解读段，要么移进补充图表附录并在正文指路，要么删除。")
            (rec["warn"] if a.draft else rec["fail"]).append(msg)
        n_fail += len(rec["fail"]); n_warn += len(rec["warn"])
        results.append(rec)

    top_warn, top_fail = [], []
    available = set()
    for p in files:
        name = os.path.basename(p).lower()
        available.add(name)
        available.add(os.path.splitext(name)[0])
    missing_refs = sorted(u for u in used if u not in available)
    if a.tex and missing_refs:
        top_fail.append("正文引用但图文件不存在：" + ", ".join(missing_refs))
        n_fail += 1
    if a.tex and not used:
        m = "正文一张图都没引用（\\includegraphics 为 0）"
        if a.draft:
            top_warn.append(m + "：骨架阶段正常，成稿阶段即 G5 fail"); n_warn += 1
        else:
            top_fail.append(m + "：成稿阶段 G5 fail"); n_fail += 1
    if len(files) < a.min_figures:
        m = (f"图总数 {len(files)} < 下限 {a.min_figures}：图表维会被直接判 0 分。"
             "每问 ≥2 张正文图（现象/结果各一）+ 检验章 ≥2 张（收敛、灵敏度）"
             "+ 补充图表附录 ≥4 张，是够到高分档的最低配置。")
        if a.draft:
            top_warn.append(m + "（骨架阶段降级）"); n_warn += 1
        else:
            top_fail.append(m); n_fail += 1
    if a.tex and len(used) < a.min_body_figures:
        m = (f"正文实际引用 {len(used)} 张 < 下限 {a.min_body_figures}："
             "把图堆进附录不算数，评委翻的是正文。")
        if a.draft:
            top_warn.append(m + "（骨架阶段降级）"); n_warn += 1
        else:
            top_fail.append(m); n_fail += 1
    if a.tex and used and not a.draft and len(used) * 2 < len(files):
        top_fail.append(f"正文只引用了 {len(used)} 张，图目录里 {len(files)} 个文件：过半的图没进论文，检查是否漏接关键结果图")
        n_fail += 1
    contact_note = contact_sheet([p for p in files if os.path.splitext(p)[1].lower() in RASTER], a.contact)
    report = {"figdir": a.figdir, "n_figures": len(files), "n_body_figures": len(used),
              "min_figures": a.min_figures, "min_body_figures": a.min_body_figures,
              "n_fail": n_fail, "n_warn": n_warn,
              "top_fail": top_fail, "top_warn": top_warn, "skipped_files": skipped,
              "contact_sheet": contact_note,
              "manual_still_required": "逐张目检（重叠/出界/误差带/截断轴/图注自足/缩放比）仍须写入 结果/图面质检.md",
              "figures": results}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"图 {len(files)} 张：FAIL {n_fail}，WARN {n_warn} → {a.out}"
          + (f"（跳过本脚本生成物 {len(skipped)} 个：{', '.join(skipped)}）" if skipped else ""))
    print(contact_note)
    for m in top_fail:
        print(f"  FAIL 全局: {m}")
    for m in top_warn:
        print(f"  WARN 全局: {m}")
    for rec in results:
        for m in rec["fail"]:
            print(f"  FAIL {rec['file']}: {m}")
        for m in rec["warn"]:
            print(f"  WARN {rec['file']}: {m}")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
