# Paper Only

1. 建 Task Anchor；确认题面、`开题.md`、results ledger、结果文件和证书已冻结。运行 `python scripts/ledger.py --validate 结果/results_ledger.json` 与 `python scripts/ledger.py --stale-check 结果/results_ledger.json`；失败即转 `gate-triage.md`，不得补写数字。
2. 按需读 `references/abstract-moves.md` 与 `references/figure-style.md`，沿 `assets/paper/` 的分节形态写作；运行 `python scripts/ledger.py --emit-tex 结果/results_ledger.json -o 论文/numbers.tex`。
3. 每问写形式化模型、算法选择、结果解读与结论块；另写结果汇总表和六项独立检验章，不新增未经计算的结论。
4. 用 Crossref 或 OpenAlex 逐条核验最终引用；运行 `curl "https://api.crossref.org/works?query.bibliographic=<引用>"`，查不到的标注或删除。
5. 运行 `python scripts/audit_numbers.py --ledger 结果/results_ledger.json --numbers 论文/numbers.tex --tex 论文/*.tex --out 结果/审计报告.md`，再执行 `latex-fix.md`。
