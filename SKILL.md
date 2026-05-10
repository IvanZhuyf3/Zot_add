---
name: zot
description: Add a paper to Zotero library with full metadata, download its PDF, and attach it. Use when user says "zot URL" or wants to save a paper to Zotero with PDF. Triggers: "zot", "add to zotero", "save paper", "import paper". 输入出版商URL，自动提取元数据、添加到Zotero、下载PDF、挂载附件。
allowed-tools: Bash(uv:*), Bash(python:*)
---

# 规则

- 把当前 `SKILL.md` 所在目录视为 `<skill-base>`。所有本地资源（config.yaml）从这里解析。
- **首次使用必须先配置**：`<skill-base>/config.yaml.example` → 复制为 `config.yaml`，填入 Zotero API key 和 library ID。
- Python 依赖：`pyzotero`, `pyyaml`, `rich`, `requests`。首次使用前安装：`pip install pyzotero pyyaml rich requests`。
- 执行命令时，设置 `PYTHONIOENCODING=utf-8` 避免 Windows GBK 编码问题。
- 本工具依赖 [paper_at_home](../Paper_at_home) skill 下载 PDF。paper_at_home 会自动启动浏览器（使用 config.yaml 中的端口和 profile），无需手动启动。
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
set PYTHONIOENCODING=utf-8 && python "<skill-base>/zot.py" "出版商URL"
```

支持任意出版商 URL（paper_at_home 支持的出版商即可）：
- `https://www.nature.com/articles/s41586-023-06139-9`
- `https://opg.optica.org/oe/fulltext.cfm?uri=oe-34-10-18068`
- `https://pubs.acs.org/doi/10.1021/...`
- 等等

**不需要手动提供 DOI**。脚本会自动从页面提取 DOI 并通过 CrossRef API 补全完整元数据。

## Step 3：确认结果

脚本输出五步结果：
1. **Duplicate check** — 如果库中已有（DOI/URL/标题匹配），跳过所有操作
2. `Page metadata: title=..., DOI=...` — 页面元数据已提取
3. `CrossRef enriched: ...` — CrossRef 已补全期刊信息
4. `✓ Zotero item created: XXXXXXXX (type: journalArticle)` — 完整条目已添加
5. `✓ PDF attached: YYYYYYYY` — PDF 已挂载

成功完成后输出机器可读行：
```
ZOT_RESULT: zot_key=XXXXXXXX|att_key=YYYYYYYY|local_pdf=C:\Users\Yifan\Zotero\storage\YYYYYYYY\paper.pdf|title=Paper Title
```

`local_pdf` 指向 Zotero 本地 storage 中的 PDF 文件（需要 Zotero desktop 同步后才存在）。如果 Zotero 尚未同步，`local_pdf` 字段为空。

## 元数据解析流程

1. **页面 meta tags**：解析 `<meta name="citation_*">` 标签，提取 title、DOI、authors、journal 等
2. **CrossRef API**：如果发现 DOI，调用 `api.crossref.org/works/{DOI}` 补全 volume、issue、pages、abstract 等字段
3. **Zotero item**：创建 `journalArticle` 类型（有 DOI 时）或 `webpage` 类型（无 DOI 时），填充所有可用字段
4. **失败容错**：即使 PDF 下载失败，也会先创建 Zotero 条目（保存元数据）

## 故障排查

| 问题 | 原因 | 解决 |
|------|------|------|
| `config.yaml not found` | 未配置 | 复制 example 文件并填写凭据 |
| `zotero.{key} not configured` | 凭据为占位符 | 填入真实值 |
| `403 / Write access denied` | API key 无写权限 | 重新创建 key，勾选 write access |
| `paper_at_home.skill_base not configured` | 路径未填 | config.yaml 填入 paper_at_home 目录的绝对路径 |
| PDF 下载失败 | 浏览器未启动 / 出版商不支持 | paper_at_home 会自动启动浏览器，如仍失败检查 config.yaml 中的 chrome_path |
| 元数据不完整 | 页面无 citation meta tags / CrossRef 无此 DOI | 条目仍会创建，可在 Zotero 中手动补充 |
| `⊘ Duplicate found` | 库中已有该文献 | 正常行为，跳过操作。用 Zotero 查看已有条目 |

# 索引

- 主脚本：`<skill-base>/zot.py`
- 配置模板：`<skill-base>/config.yaml.example`
- 实际配置（gitignored）：`<skill-base>/config.yaml`
- 依赖的 PDF 下载 skill：`../Paper_at_home/`（config.yaml 中 `paper_at_home.skill_base` 指向的目录）
