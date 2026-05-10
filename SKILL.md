---
name: zot
description: Add a paper to Zotero library, download its PDF, and attach it. Use when user says "zot URL" or wants to save a paper to Zotero with PDF. Triggers: "zot", "add to zotero", "save paper", "import paper". 输入URL或DOI，自动添加到Zotero、下载PDF、挂载附件。
allowed-tools: Bash(uv:*), Bash(python:*)
---

# 规则

- 把当前 `SKILL.md` 所在目录视为 `<skill-base>`。所有本地资源（config.yaml）从这里解析。
- **首次使用必须先配置**：`<skill-base>/config.yaml.example` → 复制为 `config.yaml`，填入 Zotero API key 和 library ID。
- Python 依赖：`pyzotero`, `pyyaml`, `rich`。首次使用前安装：`pip install pyzotero pyyaml rich`。
- 执行命令时，设置 `PYTHONIOENCODING=utf-8` 避免 Windows GBK 编码问题。
- 本工具依赖 [paper_at_home](../Paper_at_home) skill 下载 PDF。确保 Chromium 已启动（`start_browser.bat`）。
- Zotero API key 需要写权限。在 https://www.zotero.org/settings/keys/new 创建，勾选 "Allow write access"。

# 工作流程

## Step 1：配置检查

如果 `<skill-base>/config.yaml` 不存在或未填入真实凭据，引导用户：

```bash
cp "<skill-base>/config.yaml.example" "<skill-base>/config.yaml"
# 然后编辑 config.yaml，填入 zotero.library_id 和 zotero.api_key
```

## Step 2：执行 zot 命令

```bash
set PYTHONIOENCODING=utf-8 && python "<skill-base>/zot.py" "URL或DOI"
```

支持的输入格式：
- DOI：`10.1038/s41586-023-06139-9`
- DOI URL：`https://doi.org/10.1038/s41586-023-06139-9`
- 出版商 URL：`https://www.nature.com/articles/s41586-023-06139-9`
- arXiv：`https://arxiv.org/abs/2301.00001`

## Step 3：确认结果

脚本输出三步结果：
1. `✓ Zotero item created: XXXXXXXX` — 条目已添加
2. `✓ PDF downloaded: C:\path\to\file.pdf` — PDF 已下载
3. `✓ PDF attached: YYYYYYYY` — PDF 已挂载

如果某步失败，脚本会报错并给出后续操作建议。

## 故障排查

| 问题 | 原因 | 解决 |
|------|------|------|
| `config.yaml not found` | 未配置 | 复制 example 文件并填写凭据 |
| `zotero.{key} not configured` | 凭据为占位符 | 填入真实值 |
| `403 / Write access denied` | API key 无写权限 | 重新创建 key，勾选 write access |
| `paper_at_home.skill_base not configured` | 路径未填 | config.yaml 填入 paper_at_home 目录的绝对路径 |
| PDF 下载失败 | Chromium 未启动 / 出版商不支持 | 先启动 `start_browser.bat`，参考 paper_at_home 的 SKILL.md |

# 索引

- 主脚本：`<skill-base>/zot.py`
- 配置模板：`<skill-base>/config.yaml.example`
- 实际配置（gitignored）：`<skill-base>/config.yaml`
- 依赖的 PDF 下载 skill：`../Paper_at_home/`（SKILL.md 中 `paper_at_home.skill_base` 指向的目录）
