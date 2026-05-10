# Zot — AGENTS.md

## What This Is

A four-step paper workflow: **metadata extraction → PDF download → Zotero add → PDF attach**.
Given a publisher URL, extracts full bibliographic metadata (via citation meta tags + CrossRef API), downloads the PDF, creates a proper Zotero `journalArticle` item, and attaches the PDF.

## Files

| File | Purpose |
|------|---------|
| `zot.py` | Main orchestration script. Four phases: `extract_metadata()` → `download_pdf()` → `add_to_zotero()` → `attach_pdf()`. |
| `config.yaml` | User credentials (Zotero API key, library ID, paper_at_home path). **Gitignored.** |
| `config.yaml.example` | Template — copy to `config.yaml` and fill in. |
| `SKILL.md` | Agent-facing skill definition. |
| `requirements.txt` | `pyzotero`, `pyyaml`, `rich`, `requests`. |

## Running

```bash
set PYTHONIOENCODING=utf-8 && python zot.py "publisher_URL"
```

## Prerequisites

1. **Zotero API key** with write access → https://www.zotero.org/settings/keys/new
2. **paper_at_home** skill set up and Chromium running (`start_browser.bat`)
3. `config.yaml` created from example and filled in

## Architecture Notes

- **Metadata extraction** (`extract_metadata`): Fetches page HTML with `requests`, parses `<meta name="citation_*">` tags for title/DOI/authors/journal. If DOI found, calls CrossRef API to enrich volume/issue/pages/abstract.
- **Zotero item creation** (`add_to_zotero`): Creates `journalArticle` with all populated fields via `pyzotero.Zotero.create_items()`. Falls back to `webpage` type only when no DOI is found.
- **PDF download** (`download_pdf`): Delegates to `Paper_at_home/main.py` as subprocess with explicit `--config` flag (avoids CWD-relative config loading bug). Parses output with regex to extract file path (handles terminal-wrapped paths).
- **PDF attachment** (`attach_pdf`): Uses `pyzotero.Zotero.attachment_simple()` — handles the multi-step Zotero upload protocol internally.
- Error resilience: if PDF download fails, still creates the Zotero item with metadata. If attachment fails, preserves both item and downloaded PDF with actionable recovery instructions.

## Key Gotchas

- Port 9222 may be reserved by Windows Hyper-V. Paper_at_home config uses port 19222 on this machine.
- paper_at_home's `--config` argparse default must be `None` (not `"config.yaml"`) to avoid loading CWD-relative config when called as subprocess.
- Rich terminal output wraps long PDF paths across lines — the regex uses `[\s\S]+?` to handle this.

## Conventions

- Always `PYTHONIOENCODING=utf-8` on Windows.
- Secrets only in `config.yaml` (gitignored). Never log API keys.
- CrossRef API requires `User-Agent` header with mailto for polite pool.
