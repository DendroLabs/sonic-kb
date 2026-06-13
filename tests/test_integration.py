"""Integration tests for the sonic-kb tool layer.

Exercises execute_tool() end-to-end against the real knowledge-base/ content:
every tool gets at least one happy-path call, plus tests for miss handling,
argument validation, serialization shape (kb_coverage), and the two-tier
search_source_ref backend.
"""

import json

import pytest

from src.agent._tools import TOOL_DEFINITIONS, _serialize, execute_tool
from src.retrieval._loader import load_source_functions_artifact, load_vector_index


def call(name: str, arguments: dict | None = None) -> dict:
    """Run a tool and return its parsed JSON content, asserting no error."""
    result = execute_tool(name, arguments or {})
    data = json.loads(result.content)
    assert not result.is_error, f"{name} errored: {data}"
    assert "error" not in data, f"{name} returned error payload: {data}"
    return data


# --- Happy path: every tool returns valid, found, kb_coverage-stamped JSON ---

HAPPY_PATH_CALLS = [
    ("get_protocol", {"protocol_id": "bgp-4"}),
    ("get_protocol_state", {"protocol_id": "bgp-4", "state": "ESTABLISHED"}),
    ("get_protocol_failures", {"protocol_id": "bgp-4"}),
    ("get_protocol_timers", {"protocol_id": "bgp-4"}),
    ("get_protocol_messages", {"protocol_id": "bgp-4"}),
    ("get_related_protocols", {"protocol_id": "bgp-4"}),
    ("search_protocols_by_tag", {"tag": "routing"}),
    ("get_verify_commands", {"protocol_id": "bgp-4"}),
    ("get_config_db_table", {"table_name": "BGP_NEIGHBOR"}),
    ("get_daemon_info", {"daemon_name": "orchagent"}),
    ("trace_config_flow", {"entity_type": "route"}),
    ("list_containers", {}),
    ("get_log_message", {"pattern": "FPM"}),
    ("detect_human_error", {"description": "edited frr.conf directly inside the bgp container"}),
    ("get_diagnostic_tree", {"symptom": "bgp-not-establishing"}),
    ("get_procedure", {"procedure_id": "config-reload"}),
    ("get_best_practices", {}),
    ("get_grounding_rules", {}),
    ("search_source_ref", {"query": "doTask"}),
]

_has_vector_deps = load_vector_index() is not None
try:
    import sentence_transformers  # noqa: F401
    _has_st = True
except ImportError:
    _has_st = False
_can_search_kb = _has_vector_deps and _has_st


@pytest.mark.parametrize("name,args", HAPPY_PATH_CALLS, ids=[c[0] for c in HAPPY_PATH_CALLS])
def test_tool_happy_path(name, args):
    data = call(name, args)
    assert data.get("kb_coverage") == "indexed"
    assert data.get("found") is not False


@pytest.mark.skipif(not _can_search_kb, reason="vector index or sentence-transformers not available")
def test_search_kb_happy_path():
    """search_kb tested separately because it requires optional [vector] deps."""
    data = call("search_kb", {"query": "BGP session not establishing"})
    assert data.get("kb_coverage") == "indexed"
    assert data["count"] >= 1


def test_all_tools_covered():
    """Every defined tool has a happy-path test above or a dedicated happy-path test."""
    defined = {t.name for t in TOOL_DEFINITIONS}
    tested = {name for name, _ in HAPPY_PATH_CALLS}
    tested.add("search_kb")
    assert defined == tested


# --- Content spot checks ---

def test_get_protocol_resolves_def_refs():
    data = call("get_protocol", {"protocol_id": "bgp-4"})
    assert data["protocol_id"] == "bgp-4"
    assert data["states"], "expected resolved states"
    # def_refs must be inlined by the resolver, not leak through as bare IDs
    assert "def_refs" not in json.dumps(data["states"])


def test_get_daemon_info_fdbsyncd():
    """fdbsyncd was added in Phase 4 — regression-guard its presence."""
    data = call("get_daemon_info", {"daemon_name": "fdbsyncd"})
    assert data.get("found") is not False
    text = json.dumps(data)
    assert "swss" in text and "EVPN" in text


def test_trace_config_flow_route_steps_ordered():
    data = call("trace_config_flow", {"entity_type": "route"})
    steps = data.get("steps", [])
    assert steps, "route code path should have steps"
    numbers = [s["step"] for s in steps if "step" in s]
    assert numbers == sorted(numbers)


def test_list_containers_includes_core():
    data = call("list_containers", {})
    text = json.dumps(data)
    for container in ("swss", "syncd", "bgp", "database"):
        assert container in text


def test_get_log_message_fpm():
    data = call("get_log_message", {"pattern": "FPM", "daemon": "fpmsyncd"})
    assert "fpm" in json.dumps(data).lower()


# --- Miss handling ---

def test_miss_returns_not_indexed():
    result = execute_tool("get_protocol", {"protocol_id": "no-such-protocol"})
    data = json.loads(result.content)
    assert data["found"] is False
    assert data["kb_coverage"] == "not_indexed"
    assert "coverage_note" in data


def test_config_db_table_miss():
    result = execute_tool("get_config_db_table", {"table_name": "NO_SUCH_TABLE_XYZ"})
    data = json.loads(result.content)
    assert data["found"] is False
    assert data["kb_coverage"] == "not_indexed"


# --- Argument validation and dispatch errors ---

def test_unknown_tool_errors():
    result = execute_tool("no_such_tool", {})
    assert result.is_error
    assert "Unknown tool" in json.loads(result.content)["error"]

def test_missing_required_argument_errors():
    result = execute_tool("get_protocol", {})
    assert result.is_error
    assert "protocol_id" in json.loads(result.content)["error"]


# --- Serialization shape ---

def test_serialize_none():
    data = json.loads(_serialize(None))
    assert data == {
        "found": False,
        "kb_coverage": "not_indexed",
        "coverage_note": "No matching data in the SONiC KB for this query.",
    }


def test_serialize_dict_stamps_coverage():
    data = json.loads(_serialize({"a": 1}))
    assert data == {"a": 1, "kb_coverage": "indexed"}


def test_serialize_dict_preserves_existing_coverage():
    data = json.loads(_serialize({"a": 1, "kb_coverage": "partial"}))
    assert data["kb_coverage"] == "partial"


def test_serialize_list_wraps_with_count():
    data = json.loads(_serialize([{"x": 1}, {"y": 2}]))
    assert data["count"] == 2
    assert data["results"] == [{"x": 1}, {"y": 2}]
    assert data["kb_coverage"] == "indexed"


def test_serialize_scalar():
    data = json.loads(_serialize(42))
    assert data == {"result": "42", "kb_coverage": "indexed"}


# --- Tiered search_source_ref ---

def test_search_source_ref_annotated_tier():
    data = call("search_source_ref", {"query": "doTask"})
    sources = {r["source"] for r in data["results"]}
    assert "annotated" in sources


def test_search_source_ref_no_duplicate_functions():
    data = call("search_source_ref", {"query": "doTask"})
    artifact_funcs = [r["source_function"] for r in data["results"] if r["source"] == "artifact"]
    annotated_funcs = {r.get("source_function") for r in data["results"] if r["source"] == "annotated"}
    assert not annotated_funcs & set(artifact_funcs), "artifact tier must not repeat annotated functions"


@pytest.mark.skipif(
    load_source_functions_artifact() is None,
    reason="build/artifacts/source_functions.json not present (run scripts/build/01-04)",
)
def test_search_source_ref_artifact_tier():
    data = call("search_source_ref", {"query": "fdbsync"})
    sources = {r["source"] for r in data["results"]}
    assert "artifact" in sources
    for r in data["results"]:
        if r["source"] == "artifact":
            assert ":" in r["source_file"], "artifact refs are repo:file"
            assert r["line"] >= 0


def test_search_source_ref_no_match_is_empty():
    data = call("search_source_ref", {"query": "zzz_no_such_symbol_zzz"})
    assert data["count"] == 0
    assert data["results"] == []


# --- Semantic search (search_kb) ---

_skip_no_search = pytest.mark.skipif(
    not _can_search_kb, reason="vector index or sentence-transformers not available"
)


@_skip_no_search
def test_search_kb_returns_ranked_results():
    data = call("search_kb", {"query": "BGP neighbor keeps going down"})
    results = data["results"]
    assert len(results) >= 1
    assert all("score" in r and "id" in r and "type" in r for r in results)
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True), "results must be ranked by score"


@_skip_no_search
def test_search_kb_content_type_filter():
    data = call("search_kb", {"query": "configuration change", "content_type": "human-error"})
    results = data["results"]
    assert all(r["type"] == "human-error" for r in results)


@_skip_no_search
def test_search_kb_top_k():
    data = call("search_kb", {"query": "VLAN", "top_k": 3})
    assert len(data["results"]) <= 3


@_skip_no_search
def test_search_kb_bgp_query_finds_protocol():
    data = call("search_kb", {"query": "BGP routing protocol session establishment"})
    types = {r["type"] for r in data["results"]}
    ids = {r["id"] for r in data["results"]}
    assert "protocol" in types or any("bgp" in i for i in ids)
