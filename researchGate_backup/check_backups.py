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

# RG embeds URLs with spaces inserted by the PDF renderer, e.g.:
#   "https://www .researchgate.ne t/public ation/389024613"
# We collapse all whitespace in the first 800 chars and search for the ID.
_RG_URL_RE = re.compile(
    r'researchgate[.\s]*net[/\s]*publication[/\s]*(\d{6,12})',
    re.IGNORECASE
)


# ---------------------------------------------------------------------------
# PDF helpers
# ---------------------------------------------------------------------------
def _is_noise_line(line):
    low = line.lower()
    return any(re.search(p, low) for p in RG_NOISE_PATTERNS)


def extract_rg_url_from_pdf(pdf_path):
    """Return the canonical RG publication URL embedded in the PDF watermark, or None."""
    if not PYPDF2_AVAILABLE:
        return None
    try:
        reader = PdfReader(pdf_path)
        if not reader.pages:
            return None
        # Collapse spaces so split tokens rejoin correctly
        raw = (reader.pages[0].extract_text() or "")[:1200]
        collapsed = re.sub(r'\s+', '', raw)   # remove ALL whitespace for URL matching
        m = re.search(r'researchgate\.?net/?publication/?([0-9]{6,12})', collapsed, re.IGNORECASE)
        if m:
            pub_id = m.group(1)
            return f"https://www.researchgate.net/publication/{pub_id}"
    except Exception:
        pass
    return None


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


def md_cell(text):
    """Escape a value so a literal '|' (seen in real RG titles) can't split a table row."""
    return str(text).replace('|', '\\|') if text else text


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
                    rg_url    = extract_rg_url_from_pdf(full_path)
                    rg_id     = rg_url.rsplit('/', 1)[-1] if rg_url else None
                elif ext == '.md':
                    pub_type  = "Markdown"
                    pdf_title = None
                    rg_id     = None
                else:
                    pub_type  = ext.lstrip('.').upper() or "File"
                    pdf_title = None
                    rg_id     = None

                files_info.append({
                    "name":      file,
                    "rel_path":  rel_path,
                    "full_path": full_path,
                    "size":      size_str,
                    "type":      pub_type,
                    "pdf_title": pdf_title,
                    "rg_id":     rg_id,   # ground-truth RG publication ID embedded in the PDF watermark, if any
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
    rg_publications.json is the committed baseline. If a saved rg_profile.html
    is ALSO present (dropped in manually to dodge Cloudflare), it is merged in —
    any publication id it contains that isn't already in the JSON is added.
    Without this merge, saving a fresh HTML snapshot next to an existing JSON
    was a silent no-op, since JSON always won.
    """
    pubs = []
    sources = []

    if os.path.exists(RG_JSON_PATH):
        with open(RG_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        pubs = list(data.get("publications", []))
        print(f"Loaded {len(pubs)} RG publication(s) from rg_publications.json.")
        sources.append("rg_publications.json")

    for candidate in ["rg_profile.html", "profile.html", "Artur-Kraskov.html"]:
        p = os.path.join(RG_BACKUP_DIR, candidate)
        if os.path.exists(p):
            html_pubs = parse_rg_profile_html(p)
            known_ids = {pub["id"] for pub in pubs}
            new_pubs  = [pub for pub in html_pubs if pub["id"] not in known_ids]
            pubs.extend(new_pubs)
            print(f"Loaded {len(html_pubs)} RG publication(s) from {candidate} "
                  f"({len(new_pubs)} new, not already in rg_publications.json).")
            sources.append(candidate)
            break

    if not pubs:
        print("No RG publication source found (add rg_publications.json or rg_profile.html).")
        return [], None

    return pubs, " + ".join(sources)


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
    # Pass 1 — exact match on the RG publication ID embedded in the PDF's own
    # watermark. This is ground truth (the file was literally downloaded from
    # that RG page) and takes priority over any fuzzy title guess.
    id_to_pub          = {pub["id"]: pub for pub in rg_pubs}
    matched_file_paths = {}   # rel_path → pub id
    pub_match          = {}   # pub id  → {"file": gf, "exact": bool}
    claimed_files       = set()

    for gf in pub_files:
        rg_id = gf.get("rg_id")
        if rg_id and rg_id in id_to_pub and rg_id not in pub_match:
            pub_match[rg_id] = {"file": gf, "exact": True}
            matched_file_paths[gf["rel_path"]] = rg_id
            claimed_files.add(gf["rel_path"])

    # Pass 2 — fuzzy Jaccard fallback for publications with no watermark hit
    # (e.g. self-authored uploads that pre-date the RG copy). Score every
    # remaining (pub, file) pair, then assign greedily by descending score so
    # one file can't silently absorb five different publications.
    remaining_pubs  = [p for p in rg_pubs if p["id"] not in pub_match]
    remaining_files = [f for f in pub_files if f["rel_path"] not in claimed_files]

    candidates = []
    for pub in remaining_pubs:
        for gf in remaining_files:
            sc = best_score(pub["title"], gf["name"], gf.get("pdf_title"))
            if sc >= MATCH_THRESHOLD:
                candidates.append((sc, pub["id"], gf["rel_path"]))
    candidates.sort(key=lambda c: c[0], reverse=True)

    fuzzy_claimed_pubs  = set()
    fuzzy_claimed_files = set()
    file_by_path = {f["rel_path"]: f for f in pub_files}
    for sc, pub_id, rel_path in candidates:
        if pub_id in fuzzy_claimed_pubs or rel_path in fuzzy_claimed_files:
            continue
        fuzzy_claimed_pubs.add(pub_id)
        fuzzy_claimed_files.add(rel_path)
        pub_match[pub_id] = {"file": file_by_path[rel_path], "exact": False}
        matched_file_paths[rel_path] = pub_id
        claimed_files.add(rel_path)

    # 4. Render RG publication rows
    rg_rows = []
    for pub in rg_pubs:
        title    = pub["title"]
        url      = pub.get("url", "")
        pub_type = pub.get("type", "Publication")
        pub_date = pub.get("date", "N/A")

        m = pub_match.get(pub["id"])
        if m:
            gf        = m["file"]
            status    = "✅ Backed Up"
            pdf_title = gf.get("pdf_title") or "—"
            marker    = "" if m["exact"] else "≈ "  # ≈ flags a fuzzy title guess, not a verified ID match
            git_col   = f"{marker}[`{gf['name']}`](../{gf['rel_path']})"
        else:
            status    = "❌ Not Backed Up"
            pdf_title = "—"
            git_col   = "—"

        rg_link = f"[↗ RG]({url})" if url else "—"
        rg_rows.append(
            f"| {md_cell(title)} | {pub_type} | {pub_date} | {md_cell(pdf_title)} | {rg_link} | {status} | {git_col} |"
        )

    # 5. Files with a watermark ID that ISN'T in rg_publications.json yet —
    # these are real RG publications (proven by the embedded ID) that the
    # tracked list is simply missing. Surface them instead of silently
    # dumping them into "local only".
    discovered = []
    for gf in pub_files:
        rg_id = gf.get("rg_id")
        if not rg_id or rg_id in id_to_pub:
            continue
        # Does an existing "not backed up" pub look like the same paper under
        # a stale/wrong ID? Flag it so a human can decide to correct vs. add.
        possible_dup = None
        for pub in rg_pubs:
            if pub["id"] in pub_match:
                continue
            if jaccard(normalize_words(pub["title"]), normalize_words(gf.get("pdf_title") or "")) >= 0.5:
                possible_dup = pub
                break
        discovered.append({"file": gf, "rg_id": rg_id, "possible_dup": possible_dup})

    # 6. Repo files NOT matched to any RG publication and NOT a discovered pub
    discovered_paths = {d["file"]["rel_path"] for d in discovered}
    local_only = [gf for gf in pub_files
                  if gf["rel_path"] not in matched_file_paths
                  and gf["rel_path"] not in discovered_paths]

    # 7. Write README
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
        "`≈` next to a Git File means it was matched by fuzzy title similarity, not a "
        "verified watermark ID — worth a manual sanity check.",
        "",
        "| Publication Title | Type | Date | PDF Title (extracted) | RG Link | Backup Status | Git File |",
        "| :--- | :--- | :--- | :--- | :---: | :---: | :--- |",
    ]

    if rg_rows:
        lines.extend(rg_rows)
    else:
        lines.append("| *No RG publications loaded — add `rg_publications.json`* | | | | | | |")

    lines.append("")

    if discovered:
        lines += [
            "---",
            "",
            "## 🆕 Possible New Publications (found via PDF watermark, not yet tracked)",
            "",
            "These files carry a ResearchGate publication ID in their own watermark "
            "(proof they were downloaded from an RG page), but that ID isn't in "
            "`rg_publications.json` yet. Add them if they're real, separate entries.",
            "",
            "| File | Watermark RG ID | Extracted Title | Note |",
            "| :--- | :--- | :--- | :--- |",
        ]
        for d in discovered:
            gf    = d["file"]
            note  = "—"
            if d["possible_dup"]:
                dup = d["possible_dup"]
                note = (f"⚠️ May be the same paper as tracked entry *{dup['title']}* "
                        f"(id `{dup['id']}`) — that ID might be stale/wrong")
            lines.append(
                f"| [`{gf['name']}`](../{gf['rel_path']}) "
                f"| [{d['rg_id']}](https://www.researchgate.net/publication/{d['rg_id']}) "
                f"| {md_cell(gf.get('pdf_title') or '—')} | {md_cell(note)} |"
            )
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
            pdf_t = md_cell(gf.get("pdf_title") or "—")
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
        "ResearchGate blocks automated fetches (Cloudflare 403s curl, WebFetch, "
        "and GitHub Actions runners alike), so this list can't be scraped live. "
        "There are two ways to keep it current:",
        "",
        "1. **Watermark auto-discovery** — any PDF you drop into `researchGate_backup/` "
        "that was downloaded from an RG page (i.e. it carries RG's own watermark) is "
        "automatically detected and cross-checked by ID, no manual entry needed.",
        "2. **Manual profile snapshot** — for publications not yet backed up as a PDF, "
        "save your logged-in profile page as `researchGate_backup/rg_profile.html` "
        "(browser: Save As → Webpage, HTML only). The script merges any new "
        "publication IDs it finds there into `rg_publications.json`'s list on the next run.",
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
