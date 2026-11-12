"""
main.py — FastAPI app: routes, static serving, startup logic.
"""
import json, re, time, logging, socket
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, field_validator

from app.config import CHUNKS_FILE, INDEX_FILE, SIMILARITY_THRESHOLD, TOP_K, BGE_QUERY_PREFIX

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = FastAPI(title="Kaveri Precision Copilot")

STATIC_DIR = Path(__file__).parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ── Startup ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    if not INDEX_FILE.exists() or not CHUNKS_FILE.exists():
        log.info("Index not found — running ingestion ...")
        from app.ingest import run_ingest
        run_ingest()

    # Eagerly load index + model so first request is fast
    from app.retrieve import _load
    _load()

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        lan_ip = s.getsockname()[0]
        s.close()
    except Exception:
        lan_ip = "localhost"
    print(f"\nLAN URL: http://{lan_ip}:8000  (open on phone/tablet on same Wi-Fi)\n")


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/health")
def health():
    return {"status": "ok", "index_exists": INDEX_FILE.exists()}


@app.get("/documents")
def documents():
    if not CHUNKS_FILE.exists():
        return []
    from app.retrieve import get_all_chunks
    chunks = get_all_chunks()
    seen = {}
    for c in chunks:
        key = (c["doc_no"], c["revision"])
        if key not in seen:
            seen[key] = {
                "doc_no": c["doc_no"],
                "revision": c["revision"],
                "effective_date": c.get("effective_date", ""),
                "file_name": c["file_name"],
                "superseded": c.get("superseded", False),
            }
    return list(seen.values())


@app.post("/reindex")
def reindex():
    import app.retrieve as r
    r._chunks = None; r._embeddings = None; r._bm25 = None; r._model = None
    from app.ingest import run_ingest
    run_ingest()
    return {"status": "ok"}


class AskRequest(BaseModel):
    question: str

    @field_validator("question")
    @classmethod
    def validate_question(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Question cannot be empty.")
        if len(v) > 500:
            raise ValueError("Question too long (max 500 chars).")
        return v


@app.post("/ask")
def ask(req: AskRequest):
    import numpy as np
    import app.retrieve as _ret
    from app.retrieve import retrieve, build_superseded_note
    from app.prompts import SYSTEM_PROMPT, build_user_message
    from app.llm import generate

    t0 = time.time()
    _ret._load()

    chunks, best_score = retrieve(req.question)
    log.info("Q: %r | best_score=%.3f | chunks=%d", req.question, best_score, len(chunks))

    # Refusal layer 1: below threshold
    if best_score < SIMILARITY_THRESHOLD or not chunks:
        log.info("-> answerable=false (threshold)")
        return _not_found(t0)

    # Build superseded note from pre-filter candidates
    q_vec = _ret._model.encode(BGE_QUERY_PREFIX + req.question, normalize_embeddings=True).astype(np.float32)
    dense_scores = _ret._cosine_scores(q_vec)
    dense_ranks = np.argsort(-dense_scores).tolist()
    bm25_scores = _ret._bm25.get_scores(req.question.lower().split())
    bm25_ranks = np.argsort(-bm25_scores).tolist()
    rrf_scores = _ret._rrf([dense_ranks[:50], bm25_ranks[:50]])
    pre_filter = [idx for idx, _ in sorted(rrf_scores.items(), key=lambda x: -x[1])[:TOP_K * 2]]
    superseded_note = build_superseded_note(chunks, pre_filter)

    # Call LLM
    user_msg = build_user_message(req.question, chunks)
    try:
        raw = generate(SYSTEM_PROMPT, user_msg)
    except Exception as e:
        log.error("LLM error: %s", e)
        raise HTTPException(502, f"LLM unavailable: {e}")

    parsed = _parse_llm_response(raw)

    # Refusal layer 2: model says not answerable
    if not parsed.get("answerable", False):
        log.info("-> answerable=false (model)")
        return _not_found(t0)

    # Citation check: drop unverifiable sources but keep the answer
    verified_sources = _verify_sources(parsed.get("sources", []), chunks)
    # Only fall back to not-found if model explicitly said not answerable
    # (verified_sources may be empty if LLM quoted paraphrases — that's ok)

    latency = int((time.time() - t0) * 1000)
    log.info("-> answerable=true | latency=%dms", latency)

    return {
        "answerable": True,
        "answer": parsed.get("answer", ""),
        "superseded_note": superseded_note,
        "sources": verified_sources,
        "latency_ms": latency,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _not_found(t0: float) -> dict:
    return {
        "answerable": False,
        "answer": "",
        "superseded_note": None,
        "sources": [],
        "latency_ms": int((time.time() - t0) * 1000),
    }


def _parse_llm_response(raw: str) -> dict:
    """Strip code fences, parse JSON; return empty dict on failure."""
    text = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    text = re.sub(r"\s*```$", "", text.strip())
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        log.warning("No JSON found in LLM response: %r", raw[:200])
        return {"answerable": False}
    try:
        return json.loads(m.group())
    except json.JSONDecodeError:
        log.warning("JSON parse failed: %r", raw[:200])
        return {"answerable": False}


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _verify_sources(sources: list[dict], chunks: list[dict]) -> list[dict]:
    """Keep only sources whose quote appears (normalised) in a retrieved chunk."""
    chunk_texts = [_normalize(c["text"]) for c in chunks]
    verified = []
    for src in sources:
        quote = _normalize(src.get("quote", ""))
        if not quote:
            continue
        if any(quote in ct for ct in chunk_texts):
            match = next(
                (c for c in chunks
                 if c["doc_no"] == src.get("doc_no") and
                    str(c["page_number"]) == str(src.get("page", ""))),
                chunks[0] if chunks else {}
            )
            verified.append({
                "doc_no": src.get("doc_no", ""),
                "revision": src.get("revision", ""),
                "file_name": match.get("file_name", ""),
                "page": src.get("page", match.get("page_number", 0)),
                "section": src.get("section", ""),
                "quote": src.get("quote", ""),
                "score": match.get("score", 0.0),
            })
    return verified
