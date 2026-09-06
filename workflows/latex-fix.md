# LaTeX Fix

1. 建 Task Anchor；从 `开题.md` 确认模板和引擎，运行 `latexmk -xelatex -halt-on-error -interaction=nonstopmode 论文/main.tex` 并保留首个阻断错误。
2. 只修首个根因；有参考文献时跑模板要求的完整 bibliography 链，再重新编译至交叉引用收敛。
3. 运行 `python scripts/latex_gate.py 论文/main.log --pdf 论文/main.pdf --aux 论文/main.aux --tex 论文/main.tex --json`；非零则按报告回第 2 步。
4. 运行 `pdftoppm -png 论文/main.pdf 结果/pdf-page`，逐页检查缺图、溢出、遮挡、字体和摘要边界；修后重跑编译与 gate。
