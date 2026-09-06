# Other Task Execution

1. 写 Task Anchor：Goal、Boundaries、Done When；运行 `rg -n "<任务关键词>" SKILL.md routing.yaml rules workflows references` 收集最小证据。
2. 若证据命中完整求解、论文、LaTeX 或门禁意图，改走对应 route；否则列出最小产物与验证命令后执行。
3. 只读决定当前动作的 reference；涉及数字、声明、图或提交时分别执行 ledger、审计、figqa 或 pkg_scan 官方命令。
4. 用 Done When 指定的命令复验并报告实际退出码；新任务到来时丢弃本路线并重走 `routing.yaml`。
