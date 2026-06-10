#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== sonic-kb install ==="
echo "Location: $REPO_DIR"
echo ""

# Check Python version
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found. Install Python 3.11+ first."
    exit 1
fi

PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 11 ]; }; then
    echo "ERROR: Python 3.11+ required (found $PY_VERSION)"
    exit 1
fi

echo "[1/4] Creating virtual environment..."
python3 -m venv "$REPO_DIR/.venv"
source "$REPO_DIR/.venv/bin/activate"

echo "[2/4] Installing dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -e "$REPO_DIR[mcp]"

echo "[3/4] Validating knowledge base..."
python3 "$REPO_DIR/scripts/build/20_validate_kb.py" || {
    echo "WARNING: KB validation reported issues (non-fatal)"
}

# --- Auto-configure MCP for detected tools ---

HAS_CLAUDE=false
HAS_OPENCODE=false
CONFIGURED=""

if command -v claude &>/dev/null; then
    HAS_CLAUDE=true
fi

if command -v opencode &>/dev/null; then
    HAS_OPENCODE=true
fi

echo "[4/4] Configuring MCP server..."

if $HAS_CLAUDE; then
    CLAUDE_MCP_DIR="$HOME/.claude"
    CLAUDE_MCP_FILE="$CLAUDE_MCP_DIR/.mcp.json"
    mkdir -p "$CLAUDE_MCP_DIR"

    if [ -f "$CLAUDE_MCP_FILE" ]; then
        # Check if sonic-kb is already configured
        if python3 -c "import json,sys; d=json.load(open('$CLAUDE_MCP_FILE')); sys.exit(0 if 'sonic-kb' in d.get('mcpServers',{}) else 1)" 2>/dev/null; then
            echo "  Claude Code: sonic-kb already configured in $CLAUDE_MCP_FILE"
        else
            # Merge into existing file
            python3 -c "
import json
with open('$CLAUDE_MCP_FILE') as f:
    config = json.load(f)
config.setdefault('mcpServers', {})['sonic-kb'] = {
    'command': 'python3',
    'args': ['run_mcp.py'],
    'cwd': '$REPO_DIR'
}
with open('$CLAUDE_MCP_FILE', 'w') as f:
    json.dump(config, f, indent=2)
"
            echo "  Claude Code: added sonic-kb to $CLAUDE_MCP_FILE"
        fi
    else
        # Create new file
        python3 -c "
import json
config = {'mcpServers': {'sonic-kb': {
    'command': 'python3',
    'args': ['run_mcp.py'],
    'cwd': '$REPO_DIR'
}}}
with open('$CLAUDE_MCP_FILE', 'w') as f:
    json.dump(config, f, indent=2)
"
        echo "  Claude Code: created $CLAUDE_MCP_FILE"
    fi
    CONFIGURED="$CONFIGURED claude"
fi

if $HAS_OPENCODE; then
    OPENCODE_CFG="$HOME/.config/opencode/opencode.json"
    OPENCODE_DIR="$(dirname "$OPENCODE_CFG")"
    mkdir -p "$OPENCODE_DIR"

    if [ -f "$OPENCODE_CFG" ]; then
        if python3 -c "import json,sys; d=json.load(open('$OPENCODE_CFG')); sys.exit(0 if 'sonic-kb' in d.get('mcp',{}) else 1)" 2>/dev/null; then
            echo "  OpenCode: sonic-kb already configured in $OPENCODE_CFG"
        else
            python3 -c "
import json
with open('$OPENCODE_CFG') as f:
    config = json.load(f)
config.setdefault('mcp', {})['sonic-kb'] = {
    'type': 'local',
    'command': ['$REPO_DIR/.venv/bin/python3', '$REPO_DIR/run_mcp.py']
}
with open('$OPENCODE_CFG', 'w') as f:
    json.dump(config, f, indent=2)
"
            echo "  OpenCode: added sonic-kb to $OPENCODE_CFG"
        fi
    else
        python3 -c "
import json
config = {'mcp': {'sonic-kb': {
    'type': 'local',
    'command': ['$REPO_DIR/.venv/bin/python3', '$REPO_DIR/run_mcp.py']
}}}
with open('$OPENCODE_CFG', 'w') as f:
    json.dump(config, f, indent=2)
"
        echo "  OpenCode: created $OPENCODE_CFG"
    fi
    CONFIGURED="$CONFIGURED opencode"
fi

echo ""
echo "=== Install complete ==="

if [ -n "$CONFIGURED" ]; then
    echo ""
    echo "MCP server configured for:$CONFIGURED"
    echo "Restart your tool to pick up the new server."
else
    echo ""
    echo "Neither 'claude' nor 'opencode' found in PATH."
    echo ""
    echo "For Claude Code, add to ~/.claude/.mcp.json:"
    echo '  {"mcpServers":{"sonic-kb":{"command":"python3","args":["run_mcp.py"],"cwd":"'$REPO_DIR'"}}}'
    echo ""
    echo "For OpenCode, add to ~/.config/opencode/opencode.json:"
    echo '  {"mcp":{"sonic-kb":{"type":"local","command":["'$REPO_DIR'/.venv/bin/python3","'$REPO_DIR'/run_mcp.py"]}}}'
fi
