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


def _read_json(path: Path) -> dict | list:
    with open(path) as f:
        return json.load(f)


def _text(*parts: str) -> str:
    return ". ".join(p.strip().rstrip(".") for p in parts if p and p.strip())


# --- Content extractors: each yields (id, type, title, text) tuples ---


def extract_protocols() -> list[tuple[str, str, str, str]]:
    chunks = []
    proto_dir = KB_DIR / "protocols"
    for path in sorted(proto_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue
        d = _read_json(path)
        pid = d.get("protocol_id", path.stem)
        title = d.get("protocol_name", pid)
        parts = [title, d.get("purpose", "")]
        for fm in d.get("failure_modes", []):
            parts.append(fm.get("name", ""))
            parts.append(fm.get("description", ""))
        chunks.append((f"protocol:{pid}", "protocol", title, _text(*parts)))
    return chunks


def extract_subsystems() -> list[tuple[str, str, str, str]]:
    chunks = []
    sub_dir = KB_DIR / "subsystems"
    for path in sorted(sub_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue
        d = _read_json(path)
        sid = d.get("subsystem_id", path.stem)
        title = d.get("display_name", sid)
        parts = [title, d.get("purpose", "")]
        for daemon in d.get("daemons", []):
            parts.append(f"{daemon.get('name', '')}: {daemon.get('role', '')}")
        chunks.append((f"subsystem:{sid}", "subsystem", title, _text(*parts)))
    return chunks


def extract_code_paths() -> list[tuple[str, str, str, str]]:
    chunks = []
    cp_dir = KB_DIR / "code-paths"
    for path in sorted(cp_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue
        d = _read_json(path)
        pid = d.get("path_id", path.stem)
        title = d.get("display_name", pid)
        parts = [title, d.get("trigger", "")]
        for step in d.get("steps", []):
            parts.append(step.get("action", ""))
        chunks.append((f"code-path:{pid}", "code-path", title, _text(*parts)))
    return chunks


def extract_human_errors() -> list[tuple[str, str, str, str]]:
    chunks = []
    he_dir = KB_DIR / "human-errors"
    for path in sorted(he_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue
        d = _read_json(path)
        eid = d.get("error_id", path.stem)
        title = d.get("display_name", eid)
        parts = [title, d.get("pattern", ""), d.get("what_goes_wrong", "")]
        for s in d.get("symptoms", []):
            parts.append(s if isinstance(s, str) else s.get("description", ""))
        parts.append(d.get("correct_procedure", ""))
        chunks.append((f"human-error:{eid}", "human-error", title, _text(*parts)))
    return chunks


def extract_diagnostics() -> list[tuple[str, str, str, str]]:
    chunks = []
    diag_dir = KB_DIR / "diagnostics"
    for path in sorted(diag_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue
        d = _read_json(path)
        tid = d.get("tree_id", path.stem)
        title = d.get("display_name", tid)
        parts = [title, d.get("entry_symptom", "")]
        for node in d.get("nodes", []):
            parts.append(node.get("question", ""))
            parts.append(node.get("finding", ""))
            parts.append(node.get("action", ""))
        chunks.append((f"diagnostic:{tid}", "diagnostic", title, _text(*parts)))
    return chunks


def extract_procedures() -> list[tuple[str, str, str, str]]:
    chunks = []
    proc_dir = KB_DIR / "procedures"
    for path in sorted(proc_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue
        d = _read_json(path)
        pid = d.get("procedure_id", path.stem)
        title = d.get("procedure_name", pid)
        parts = [title, d.get("purpose", "")]
        for step in d.get("steps", []):
            parts.append(step.get("action", ""))
        chunks.append((f"procedure:{pid}", "procedure", title, _text(*parts)))
    return chunks


def extract_best_practices() -> list[tuple[str, str, str, str]]:
    chunks = []
    bp_path = KB_DIR / "best-practices" / "index.json"
    if not bp_path.exists():
        return chunks
    data = _read_json(bp_path)
    for i, p in enumerate(data.get("practices", [])):
        title = p.get("title", f"practice-{i}")
        topic = p.get("topic", "")
        content = p.get("content", "")
        bp_id = f"best-practice:{topic}:{i}"
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


def collect_all_chunks() -> list[tuple[str, str, str, str]]:
    extractors = [
        extract_protocols,
        extract_subsystems,
        extract_code_paths,
        extract_human_errors,
        extract_diagnostics,
        extract_procedures,
        extract_best_practices,
        extract_logs,
        extract_definitions,
    ]
    all_chunks = []
    for fn in extractors:
        all_chunks.extend(fn())
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
            "text": text[:300],
            "embedding": [round(float(v), FLOAT_PRECISION) for v in emb],
        })

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(index, f, separators=(",", ":"))

    size_kb = OUT_PATH.stat().st_size / 1024
    print(f"Wrote {OUT_PATH} ({size_kb:.0f} KB, {len(chunks)} chunks)")


if __name__ == "__main__":
    build_vector_index()
