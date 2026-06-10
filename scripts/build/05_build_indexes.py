#!/usr/bin/env python3
"""Build Layer 3 indexes from committed KB files.

Generates cross-reference maps for O(1) lookup at query time.
Run after any KB content change: python scripts/build/05_build_indexes.py
"""

import json
import sys
from pathlib import Path

KB_DIR = Path(__file__).parent.parent.parent / "knowledge-base"
IDX_DIR = KB_DIR / "indexes"


def _read_json(path: Path) -> dict | list:
    with open(path) as f:
        return json.load(f)


def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  wrote {path.name} ({len(json.dumps(data))} bytes)")


def build_protocol_index():
    path = KB_DIR / "protocols" / "_index.json"
    if path.exists():
        return _read_json(path)
    return {}


def build_daemon_index():
    """Build daemon index from definitions/daemons.json."""
    path = KB_DIR / "definitions" / "daemons.json"
    if not path.exists():
        return {}
    daemons = _read_json(path)
    index = {}
    for d in daemons:
        did = d.get("def_id", "")
        name = d.get("process_name", did.replace("daemon:", ""))
        index[name] = {
            "def_id": did,
            "process_name": name,
            "container": d.get("container", ""),
            "subscribes_to": d.get("subscribes_to", []),
            "writes_to": d.get("writes_to", []),
            "purpose": d.get("purpose", ""),
        }
    return index


def build_db_table_index():
    """Cross-reference: table_name -> protocols, daemons, human_errors that mention it."""
    index = {}

    for proto_file in (KB_DIR / "protocols").glob("*.json"):
        if proto_file.name == "_index.json":
            continue
        proto = _read_json(proto_file)
        for table_entry in proto.get("config_db_tables", []):
            table = table_entry.get("table", "")
            if not table:
                continue
            key = f"CONFIG_DB:{table}"
            if key not in index:
                index[key] = {
                    "table": table, "db": "CONFIG_DB",
                    "protocols": [], "daemons": [], "human_errors": [],
                    **{k: v for k, v in table_entry.items() if k != "table"},
                }
            pid = proto.get("protocol_id", proto_file.stem)
            if pid not in index[key]["protocols"]:
                index[key]["protocols"].append(pid)

    for err_file in (KB_DIR / "human-errors").glob("*.json"):
        if err_file.name == "_index.json":
            continue
        err = _read_json(err_file)
        for db_ref in err.get("ref_dbs", []):
            db_name = db_ref.replace("db:", "").upper()
            for key in index:
                if db_name in key:
                    eid = err.get("error_id", err_file.stem)
                    if eid not in index[key]["human_errors"]:
                        index[key]["human_errors"].append(eid)

    return index


def build_human_error_index():
    """Build keyword index for human error detection."""
    index = {}
    for err_file in (KB_DIR / "human-errors").glob("*.json"):
        if err_file.name == "_index.json":
            continue
        err = _read_json(err_file)
        eid = err.get("error_id", err_file.stem)
        index[eid] = {
            "display_name": err.get("display_name", ""),
            "severity": err.get("severity", ""),
            "keywords": err.get("keywords", []),
            "context_keywords": err.get("context_keywords", []),
        }
    return index


def build_log_message_index():
    """Flatten all log catalogs into one searchable list."""
    messages = []
    for log_file in (KB_DIR / "logs").glob("*.json"):
        catalog = _read_json(log_file)
        daemon = catalog.get("daemon", log_file.stem)
        for msg in catalog.get("messages", []):
            messages.append({"daemon": daemon, **msg})
    return messages


def build_source_refs_index():
    """Build source reference index from code-path files."""
    index = {}
    for cp_file in (KB_DIR / "code-paths").glob("*.json"):
        if cp_file.name == "_index.json":
            continue
        cp = _read_json(cp_file)
        for step in cp.get("steps", []):
            func = step.get("source_function", "")
            if func:
                key = f"{step.get('actor', '')}::{func}"
                index[key] = {
                    "source_file": step.get("source_file", ""),
                    "source_function": func,
                    "actor": step.get("actor", ""),
                    "action": step.get("action", ""),
                    "code_path": cp.get("path_id", ""),
                }
    return index


def main():
    print("Building sonic-kb indexes...")
    IDX_DIR.mkdir(parents=True, exist_ok=True)

    _write_json(IDX_DIR / "_daemon_index.json", build_daemon_index())
    _write_json(IDX_DIR / "_db_table_index.json", build_db_table_index())
    _write_json(IDX_DIR / "_human_error_index.json", build_human_error_index())
    _write_json(IDX_DIR / "_log_message_index.json", build_log_message_index())
    _write_json(IDX_DIR / "_source_refs_index.json", build_source_refs_index())

    print("Done.")


if __name__ == "__main__":
    main()
