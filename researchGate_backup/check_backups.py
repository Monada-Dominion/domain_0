#!/usr/bin/env python3
"""
check_backups.py

Scans the domain_0 repo for publication files, cross-references them
against the authoritative rg_publications.json (and optionally a saved
rg_profile.html), and writes a full bidirectional status table to README.md.

Directions checked:
  1. RG → Repo : publication is on ResearchGate — is it backed up locally?
  2. Repo → RG : file is in the repo — does it match a known RG publication?
"""
import os
import re
import json
import html
from datetime import datetime

try:
    from PyPDF2 import PdfReader
    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False
    print("Warning: PyPDF2 not installed. PDF title extraction disabled.")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCRIPT_DIR     = os.path.dirname(os.path.abspath(__file__))
DOMAIN_0_DIR   = os.path.dirname(SCRIPT_DIR)
RG_BACKUP_DIR  = SCRIPT_DIR
OTHER_PUBS_DIR = os.path.join(DOMAIN_0_DIR, "other_publications")
README_PATH    = os.path.join(RG_BACKUP_DIR, "README.md")
RG_JSON_PATH   = os.path.join(RG_BACKUP_DIR, "rg_publications.json")

IGNORED_EXTS  = {'.py', '.sh', '.html', '.webp', '.png', '.jpg',
                 '.jpeg', '.gif', '.svg', '.yml', '.yaml', '.json',
                 '.txt', '.toml', '.cfg', '.ini'}
IGNORED_FILES = {"README.md", "LICENSE", ".gitignore", ".DS_Store"}

# Lines that are RG watermark/header noise — skip these when extracting titles
RG_NOISE_PATTERNS = [
    r"see discussions",
    r"researchgate\.net",
    r"www\.researchgate",
    r"^https?://",
    r"stats and author",
    r"author pr ofiles",
    r"public ation",
]


# ---------------------------------------------------------------------------
# PDF title extraction
# ---------------------------------------------------------------------------
def _is_noise_line(line):
    low = line.lower()
    return any(re.search(p, low) for p in RG_NOISE_PATTERNS)


def extract_pdf_title(pdf_path):
    """Return the real title from a PDF, skipping RG watermark lines."""
    if not PYPDF2_AVAILABLE:
        return None
    try:
        reader = PdfReader(pdf_path)
        # 1. PDF metadata title (most reliable)
        if reader.metadata:
            meta = reader.metadata.get("/Title") or reader.metadata.get("title")
            if meta and meta.strip() and not _is_noise_line(meta):
                return meta.strip()
        # 2. First meaningful non-noise line across first 3 pages
        for page in reader.pages[:3]:
            text = page.extract_text() or ""
            for line in text.splitlines():
                line = line.strip()
                if len(line) > 8 and not _is_noise_line(line):
                    return line
    except Exception as e:
        print(f"  [warn] Could not read PDF {os.path.basename(pdf_path)}: {e}")
    return None


# ---------------------------------------------------------------------------
# Fuzzy / Jaccard matching
# ---------------------------------------------------------------------------
def normalize_words(text):
    return set(re.sub(r'[^a-z0-9]', ' ', text.lower()).split())


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def best_score(rg_title, file_name, pdf_title=None):
    rg_w = normalize_words(rg_title)
    clean = os.path.splitext(os.path.basename(file_name))[0].replace('_', ' ').replace('-', ' ')
    score = jaccard(rg_w, normalize_words(clean))
    if pdf_title:
        score = max(score, jaccard(rg_w, normalize_words(pdf_title)))
    return score


MATCH_THRESHOLD = 0.30


# ---------------------------------------------------------------------------
# Scan repo files
# ---------------------------------------------------------------------------
def scan_publication_files():
    files_info = []

    def _collect(root_dir):
        for root, dirs, files in os.walk(root_dir):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for file in sorted(files):
                if file.startswith('.') or file in IGNORED_FILES:
                    continue
                ext = os.path.splitext(file)[1].lower()
                if ext in IGNORED_EXTS:
                    continue
                full_path = os.path.join(root, file)
                rel_path  = os.path.relpath(full_path, DOMAIN_0_DIR)
                size_b    = os.path.getsize(full_path)
                size_str  = (f"{size_b/(1024*1024):.1f} MB"
                             if size_b >= 1024*1024
                             else f"{size_b/1024:.1f} KB")
                if ext == '.pdf':
                    pub_type  = "PDF"
                    pdf_title = extract_pdf_title(full_path)
                elif ext == '.md':
                    pub_type  = "Markdown"
                    pdf_title = None
                else:
                    pub_type  = ext.lstrip('.').upper() or "File"
                    pdf_title = None

                files_info.append({
                    "name":      file,
                    "rel_path":  rel_path,
                    "full_path": full_path,
                    "size":      size_str,
                    "type":      pub_type,
                    "pdf_title": pdf_title,
                })

    _collect(RG_BACKUP_DIR)
    if os.path.exists(OTHER_PUBS_DIR):
        _collect(OTHER_PUBS_DIR)

    return files_info


# ---------------------------------------------------------------------------
# Load RG publications (JSON → HTML → empty)
# ---------------------------------------------------------------------------
def load_rg_publications():
    """
    Priority:
      1. rg_publications.json  (committed, always up-to-date authoritative list)
      2. rg_profile.html       (user-saved RG page, parsed on the fly)
      3. Empty list            (nothing available)
    """
    # 1. JSON
    if os.path.exists(RG_JSON_PATH):
        with open(RG_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        pubs = data.get("publications", [])
        print(f"Loaded {len(pubs)} RG publication(s) from rg_publications.json.")
        return pubs, "rg_publications.json"

    # 2. HTML
    for candidate in ["rg_profile.html", "profile.html", "Artur-Kraskov.html"]:
        p = os.path.join(RG_BACKUP_DIR, candidate)
        if os.path.exists(p):
            pubs = parse_rg_profile_html(p)
            print(f"Loaded {len(pubs)} RG publication(s) from {candidate}.")
            return pubs, candidate

    print("No RG publication source found (add rg_publications.json or rg_profile.html).")
    return [], None


def parse_rg_profile_html(file_path):
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    pattern = (r'<a[^>]*href="([^"]*publication/(\d+)'
               r'_([^"?#\s>]+)(?:[^"]*)?)"[^>]*>([\s\S]*?)<\/a>')
    matches = re.findall(pattern, content, re.IGNORECASE)
    publications = {}
    for href, pub_id, slug, text in matches:
        text_clean = re.sub(r'<[^>]+>', ' ', text)
        text_clean = html.unescape(text_clean).strip()
        text_clean = re.sub(r'\s+', ' ', text_clean)
        if (not text_clean or len(text_clean) < 8 or
                text_clean.lower() in {'read full-text', 'download',
                                       'full-text available', 'view', 'read'}):
            text_clean = slug.replace('_', ' ').replace('-', ' ').strip()
        full_url = (href if href.startswith('http')
                    else 'https://www.researchgate.net' + href)
        full_url = full_url.split('?')[0]
        if pub_id not in publications:
            publications[pub_id] = {"id": pub_id, "title": text_clean,
                                    "url": full_url, "type": "Publication", "date": "N/A"}
    return list(publications.values())


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def generate_report():
    print("=" * 60)
    print("ResearchGate Backup Checker")
    print("=" * 60)

    # 1. Scan repo
    pub_files = scan_publication_files()
    print(f"\nFound {len(pub_files)} file(s) in repository.")
    for f in pub_files:
        t = f"  → title: {f['pdf_title']}" if f['pdf_title'] else ""
        print(f"  • {f['rel_path']}{t}")

    # 2. Load RG publications list
    print()
    rg_pubs, rg_source = load_rg_publications()

    # 3. Bidirectional matching
    # matched_file_paths: repo path → rg pub that claimed it
    matched_file_paths = {}   # rel_path → pub id
    rg_rows = []              # rows for the RG publications section

    for pub in rg_pubs:
        title    = pub["title"]
        url      = pub.get("url", "")
        pub_type = pub.get("type", "Publication")
        pub_date = pub.get("date", "N/A")

        # Find best-matching repo file
        best_file  = None
        best_sc    = 0.0
        for gf in pub_files:
            sc = best_score(title, gf["name"], gf.get("pdf_title"))
            if sc > best_sc:
                best_sc   = sc
                best_file = gf

        if best_file and best_sc >= MATCH_THRESHOLD:
            matched_file_paths[best_file["rel_path"]] = pub["id"]
            status    = "✅ Backed Up"
            pdf_title = best_file.get("pdf_title") or "—"
            git_col   = f"[`{best_file['name']}`](../{best_file['rel_path']})"
        else:
            status    = "❌ Not Backed Up"
            pdf_title = "—"
            git_col   = "—"

        rg_link = f"[↗ RG]({url})" if url else "—"
        rg_rows.append(
            f"| {title} | {pub_type} | {pub_date} | {pdf_title} | {rg_link} | {status} | {git_col} |"
        )

    # 4. Repo files NOT matched to any RG publication
    local_only = [gf for gf in pub_files if gf["rel_path"] not in matched_file_paths]

    # 5. Write README
    source_note = rg_source if rg_source else "Repo scan only — add rg_publications.json to track RG"
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    lines = [
        "# Domain 0: Research Gate Backup & Publications",
        "",
        "This directory serves as the primary repository for backing up and tracking research publications.",
        "",
        "## Authors",
        "",
        "- **Artur Kraskov** ([ResearchGate Profile](https://www.researchgate.net/profile/Artur-Kraskov))",
        "- **Shallwin Silvania** ([ResearchGate Profile](https://www.researchgate.net/profile/Shallwin-Silvania))",
        "",
        "---",
        "",
        "## ResearchGate Publications Backup Status",
        "",
        f"*Last verified: {now} · Source: {source_note}*",
        "",
        "| Publication Title | Type | Date | PDF Title (extracted) | RG Link | Backup Status | Git File |",
        "| :--- | :--- | :--- | :--- | :---: | :---: | :--- |",
    ]

    if rg_rows:
        lines.extend(rg_rows)
    else:
        lines.append("| *No RG publications loaded — add `rg_publications.json`* | | | | | | |")

    lines.append("")

    if local_only:
        lines += [
            "---",
            "",
            "## Local Files Not Matched to Any RG Publication",
            "",
            "| File | Path | Size | Type | Extracted Title |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ]
        for gf in local_only:
            pdf_t = gf.get("pdf_title") or "—"
            lines.append(
                f"| `{gf['name']}` | [`{gf['rel_path']}`](../{gf['rel_path']}) "
                f"| {gf['size']} | {gf['type']} | {pdf_t} |"
            )
        lines.append("")

    lines += [
        "---",
        "## How to update",
        "",
        "### Update the RG publications list",
        "Edit `rg_publications.json` to add new publications from ResearchGate.",
        "",
        "### Re-generate the table locally",
        "```bash",
        "pip install PyPDF2",
        "python3 researchGate_backup/check_backups.py",
        "```",
        "",
        "### Or trigger via GitHub Actions",
        "Go to **Actions → Check Publications Backup → Run workflow**.",
    ]

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"\nREADME.md written → {README_PATH}")
    backed   = sum(1 for r in rg_rows if "✅" in r)
    missing  = sum(1 for r in rg_rows if "❌" in r)
    print(f"Summary: {backed} backed up, {missing} not backed up, {len(local_only)} local-only files.")
    print("Done.")


if __name__ == "__main__":
    generate_report()
