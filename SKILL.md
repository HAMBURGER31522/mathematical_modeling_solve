---
name: math-modeling-solve
description: >
  Use when 用户提供数学建模竞赛题、附件或论文工程，并要求"完整解题并写论文"、
  "只生成数模论文"、"修一下 LaTeX 编译错误"或"看看这个门禁为什么没过"；
  也在请求涉及赛题拆解、真实计算结果、证书、图表、论文或交付包时使用。
primary: true
---

# Math Modeling Solve v3.3

把赛题推进为可复核、可编译、可复现的提交物；路径由任务意图决定。

<always-applicable>

## Always Read
<!-- ALWAYS_READ_START -->
无固定必读。规则按路由带：每条任务在 `routing.yaml` 里声明自己的 `required_reads`，workflow 在到达对应阶段时才拉取知识。
这样纯排版或门禁排查不会被迫读完建模红线。
<!-- ALWAYS_READ_END -->

## Session Discipline
每个新任务，包括同会话里的新请求，都重读 `routing.yaml`，按 labels、trigger_examples 与意图只匹配一条路由；无匹配走 `other`，不预读无关 reference。
非简单任务先写 Task Anchor：Goal、Boundaries、Done When；再用原生 Plan 推进，每步只以新证据标完成。中断或压缩后重读当前 workflow 与决定下一步所需的证据。
检验：本轮所读 workflow 是否正是 `routing.yaml` 唯一命中的条目，当前动作是否直接服务 Task Anchor？

</always-applicable>

<task-routing>

## Common Tasks
<!-- ROUTING_SUMMARY_START -->
- For each new task, read `routing.yaml`, match exactly one route by `labels`, `trigger_examples`, and task intent, fall back to `other`, and follow only that route's `workflow`. A task route does not preload knowledge.
<!-- ROUTING_SUMMARY_END -->

</task-routing>

## Known Gotchas
- 机械门禁全绿仍可能解错问题；先跑退化探针并让口径撞现实 → [gotchas](references/gotchas.md#green-gates-wrong-problem)
- 行序、数组位置或显示标签不能代替语义身份 → [gotchas](references/gotchas.md#semantic-identity)
- 长计算没有检查点会把已用机时变成全损风险 → [gotchas](references/gotchas.md#all-or-nothing-batches)
- 随机几何/渗流题另有领域陷阱，命中后再读 → [gotchas](references/gotchas.md#random-geometry--percolation)

## Project Boundaries
- 本 skill 管读题、求解、证书、图表、论文、编译门禁与交付复现；用户拥有题意裁决、赛事参数和最终提交决定。
- `开题.md` 是赛事参数唯一来源；`scripts/` 是官方门禁执行体；`assets/` 是论文形态与复现模板，不在正文规则中复制其细节。
- reference 只在 workflow 的触发点按需读；代码或文档自称 PASS 不能覆盖脚本退出码与科学证据。
- `rules/` 只收稳定约束，`workflows/` 只收有序步骤，`references/` 只收可泛化且带触发条件的知识；会话历史、调试过程与实验记录一律不写进本 skill——那是 git 与实验室仓的事。


## 2026 数学建模论文模板规则

当任务需要写论文模板或从 Word 参照迁移到 LaTeX 时，先读 `references/competition-delivery.md`；竞赛 PDF 是交付规则的唯一上位来源，提示词文档只提供可选质量建议。

1. 第 2 章命名为“问题分析”。按题面实际问题数 $n$，大标题下直接写 2.1–2.$n$ 各问题的分析，不设置章首总述；全部问题分析完成后再放文章总体思路图。四问时才使用 2.1–2.4。问题分析只解释题型、变量关系、方法路线和验证接口，不提前写模型结果。
2. 第 5 章按题面实际问题数 $n$ 分别装配 5.1–5.$n$。每个 5.i 文件先输出“问题 i 的模型的建立和求解”标题，标题下直接放该问题的流程图，不为流程图设置小标题；流程图之后进入 5.i.1 模型准备，再继续 5.i.2 模型建立和 5.i.3 模型求解。问题二至第 $n$ 问复制问题一的同一套文件和结构，调整节号、问题文字、图表标签和 input 路径。
3. 流程图采用 LaTeX 原生 TikZ，使用 positioning、arrows.meta 和 shapes.geometric；节点尺寸固定，箭头清晰，图题由 caption 提供，流程图在正文中必须有引用和现象—原因—意义解读。第 2 章只放总体思路图，各问流程图留在对应 5.i 标题下。
4. 第 8 章删除“模型的推广”，只保留“模型的改进”；现有简要 AI 工具使用声明已位于参考文献之前，保持其位置。实际使用 AI 时，详细记录只放支撑材料中的 `AI工具使用详情.pdf`；未使用 AI 时不提交该 PDF，也不补造声明。
5. 附录列出支撑材料、实际环境、复现入口和核心代码节选；完整可运行源码放在 `支撑材料/source/`。保留 `sec:appendix` 标签、数字台账和现有门禁。
6. 摘要按 `references/abstract-emphasis.md` 做语义稀疏加重，不设固定粗体数量；图表只保留支撑结论的真实图，不接受固定页数、图数、工具或多格式配额。

Word 参照模板中的提示性文字是写作规范，不是待提交的具体结果。不要把示例数字、示例工具日期、示例文件名或示例结论写成事实；模板只提供占位符和填写方向。
