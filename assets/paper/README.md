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
