# Zot — AGENTS.md

## What This Is

A four-step paper workflow: **dedup check → metadata extraction → PDF download → Zotero add → PDF attach**.
Given a publisher URL, checks for duplicates, extracts full bibliographic metadata (via citation meta tags + CrossRef API), downloads the PDF, creates a proper Zotero `journalArticle` item, and attaches the PDF. Outputs a machine-readable `ZOT_RESULT` line for LLM consumption.

## Files

| File | Purpose |
|------|---------|
| `zot.py` | Main orchestration script. Five phases: `check_duplicate()` → `extract_metadata()` → `download_pdf()` → `add_to_zotero()` → `attach_pdf()`. |
| `config.yaml` | User credentials (Zotero API key, library ID, storage path, paper_at_home path). **Gitignored.** |
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
- **Dedup check** (`check_duplicate`): Searches Zotero library by DOI (priority), URL, and title. Resolves attachment matches to parent items. Skips all operations if duplicate found.
- **Zotero item creation** (`add_to_zotero`): Creates `journalArticle` with all populated fields via `pyzotero.Zotero.create_items()`. Falls back to `webpage` type only when no DOI is found.
- **PDF download** (`download_pdf`): Delegates to `Paper_at_home/main.py` as subprocess with explicit `--config` flag (avoids CWD-relative config loading bug). Parses output with regex to extract file path (handles terminal-wrapped paths).
- **PDF attachment** (`attach_pdf`): Uses `pyzotero.Zotero.attachment_simple()` — handles the multi-step Zotero upload protocol internally.
- **Local path resolution**: After attach, constructs `<storage_path>/<att_key>/<filename>.pdf` from `config.yaml` `zotero.storage_path`.
- **Machine-readable output**: Prints `ZOT_RESULT: zot_key=...|att_key=...|local_pdf=...|title=...` on its own line for LLM parsing.
- Error resilience: if PDF download fails, still creates the Zotero item with metadata. If attachment fails, preserves both item and downloaded PDF with actionable recovery instructions.

## Key Gotchas

- Port 9222 may be reserved by Windows Hyper-V. Paper_at_home config uses port 19222 on this machine.
- paper_at_home's `--config` argparse default must be `None` (not `"config.yaml"`) to avoid loading CWD-relative config when called as subprocess.
- Rich terminal output wraps long PDF paths across lines — the regex uses `[\s\S]+?` to handle this.

## Conventions

- Always `PYTHONIOENCODING=utf-8` on Windows.
- Secrets only in `config.yaml` (gitignored). Never log API keys.
- CrossRef API requires `User-Agent` header with mailto for polite pool.
