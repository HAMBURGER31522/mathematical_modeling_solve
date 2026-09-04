# -*- coding: utf-8 -*-
"""交付包出门扫描（P7 阻断项）：秘密、绝对路径、包外依赖、运行产物。

为什么需要
----------
2026-09-04 实测：一份已判"R7 合规门禁全 PASS"的交付物里，
`求解/run_mc.py` 第 16 行写着 `USER, PWD = 'root', '<真实口令>'`。
它在工作区里（gitignored）所以历史清洗扫不到，但交付物是要被拷进 winner 目录并上传的——
**差一步就把凭据推上公开仓库**。同一份交付物还有：
硬编码的 `F:\...` 绝对路径、README 引用的不存在文件、图脚本里写死的过期数值。

这些都不是"写在规范里提醒一下"能拦住的，必须是**出门前跑、有退出码**的扫描。

用法
----
    python scripts/pkg_scan.py <交付物目录> [--allow-abs] [--out 结果/gates/G7-出门扫描.json]

退出码：0 无阻断项；1 有阻断项。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

TEXT_EXT = {".py", ".md", ".txt", ".tex", ".json", ".csv", ".yml", ".yaml",
            ".ini", ".cfg", ".sh", ".ps1", ".bat", ".toml"}

SECRET_PATTERNS = [
    (r"(?i)\b(pwd|passwd|password)\s*[:=]\s*['\"][^'\"]{6,}['\"]", "疑似明文口令赋值"),
    (r"(?i)\b(api[_-]?key|secret|token)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]", "疑似密钥/令牌"),
    (r"sk-[A-Za-z0-9]{20,}", "疑似 OpenAI 风格密钥"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "私钥文件内容"),
    (r"(?i)\b(username|user)\s*[:=]\s*['\"]root['\"][^\n]{0,80}(pwd|passwd|password)", "root 账号+口令同行"),
    (r"(?i)ssh://[^\s'\"]*:[^\s'\"@]+@", "URL 内嵌凭据"),
]

ABS_PATTERNS = [
    (r"[A-Za-z]:\\\\?[A-Za-z0-9_\u4e00-\u9fff]", "Windows 绝对路径"),
    (r"(?<![\w.])/(?:home|root|Users)/[A-Za-z0-9_.-]+", "Unix 绝对路径"),
]

JUNK_RE = re.compile(r"__pycache__|\.pyc$|\.pytest_cache|\.aux$|\.fls$|\.fdb_latexmk$|\.synctex|\.log$")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--allow-abs", action="store_true",
                    help="确有正当理由保留绝对路径时才可加，并须在 README 说明")
    ap.add_argument("--out", default="结果/gates/G7-出门扫描.json")
    a = ap.parse_args(argv)

    root = os.path.abspath(a.root)
    if not os.path.isdir(root):
        print(f"目录不存在：{root}", file=sys.stderr)
        return 2

    blocking, warn = [], []
    files = []
    for dp, _dn, fn in os.walk(root):
        for f in fn:
            files.append(os.path.join(dp, f))

    for p in files:
        rel = os.path.relpath(p, root).replace("\\", "/")
        if JUNK_RE.search(p):
            (blocking if not p.endswith(".log") else warn).append(
                {"类型": "运行产物残留", "文件": rel, "说明": "交付包内不得含缓存与编译中间件"})
            continue
        if os.path.splitext(p)[1].lower() not in TEXT_EXT:
            continue
        try:
            txt = open(p, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        for pat, why in SECRET_PATTERNS:
            for m in re.finditer(pat, txt):
                line = txt[:m.start()].count("\n") + 1
                blocking.append({"类型": "疑似凭据", "文件": f"{rel}:{line}", "说明": why,
                                 "片段": re.sub(r"['\"][^'\"]{4,}['\"]", "'***'", m.group(0))[:80]})
        if not a.allow_abs:
            for pat, why in ABS_PATTERNS:
                hits = list(re.finditer(pat, txt))
                if hits:
                    line = txt[:hits[0].start()].count("\n") + 1
                    blocking.append({"类型": "绝对路径", "文件": f"{rel}:{line}", "说明": why,
                                     "出现次数": len(hits),
                                     "片段": txt[hits[0].start():hits[0].start() + 60].split("\n")[0]})

    # README 引用的文件是否存在（包外依赖的常见形态）
    for p in files:
        if not re.match(r"readme", os.path.basename(p), re.I):
            continue
        txt = open(p, encoding="utf-8", errors="replace").read()
        for m in re.finditer(r"[`'\"]([\w\u4e00-\u9fff./\\-]+\.(?:csv|json|py|npz|tex|pdf))[`'\"]", txt):
            name = m.group(1)
            if os.path.isabs(name):
                continue
            cand = os.path.normpath(os.path.join(root, name))
            if not os.path.exists(cand) and not any(os.path.basename(f) == os.path.basename(name) for f in files):
                warn.append({"类型": "README 引用不存在的文件", "文件": os.path.relpath(p, root),
                             "说明": name})

    report = {"root": root, "文件数": len(files),
              "阻断项": len(blocking), "提示项": len(warn),
              "blocking": blocking[:200], "warnings": warn[:100],
              "口径": "P7 出门扫描；阻断项清零才可打包上交"}
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")

    for b in blocking[:20]:
        print(f"  [阻断] {b['类型']}  {b['文件']}  — {b['说明']}")
    for w in warn[:10]:
        print(f"  [提示] {w['类型']}  {w.get('文件','')}  — {w['说明']}")
    print(f"出门扫描：阻断 {len(blocking)}，提示 {len(warn)} → {a.out}")
    if blocking:
        print("！！交付包不得上交。凭据必须换掉而不只是删除；绝对路径改为包内相对路径。", file=sys.stderr)
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
