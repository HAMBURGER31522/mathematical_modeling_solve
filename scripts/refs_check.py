# -*- coding: utf-8 -*-
"""参考文献真实性核验（P6）——逐条查 Crossref，把编造的引用挡在提交之前。

评委随手一查即为 rules 维失分，而模型编造参考文献是公认高频错误。
本脚本只回答一个问题：**这条引用真的存在吗**；不判断它切不切题。

用法：
    python scripts/refs_check.py 论文/refs.bib --out 结果/参考文献核验.md
    python scripts/refs_check.py 论文/10.参考文献.tex --out 结果/参考文献核验.md

退出码：0 = 全部可核验；1 = 存在查无此文或标题不符的条目；2 = 用法/网络错误。
无网络时用 --offline 只做结构检查（缺 DOI 的条目照样记 FAIL），退出码语义不变。
纯标准库。
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

CROSSREF = "https://api.crossref.org/works/"
UA = "math-modeling-solve/refs_check (mailto:anonymous@example.org)"
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")


def norm(text):
    """标题比对用：去空白、去标点、转小写，避免大小写与排版差异造成假阳性。"""
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", (text or "").lower())


def parse_entries(path):
    """从 .bib 或 .tex 抽条目：每条给 (原文片段, doi, 标题)。标题抽不到就留空。"""
    raw = open(path, encoding="utf-8", errors="replace").read()
    entries = []
    if path.lower().endswith(".bib"):
        # 按行首的 @ 切条目。旧写法在文件以 @ 开头时会把唯一一片当成前导内容丢掉，
        # 结果任何正常 .bib 都解析出 0 条 —— 契约测试抓到的第一个真 bug。
        for block in re.split(r"(?m)^@", raw):
            if not block.strip() or "{" not in block:
                continue
            doi = DOI_RE.search(block)
            title = re.search(r"title\s*=\s*[{\"]+(.+?)[}\"]+\s*,", block, re.S | re.I)
            entries.append((block.strip().split("\n")[0][:80], doi.group(0) if doi else "",
                            title.group(1).strip() if title else ""))
    else:
        for item in re.findall(r"\\bibitem(?:\[[^\]]*\])?\{[^}]*\}(.+?)(?=\\bibitem|\\end\{thebibliography\}|\Z)",
                               raw, re.S):
            doi = DOI_RE.search(item)
            entries.append((" ".join(item.split())[:80], doi.group(0) if doi else "", ""))
    return entries


def query(doi, timeout):
    req = urllib.request.Request(CROSSREF + urllib.parse.quote(doi), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))["message"]


def main():
    ap = argparse.ArgumentParser(description="参考文献 Crossref 核验")
    ap.add_argument("refs", help="论文的 .bib 或参考文献 .tex")
    ap.add_argument("--out", default="结果/参考文献核验.md")
    ap.add_argument("--offline", action="store_true", help="不联网，只做结构检查")
    ap.add_argument("--timeout", type=float, default=15.0)
    ap.add_argument("--sleep", type=float, default=0.4, help="两次请求间隔，别打爆公共 API")
    a = ap.parse_args()

    if not os.path.isfile(a.refs):
        print("找不到参考文献文件：%s" % a.refs, file=sys.stderr)
        return 2

    entries = parse_entries(a.refs)
    if not entries:
        print("未解析出任何参考文献条目——空检查一律记 fail，不是通过", file=sys.stderr)
        return 1

    rows, failed = [], 0
    for head, doi, title in entries:
        if not doi:
            rows.append(("FAIL", head, "", "无 DOI，无法核验"))
            failed += 1
            continue
        if a.offline:
            rows.append(("SKIP", head, doi, "--offline，未联网核验"))
            continue
        try:
            msg = query(doi, a.timeout)
        except urllib.error.HTTPError as exc:
            rows.append(("FAIL", head, doi, "Crossref 查无此 DOI（HTTP %s）" % exc.code))
            failed += 1
            time.sleep(a.sleep)
            continue
        except Exception as exc:  # 网络问题不冒充学术问题
            print("网络错误：%s。可加 --offline 只做结构检查。" % exc, file=sys.stderr)
            return 2
        got = (msg.get("title") or [""])[0]
        if title and norm(title) and norm(title) not in norm(got) and norm(got) not in norm(title):
            rows.append(("FAIL", head, doi, "标题不符：文中「%s」↔ Crossref「%s」" % (title[:40], got[:40])))
            failed += 1
        else:
            year = ((msg.get("issued") or {}).get("date-parts") or [[""]])[0][0]
            rows.append(("PASS", head, doi, "%s (%s)" % (got[:60], year)))
        time.sleep(a.sleep)

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("# 参考文献核验\n\n来源：`%s`　条目 %d　FAIL %d\n\n" % (a.refs, len(rows), failed))
        fh.write("| 判定 | 条目 | DOI | 说明 |\n|---|---|---|---|\n")
        for verdict, head, doi, note in rows:
            fh.write("| %s | %s | %s | %s |\n" % (verdict, head.replace("|", "/"), doi, note.replace("|", "/")))
    print("条目 %d，FAIL %d → %s" % (len(rows), failed, a.out))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
