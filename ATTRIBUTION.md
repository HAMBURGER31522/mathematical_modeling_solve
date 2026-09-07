# 来源与许可（ATTRIBUTION）

本 skill 由对多个开源数学建模 skill 的两轮全流程实测评估后融合而成：每个候选在同一竞赛题上完整跑通（两种不同模型各一轮），交付物由独立裁判盲评对照高分基线，萃取实测有效的维度、修复实测暴露的缺陷，并经三个不同模型的独立审查（败因覆盖/执行压力测试/红队）修订。

## 萃取与引入来源（均有 MIT LICENSE 文件）

| 上游项目 | 许可 | 萃取内容 |
|---|---|---|
| [sweetcornna/mathodology](https://github.com/sweetcornna/mathodology) | MIT | 图文质检思想（contact sheet/逐张质检/PDF 检查）、多路线选型比较、迭代预算（每 Gate ≤2 轮、全程 ≤8 轮、decision memo） |
| [zhnnky329/MathModeling-skills](https://github.com/zhnnky329/MathModeling-skills) | MIT | 数字冻结契约（代码→账本→论文单向流）、三向一致性审计、变更影响传播（stale 标记）、方法选型风险探针、反过度主张扫描 |
| [Lupynow/math-modeling-skills](https://github.com/Lupynow/math-modeling-skills) | MIT | 选模与冲突裁决思想、Claim-Evidence 自审框架、去 AI 味写作铁律 |
| Remit `backend/app/core/knowledge/modeling_methods.json` | MIT | 原样引入 `references/method-cards.json`：66 个方法的 assumptions、failure_modes、validation 字段 |

## 仅参考做法/设计思想（未复制任何文本）

- [i3by4t3oyt/Mrite](https://github.com/i3by4t3oyt/Mrite)（含 LICENSE 文件）：`assets/paper/` 引入其 `projects/高教社杯/论文/` 的 `format.cls`、`fonts/` 与分节 tex 结构，并沿用其写作形态契约（摘要字数与一页核验、正文禁分点禁 \textbf、表格列宽通式、9 框流程图、算法选择五段式）。有意差异三处：模型检验章改为六小节、模型评价章缺点按「缺陷—影响—改进」写、附录加 `\label{sec:appendix}` 供页数切分。`main.tex` 另加 numbers.tex 注入位与 `[NUMBERS-MISSING]` 失败标记。
- yushui2022/MathModel-Skill（无许可证）：阶段交接契约、运行清单哈希、结果 JSON 回填正文的设计思想，全部独立重实现并修复其实测缺陷（门禁必须理解统计语义、渲染失败不得静默降级）。
- XiaoMaColtAI/math-modeling-skill（无 LICENSE）与 jihe520/MathModelAgent（自定义非商用条款，禁止二次组合）：**未合入任何内容**；本 skill P7 的编译门禁、复现闭环等相似环节系独立设计，与二者无承继关系。

## 用户自有语料（不随仓库分发）

- `references/abstract-moves.md`：从 12 篇国奖论文摘要（11 张公开获奖论文摘要截图 + 1 篇同题获奖论文首页）逐篇标功能后跨篇对齐得到。仓库只收蒸馏结论，不含语料本身。
- `references/figure-style.md`：从 103 篇期刊图复现文章（97 篇带代码，多数为 R/ggplot2）与其配图对齐得到，只保留跨绘图语言通用的版面与色彩编码规则。样例图目录由使用者在 `开题.md` 指定，不随仓库分发。

## 原创部分（源于两轮 10 次实测的败因归纳与用户自有材料）

- 深度审查层（五问五工件 + M1–M7 家族模块）：来自用户自有草稿，经实测败因映射验证后合入。
- 口径审定阶段（P1）、口径决策表、口径对照实验、语义验收测试。
- 七条算法红线及其判定标准；外部核验工件（声明-实现抽查、跨问一致性、量级对照、私货扫描）。
- 证书-样本预算联动（Δ 来源约束、u ≤ Δ/3）、一次封存终验、不达标处置顺序、双路互证、答案稳定性复核、唯一权威答案。
- 数据体检、降级协议（D0/D1/D2）、时间预算与冻结点、复现闭环。
- `scripts/` 下的全部门禁执行体与契约测试。
  （`assets/paper/` **不在原创之列**——它引自 Mrite，见上文；本仓只在其上做了三处有意差异。）

## 可选运行时依赖（不合入本仓库，运行期按路径/克隆调用）

- ~~figure-forge~~：v3.3 已移除该实现层（A/B 对比评估期属半成品），出图改为按 references/figure-style.md 看样例图模仿，数量与引用仍由 figqa.py 判。
- [math-model-resource-router](https://github.com/HAMBURGER31522/Mathematical_Modeling_Algorithm)（用户自有算法资源路由库）：P2 实现层选库的首选依据——90 个经审计的 GitHub 算法源（钉定 commit、入口路径、许可证据、声明缺口）。查找与降级顺序见 SKILL.md P2 节；不可用时记 N/A 照常自研，功能不受阻断。
