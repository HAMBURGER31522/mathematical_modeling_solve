# LaTeX Fix

1. 建 Task Anchor；从 `开题.md` 确认模板和引擎，运行 `latexmk -xelatex -halt-on-error -interaction=nonstopmode '-auxdir=论文/.latex-build' '-outdir=论文' 论文/main.tex` 并保留首个阻断错误；`auxdir` / `outdir` 参数必须整体加引号，避免 Windows PowerShell 拆参。最终只保留 `论文/main.pdf`，其余编译文件集中在可整目录删除的 `论文/.latex-build/`。
2. 只修首个根因；有参考文献时跑模板要求的完整 bibliography 链，再重新编译至交叉引用收敛。
3. 运行 `python scripts/latex_gate.py 论文/.latex-build/main.log --pdf 论文/main.pdf --aux 论文/.latex-build/main.aux --tex 论文/main.tex --json`；非零则按报告回第 2 步。
4. 运行 `pdftoppm -png 论文/main.pdf 结果/pdf-page`，逐页检查缺图、溢出、遮挡、字体和摘要边界；修后重跑编译与 gate。
