# Zot — AGENTS.md

## What This Is

A three-step paper workflow: **Zotero add → PDF download → PDF attach**.
Wraps the Zotero Web API (via `pyzotero`) and the `Paper_at_home` skill into one command.

## Files

| File | Purpose |
|------|---------|
| `zot.py` | Main orchestration script. Three phases: `add_to_zotero()` → `download_pdf()` → `attach_pdf()`. |
| `config.yaml` | User credentials (Zotero API key, library ID, paper_at_home path). **Gitignored.** |
| `config.yaml.example` | Template — copy to `config.yaml` and fill in. |
| `SKILL.md` | Agent-facing skill definition. |
| `requirements.txt` | `pyzotero`, `pyyaml`, `rich`. |

## Running

```bash
# Must set encoding on Windows
set PYTHONIOENCODING=utf-8 && python zot.py "URL_or_DOI"
```

## Prerequisites

1. **Zotero API key** with write access → https://www.zotero.org/settings/keys/new
2. **paper_at_home** skill set up and Chromium running (`start_browser.bat`)
3. `config.yaml` created from example and filled in

## Architecture Notes

- `zot.py` calls `pyzotero.Zotero.create_items()` with `item_template("journalArticle")` for DOIs or `item_template("webpage")` for generic URLs.
- PDF attachment uses `pyzotero.Zotero.attachment_simple()` — handles the multi-step Zotero upload protocol internally.
- PDF download delegates to `Paper_at_home/main.py` as a subprocess; output is parsed with regex to extract the file path.
- If step 2 or 3 fails, earlier steps are preserved (item exists in Zotero, PDF exists on disk) with actionable error messages.

## Conventions

- Always `PYTHONIOENCODING=utf-8` on Windows.
- Secrets only in `config.yaml` (gitignored). Never log API keys.
- DOI detection: starts with `10.` or contains `doi.org/`.
