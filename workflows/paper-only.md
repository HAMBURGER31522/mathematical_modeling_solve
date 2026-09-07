# Paper Only

1. 建 Task Anchor；确认题面、`开题.md`、results ledger、结果文件和证书已冻结。运行 `python scripts/ledger.py --validate 结果/results_ledger.json` 与 `python scripts/ledger.py --stale-check 结果/results_ledger.json`；失败即转 `gate-triage.md`，不得补写数字。
2. 按需读 `references/abstract-moves.md` 与 `references/figure-style.md`，先读 `assets/paper/README.md` 的按问题数装配流程，再沿 `assets/paper/` 的分节形态写作；运行 `python scripts/ledger.py --emit-tex 结果/results_ledger.json -o 论文/numbers.tex`。
3. 每问写形式化模型、算法选择、结果解读与结论块；另写结果汇总表和六项独立检验章，不新增未经计算的结论。
4. 逐条核验最终引用：模板尚未装配时运行
   `python scripts/refs_check.py assets/paper/9.参考文献.tex --out 结果/参考文献核验.md`；
   装配到交付目录后运行
   `python scripts/refs_check.py 论文/9.参考文献.tex --out 结果/参考文献核验.md`，退出码必须为 0；
   无 DOI、查无此文或标题不符的条目改引或删除。`.tex` 只支持标准 `\bibitem` 的 `\newblock` 标题
   格式；使用 BibTeX 时改为真实存在的 `.bib` 文件。不要用裸 curl 替代——它没有标题比对，也没有退出码。
5. 运行 `python scripts/audit_numbers.py --ledger 结果/results_ledger.json --numbers 论文/numbers.tex --tex 论文/*.tex --out 结果/审计报告.md`，再执行 `latex-fix.md`。
