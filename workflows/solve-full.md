# 完整求解：P0 → P7

必读：`rules/modeling-redlines.md`、`rules/execution-discipline.md`

开工前建 Task Anchor（Goal / Boundaries / Done When），运行 `python scripts/openconf.py`
确认题面、附件、模板与赛事参数都读得到。**每道门禁以退出码为准，不以复述为准。**

## P0 读题与体检

1. 逐问忠实转录原题，不改写、不合并。
2. 写 `结果/拆问卡.md`，每问九字段；`expected_outputs` 里写清对象身份口径。
   **`validation_requirements` 必须现在写死**——有了答案再挑验证方法，挑的一定是刚好能过的那个。
3. 初始化 `结果/results_ledger.json`。
4. 逐列体检附件：规模、量纲、min/max/mean/std、缺失异常，并与题面声明逐条对照。
5. `python scripts/task_cards.py --cards 结果/拆问卡.md --ledger 结果/results_ledger.json`

## P1 口径审定

1. 只看原题、不看已填表，独立重建一遍可解释点，再与拆问卡对表。
2. 每项口径绑定题面 locator、被否口径的定量对照、判别实验与对象身份。
3. 每条口径挂一个判别实验：**若本条定错，哪个可观测量会异常**。挂不上就标 `UNVERIFIABLE` 并在论文披露。
4. `rg -n "BLOCKED|UNVERIFIABLE|待附件核验" 结果/拆问卡.md 结果/数据体检.md`，逐条处置命中。

## P2 选模与 Pilot

1. 先认题型再选方法族；多问题目共用同一个判定内核，各问只在生成/扫描/优化上分叉。
2. 查方法卡拿候选：`python scripts/method_query.py "<题意关键词>" --top 6`。
   返回的 `failure_modes` 进拆问卡⑦，`validation` 进拆问卡⑧。**高分方法可以拒绝，但要在
   `选型.md` 写明为什么不合适**；零命中也是有效信息，按自研处理并记一行。
3. `选型.md` 每问写一行实现来源：库与 commit ／ 自研理由 ／ N/A。禁止手搓教科书算法。
4. 机时必须用**真实内核实测**后外推，复杂度符号不能替代计时
   （`references/gotchas.md#measured-runtime-beats-estimates`）。超配额就先提速再开跑。
5. Pilot：每问 2–3 个候选**外加一个简单 baseline**，同数据划分、同指标、同时间预算真跑。
   `python scripts/pilot_gate.py --results 结果/pilot_results.json`
6. 放大计算前，先用小规模把 P3→P7 跑通一遍最小闭环——结果、图、论文、PDF、复现入口都要真的存在。

## P3 实现与计算

**实现与测试**

1. 核心原语与判据实现在 `求解/core/`，各问一律 import，禁止逐问复制。
2. 先写独立神谕测试再进生产：expected 只来自手算、解析解或独立实现。
3. `python scripts/test_inventory.py --tests-dir 求解/tests --report 结果/gates/G3-tests.json`
4. `python scripts/degenerate.py --fn <模块:函数> --threshold <题面阈值> --n-probe <题面档位>`
   ——退化端点必须符合物理期望且对阈值敏感。

**长批执行**

5. 长批必须写成可恢复状态机：每块 ≤500 单元、临时文件 `os.replace` 原子落盘、启动扫描跳过已完成块。
6. `python scripts/batch_gate.py 求解/*.py --out 结果/gates/G3-batch.md`，退出码必须为 0。
7. 先算后画：计算脚本只落盘结果，绘图脚本只读结果文件。

**统计认证与稳定性**

8. 机会约束或 iid 伯努利型结论由官方证书执行体出具，不得手写公式：
   `python scripts/certify.py --k <成功数> --n <样本量> --threshold <题面阈值> --delta <分辨率>`
   三态判定与下界、n、seed 写进 ledger 的 `certificate`；其他方法家族改走该家族对应证书并写明。
9. 区间跨过阈值只能称**证据不足**，不得改称不可行、也不得直接改报更保守的答案
   （`references/gotchas.md#inconclusive-is-not-failure`）。
10. `python scripts/sample_gate.py --scenarios 结果/sample-scenarios.json --report 结果/gates/G3-samples.json`
11. 临界／阈值／最优档位答案必须多种子复核：≥2 个独立种子族各覆盖答案点与相邻档。
    `python scripts/seed_gate.py 结果/多种子.json --out 结果/gates/G3-seed.md`
    退出码非 0 即答案未分辨，写 `certificate.resolved=false` 并降档报告
    （实测：同一临界档两族满样本各判 614 与 615，见 `references/gotchas.md#seed-dependent-answers`）。
12. 关键答案双路互证，差异 ≳ Δ 必须定位原因，不取平均、不择优报喜。

**入账冻结**

13. 合理性检查：极限退化、单调性、量级粗估、跨问互恰、派生统计量从来源结构独立重算。
14. `python scripts/ledger.py --validate 结果/results_ledger.json` 然后 `--freeze`。

## P4 深度审查

1. 逐问核声明强度、gap、误差预算、适用家族与外部量级对照。
2. 声明-实现一致性抽查：`论文口径原句 ↔ 代码文件:行号 ↔ 该行实际谓词`，每问关键判据至少抽 3 处。
3. 跨问一致性**从代码行号取证，不从论文取证**。
4. 私货约束扫描：每条模型约束都要能指到题面原文。
5. 内核或输入改变后 `python scripts/ledger.py --stale-check 结果/results_ledger.json --write` 并回 P3。

## P5 图表

1. 每张图先写一句「它要让评委看见什么」，并指定它支持的结论、ledger 键与正文落点。写不出就不画。
2. 按需读 `references/figure-style.md`，并打开 `开题.md` 指定目录里的样例图看 2–3 张。
3. `python scripts/figqa.py 图/ --tex 论文/*.tex --out 结果/figqa.json --contact 图/_contact.png`
4. 目检 contact sheet：重叠、误差带、截断轴、图注自足、缩放比。
5. 生成的图未被正文引用即论证链断裂——要么引用并配解读段、要么移进补充图表附录并在正文指路、要么删除
   （`references/gotchas.md#generated-but-unused-figures`）。

## P6 论文

**装配与数字**

1. 先读 `assets/paper/README.md` 的按问题数装配流程，再沿 `assets/paper/` 分节装配。
2. `python scripts/ledger.py --emit-tex 结果/results_ledger.json -o 论文/numbers.tex`——先生成宏再写文。
3. 正文只引用宏；宏携带证书元数据（下界、n、seed、verdict、resolved、Δ、u），
   机会约束类数字旁必须出现下界值。

**正文与检验**

4. 按需读 `references/abstract-moves.md` 写摘要。
5. 每问写形式化模型、算法段落、结果解读与结论块（最终答案 + 证书 + 适用条件三行）；全文放一张结果汇总表。
6. 每张正文图后紧跟解读段，按「现象—原因—意义」写；只写「如图 X 所示」不算解读。
7. 检验章独立成章、六小节缺一不可：双路互证 / 与可核事实对表 / 参数灵敏度 / 样本量与收敛 /
   稳健性对照 / 适用边界与失效域。
8. 模型评价章的缺点按「缺陷—影响—改进」写，并与降级声明逐条一致。

**审计**

9. `python scripts/refs_check.py 论文/refs.bib --out 结果/参考文献核验.md`，退出码必须为 0。
10. `python scripts/audit_numbers.py --ledger 结果/results_ledger.json --numbers 论文/numbers.tex --tex 论文/*.tex --out 结果/审计报告.md`
11. 答案唯一性：每问最终答案在摘要、正文、图表、结论里是同一个数。

## P7 编译与打包

1. `latexmk -xelatex -halt-on-error -interaction=nonstopmode 论文/main.tex`
2. `python scripts/latex_gate.py 论文/main.log --pdf 论文/main.pdf --aux 论文/main.aux --tex 论文/main.tex --appendix-label sec:appendix --abstract-label abstract:end`
3. 页数不够时**补附录，不要撑正文**——赛制限的是正文，附录是承载工作量的地方。
4. 复现闭环：把 `assets/reproduce.py` 复制到交付根目录，填入至少一条真实重算命令
   （`RECOMPUTE` 默认为空，只跑 `--check-only` 不算通过），解包后在该目录执行默认模式。
5. `python scripts/pkg_scan.py 交付/`——工作区与交付包是两个安全边界，工作区扫干净不等于包里干净
   （`references/gotchas.md#delivery-boundary-leaks`）。
6. 每道 Gate 的记录写进 `结果/gates/G<n>.md`：命令原文、退出码、判定、证据路径。
   **没有命令与退出码的 Gate 记录视为未执行。**
