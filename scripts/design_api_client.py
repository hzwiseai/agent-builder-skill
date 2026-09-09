#!/usr/bin/env python3
"""Read-only diagnostic client for the underlying WiseCopilot service API.

Use this only for investigation where direct API evidence is useful. All asset,
publication, Agent, and resource mutations must go through Design MCP's
prepare/commit confirmation protocol.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from _integrity import enforce


SKILL_ROOT = Path(__file__).resolve().parents[1]


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() and key.strip() not in os.environ:
            os.environ[key.strip()] = value.strip().strip('"').strip("'")


def request_json(base_url: str, path: str, *, token: str | None = None, method: str = "GET", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    body = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")
    req = Request(f"{base_url.rstrip('/')}{path}", data=body, headers=headers, method=method)
    try:
        with urlopen(req, timeout=30) as response:  # nosec B310: URL is operator-provided trusted service config
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"API returned HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"API request failed: {exc.reason}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("API returned a non-object JSON response")
    return data


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: "***" if key.lower() in {"access_token", "password", "token", "authorization"} else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def main() -> int:
    enforce()
    parser = argparse.ArgumentParser(description="Run a read-only WiseCopilot service API query.")
    parser.add_argument("--operation", required=True, choices=["platform-contract", "assets", "agents", "package-preview", "asset"])
    parser.add_argument("--package-key")
    parser.add_argument("--record-id", type=int)
    args = parser.parse_args()
    try:
        load_env(SKILL_ROOT / ".env")
        base_url = os.environ.get("WISECOPILOT_API_BASE_URL", "").strip()
        username = os.environ.get("WISECOPILOT_USERNAME", "").strip()
        password = os.environ.get("WISECOPILOT_PASSWORD", "")
        if not base_url or not username or not password:
            raise ValueError("WISECOPILOT_API_BASE_URL, WISECOPILOT_USERNAME and WISECOPILOT_PASSWORD are required in wisecopilot/.env")
        login = request_json(base_url, "/api/auth/login", method="POST", payload={"username": username, "password": password})
        token = str((login.get("data") or {}).get("access_token") or login.get("access_token") or "")
        if not token:
            raise RuntimeError("Login response did not contain an access token")
        paths = {
            "platform-contract": "/api/agents/v2/assets/platform-contracts",
            "assets": "/api/agents/v2/assets/drafts",
            "agents": "/api/agents/v2/agent-instances",
        }
        if args.operation == "package-preview":
            if not args.package_key:
                raise ValueError("--package-key is required for package-preview")
            path = f"/api/agents/v2/business-packages/{args.package_key}/draft-release-preview"
        elif args.operation == "asset":
            if args.record_id is None:
                raise ValueError("--record-id is required for asset")
            path = f"/api/agents/v2/assets/drafts/{args.record_id}"
        else:
            path = paths[args.operation]
        print(json.dumps(redact(request_json(base_url, path, token=token)), ensure_ascii=False, indent=2))
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
