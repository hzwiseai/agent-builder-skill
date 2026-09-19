#!/usr/bin/env python3
"""Small, portable WiseCopilot MCP client.

It reads ``wisecopilot/.env``, authenticates with the Design MCP, then lists
or invokes a tool. Authentication prefers ``WISECOPILOT_API_KEY`` and falls back
to the username and password when no key is configured. Mutating operations still require the MCP's prepare/commit
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

    api_key = os.environ.get("WISECOPILOT_API_KEY", "").strip()
    username = os.environ.get("WISECOPILOT_USERNAME", "").strip()
    organization_id = os.environ.get("WISECOPILOT_ORG_ID", "").strip()
    # The key is hashed, never stored: two keys of the same user still map to
    # different accounts here, so swapping keys does not inherit a session.
    return hashlib.sha256(
        f"{api_key}\n{username}\n{organization_id}".encode("utf-8")
    ).hexdigest()


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


async def establish_session(
    session: ClientSession, *, api_key: str = "", username: str = "", password: str = "",
    organization_id: str = "",
) -> str:
    # Send one credential, not both: the server would accept the key and ignore
    # the password, and a caller reading the wire should not have to guess which
    # one actually opened the session.
    auth_args: dict[str, Any] = {"api_key": api_key} if api_key else {"username": username, "password": password}
    if organization_id:
        auth_args["organization_id"] = organization_id
    authenticated = tool_mapping(await session.call_tool("design_authenticate", auth_args))
    session_id = str(authenticated.get("session_id") or "")
    if not session_id:
        # The server distinguishes a revoked key from an expired one, from an
        # account that left the organization, from an organization that turned
        # external design access off. Dropping that here costs the user a
        # debugging session to rediscover what the response already said.
        code = str(authenticated.get("code") or "") or "design_authentication_failed"
        detail = str(authenticated.get("detail") or "").strip()
        raise RuntimeError(f"{code}: {detail}" if detail else code)
    store_session_id(session_id, int(authenticated.get("expires_in_seconds") or 0))
    return session_id


async def _invoke(
    tool_name: str, tool_args: dict[str, Any], *, list_tools: bool = False,
    session_id: str = "", new_session: bool = False,
) -> dict[str, Any]:
    load_env(SKILL_ROOT / ".env")
    mcp_url = os.environ.get("WISECOPILOT_MCP_URL", "").strip()
    api_key = os.environ.get("WISECOPILOT_API_KEY", "").strip()
    username = os.environ.get("WISECOPILOT_USERNAME", "").strip()
    password = os.environ.get("WISECOPILOT_PASSWORD", "")
    organization_id = os.environ.get("WISECOPILOT_ORG_ID", "").strip()
    if not mcp_url:
        raise ValueError("WISECOPILOT_MCP_URL is required in wisecopilot/.env")
    # A key is preferred over a password because the token it yields is limited
    # to the design surface; a password login is the fallback, not the default.
    has_credentials = bool(api_key or (username and password))
    credentials_error = (
        "Set WISECOPILOT_API_KEY, or WISECOPILOT_USERNAME and WISECOPILOT_PASSWORD, in wisecopilot/.env"
    )

    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            if list_tools:
                listing = await session.list_tools()
                return {"tools": [model_data(item) for item in listing.tools]}
            if not tool_name:
                raise ValueError("Provide --list-tools or --tool TOOL_NAME")
            if tool_name == "design_authenticate":
                if not tool_args.get("api_key") and not (tool_args.get("username") and tool_args.get("password")):
                    if api_key:
                        tool_args["api_key"] = api_key
                    else:
                        tool_args.setdefault("username", username)
                        tool_args.setdefault("password", password)
                if organization_id:
                    tool_args.setdefault("organization_id", organization_id)
                if not tool_args.get("api_key") and not (tool_args.get("username") and tool_args.get("password")):
                    raise ValueError(credentials_error)
                return tool_mapping(await session.call_tool(tool_name, tool_args))
            if "session_id" in tool_args:
                return tool_mapping(await session.call_tool(tool_name, tool_args))
            reused = "" if new_session else (session_id or cached_session_id())
            if not reused and not has_credentials:
                raise ValueError(credentials_error)
            tool_args["session_id"] = reused or await establish_session(
                session, api_key=api_key, username=username, password=password,
                organization_id=organization_id,
            )
            result = tool_mapping(await session.call_tool(tool_name, tool_args))
            if not reused or str(result.get("code") or "") != "design_session_invalid_or_expired":
                return result
            if not has_credentials:
                raise ValueError(credentials_error)
            tool_args["session_id"] = await establish_session(
                session, api_key=api_key, username=username, password=password,
                organization_id=organization_id,
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


def _readable_error(exc: BaseException) -> str:
    """Unwrap the anyio task group that the MCP client runs its stream inside.

    Its ``str`` is always "unhandled errors in a TaskGroup", which says nothing
    about why the call failed; the cause it wraps is the message worth printing.
    """

    seen: list[str] = []
    stack: list[BaseException] = [exc]
    while stack:
        current = stack.pop()
        nested = getattr(current, "exceptions", None)
        if nested:
            stack.extend(nested)
            continue
        message = str(current).strip()
        if message and message not in seen:
            seen.append(message)
    return "; ".join(seen) or exc.__class__.__name__


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
        print(json.dumps({"status": "error", "message": _readable_error(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
