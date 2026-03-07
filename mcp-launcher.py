#!/usr/bin/env python
"""Cross-platform MCP server launcher for anymate-cc.

This script finds the correct Python interpreter and launches anymate.server,
ensuring compatibility across Windows, Linux, macOS, and Termux.
"""
import sys
import os
from pathlib import Path

# Add src directory to Python path if not already installed
project_root = Path(__file__).parent
src_dir = project_root / "src"
if src_dir.exists() and str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

# Launch the MCP server
if __name__ == "__main__":
    from anymate.server import main
    main()
