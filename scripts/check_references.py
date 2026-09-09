#!/usr/bin/env python3
"""Fail when the skill's prose names a Design MCP tool the service does not have.

An invented tool name in a reference file is worse than a missing one: the
routing rules send a designer straight to that file, and the name reads as
authoritative.  This compares every ``design_*`` identifier in the shipped
Markdown against the live tool catalog.

Error codes and glob patterns share the ``design_`` prefix but are not tool
names, so the check drops them heuristically: a service code carries an outcome
word such as ``_invalid``, ``_missing`` or ``_requires_``, which no tool name
does. The heuristic is tuned to stay noisy rather than silent — a real invented
name like ``design_validate_bundle`` carries no outcome word and is still
caught.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import re
import sys

from _integrity import SKILL_ROOT
from design_mcp_client import _invoke

# Prose prefixes for a family of tools, this skill's own script names, and the
# outcome words that mark a service result code rather than a callable tool.
_OUTCOME_WORDS = (
    "failed", "stale", "invalid", "expired", "missing", "denied", "empty", "editable",
    "supported", "found", "enabled", "requires", "not",
)
NOT_TOOL_NAMES = re.compile(
    r"^design_(prepare|commit)_?$|^design_(mcp|api|asset)_|(^|_)(" + "|".join(_OUTCOME_WORDS) + r")(_|$)"
)
DOCUMENTED = re.compile(r"`(design_[a-z0-9_]+)`")


def documented_tool_names() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for pattern in ("SKILL.md", "references/*.md", "workspace/README.md"):
        for doc in sorted(SKILL_ROOT.glob(pattern)):
            names = {
                name for name in DOCUMENTED.findall(doc.read_text(encoding="utf-8"))
                if not NOT_TOOL_NAMES.search(name)
            }
            if names:
                found[str(doc.relative_to(SKILL_ROOT))] = names
    return found


def main() -> int:
    catalog = asyncio.run(_invoke("", {}, list_tools=True))
    deployed = {tool["name"] for tool in catalog.get("tools", [])}
    if not deployed:
        print(json.dumps({"status": "error", "message": "the service returned no tool catalog"}, ensure_ascii=False), file=sys.stderr)
        return 1
    unknown = {
        document: sorted(names - deployed)
        for document, names in documented_tool_names().items()
        if names - deployed
    }
    if unknown:
        print(json.dumps({"status": "unknown_tool_names", "deployed_count": len(deployed), "unknown": unknown}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1
    print(json.dumps({"status": "ok", "deployed_count": len(deployed)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
