# 完整求解：P-1 规格 → P0–P7

必读：`rules/modeling-redlines.md`、`rules/execution-discipline.md`

**角色与模型的对应关系在 `开题.md` 里**，本文件只写角色与交接。换模型不影响流程。
每个角色的**职责维度与交接验收单**见 `references/roles.md`——交接点按那张表逐条核，缺项退回。
单人单会话也能跑完——那时一人兼所有角色，但**交接点的产物一个都不能省**。

每道门禁以退出码为准，不以复述为准。

---

## P-1a 规格关（Coordinator）——PRD 未过关，禁止定方法路线

1. 读赛题、附件、格式规范；建 Task Anchor：Goal / Boundaries / Done When。
2. 运行 `python scripts/openconf.py`，确认赛事参数、模板与样例目录都读得到；
   缺项或占位符会直接报错——**没填就是没填，不给兜底默认值**。
3. 写 **PRD**（`结果/PRD.md`）：目标、边界、完成标准、已知事实与待定项。
4. **按轮次追问，不要一次问一个**。把待定项画成设计树：**前沿**＝所有前置已定、
   现在就能问的决策。**一轮把整个前沿问完**，每题编号并**给出你推荐的答案**；
   答案依赖本轮尚未定的问题，属于**下一轮**，不要在这一轮猜。
   用户答完，settled 的决策把前沿往外推，重算前沿再问下一轮。
   - **找事实是你的活，不是使用者的**：题面、附件、格式规范里能查到的，自己去查；
     查这件事**不阻塞其余前沿**——只有依赖它的问题等结果，其余照问。
   - 只问真正属于使用者的东西：目标取舍、范围边界、风险容忍度。
     「要不要我去看附件」这类过程问题不许问。
   - **前沿为空才算问完**：每条分支都走到，没有一处被默默假设。
5. **打磨关**：把 PRD 逐条追问一遍——每条完成标准都要能回答
   「怎么算过？谁来判？用什么命令判？」答不上来的条目不许留在 PRD 里。

> **本关未过之前，禁止**：定方法路线、写建模详要、动任何代码、跑任何计算。
> 「要解决什么」没定死就去想「怎么解」，等于让方案反过来定义问题。

**交出**：PRD + 题面分析。

## P-1b 建模详要（Coordinator）——本关未过，禁止进入 P0 之后的任何阶段

P-1a 通过之后才开始。**这一关的产物就是方法路线本身**，所以它不受上一关的禁令约束；
但它同样不许动代码、不许跑计算。

1. 写 `结果/建模详要.md`——**逐问一节**，每问十项：题型判定、形式化三要素、
   主路线、独立核验路线、承重假设、口径、证书预告、分辨率、数据接口、已知失败模式。
   规格与「必须写到什么程度」见 `references/roles.md` 的建模详要一节。
   **这是下游唯一的执行依据**：写薄了，执行方只能自己重新推导，
   两方各建各的模型，对抗性审查就变成了两套方案互相比较，而不是审查。
2. `python scripts/design_gate.py 结果/建模详要.md --out 结果/gates/G-1-建模详要.md`
   ——逐问十项齐全、每项有实质内容，且不得是「待补充／视情况而定」这类空洞措辞。
   退出码必须为 0。

> **本关未过之前，禁止**：动任何代码、跑任何计算、进入 P0 之后的任何阶段。

**交出**：建模详要。连同 P-1a 的 PRD 与题面分析一并交给下游——**这三样，不是一句口头描述**。

## P0 读题与体检（Coder，Coordinator 验收）

1. 逐问忠实转录原题，不改写、不合并。
2. 写 `结果/拆问卡.md`，每问九字段；`expected_outputs` 里写清对象身份口径。
   **`validation_requirements` 必须现在写死**——有了答案再挑验证方法，挑的一定是刚好能过的那个。
3. 初始化 `结果/results_ledger.json`。
4. 逐列体检附件：规模、量纲、min/max/mean/std、缺失异常，并与题面声明逐条对照。
5. `python scripts/task_cards.py --cards 结果/拆问卡.md --ledger 结果/results_ledger.json`

## P1 口径审定（Coder）

1. 只看原题、不看已填表，独立重建一遍可解释点，再与拆问卡对表。
2. 每项口径绑定题面 locator、被否口径的定量对照、判别实验与对象身份。
3. 每条口径挂一个判别实验：**若本条定错，哪个可观测量会异常**。挂不上就标 `UNVERIFIABLE` 并在论文披露。
4. `rg -n "BLOCKED|UNVERIFIABLE|待附件核验" 结果/拆问卡.md 结果/数据体检.md`，逐条处置命中。

## P2 选模与 Pilot（Modeler 先评审，再 Coder 执行）

**Modeler 的执行前评审——有异议就退回，不动手**

1. 拿 PRD、题目与题面分析（其中已含 Coordinator 提出的**建模思路**：题型、方法族、
   主路线与独立核验路线、承重假设），先做独立复核：题意有没有读偏、方法族选得对不对、
   主路线与核验路线是否真的独立、完成标准可不可判。
   **Modeler 是复核者不是原创者**——有异议列成清单交回 Coordinator，**不进入下面的步骤**，
   也不夹带自行修改。
2. Coordinator 按第一性原理查疏漏（见下面 Critic 一节），补充项同步回来后才继续。

**定型**

3. 按 Coordinator 在 PRD 里定的题型与方法族推进；多问题目共用同一个判定内核，
   各问只在生成/扫描/优化上分叉。执行中若发现思路本身要改，退回 Coordinator，不就地改。
4. 查方法卡拿候选：`python scripts/method_query.py "<题意关键词>" --top 6`。
   返回的 `failure_modes` 进拆问卡⑦，`validation` 进拆问卡⑧。**高分方法可以拒绝，但要在
   `选型.md` 写明为什么不合适**；零命中也是有效信息，按自研处理并记一行。
5. `选型.md` 每问写一行实现来源：库与 commit ／ 自研理由 ／ N/A。优先用有维护、
   有许可证、可钉版本的实现；自研要在 `选型.md` 写明理由。
6. 机时必须用**真实内核实测**后外推，复杂度符号不能替代计时
   （`references/gotchas.md#measured-runtime-beats-estimates`）。超配额就先提速再开跑。
7. Pilot：每问 2–3 个候选**外加一个简单 baseline**，同数据划分、同指标、同时间预算真跑。
   `python scripts/pilot_gate.py --results 结果/pilot_results.json`
8. 放大计算前，先用小规模把 P3→P7 跑通一遍最小闭环——结果、图、论文、PDF、复现入口都要真的存在。

## Critic 对抗性审查（贯穿 P2 与 P4，由**没参与实现的一方**做）

**入口是两问，深度交给专门的方法。** 这两条查的是「我凭什么说我做完了」，
最容易查、也最容易被跳过：

- **复现了吗？** 换台机器、换个种子、解包后照说明跑，还能得到同一个数吗？
- **红绿了吗？** 每个断言都先红过吗，还是写完实现才补的测试？

再往下就不是这两问能覆盖的了——对**方案本身**的第一性原理（公理化、拆解假设、
建立 ground truth、向上推导，以及 Complexity／Analogy／Legacy 三类陷阱的检查动作），
用 `first-principles-thinking`（若已安装）或按其六阶段自行展开，不要在本流程里重述。

本角色的完整审查维度见 `references/roles.md` 的 Critic 表（R1–R10）。

作者复核自己的实现，看到的是「我以为我写了什么」。这一步的全部价值在于**没参与**。
发现的疏漏同步给 Coder，改完重跑受影响的门禁，不是口头确认。

## P3 实现与计算（Coder）

**按题型/方法家族分派门禁**

所有题目仍要跑适用的 `test_inventory.py`、`ledger.py`、`figqa.py`、`audit_numbers.py`、
`pkg_scan.py`；长批仍由 `batch_gate.py` 审查，随机答案仍按适用性使用 `seed_gate.py`。
下表只避免把随机几何/伯努利专用检验伪装成通用要求。

| 题型/方法家族 | 必跑门禁 | 不适用时怎么办 |
|---|---|---|
| 随机几何、渗流或以 `conducts(n, threshold, seed)` 判定的模型 | `degenerate.py`；若结论由 iid Bernoulli 样本支持，再跑 `sample_gate.py`、`certify.py`、`seed_gate.py` | 不适用情形必须在 Gate 记录写 `N/A + 定量理由`，不能静默跳过。 |
| iid Bernoulli 机会约束，但没有上述几何导通原语 | `sample_gate.py`、`certify.py`、`seed_gate.py` | 对 `degenerate.py` 运行 `--not-applicable "无 conducts 原语：0 个几何个体"` 并保存记录。 |
| 回归、分类、预测、评价 | Pilot、独立测试、数据划分/指标审计、ledger；必要时按该方法的统计检验 | 对两道专用门禁各运行 `--not-applicable "回归评价：0 次 Bernoulli 试验"` 并保存记录。 |
| 确定性规划、网络优化、解析模型 | 独立神谕/对偶或解析证据、测试、ledger；长批时再跑 `batch_gate.py` | 对两道专用门禁各运行 `--not-applicable "确定性求解：0 个随机个体，0 次 Bernoulli 试验"` 并保存记录。 |

`--not-applicable` 的理由为空或没有定量信息即退出 2；带合格理由时输出 N/A 记录并退出 0。

**实现与测试**

1. 核心原语与判据实现在 `求解/core/`，各问一律 import，禁止逐问复制。
2. 先写独立神谕测试再进生产：expected 只来自手算、解析解或独立实现。
3. `python scripts/test_inventory.py --tests-dir 求解/tests --report 结果/gates/G3-tests.json`
4. 对表中适用的随机几何模型运行
   `python scripts/degenerate.py --fn <模块:函数> --threshold <题面阈值> --n-probe <题面档位>`
   ——退化端点必须符合物理期望且对阈值敏感；不适用时运行
   `python scripts/degenerate.py --not-applicable "<定量理由>" --out 结果/gates/G3-degenerate.json`。

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
10. 对表中适用的 iid Bernoulli 结论运行
    `python scripts/sample_gate.py --scenarios 结果/sample-scenarios.json --report 结果/gates/G3-samples.json`；
    不适用时运行 `python scripts/sample_gate.py --not-applicable "<定量理由>" --report 结果/gates/G3-samples.json`。
11. 临界／阈值／最优档位答案必须多种子复核：≥2 个独立种子族各覆盖答案点与相邻档。
    `python scripts/seed_gate.py 结果/多种子.json --out 结果/gates/G3-seed.md`
    退出码非 0 即答案未分辨，写 `certificate.resolved=false` 并降档报告
    （实测：同一临界档三族满样本判出三个相邻但不同的档位，见 `references/gotchas.md#seed-dependent-answers`）。
12. 关键答案双路互证，差异 ≳ Δ 必须定位原因，不取平均、不择优报喜。

**入账冻结**

13. 合理性检查：极限退化、单调性、量级粗估、跨问互恰、派生统计量从来源结构独立重算。
14. `python scripts/ledger.py --validate 结果/results_ledger.json` 然后 `--freeze`。

## P4 深度审查（Critic）

1. 逐问核声明强度、gap、误差预算、适用家族与外部量级对照。
2. 声明-实现一致性抽查：`论文口径原句 ↔ 代码文件:行号 ↔ 该行实际谓词`，每问关键判据至少抽 3 处。
3. 跨问一致性**从代码行号取证，不从论文取证**。
4. 私货约束扫描：每条模型约束都要能指到题面原文。
5. 内核或输入改变后 `python scripts/ledger.py --stale-check 结果/results_ledger.json --write` 并回 P3。

## P5 图表（Illustrator）

1. 每张图先写一句「它要让评委看见什么」，并指定它支持的结论、ledger 键与正文落点。写不出就不画。
2. 按需读 `references/figure-style.md`。**三套并行出图**：
   - ① 主控自出一套；
   - ② 执行方按背景、结论与结果文件路径出一套；
   - ③ 执行方模仿 `开题.md` 指定的样例目录再出一套。
3. 生成对照页 `图/对照.html`，三套同图并排，便于事后挑选。
4. **默认采用第 ① 套继续走 P6**——生成文章必然要引用图，流程不停下来等人选。
   对照页是留给使用者的接口：看完指定用哪套，替换后重跑本阶段门禁即可，其余环节不受影响。
5. 模仿的是版面与色彩编码，**长相可以仿，数字一个都不许仿**——图里每个数必须来自账本。
6. `python scripts/figqa.py 图/ --tex 论文/*.tex --out 结果/figqa.json --contact 图/_contact.png`
7. 目检 contact sheet：重叠、误差带、截断轴、图注自足、缩放比。
8. 生成的图未被正文引用即论证链断裂——要么引用并配解读段、要么移进补充图表附录并在正文指路、要么删除
   （`references/gotchas.md#generated-but-unused-figures`）。

## P6 论文（Writer）

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

9. 模板尚未装配时运行
   `python scripts/refs_check.py assets/paper/9.参考文献.tex --out 结果/参考文献核验.md`；
   装配到交付目录后运行
   `python scripts/refs_check.py 论文/9.参考文献.tex --out 结果/参考文献核验.md`，退出码必须为 0。
   `.tex` 只有标准 `\bibitem` 的 `\newblock` 标题格式才会做标题比对；使用 BibTeX 时把参数改为
   实际存在的 `.bib` 文件，不能凭空写 `论文/refs.bib`。
10. `python scripts/audit_numbers.py --ledger 结果/results_ledger.json --numbers 论文/numbers.tex --tex 论文/*.tex --out 结果/审计报告.md`
11. 答案唯一性：每问最终答案在摘要、正文、图表、结论里是同一个数。

## P6.5 复核（Auditor）

拿**题面原文 + 全部交付物**（不只是论文）逐条核，每条给证据位置。
完整维度见 `references/roles.md` 的 Auditor 表（A1–A10），核心十条：

1. **最优解是否入文**——账本里的 authoritative 答案与正文结论逐问一致；被选方案的最优性依据在文中可见。
2. **公式有无写坏**——符号、下标、量纲、编号引用、跨章符号是否同义。
3. **规范文字**——结论块三行、结果汇总表、检验章六小节、图后解读段、摘要 move，逐项在位。
4. **数字一致性**——正文 ↔ 宏 ↔ 账本三处同一个数；抽查若干条能否回读到结果文件。
5. **证书措辞匹配**——`resolved=false` 的结论有没有降精度；机会约束数字旁有没有下界值。
6. **图文对应**——图注与正文说的是不是同一件事；引用编号、图序、表序对得上。
7. **越级主张**——最优／证明／显著／必然／全局 逐处查，超出证据即标出。
8. **赛制合规**——页数口径、匿名、AI 声明、命名、附录指路句。
9. **复现声明属实**——论文里写的复现方式与交付包里真能跑的是否一致。
10. **未决项交代**——降级声明、未分辨结论、放弃的加分项有没有在文中如实交代。

只给论文核不了第 1 条与第 9 条。复核意见交回 Coordinator 裁决，**不直接改稿**。

## P7 编译与打包（Coordinator 确认后交 Finisher）

1. `latexmk -xelatex -halt-on-error -interaction=nonstopmode 论文/main.tex`
2. `python scripts/latex_gate.py 论文/main.log --pdf 论文/main.pdf --aux 论文/main.aux --tex 论文/main.tex --appendix-label sec:appendix --abstract-label abstract:end`
3. 页数不够时**补附录，不要撑正文**——赛制限的是正文，附录是承载工作量的地方。
4. 复现闭环：把 `assets/reproduce.py` 复制到交付根目录，填入至少一条真实重算命令
   （`RECOMPUTE` 默认为空，只跑 `--check-only` 不算通过），解包后在该目录执行默认模式。
5. `python scripts/pkg_scan.py 交付/`——工作区与交付包是两个安全边界，工作区扫干净不等于包里干净
   （`references/gotchas.md#delivery-boundary-leaks`）。
6. 每道 Gate 的记录写进 `结果/gates/G<n>.md`：命令原文、退出码、判定、证据路径。
   **没有命令与退出码的 Gate 记录视为未执行。**
