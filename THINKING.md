# THINKING.md — Kaveri Precision Plant Copilot

---

## 1. Understand the User

**Who is the supervisor?**

A shop-floor supervisor at a mid-size precision machining plant (like Kaveri Precision, Hosur) typically:
- Oversees 10–30 operators across CNC turning, milling, or grinding cells
- Works rotating shifts (often 12-hour), frequently on their feet on the floor
- Is accountable for quality, safety compliance, and machine uptime simultaneously
- Has a diploma or ITI background — technically strong, but not a desk worker

**What are they trying to do?**

During a shift they constantly hit micro-decisions that require document lookups:
- "This alarm just fired — what do I do?"
- "Inspector flagged a dimension — what's the tolerance?"
- "Maintenance wants to open the hydraulic line — what's the LOTO procedure?"
- "Incoming lot has no MTC — can I accept it?"

Today they solve this by: walking to the supervisor's cabin, finding the right binder, flipping to the right page — or calling a senior engineer who may not pick up. Each lookup takes 5–15 minutes. During that time the line may be stopped.

**What frustrates them?**

1. Documents are in binders or shared drives — not searchable, not mobile-friendly
2. Multiple revisions exist; they're not always sure which is current
3. They can't afford to get safety or quality decisions wrong — the stakes are real
4. They don't have time to read a 20-page SOP to find one number
5. They're often on the floor with a phone, not at a desktop

**Assumptions I'm making:**
- The supervisor has basic smartphone literacy (WhatsApp, etc.)
- The plant has Wi-Fi on the shop floor, or at least in the supervisor's area
- Documents are already digitised as PDFs (not handwritten or scanned images)
- The supervisor asks in English; regional language support would be a real-world need but is out of scope here

---

## 2. User Journey (first draft, written before AI critique)

**Scenario:** Ravi, a shift supervisor at Kaveri Precision, is doing incoming inspection when a lot of BH-220 bearing housings arrives. The inspector flags an outer diameter reading of 90.038 mm and asks if it's within tolerance.

**Step 1 — Trigger**
Ravi is on the floor. He pulls out his phone and opens the Plant Copilot URL (bookmarked).

**Step 2 — Ask**
He types: *"What is the outer diameter tolerance for BH-220?"*
He hits Ask (or presses Enter).

**Step 3 — Wait**
A spinner shows "Searching documents…". Response arrives in ~2 seconds.

**Step 4 — Read answer**
The app shows: *"90.000 mm ± 0.050 mm"* with source: QC-SOP-014 Rev 04, p.2, §6.

**Step 5 — Verify source**
Ravi taps the source card to expand it. He sees the exact quoted phrase from the document and the revision date. He trusts it because it cites the current revision.

**Step 6 — Decision**
90.038 mm is within 90.000 ± 0.050 mm. Ravi tells the inspector to accept the lot.

**Step 7 — Edge case: answer not in documents**
Later, Ravi asks: *"What is the maximum spindle speed of the TX-200?"*
The app responds: *"I couldn't find this in the plant documents. Please check with your Quality / Maintenance / Safety owner."*
Ravi knows to call the maintenance engineer instead of guessing.

**What could go wrong:**
- Ravi types a vague question and gets a low-confidence answer
- The document has been updated but the index hasn't been rebuilt
- The app is slow on a congested Wi-Fi network
- Ravi's phone screen is hard to read in bright shop-floor lighting
- A small LLM hallucinates a value that sounds plausible but is wrong
- Two revisions of the same SOP exist — Ravi gets an answer from the old one

---

## 3. AI Challenge

I asked Claude to critique my user journey as a skeptical product manager. Key excerpts:

**Me:** Here's my user journey for a shop-floor supervisor using a RAG copilot. Please critique it as a skeptical PM.

**Claude:** A few things I'd push back on:

*"The supervisor trusts it because it cites the current revision"* — this assumes trust is earned automatically. In safety-critical environments, supervisors are trained to be skeptical of new tools. The first time the app gives a wrong answer (even once), they'll stop using it entirely. How are you handling hallucinations?

*"Response arrives in ~2 seconds"* — on a congested factory Wi-Fi with a phone browser, 2 seconds is optimistic. Have you tested on actual mobile hardware? A 5-second wait feels very different when you're standing at a machine.

*"He types: What is the outer diameter tolerance for BH-220?"* — supervisors under pressure don't type carefully. They'll type "BH220 OD tol" or "bearing housing size". Does your retrieval handle abbreviations and typos?

*The edge case section is too short.* What happens when the answer IS in the documents but the retrieval misses it? That's more dangerous than a clean "not found" — the supervisor gets a wrong answer with a citation.

**My reflection:**

- **Agreed:** The trust point is the most important critique. I added a citation check layer (verifying the LLM's quoted phrase actually exists in the retrieved chunks) and a hard threshold refusal (if cosine similarity < 0.30, don't call the LLM at all). I also added a superseded-revision banner so the supervisor always knows if an older version also matched.

- **Agreed:** Latency on mobile is real. I tested on my phone on the same Wi-Fi — actual latency with Groq was 1.5–2.5 seconds, which is acceptable. I added a spinner with "Searching documents…" so the wait feels intentional.

- **Partially agreed:** Abbreviation handling — BM25 helps with exact keyword matches (BH-220, AL-104), and the BGE embedding model handles semantic similarity. I didn't add explicit abbreviation expansion, but the hybrid retrieval (dense + BM25 + RRF) handles most real cases.

- **Agreed and changed:** The "wrong answer with citation" risk is the hardest problem. I added a three-layer refusal: (1) threshold check before calling LLM, (2) LLM returns `answerable: false`, (3) citation check drops sources whose quoted phrase can't be found verbatim in the retrieved chunks. This doesn't eliminate hallucination but catches the most obvious cases.

- **Disagreed:** The PM suggested adding a feedback button ("Was this helpful?"). I chose not to — it adds UI complexity and the data is useless without a backend to store and act on it. Better to do that in v2 with a real logging system.

---

## 4. The Improvement I Added, and Why

**Improvement: Superseded revision detection with a visible warning banner**

Both Rev 03 and Rev 04 of QC-SOP-014 are indexed. Without handling this, a query about sampling plans could return an answer from the old revision — and the supervisor would have no idea.

**What I built:**
- During ingestion, chunks from older revisions of the same document are marked `superseded: True`
- During retrieval, if both superseded and current chunks match, only current chunks go to the LLM
- If a superseded chunk also matched strongly (was in the pre-filter candidates), a yellow warning banner is shown: *"Note: An older revision (QC-SOP-014 Rev 03) also matched. Rev 04, effective 01-Jul-2026, is the current version and supersedes it."*
- The documents panel at the bottom of the UI shows CURRENT/SUPERSEDED badges for every indexed document

**Why this improvement:**
This is the highest-stakes failure mode for a manufacturing copilot. A supervisor acting on a superseded sampling plan or tolerance value could cause a quality escape or a safety incident. The fix is low-cost (metadata + one filter pass) but the safety value is high. It also builds trust — the supervisor can see that the app is aware of document versions, not just blindly searching.

---

## 5. Final Reflection

**What I'd build next:**

1. **Incremental index updates** — currently the full index is rebuilt on every `POST /reindex`. For a plant with 200+ documents, this would take minutes. A proper solution tracks file hashes and only re-embeds changed documents.

2. **Regional language support** — supervisors in Hosur may be more comfortable in Tamil. A translation layer (query → English → retrieve → answer → translate back) would make the tool genuinely accessible.

3. **Feedback loop** — a thumbs up/down on each answer, stored with the question and retrieved chunks, would let us identify retrieval failures and fine-tune the threshold per document type.

4. **Authentication** — currently anyone on the Wi-Fi can access the app. Even a simple PIN would be appropriate for a plant environment.

5. **Offline mode** — factory Wi-Fi can be unreliable. A PWA with cached recent answers would help.

**What I'm unsure about:**

- **Table parsing fragility**: My text-based table parser works for these four PDFs because I know their exact column structure. A real plant's PDFs will have wildly different layouts. I'd want to test on 20+ real SOPs before trusting it.
- **Threshold tuning**: The 0.30 cosine threshold was tuned on 11 questions. It may be too loose or too tight for a different document set. I'd want a larger eval set before deploying.
- **Small model reliability**: Groq's hosted Qwen model is fast and free, but small models sometimes ignore the "answer only from context" instruction. The citation check catches some hallucinations but not all paraphrased ones.

**What I'd ask the customer:**

1. How many documents are in scope, and how often are they updated?
2. Are the PDFs digitally created or scanned? (OCR changes the architecture significantly)
3. What languages do supervisors use on the floor?
4. Is there an existing document management system (DMS) we should integrate with, or are PDFs just in a shared folder?
5. What's the consequence of a wrong answer? (Calibrates how conservative the threshold should be)
6. Do supervisors have smartphones, or is there a shared tablet/terminal on the floor?

**Biggest challenge and how I handled it:**

The hardest problem was **table extraction from text-layout PDFs**. The four sample PDFs don't use PDF table objects — tables are rendered as plain text with columns separated by whitespace. pymupdf's `find_tables()` returned nothing.

I solved this by writing document-specific text parsers: for the alarm table (AL-XXX codes), the sampling plan (4-column, 4-lines-per-row), the PM schedule (variable-length activity field), and the inspection dimensions table. Each parser locates its table by a known header string, then walks the lines with document-specific logic.

This works for these four PDFs but is brittle for new documents. The honest fix for production would be a VLM-based table extractor (e.g., using a vision model to read table images) or a commercial PDF parser. I documented this limitation clearly in the README.

The second challenge was **revision handling** — both Rev 03 and Rev 04 of QC-SOP-014 are indexed, and naive retrieval would mix them. I solved this with a metadata-based filter: mark older revisions as superseded during ingestion, filter them out during retrieval when a current version exists, and show a warning banner when the old version also matched strongly. This took more thought than code.
