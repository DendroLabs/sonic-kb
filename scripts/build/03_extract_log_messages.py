#!/usr/bin/env python3
"""Extract log message patterns from cloned SONiC source repos.

Scans for logging calls and records the message template with its source
location, so KB log catalogs can be grounded in real source strings:
  - sonic-swss / sonic-sairedis (C++): SWSS_LOG_ERROR / WARN / NOTICE / THROW
  - sonic-frr (C): zlog_err / zlog_warning / zlog_notice, flog_err / flog_warn
  - sonic-platform-daemons (Python): log_error / log_warning / log_notice

Output: build/artifacts/log_messages.json
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
REPOS_DIR = ROOT / "build" / "repos"
OUT_PATH = ROOT / "build" / "artifacts" / "log_messages.json"

SKIP_DIRS = {"tests", "test", "doc", "docs", ".git", "debian"}

# A sequence of adjacent C string literals: "..." "..."
C_STR = r'((?:"(?:[^"\\]|\\.)*"\s*)+)'

C_PATTERNS = [
    (re.compile(r"SWSS_LOG_(ERROR|WARN|NOTICE|THROW)\s*\(\s*" + C_STR), None),
    (re.compile(r"\bzlog_(err|warn|notice)\s*\(\s*" + C_STR), None),
    (re.compile(r"\bflog_(err|warn)\s*\(\s*EC_\w+\s*,\s*" + C_STR), None),
]

PY_PATTERN = re.compile(
    r"log_(error|warning|notice)\s*\(\s*([fr]?)(\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*')"
)

LEVEL_MAP = {
    "ERROR": "ERROR", "err": "ERROR", "error": "ERROR", "THROW": "ERROR",
    "WARN": "WARNING", "warn": "WARNING", "warning": "WARNING",
    "NOTICE": "NOTICE", "notice": "NOTICE",
}

REPO_CONFIG = {
    "sonic-swss": {"suffixes": (".cpp", ".c", ".h"), "lang": "c"},
    "sonic-sairedis": {"suffixes": (".cpp", ".c", ".h"), "lang": "c"},
    "sonic-frr": {"suffixes": (".c",), "lang": "c",
                  "subdirs": ["bgpd", "zebra", "bfdd", "ospfd", "staticd", "lib"]},
    "sonic-platform-daemons": {"suffixes": (".py",), "lang": "py"},
}


def _join_c_literals(raw: str) -> str:
    parts = re.findall(r'"((?:[^"\\]|\\.)*)"', raw)
    return "".join(parts)


def _iter_source_files(repo_dir: Path, cfg: dict):
    roots = [repo_dir / d for d in cfg.get("subdirs", [])] or [repo_dir]
    for r in roots:
        if not r.exists():
            continue
        for path in r.rglob("*"):
            if path.suffix not in cfg["suffixes"]:
                continue
            if any(part in SKIP_DIRS for part in path.relative_to(repo_dir).parts):
                continue
            yield path


def extract_from_file(path: Path, repo: str, repo_dir: Path, lang: str) -> list[dict]:
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return []
    rel = str(path.relative_to(repo_dir))
    messages = []

    if lang == "c":
        for pattern, _ in C_PATTERNS:
            for m in pattern.finditer(text):
                msg = _join_c_literals(m.group(2))
                if len(msg) < 8:
                    continue  # skip trivial/empty format strings
                messages.append({
                    "repo": repo,
                    "file": rel,
                    "line": text.count("\n", 0, m.start()) + 1,
                    "level": LEVEL_MAP[m.group(1)],
                    "message": msg,
                })
    else:
        for m in PY_PATTERN.finditer(text):
            msg = m.group(3)[1:-1]
            if len(msg) < 8:
                continue
            messages.append({
                "repo": repo,
                "file": rel,
                "line": text.count("\n", 0, m.start()) + 1,
                "level": LEVEL_MAP[m.group(1)],
                "message": msg,
            })
    return messages


def main():
    if not REPOS_DIR.exists():
        print(f"ERROR: {REPOS_DIR} not found. Run scripts/build/01_clone_repos.sh first.")
        sys.exit(1)

    all_messages = []
    for repo, cfg in REPO_CONFIG.items():
        repo_dir = REPOS_DIR / repo
        if not repo_dir.exists():
            print(f"  WARN: {repo} not cloned, skipping")
            continue
        count_before = len(all_messages)
        for path in _iter_source_files(repo_dir, cfg):
            all_messages.extend(extract_from_file(path, repo, repo_dir, cfg["lang"]))
        print(f"  {repo}: {len(all_messages) - count_before} messages")

    all_messages.sort(key=lambda m: (m["repo"], m["file"], m["line"]))
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(all_messages, f, indent=1)

    by_level = {}
    for m in all_messages:
        by_level[m["level"]] = by_level.get(m["level"], 0) + 1
    print(f"Extracted {len(all_messages)} log messages {by_level}")
    print(f"Wrote {OUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
