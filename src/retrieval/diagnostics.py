"""Diagnostic decision tree retrieval for sonic-kb."""

from __future__ import annotations

from ._loader import load_diagnostic_index, load_diagnostic_tree


def get_diagnostic_tree(symptom: str, node_id: str | None = None) -> dict | None:
    """Load a diagnostic tree by symptom keyword or tree_id, optionally returning a single node."""
    tree = load_diagnostic_tree(symptom)
    if tree is None:
        index = load_diagnostic_index()
        symptom_lower = symptom.lower()
        for tid, meta in index.items():
            if symptom_lower in meta.get("entry_symptom", "").lower():
                tree = load_diagnostic_tree(tid)
                break
            if symptom_lower in meta.get("display_name", "").lower():
                tree = load_diagnostic_tree(tid)
                break

    if tree is None:
        return None

    if node_id:
        for node in tree.get("nodes", []):
            if node.get("node_id") == node_id:
                return {"tree_id": tree.get("tree_id"), "node": node}
        return None

    return tree


def list_diagnostic_trees() -> list[dict]:
    index = load_diagnostic_index()
    return [{"tree_id": tid, **meta} for tid, meta in index.items()]
