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
# Edit .env: add your GROQ_API_KEY (get free key at console.groq.com)

# 5. Build the index (first time, ~2 min on CPU)
python -m app.ingest

# 6. Start the server
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
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
GROQ_MODEL=qwen/qwen3.8-27b
```

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
   The server prints the URL on startup: `LAN URL: http://192.168.x.x:8000`

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
  parse text-based tables → one chunk per row (prefixed with header)
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
  boost current-revision chunks x1.2
  expand SAF-SOP-003 §5+§6 together (LOTO rule + exception)
  expand MNT §3 when §4 matches (gets spindle runout limit)
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

*(Generated from eval/results.md — run `python -m eval.run_eval` to regenerate)*

| # | Question | App Answer | Source | Pass |
|---|---|---|---|---|
| 6 | How many samples do I inspect for a lot of 200 pieces? | **13** | QC-SOP-014 Rev 04, p.1, §4 Sampling Plan *(superseded Rev 03 note shown)* | ✅ |
| 7 | Where do I put rejected material? | **Tag with a RED tag and move to Quarantine Cage Q1, Stores Bay 3.** | QC-SOP-014 Rev 04, p.2, §8 | ✅ |
| 8 | What should I do before replacing a hydraulic hose on the TX-200? | **Isolate the machine as per SAF-SOP-003 Lockout/Tagout. Never open the hydraulic circuit on a running or energised machine.** | MNT-MAN-CNC-02 Rev 02, p.1, §2 Safety First | ✅ |
| 9 | A lot arrived without a Material Test Certificate. Can I inspect it? | **No. The lot is put on HOLD and must not be inspected or accepted until the MTC is received.** | QC-SOP-014 Rev 04, p.2, §2 *(superseded Rev 03 note shown)* | ✅ |
| 10 | What is the maximum spindle speed of the TX-200? | **Not answerable — not in the plant documents. Please check with your Quality / Maintenance / Safety owner.** | — (not in documents) | ✅ |

*Full eval output (11 questions, 10/11 pass) is in `eval/results.md`.*

---

## Known Limitations and Honest Notes

1. **Hallucination risk**: The model (qwen/qwen3.8-27b via Groq) sometimes omits numeric values even when they are in the retrieved context. Larger models (GPT-4o, Claude 3.5) are more reliable. The citation-check layer catches fabricated quotes but not omissions.

2. **Table parsing is hand-tuned**: The table parser detects tables by known column headers ("Alarm", "Characteristic", "Frequency"). A PDF with different heading styles will silently produce no table chunks. Check `python -m app.ingest` output for table row counts.

3. **Scanned PDFs not supported**: If a PDF page has very little extracted text, it may be a scanned image. This app does not do OCR. Pre-process with Tesseract or Adobe Acrobat first.

4. **Threshold tuning**: SIMILARITY_THRESHOLD=0.30 was tuned on 11 questions. Add new documents and re-run `python -m eval.run_eval` to check if it needs adjusting.

5. **No authentication**: Anyone on the same Wi-Fi can access the app. Do not expose to the internet without adding auth.

6. **No incremental indexing**: To add or update a PDF, copy it to `docs/` and run `POST /reindex` or restart. The full index is rebuilt each time.

7. **Groq free tier rate limits**: The free tier allows ~30 requests/minute. The eval adds a 5-second delay between questions to avoid 429 errors. For production use, a paid tier or locally-hosted model is recommended.
