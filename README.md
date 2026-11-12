# Kaveri Precision — Plant Copilot

A RAG (Retrieval-Augmented Generation) AI copilot for shop-floor supervisors at Kaveri Precision Components, Hosur Plant. Ask questions in plain English; get answers grounded only in the plant's SOPs and manuals, with the exact source document, revision, and page shown.

---

## Setup and Run

```bash
# 1. Create and activate virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Mac/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Put the 4 PDFs in docs/
#    QC-SOP-014_Rev03_...pdf, QC-SOP-014_Rev04_...pdf
#    SAF-SOP-003_...pdf, MNT-MAN-CNC-02_...pdf

# 4. Copy and edit .env
copy .env.example .env         # Windows
# cp .env.example .env         # Mac/Linux
# Edit .env: set LLM_PROVIDER and model/key

# 5. Build the index (first time, ~2-3 min on CPU)
python -m app.ingest

# 6. Start the server
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000 in your browser.

---

## LLM Setup

### Groq (default — fast cloud inference, free tier)
```
# 1. Get a free API key at https://console.groq.com
# 2. Edit .env:
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...
GROQ_MODEL=llama3-8b-8192   # or llama3-70b-8192, mixtral-8x7b-32768
```
Groq runs open-source models (Llama 3, Mixtral) on custom hardware — responses in ~1-2 s.

### OpenAI
```
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```

### Anthropic
```
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-3-haiku-20240307
```

### Gemini
```
LLM_PROVIDER=gemini
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-1.5-flash
```

---

## Phone Access on Local Network

1. Find your laptop's IP:
   - Windows: `ipconfig` → look for "IPv4 Address" under your Wi-Fi adapter
   - Mac: `ipconfig getifaddr en0`
   - Linux: `hostname -I`

2. Open `http://<your-laptop-ip>:8000` on your phone (same Wi-Fi).

### Troubleshooting
- **Windows Firewall**: Allow port 8000 inbound:
  `netsh advfirewall firewall add rule name="Plant Copilot" dir=in action=allow protocol=TCP localport=8000`
- **Same Wi-Fi**: Phone and laptop must be on the same network. Guest networks with AP isolation will block this.
- **VPN**: Disable VPN on the laptop — it often blocks LAN traffic.
- **Laptop sleep**: Keep the laptop awake while supervisors use it.

---

## Architecture

```
docs/ (PDFs)
    │
    ▼
[ingest.py]
  pymupdf → raw text per page
  strip headers/footers (regex)
  detect section headings → section chunks
  detect tables → one chunk per row (prefixed with header)
  mark older revisions as superseded
  BAAI/bge-small-en-v1.5 → embeddings (numpy float32)
    │
    ▼
data/index.npz   (embeddings)
data/chunks.json (chunk text + metadata)
    │
    ▼
[retrieve.py]  on each /ask
  dense search: bge query embedding → cosine similarity (numpy dot product)
  BM25 search: rank_bm25 on tokenised chunk text
  Reciprocal Rank Fusion → combined ranking
  boost current-revision chunks ×1.2
  expand SAF-SOP-003 §5+§6 together (LOTO rule + exception)
  drop superseded chunks when current exists for same doc_no
  threshold check: best dense score < 0.30 → refuse without calling LLM
    │
    ▼
[llm.py + prompts.py]
  system prompt: answer only from context, exact values, JSON output
  user message: numbered context chunks + question
  LLM → JSON {"answerable", "answer", "sources"}
  citation check: verify each quoted phrase exists in retrieved chunks
    │
    ▼
[main.py]  FastAPI
  POST /ask → full pipeline above
  GET /documents → list with CURRENT/SUPERSEDED badges
  GET / → static/index.html (vanilla JS, mobile-first)
```

### How each piece works (plain language)

**Chunking**: Instead of splitting by fixed character count (which breaks mid-sentence), we split by numbered section headings ("1. Purpose", "4. Sampling Plan"). Tables get one chunk per row, each prefixed with the column headers so the row is self-contained even without surrounding context.

**Embeddings**: Each chunk is converted to a 384-dimensional vector by the BGE model. Similar meaning → similar vectors. Stored as a numpy array on disk.

**Hybrid retrieval**: Dense search finds semantically similar chunks; BM25 finds exact keyword matches (important for codes like AL-104, BH-220, SF-12). Reciprocal Rank Fusion combines both rankings without needing to tune weights.

**Threshold**: If the best cosine similarity score is below 0.30, we refuse to call the LLM at all. This catches questions about topics not in the documents.

**Revision handling**: Both Rev 03 and Rev 04 of QC-SOP-014 are indexed. When both match a query, only Rev 04 chunks go to the LLM. If Rev 03 also matched strongly, a yellow "Old version" banner is shown.

**Refusal layers**: Layer 1 = threshold check (no LLM call). Layer 2 = LLM returns `answerable: false`. Layer 3 = citation check fails (quoted text not found in retrieved chunks).

---

## My 5 Custom Questions — Actual App Answers

| # | Question | App Answer | Source | Pass |
|---|---|---|---|---|
| 6 | How many samples do I inspect for a lot of 200 pieces? | **13** | QC-SOP-014 Rev 04, p.1, §4 Sampling Plan *(superseded Rev 03 note shown)* | ✅ |
| 7 | Where do I put rejected material? | **Tag with a RED tag and move to Quarantine Cage Q1, Stores Bay 3.** | QC-SOP-014 Rev 04, p.2, §8 | ✅ |
| 8 | What should I do before replacing a hydraulic hose on the TX-200? | **Isolate the machine as per SAF-SOP-003 Lockout/Tagout. Never open the hydraulic circuit on a running or energised machine.** | MNT-MAN-CNC-02 Rev 02, p.1, §2 Safety First | ✅ |
| 9 | A lot arrived without a Material Test Certificate. Can I inspect it? | **No. The lot is put on HOLD and must not be inspected or accepted until the MTC is received.** | QC-SOP-014 Rev 04, p.2, §2 *(superseded Rev 03 note shown)* | ✅ |
| 10 | What is the maximum spindle speed of the TX-200? | **❌ I couldn't find this in the plant documents. Please check with your Quality / Maintenance / Safety owner.** | — (not in documents) | ✅ |

*Full eval output (11 questions, 10/11 pass) is in `eval/results.md`. Run `python -m eval.run_eval` to regenerate.*

---

## Known Limitations and Honest Notes

1. **Small-model hallucination risk**: llama3.2:3b and qwen2.5:3b are small models. They sometimes ignore the "answer only from context" instruction and invent plausible-sounding values. Larger models (GPT-4o, Claude 3.5) are significantly more reliable. The citation-check layer catches some hallucinations but not all.

2. **Table parsing fragility**: pymupdf's `find_tables()` works well on digitally-created PDFs but fails on scanned or image-based PDFs. The fallback is line-based parsing, which is less accurate. If alarm codes or tolerance values are missing from answers, check the table chunks with `python -m app.ingest` output.

3. **Scanned PDFs**: If a PDF page has very little extracted text (logged as a warning), it may be a scanned image. This app does not do OCR. You would need to pre-process with Tesseract or Adobe Acrobat.

4. **Threshold tuning**: The default threshold (0.30) was chosen so all 5 sample questions pass and the 2 unanswerable ones fail. If you add new documents, re-run the eval and adjust `SIMILARITY_THRESHOLD` in `.env`.

5. **No authentication**: Anyone on the same Wi-Fi can access the app. Do not expose it to the internet without adding auth.

6. **No document update workflow**: To add or update a PDF, copy it to `docs/` and call `POST /reindex` or restart the server. There is no incremental update — the full index is rebuilt each time.

7. **Section detection depends on heading format**: The chunker looks for headings like "1. Purpose" or "4.2 Sampling Plan". If a PDF uses a different heading style (bold text, Roman numerals, etc.), sections won't be detected and the whole document becomes one chunk.

8. **I am least sure about**: The table row chunking for multi-page tables. The code merges rows across pages by collecting all rows from all pages and deduplicating the header row. This works for the TX-200 alarm table but could break if a table has a complex structure or if pymupdf assigns rows to the wrong page.
