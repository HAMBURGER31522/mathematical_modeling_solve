# 论文模板（高教社杯 / CUMCM 形态契约）

`format.cls` 是 `cumcmthesis` v2.6（国赛标准模板），与 `fonts/`（思源宋体 Bold + Regular）
一并取自 Mrite。**有官方模板时不得用它覆盖官方 class**，只沿用这里的分节装配结构与写作合同。

每个分节 tex 顶部写着**该节专属的写作合同**——照着填就对，不必回头读规范散文。
全文通用的四条（禁分点禁 `\textbf`、表格列宽通式、图宽与 caption、章节间不加 `\newpage`）
在每个文件顶部重复一遍，因为写某一节时只会打开那一个文件。

## 文件

| 文件 | 说明 |
|---|---|
| `main.tex` | 主控，装配全部分节；含 `numbers.tex` 注入位与 `[NUMBERS-MISSING]` 失败标记 |
| `format.cls` + `fonts/` | 国赛样式与字体，不要改 |
| `0.摘要.tex` … `10.附录.tex` | 分节模板，各带本节写作合同 |

## 按问题数装配

模板只预置**问题一**（`5.1.*`）。多一问就复制一次：

```bash
cp 5.1.问题1的建立求解.tex 5.2.问题2的建立求解.tex
cp 5.1.1.分析与准备.tex     5.2.1.分析与准备.tex
cp 5.1.2.建模与求解.tex     5.2.2.建模与求解.tex
# 改文件里的 \input 路径与小节号，再在 5.模型的建立与求解.tex 里加一行 \input
```

问题少于预置数就删掉对应的 `\input` 行。总结建议类的问题不分小节，写自然段落。

## 数字只能从台账来

正文不写裸数字，一律引用宏：

```bash
python scripts/ledger.py --emit-tex 结果/results_ledger.json -o 论文/numbers.tex
```

没生成就编译，`main.tex` 会打出 `[NUMBERS-MISSING]` 而不是静默出一份缺数字的 PDF。
宏携带证书元数据（下界、n、seed、verdict、resolved、Δ、u），机会约束类数字旁必须出现下界值。

## 编译与门禁

```bash
latexmk -xelatex -halt-on-error -interaction=nonstopmode '-auxdir=.latex-build' '-outdir=.' main.tex
python scripts/latex_gate.py 论文/.latex-build/main.log --pdf 论文/main.pdf --aux 论文/.latex-build/main.aux \
       --tex 论文/main.tex --appendix-label sec:appendix --abstract-label abstract:end
```

最终成品只保留 `main.pdf`；其余编译文件全部集中在 `.latex-build/`，确认 PDF 后可整目录删除。

页数上下限从 `开题.md` 读，不写死在这里。`sec:appendix` 与 `abstract:end` 两个 label
不得删除——前者用来切分正文页数与附录页数，后者用来程序化核验摘要恰为一页。

编译不干净时走 `workflows/latex-fix.md`。

## 五处与 Mrite 原版的差异

1. **模型检验章是六小节**（双路互证 / 可核事实对表 / 参数灵敏度 / 样本量与收敛 /
   稳健性对照 / 适用边界），不是原版的"误差分析 + 灵敏度分析"两节。
   对标同题人工基线，检验章体量是全文第二大；压成几句话是我方历史上最大的单项失分。
2. **模型评价章的缺点按「缺陷—影响—改进」写**，并须与降级声明逐条一致：
   凡被降级的结论，此处要写明它的实际强度等级。
3. **附录带 `sec:appendix` 标签**，供门禁切分正文与附录页数。
4. **主文件带 `numbers.tex` 注入位**；缺失时显示 `[NUMBERS-MISSING]`，不静默伪装为完整论文。
5. **不生成目录页**；摘要后直接另起一页进入正文，减少无必要的交付页。


## 2026 版章节装配与流程图规则

第 2 章固定命名为“问题分析”，按题面实际问题数 n，大标题下不写章节总述，直接进入 2.1–2.n 各问题分析；全部问题分析之后再放文章总体思路图。四问时才使用 2.1–2.4。问题分析小节只解释题型、变量关系、方法路线和验证接口，不提前写模型结果。

第 5 章按题面实际问题数 n 分别装配。以问题一为种子时，assets/paper/5.1.问题1的建立求解.tex 先输出“问题一的模型的建立和求解”标题，紧接问题一流程图（流程图不设置小标题），然后输入 5.1.1.分析与准备.tex 的“模型准备”，再输入 5.1.2.建模与求解.tex 的模型建立和模型求解。问题二至第 n 问分别复制同一结构为 5.2.* 至 5.n.*，同步修改节号、问题文字、图表标签和 input 路径；不能只复制流程图而漏掉模型准备或模型求解。

流程图使用 main.tex 已配置的原生 TikZ、positioning、arrows.meta 和 shapes.geometric 库。节点尺寸固定，箭头方向明确；第 5 章各问流程图留在对应的 5.i 标题下，不前移到第 2 章。生成图后仍需在正文中引用并写出“现象—原因—意义”解读。

## 2026 版 AI 声明、附录与支撑材料

第 8 章只保留“模型的改进”，删除“模型的推广”。其中的“AI工具使用声明”已经位于参考文献之前；不要新增、移动或在附录重复该声明。

实际使用 AI 时，保留真实、简短的用途说明，并在支撑材料中提交由 `assets/supporting-materials/AI工具使用详情.tex` 编译得到的 `AI工具使用详情.pdf`。详细工具、版本、交互、采纳/修改和人工核验不写进论文附录。未使用 AI 时，改用未使用声明，不提交该 PDF。

附录的职责是列出支撑文件、实际环境、复现入口和核心代码节选；完整可运行源码放在 `支撑材料/source/`。`10.附录.tex` 的 `app:support-files`、`app:core-code` 和 `app:reproduction` 标签对应 `assets/delivery/delivery-manifest.json`；实际使用 AI 时还使用 `app:ai-details`。竞赛已提供的原始数据不重复提交，自行获得的数据和大结果按需放入支撑材料。

打包时按 `references/competition-delivery.md` 组装 `交付/`，再运行：

```bash
python scripts/delivery_gate.py 交付/ --appendix-source 论文/10.附录.tex \
  --out 结果/gates/G7-交付清单.json
python 交付/reproduce.py
python scripts/pkg_scan.py 交付/ --out 结果/gates/G7-出门扫描.json
```

门禁只验证结构与路径关系；科学结论、真实 AI 记录、完整复现、数据来源和匿名性仍须人工核验。
