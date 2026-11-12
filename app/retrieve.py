"""
retrieve.py - hybrid dense + BM25 search with revision handling.
"""
import json
import numpy as np
from rank_bm25 import BM25Okapi

from app.config import (
    CHUNKS_FILE, INDEX_FILE, TOP_K, SIMILARITY_THRESHOLD, EMBED_MODEL, BGE_QUERY_PREFIX
)

# Module-level cache — loaded once per process
_chunks: list[dict] | None = None
_embeddings: np.ndarray | None = None
_bm25: BM25Okapi | None = None
_model = None


def _load():
    """Load index and model into memory. Safe to call multiple times."""
    global _chunks, _embeddings, _bm25, _model
    if _chunks is not None:
        return  # already loaded

    with open(CHUNKS_FILE, encoding="utf-8") as f:
        _chunks = json.load(f)

    data = np.load(str(INDEX_FILE))
    _embeddings = data["embeddings"].astype(np.float32)

    tokenized = [c["text"].lower().split() for c in _chunks]
    _bm25 = BM25Okapi(tokenized)

    from sentence_transformers import SentenceTransformer
    _model = SentenceTransformer(EMBED_MODEL)


def _cosine_scores(query_vec: np.ndarray) -> np.ndarray:
    return (_embeddings @ query_vec).astype(float)


def _rrf(rank_lists: list[list[int]], k: int = 60) -> dict[int, float]:
    """Reciprocal Rank Fusion — combine multiple ranked lists."""
    scores: dict[int, float] = {}
    for ranks in rank_lists:
        for rank, idx in enumerate(ranks):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (k + rank + 1)
    return scores


def retrieve(question: str, top_k: int = TOP_K) -> tuple[list[dict], float]:
    """
    Return (chunks, best_dense_score).
    Hybrid dense + BM25 search with revision filtering.
    """
    _load()

    # Dense retrieval
    q_vec = _model.encode(
        BGE_QUERY_PREFIX + question, normalize_embeddings=True
    ).astype(np.float32)
    dense_scores = _cosine_scores(q_vec)
    dense_ranks = np.argsort(-dense_scores).tolist()

    # BM25 retrieval
    bm25_scores = _bm25.get_scores(question.lower().split())
    bm25_ranks = np.argsort(-bm25_scores).tolist()

    # Combine with Reciprocal Rank Fusion
    rrf_scores = _rrf([dense_ranks[:50], bm25_ranks[:50]])
    candidates = sorted(rrf_scores.items(), key=lambda x: -x[1])
    candidate_indices = [idx for idx, _ in candidates[: top_k * 2]]

    # Best dense score for threshold check
    best_dense = float(dense_scores[dense_ranks[0]]) if dense_ranks else 0.0

    # Boost current-revision chunks x1.2
    boosted = {}
    for idx in candidate_indices:
        score = rrf_scores[idx]
        if not _chunks[idx].get("superseded", False):
            score *= 1.2
        boosted[idx] = score

    top_indices = sorted(boosted, key=lambda i: -boosted[i])[:top_k]

    # Expand SAF-SOP-003 sections 5+6 together (LOTO rule + exception)
    top_indices = _expand_loto_sections(top_indices)

    # Expand MNT operating params when PM schedule is retrieved (gets spindle runout limit)
    top_indices = _expand_operating_params(top_indices)

    # Drop superseded chunks when current revision exists for same doc_no
    top_indices = _filter_superseded(top_indices)

    result_chunks = []
    for idx in top_indices:
        c = dict(_chunks[idx])
        c["score"] = round(float(dense_scores[idx]), 4)
        result_chunks.append(c)

    return result_chunks, best_dense


def _expand_loto_sections(indices: list[int]) -> list[int]:
    """If SAF-SOP-003 §5 or §6 is retrieved, include both."""
    has_loto = any(
        _chunks[i]["doc_no"] == "SAF-SOP-003" and _chunks[i]["section_number"] in ("5", "6")
        for i in indices
    )
    if not has_loto:
        return indices
    extra = [
        i for i, c in enumerate(_chunks)
        if c["doc_no"] == "SAF-SOP-003" and c["section_number"] in ("5", "6")
        and i not in indices
    ]
    return indices + extra[:2]


def _expand_operating_params(indices: list[int]) -> list[int]:
    """If MNT PM schedule (§4) is retrieved, also include operating params (§3).
    This ensures spindle runout limit (0.005 mm) is always in context."""
    has_pm = any(
        _chunks[i]["doc_no"] == "MNT-MAN-CNC-02" and _chunks[i]["section_number"] == "4"
        for i in indices
    )
    if not has_pm:
        return indices
    extra = [
        i for i, c in enumerate(_chunks)
        if c["doc_no"] == "MNT-MAN-CNC-02" and c["section_number"] == "3"
        and i not in indices
    ]
    return indices + extra[:2]


def _filter_superseded(indices: list[int]) -> list[int]:
    """Drop superseded chunks when a current-revision chunk exists for the same doc_no."""
    by_doc: dict[str, list[int]] = {}
    for i in indices:
        by_doc.setdefault(_chunks[i]["doc_no"], []).append(i)

    result = []
    for dn, idxs in by_doc.items():
        has_current = any(not _chunks[i]["superseded"] for i in idxs)
        for i in idxs:
            if has_current and _chunks[i]["superseded"]:
                continue
            result.append(i)
    return result


def build_superseded_note(question_chunks: list[dict], pre_filter_indices: list[int]) -> str | None:
    """Build a human-readable note when a superseded revision also matched."""
    current_doc_nos = {c["doc_no"] for c in question_chunks if not c.get("superseded")}
    notes = []
    seen: set[str] = set()
    for i in pre_filter_indices:
        c = _chunks[i]
        if c.get("superseded") and c["doc_no"] in current_doc_nos and c["doc_no"] not in seen:
            seen.add(c["doc_no"])
            current_rev = next(
                (qc["revision"] for qc in question_chunks
                 if qc["doc_no"] == c["doc_no"] and not qc.get("superseded")), "?"
            )
            current_date = next(
                (qc["effective_date"] for qc in question_chunks
                 if qc["doc_no"] == c["doc_no"] and not qc.get("superseded")), ""
            )
            note = (
                f"Note: An older revision ({c['doc_no']} Rev {c['revision']}) also matched. "
                f"Rev {current_rev}"
                + (f", effective {current_date}," if current_date else "")
                + " is the current version and supersedes it."
            )
            notes.append(note)
    return " ".join(notes) if notes else None


def get_all_chunks() -> list[dict]:
    _load()
    return _chunks
