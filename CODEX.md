# CODEX.md

## Quick Routing
| Task | Required reads | Workflow |
|---|---|---|
| 完整数模解题 | `rules/modeling-redlines.md` + `rules/execution-discipline.md` | `workflows/solve-full.md` |
| 基于已验证结果写论文 | 同上 | `workflows/paper-only.md` |
| LaTeX 编译或版面修错 | 同上 | `workflows/latex-fix.md` |
| Gate 失败排查 | 同上 | `workflows/gate-triage.md` |
| Other | 同上 | `workflows/task-execution.md` |

## Auto-Triggers
- **同会话新任务重走路由**：重读 `routing.yaml`，只匹配一条 route；无匹配走 `other`。
- 上下文压缩或中断：重读当前 workflow、Task Anchor 与决定下一步所需证据。
- 声明非简单任务完成前：重跑 Done When 对应命令并读取退出码。

## Red Flags — STOP
- “测试和 Gate 都绿，所以题意一定正确” -> 停止，运行退化探针与现实判别实验。
- “已在论文披露，可以带着红线继续” -> 停止；披露不构成修复。
- “自写一个等价检查也算官方门禁” -> 停止；回到 `scripts/` 的执行体。
