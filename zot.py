"""
zot.py — Add paper to Zotero, download PDF, attach it.

Usage:
    set PYTHONIOENCODING=utf-8 && python zot.py "https://doi.org/10.1038/..."
    set PYTHONIOENCODING=utf-8 && python zot.py "https://opg.optica.org/oe/fulltext.cfm?uri=..."

Workflow:
    1. Extract metadata from URL (citation meta tags + CrossRef)
    2. Download PDF via paper_at_home
    3. Create Zotero item with full metadata
    4. Attach PDF to item
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import requests
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
# Step 0: Dedup check
# ---------------------------------------------------------------------------

def check_duplicate(meta: dict, cfg: dict) -> tuple[str | None, str | None]:
    """Check if an item with the same DOI, URL, or title already exists in Zotero.

    Returns (item_key, match_reason) if duplicate found, (None, None) otherwise.
    """
    from pyzotero import zotero as zotero_mod

    zcfg = cfg["zotero"]
    zot = zotero_mod.Zotero(zcfg["library_id"], zcfg.get("library_type", "user"), zcfg["api_key"])

    doi = meta.get("DOI", "").lower().strip()
    title = meta.get("title", "").strip()
    url = meta.get("url", "").strip()

    # Build search queries to try
    queries = []
    if title:
        queries.append(("title", title[:60]))
    if doi:
        queries.append(("DOI", doi))
    if url:
        queries.append(("URL", url.split("?")[0][-60:]))

    for label, query in queries:
        try:
            results = zot.items(q=query, limit=25)
        except Exception:
            continue
        for item in results:
            d = item.get("data", {})
            itype = d.get("itemType", "")
            item_doi = d.get("DOI", "").lower().strip()
            item_title = d.get("title", "").strip()
            item_url = d.get("url", "").strip()

            # Check DOI match (highest confidence)
            if doi and item_doi == doi and itype not in ("attachment", "note"):
                return d["key"], "DOI"

            # Check URL match
            if url and item_url == url and itype not in ("attachment", "note"):
                return d["key"], "URL"

            # Check title match (exact, case-insensitive) on parent items
            if title and item_title and item_title.lower() == title.lower() and itype not in ("attachment", "note"):
                return d["key"], "title"

            # For attachments: check title match, then resolve parent
            if itype == "attachment" and title and item_title:
                if item_title.lower() == title.lower():
                    parent = d.get("parentItem", "")
                    if parent:
                        return parent, "title"

    return None, None


# ---------------------------------------------------------------------------
# Step 1: Extract metadata from URL
# ---------------------------------------------------------------------------
def extract_metadata(url: str) -> dict:
    """Fetch page HTML, parse citation meta tags, enrich via CrossRef if DOI found.

    Returns a dict with keys suitable for pyzotero item_template:
        title, authors (list of str), DOI, url, year, journal, volume, issue, pages, ISSN, abstract, publisher
    """
    meta = {"url": url}

    # 1. Fetch page HTML
    try:
        resp = requests.get(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }, timeout=30)
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        console.print(f"[yellow]⚠ Could not fetch page for metadata: {e}[/yellow]")
        return meta

    # 2. Parse citation meta tags
    def _meta(name: str) -> str:
        """Extract <meta name="..."> content."""
        m = re.search(rf'<meta\s+name="{re.escape(name)}"\s+content="([^"]*)"', html, re.IGNORECASE)
        if not m:
            # Try property= variant (OpenGraph)
            m = re.search(rf'<meta\s+property="{re.escape(name)}"\s+content="([^"]*)"', html, re.IGNORECASE)
        return m.group(1).strip() if m else ""

    meta["title"] = _meta("citation_title") or _meta("og:title")
    meta["DOI"] = _extract_doi_from_text(_meta("citation_doi") or _meta("DOI"))
    meta["journal"] = _meta("citation_journal_title") or _meta("citation_journal_abbrev")
    meta["year"] = _meta("citation_date")[:4] if _meta("citation_date") else ""
    meta["volume"] = _meta("citation_volume")
    meta["issue"] = _meta("citation_issue")
    meta["ISSN"] = _meta("citation_ISSN")
    meta["publisher"] = _meta("citation_publisher")

    # Pages: "firstpage-lastpage" or just "firstpage"
    first = _meta("citation_firstpage")
    last = _meta("citation_lastpage")
    meta["pages"] = f"{first}-{last}" if first and last else (first or "")

    # Authors from multiple <meta name="citation_author"> tags
    author_names = re.findall(r'<meta\s+name="citation_author"\s+content="([^"]*)"', html, re.IGNORECASE)
    if not author_names:
        # Try citation_author given+family pattern
        # Some publishers use separate given/family meta tags
        author_names = re.findall(r'<meta\s+name="dc\.Creator"\s+content="([^"]*)"', html, re.IGNORECASE)
    meta["authors"] = [a.strip() for a in author_names if a.strip()]

    # Abstract (strip HTML tags)
    abstract = _meta("citation_abstract") or _meta("abstract") or _meta("description")
    meta["abstract"] = re.sub(r"<[^>]+>", "", abstract) if abstract else ""

    console.print(f"[dim]  Page metadata: title={meta.get('title','?')[:60]}, DOI={meta.get('DOI','?')}[/dim]")

    # 3. CrossRef enrichment if DOI found
    doi = meta.get("DOI", "")
    if doi:
        crossref = _crossref_lookup(doi)
        if crossref:
            # CrossRef data is more complete — overwrite page metadata
            for key in ("title", "journal", "year", "volume", "issue", "pages", "ISSN", "abstract", "publisher"):
                if crossref.get(key):
                    meta[key] = crossref[key]
            if crossref.get("authors"):
                meta["authors"] = crossref["authors"]
            console.print(f"[dim]  CrossRef enriched: {meta.get('journal','')} {meta.get('year','')} v{meta.get('volume','')}[/dim]")
        else:
            console.print(f"[dim]  CrossRef lookup failed, using page metadata[/dim]")

    return meta


def _extract_doi_from_text(text: str) -> str:
    """Extract a DOI from various text forms."""
    text = text.strip()
    if not text:
        return ""
    # Already a bare DOI
    if re.match(r"^10\.\d{4,}", text):
        return text
    # doi.org URL
    m = re.search(r"doi\.org/(10\.\S+)", text)
    if m:
        return m.group(1)
    # DOI embedded in text
    m = re.search(r"(10\.\d{4,}/\S+)", text)
    if m:
        return m.group(1).rstrip(".;,")
    return text


def _crossref_lookup(doi: str) -> dict | None:
    """Look up DOI on CrossRef API. Returns metadata dict or None."""
    try:
        resp = requests.get(
            f"https://api.crossref.org/works/{doi}",
            headers={"User-Agent": "ZotTool/1.0 (mailto:zot@localhost)"},
            timeout=15,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()["message"]
    except Exception:
        return None

    result = {}

    # Title
    titles = data.get("title", [])
    if titles:
        result["title"] = titles[0]

    # Authors
    authors = []
    for a in data.get("author", []):
        given = a.get("given", "")
        family = a.get("family", "")
        authors.append(f"{given} {family}".strip())
    if authors:
        result["authors"] = authors

    # Journal
    containers = data.get("container-title", [])
    if containers:
        result["journal"] = containers[0]

    # Year
    for field in ("published-print", "published-online", "created"):
        pub = data.get(field, {})
        parts = pub.get("date-parts", [[]])
        if parts and parts[0]:
            result["year"] = str(parts[0][0])
            break

    result["volume"] = data.get("volume", "")
    result["issue"] = data.get("issue", "")
    result["pages"] = data.get("page", "")
    result["publisher"] = data.get("publisher", "")

    issns = data.get("ISSN", [])
    if issns:
        result["ISSN"] = issns[0]

    abstract = data.get("abstract", "")
    if abstract:
        result["abstract"] = re.sub(r"<[^>]+>", "", abstract)

    return result


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

    console.print(f"[dim]Running paper_at_home...[/dim]")
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )

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
    # Path may wrap across lines due to terminal width
    m = re.search(r"(?:Downloaded|Already exists):\s*([\s\S]+?\.pdf)", output)
    if m:
        raw = re.sub(r"\s+", " ", m.group(1)).strip()
        p = Path(raw)
        if p.exists():
            return p
    return None


# ---------------------------------------------------------------------------
# Step 3: Create Zotero item with full metadata
# ---------------------------------------------------------------------------

def add_to_zotero(meta: dict, cfg: dict) -> str:
    """Create a Zotero library item with full metadata. Returns item key."""
    from pyzotero import zotero as zotero_mod

    zcfg = cfg["zotero"]
    zot = zotero_mod.Zotero(zcfg["library_id"], zcfg.get("library_type", "user"), zcfg["api_key"])

    doi = meta.get("DOI", "")
    has_full_meta = bool(meta.get("title") and meta.get("journal"))

    if doi and has_full_meta:
        item_type = "journalArticle"
    else:
        item_type = "journalArticle" if doi else "webpage"

    template = zot.item_template(item_type)

    # Core fields
    template["title"] = meta.get("title", meta.get("url", ""))
    template["url"] = meta.get("url", "")

    if doi:
        template["DOI"] = doi

    if item_type == "journalArticle":
        # Bibliographic fields
        if meta.get("journal"):
            template["publicationTitle"] = meta["journal"]
        if meta.get("year"):
            template["date"] = meta["year"]
        if meta.get("volume"):
            template["volume"] = meta["volume"]
        if meta.get("issue"):
            template["issue"] = meta["issue"]
        if meta.get("pages"):
            template["pages"] = meta["pages"]
        if meta.get("ISSN"):
            template["ISSN"] = meta["ISSN"]
        if meta.get("abstract"):
            template["abstractNote"] = meta["abstract"]
        if meta.get("publisher"):
            template["publisher"] = meta["publisher"]

    # Authors → creators
    authors = meta.get("authors", [])
    if authors:
        template["creators"] = []
        for name in authors:
            parts = name.rsplit(" ", 1)
            if len(parts) == 2:
                template["creators"].append({
                    "creatorType": "author",
                    "firstName": parts[0],
                    "lastName": parts[1],
                })
            else:
                template["creators"].append({
                    "creatorType": "author",
                    "lastName": name,
                })

    resp = zot.create_items([template])
    key = _parse_create_response(resp)
    console.print(f"[green]✓ Zotero item created:[/green] {key}  (type: {item_type}, title: {template.get('title','')[:60]})")
    return key


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
# Step 4: Attach PDF to Zotero item
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
        console.print("Usage: [bold]python zot.py <URL>[/bold]")
        console.print('  python zot.py "https://opg.optica.org/oe/fulltext.cfm?uri=oe-34-10-18068"')
        console.print('  python zot.py "https://www.nature.com/articles/s41586-023-06139-9"')
        console.print('  python zot.py "https://arxiv.org/abs/2301.00001"')
        sys.exit(1)

    url = sys.argv[1]
    cfg = load_config()

    console.print(f"\n[bold cyan]━━━ zot: {url[:80]}{'...' if len(url) > 80 else ''} ━━━[/bold cyan]\n")

    # Step 0: Quick dedup pre-check by URL (before fetching page metadata)
    console.print("[bold]Step 0/4:[/bold] Checking for duplicates...")
    # Extract minimal metadata for dedup (just need DOI/URL/title)
    console.print("[bold]Step 1/4:[/bold] Extracting metadata from page...")
    meta = extract_metadata(url)

    dup_key, dup_reason = check_duplicate(meta, cfg)
    if dup_key:
        console.print(f"[yellow]⊘ Duplicate found:[/yellow] item [bold]{dup_key}[/bold] (matched by {dup_reason})")
        console.print(f"[dim]  Skipping all operations. Use Zotero to view the existing item.[/dim]")
        return

    # Step 2: Download PDF
    console.print(f"\n[bold]Step 2/4:[/bold] Downloading PDF via paper_at_home...")
    try:
        pdf_path = download_pdf(url, cfg)
    except Exception as e:
        console.print(f"[yellow]⚠ PDF download failed: {e}[/yellow]")
        # Still create the item so at least the metadata is saved
        console.print("[dim]Creating Zotero item anyway (no PDF)...[/dim]")
        try:
            item_key = add_to_zotero(meta, cfg)
            console.print(f"[dim]Item {item_key} created. Retry PDF later.[/dim]")
        except Exception as e2:
            console.print(f"[red]Also failed to create item: {e2}[/red]")
        sys.exit(1)

    # Step 3: Create Zotero item with full metadata
    console.print(f"\n[bold]Step 3/4:[/bold] Creating Zotero item...")
    try:
        item_key = add_to_zotero(meta, cfg)
    except Exception as e:
        console.print(f"[red]Failed to create item: {e}[/red]")
        console.print(f"[dim]PDF is at: {pdf_path}[/dim]")
        sys.exit(1)

    # Step 4: Attach PDF
    console.print(f"\n[bold]Step 4/4:[/bold] Attaching PDF to Zotero item {item_key}...")
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
    console.print(f"  Title: {meta.get('title', '?')[:80]}")


if __name__ == "__main__":
    main()
