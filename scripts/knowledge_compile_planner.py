#!/usr/bin/env python3
"""Generate a knowledge-center-to-asset proposal without Builder Copilot.

The Design MCP remains the transport and safety gate: this script only reads
released knowledge and the current business package, then emits typed Harness
operations that can be reviewed, validated, and applied through MCP tools.
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Mapping
import hashlib
import json
import re
import sys
from typing import Any

from _integrity import enforce
from design_mcp_client import call_tool


KNOWN_POLICY_KEYS = {
    "社保": "example_shared_social_insurance",
    "试岗与劳动合同": "example_shared_probation_and_contract",
    "不承诺录用": "interview_no_hire_promise",
    "不承诺收入": "interview_no_income_promise",
    "不承诺人工回复时间": "interview_no_human_response_time_promise",
    "不收取任何费用": "interview_no_fees",
    "不做歧视性表述": "interview_no_discriminatory_statement",
    "不冒充真人": "interview_no_impersonation",
}

POLICY_CATEGORY_BY_KNOWLEDGE_CATEGORY = {
    "job_conditions": "service_scope",
    "reply_boundaries": "service_scope",
}

POLICY_ENFORCEMENT_BY_KNOWLEDGE_CATEGORY = {
    "job_conditions": "guidance",
    "reply_boundaries": "operation_block",
}

EVAL_TEMPLATES = {
    "社保": {
        "case_key": "knowledge_social_insurance_answer",
        "message": "入职以后有社保吗？",
        "must_contain": ["入职满一个月", "申请", "社保"],
    },
    "试岗与劳动合同": {
        "case_key": "knowledge_probation_contract_answer",
        "message": "试岗有工资吗，合同怎么签？",
        "must_contain": ["试岗", "3 天", "工资", "劳动合同"],
    },
}


def _text(value: object) -> str:
    return str(value or "").strip()


def _as_dict(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_list(value: object) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _slug(title: str, *, item_id: int | str) -> str:
    known = KNOWN_POLICY_KEYS.get(title)
    if known:
        return known
    asciiish = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    if asciiish:
        return f"knowledge_{asciiish}"[:120]
    digest = hashlib.sha256(f"{title}:{item_id}".encode("utf-8")).hexdigest()[:10]
    return f"knowledge_policy_{digest}"


def _fields(item: Mapping[str, Any]) -> dict[str, Any]:
    return _as_dict(item.get("fields"))


def _asset_ref_key(item: Mapping[str, Any]) -> str:
    ref = _as_dict(item.get("asset_ref"))
    return _text(ref.get("key"))


def _statement_from_item(item: Mapping[str, Any]) -> str:
    fields = _fields(item)
    parts: list[str] = []
    for key in ("answer", "body", "summary"):
        text = _text(fields.get(key))
        if text:
            parts.append(text)
            break
    for key in ("roadmap_note", "conditions", "evidence_note"):
        text = _text(fields.get(key))
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def _source(item: Mapping[str, Any], release_key: str) -> dict[str, Any]:
    return {
        "release_key": release_key,
        "item_id": item.get("item_id"),
        "revision_id": item.get("revision_id"),
        "title": item.get("title"),
    }


def _operation(
    *, package_key: str, operation_key: str, path: str, value: dict[str, Any],
    item: Mapping[str, Any], release_key: str,
) -> dict[str, Any]:
    return {
        "target_asset_key": package_key,
        "operation_key": operation_key,
        "path": path,
        "value": value,
        "source": _source(item, release_key),
    }


def _finding(
    *, title: str, detail: str, item: Mapping[str, Any] | None = None,
    release_key: str = "", suggested_next_step: str = "maintain_knowledge",
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "scope": "knowledge_center",
        "asset_key": "knowledge_center",
        "title": title,
        "detail": detail,
        "suggested_next_step": suggested_next_step,
    }
    if item is not None:
        result["source"] = _source(item, release_key)
    return result


def _current_document(asset: Mapping[str, Any]) -> dict[str, Any]:
    data = _as_dict(asset.get("data"))
    return _as_dict(data.get("document"))


def _base_hash(asset: Mapping[str, Any], package_key: str) -> dict[str, str]:
    data = _as_dict(asset.get("data"))
    content_hash = _text(data.get("content_hash"))
    return {package_key: content_hash} if content_hash else {}


def _base_content_hash(asset: Mapping[str, Any]) -> str:
    data = _as_dict(asset.get("data"))
    return _text(data.get("content_hash"))


def _existing_policy_keys(document: Mapping[str, Any]) -> set[str]:
    return {
        _text(item.get("policy_key"))
        for item in _as_list(document.get("policies"))
        if isinstance(item, Mapping) and _text(item.get("policy_key"))
    }


def _existing_eval_keys(document: Mapping[str, Any]) -> set[str]:
    return {
        _text(item.get("case_key"))
        for item in _as_list(document.get("evals"))
        if isinstance(item, Mapping) and _text(item.get("case_key"))
    }


def _policy_value(item: Mapping[str, Any], *, category_key: str) -> dict[str, Any] | None:
    title = _text(item.get("title"))
    statement = _statement_from_item(item)
    if not title or not statement:
        return None
    return {
        "policy_key": _slug(title, item_id=item.get("item_id") or title),
        "title": title,
        "statement": statement,
        "category": POLICY_CATEGORY_BY_KNOWLEDGE_CATEGORY.get(category_key, "service_scope"),
        "enforcement": POLICY_ENFORCEMENT_BY_KNOWLEDGE_CATEGORY.get(category_key, "guidance"),
    }


def _eval_value(title: str) -> dict[str, Any] | None:
    template = EVAL_TEMPLATES.get(title)
    if not template:
        return None
    return {
        "case_key": template["case_key"],
        "input": {
            "message": template["message"],
            "collected_facts": {
                "sys_recruitment_job_intent": {"status": "seeking"},
                "sys_interview_position_selection": {"position_key": "front_hall"},
            },
        },
        "expected": {
            "capability": None,
            "reply_must_contain": template["must_contain"],
            "reply_must_not_contain": ["保证", "肯定录用", "一定"],
        },
    }


def build_proposal(
    compile_input: Mapping[str, Any], *, package_key: str, current_asset: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    release_key = _text(compile_input.get("release_key"))
    document = _current_document(current_asset or {})
    policy_keys = _existing_policy_keys(document)
    eval_keys = _existing_eval_keys(document)
    operations: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for target in _as_list(compile_input.get("targets")):
        if not isinstance(target, Mapping):
            continue
        category_key = _text(target.get("category_key"))
        asset_target = _text(target.get("asset_target"))
        for raw_item in _as_list(target.get("items")):
            if not isinstance(raw_item, Mapping):
                continue
            item = raw_item
            title = _text(item.get("title"))
            has_ref = bool(_as_dict(item.get("asset_ref")))
            conditions = _text(_fields(item).get("conditions"))
            if "不一致" in conditions or "冲突" in conditions:
                findings.append(_finding(
                    title=f"{title}存在知识口径冲突",
                    detail=f"知识条目 conditions 标注存在口径冲突：{conditions}",
                    item=item,
                    release_key=release_key,
                ))
            if has_ref:
                continue
            if asset_target == "policies" and category_key in POLICY_CATEGORY_BY_KNOWLEDGE_CATEGORY:
                policy = _policy_value(item, category_key=category_key)
                if not policy:
                    findings.append(_finding(
                        title=f"{title}无法生成业务政策",
                        detail="条目缺少可写入政策 statement 的正文。",
                        item=item,
                        release_key=release_key,
                    ))
                    continue
                operation_key = "upsert_business_policy" if policy["policy_key"] in policy_keys else "append_business_policy"
                if operation_key == "upsert_business_policy":
                    skipped.append({
                        "title": title,
                        "reason": "current_package_already_has_policy_key",
                        "policy_key": policy["policy_key"],
                    })
                    continue
                operations.append(_operation(
                    package_key=package_key,
                    operation_key=operation_key,
                    path="/policies",
                    value=policy,
                    item=item,
                    release_key=release_key,
                ))
                eval_case = _eval_value(title)
                if eval_case and eval_case["case_key"] not in eval_keys:
                    operations.append(_operation(
                        package_key=package_key,
                        operation_key="append_business_eval",
                        path="/evals",
                        value=eval_case,
                        item=item,
                        release_key=release_key,
                    ))
                continue
            if category_key == "job_catalog":
                findings.append(_finding(
                    title=f"{title}缺少岗位绑定 asset_ref",
                    detail="新增岗位或岗位别名不由业务政策伪装写入；请先在知识中心补齐 position_key 归属，或在岗位配置责任面新增岗位。",
                    item=item,
                    release_key=release_key,
                ))
            elif category_key == "objection_scripts":
                findings.append(_finding(
                    title=f"{title}缺少话术资产引用",
                    detail="新增顾虑话术正文属于回复模板库或话术包责任面；请先维护并发布话术项，再把知识条目绑定到 reply_template 或 objection_handler。",
                    item=item,
                    release_key=release_key,
                ))
            else:
                findings.append(_finding(
                    title=f"{title}缺少可写资产引用",
                    detail=f"该条目属于 {category_key}/{asset_target}，当前本地 planner 未将其映射为可写业务包操作。",
                    item=item,
                    release_key=release_key,
                ))

    change_sets = [
        {
            "target_asset_key": package_key,
            "operation_count": len(operations),
            "operation_keys": sorted({_text(item.get("operation_key")) for item in operations}),
        }
    ] if operations else []
    summary = (
        f"本地 planner 基于知识版本 {release_key} 生成 {len(operations)} 个候选操作、"
        f"{len(findings)} 个责任面 finding；生成过程由 wisecopilot 本地 planner 完成。"
    )
    return {
        "ok": True,
        "generator": "wisecopilot.local_knowledge_compile_planner",
        "release_key": release_key,
        "package_key": package_key,
        "summary": summary,
        "operations": operations,
        "change_sets": change_sets,
        "findings": findings,
        "skipped": skipped,
        "base_document_hashes": _base_hash(current_asset or {}, package_key),
        "next_step": "Review operations, then rerun with --prepare-draft-save to get an MCP draft-save diff and confirmation token.",
    }


def _upsert_by_key(items: list[Any], *, key_field: str, value: Mapping[str, Any]) -> None:
    key = _text(value.get(key_field))
    for index, current in enumerate(items):
        if isinstance(current, Mapping) and _text(current.get(key_field)) == key:
            items[index] = dict(value)
            return
    items.append(dict(value))


def apply_operations_to_document(document: Mapping[str, Any], operations: list[Mapping[str, Any]]) -> dict[str, Any]:
    updated = json.loads(json.dumps(document, ensure_ascii=False))
    policies = updated.setdefault("policies", [])
    evals = updated.setdefault("evals", [])
    if not isinstance(policies, list) or not isinstance(evals, list):
        raise ValueError("business package document has no list policies/evals")
    for operation in operations:
        operation_key = _text(operation.get("operation_key"))
        value = _as_dict(operation.get("value"))
        if operation_key in {"append_business_policy", "upsert_business_policy"}:
            _upsert_by_key(policies, key_field="policy_key", value=value)
        elif operation_key in {"append_business_eval", "upsert_business_eval"}:
            _upsert_by_key(evals, key_field="case_key", value=value)
        else:
            raise ValueError(f"local planner cannot apply operation: {operation_key}")
    return updated


async def _read_compile_input(space_id: int) -> dict[str, Any]:
    result = await call_tool("design_get_knowledge_compile_input", {"space_id": int(space_id)})
    if not result.get("ok"):
        raise RuntimeError(f"design_get_knowledge_compile_input failed: {result}")
    return result


async def _read_current_asset(package_key: str) -> dict[str, Any]:
    listed = await call_tool("design_list_assets", {"asset_kind": "business_asset_package", "query": package_key})
    if not listed.get("ok"):
        raise RuntimeError(f"design_list_assets failed: {listed}")
    items = _as_list(_as_dict(listed.get("data")).get("items"))
    match = next((item for item in items if isinstance(item, Mapping) and _text(item.get("asset_key")) == package_key), None)
    if not match:
        raise RuntimeError(f"business package not found: {package_key}")
    record_id = match.get("record_id")
    asset = await call_tool("design_get_asset", {"record_id": int(record_id)})
    if not asset.get("ok"):
        raise RuntimeError(f"design_get_asset failed: {asset}")
    return asset


async def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.input_json:
        with open(args.input_json, encoding="utf-8") as handle:
            compile_input = json.load(handle)
    else:
        compile_input = await _read_compile_input(args.space_id)
    package_key = args.package_key or _text(
        (_as_list(compile_input.get("consumers"))[0] or {}).get("primary_business_package_key")
        if _as_list(compile_input.get("consumers")) else ""
    )
    if not package_key:
        raise ValueError("--package-key is required when compile input has no consumer package")
    current_asset = None
    if not args.no_current_asset:
        current_asset = await _read_current_asset(package_key)
    proposal = build_proposal(compile_input, package_key=package_key, current_asset=current_asset)
    if args.prepare_draft_save:
        if current_asset is None:
            raise ValueError("--prepare-draft-save requires reading the current asset")
        document = _current_document(current_asset)
        updated = apply_operations_to_document(document, proposal["operations"])
        prepared = await call_tool("design_prepare_draft_save", {
            "document": updated,
            "draft_key": "main",
            "base_content_hash": _base_content_hash(current_asset),
        })
        proposal["draft_save_prepare"] = prepared
        proposal["next_step"] = "Review draft_save_prepare. Commit with design_commit_draft_save only after explicit user confirmation; then publish separately."
    return proposal


def main() -> int:
    enforce()
    parser = argparse.ArgumentParser(description="Plan knowledge-center-to-business-asset operations locally.")
    parser.add_argument("--space-id", type=int, help="Knowledge space id to read through Design MCP.")
    parser.add_argument("--package-key", default="", help="Business package key. Defaults to the first declared consumer.")
    parser.add_argument("--input-json", help="Use a saved design_get_knowledge_compile_input JSON file instead of MCP.")
    parser.add_argument("--no-current-asset", action="store_true", help="Do not read the current package document for duplicate checks.")
    parser.add_argument("--prepare-draft-save", action="store_true", help="Prepare a draft save from the local proposal. This does not write the draft.")
    args = parser.parse_args()
    if not args.input_json and not args.space_id:
        parser.error("--space-id or --input-json is required")
    try:
        print(json.dumps(asyncio.run(run(args)), ensure_ascii=False, indent=2))
    except Exception as exc:
        print(json.dumps({"ok": False, "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
