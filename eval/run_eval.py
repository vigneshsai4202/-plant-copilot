"""
run_eval.py — call the pipeline directly (no running server needed) and write results.md.
Usage: python -m eval.run_eval
"""
import json, re, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

QUESTIONS_FILE = Path(__file__).parent / "questions.json"
RESULTS_FILE   = Path(__file__).parent / "results.md"


def call_pipeline(question: str) -> dict:
    """Call retrieve + generate directly (no HTTP)."""
    from app.config import SIMILARITY_THRESHOLD, TOP_K, BGE_QUERY_PREFIX
    import app.retrieve as _ret
    from app.retrieve import retrieve, build_superseded_note
    from app.prompts import SYSTEM_PROMPT, build_user_message
    from app.llm import generate
    import numpy as np

    _ret._load()
    t0 = time.time()
    chunks, best_score = retrieve(question)

    if best_score < SIMILARITY_THRESHOLD or not chunks:
        return {"answerable": False, "answer": "", "sources": [],
                "latency_ms": int((time.time()-t0)*1000), "superseded_note": None}

    # Build superseded note using pre-filter candidates
    q_vec = _ret._model.encode(BGE_QUERY_PREFIX + question, normalize_embeddings=True).astype(np.float32)
    dense_scores = _ret._cosine_scores(q_vec)
    dense_ranks = np.argsort(-dense_scores).tolist()
    bm25_scores = _ret._bm25.get_scores(question.lower().split())
    bm25_ranks = np.argsort(-bm25_scores).tolist()
    rrf_scores = _ret._rrf([dense_ranks[:50], bm25_ranks[:50]])
    pre_filter = [idx for idx, _ in sorted(rrf_scores.items(), key=lambda x: -x[1])[:TOP_K*2]]
    superseded_note = build_superseded_note(chunks, pre_filter)

    user_msg = build_user_message(question, chunks)
    try:
        raw = generate(SYSTEM_PROMPT, user_msg)
    except Exception as e:
        print(f"  [LLM ERROR] {e}")
        return {"answerable": False, "answer": f"LLM error: {e}", "sources": [],
                "latency_ms": int((time.time()-t0)*1000), "superseded_note": None}

    # Parse JSON response
    text = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    text = re.sub(r"\s*```$", "", text.strip())
    m = re.search(r"\{.*\}", text, re.DOTALL)
    parsed = {}
    if m:
        try:
            parsed = json.loads(m.group())
        except Exception:
            pass

    return {
        "answerable": parsed.get("answerable", False),
        "answer": parsed.get("answer", ""),
        "sources": parsed.get("sources", []),
        "superseded_note": superseded_note,
        "latency_ms": int((time.time()-t0)*1000),
    }


def check(result: dict, q: dict) -> tuple[bool, list[str]]:
    """Return (passed, list_of_failure_reasons)."""
    failures = []
    answer_lower = (result.get("answer") or "").lower()
    expected_answerable = q.get("answerable", True)
    got_answerable = result.get("answerable", False)

    if expected_answerable != got_answerable:
        failures.append(f"answerable={got_answerable}, expected={expected_answerable}")
        return False, failures

    if not expected_answerable:
        return True, []  # unanswerable — just needed answerable=false

    for fact in q.get("expected_facts", []):
        if fact.lower() not in answer_lower:
            failures.append(f"missing fact: '{fact}'")

    for bad in q.get("forbidden_facts", []):
        if bad.lower() in answer_lower:
            failures.append(f"forbidden fact present: '{bad}'")

    if "expected_doc" in q:
        doc_nos = [s.get("doc_no", "") for s in result.get("sources", [])]
        if not any(q["expected_doc"] in dn for dn in doc_nos):
            failures.append(f"expected source {q['expected_doc']} not cited")

    if q.get("expect_superseded_note") and not result.get("superseded_note"):
        failures.append("expected superseded_note but got none")

    return len(failures) == 0, failures


def main():
    questions = json.loads(QUESTIONS_FILE.read_text())
    rows = []
    passed = 0

    print(f"\n{'ID':>3}  {'PASS':>5}  {'ms':>5}  Question")
    print("-" * 70)

    for q in questions:
        result = call_pipeline(q["question"])
        ok, failures = check(result, q)
        if ok:
            passed += 1
        status = "PASS" if ok else "FAIL"
        print(f"{q['id']:>3}  {status:>5}  {result['latency_ms']:>5}  {q['question'][:55]}")
        if failures:
            for f in failures:
                print(f"          -> {f}")
        rows.append((q, result, ok, failures))

    total = len(questions)
    print(f"\nResult: {passed}/{total} passed\n")

    # Write results.md
    lines = ["# Eval Results\n\n", f"**{passed}/{total} passed**\n\n",
             "| ID | Question | Answerable | Pass | Latency | Notes |\n",
             "|---|---|---|---|---|---|\n"]
    for q, r, ok, failures in rows:
        note = "; ".join(failures) if failures else ""
        lines.append(
            f"| {q['id']} | {q['question'][:60]} | {r['answerable']} | "
            f"{'PASS' if ok else 'FAIL'} | {r['latency_ms']}ms | {note} |\n"
        )
    lines.append("\n## Answers\n\n")
    for q, r, ok, _ in rows:
        lines.append(f"### Q{q['id']}: {q['question']}\n\n")
        lines.append(f"**Answerable:** {r['answerable']}  \n")
        lines.append(f"**Answer:** {r.get('answer','')}\n\n")
        if r.get('superseded_note'):
            lines.append(f"**Superseded note:** {r['superseded_note']}\n\n")
        if r.get('sources'):
            lines.append("**Sources:**\n")
            for s in r['sources']:
                lines.append(f"- {s.get('doc_no')} Rev {s.get('revision')} p.{s.get('page')} s.{s.get('section')}\n")
        lines.append("\n")

    RESULTS_FILE.write_text("".join(lines), encoding="utf-8")
    print(f"Results written to {RESULTS_FILE}")


if __name__ == "__main__":
    main()
