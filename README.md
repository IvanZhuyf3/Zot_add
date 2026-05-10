# Zot

Paper workflow: **dedup → metadata extraction → PDF download → Zotero attach**.

Give it a publisher URL, it checks for duplicates, extracts full bibliographic metadata (via citation meta tags + CrossRef API), downloads the PDF via Chromium, creates a proper `journalArticle` item in your Zotero library, and attaches the PDF. Outputs a machine-readable `ZOT_RESULT` line for LLM consumption.

## Quick Start

```bash
# 1. Configure
cp config.yaml.example config.yaml
# Edit config.yaml — fill in Zotero API key, library ID, paper_at_home path

# 2. Install dependencies
pip install pyzotero pyyaml rich requests

# 3. Run (browser auto-starts from paper_at_home config.yaml)
set PYTHONIOENCODING=utf-8 && python zot.py "https://www.nature.com/articles/s41586-023-06139-9"
```

Output:

```
Step 1/4: Extracting metadata from page...
  Page metadata: title=Transfer learning enables predictions..., DOI=10.1038/s41586-023-06139-9
  CrossRef enriched: Nature 2023 v618

Step 2/4: Downloading PDF via paper_at_home...
✓ PDF downloaded: ...\Transfer learning enables predictions in network biology.pdf

Step 3/4: Creating Zotero item...
✓ Zotero item created: XXXXXXXX (type: journalArticle, title=Transfer learning enables...)

Step 4/4: Attaching PDF to Zotero item XXXXXXXX...
✓ PDF attached: YYYYYYYY

━━━ Done! ━━━
```

## How It Works

| Step | What happens |
|------|-------------|
| **Dedup check** | Searches Zotero library by DOI, URL, and title. Skips all operations if duplicate found. |
| **Metadata extraction** | Fetches page HTML, parses `<meta name="citation_*">` tags. If DOI found, calls CrossRef API to enrich journal/volume/issue/pages/abstract. |
| **PDF download** | Delegates to [paper_at_home](https://github.com/IvanZhuyf3/Literature_downloader_skill) — Chromium CDP with real browser session. Handles JS challenges, institutional logins, 20+ publishers. |
| **Zotero item creation** | Creates `journalArticle` (with DOI) or `webpage` (without), populated with all extracted metadata via pyzotero. |
| **PDF attachment** | Uploads PDF to Zotero via `attachment_simple()`. Resolves local storage path. |

If the PDF download fails, the Zotero item is still created with metadata — you can attach the PDF later.

## Configuration

`config.yaml` (gitignored — copy from `config.yaml.example`):

```yaml
zotero:
  library_id: "YOUR_LIBRARY_ID"      # numeric, from zotero.org/settings/keys
  api_key: "YOUR_API_KEY"            # needs write access
  library_type: "user"               # "user" or "group"
  storage_path: "C:\\Users\\you\\Zotero\\storage"  # local Zotero storage for local_pdf output

paper_at_home:
  skill_base: "C:\\path\\to\\Paper_at_home"
  download_dir: "C:\\Users\\you\\Downloads\\temp"
```

### Zotero API Key

1. Go to https://www.zotero.org/settings/keys/new
2. Check **Allow library access** → **Allow write access**
3. Copy the key and your user ID into `config.yaml`

## Machine-Readable Output

On success, the script prints a `ZOT_RESULT` line for LLM/automation consumption:

```
ZOT_RESULT: zot_key=XXXXXXXX|att_key=YYYYYYYY|local_pdf=C:\Users\you\Zotero\storage\YYYYYYYY\paper.pdf|title=Paper Title
```

| Field | Description |
|-------|-------------|
| `zot_key` | Zotero item key |
| `att_key` | PDF attachment key |
| `local_pdf` | Absolute path to PDF in local Zotero storage (empty if Zotero hasn't synced yet) |
| `title` | Paper title (truncated to 100 chars) |

## Dependencies

- Python 3.11+
- `pyzotero` — Zotero Web API client
- `pyyaml` — config loading
- `rich` — terminal output
- `requests` — page metadata fetch + CrossRef API
- [paper_at_home](https://github.com/IvanZhuyf3/Literature_downloader_skill) — PDF download engine (separate project)

## Project Structure

```
zot.py               # Main script — 4-step orchestration
config.yaml.example   # Configuration template
config.yaml           # Actual config (gitignored)
SKILL.md              # Agent-facing skill definition (for OpenCode)
AGENTS.md             # Repo knowledge base
requirements.txt      # Python dependencies
```
