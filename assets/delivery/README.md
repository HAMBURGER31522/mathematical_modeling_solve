# 交付清单模板

将 `delivery-manifest.json` 复制到最终 `交付/` 根目录，再按实际包内容填写。示例展示“实际使用 AI 且有自行获得数据”的路径；未使用 AI 时，将 `ai_use.used` 改为 `false`，删除 `details_pdf` 和 `ai_tool_use_details` 条目。没有自行获得的数据或大结果时，删除对应条目，不要留假文件。

`source_code` 必须指向 `支撑材料/source/` 下的完整可运行项目，`entrypoints` 是其中实际运行的入口；论文附录只展示核心代码。所有路径必须是包内的 `/` 相对路径。

在最终包上运行：

```bash
python scripts/delivery_gate.py 交付/ --appendix-source 论文/10.附录.tex \
  --out 结果/gates/G7-交付清单.json
```

门禁检查存在性、边界和附录关系，仍需人工运行 `reproduce.py`、检查匿名和核验科学内容。完整规则见 `references/competition-delivery.md`。
