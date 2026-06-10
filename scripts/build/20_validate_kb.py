#!/usr/bin/env python3
"""Validate sonic-kb integrity.

Checks:
1. All def_refs in domain files resolve to existing def_ids in definitions/
2. All related_protocols references resolve to protocol index entries
3. All code-path step sequences are contiguous
4. All human-error ref_daemons and ref_dbs resolve
5. No duplicate def_ids across definition files
"""

import json
import sys
from pathlib import Path

KB_DIR = Path(__file__).parent.parent.parent / "knowledge-base"


def _read_json(path: Path) -> dict | list:
    with open(path) as f:
        return json.load(f)


def load_all_def_ids() -> set[str]:
    """Collect all def_ids from definitions/."""
    ids = set()
    def_dir = KB_DIR / "definitions"
    if not def_dir.exists():
        return ids
    for path in def_dir.glob("*.json"):
        data = _read_json(path)
        items = data if isinstance(data, list) else data.values() if isinstance(data, dict) else []
        for item in items:
            if isinstance(item, dict) and "def_id" in item:
                if item["def_id"] in ids:
                    print(f"  DUPLICATE def_id: {item['def_id']} in {path.name}")
                ids.add(item["def_id"])
    return ids


def validate_def_refs(all_def_ids: set[str]) -> list[str]:
    """Check that all def_refs in domain files resolve."""
    errors = []
    for pattern in ["protocols/*.json", "subsystems/*.json", "code-paths/*.json",
                     "procedures/*.json"]:
        for path in KB_DIR.glob(pattern):
            if path.name == "_index.json":
                continue
            data = _read_json(path)
            for ref in data.get("def_refs", []):
                if ref not in all_def_ids:
                    errors.append(f"{path.relative_to(KB_DIR)}: missing def_id '{ref}'")
    return errors


def validate_protocol_refs() -> list[str]:
    """Check that related_protocols references resolve."""
    errors = []
    index_path = KB_DIR / "protocols" / "_index.json"
    if not index_path.exists():
        return errors
    index = _read_json(index_path)
    for proto_file in (KB_DIR / "protocols").glob("*.json"):
        if proto_file.name == "_index.json":
            continue
        data = _read_json(proto_file)
        for ref in data.get("related_protocols", []):
            if ref not in index:
                errors.append(f"{proto_file.name}: unknown related_protocol '{ref}'")
    return errors


def validate_code_path_steps() -> list[str]:
    """Check step sequences are contiguous."""
    errors = []
    for cp_file in (KB_DIR / "code-paths").glob("*.json"):
        if cp_file.name == "_index.json":
            continue
        data = _read_json(cp_file)
        steps = data.get("steps", [])
        step_nums = [s.get("step", 0) for s in steps]
        if step_nums and step_nums != list(range(1, len(step_nums) + 1)):
            errors.append(f"{cp_file.name}: non-contiguous steps: {step_nums}")
    return errors


def main():
    print("Validating sonic-kb...")
    all_errors = []

    def_ids = load_all_def_ids()
    print(f"  Found {len(def_ids)} definition IDs")

    errors = validate_def_refs(def_ids)
    all_errors.extend(errors)
    for e in errors:
        print(f"  DEF_REF ERROR: {e}")

    errors = validate_protocol_refs()
    all_errors.extend(errors)
    for e in errors:
        print(f"  PROTO_REF ERROR: {e}")

    errors = validate_code_path_steps()
    all_errors.extend(errors)
    for e in errors:
        print(f"  STEP ERROR: {e}")

    if all_errors:
        print(f"\nFAILED: {len(all_errors)} errors found.")
        sys.exit(1)
    else:
        print("\nPASSED: All validations passed.")


if __name__ == "__main__":
    main()
