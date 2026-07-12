#!/usr/bin/env python3
"""
check_backups.py

Scans the domain_0 repo for publication files (PDFs and Markdown),
extracts titles from PDF metadata/text, optionally cross-references a
saved ResearchGate profile HTML, and writes a status table to README.md.

NO hardcoded publication lists — everything is derived from real files.
"""
import os
import re
import html
from datetime import datetime

try:
    from PyPDF2 import PdfReader
    PYPDF2_AVAILABLE = True
except ImportError:
    PYPDF2_AVAILABLE = False
    print("Warning: PyPDF2 not installed. PDF title extraction disabled.")

# ---------------------------------------------------------------------------
# Paths (all relative to this script so CI and local runs both work)
# ---------------------------------------------------------------------------
SCRIPT_DIR     = os.path.dirname(os.path.abspath(__file__))
DOMAIN_0_DIR   = os.path.dirname(SCRIPT_DIR)
RG_BACKUP_DIR  = SCRIPT_DIR
OTHER_PUBS_DIR = os.path.join(DOMAIN_0_DIR, "other_publications")
README_PATH    = os.path.join(RG_BACKUP_DIR, "README.md")

# File extensions we never want to treat as publications
IGNORED_EXTS = {'.py', '.sh', '.html', '.webp', '.png', '.jpg',
                '.jpeg', '.gif', '.svg', '.yml', '.yaml', '.json',
                '.txt', '.toml', '.cfg', '.ini'}

IGNORED_FILES = {"README.md", "LICENSE", ".gitignore", ".DS_Store"}


# ---------------------------------------------------------------------------
# PDF helpers
# ---------------------------------------------------------------------------
def extract_pdf_title(pdf_path):
    """Return the title string from a PDF, or None on failure."""
    if not PYPDF2_AVAILABLE:
        return None
    try:
        reader = PdfReader(pdf_path)
        # 1. PDF metadata
        if reader.metadata:
            meta_title = reader.metadata.get("/Title") or reader.metadata.get("title")
            if meta_title and meta_title.strip():
                return meta_title.strip()
        # 2. First non-empty line of page 1
        if reader.pages:
            text = reader.pages[0].extract_text() or ""
            for line in text.splitlines():
                line = line.strip()
                if line and len(line) > 5:
                    return line
    except Exception as e:
        print(f"  [warn] Could not read {pdf_path}: {e}")
    return None


# ---------------------------------------------------------------------------
# Fuzzy matching
# ---------------------------------------------------------------------------
def normalize_words(text):
    """Lowercase alphanumeric word set — used for Jaccard-style matching."""
    return set(re.sub(r'[^a-z0-9]', ' ', text.lower()).split())


def jaccard_similarity(a, b):
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def best_match_score(rg_title, file_name, pdf_title=None):
    """
    Return the best similarity score between an RG title and a local file.
    Compares against both the filename (sans extension) and the PDF title.
    """
    rg_words = normalize_words(rg_title)

    # Compare with filename
    clean_name = os.path.splitext(os.path.basename(file_name))[0]
    clean_name = clean_name.replace('_', ' ').replace('-', ' ')
    name_words = normalize_words(clean_name)
    score = jaccard_similarity(rg_words, name_words)

    # Compare with PDF title (usually more accurate)
    if pdf_title:
        pdf_words  = normalize_words(pdf_title)
        score = max(score, jaccard_similarity(rg_words, pdf_words))

    return score


MATCH_THRESHOLD = 0.35   # lower = more generous; raise if too many false positives


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------
def scan_publication_files():
    """Walk the repo and collect every file that looks like a publication."""
    files_info = []

    def _collect(root_dir):
        for root, dirs, files in os.walk(root_dir):
            # Skip hidden dirs
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for file in files:
                if file.startswith('.') or file in IGNORED_FILES:
                    continue
                ext = os.path.splitext(file)[1].lower()
                if ext in IGNORED_EXTS:
                    continue

                full_path = os.path.join(root, file)
                rel_path  = os.path.relpath(full_path, DOMAIN_0_DIR)

                size_bytes = os.path.getsize(full_path)
                size_str   = (f"{size_bytes / (1024*1024):.1f} MB"
                              if size_bytes >= 1024 * 1024
                              else f"{size_bytes / 1024:.1f} KB")

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
# Optional: parse a saved RG profile HTML
# ---------------------------------------------------------------------------
def parse_rg_profile_html(file_path):
    """Extract publication records from a locally saved RG profile HTML."""
    print(f"  Reading RG HTML profile: {file_path}")
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

        # Skip action links
        if (not text_clean or len(text_clean) < 8 or
                text_clean.lower() in {'read full-text', 'download',
                                       'full-text available', 'view', 'read'}):
            text_clean = slug.replace('_', ' ').replace('-', ' ').strip()

        full_url = href if href.startswith('http') else 'https://www.researchgate.net' + href
        full_url = full_url.split('?')[0]

        if pub_id not in publications:
            publications[pub_id] = {
                "id":    pub_id,
                "title": text_clean,
                "url":   full_url,
                "type":  "Publication",
                "date":  "N/A",
            }

    return list(publications.values())


# ---------------------------------------------------------------------------
# Main report generator
# ---------------------------------------------------------------------------
def generate_report():
    print("=" * 60)
    print("ResearchGate Backup Checker")
    print("=" * 60)

    # 1. Scan real files from disk
    pub_files = scan_publication_files()
    print(f"\nFound {len(pub_files)} publication file(s) in repository:")
    for f in pub_files:
        title_str = f"  → PDF title: {f['pdf_title']}" if f['pdf_title'] else ""
        print(f"  • {f['rel_path']} ({f['size']}){title_str}")

    # 2. Try to load RG profile HTML for cross-referencing
    rg_pubs  = []
    rg_source = None
    for candidate in ["rg_profile.html", "profile.html", "Artur-Kraskov.html"]:
        p = os.path.join(RG_BACKUP_DIR, candidate)
        if os.path.exists(p):
            try:
                rg_pubs   = parse_rg_profile_html(p)
                rg_source = os.path.basename(p)
                print(f"\nLoaded {len(rg_pubs)} RG publication(s) from {rg_source}.")
            except Exception as e:
                print(f"\nCould not parse {p}: {e}")
            break

    if not rg_pubs:
        print("\nNo RG profile HTML found — table will list repo files only.")

    # 3. Build the table
    # Case A: We have RG publications → match each to repo files
    # Case B: No RG data → just list every file we found
    rows = []

    if rg_pubs:
        matched_paths = set()
        for pub in rg_pubs:
            title    = pub["title"]
            url      = pub["url"]
            pub_type = pub.get("type", "Publication")
            pub_date = pub.get("date", "N/A")

            best_score = 0.0
            best_file  = None
            for gf in pub_files:
                score = best_match_score(title, gf["name"], gf.get("pdf_title"))
                if score > best_score:
                    best_score = score
                    best_file  = gf

            if best_file and best_score >= MATCH_THRESHOLD:
                matched_paths.add(best_file["rel_path"])
                status    = "✅ Backed Up"
                pdf_title = best_file.get("pdf_title") or "—"
                git_col   = f"[`{best_file['name']}`](../{best_file['rel_path']})"
            else:
                status    = "❌ Missing"
                pdf_title = "—"
                git_col   = "—"

            rows.append(f"| {title} | {pub_type} | {pub_date} | {pdf_title} "
                        f"| [{title}]({url}) | {status} | {git_col} |")

        # Unmatched repo files
        unmatched = [gf for gf in pub_files if gf["rel_path"] not in matched_paths]
    else:
        # No RG data — list all files as standalone entries
        unmatched = pub_files
        for gf in pub_files:
            title     = gf.get("pdf_title") or os.path.splitext(gf["name"])[0].replace("_", " ")
            pdf_title = gf.get("pdf_title") or "—"
            git_col   = f"[`{gf['name']}`](../{gf['rel_path']})"
            rows.append(f"| {title} | {gf['type']} | — | {pdf_title} "
                        f"| — | 📁 In Repo | {git_col} |")
        unmatched = []   # already listed above

    # 4. Write README
    source_note = rg_source if rg_source else "Repo scan only (no RG HTML provided)"
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
        "## Publications Backup Tracker",
        "",
        f"*Last verified: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · Source: {source_note}*",
        "",
        "| Publication Title | Type | Date | PDF Title | RG Link | Backup Status | Git File |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    lines.extend(rows)
    lines.append("")

    if unmatched:
        lines += [
            "## Other Repo Files (not matched to RG publications)",
            "",
            "| File | Path | Size | Type |",
            "| :--- | :--- | :--- | :--- |",
        ]
        for gf in unmatched:
            lines.append(f"| `{gf['name']}` | [`{gf['rel_path']}`](../{gf['rel_path']}) "
                         f"| {gf['size']} | {gf['type']} |")
        lines.append("")

    lines += [
        "---",
        "## How to update",
        "1. Log into ResearchGate, save your profile page as `rg_profile.html` in this folder.",
        "2. Run:",
        "   ```bash",
        "   python3 researchGate_backup/check_backups.py",
        "   ```",
        "3. Commit and push the changes.",
    ]

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"\nREADME.md written → {README_PATH}")
    print("Done.")


if __name__ == "__main__":
    generate_report()
