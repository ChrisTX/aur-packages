#!/bin/sh
# The MCP bridge of GhidraMCP. It runs with the MCP SDK 1.x the package keeps in its own folder, which
# comes first on the path, ahead of a python-mcp (2.x) installed for other programs.
PYTHONPATH="@SITE@${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONPATH
exec /usr/bin/python -m bridge_mcp_ghidra "$@"
