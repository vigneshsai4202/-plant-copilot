# THINKING.md — Kaveri Precision Plant Copilot

## 1. Understand the user

**Who:** A shop-floor supervisor running a shift of roughly 10–30 people on CNC machines, assembly or inspection. Likely diploma/ITI trained, very hands-on, little time to read, and phone-first rather than computer-first. They are accountable if a safety or quality mistake happens.

**What they're trying to do:** Make quick decisions mid-shift and act on them with confidence, for example:
- "Machine shows AL-104, what do I do?"
- "A lot arrived without an MTC, can I inspect it?"
- "How many samples for a lot of 200?"
- "Before my technician replaces a hydraulic hose, what has to happen first?"

**What frustrates them today:**
- SOPs live in binders or on a shared drive, and finding the right one takes minutes.
- They need to know which document to open before they can search.
- Multiple revisions exist, so it's easy to follow an old one.
- One-handed phone use, possibly with gloves, makes long PDFs painful.
- Calling the QC or maintenance manager for every question slows everyone down.

**Assumptions (not verified with real users):**
- Supervisors carry a smartphone and there is Wi-Fi on the floor.
- They can type a short question in English.
- The PDFs are digitally created, not scanned images.
- I haven't spoken to a real supervisor. This is based on general research and reasonable assumptions.

## 2. User journey (my first draft, before AI feedback)

**Today (without the copilot):** CNC-07 shows an alarm. Rajan, the supervisor, walks to the office or binder, finds the maintenance manual, flips to alarms, and reads it. If he can't find it, he phones maintenance. This takes several minutes with the operator waiting.

**With the copilot:**
1. Rajan opens the app on his phone (bookmarked URL).
2. He types "AL-104 what to do".
3. The app returns a short answer from the maintenance manual and shows which document it came from.
4. He acts on it and the machine resumes.

**What could go wrong:**
- Vague or misspelled question ("machine problem", "al104") and no useful match.
- The answer isn't in the documents and the app has nowhere to send him.
- The app quotes an old revision of an SOP.
- The model gets a number wrong (oil grade, torque, tolerance).
- The app is down (laptop asleep, bad Wi-Fi) and he stops trusting it.
- He trusts the answer without checking and acts on a safety-critical step.
- He isn't comfortable reading English.

## 3. AI challenge

I shared my draft with Claude and asked for a critical review. Below are the key points (paraphrased from the real conversation), then my reflection.

**Key points raised:**
- Parts of my first write-up looked written after the build: the journey already used features I added later (source cards, version banner), so it didn't show my original thinking.
- Specific claims (page loads in under 2 seconds, answer in about 2 seconds, machine running in 5 minutes) were not measured.
- My reflection covered parsing and rate limits but not deployment problems.
- A failed eval case (Q5) may have been my check being stricter than the question: "how often and who" was answered correctly, and the 0.005 mm limit was not asked for.
- Excerpts that read like scripted dialogue would not be credible, so the section should reflect only what really happened.

**What I agreed with:**
- All of the above. The version-awareness and verify-at-a-glance ideas matter most because acting on an outdated or wrong value is the supervisor's biggest risk, and the journey should be written plainly first.

**What I disagreed with / pushed back on:**
- [FILL: one honest point you disagree with, or write "Nothing major; the critique matched my own doubts."]

**What I changed:**
- Rewrote the journey in plain form without the later features.
- Removed unmeasured timing claims and labelled targets as assumptions.
- Added deployment challenges to the reflection.
- Relaxed the Q5 eval check to match the question that was asked.
- [FILL: any UI/prompt changes you really made, such as example chips, not-found message wording, README limitations.]

## 4. The improvement I added, and why

**Verify-at-a-glance sources + revision awareness.**
- Under every answer the app shows expandable source cards with the exact quoted passage, document number, revision and page.
- If a superseded revision also matched, a highlighted banner says so and names the current revision and effective date.

**Why:** Supervisors act immediately, and in this dataset the risk is real. QC-SOP-014 Rev 03 says 5 samples for every lot, while Rev 04 (effective 01-Jul-2026) uses a lot-size plan, e.g. 13 samples for 91–500 pieces. Rev 03 also says rejected material goes to the Red Bin by Gate 2, while Rev 04 says Quarantine Cage Q1. A plain RAG could mix these. The source cards let a supervisor check the exact sentence in seconds, and the banner stops them following an old procedure. Answers are built from the current revision only.

## 5. Final reflection

**What I'd build next**
1. Voice input, since typing with gloves on a noisy floor is hard.
2. Regional language support (Tamil/Hindi): translate the query, retrieve in English, translate the answer back.
3. Incremental document updates instead of full reindexing.
4. Simple authentication (PIN or QR), since anyone on the Wi-Fi can open it today.
5. A thumbs up/down log to see which questions fail.

**What I'm unsure about**
- **Table parsing:** My parser is tuned to these four PDFs. A document with different layouts or headers could silently produce no table chunks.
- **Hallucination:** The citation check verifies quotes exist in the retrieved text, but the model can still word the answer wrongly. A small model makes this worse.
- **Threshold:** I tuned SIMILARITY_THRESHOLD (=[0.30]) on about [11] questions. That's too few to trust on a larger document set.
- **Real-user fit:** I haven't tested with an actual supervisor.

**What I'd ask the customer**
1. How many documents exist, and are any scanned?
2. Which languages do supervisors prefer?
3. Is there Wi-Fi everywhere on the floor, or must it work offline?
4. Who owns SOP updates, and how often do they change?
5. Do some documents need role-based access?
6. Which questions have the highest safety stakes, so we can handle them more strictly?

**Biggest challenge and how I handled it: PDF table parsing**
The tables (alarms, sampling plan, BH-220 dimensions, PM schedule) are plain-text layouts, and `find_tables()` did not detect them. I wrote a text-based parser that detects tables by known header patterns and groups rows. The alarm table spans two pages with a repeated header, so I merged pages before parsing and matched alarm rows by their `AL-xxx` pattern rather than by line count. I also fixed a metadata bug: the maintenance manual mentions "SAF-SOP-003" in a cross-reference, so my doc-number regex labelled it wrongly. I now parse the document number from the filename first and only fall back to the text.

**Other challenges**
- **LLM rate limits:** The free Groq tier returned 429 errors during the 11-question eval. I added exponential backoff and a short delay between questions. A paid tier or a local model would be needed in production.
- **Deployment on the local network:** [FILL honestly, for example: running uvicorn with `--host 0.0.0.0`, finding the laptop IP, allowing port 8000 through the firewall, phone and laptop on the same Wi-Fi.]
- **Measured performance:** [FILL: one real response time you observed on your phone, or delete.]

**Eval result:** 10/11 questions pass. [FILL: note any failure and why. If Q5 is "failing" only because the numeric limit wasn't included, say the check was stricter than the question.]
