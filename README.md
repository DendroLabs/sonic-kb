# sonic-kb -- SONiC Troubleshooting Knowledge Base

Pre-compiled troubleshooting knowledge base for SONiC 202511, served as an MCP server for Claude Code.

20 tools covering protocols, subsystems, config flows, diagnostics, log decoding, human-error detection, operational procedures, and semantic search.

## Quick Start

```bash
git clone https://github.com/DendroLabs/sonic-kb.git
cd sonic-kb
./install.sh
```

The install script:
1. Creates a virtualenv and installs dependencies
2. Validates the KB
3. Auto-detects Claude Code and/or OpenCode and configures the MCP server for whichever is installed

If neither tool is found, it prints manual config snippets for both.

## Manual Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[mcp]'
```

Then configure your tool manually:

**Claude Code** -- add to `~/.claude/.mcp.json`:
```json
{
  "mcpServers": {
    "sonic-kb": {
      "command": "python3",
      "args": ["run_mcp.py"],
      "cwd": "/path/to/sonic-kb"
    }
  }
}
```

**OpenCode** -- add to `~/.config/opencode/opencode.json`:
```json
{
  "mcp": {
    "sonic-kb": {
      "type": "local",
      "command": ["/path/to/sonic-kb/.venv/bin/python3", "/path/to/sonic-kb/run_mcp.py"]
    }
  }
}
```

## Usage

Once configured, the 20 tools are available automatically. Ask things like:

- "Why is my BGP session stuck in ACTIVE?"
- "What happens when I edit config_db.json directly?"
- "Trace the config flow for a route install"
- "What does this orchagent log message mean?"

To run standalone (JSON-RPC over stdio):

```bash
python3 run_mcp.py
```

## Tools

| Category | Tools |
|----------|-------|
| Protocols | get_protocol, get_protocol_state, get_protocol_failures, get_protocol_timers, get_protocol_messages, get_related_protocols, search_protocols_by_tag, get_verify_commands |
| Subsystems | get_config_db_table, get_daemon_info, trace_config_flow, list_containers |
| Diagnostics | get_log_message, detect_human_error, get_diagnostic_tree |
| Operations | get_procedure, get_best_practices, get_grounding_rules, search_source_ref |
| Search | search_kb (semantic similarity search across all content types) |

## Extending the KB

1. Add/edit JSON files under `knowledge-base/`
2. Rebuild indexes: `python3 scripts/build/05_build_indexes.py`
3. Rebuild vector index: `python3 scripts/build/06_build_vector_index.py`
   (requires `pip install -e '.[vector]'`)
4. Validate: `python3 scripts/build/20_validate_kb.py`
5. Run the integration tests: `python3 -m pytest tests/ -q` (43 tests
   covering all 20 tools; no clones or artifacts required)
6. (Recommended) Verify source references against real SONiC source:
   `scripts/build/01_clone_repos.sh` once to clone the 202511 repos into
   `build/repos/`, then `python3 scripts/build/21_verify_source_refs.py`

Note: `search_source_ref` serves a 56-entry annotated index from the committed
KB; when `build/artifacts/source_functions.json` exists locally (extraction
step above), it transparently adds an 18,965-entry tier-2 fallback. Without
the artifact it silently degrades to the annotated index.

`scripts/build/02_extract_db_schemas.py`, `03_extract_log_messages.py`, and
`04_extract_source_refs.py` extract CONFIG_DB schemas, log message templates,
and function locations from the cloned source into `build/artifacts/` for use
when authoring new content.

## Verification Council

Mechanical checks (steps 2-5 above) catch structural and path-shaped errors;
semantic errors (wrong behavior claims, invented fields, wrong ordering) are
caught by the verification council -- a multi-agent review that re-derives
each claim *blind* (reviewers never see the candidate content, only derivation
goals) from independent evidence sources: the source clones, the extracted
CONFIG_DB schemas, protocol specs, and pure logic. A single fault-finder scores
findings with evidence-gated severity. New KB content passes the council before
commit; every finding is logged to `review/council-log.jsonl` (schema and
details in `review/README.md`, trends via
`python3 scripts/council/aggregate_log.py`).

The council runs as a Claude Code workflow
(`scripts/council/sonic-council.workflow.js`) and is not required to *use*
the KB -- only to contribute content.

## Requirements

- Python 3.11+
- No external services required -- everything is local JSON
