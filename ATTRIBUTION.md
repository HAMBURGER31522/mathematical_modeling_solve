# 来源与许可（ATTRIBUTION）

本 skill 由对多个开源数学建模 skill 的两轮全流程实测评估后融合而成：每个候选在同一竞赛题上完整跑通（两种不同模型各一轮），交付物由独立裁判盲评对照高分基线，萃取实测有效的维度、修复实测暴露的缺陷，并经三个不同模型的独立审查（败因覆盖/执行压力测试/红队）修订。

## 萃取来源（均有 MIT LICENSE 文件；做法全部改写重实现，未复制上游文本）

| 上游项目 | 许可 | 萃取内容 |
|---|---|---|
| [sweetcornna/mathodology](https://github.com/sweetcornna/mathodology) | MIT | 图文质检思想（contact sheet/逐张质检/PDF 检查）、多路线选型比较、迭代预算（每 Gate ≤2 轮、全程 ≤8 轮、decision memo） |
| [zhnnky329/MathModeling-skills](https://github.com/zhnnky329/MathModeling-skills) | MIT | 数字冻结契约（代码→账本→论文单向流）、三向一致性审计、变更影响传播（stale 标记）、方法选型风险探针、反过度主张扫描 |
| [Lupynow/math-modeling-skills](https://github.com/Lupynow/math-modeling-skills) | MIT | 选模与冲突裁决思想、Claim-Evidence 自审框架、去 AI 味写作铁律 |

## 仅参考做法/设计思想（未复制任何文本）

- [Rzna-5559/Mrite](https://github.com/Rzna-5559/Mrite)：仓库无 LICENSE 文件，仅 README 声明 MIT 而无授权正文，从严按"仅参考做法"处理（证据快照见融合仓库 scorecards/license-evidence-mrite.md，含访问日期）。参考的做法：求解计划先行、两阶段执行（先算后画）、xelatex 编译错误门禁、排版优化循环、摘要页数 aux 验证。
- yushui2022/MathModel-Skill（无许可证）：阶段交接契约、运行清单哈希、结果 JSON 回填正文的设计思想，全部独立重实现并修复其实测缺陷（门禁必须理解统计语义、渲染失败不得静默降级）。

## 原创部分（源于两轮 10 次实测的败因归纳与用户自有材料）

- 深度审查层（五问五工件 + M1–M7 家族模块）：来自用户自有草稿，经实测败因映射验证后合入。
- 口径审定阶段（P1）、口径决策表、口径对照实验、语义验收测试。
- 七条算法红线及其判定标准；外部核验工件（声明-实现抽查、跨问一致性、量级对照、私货扫描）。
- 证书-样本预算联动（Δ 来源约束、u ≤ Δ/3）、一次封存终验、不达标处置顺序、双路互证、答案稳定性复核、唯一权威答案。
- 数据体检、降级协议（D0/D1/D2）、时间预算与冻结点、复现闭环。
- `scripts/` 全部辅助脚本（certify / ledger / audit_numbers / figqa / latex_gate）与 `assets/paper-skeleton.tex`。
