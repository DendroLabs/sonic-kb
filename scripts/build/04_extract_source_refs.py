#!/usr/bin/env python3
"""Extract function definition locations from cloned SONiC source repos.

Builds a function index (repo, file, line, function) used to ground code-path
steps and to back the search_source_ref tool:
  - sonic-swss / sonic-sairedis (C++): Class::method definitions
  - sonic-frr (C): GNU-style functions (name at column 0)
  - sonic-platform-daemons (Python): class methods and functions

Output: build/artifacts/source_functions.json
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
REPOS_DIR = ROOT / "build" / "repos"
OUT_PATH = ROOT / "build" / "artifacts" / "source_functions.json"

SKIP_DIRS = {"tests", "test", "doc", "docs", ".git", "debian"}

# C++ method definition at column 0: optional return type tokens, then Class::name(
CPP_DEF = re.compile(
    r"^(?:[\w:<>,*&~\[\]]+\s+)*([A-Za-z_]\w*::~?[A-Za-z_]\w*)\s*\(", re.MULTILINE
)
# GNU C style: function name at column 0, return type on the preceding line
C_DEF_COL0 = re.compile(r"^([a-z_]\w*)\s*\(", re.MULTILINE)
# Same-line style: return type tokens then name, all starting at column 0
C_DEF_INLINE = re.compile(
    r"^(?:static\s+|const\s+|unsigned\s+|signed\s+|inline\s+|struct\s+\w+\s+|"
    r"enum\s+\w+\s+|union\s+\w+\s+|[a-z_]\w*\s+)+\**([a-z_]\w*)\s*\(",
    re.MULTILINE,
)
C_KEYWORDS = {"if", "while", "for", "switch", "return", "sizeof", "defined",
              "else", "do", "case", "goto", "typedef"}


def _is_definition(text: str, open_paren: int) -> bool:
    """True if the '(' at open_paren belongs to a definition (body follows)
    rather than a declaration (';' follows the closing paren)."""
    depth = 0
    for i in range(open_paren, min(open_paren + 4000, len(text))):
        c = text[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                rest = text[i + 1:i + 200].lstrip()
                return rest.startswith("{")
    return False

PY_CLASS = re.compile(r"^class\s+(\w+)")
PY_DEF = re.compile(r"^(\s*)def\s+(\w+)\s*\(")

REPO_CONFIG = {
    "sonic-swss": {"suffixes": (".cpp",), "lang": "cpp"},
    "sonic-sairedis": {"suffixes": (".cpp",), "lang": "cpp"},
    "sonic-frr": {"suffixes": (".c",), "lang": "c",
                  "subdirs": ["bgpd", "zebra", "bfdd", "ospfd", "staticd", "lib"]},
    "sonic-platform-daemons": {"suffixes": (".py",), "lang": "py"},
}


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


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def extract_cpp(text: str) -> list[tuple[int, str]]:
    return [(_line_of(text, m.start()), m.group(1) + "()")
            for m in CPP_DEF.finditer(text)]


def extract_c(text: str) -> list[tuple[int, str]]:
    found = {}
    for m in C_DEF_INLINE.finditer(text):
        name = m.group(1)
        if name in C_KEYWORDS or not _is_definition(text, m.end() - 1):
            continue
        found[m.start()] = name
    for m in C_DEF_COL0.finditer(text):
        name = m.group(1)
        if name in C_KEYWORDS or m.start() in found:
            continue
        # require a plausible return type on the previous line (GNU style)
        prev_end = text.rfind("\n", 0, m.start())
        prev_start = text.rfind("\n", 0, prev_end) + 1
        prev = text[prev_start:prev_end].strip() if prev_end > 0 else ""
        if not prev or prev.endswith((";", ",", "\\", "{", "}", ")", ":")):
            continue
        if not re.fullmatch(r"(?:static\s+|const\s+|struct\s+|enum\s+|unsigned\s+)*[\w*\s]+\**", prev):
            continue
        if not _is_definition(text, m.end() - 1):
            continue
        found[m.start()] = name
    return [(_line_of(text, pos), name + "()") for pos, name in sorted(found.items())]


def extract_py(text: str) -> list[tuple[int, str]]:
    funcs = []
    current_class = None
    for lineno, line in enumerate(text.splitlines(), start=1):
        cm = PY_CLASS.match(line)
        if cm:
            current_class = cm.group(1)
            continue
        dm = PY_DEF.match(line)
        if dm:
            indent, name = dm.group(1), dm.group(2)
            if indent and current_class:
                funcs.append((lineno, f"{current_class}.{name}()"))
            else:
                if not indent:
                    current_class = None
                funcs.append((lineno, name + "()"))
    return funcs


EXTRACTORS = {"cpp": extract_cpp, "c": extract_c, "py": extract_py}


def main():
    if not REPOS_DIR.exists():
        print(f"ERROR: {REPOS_DIR} not found. Run scripts/build/01_clone_repos.sh first.")
        sys.exit(1)

    index = []
    for repo, cfg in REPO_CONFIG.items():
        repo_dir = REPOS_DIR / repo
        if not repo_dir.exists():
            print(f"  WARN: {repo} not cloned, skipping")
            continue
        extractor = EXTRACTORS[cfg["lang"]]
        count_before = len(index)
        for path in _iter_source_files(repo_dir, cfg):
            try:
                text = path.read_text(errors="replace")
            except OSError:
                continue
            rel = str(path.relative_to(repo_dir))
            for line, func in extractor(text):
                index.append({"repo": repo, "file": rel, "line": line, "function": func})
        print(f"  {repo}: {len(index) - count_before} functions")

    index.sort(key=lambda e: (e["repo"], e["file"], e["line"]))
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(index, f, indent=1)

    print(f"Extracted {len(index)} function definitions")
    print(f"Wrote {OUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
