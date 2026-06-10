"""Procedure retrieval for sonic-kb."""

from __future__ import annotations

from ._loader import load_procedure, load_procedure_index
from ._resolver import resolve_def_refs


def get_procedure(procedure_id: str, step_id: str | None = None) -> dict | None:
    data = load_procedure(procedure_id)
    if data is None:
        return None
    data = resolve_def_refs(data)
    if step_id:
        for step in data.get("steps", []):
            if step.get("step_id") == step_id:
                return {"procedure_id": procedure_id, "step": step}
        return None
    return data


def list_procedures() -> list[dict]:
    index = load_procedure_index()
    return [{"procedure_id": pid, **meta} for pid, meta in index.items()]
