#!/usr/bin/env python3
import os
import re
import html
import sys
from datetime import datetime

# Define directories relative to this script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DOMAIN_0_DIR = os.path.dirname(SCRIPT_DIR)
RG_BACKUP_DIR = SCRIPT_DIR
OTHER_PUBS_DIR = os.path.join(DOMAIN_0_DIR, "other_publications")
README_PATH = os.path.join(RG_BACKUP_DIR, "README.md")

# Default/Fallback publications from Artur Kraskov's profile
FALLBACK_PUBLICATIONS = [
    {
        "id": "397191799",
        "title": "The Universal Matrix: From Visual Heuristic to Algorithmic Construction",
        "url": "https://www.researchgate.net/publication/397191799_The_Universal_Matrix_From_Visual_Heuristic_to_Algorithmic_Construction",
        "type": "Preprint",
        "date": "2026"
    },
    {
        "id": "392942469_protocol",
        "title": "Universal Matrix: Least-Action Cartesian Construction Protocol Permitted Tools and Primitive Moves",
        "url": "https://www.researchgate.net/publication/392942469_Universal_Matrix_Least-Action_Cartesian_Construction_Protocol_Permitted_Tools_and_Primitive_Moves",
        "type": "Preprint",
        "date": "2025"
    },
    {
        "id": "395696803",
        "title": "Universal Matrix RL with Requisite Variety: Architecture and Behaviour",
        "url": "https://www.researchgate.net/publication/395696803_Universal_Matrix_RL_with_Requisite_Variety_Architecture_and_Behaviour",
        "type": "Working Paper",
        "date": "2025"
    },
    {
        "id": "392942469_framework",
        "title": "Universal Matrix as a Cyber-Cognitive Framework Across Systems, Cognition, and Processes",
        "url": "https://www.researchgate.net/publication/392942469_Universal_Matrix_as_a_Cyber-Cognitive_Framework_Across_Systems_Cognition_and_Processes",
        "type": "Working Paper",
        "date": "2025"
    },
    {
        "id": "383196940",
        "title": "Universal Matrix Definition & Visual Proof, Visual Heuristic, Logical Chain",
        "url": "https://www.researchgate.net/publication/383196940_Universal_Matrix_Definition_Visual_Proof_Visual_Heuristic_Logical_Chain",
        "type": "Technical Report",
        "date": "2024"
    },
    {
        "id": "3370632967",
        "title": "Constructive Geometric Sequence Notation for the Universal Matrix",
        "url": "https://www.researchgate.net/publication/3370632967_Constructive_Geometric_Sequence_Notation_for_the_Universal_Matrix",
        "type": "Preprint",
        "date": "2025"
    }
]

# Manual mapping has been removed. The script now relies solely on fuzzy matching
# between ResearchGate publication titles and repository file names.
MANUAL_MAPPING = {}
from PyPDF2 import PdfReader


def extract_pdf_title(pdf_path):
    """Extract a title from a PDF file.
    First tries the PDF metadata 'title'. If not present, reads the first page
    and returns the first non‑empty line of text. Returns None on failure.
    """
    try:
        reader = PdfReader(pdf_path)
        # Metadata title
        meta_title = getattr(reader.metadata, 'title', None)
        if meta_title:
            return meta_title.strip()
        # Fallback: first page text
        if reader.pages:
            first_page = reader.pages[0]
            text = first_page.extract_text()
            if text:
                for line in text.splitlines():
                    line = line.strip()
                    if line:
                        return line
    except Exception as e:
        # Silently ignore PDF parsing errors
        return None
    return None


def normalize_text(text):
    """Normalize text for fuzzy matching (lowercase, alphanumeric only)."""
    return set(re.sub(r'[^a-z0-9]', ' ', text.lower()).split())

def is_fuzzy_match(title, filename):
    """Fuzzy matching logic based on word intersection."""
    # Strip extension and directory path
    name_only = os.path.splitext(os.path.basename(filename))[0]
    # Replace underscores/hyphens with spaces
    name_clean = name_only.replace('_', ' ').replace('-', ' ')
    
    words_title = normalize_text(title)
    words_file = normalize_text(name_clean)
    
    if not words_title or not words_file:
        return False
        
    intersection = words_title.intersection(words_file)
    # Check if a significant portion of words match
    min_len = min(len(words_title), len(words_file))
    if min_len == 0:
        return False
    overlap_ratio = len(intersection) / min_len
    
    # Substring match or high overlap ratio
    return overlap_ratio >= 0.75 or name_clean.lower() in title.lower() or title.lower() in name_clean.lower()

def scan_git_files():
    """Scan domain_0 directory for local publication files."""
    files_info = []
    ignored_exts = {'.py', '.html', '.webp', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.sh'}
    
    # Scan researchGate_backup
    for root, _, files in os.walk(RG_BACKUP_DIR):
        # Exclude hidden files/directories and reference folder
        if '.git' in root:
            continue
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if file.startswith('.') or file in {"README.md", "LICENSE"} or ext in ignored_exts:
                continue
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, DOMAIN_0_DIR)
            
            # Format size
            size_bytes = os.path.getsize(full_path)
            if size_bytes < 1024 * 1024:
                size_str = f"{size_bytes / 1024:.1f} KB"
            else:
                size_str = f"{size_bytes / (1024 * 1024):.1f} MB"
                
            if ext == '.pdf':
                pdf_title = extract_pdf_title(full_path)
            else:
                pdf_title = None
            files_info.append({
                "name": file,
                "rel_path": rel_path,
                "size": size_str,
                "type": "PDF Document" if file.endswith(".pdf") else "File",
                "pdf_title": pdf_title,
            })
            
    # Scan other_publications
    if os.path.exists(OTHER_PUBS_DIR):
        for root, _, files in os.walk(OTHER_PUBS_DIR):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if file.startswith('.') or file in {"README.md", "LICENSE"} or ext in ignored_exts:
                    continue
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, DOMAIN_0_DIR)
                
                size_bytes = os.path.getsize(full_path)
                if size_bytes < 1024 * 1024:
                    size_str = f"{size_bytes / 1024:.1f} KB"
                else:
                    size_str = f"{size_bytes / (1024 * 1024):.1f} MB"
                    
                pub_type = "Markdown Article" if file.endswith(".md") else "File"
                files_info.append({
                    "name": file,
                    "rel_path": rel_path,
                    "size": size_str,
                    "type": pub_type
                })
                
    return files_info

def parse_rg_profile_html(file_path):
    """Extract publication details from a saved ResearchGate profile HTML file."""
    print(f"Reading local HTML profile: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        html_content = f.read()
        
    # We look for links pointing to publication items
    # Example format: <a href="https://www.researchgate.net/publication/123456_Title">Title</a>
    # or relative: <a href="/publication/123456_Title">Title</a>
    pattern = r'<a[^>]*href="([^"]*publication/(\d+)_([^"?#\s>]+)(?:[^"]*)")"[^>]*>([\s\S]*?)<\/a>'
    matches = re.findall(pattern, html_content, re.IGNORECASE)
    
    publications = {}
    for href, pub_id, slug, text in matches:
        text_cleaned = re.sub(r'<[^>]+>', ' ', text)
        text_cleaned = html.unescape(text_cleaned).strip()
        text_cleaned = re.sub(r'\s+', ' ', text_cleaned)
        
        # Filter out minor actions/links like "Read full-text", "Download", etc.
        if not text_cleaned or len(text_cleaned) < 8 or text_cleaned.lower() in [
            'read full-text', 'download', 'full-text available', 'view', 'read'
        ]:
            # Convert slug to a readable title
            text_cleaned = slug.replace('_', ' ').replace('-', ' ').strip()
            
        full_url = href
        if not href.startswith('http'):
            full_url = 'https://www.researchgate.net' + href
        if '?' in full_url:
            full_url = full_url.split('?')[0]
            
        # Determine some metadata from content if possible, or leave default
        publications[pub_id] = {
            "id": pub_id,
            "title": text_cleaned,
            "url": full_url,
            "type": "Article/Preprint", # default
            "date": "N/A"
        }
        
    return list(publications.values())

def generate_report():
    print("Starting ResearchGate Backup Checker...")
    
    # 1. Scan Git Files
    git_files = scan_git_files()
    print(f"Found {len(git_files)} files in Git.")
    
    # 2. Get ResearchGate publications (from HTML if exists, otherwise fallback)
    html_file = None
    # Check potential HTML locations
    for filename in ["rg_profile.html", "profile.html", "Artur-Kraskov.html"]:
        p = os.path.join(RG_BACKUP_DIR, filename)
        if os.path.exists(p):
            html_file = p
            break
            
    rg_pubs = []
    source = "Fallback Database"
    if html_file:
        try:
            rg_pubs = parse_rg_profile_html(html_file)
            source = f"HTML Profile File ({os.path.basename(html_file)})"
        except Exception as e:
            print(f"Error parsing HTML file: {e}. Falling back to default list.")
            
    if not rg_pubs:
        rg_pubs = FALLBACK_PUBLICATIONS
        print(f"Using default database with {len(rg_pubs)} publications.")
    else:
        print(f"Extracted {len(rg_pubs)} publications from {source}.")
        
        # 3. Match ResearchGate Publications with Git Files
        matched_git_paths = set()
        rg_table_rows = []
        
        for pub in rg_pubs:
            pub_id = pub["id"]
            title = pub["title"]
            url = pub["url"]
            pub_type = pub.get("type", "Publication")
            pub_date = pub.get("date", "N/A")
            
            matched_files = []
            # First, try fuzzy match against PDF extracted titles if available
            for gf in git_files:
                # Prefer PDF title if present
                if gf.get("pdf_title"):
                    if is_fuzzy_match(title, gf["pdf_title"]):
                        matched_files.append(gf["rel_path"])
                        matched_git_paths.add(gf["rel_path"])
                        continue
                # Fallback to filename matching
                if is_fuzzy_match(title, gf["name"]):
                    matched_files.append(gf["rel_path"])
                    matched_git_paths.add(gf["rel_path"])
            
            status = "✅ Backed Up" if matched_files else "❌ Missing"
            if matched_files:
                links = []
                for mf in matched_files:
                    base = os.path.basename(mf)
                    # Show PDF file name with link to repo
                    links.append(f"[`{base}`](../{mf})")
                git_col = "<br>".join(links)
            else:
                git_col = "—"
            
            # Build row with PDF title if available (first matched file)
            pdf_title_display = "—"
            if matched_files:
                # Find the first matched file info to get pdf_title
                first_path = matched_files[0]
                for gf in git_files:
                    if gf["rel_path"] == first_path:
                        pdf_title_display = gf.get("pdf_title") or "—"
                        break
            rg_table_rows.append(f"| {title} | {pub_type} | {pub_date} | {pdf_title_display} | [{title}]({url}) | {status} | {git_col} |")
            
        # 4. Find Git files that are NOT matched to any ResearchGate publication
        unmatched_git_files = []
        for gf in git_files:
            if gf["rel_path"] not in matched_git_paths:
                unmatched_git_files.append(gf)
                
        # 5. Build README content
        new_readme = []
        new_readme.append("# Domain 0: Research Gate Backup & Publications")
        new_readme.append("")
        new_readme.append("This directory serves as the primary repository for backing up and tracking research publications.")
        new_readme.append("")
        new_readme.append("## Authors")
        new_readme.append("")
        new_readme.append("- **Artur Kraskov** ([ResearchGate Profile](https://www.researchgate.net/profile/Artur-Kraskov))")
        new_readme.append("- **Shallwin Silvania** ([ResearchGate Profile](https://www.researchgate.net/profile/Shallwin-Silvania))")
        new_readme.append("")
        new_readme.append("---")
        new_readme.append("")
        new_readme.append("## ResearchGate Publications Backup Tracker")
        new_readme.append("")
        new_readme.append(f"*Last verified: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} (Source: {source})*")
        new_readme.append("")
        new_readme.append("| Publication Title | Type | Date | PDF Title | RG Link | Backup Status | Git Files |")
        new_readme.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
        new_readme.extend(rg_table_rows)
        new_readme.append("")
        
        if unmatched_git_files:
            new_readme.append("## Other Git Publications (Not Linked to ResearchGate)")
            new_readme.append("")
            new_readme.append("| File Name | Path | Size | Type |")
            new_readme.append("| :--- | :--- | :--- | :--- |")
            for ugf in unmatched_git_files:
                new_readme.append(f"| `{ugf['name']}` | [`{ugf['rel_path']}`](../{ugf['rel_path']}) | {ugf['size']} | {ugf['type']} |")
            new_readme.append("")
            
        new_readme.append("---")
        new_readme.append("## How to update")
        new_readme.append("1. Log into your ResearchGate profile and save the page as an HTML file named `rg_profile.html` in this folder.")
        new_readme.append("2. Run the update script to refresh this table:")
        new_readme.append("   ```bash")
        new_readme.append("   python3 researchGate_backup/check_backups.py")
        new_readme.append("   ```")
        new_readme.append("3. Commit and push the changes.")
        
        # Write to README.md
        with open(README_PATH, "w", encoding="utf-8") as f:
            f.write("\n".join(new_readme) + "\n")
        
        print(f"README.md updated successfully at: {README_PATH}")

if __name__ == "__main__":
    generate_report()
