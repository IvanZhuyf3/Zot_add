"""
zot.py — Add paper to Zotero, download PDF, attach it.

Usage:
    set PYTHONIOENCODING=utf-8 && python zot.py "https://doi.org/10.1038/..."
    set PYTHONIOENCODING=utf-8 && python zot.py "https://arxiv.org/abs/2301.00001"

Workflow:
    1. Zotero Web API: add item to library → get item key
    2. Paper-at-Home: download PDF via Chromium CDP → get local file path
    3. Zotero Web API: attach PDF to item → done
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import yaml
from rich.console import Console

# Resolve <skill-base> as the directory this script lives in
SKILL_BASE = Path(__file__).resolve().parent
CONFIG_PATH = SKILL_BASE / "config.yaml"
CONFIG_EXAMPLE = SKILL_BASE / "config.yaml.example"

console = Console()


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config() -> dict:
    """Load config.yaml; fail with actionable message if missing."""
    if not CONFIG_PATH.exists():
        console.print("[red]config.yaml not found.[/red]")
        console.print(f"  Copy [bold]{CONFIG_EXAMPLE.name}[/bold] → [bold]config.yaml[/bold] and fill in credentials.")
        console.print(f"  cp {CONFIG_EXAMPLE} {CONFIG_PATH}")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    zot = cfg.get("zotero", {})
    for key in ("library_id", "api_key"):
        val = zot.get(key, "")
        if not val or val.startswith("YOUR_"):
            console.print(f"[red]zotero.{key} not configured in config.yaml[/red]")
            sys.exit(1)
    return cfg


# ---------------------------------------------------------------------------
# Step 1: Add item to Zotero
# ---------------------------------------------------------------------------

def add_to_zotero(url: str, cfg: dict) -> str:
    """Create a Zotero library item from a URL or DOI. Returns item key."""
    from pyzotero import zotero as zotero_mod

    zcfg = cfg["zotero"]
    zot = zotero_mod.Zotero(zcfg["library_id"], zcfg.get("library_type", "user"), zcfg["api_key"])

    is_doi = _looks_like_doi(url)
    item_type = "journalArticle" if is_doi else "webpage"
    template = zot.item_template(item_type)

    if is_doi:
        # Normalize: if user gave a doi.org URL, extract the DOI
        doi = _extract_doi(url)
        template["DOI"] = doi
        template["url"] = url
    else:
        template["url"] = url
        template["title"] = url  # placeholder; Zotero will try to resolve metadata on sync

    resp = zot.create_items([template])
    key = _parse_create_response(resp)
    console.print(f"[green]✓ Zotero item created:[/green] {key}  (type: {item_type})")
    return key


def _looks_like_doi(s: str) -> bool:
    """Heuristic: is this a DOI or a doi.org URL?"""
    s = s.strip().lower()
    return s.startswith("10.") or "doi.org/" in s or "doi:" in s


def _extract_doi(s: str) -> str:
    """Extract bare DOI from various input forms."""
    s = s.strip()
    # doi.org/10.xxx
    m = re.search(r"doi\.org/(10\.\S+)", s)
    if m:
        return m.group(1)
    # doi:10.xxx
    m = re.search(r"doi:\s*(10\.\S+)", s, re.IGNORECASE)
    if m:
        return m.group(1)
    # bare 10.xxx
    if s.startswith("10."):
        return s
    return s


def _parse_create_response(resp: dict) -> str:
    """Extract item key from pyzotero create_items response."""
    if resp.get("successful") and "0" in resp["successful"]:
        return str(resp["successful"]["0"]["key"])
    failed = resp.get("failed", {})
    if failed:
        msg = failed.get("0", {}).get("message", "Unknown API error")
        console.print(f"[red]Zotero API error:[/red] {msg}")
    raise RuntimeError(f"Unexpected Zotero API response: {resp}")


# ---------------------------------------------------------------------------
# Step 2: Download PDF via Paper-at-Home
# ---------------------------------------------------------------------------

def download_pdf(url: str, cfg: dict) -> Path:
    """Call paper_at_home/main.py to download the PDF. Returns local file path."""
    pah = cfg.get("paper_at_home", {})
    skill_base = pah.get("skill_base", "")
    if not skill_base or not Path(skill_base).exists():
        console.print("[red]paper_at_home.skill_base not configured or path doesn't exist[/red]")
        sys.exit(1)

    main_py = Path(skill_base) / "main.py"
    if not main_py.exists():
        console.print(f"[red]main.py not found at {main_py}[/red]")
        sys.exit(1)

    download_dir = pah.get("download_dir", "")
    pah_config = str(Path(skill_base) / "config.yaml")
    cmd = [sys.executable, str(main_py), url, "--config", pah_config]
    if download_dir:
        cmd.extend(["--output", download_dir])

    console.print(f"[dim]Running paper_at_home: {' '.join(cmd[:3])} ...[/dim]")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )

    # Parse output to find downloaded file path
    # paper_at_home outputs like: [OK] Downloaded: C:\path\to\file.pdf
    # or: [SKIP] Already exists: C:\path\to\file.pdf
    pdf_path = _parse_download_output(result.stdout + result.stderr)
    if pdf_path is None:
        console.print("[red]PDF download failed.[/red]")
        console.print(f"[dim]stdout: {result.stdout[-500:]}" if result.stdout else "")
        console.print(f"[dim]stderr: {result.stderr[-500:]}" if result.stderr else "")
        raise RuntimeError("paper_at_home did not produce a PDF file")

    console.print(f"[green]✓ PDF downloaded:[/green] {pdf_path}")
    return pdf_path


def _parse_download_output(output: str) -> Path | None:
    """Find the PDF file path from paper_at_home's console output."""
    # Match "[OK] Downloaded: path" or "[SKIP] Already exists: path"
    m = re.search(r"(?:Downloaded|Already exists):\s*(.+\.pdf)", output)
    if m:
        p = Path(m.group(1).strip())
        if p.exists():
            return p
    return None


# ---------------------------------------------------------------------------
# Step 3: Attach PDF to Zotero item
# ---------------------------------------------------------------------------

def attach_pdf(item_key: str, pdf_path: Path, cfg: dict) -> str:
    """Upload PDF as attachment to Zotero item. Returns attachment key."""
    from pyzotero import zotero as zotero_mod

    zcfg = cfg["zotero"]
    zot = zotero_mod.Zotero(zcfg["library_id"], zcfg.get("library_type", "user"), zcfg["api_key"])

    resp = zot.attachment_simple([str(pdf_path)], parentid=item_key)

    if resp.get("success"):
        att_key = str(resp["success"][0]["key"])
    elif resp.get("unchanged"):
        att_key = str(resp["unchanged"][0]["key"])
    elif resp.get("failure"):
        msg = resp["failure"][0].get("message", "Upload failed")
        raise RuntimeError(f"Attachment upload failed: {msg}")
    else:
        raise RuntimeError(f"Unexpected attachment response: {resp}")

    console.print(f"[green]✓ PDF attached:[/green] {att_key}")
    return att_key


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) < 2:
        console.print("Usage: [bold]python zot.py <URL_or_DOI>[/bold]")
        console.print("  python zot.py \"https://doi.org/10.1038/s41586-023-06139-9\"")
        console.print("  python zot.py \"10.1038/s41586-023-06139-9\"")
        console.print("  python zot.py \"https://arxiv.org/abs/2301.00001\"")
        sys.exit(1)

    url = sys.argv[1]
    cfg = load_config()

    console.print(f"\n[bold cyan]━━━ zot: {url[:80]}{'...' if len(url) > 80 else ''} ━━━[/bold cyan]\n")

    # Step 1: Add to Zotero
    console.print("[bold]Step 1/3:[/bold] Adding to Zotero library...")
    try:
        item_key = add_to_zotero(url, cfg)
    except Exception as e:
        console.print(f"[red]Failed to add item: {e}[/red]")
        sys.exit(1)

    # Step 2: Download PDF
    console.print(f"\n[bold]Step 2/3:[/bold] Downloading PDF via paper_at_home...")
    try:
        pdf_path = download_pdf(url, cfg)
    except Exception as e:
        console.print(f"[yellow]⚠ Item {item_key} added to Zotero, but PDF download failed: {e}[/yellow]")
        console.print(f"[dim]You can retry the attachment later with the item key: {item_key}[/dim]")
        sys.exit(1)

    # Step 3: Attach PDF
    console.print(f"\n[bold]Step 3/3:[/bold] Attaching PDF to Zotero item {item_key}...")
    try:
        att_key = attach_pdf(item_key, pdf_path, cfg)
    except Exception as e:
        console.print(f"[yellow]⚠ Item created and PDF downloaded, but attachment failed: {e}[/yellow]")
        console.print(f"[dim]PDF is at: {pdf_path}[/dim]")
        console.print(f"[dim]Item key: {item_key} — attach manually in Zotero.[/dim]")
        sys.exit(1)

    # Done
    console.print(f"\n[bold green]━━━ Done! ━━━[/bold green]")
    console.print(f"  Item:  {item_key}")
    console.print(f"  PDF:   {att_key}")
    console.print(f"  File:  {pdf_path}")


if __name__ == "__main__":
    main()
