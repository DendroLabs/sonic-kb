#!/usr/bin/env python3
"""Verify KB source references against the cloned SONiC repos.

Checks every source reference in knowledge-base/ against build/repos/:
  - "source_file": "repo:path" (+ sibling "source_function") — path must exist,
    function name must appear in the file
  - "source_path": "path" — must exist in one of the cloned repos
  - "source_ref": free text — embedded path-like tokens are checked (warning only)

Requires scripts/build/01_clone_repos.sh to have been run.
Exits 1 on hard failures (missing source_file/source_path), 0 otherwise.

Output: build/artifacts/source_ref_verification.json
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
KB_DIR = ROOT / "knowledge-base"
REPOS_DIR = ROOT / "build" / "repos"
OUT_PATH = ROOT / "build" / "artifacts" / "source_ref_verification.json"

REPO_SEARCH_ORDER = [
    "sonic-swss", "sonic-sairedis", "sonic-frr",
    "sonic-platform-daemons", "sonic-buildimage",
    "sonic-dbsyncd", "sonic-stp", "sonic-utilities",
]

EMBEDDED_PATH = re.compile(r"\b([\w-]+(?:/[\w.-]+)+\.(?:c|cpp|h|hpp|py))\b")


def _walk(obj, visit, ancestry=()):
    """Recursively visit every dict in a JSON structure."""
    if isinstance(obj, dict):
        visit(obj, ancestry)
        for v in obj.values():
            _walk(v, visit, ancestry)
    elif isinstance(obj, list):
        for v in obj:
            _walk(v, visit, ancestry)


def _find_repo(path: str) -> str | None:
    # normalize buildimage submodule-style prefixes: src/<repo>/... or <repo>/...
    parts = path.split("/")
    if parts[0] == "src" and len(parts) > 2 and parts[1] in REPO_SEARCH_ORDER:
        path = "/".join(parts[2:])
    elif parts[0] in REPO_SEARCH_ORDER and parts[0] != "sonic-platform-daemons":
        path = "/".join(parts[1:])
    for repo in REPO_SEARCH_ORDER:
        if (REPOS_DIR / repo / path).is_file():
            return repo
    return None


def _function_in_file(repo: str, path: str, func: str) -> bool:
    name = func.replace("()", "")
    if "::" in name:
        name = name.split("::")[-1]
    if "." in name:
        name = name.split(".")[-1]
    try:
        text = (REPOS_DIR / repo / path).read_text(errors="replace")
    except OSError:
        return False
    return re.search(r"\b" + re.escape(name) + r"\s*\(", text) is not None


def collect_refs(kb_file: Path) -> list[dict]:
    refs = []

    def visit(d, _ancestry):
        if "source_file" in d and isinstance(d["source_file"], str):
            refs.append({
                "kind": "source_file",
                "value": d["source_file"],
                "function": d.get("source_function"),
            })
        if "source_path" in d and isinstance(d["source_path"], str):
            refs.append({"kind": "source_path", "value": d["source_path"]})
        if "source_ref" in d and isinstance(d["source_ref"], str):
            for m in EMBEDDED_PATH.finditer(d["source_ref"]):
                refs.append({"kind": "source_ref_embedded", "value": m.group(1)})

    _walk(json.load(open(kb_file)), visit)
    for r in refs:
        r["kb_file"] = str(kb_file.relative_to(KB_DIR))
    return refs


def verify_ref(ref: dict) -> dict:
    result = dict(ref)
    if ref["kind"] == "source_file":
        repo, _, path = ref["value"].partition(":")
        if not (REPOS_DIR / repo / path).is_file():
            result["status"] = "missing_file"
        elif ref.get("function") and not _function_in_file(repo, path, ref["function"]):
            result["status"] = "missing_function"
        else:
            result["status"] = "ok"
    else:
        repo = _find_repo(ref["value"])
        result["status"] = "ok" if repo else "missing_file"
        if repo:
            result["resolved_repo"] = repo
    return result


def main():
    if not REPOS_DIR.exists() or not any(REPOS_DIR.iterdir()):
        print(f"ERROR: {REPOS_DIR} is empty. Run scripts/build/01_clone_repos.sh first.")
        sys.exit(1)

    print("Verifying KB source references against build/repos/...")
    results = []
    for kb_file in sorted(KB_DIR.rglob("*.json")):
        results.extend(verify_ref(r) for r in collect_refs(kb_file))

    hard_kinds = {"source_file", "source_path"}
    failures = [r for r in results if r["status"] != "ok" and r["kind"] in hard_kinds]
    warnings = [r for r in results if r["status"] != "ok" and r["kind"] not in hard_kinds]
    ok = [r for r in results if r["status"] == "ok"]

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(results, f, indent=1)

    print(f"  {len(ok)} ok, {len(failures)} failures, {len(warnings)} warnings "
          f"({len(results)} refs total)")
    for r in failures:
        func = f" :: {r['function']}" if r.get("function") else ""
        print(f"  FAIL [{r['status']}] {r['kb_file']}: {r['value']}{func}")
    for r in warnings:
        print(f"  warn [{r['status']}] {r['kb_file']}: {r['value']} (free-text ref)")
    print(f"Wrote {OUT_PATH.relative_to(ROOT)}")

    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
