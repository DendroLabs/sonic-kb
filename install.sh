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

echo "[1/3] Creating virtual environment..."
python3 -m venv "$REPO_DIR/.venv"
source "$REPO_DIR/.venv/bin/activate"

echo "[2/3] Installing dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -e "$REPO_DIR[mcp]"

echo "[3/3] Validating knowledge base..."
python3 "$REPO_DIR/scripts/build/20_validate_kb.py" || {
    echo "WARNING: KB validation reported issues (non-fatal)"
}

echo ""
echo "=== Install complete ==="
echo ""
echo "To use with Claude Code, add this to your project's .mcp.json:"
echo ""
echo "  {"
echo "    \"mcpServers\": {"
echo "      \"sonic-kb\": {"
echo "        \"command\": \"python3\","
echo "        \"args\": [\"run_mcp.py\"],"
echo "        \"cwd\": \"$REPO_DIR\""
echo "      }"
echo "    }"
echo "  }"
echo ""
echo "Or run manually:  cd $REPO_DIR && python3 run_mcp.py"
