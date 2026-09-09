#!/usr/bin/env python3
"""Small, portable WiseCopilot MCP client.

It reads ``wisecopilot/.env``, authenticates with the Design MCP, then lists
or invokes a tool. Mutating operations still require the MCP's prepare/commit
confirmation token; this client deliberately cannot bypass that protocol.

A confirmation token is bound to the Design session that issued it, so the
client caches its session id in ``wisecopilot/.session.json`` and reuses it.
Without that cache every invocation would open a new session and no
``design_commit_*`` call could ever redeem a token from a previous command.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import time
import sys
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from _integrity import enforce


SKILL_ROOT = Path(__file__).resolve().parents[1]
SESSION_CACHE = SKILL_ROOT / ".session.json"
# Re-authenticate before the server-side TTL edge rather than on an expiry error.
SESSION_SAFETY_MARGIN_SECONDS = 60


def load_env(path: Path) -> None:
    """Load simple KEY=VALUE pairs without replacing explicit shell values."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def model_data(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "dict"):
        return value.dict()
    return value


def tool_mapping(result: Any) -> dict[str, Any]:
    payload = model_data(result)
    if not isinstance(payload, dict):
        return {}
    structured = payload.get("structuredContent") or payload.get("structured_content")
    if isinstance(structured, dict):
        return structured
    for block in payload.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "text":
            try:
                parsed = json.loads(str(block.get("text") or ""))
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
    return payload


def _account_fingerprint() -> str:
    """Identify the configured account without storing anything about it.

    A Design session is scoped to one account and one organization. Keying the
    cache on the endpoint alone would let a session survive an ``.env`` switch
    to a different account, so a later command would silently act in the
    previous organization.
    """

    username = os.environ.get("WISECOPILOT_USERNAME", "").strip()
    organization_id = os.environ.get("WISECOPILOT_ORG_ID", "").strip()
    return hashlib.sha256(f"{username}\n{organization_id}".encode("utf-8")).hexdigest()


def cached_session_id() -> str:
    """Return a cached Design session id while it is still comfortably valid."""

    try:
        cached = json.loads(SESSION_CACHE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(cached, dict):
        return ""
    if str(cached.get("mcp_url") or "") != os.environ.get("WISECOPILOT_MCP_URL", "").strip():
        return ""
    if str(cached.get("account") or "") != _account_fingerprint():
        return ""
    if float(cached.get("expires_at") or 0) - SESSION_SAFETY_MARGIN_SECONDS <= time.time():
        return ""
    return str(cached.get("session_id") or "")


def store_session_id(session_id: str, expires_in_seconds: int) -> None:
    """Cache only the session handle; credentials never reach this file."""

    try:
        SESSION_CACHE.write_text(json.dumps({
            "session_id": session_id,
            "expires_at": time.time() + max(0, int(expires_in_seconds)),
            "mcp_url": os.environ.get("WISECOPILOT_MCP_URL", "").strip(),
            "account": _account_fingerprint(),
        }), encoding="utf-8")
        SESSION_CACHE.chmod(0o600)
    except OSError:
        pass


async def establish_session(session: ClientSession, *, username: str, password: str, organization_id: str) -> str:
    auth_args: dict[str, Any] = {"username": username, "password": password}
    if organization_id:
        auth_args["organization_id"] = organization_id
    authenticated = tool_mapping(await session.call_tool("design_authenticate", auth_args))
    session_id = str(authenticated.get("session_id") or "")
    if not session_id:
        raise RuntimeError("Design MCP authentication did not return session_id")
    store_session_id(session_id, int(authenticated.get("expires_in_seconds") or 0))
    return session_id


async def _invoke(
    tool_name: str, tool_args: dict[str, Any], *, list_tools: bool = False,
    session_id: str = "", new_session: bool = False,
) -> dict[str, Any]:
    load_env(SKILL_ROOT / ".env")
    mcp_url = os.environ.get("WISECOPILOT_MCP_URL", "").strip()
    username = os.environ.get("WISECOPILOT_USERNAME", "").strip()
    password = os.environ.get("WISECOPILOT_PASSWORD", "")
    organization_id = os.environ.get("WISECOPILOT_ORG_ID", "").strip()
    if not mcp_url:
        raise ValueError("WISECOPILOT_MCP_URL is required in wisecopilot/.env")

    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            if list_tools:
                listing = await session.list_tools()
                return {"tools": [model_data(item) for item in listing.tools]}
            if not tool_name:
                raise ValueError("Provide --list-tools or --tool TOOL_NAME")
            if tool_name == "design_authenticate":
                tool_args.setdefault("username", username)
                tool_args.setdefault("password", password)
                if organization_id:
                    tool_args.setdefault("organization_id", organization_id)
                if not tool_args.get("username") or not tool_args.get("password"):
                    raise ValueError("WISECOPILOT_USERNAME and WISECOPILOT_PASSWORD are required")
                return tool_mapping(await session.call_tool(tool_name, tool_args))
            if "session_id" in tool_args:
                return tool_mapping(await session.call_tool(tool_name, tool_args))
            reused = "" if new_session else (session_id or cached_session_id())
            if not reused and not (username and password):
                raise ValueError("WISECOPILOT_USERNAME and WISECOPILOT_PASSWORD are required for authenticated tools")
            tool_args["session_id"] = reused or await establish_session(
                session, username=username, password=password, organization_id=organization_id,
            )
            result = tool_mapping(await session.call_tool(tool_name, tool_args))
            if not reused or str(result.get("code") or "") != "design_session_invalid_or_expired":
                return result
            if not (username and password):
                raise ValueError("WISECOPILOT_USERNAME and WISECOPILOT_PASSWORD are required for authenticated tools")
            tool_args["session_id"] = await establish_session(
                session, username=username, password=password, organization_id=organization_id,
            )
            return tool_mapping(await session.call_tool(tool_name, tool_args))


async def call_tool(tool_name: str, tool_args: dict[str, Any] | None = None) -> dict[str, Any]:
    """Call one Design MCP tool on the cached session. Used by sibling scripts."""

    return await _invoke(tool_name, dict(tool_args or {}))


async def run(args: argparse.Namespace) -> dict[str, Any]:
    tool_args = json.loads(args.args_json or "{}")
    if not isinstance(tool_args, dict):
        raise ValueError("--args-json must be a JSON object")
    return await _invoke(
        args.tool or "", tool_args, list_tools=bool(args.list_tools),
        session_id=args.session_id, new_session=bool(args.new_session),
    )


def main() -> int:
    enforce()
    parser = argparse.ArgumentParser(description="Call the WiseCopilot Design MCP using wisecopilot/.env.")
    parser.add_argument("--list-tools", action="store_true")
    parser.add_argument("--tool", help="MCP tool name, such as design_list_assets")
    parser.add_argument("--args-json", default="{}", help="JSON object passed to --tool; session_id is injected when needed.")
    parser.add_argument("--session-id", default="", help="Reuse this Design session id instead of the cached one.")
    parser.add_argument("--new-session", action="store_true", help="Force a fresh authentication and discard the cached session.")
    args = parser.parse_args()
    try:
        print(json.dumps(asyncio.run(run(args)), ensure_ascii=False, indent=2))
    except Exception as exc:  # CLI boundary: do not include local environment values.
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
