"""
ingest.py - PDF -> chunks -> embeddings -> saved index.
Run: python -m app.ingest

These PDFs use plain text layout (no PDF table objects).
Tables are parsed from text using known column headers.
"""
import re, json, logging
from pathlib import Path

import numpy as np

from app.config import DOCS_DIR, DATA_DIR, INDEX_FILE, CHUNKS_FILE, EMBED_MODEL

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

# Strips the repeated uncontrolled-copy header/footer (with page number on next line)
_HEADER_RE = re.compile(
    r"[\w\-]+\s*\|\s*Rev\s*\d+\s*\|\s*Uncontrolled copy when printed[^\n]*\nPage \d+\n?",
    re.IGNORECASE,
)

# Numbered section heading: "1. Purpose", "4.2 Sampling Plan", etc.
_SECTION_RE = re.compile(r"^(\d+(?:\.\d+)*)\.[ \t]+(.+)$")

# Alarm code pattern
_ALARM_RE = re.compile(r"^AL-\d+$")


# ── PDF text extraction ───────────────────────────────────────────────────────

def _extract_pages(pdf_path: Path) -> list[tuple[int, str]]:
    """Return [(page_no_1based, raw_text)] for each page."""
    pages = []
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        for i, page in enumerate(doc, 1):
            text = page.get_text("text")
            if len(text.strip()) < 50:
                log.warning("Page %d of %s has very little text (possible scan).", i, pdf_path.name)
            pages.append((i, text))
        doc.close()
    except Exception as e:
        log.warning("pymupdf failed for %s (%s), falling back to pypdf.", pdf_path.name, e)
        from pypdf import PdfReader
        reader = PdfReader(str(pdf_path))
        for i, page in enumerate(reader.pages, 1):
            pages.append((i, page.extract_text() or ""))
    return pages


def _clean(text: str) -> str:
    """Strip uncontrolled-copy header/footer lines and normalise whitespace."""
    text = _HEADER_RE.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ── Metadata parsing ──────────────────────────────────────────────────────────

def _parse_doc_meta(pdf_path: Path, pages: list[tuple[int, str]]) -> dict:
    """
    Extract doc_no, revision, effective_date.
    doc_no: parsed from filename first (most reliable), then from the header line.
    revision: from the title block "Revision\nNN" or the header "| Rev NN |".
    Must use raw (uncleaned) text so the header line is still present.
    """
    raw_first = pages[0][1] if pages else ""

    # Filename is the most reliable source for doc_no (e.g. MNT-MAN-CNC-02_TX-200...)
    stem = pdf_path.stem  # e.g. "MNT-MAN-CNC-02_TX-200_Preventive_Maintenance"
    fn_m = re.match(r"((?:QC|SAF|MNT)-[A-Z]+-\d+(?:-\d+)?)", stem)
    if fn_m:
        doc_no = fn_m.group(1)
    else:
        # Fallback: first match in the header line only (first line of raw text)
        first_line = raw_first.split("\n")[0]
        dn_m = re.search(r"((?:QC|SAF|MNT)-[A-Z]+-\d+(?:-\d+)?)", first_line)
        doc_no = dn_m.group(1) if dn_m else stem.split("_")[0]

    # Revision: prefer "Revision\nNN" title-block format
    rev_m = re.search(r"Revision\s*\n\s*0*(\d+)", raw_first, re.IGNORECASE)
    if not rev_m:
        # Fallback: "| Rev NN |" in the header line
        rev_m = re.search(r"\|\s*Rev\s+0*(\d+)\s*\|", raw_first, re.IGNORECASE)
    revision = rev_m.group(1).zfill(2) if rev_m else "00"

    date_m = re.search(r"Effective\s+Date\s*\n([^\n]+)", raw_first, re.IGNORECASE)
    effective_date = date_m.group(1).strip() if date_m else ""

    return {
        "doc_no": doc_no, "revision": revision,
        "effective_date": effective_date, "file_name": pdf_path.name,
    }


# ── Text-based table parsing ──────────────────────────────────────────────────

def _parse_alarm_table(full_text: str, meta: dict) -> list[dict]:
    """
    Parse the alarm table which has 3 columns: Alarm | Meaning | Operator action.
    Each alarm entry spans multiple lines:
      AL-XXX
      <meaning (1 line)>
      <action (1-3 lines)>
    The table header "Alarm\nMeaning\nOperator action" marks the start.
    """
    chunks = []
    doc_no, revision = meta["doc_no"], meta["revision"]
    prefix = f"[{doc_no} Rev {revision}] Section 6 - Common Alarms"
    header_text = "Alarm | Meaning | Operator action"

    # Find all alarm entries: AL-XXX followed by meaning and action lines
    # Pattern: alarm code on its own line, then meaning line, then action lines until next AL- or section
    alarm_section_m = re.search(r"^Alarm\s*\nMeaning\s*\nOperator action\s*\n", full_text, re.MULTILINE)
    if not alarm_section_m:
        return chunks

    segment = full_text[alarm_section_m.end():]
    lines = [l.strip() for l in segment.splitlines()]

    i = 0
    while i < len(lines):
        line = lines[i]
        # Stop at a new numbered section
        if _SECTION_RE.match(line):
            break
        # Alarm code line
        if _ALARM_RE.match(line):
            alarm_code = line
            meaning = lines[i + 1] if i + 1 < len(lines) else ""
            # Collect action lines until next alarm code or section heading
            action_parts = []
            j = i + 2
            while j < len(lines):
                if _ALARM_RE.match(lines[j]) or _SECTION_RE.match(lines[j]):
                    break
                if lines[j]:
                    action_parts.append(lines[j])
                j += 1
            action = " ".join(action_parts)
            row_text = f"Alarm: {alarm_code} | Meaning: {meaning} | Operator action: {action}"
            chunks.append({
                **meta,
                "section_number": "6", "section_title": "Common Alarms",
                "page_number": _find_alarm_page(alarm_code, meta),
                "chunk_type": "table_row",
                "text": f"{prefix} | {header_text} | {row_text}",
            })
            i = j
        else:
            i += 1

    return chunks


def _find_alarm_page(alarm_code: str, meta: dict) -> int:
    """AL-101 is on page 1 of MNT doc; AL-104+ are on page 2."""
    if alarm_code == "AL-101":
        return 1
    return 2


def _parse_simple_table(full_text: str, meta: dict,
                         header_line: str, col_names: list[str],
                         sec_num: str, sec_title: str,
                         rows_per_entry: int) -> list[dict]:
    """
    Parse a simple table where each row occupies exactly `rows_per_entry` lines.
    header_line: the exact first column header text to locate the table.
    """
    chunks = []
    doc_no, revision = meta["doc_no"], meta["revision"]
    prefix = f"[{doc_no} Rev {revision}] Section {sec_num} - {sec_title}"
    header_text = " | ".join(col_names)

    # Find the header
    m = re.search(r"^" + re.escape(header_line) + r"\s*$", full_text, re.MULTILINE)
    if not m:
        return chunks

    segment = full_text[m.start():]
    lines = [l.strip() for l in segment.splitlines() if l.strip()]

    # Skip the header column lines (len(col_names) lines)
    i = len(col_names)
    while i + rows_per_entry <= len(lines):
        row = lines[i: i + rows_per_entry]
        # Stop at a new numbered section heading
        if any(_SECTION_RE.match(r) for r in row):
            break
        # Skip if this looks like a repeated header
        if row[0] == col_names[0]:
            i += len(col_names)
            continue
        row_text = " | ".join(f"{col_names[j]}: {row[j]}" for j in range(rows_per_entry))
        chunks.append({
            **meta,
            "section_number": sec_num, "section_title": sec_title,
            "page_number": 1, "chunk_type": "table_row",
            "text": f"{prefix} | {header_text} | {row_text}",
        })
        i += rows_per_entry

    return chunks


def _parse_sampling_plan(full_text: str, meta: dict) -> list[dict]:
    """
    Sampling plan table: 4 columns, each row is 4 lines.
    Lot size (pieces) | Samples to inspect | Accept if minor defects are | Reject if minor defects are
    """
    col_names = ["Lot size", "Samples to inspect", "Accept if minor defects are", "Reject if minor defects are"]
    return _parse_simple_table(full_text, meta,
                                "Lot size (pieces)", col_names, "4", "Sampling Plan", 4)


def _parse_inspection_dims(full_text: str, meta: dict) -> list[dict]:
    """
    Inspection dimensions table: 5 columns, each row is 5 lines.
    Characteristic | Nominal | Tolerance | Method | Class
    """
    col_names = ["Characteristic", "Nominal", "Tolerance", "Method", "Class"]
    return _parse_simple_table(full_text, meta,
                                "Characteristic", col_names, "6", "Inspection Dimensions", 5)


def _parse_operating_params(full_text: str, meta: dict) -> list[dict]:
    """
    Operating parameters table: 3 columns, each row is 3 lines.
    Parameter | Normal range | Check method
    """
    col_names = ["Parameter", "Normal range", "Check method"]
    return _parse_simple_table(full_text, meta,
                                "Parameter", col_names, "3", "Operating Parameters", 3)


def _parse_pm_schedule(full_text: str, meta: dict) -> list[dict]:
    """
    PM schedule table: 3 columns but Activity spans multiple lines.
    Frequency | Activity | Done by
    We detect rows by the Frequency values (Daily, Weekly, Monthly, etc.)
    """
    chunks = []
    doc_no, revision = meta["doc_no"], meta["revision"]
    prefix = f"[{doc_no} Rev {revision}] Section 4 - Preventive Maintenance Schedule"
    header_text = "Frequency | Activity | Done by"
    col_names = ["Frequency", "Activity", "Done by"]

    freq_values = {"Daily (start of shift)", "Weekly", "Monthly", "Quarterly", "Yearly"}

    m = re.search(r"^Frequency\s*$", full_text, re.MULTILINE)
    if not m:
        return chunks

    segment = full_text[m.start():]
    lines = [l.strip() for l in segment.splitlines() if l.strip()]

    # Skip header lines
    i = len(col_names)
    while i < len(lines):
        line = lines[i]
        if _SECTION_RE.match(line):
            break
        # Check if this line is a frequency value
        if any(line.startswith(f) for f in ["Daily", "Weekly", "Monthly", "Quarterly", "Yearly"]):
            frequency = line
            # Collect activity lines until we hit a "Done by" value
            done_by_values = {"Operator", "Maintenance\ntechnician", "Maintenance technician",
                              "Maintenance\nengineer", "Maintenance engineer"}
            activity_parts = []
            done_by = ""
            j = i + 1
            while j < len(lines):
                l = lines[j]
                if any(l.startswith(f) for f in ["Daily", "Weekly", "Monthly", "Quarterly", "Yearly"]):
                    break
                if _SECTION_RE.match(l):
                    break
                if l in {"Operator", "Maintenance technician", "Maintenance engineer"}:
                    done_by = l
                    j += 1
                    break
                activity_parts.append(l)
                j += 1
            activity = " ".join(activity_parts)
            row_text = f"Frequency: {frequency} | Activity: {activity} | Done by: {done_by}"
            chunks.append({
                **meta,
                "section_number": "4", "section_title": "Preventive Maintenance Schedule",
                "page_number": 1, "chunk_type": "table_row",
                "text": f"{prefix} | {header_text} | {row_text}",
            })
            i = j
        else:
            i += 1

    return chunks


def _parse_all_tables(full_text: str, meta: dict) -> list[dict]:
    """Dispatch table parsing based on doc_no."""
    doc_no = meta["doc_no"]
    chunks = []
    if doc_no == "MNT-MAN-CNC-02":
        chunks += _parse_alarm_table(full_text, meta)
        chunks += _parse_operating_params(full_text, meta)
        chunks += _parse_pm_schedule(full_text, meta)
    elif doc_no == "QC-SOP-014":
        chunks += _parse_sampling_plan(full_text, meta)
        chunks += _parse_inspection_dims(full_text, meta)
    return chunks


# ── Section chunking ──────────────────────────────────────────────────────────

def _chunk_sections(pages: list[tuple[int, str]], meta: dict) -> list[dict]:
    """Split cleaned text into section-based text chunks."""
    doc_no, revision = meta["doc_no"], meta["revision"]
    chunks = []

    lines_with_page: list[tuple[int, str]] = []
    for page_no, text in pages:
        for line in _clean(text).splitlines():
            lines_with_page.append((page_no, line))

    current_sec_num = "0"
    current_sec_title = "Preamble"
    current_lines: list[str] = []
    current_page = pages[0][0] if pages else 1

    def flush(lines, page, sec_num, sec_title):
        body = "\n".join(lines).strip()
        if len(body) < 20:
            return
        prefix = f"[{doc_no} Rev {revision}] Section {sec_num} - {sec_title}"
        chunks.append({
            **meta,
            "section_number": sec_num, "section_title": sec_title,
            "page_number": page, "chunk_type": "text",
            "text": f"{prefix}\n{body}",
        })

    for page_no, line in lines_with_page:
        m = _SECTION_RE.match(line.strip())
        if m:
            flush(current_lines, current_page, current_sec_num, current_sec_title)
            current_sec_num = m.group(1)
            current_sec_title = m.group(2).strip()
            current_lines = []
            current_page = page_no
        else:
            current_lines.append(line)

    flush(current_lines, current_page, current_sec_num, current_sec_title)
    return chunks


# ── Revision handling ─────────────────────────────────────────────────────────

def _mark_superseded(chunks: list[dict]) -> tuple[list[dict], set]:
    """Mark older revisions of the same doc_no as superseded=True."""
    best: dict[str, str] = {}
    for c in chunks:
        dn, rv = c["doc_no"], c["revision"]
        if dn not in best or rv > best[dn]:
            best[dn] = rv

    superseded_docs: set[str] = set()
    for c in chunks:
        is_sup = c["revision"] < best[c["doc_no"]]
        c["superseded"] = is_sup
        if is_sup:
            superseded_docs.add(f"{c['doc_no']} Rev {c['revision']}")

    return chunks, superseded_docs


# ── Embeddings ────────────────────────────────────────────────────────────────

def _embed(texts: list[str], model) -> np.ndarray:
    vecs = model.encode(texts, normalize_embeddings=True, show_progress_bar=True)
    return np.array(vecs, dtype=np.float32)


# ── Main entry point ──────────────────────────────────────────────────────────

def run_ingest() -> list[dict]:
    """Ingest all PDFs in docs/, save index, return chunks."""
    DATA_DIR.mkdir(exist_ok=True)

    pdf_files = [p for p in DOCS_DIR.glob("*.pdf")
                 if "sample_questions" not in p.name.lower()]
    if not pdf_files:
        log.error("No PDFs found in %s", DOCS_DIR)
        return []

    all_chunks: list[dict] = []
    doc_count = 0
    page_count = 0

    for pdf_path in sorted(pdf_files):
        log.info("Processing %s ...", pdf_path.name)
        pages = _extract_pages(pdf_path)
        meta = _parse_doc_meta(pdf_path, pages)

        text_chunks = _chunk_sections(pages, meta)
        full_text = "\n".join(text for _, text in pages)
        table_chunks = _parse_all_tables(full_text, meta)

        all_chunks.extend(text_chunks + table_chunks)
        doc_count += 1
        page_count += len(pages)
        log.info("  -> %d text chunks + %d table rows | doc_no=%s rev=%s",
                 len(text_chunks), len(table_chunks), meta["doc_no"], meta["revision"])

    all_chunks, superseded_docs = _mark_superseded(all_chunks)

    log.info("Embedding %d chunks ...", len(all_chunks))
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(EMBED_MODEL)
    embeddings = _embed([c["text"] for c in all_chunks], model)

    np.savez_compressed(str(INDEX_FILE), embeddings=embeddings)
    with open(CHUNKS_FILE, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=2)

    print("\n== Ingestion Summary ==================================")
    print(f"  Documents : {doc_count}")
    print(f"  Pages     : {page_count}")
    print(f"  Chunks    : {len(all_chunks)}")
    print(f"  Superseded: {', '.join(sorted(superseded_docs)) or 'none'}")
    print("=======================================================\n")

    return all_chunks


if __name__ == "__main__":
    run_ingest()
