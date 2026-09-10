# -*- coding: utf-8 -*-
"""参考文献真实性核验（P6）——逐条查 Crossref，把编造的引用挡在提交之前。

评委随手一查即为 rules 维失分，而模型编造参考文献是公认高频错误。
本脚本只回答一个问题：**这条引用真的存在吗**；不判断它切不切题。

用法：
    python scripts/refs_check.py 论文/refs.bib --out 结果/参考文献核验.md
    python scripts/refs_check.py 论文/9.参考文献.tex --out 结果/参考文献核验.md

退出码：0 = 全部可核验；1 = 存在查无此文或标题不符的条目；2 = 用法/网络错误。
无网络时用 --offline 只做结构检查（缺 DOI 的条目照样记 FAIL）；SKIP 不是通过。
`.tex` 同时支持标准 `\newblock` 和本仓模板的单行 `\bibitem{标签} 作者. 题名. 出版信息.`。
作者、标题或载体证据缺失时明确记为 UNVERIFIED，不静默放行。
纯标准库。
"""
import argparse
from dataclasses import dataclass
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


@dataclass(frozen=True)
class ReferenceRecord:
    head: str
    doi: str
    title: str
    authors: tuple[str, ...] = ()
    container: str = ""


def _clean_doi(match):
    return match.group(0).rstrip(".,;:)]}") if match else ""


def _bib_field(block, name):
    match = re.search(
        rf"\b{name}\s*=\s*(?:\{{([^}}]*)\}}|\"([^\"]*)\")",
        block, re.S | re.I,
    )
    return (match.group(1) or match.group(2) or "").strip() if match else ""


def _surname_list(text):
    surnames = []
    for person in re.split(r"\s+and\s+|;", text or "", flags=re.I):
        person = re.sub(r"\s+", " ", person).strip(" .,")
        if not person:
            continue
        if "," in person:
            surname = person.split(",", 1)[0].strip()
        else:
            words = person.split()
            if len(words) >= 2 and re.fullmatch(r"[A-Z](?:\.)?", words[-1]):
                surname = words[0]
            else:
                surname = words[-1]
        if surname:
            surnames.append(surname)
    return tuple(surnames)


def _strip_tex(text):
    text = re.sub(r"\\(?:emph|textit|textbf|textrm)\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\[A-Za-z]+(?:\s|\{\})?", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _clean_title(text):
    text = _strip_tex(text).strip().strip("{} ")
    text = re.split(r"(?<=[.!?])\s|\s+doi\s*:", text, maxsplit=1, flags=re.I)[0]
    return text.rstrip(".。 ")


def _clean_container(text):
    text = _strip_tex(text)
    return re.sub(r"\b(?:19|20)\d{2}\b.*$", "", text).strip(" .,:;，；")


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
            entries.append((" ".join(item.split())[:80], doi.group(0) if doi else "", _tex_bibitem_title(item)))
    return entries


def _tex_bibitem_title(item):
    """Extract the title from the common ``author\newblock title\newblock`` layout."""
    blocks = re.split(r"\\newblock\b", item, maxsplit=2)
    if len(blocks) < 2:
        clean = _strip_tex(item)
        clean = re.sub(r"\s*doi\s*:\s*10\.\d{4,9}/\S+", "", clean, flags=re.I).strip()
        parts = [part.strip() for part in re.split(
            r"(?<=[.!?。！？])\s+(?=[A-Z\u4e00-\u9fff])", clean
        ) if part.strip()]
        return _clean_title(parts[1] if len(parts) >= 2 else "")
    title = blocks[1].strip()
    title = re.sub(r"\\(?:emph|textit|textbf|textrm)\{([^{}]*)\}", r"\1", title)
    title = re.sub(r"\s+", " ", title).strip().strip("{} ")
    title = re.split(r"(?<=[.!?])\s|\s+doi\s*:", title, maxsplit=1, flags=re.I)[0]
    return title.rstrip(".。 ")


def _parse_tex_metadata(item):
    """Return title, author surnames, and publication container for a bibitem."""
    blocks = re.split(r"\\newblock\b", item, maxsplit=2)
    if len(blocks) >= 2:
        title = _tex_bibitem_title(item)
        authors = _surname_list(_strip_tex(blocks[0]))
        container = _clean_container(blocks[2] if len(blocks) > 2 else "")
        return title, authors, container
    clean = _strip_tex(item)
    clean = re.sub(r"\s*doi\s*:\s*10\.\d{4,9}/\S+", "", clean, flags=re.I).strip()
    parts = [part.strip() for part in re.split(
        r"(?<=[.!?。！？])\s+(?=[A-Z\u4e00-\u9fff])", clean
    ) if part.strip()]
    if len(parts) >= 3:
        return _clean_title(parts[1]), _surname_list(parts[0]), _clean_container(" ".join(parts[2:]))
    if len(parts) == 2:
        return _clean_title(parts[1]), _surname_list(parts[0]), ""
    return "", (), ""


def _parse_records(path):
    """Parse .bib/.tex entries into records while preserving legacy tuple parsing."""
    raw = open(path, encoding="utf-8", errors="replace").read()
    records = []
    if path.lower().endswith(".bib"):
        for block in re.split(r"(?m)^@", raw):
            if not block.strip() or "{" not in block:
                continue
            records.append(ReferenceRecord(
                block.strip().split("\n")[0][:80],
                _clean_doi(DOI_RE.search(block)),
                _bib_field(block, "title"),
                _surname_list(_bib_field(block, "author")),
                (_bib_field(block, "journal") or _bib_field(block, "container-title")
                 or _bib_field(block, "booktitle")),
            ))
    else:
        for item in re.findall(
            r"\\bibitem(?:\[[^\]]*\])?\{[^}]*\}(.+?)(?=\\bibitem|\\end\{thebibliography\}|\Z)",
            raw, re.S,
        ):
            title, authors, container = _parse_tex_metadata(item)
            records.append(ReferenceRecord(
                " ".join(item.split())[:80], _clean_doi(DOI_RE.search(item)),
                title, authors, container,
            ))
    return records


def query(doi, timeout):
    req = urllib.request.Request(CROSSREF + urllib.parse.quote(doi), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))["message"]


def _author_match(record, message):
    """Return (matched, note); None means local author evidence is absent."""
    remote = [str(author.get("family", "")) for author in (message.get("author") or [])
              if isinstance(author, dict) and author.get("family")]
    if not record.authors:
        return None, "作者证据缺失（UNVERIFIED）"
    if not remote:
        return False, "Crossref 未返回 author"
    local = {norm(name) for name in record.authors if norm(name)}
    if any(any(name in norm(family) or norm(family) in name for name in local)
           for family in remote):
        return True, "作者姓匹配"
    return False, "作者姓不符"


def _container_match(record, message):
    remote_values = message.get("container-title") or []
    remote = remote_values[0] if remote_values else ""
    if not record.container:
        return None, "载体证据缺失（UNVERIFIED）"
    if not remote:
        return False, "Crossref 未返回 container-title"
    left, right = norm(record.container), norm(remote)
    if left and (left in right or right in left):
        return True, "载体匹配"
    return False, "出版载体不符"


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

    records = _parse_records(a.refs)
    if not records:
        print("未解析出任何参考文献条目——空检查一律记 fail，不是通过", file=sys.stderr)
        return 1

    rows, failed = [], 0
    for record in records:
        head, doi, title = record.head, record.doi, record.title
        if not doi:
            rows.append(("FAIL", head, "", "无 DOI，无法核验"))
            failed += 1
            continue
        if a.offline:
            rows.append(("SKIP", head, doi, "--offline，未联网核验"))
            failed += 1
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
        mismatches = []
        if not title:
            mismatches.append("标题证据缺失（UNVERIFIED）")
        elif norm(title) not in norm(got) and norm(got) not in norm(title):
            mismatches.append("标题不符：文中「%s」↔ Crossref「%s」" % (title[:40], got[:40]))
        author_ok, author_note = _author_match(record, msg)
        if author_ok is not True:
            mismatches.append(author_note)
        container_ok, container_note = _container_match(record, msg)
        if container_ok is not True:
            mismatches.append(container_note)
        year = ((msg.get("issued") or {}).get("date-parts") or [[""]])[0][0]
        if mismatches:
            rows.append(("FAIL", head, doi, "; ".join(mismatches)))
            failed += 1
        else:
            rows.append(("PASS", head, doi, "%s (%s); 作者姓匹配；载体匹配" % (got[:60], year)))
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
