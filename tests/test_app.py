"""
tests/test_app.py — pytest tests for ingestion, retrieval, and API schema.
Run: pytest tests/ -v
"""
import json, pytest
from pathlib import Path

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def chunks():
    chunks_file = Path(__file__).parent.parent / "data" / "chunks.json"
    if not chunks_file.exists():
        pytest.skip("Index not built — run python -m app.ingest first")
    return json.loads(chunks_file.read_text())


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


# ── Ingestion tests ───────────────────────────────────────────────────────────

def test_chunks_have_required_fields(chunks):
    required = {"doc_no", "revision", "page_number", "text", "section_number"}
    for c in chunks[:20]:
        assert required.issubset(c.keys()), f"Missing fields in chunk: {c.keys()}"


def test_rev03_marked_superseded(chunks):
    rev03 = [c for c in chunks if c["doc_no"] == "QC-SOP-014" and c["revision"] == "03"]
    assert rev03, "No Rev 03 chunks found"
    assert all(c["superseded"] for c in rev03), "Rev 03 chunks should be superseded"


def test_rev04_not_superseded(chunks):
    rev04 = [c for c in chunks if c["doc_no"] == "QC-SOP-014" and c["revision"] == "04"]
    assert rev04, "No Rev 04 chunks found"
    assert all(not c["superseded"] for c in rev04), "Rev 04 should not be superseded"


def test_header_footer_stripped(chunks):
    """Uncontrolled copy text should not appear in chunk text."""
    for c in chunks:
        assert "Uncontrolled copy when printed" not in c["text"], \
            f"Header not stripped in chunk: {c['text'][:100]}"


def test_alarm_table_rows(chunks):
    """Alarm table must have rows for AL-101, AL-104, AL-210, AL-305, AL-412."""
    alarm_chunks = [c for c in chunks if c.get("chunk_type") == "table_row"
                    and "alarm" in c.get("section_title", "").lower()]
    alarm_text = " ".join(c["text"] for c in alarm_chunks)
    for alarm_id in ["AL-101", "AL-104", "AL-210", "AL-305", "AL-412"]:
        assert alarm_id in alarm_text, f"{alarm_id} not found in alarm table chunks"


# ── API schema tests ──────────────────────────────────────────────────────────

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_ask_schema(client):
    r = client.post("/ask", json={"question": "What is the coolant concentration?"})
    assert r.status_code == 200
    data = r.json()
    assert "answerable" in data
    assert "answer" in data
    assert "sources" in data
    assert "latency_ms" in data


def test_ask_empty_question(client):
    r = client.post("/ask", json={"question": ""})
    assert r.status_code == 422


def test_unanswerable_question(client):
    r = client.post("/ask", json={"question": "What is the maximum spindle speed of the TX-200?"})
    assert r.status_code == 200
    data = r.json()
    assert data["answerable"] is False, "Should return answerable=false for out-of-scope question"


def test_documents_endpoint(client):
    r = client.get("/documents")
    assert r.status_code == 200
    docs = r.json()
    assert isinstance(docs, list)
    doc_nos = [d["doc_no"] for d in docs]
    assert "QC-SOP-014" in doc_nos
