# CODEX

正式文档在本仓根目录：先读 `SKILL.md`（`primary: true`），任务明确属于别的 skill 时才切换。

<!-- 下面的 XML 标签是承重的：LLM 把标签块当离散硬约束段落解析，
     压缩后比纯 markdown 标题可靠。薄壳的全部意义就是压缩后只剩它。 -->

<always-applicable>

**Always Read（每个任务，选路由之前）**

1. `rules/modeling-redlines.md`
2. `rules/execution-discipline.md`

赛事参数只从 `开题.md` 取；门禁判定只认 `scripts/` 的退出码，不认复述。

</always-applicable>

<task-routing>

## Quick Routing
| Task | Required reads | Workflow |
|---|---|---|
| 完整数模解题 | `rules/modeling-redlines.md` + `rules/execution-discipline.md` | `workflows/solve-full.md` |
| 基于已验证结果写论文 | 同上 | `workflows/paper-only.md` |
| LaTeX 编译或版面修错 | 同上 | `workflows/latex-fix.md` |
| Gate 失败排查 | 同上 | `workflows/gate-triage.md` |
| Other | 同上 | `workflows/task-execution.md` |

</task-routing>

## Auto-Triggers
- **同会话新任务重走路由**：重读 `routing.yaml`，只匹配一条 route；无匹配走 `other`。
- 上下文压缩或中断：重读当前 workflow、Task Anchor 与决定下一步所需证据。
- 声明非简单任务完成前：重跑 Done When 对应命令并读取退出码。

## Red Flags — STOP
- “测试和 Gate 都绿，所以题意一定正确” -> 停止，运行退化探针与现实判别实验。
- “已在论文披露，可以带着红线继续” -> 停止；披露不构成修复。
- “自写一个等价检查也算官方门禁” -> 停止；回到 `scripts/` 的执行体。
- “证书自报 resolved=false，但先写论文，样本回头再补” -> 停止。未分辨就降精度报告，不许挂账——这条借口在实测中真实出现过。
