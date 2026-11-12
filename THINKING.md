# THINKING.md — Kaveri Precision Plant Copilot

---

## 1. Understand the User

**Who is the supervisor?**
A shop-floor supervisor at a manufacturing plant (e.g. Kaveri Precision Components, Hosur) is responsible for a shift of 10–30 workers running CNC machines, assembly lines, or quality inspection stations. They typically have a diploma or ITI qualification, strong hands-on experience, and limited time for reading. They are not software users by habit — their primary tools are a clipboard, a walkie-talkie, and a phone.

**What are they trying to do?**
During a shift they face dozens of quick decisions:
- "This machine is showing AL-104 — what do I do?"
- "A delivery just arrived without an MTC — can I accept it?"
- "How many samples do I pull for this lot of 200 pieces?"
- "My technician is about to replace a hydraulic hose — what's the safety checklist?"

They need the answer in under 30 seconds, with enough confidence to act on it immediately.

**What frustrates them today?**
- SOPs are stored as PDFs on a shared drive or printed in a binder. Finding the right document takes 5–10 minutes.
- Documents have multiple revisions. It is easy to act on an outdated procedure.
- They cannot search across documents — they must know which document to open first.
- On the shop floor, they are standing, often wearing gloves, using a phone with one hand. Long PDFs are unusable.
- If they call the QC or Maintenance manager for every question, it slows everyone down.
- They are accountable for safety incidents. Acting on wrong information is a serious risk.

**Assumptions I am making:**
- Supervisors have a smartphone on the shop floor (common in Indian manufacturing plants since ~2018).
- The plant has Wi-Fi coverage on the shop floor (increasingly standard).
- Supervisors can type a short question in English or will adapt quickly to doing so.
- The plant's SOPs are digitally created PDFs (not scanned images).

---

## 2. User Journey

**Scenario**: It is 2:30 PM. The supervisor, Rajan, is doing his rounds. Machine CNC-07 shows alarm AL-104. His operator is waiting.

**Step 1 — Rajan opens the app on his phone.**
He has the URL bookmarked. The page loads in under 2 seconds (it is a static HTML page served locally).

**Step 2 — He types his question.**
"Machine showing AL-104 what to do"
He taps Ask.

**Step 3 — The app responds in ~2 seconds.**
"AL-104 means Way lube oil level low. Top up with ISO VG 68 oil to the MAX mark, then press RESET. Machine can continue after reset."
Below the answer: a source card — MNT-MAN-CNC-02 Rev 02, Section 6, with the exact quoted line.

**Step 4 — Rajan verifies.**
He taps the source card, sees the exact sentence from the manual. He is confident. He tells his operator to top up the oil.

**Step 5 — Machine is back running in 5 minutes.**

**What could go wrong:**
- Rajan types a vague question ("machine problem") → app returns a low-confidence or not-found response. He needs to be more specific.
- The answer references an old revision → the app shows a yellow "Old version" banner. Rajan knows to check with QC.
- The app is down (laptop asleep, Wi-Fi issue) → Rajan falls back to the binder. The app must be reliable or supervisors will stop trusting it.
- The LLM hallucinates a value (e.g. wrong oil grade) → the citation check catches it, but not always. This is the biggest risk.
- Rajan acts on the answer without reading the source → training needed: "always verify the source card for safety-critical actions."

---

## 3. AI Challenge

**I asked Claude to critique my user journey as a skeptical product manager.**

Key excerpts:

> **Claude**: "You assume Rajan can type a coherent question under pressure. On a noisy shop floor, with gloves on, after a machine alarm, he may type something like 'al104' or 'alarm oil'. Does your app handle that?"

> **My response**: Good point. I tested "al104" — BM25 retrieval picks it up correctly because it matches the exact token. But "alarm oil" is weaker. I added example chips on the UI so supervisors can tap a pre-written question instead of typing from scratch.

> **Claude**: "Your journey assumes the answer is always in the documents. What happens when it isn't — and the supervisor needs to act anyway? Does the app tell him who to call?"

> **My response**: I agreed with this. I updated the not-found message to say "Please check with your Quality / Maintenance / Safety owner" — giving a clear next action instead of just a dead end.

> **Claude**: "The 'verify the source card' step assumes supervisors will actually do this. In practice, people trust the first answer they see. How do you prevent them from acting on a hallucinated value?"

> **My response**: I partially agreed. The citation check layer drops sources whose quotes don't appear in the retrieved text. But I was honest: a small model can still hallucinate the answer text itself. I added a note in the UI and README about this risk. I disagreed that this makes the app unusable — it is still far better than searching a PDF binder.

> **Claude**: "What about supervisors who don't read English well?"

> **My response**: Valid limitation I hadn't considered. I noted it as a future improvement (regional language support). Out of scope for this assignment but important for real deployment.

**What I changed after the AI challenge:**
- Added example question chips to the UI (tap instead of type)
- Improved the not-found message to include "check with your Quality / Maintenance / Safety owner"
- Added an honest limitations section to the README about hallucination risk
- Added the superseded-revision banner (the improvement I chose — see below)

---

## 4. The Improvement I Added, and Why

**Improvement: Verify-at-a-glance + Version Awareness**

Under every answer, the app shows expandable source cards with:
- The exact quoted passage from the document
- Document name, revision number, and page
- A yellow "Old version" banner when an answer touches a superseded revision

**Why I chose this:**

The AI challenge conversation made one thing very clear: supervisors act on safety and quality instructions immediately. If the app shows the right answer from the wrong revision, the consequences can be serious (wrong sample size, wrong quarantine location, wrong oil grade).

The two-revision problem is real in this dataset: QC-SOP-014 exists as both Rev 03 (superseded) and Rev 04 (current). Rev 03 says inspect 5 samples for a lot of 91–500 pieces. Rev 04 says 13. If a supervisor acts on Rev 03, they under-inspect and may accept a defective lot.

The source card solves two problems at once:
1. **Verification**: The supervisor can see the exact sentence the answer came from, in under 5 seconds, without opening the PDF.
2. **Version awareness**: The yellow banner makes it impossible to miss when an old revision also matched — and tells the supervisor which revision is current and when it took effect.

This is the improvement most directly tied to the user journey: it reduces the risk of acting on wrong information, which is the supervisor's biggest fear.

---

## 5. Final Reflection

**What I'd build next:**

1. **Voice input**: On a noisy shop floor with gloves on, typing is hard. A "tap and speak" button using the browser's Web Speech API would make the app much more usable.

2. **Regional language support**: Many shop-floor supervisors in Tamil Nadu are more comfortable in Tamil than English. Adding a translation layer (query in Tamil → retrieve in English → answer translated back) would dramatically increase adoption.

3. **Incremental indexing**: Right now, adding a new PDF requires rebuilding the entire index. A proper document store with incremental updates would make it practical for a real plant with dozens of documents updated regularly.

4. **Authentication**: Anyone on the Wi-Fi can access the app. For a real deployment, even a simple PIN or QR-code login would be needed.

5. **Feedback loop**: A thumbs up/down button on each answer, logged to a file. After a week, you can see which questions fail most often and fix the chunking or prompts.

**What I'm unsure about:**

- **Table parsing across PDFs I haven't seen**: My table parser is hand-tuned for these 4 PDFs. It detects tables by looking for known column header patterns ("Alarm", "Characteristic", "Frequency"). A different PDF with different headers would silently produce no table chunks. I would need a more general approach (e.g. detecting columnar text by x-position) for production use.

- **The citation check**: I verify that the LLM's quoted phrase appears in the retrieved chunks. But the LLM can still hallucinate the answer text while quoting correctly. I am not fully confident the citation check catches all hallucinations — it catches the obvious ones.

- **Threshold value**: I set SIMILARITY_THRESHOLD=0.30 based on the eval set of 11 questions. With more documents and more question types, this value may need retuning. I would want at least 50 test questions before trusting it.

**What I'd ask the customer:**

1. How many documents does the plant actually have? (4 is a demo; 400 changes the architecture.)
2. Are any documents scanned images? (OCR pipeline needed.)
3. What languages do supervisors prefer? (Tamil, Hindi, English?)
4. Is there Wi-Fi on the shop floor, or would this need to work offline?
5. What is the process for updating SOPs? (Who uploads new PDFs, how often?)
6. Are there any documents that must never be shown to certain roles? (Access control.)

**Biggest challenge and how I handled it:**

The biggest challenge was **PDF table parsing**. The PDFs use plain text layout — there are no actual PDF table objects, just text formatted to look like tables. PyMuPDF's `find_tables()` returned nothing. I had to write a custom text-based parser that detects tables by their known column headers and groups lines into rows.

The tricky part was the alarm table, which spans two pages. The first page ends mid-table (after AL-101) and the second page starts with a repeated header row. I handled this by merging all pages into one text string before parsing, then detecting alarm entries by their AL-XXX pattern rather than by line count.

I also hit a metadata parsing bug: the MNT document's text contains the string "SAF-SOP-003" (in a cross-reference), so my doc_no regex was matching the wrong document. I fixed this by parsing doc_no from the filename first (most reliable) and only falling back to text if the filename doesn't match.

The second biggest challenge was **Groq rate limiting** on the free tier. The eval runs 11 LLM calls in sequence and hits the 429 limit around call 5. I added exponential backoff (20s, 40s, 60s) and a 5-second delay between eval questions. For production, a paid tier or a locally-hosted model would be needed.

**Final score: 10/11 eval questions pass.** The one failure (Q5: spindle runout limit 0.005 mm) is a prompt issue — the model answers correctly (monthly, maintenance technician) but omits the numeric limit. The value is in the retrieved context; a stronger prompt or a larger model would include it.
