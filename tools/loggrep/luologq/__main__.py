#!/usr/bin/env python3
"""luologq - Enhanced qlog CLI."""
import sys
sys.path.insert(0, '/home/workspace/linix-tool/tools/loggrep')
from luologq.cli import main
sys.exit(main() or 0)
