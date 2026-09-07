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
1. `rules/modeling-redlines.md`
2. `rules/execution-discipline.md`
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
