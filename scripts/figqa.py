#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图面自动质检 + contact sheet 导出（G5 硬项的可执行部分）。

对应 references/figures-standards.md。位图检查需要 Pillow（缺失时自动降级为
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
import hashlib
import json
import os
import re
import sys

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


def referenced_figures(tex_paths):
    used = set()
    for p in tex_paths:
        with open(p, encoding="utf-8", errors="replace") as f:
            txt = f.read()
        txt = re.sub(r"(?<!\\)%.*", "", txt)
        for m in re.finditer(r"\\includegraphics\s*(?:\[[^\]]*\])?\s*\{([^}]+)\}", txt):
            used.add(os.path.basename(m.group(1).strip()).lower())
    return used


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


def main(argv=None):
    ap = argparse.ArgumentParser(description="图面自动质检与 contact sheet")
    ap.add_argument("figdir")
    ap.add_argument("--tex", nargs="*", default=[], help="正文 tex，用于检查图是否被引用")
    ap.add_argument("--out", default="结果/figqa.json")
    ap.add_argument("--contact", default="图/_contact.png")
    a = ap.parse_args(argv)

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
            rec["warn"].append("未被正文 \\includegraphics 引用（未引用的图移附录或删除）")
        n_fail += len(rec["fail"]); n_warn += len(rec["warn"])
        results.append(rec)

    top_warn = []
    if a.tex and not used:
        top_warn.append("正文一张图都没引用（\\includegraphics 为 0）：骨架阶段正常，成稿阶段即 G5 fail")
        n_warn += 1
    contact_note = contact_sheet([p for p in files if os.path.splitext(p)[1].lower() in RASTER], a.contact)
    report = {"figdir": a.figdir, "n_figures": len(files), "n_fail": n_fail, "n_warn": n_warn,
              "top_warn": top_warn, "skipped_files": skipped,
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
