#!/usr/bin/env python3
"""Build semantic search vector index for the sonic-kb knowledge base.

Walks all KB content types, extracts embeddable text per chunk, encodes with
sentence-transformers (all-MiniLM-L6-v2), and writes the vector index to
knowledge-base/indexes/_vector_index.json.

Requires: pip install sonic-knowledge-base[vector]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent.parent
KB_DIR = BASE_DIR / "knowledge-base"
OUT_PATH = KB_DIR / "indexes" / "_vector_index.json"

MODEL_NAME = "all-MiniLM-L6-v2"
FLOAT_PRECISION = 4
TEXT_PREVIEW_LEN = 300


def _read_json(path: Path) -> dict | list:
    with open(path) as f:
        return json.load(f)


def _text(*parts: str) -> str:
    return ". ".join(p.strip().rstrip(".") for p in parts if p and p.strip())


# --- Content extractors ---


def _extract_dir(dir_name, content_type, id_field, title_field, text_fn):
    """Generic extractor for directory-based KB content."""
    chunks = []
    for path in sorted((KB_DIR / dir_name).glob("*.json")):
        if path.name.startswith("_"):
            continue
        d = _read_json(path)
        cid = d.get(id_field, path.stem)
        title = d.get(title_field, cid)
        chunks.append((f"{content_type}:{cid}", content_type, title, text_fn(d, title)))
    return chunks


def _proto_text(d, title):
    parts = [title, d.get("purpose", "")]
    for fm in d.get("failure_modes", []):
        parts.extend([fm.get("name", ""), fm.get("description", "")])
    return _text(*parts)


def _subsystem_text(d, title):
    parts = [title, d.get("purpose", "")]
    for daemon in d.get("daemons", []):
        parts.append(f"{daemon.get('name', '')}: {daemon.get('role', '')}")
    return _text(*parts)


def _code_path_text(d, title):
    parts = [title, d.get("trigger", "")]
    for step in d.get("steps", []):
        parts.append(step.get("action", ""))
    return _text(*parts)


def _human_error_text(d, title):
    parts = [title, d.get("pattern", ""), d.get("what_goes_wrong", "")]
    for s in d.get("symptoms", []):
        parts.append(s if isinstance(s, str) else s.get("description", ""))
    parts.append(d.get("correct_procedure", ""))
    return _text(*parts)


def _diagnostic_text(d, title):
    parts = [title, d.get("entry_symptom", "")]
    for node in d.get("nodes", []):
        parts.extend([node.get("question", ""), node.get("finding", ""), node.get("action", "")])
    return _text(*parts)


def _procedure_text(d, title):
    parts = [title, d.get("purpose", "")]
    for step in d.get("steps", []):
        parts.append(step.get("action", ""))
    return _text(*parts)


def extract_best_practices() -> list[tuple[str, str, str, str]]:
    chunks = []
    bp_path = KB_DIR / "best-practices" / "index.json"
    if not bp_path.exists():
        return chunks
    data = _read_json(bp_path)
    for p in data.get("practices", []):
        title = p.get("title", "untitled")
        topic = p.get("topic", "general")
        slug = title.lower()[:40].replace(" ", "-").strip("-")
        bp_id = f"best-practice:{topic}:{slug}"
        content = p.get("content", "")
        chunks.append((bp_id, "best-practice", title, _text(title, content)))
    return chunks


def extract_logs() -> list[tuple[str, str, str, str]]:
    chunks = []
    log_dir = KB_DIR / "logs"
    for path in sorted(log_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue
        d = _read_json(path)
        daemon = d.get("daemon", path.stem)
        for j, msg in enumerate(d.get("messages", [])):
            log_id = msg.get("log_id", f"{daemon}-{j}")
            pattern = msg.get("pattern", "")
            meaning = msg.get("meaning", "")
            causes = ". ".join(msg.get("likely_causes", []))
            title = f"{daemon}: {pattern[:80]}"
            chunks.append((f"log:{log_id}", "log", title, _text(pattern, meaning, causes)))
    return chunks


def extract_definitions() -> list[tuple[str, str, str, str]]:
    chunks = []
    def_dir = KB_DIR / "definitions"

    daemons_path = def_dir / "daemons.json"
    if daemons_path.exists():
        for d in _read_json(daemons_path):
            did = d.get("def_id", "")
            name = d.get("process_name", did)
            purpose = d.get("purpose", "")
            container = d.get("container", "")
            chunks.append((
                f"definition:{did}", "definition",
                f"daemon: {name}",
                _text(f"{name} daemon in {container} container", purpose),
            ))

    timers_path = def_dir / "timers.json"
    if timers_path.exists():
        for t in _read_json(timers_path):
            tid = t.get("def_id", "")
            name = t.get("name", tid)
            protocol = t.get("protocol", "")
            advice = t.get("tuning_advice", "")
            chunks.append((
                f"definition:{tid}", "definition",
                f"timer: {name}",
                _text(f"{name} timer for {protocol}", advice),
            ))

    dbs_path = def_dir / "redis_dbs.json"
    if dbs_path.exists():
        for db in _read_json(dbs_path):
            did = db.get("def_id", "")
            name = db.get("name", did)
            purpose = db.get("purpose", "")
            chunks.append((
                f"definition:{did}", "definition",
                f"database: {name}",
                _text(f"{name} Redis database", purpose),
            ))

    return chunks


_DIR_SOURCES = [
    ("protocols", "protocol", "protocol_id", "protocol_name", _proto_text),
    ("subsystems", "subsystem", "subsystem_id", "display_name", _subsystem_text),
    ("code-paths", "code-path", "path_id", "display_name", _code_path_text),
    ("human-errors", "human-error", "error_id", "display_name", _human_error_text),
    ("diagnostics", "diagnostic", "tree_id", "display_name", _diagnostic_text),
    ("procedures", "procedure", "procedure_id", "procedure_name", _procedure_text),
]


def collect_all_chunks() -> list[tuple[str, str, str, str]]:
    all_chunks = []
    for args in _DIR_SOURCES:
        all_chunks.extend(_extract_dir(*args))
    all_chunks.extend(extract_best_practices())
    all_chunks.extend(extract_logs())
    all_chunks.extend(extract_definitions())
    return all_chunks


def build_vector_index() -> None:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("ERROR: sentence-transformers not installed.", file=sys.stderr)
        print("Run: pip install sonic-knowledge-base[vector]", file=sys.stderr)
        sys.exit(1)

    print(f"Loading model: {MODEL_NAME}")
    model = SentenceTransformer(MODEL_NAME)

    print("Collecting KB chunks...")
    chunks = collect_all_chunks()
    print(f"  {len(chunks)} chunks collected")

    texts = [c[3] for c in chunks]
    print("Encoding embeddings...")
    t0 = time.time()
    embeddings = model.encode(texts, show_progress_bar=True, normalize_embeddings=True)
    elapsed = time.time() - t0
    print(f"  Encoded in {elapsed:.1f}s")

    index = {
        "model": MODEL_NAME,
        "dimension": embeddings.shape[1],
        "chunk_count": len(chunks),
        "chunks": [],
    }
    for (cid, ctype, title, text), emb in zip(chunks, embeddings):
        index["chunks"].append({
            "id": cid,
            "type": ctype,
            "title": title,
            "text": text[:TEXT_PREVIEW_LEN],
            "embedding": [round(float(v), FLOAT_PRECISION) for v in emb],
        })

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(index, f, separators=(",", ":"))

    size_kb = OUT_PATH.stat().st_size / 1024
    print(f"Wrote {OUT_PATH} ({size_kb:.0f} KB, {len(chunks)} chunks)")


if __name__ == "__main__":
    build_vector_index()
