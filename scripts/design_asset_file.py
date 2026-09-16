#!/usr/bin/env python3
"""Edit one V2 platform asset as a local file: pull, edit, push.

``--pull`` writes ``{"asset": {...identity...}, "document": {...}}`` so any
editor or agent can change the document offline.  ``--push`` sends that file
back through the same MCP prepare/commit confirmation the browser uses, and
carries the ``content_hash`` captured at pull time so a draft that someone else
changed in the meantime is refused instead of silently overwritten.

Pushing stops at the prepared diff by default. Nothing is written until the
user has read that diff and the caller repeats the push with ``--confirm``.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

from _integrity import enforce
from design_mcp_client import SKILL_ROOT, call_tool  # noqa: F401


def _fail(message: str, **extra: Any) -> int:
    print(json.dumps({"status": "error", "message": message, **extra}, ensure_ascii=False), file=sys.stderr)
    return 1


async def pull(record_id: int, path: Path, draft_key: str) -> int:
    result = await call_tool("design_get_asset", {"record_id": int(record_id), "draft_key": draft_key})
    if not result.get("ok"):
        return _fail("design_get_asset failed", result=result)
    asset = result.get("data") or {}
    document = asset.get("document")
    if not isinstance(document, dict) or not document:
        return _fail("asset has no editable document", record_id=int(record_id))
    payload = {
        "asset": {
            "record_id": int(asset.get("record_id") or record_id),
            "asset_kind": asset.get("asset_kind"),
            "asset_key": asset.get("asset_key"),
            "draft_key": asset.get("draft_key") or draft_key,
            "content_hash": asset.get("content_hash"),
            "pulled_status": asset.get("status"),
        },
        "document": document,
        "sync": {
            "baseline_content_hash": asset.get("content_hash"),
            "pulled_at": datetime.now(timezone.utc).isoformat(),
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "pulled", "file": str(path), **payload["asset"]}, ensure_ascii=False, indent=2))
    return 0


async def push(path: Path, confirm: bool) -> int:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _fail(f"cannot read {path}: {exc}")
    asset, document = payload.get("asset") or {}, payload.get("document")
    if not isinstance(document, dict) or not document:
        return _fail("file has no document object; pull it first")
    # A file round-trip is optimistic-locking by definition. Never allow a
    # missing baseline to become an unconditional whole-document overwrite.
    if not asset.get("content_hash"):
        return _fail("file has no content_hash baseline; pull the current asset again before editing")
    if not asset.get("asset_kind") or not asset.get("asset_key"):
        return _fail("file has no asset identity; pull the current asset again before editing")
    prepared = await call_tool("design_prepare_draft_save", {
        "document": document,
        "draft_key": asset.get("draft_key") or "main",
        "base_content_hash": asset.get("content_hash") or "",
    })
    if not prepared.get("ok"):
        return _fail("prepare refused the change", result=prepared)
    if not confirm:
        print(json.dumps({
            "status": "prepared",
            "confirmation_id": prepared.get("confirmation_id"),
            "asset_key": prepared.get("asset_key"),
            "changes": prepared.get("changes"),
            "next_step": "Show this diff to the user, then re-run with --confirm.",
        }, ensure_ascii=False, indent=2))
        return 0
    committed = await call_tool("design_commit_draft_save", {"confirmation_id": prepared["confirmation_id"]})
    if not committed.get("ok"):
        return _fail("commit refused the change", result=committed)
    # Refresh the saved document's hash immediately. The local envelope now
    # becomes the next round's baseline instead of remaining stale.
    record_id = asset.get("record_id")
    refreshed = await call_tool("design_get_asset", {"record_id": int(record_id), "draft_key": asset.get("draft_key") or "main"}) if record_id else {}
    refreshed_asset = refreshed.get("data") if isinstance(refreshed, dict) else None
    new_hash = refreshed_asset.get("content_hash") if isinstance(refreshed_asset, dict) else None
    if new_hash:
        payload["asset"]["content_hash"] = new_hash
        payload["asset"]["pulled_status"] = refreshed_asset.get("status")
        payload["sync"] = {
            "baseline_content_hash": new_hash,
            "previous_baseline_content_hash": asset.get("content_hash"),
            "synced_at": datetime.now(timezone.utc).isoformat(),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "saved", "asset_key": prepared.get("asset_key"),
                      "new_content_hash": new_hash, "local_baseline_refreshed": bool(new_hash)}, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    enforce()
    parser = argparse.ArgumentParser(description="Pull one V2 asset to a file, or push an edited file back.")
    parser.add_argument("--pull", type=int, metavar="RECORD_ID", help="Record id from design_list_assets.")
    parser.add_argument("--push", action="store_true", help="Send the edited file back through prepare/commit.")
    parser.add_argument("--file", required=True, type=Path, help="Local JSON file holding the pulled asset.")
    parser.add_argument("--draft-key", default="main")
    parser.add_argument("--confirm", action="store_true", help="Commit the prepared diff the user already reviewed.")
    args = parser.parse_args()
    if bool(args.pull) == bool(args.push):
        return _fail("choose exactly one of --pull RECORD_ID or --push")
    if args.pull:
        return asyncio.run(pull(args.pull, args.file, args.draft_key))
    return asyncio.run(push(args.file, args.confirm))


if __name__ == "__main__":
    raise SystemExit(main())
