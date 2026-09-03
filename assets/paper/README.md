# 分节论文模板包（assets/paper/）

无官方模板且中文写作时的默认起点。**有官方模板时以官方 class 为准**，本包只贡献「分节装配」这一结构。

## 为什么分节而不是单文件

基线 A 的论文与 `Rzna-5559/Mrite` 的模板都是分节 `.tex` + 主控编译（spec §9 把这条链路定为必抽片段）。
分节的收益不是美观，而是：

- **编译错误可定位**：`main.log` 的行号落在某一节文件里，不用在千行单文件里翻。
- **可并行写作**：出数的问和还在算的问互不阻塞，先写完的先编译验证。
- **可增量重编**：改一节不必重排全文，修错循环变快。
- **粒度可调**：某一问写长了就拆成「分析与准备 / 建模与求解」两片，改 `main.tex` 一行 `\input`。

## 用法

1. 拷贝整个目录到 `论文/`，按题目改 `main.tex` 的标题与 `\input` 清单（问数不是四问就删/加）。
2. 先跑通台账：`python scripts/ledger.py --emit-tex 结果/results_ledger.json -o 论文/numbers.tex`。
3. 再写正文。**正文里每个数字都引用宏**，不手抄。
4. 编译：`latexmk -xelatex -halt-on-error -interaction=nonstopmode main.tex`，**检查退出码**。
5. 过门禁：`python scripts/latex_gate.py 论文/main.log --aux 论文/main.aux`。

## 编译修错循环（照这个顺序修，别乱试）

| 症状 | 真因 | 修法 |
|---|---|---|
| 一片 `Undefined control sequence`，但 `numbers.tex` 里明明有 | `main.tex` 漏了 `\input{numbers.tex}` | 补上那一行——先查这个，别急着改宏 |
| `Undefined control sequence` 且宏名含数字 | LaTeX 宏名不允许数字（`\qNum1` 非法） | 台账键改纯字母驼峰，重新发射 |
| `numbers.tex` 加载到一半报错 | 发射器写出了非法宏名或未转义字符 | 找 log 里**第一条**错误，之后的都是连锁反应 |
| `Undefined reference/citation` | 交叉引用未收敛 | 编译两遍；有 bib 走 xelatex→biber→xelatex 两遍 |
| `Missing character` / 缺字形 | 字体不含该字形 | 换系统可用字体并写回退链，**不许静默降级** |
| `Overfull \hbox` | 长公式 / 长表 / 长 URL | 公式断行、表用 `tabularx`、URL 用 `\url` 断字 |
| `Float too large` | 图尺寸超版心 | 用 `width=0.9\linewidth`，别用绝对尺寸 |
| PDF 里出现空图框 | 图文件缺失或路径错 | log 里**没有**对应报错，靠 `figqa.py` + 目检抓 |

残余的非阻断 warning 记进 `结果/编译白名单.md` 并写明理由；复检时不得新增。

## 与门禁的对接

- G6（论文）：`audit_numbers.py` 做论文↔台账↔结果文件三向审计，引用 stale 键 = fail。
- G7（编译打包）：`latex_gate.py` 分类阻断项，清零才过；摘要页数从 `.aux` 程序化核实。
