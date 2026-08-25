# Third-Party Notices

本项目自有代码采用 Apache License 2.0，标准文本见仓库根目录 [LICENSE](LICENSE)。本文件只记录 Public Alpha 当前保留或可选使用的第三方代码、图标和资产来源。

第三方代码、图标、依赖和资产仍按各自上游许可证和适用通知执行，不被本项目根目录的 Apache-2.0 LICENSE 覆盖或重新授权。项目 LICENSE 不改变第三方商标、品牌资产或其原始授权边界。

## Tabler Icons

- 来源：[tabler/tabler-icons](https://github.com/tabler/tabler-icons)
- License：MIT
- 仓库路径：`my-ppt-skill/ppt-ai-core/templates/icons/tabler-filled/`、`tabler-outline/`，以及对应的 `my-ppt-skill/templates/ppt-master/icons/` 兼容副本。
- `my-ppt-skill/assets/icons/element-plus/` 中的 40 个兼容命名 SVG 与本地 Tabler outline 图标逐一规范化精确匹配；本仓库按 Tabler-derived compatibility assets 记录，不声明其为 Element Plus 原始文件。

## SVG Repo compatibility set

原 `chunk/` 目录的 SVG 文件带有 SVG Repo 上传工具注释，但缺少逐项作者、条目 URL 和 License。由于无法建立可靠的逐项授权链，`chunk/` 已移出 Public Alpha 工作树并送入回收站，不作为本项目公开资产分发。

## Python dependencies

这些依赖由包管理器安装，未将其源代码 vendored 到仓库；发布时应按实际解析版本复核对应许可证文本和传递依赖：

| 依赖 | 许可证 / 来源 |
|---|---|
| `python-pptx` | MIT；[官方仓库](https://github.com/scanny/python-pptx) |
| `CairoSVG` | LGPL-3.0；[官方仓库](https://github.com/Kozea/CairoSVG) |
| `Pillow` | Pillow License（MIT-CMU）；[官方 License](https://github.com/python-pillow/Pillow/blob/main/LICENSE) |
| `PyMuPDF`（optional `pdf` extra） | AGPL 或 commercial；[官方许可说明](https://github.com/pymupdf/PyMuPDF/blob/main/docs/about.rst) |

`PyMuPDF` 不属于默认安装依赖；只有启用 PDF 输入或 PDF-backed raster fallback 时按 `my-ppt-skill/scripts/requirements-pdf.txt` 安装。
