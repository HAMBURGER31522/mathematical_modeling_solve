# -*- coding: utf-8 -*-
"""方法卡检索（P2）——把 1769 行的 method-cards.json 变成可按需读的少量候选。

为什么需要它：`references/method-cards.json` 有 6 个领域、66 张方法卡，没有索引就只有
两种结局——整文件读进上下文，或者读一半被截断。两者都让「渐进加载」名存实亡。

评分沿用 Remit 的三层加权（领域 20% / 子领域 30% / 方法 50%）：同一个词命中越具体的
层级，权重越高。检索完全本地、无向量库、无模型调用，同样的输入必然得到同样的输出，
方便复查——这也是它能进门禁链路的前提。

**它给的是候选，不是答案。** 高分方法可以被拒绝，但 `选型.md` 里要写明为什么不合适；
方法卡的 `failure_modes` 与 `validation` 两栏分别喂给拆问卡的⑦风险与⑧验证要求。

用法：
    python scripts/method_query.py "时间序列 预测 缺失值" --top 6
    python scripts/method_query.py "阈值反解 概率约束" --top 5 --json

退出码：0 = 有命中；1 = 零命中（属有效信息：说明这是声明缺口，按自研处理并记进选型.md）；
2 = 用法/数据错误。纯标准库。
"""
import argparse
import json
import os
import re
import sys

CARDS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                     "references", "method-cards.json")
W_DOMAIN, W_SUB, W_METHOD = 0.2, 0.3, 0.5


def tokenize(text):
    """中英混排：英文按词、中文按 2-gram，够检索用，不引依赖。"""
    text = (text or "").lower()
    tokens = set(re.findall(r"[a-z][a-z0-9_+-]{1,}", text))
    cjk = re.findall(r"[一-鿿]+", text)
    for run in cjk:
        tokens.update(run[i:i + 2] for i in range(max(len(run) - 1, 1)))
    return tokens


def bag(*fields):
    out = set()
    for field in fields:
        if isinstance(field, list):
            for item in field:
                out |= tokenize(str(item))
        else:
            out |= tokenize(str(field))
    return out


def overlap(query, target):
    return len(query & target) / len(query) if query else 0.0


def search(query_text, top):
    with open(CARDS, encoding="utf-8") as fh:
        domains = json.load(fh)
    query = tokenize(query_text)
    if not query:
        return []

    hits = []
    for domain in domains:
        d_score = overlap(query, bag(domain["name"], domain.get("description"),
                                     domain.get("keywords")))
        for sub in domain["subdomains"]:
            s_score = overlap(query, bag(sub["name"], sub.get("description"),
                                         sub.get("keywords")))
            for method in sub["methods"]:
                m_score = overlap(query, bag(method["name"], method.get("summary"),
                                             method.get("keywords"),
                                             method.get("assumptions"),
                                             method.get("failure_modes")))
                total = W_DOMAIN * d_score + W_SUB * s_score + W_METHOD * m_score
                if total > 0:
                    hits.append({
                        "score": round(total, 4),
                        "domain": domain["name"],
                        "subdomain": sub["name"],
                        "name": method["name"],
                        "summary": method.get("summary", ""),
                        "assumptions": method.get("assumptions", []),
                        "failure_modes": method.get("failure_modes", []),
                        "validation": method.get("validation", []),
                    })
    hits.sort(key=lambda h: (-h["score"], h["name"]))
    return hits[:top]


def main():
    ap = argparse.ArgumentParser(description="方法卡检索")
    ap.add_argument("query", help="题意关键词，中英皆可，空格分隔")
    ap.add_argument("--top", type=int, default=6)
    ap.add_argument("--json", action="store_true", help="输出 JSON 而非可读文本")
    a = ap.parse_args()

    if not os.path.isfile(CARDS):
        print("找不到 references/method-cards.json", file=sys.stderr)
        return 2
    try:
        hits = search(a.query, a.top)
    except (ValueError, KeyError, TypeError) as exc:
        print("方法卡结构不合法：%s" % exc, file=sys.stderr)
        return 2

    if not hits:
        print("零命中。这是有效信息：方法卡里没有对应条目，按自研处理，"
              "并在 选型.md 写明「路由库无匹配，自研」。", file=sys.stderr)
        return 1

    if a.json:
        print(json.dumps(hits, ensure_ascii=False, indent=1))
        return 0

    for hit in hits:
        print("[%.3f] %s（%s / %s）" % (hit["score"], hit["name"],
                                        hit["domain"], hit["subdomain"]))
        print("       " + hit["summary"])
        if hit["assumptions"]:
            print("       前提：" + "；".join(hit["assumptions"]))
        if hit["failure_modes"]:
            print("       会怎么死：" + "；".join(hit["failure_modes"]))
        if hit["validation"]:
            print("       怎么验：" + "；".join(hit["validation"]))
    print()
    print("以上是候选不是结论。拒绝高分方法要在 选型.md 写明理由；"
          "failure_modes 进拆问卡⑦，validation 进拆问卡⑧。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
