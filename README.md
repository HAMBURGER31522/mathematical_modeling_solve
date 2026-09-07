# math-modeling-solve

数学建模竞赛的端到端求解 skill：读题 → 数据体检 → 口径审定 → 选模 → 计算 → 证书 →
深度审查 → 图表 → 论文 → 编译合规 → 打包复现。

给 Claude Code / Codex 用。把仓库整个放进 skills 目录即可，`SKILL.md` 在根。

## 设计取舍

**散文越少越好，退出码一个都不能少。**

这不是审美偏好，是实测结论。一份交付物曾自写 `emit_ledger.py`、`figures_mc.py`、
`rules_gate.py` 绕过官方脚本，结果**所有门禁记录都是交付者给自己发的**——
skill 里那些写得完全正确的规范（共享内核、独立神谕、证书分离、三向审计）一条都没真正执行，
而门禁看起来全绿。规范可以被"我读过了、我遵守了"糊弄，`degenerate.py` 退出码 1 糊弄不过去。

所以本 skill 的判据是：**一条规则要留下，要么它是退出码，要么它是换个更强模型重跑仍会犯的错。**
只有某道题会犯的、只有弱模型会犯的，都不进来。按这把尺子，v3.3 把散文从 1423 行砍到约 400 行，
脚本一个没少，还新增了三个。

## 门禁

| 脚本 | 它拦住过什么 |
|---|---|
| `degenerate.py` | 一份 92 项测试全绿、G0–G7 全绿的交付物，n=1 单体自导通 24.7%、阈值敏感性 0，答案错近 70 倍。**统计证书拦不住错的物理，这条 30 秒的检查能** |
| `pkg_scan.py` | 已判「合规全 PASS」的交付包里 `run_mc.py:16` 写着真实口令，差一步推上公开仓库 |
| `certify.py` | 三态证书（可行／已排除／**证据不足**）。区间跨过阈值只能说"证据不足"，不能说"不可行" |
| `ledger.py` + `audit_numbers.py` | 唯一权威答案、依赖哈希冻结、论文↔台账↔结果文件三向审计 |
| `seed_gate.py` | 临界档答案换一批独立随机数还成立吗。漂移即未分辨，必须降档报告 |
| `batch_gate.py` | 长批必须是可恢复状态机。一次性 `pool.map` 赌 18 万任务的脚本从未跑完过 |
| `task_cards.py` | 每问九字段拆问卡，且**验证方式必须早于答案落盘**——有了答案再挑验证方法，挑的一定是刚好能过的那个 |
| `pilot_gate.py` | 定型前每问 2–3 个候选加一个 baseline 真跑一轮，只从跑通的里面定案 |
| `figqa.py` / `latex_gate.py` | 图数与引用、编译阻断项、页数与摘要页程序化核验 |
| `skill_smoke.py` | skill 自己的自检：行数预算、占位符残留、路由断链、薄壳承重结构 |
| `refs_check.py` | 参考文献逐条过 Crossref，编造的引用是 rules 维实打实的失分 |

`scripts/tests/test_contracts.py` 把每个脚本在文档里承诺的行为钉成断言。
**契约测试不过时，"官方脚本不可替代"这句话就是虚假确定性。**

## 赛制参数不在 skill 里

页数、图数、时限这些随赛事变，硬编码就是过拟合。它们在 `开题.md`，每场比赛填一次，
门禁从那里取参数，**没填就报错，不给兜底默认值**。

## 结构

```
SKILL.md        路由入口（description ≤25 行，正文 ≤90 行）
routing.yaml    任务 → workflow，含 other 兜底
CLAUDE.md       薄壳：压缩后唯一幸存的东西，路由表 + Auto-Triggers + Red Flags
CODEX.md        同上
rules/          「我能做 X 吗」——红线，每条「原则 + 检验句」
workflows/      「我现在该做什么」——P0–P7 主链与三条支线
references/     「这个坑怎么避」——按触发条件跳读
scripts/        门禁执行体 + 契约测试
assets/paper/   论文形态契约（cumcmthesis 分节模板，各节带写作合同）
```

## 来源与许可

做法萃取自若干开源数模 skill 的实测赢家维度，全部改写重实现；论文模板与写作契约来自
Mrite（高教社杯 `cumcmthesis`），方法卡来自 Remit（MIT），skill 组织方式参考
skill-based-architecture 与 karpathy-guidelines。逐项落位与许可见
[ATTRIBUTION.md](ATTRIBUTION.md)。深度审查层、红线体系与 `scripts/` 为原创。
