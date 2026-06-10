#!/usr/bin/env python3
"""Extract CONFIG_DB table schemas from sonic-buildimage YANG models.

Parses src/sonic-yang-models/yang-models/sonic-*.yang from the cloned
sonic-buildimage repo (see 01_clone_repos.sh) and emits one schema entry per
CONFIG_DB table: key fields, leaf fields with types and descriptions.

Output: build/artifacts/db_schemas.json
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
YANG_DIR = ROOT / "build" / "repos" / "sonic-buildimage" / "src" / "sonic-yang-models" / "yang-models"
OUT_PATH = ROOT / "build" / "artifacts" / "db_schemas.json"


class Node:
    __slots__ = ("keyword", "arg", "children")

    def __init__(self, keyword, arg):
        self.keyword = keyword
        self.arg = arg
        self.children = []

    def find(self, keyword):
        return [c for c in self.children if c.keyword == keyword]

    def first(self, keyword):
        for c in self.children:
            if c.keyword == keyword:
                return c
        return None


def _tokenize(text: str):
    """Yield YANG tokens: quoted strings, '{', '}', ';', bare words.

    Comments are skipped here rather than pre-stripped so that '//' inside
    quoted strings (e.g. namespace URLs) is preserved.
    """
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
        elif text.startswith("//", i):
            i = text.find("\n", i)
            i = n if i == -1 else i + 1
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end == -1 else end + 2
        elif c in "{};":
            yield c
            i += 1
        elif c in "\"'":
            quote = c
            i += 1
            buf = []
            while i < n:
                if text[i] == "\\" and quote == '"':
                    buf.append(text[i:i + 2])
                    i += 2
                elif text[i] == quote:
                    i += 1
                    break
                else:
                    buf.append(text[i])
                    i += 1
            yield ("STR", "".join(buf))
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in "{};\"'":
                j += 1
            yield text[i:j]
            i = j


def _parse(tokens) -> Node:
    """Parse YANG statements into a tree. Grammar: kw [arg] (';' | '{' stmt* '}')."""
    root = Node("__root__", "")
    stack = [root]
    keyword, arg_parts = None, []
    for tok in tokens:
        if tok == ";":
            if keyword:
                stack[-1].children.append(Node(keyword, " ".join(arg_parts)))
            keyword, arg_parts = None, []
        elif tok == "{":
            node = Node(keyword or "", " ".join(arg_parts))
            stack[-1].children.append(node)
            stack.append(node)
            keyword, arg_parts = None, []
        elif tok == "}":
            if len(stack) > 1:
                stack.pop()
            keyword, arg_parts = None, []
        else:
            value = tok[1] if isinstance(tok, tuple) else tok
            if tok == "+":
                continue  # string concatenation: just join parts
            if keyword is None:
                keyword = value
            else:
                arg_parts.append(value)
    return root


def _clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _leaf_entry(leaf: Node) -> dict:
    entry = {}
    type_node = leaf.first("type")
    if type_node:
        entry["type"] = type_node.arg
        if type_node.arg == "leafref":
            path = type_node.first("path")
            if path:
                entry["leafref_path"] = _clean_text(path.arg)
        elif type_node.arg == "enumeration":
            entry["enum_values"] = [e.arg for e in type_node.find("enum")]
    desc = leaf.first("description")
    if desc:
        entry["description"] = _clean_text(desc.arg)
    if leaf.first("mandatory") and leaf.first("mandatory").arg == "true":
        entry["mandatory"] = True
    default = leaf.first("default")
    if default:
        entry["default"] = default.arg
    if leaf.keyword == "leaf-list":
        entry["is_list"] = True
    return entry


def _extract_fields(node: Node) -> dict:
    """Collect leaf/leaf-list fields from a list or container node (recursing
    into choice/case wrappers)."""
    fields = {}
    for child in node.children:
        if child.keyword in ("leaf", "leaf-list"):
            fields[child.arg] = _leaf_entry(child)
        elif child.keyword in ("choice", "case"):
            fields.update(_extract_fields(child))
    return fields


def extract_tables(yang_path: Path) -> dict:
    """Extract CONFIG_DB tables from one sonic-*.yang module."""
    root = _parse(_tokenize(yang_path.read_text()))
    module = root.first("module")
    if not module:
        return {}

    tables = {}
    top_containers = module.find("container")
    for top in top_containers:
        for table_node in top.find("container"):
            table = table_node.arg
            if not table or table != table.upper():
                continue  # CONFIG_DB tables are ALL_CAPS containers
            entry = {"yang_module": module.arg, "yang_file": yang_path.name}
            desc = table_node.first("description")
            if desc:
                entry["description"] = _clean_text(desc.arg)

            keys, fields = [], {}
            lists = table_node.find("list")
            if lists:
                for lst in lists:
                    key_node = lst.first("key")
                    if key_node:
                        keys.extend(k for k in key_node.arg.split() if k not in keys)
                    fields.update(_extract_fields(lst))
            else:
                # keyless singleton tables (e.g. global config containers)
                fields.update(_extract_fields(table_node))
                for sub in table_node.find("container"):
                    fields.update({f"{sub.arg}.{k}": v
                                   for k, v in _extract_fields(sub).items()})
            entry["keys"] = keys
            entry["fields"] = fields
            tables[table] = entry
    return tables


def main():
    if not YANG_DIR.exists():
        print(f"ERROR: {YANG_DIR} not found. Run scripts/build/01_clone_repos.sh first.")
        sys.exit(1)

    all_tables = {}
    files = sorted(YANG_DIR.glob("sonic-*.yang"))
    print(f"Parsing {len(files)} YANG models from {YANG_DIR.relative_to(ROOT)}...")
    for path in files:
        try:
            tables = extract_tables(path)
        except Exception as e:  # tolerate odd grammar; report and continue
            print(f"  WARN: failed to parse {path.name}: {e}")
            continue
        for name, entry in tables.items():
            if name in all_tables:
                # same table augmented across modules: merge fields
                all_tables[name]["fields"].update(entry["fields"])
            else:
                all_tables[name] = entry

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(all_tables, f, indent=2, sort_keys=True)

    total_fields = sum(len(t["fields"]) for t in all_tables.values())
    print(f"Extracted {len(all_tables)} tables, {total_fields} fields")
    print(f"Wrote {OUT_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
