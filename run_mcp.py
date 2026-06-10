"""MCP server launcher -- finds its own venv, resolves all paths."""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENV_PYTHON = HERE / ".venv" / "bin" / "python"

if VENV_PYTHON.exists():
    venv_site = HERE / ".venv" / "lib"
    if not any(str(p).startswith(str(venv_site)) for p in map(Path, sys.path)):
        os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), str(HERE / "run_mcp.py")])

sys.path.insert(0, str(HERE))

import asyncio
from src.mcp_server import main

asyncio.run(main())
