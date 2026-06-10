# sonic-kb -- SONiC Troubleshooting Knowledge Base

Pre-compiled troubleshooting knowledge base for SONiC 202511, served as an MCP server for Claude Code.

19 tools covering protocols, subsystems, config flows, diagnostics, log decoding, human-error detection, and operational procedures.

## Quick Start

```bash
git clone https://github.com/DendroLabs/sonic-kb.git
cd sonic-kb
./install.sh
```

The install script creates a virtualenv, installs dependencies, and validates the KB. At the end it prints the `.mcp.json` snippet to wire it into Claude Code.

## Manual Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[mcp]'
```

## Usage

### With Claude Code

Add to your project's `.mcp.json` (or `~/.claude/.mcp.json` for global access):

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

Then in Claude Code, the 19 tools are available automatically. Ask things like:

- "Why is my BGP session stuck in ACTIVE?"
- "What happens when I edit config_db.json directly?"
- "Trace the config flow for a route install"
- "What does this orchagent log message mean?"

### Standalone

```bash
python3 run_mcp.py
```

Speaks JSON-RPC over stdio (MCP protocol).

## Tools

| Category | Tools |
|----------|-------|
| Protocols | get_protocol, get_protocol_state, get_protocol_failures, get_protocol_timers, get_protocol_messages, get_related_protocols, search_protocols_by_tag, get_verify_commands |
| Subsystems | get_config_db_table, get_daemon_info, trace_config_flow, list_containers |
| Diagnostics | get_log_message, detect_human_error, get_diagnostic_tree |
| Operations | get_procedure, get_best_practices, get_grounding_rules, search_source_ref |

## Extending the KB

1. Add/edit JSON files under `knowledge-base/`
2. Rebuild indexes: `python3 scripts/build/05_build_indexes.py`
3. Validate: `python3 scripts/build/20_validate_kb.py`

## Requirements

- Python 3.11+
- No external services required -- everything is local JSON
