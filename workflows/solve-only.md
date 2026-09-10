# 只求解，暂不写论文：P-1a → P4

必读：`rules/modeling-redlines.md`、`rules/execution-discipline.md`

用在「先做问题一」「只要模型、代码和结果」「论文回头再说」这类分阶段请求上。
**不进 P5–P7**，但 P-1a 到 P4 的纪律一条不减——恰恰是这类请求最容易丢掉它们。

为什么不能落到通用流程：拆问卡、Pilot、独立神谕测试、证书与冻结是**后面写论文时无法补做**的。
数字一旦在没有这些纪律的情况下算出来，之后再写论文就只能拿它当既成事实。

## 前置规格关

1. 先照 `workflows/solve-full.md` 完成 **P-1a**：写 PRD、按设计树前沿澄清并过打磨关，运行
   `python scripts/prd_gate.py 结果/PRD.md --out 结果/gates/G-0-PRD.md`，退出码必须为 0。
2. 再完成 **P-1b**：逐问写建模详要，运行
   `python scripts/design_gate.py 结果/建模详要.md --out 结果/gates/G-1-建模详要.md`，退出码必须为 0。
3. Modeler 按完整流程做执行前规格复核；只有明确交出「无异议，可执行」，Coder 才能进入 P0。

## 与完整求解的关系

P-1a、P-1b、执行前规格复核以及 P0–P4 都照 `workflows/solve-full.md` 执行，**不做简化**。
本文件只说明差异：

| 项 | 本流程 |
|---|---|
| 范围 | 只做被点名的那些问；未点名的问不预先求解，也不在 ledger 里占位 |
| 图 | 只画支撑当前结论所必需的诊断图；`figqa.py` 的数量下限**不适用**（那是论文的要求） |
| 论文 | 不装配、不写正文；但 P3 的宏发射照做，`numbers.tex` 先备好 |
| 交付 | 不打包；`pkg_scan.py` 不跑 |

## 收尾（本流程的 Done When）

1. 被点名的每问都有：拆问卡九字段、Pilot 记录、独立神谕测试、证书、ledger 中的 authoritative 条目。
2. `python scripts/ledger.py --validate 结果/results_ledger.json` 与 `--freeze` 均退出码 0。
3. `python scripts/task_cards.py --cards 结果/拆问卡.md --ledger 结果/results_ledger.json` 退出码 0。
4. 写一份**接续说明** `结果/未完成项.md`：哪些问没做、哪些数字尚未冻结、
   下次进 P5–P7 前必须先补什么。没有这份说明，下一轮会把"没做"当成"做过了"。

## 转入完整流程

用户要论文时，直接接 `workflows/paper-only.md`（结果已在账本里）或回到
`workflows/solve-full.md` 的 P5。**不要重跑 P0–P4**——除非 `--stale-check` 报了失效。
