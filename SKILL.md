---
name: wisecopilot
description: Diagnose, design, and safely author V2 business assets, packages, and Agent instances for an AI team, AI sales, or AI customer-service platform through the WiseCopilot Design MCP service. Use when a user asks to inspect or create a role, reusable task skill, Agent, or talk/reply package.
metadata:
  version: "0.1.3"
  display_name: "慧言AI员工训练Skill"
  display_name_en: "WiseCopilot AI Worker Trainer"
  description_zh: "通过 WiseCopilot Design MCP 诊断现有配置，为 AI 团队、AI 销售和 AI 客服设计岗位职责、任务技能、话术与应答边界，并以可追溯的方式落地到平台组织。"
  description_en: "Diagnose existing configuration and design roles, task skills, reply packages and guardrails for AI teams, sales and customer service through the WiseCopilot Design MCP, then apply them to an organization with a full audit trail."
---

# WiseCopilot asset designer

Use the WiseCopilot Design MCP service to turn a business requirement into an
evidence-backed V2 asset proposal or a controlled organization change.
This skill is portable: it is written for any MCP-capable client, including
Codex, Claude, and WorkBuddy. Client-specific MCP registration is deliberately
outside this file; the single endpoint and environment contract are in
[`.env.example`](.env.example) and
[the Design MCP contract](references/design-mcp-contract.md).

## Start every session

1. Load local configuration from `.env`; it includes `WISECOPILOT_MCP_URL`
   and `WISECOPILOT_API_BASE_URL`. Never print, commit, quote, or put
   the password into a prompt, asset, log, or generated file.
2. Connect to `WISECOPILOT_MCP_URL` using streamable HTTP. Call
   `design_authenticate` with the configured username and password before any
   organization operation. Keep its returned session credential in the MCP
   connection only. If it returns `design_organization_mcp_not_enabled`, ask
   the current organization's administrator to enable WiseCopilot external
   design access in Organization Management; never work around this gate.
   Reuse one Design session for the whole task. A `design_prepare_*`
   confirmation token is bound to the session that issued it, so a prepare and
   its commit must run in the same session or the commit is rejected.
3. Call `design_get_platform_contract`. It returns two different things, and
   confusing them causes invented fields:
   - **Authoritative values you can use directly**: `acts`, `dimensions`, and
     `embedded_enums`. Each names the schema position that enforces it, so a
     vocabulary act or a dimension value must come from these lists rather
     than being made up.
   - **An index, not definitions**: `schema_registry.schemas` lists 24 entries
     of `{key, path, description}`. The `path` is a repository path this
     session cannot open.

   For an actual field name, a required property, or an enum inside an asset
   document, call `design_get_schema` with the registry `key`. Never write a
   V2 field from memory, from a reference file, or from a schema you read in
   some other checkout: this skill's own guidance has been wrong about a field
   that way before. Do not invent a tool name the service does not advertise.
4. For a request about an existing system, gather evidence first with the
   read-only tools. Use `design_get_agent_resources` before recommending a
   resource or tool-binding change. State the organization, published version,
   Agent resource state, and assets that support the conclusion.

   When the user has not named a target — "what do we have", "which one should
   we improve", "optimize our recruitment agent" — start with
   `design_get_organization_overview`. It returns every business package the
   organization owns (the roles), the Agents running each one, each Agent's
   binding coverage and recent run health, and an `attention` list of concrete
   findings. Show the user that survey and let them choose; do not pick a
   target for them from a single signal, and do not propose a change before
   reading the chosen target's conversation evidence.
5. For a request to analyze a customer conversation, call
   `design_get_conversation_evidence` with its `conversation_key`. Use only
   the returned execution, asset, decision, and delivery evidence; it is not a
   transcript tool. If no V2 runs are returned, say that no V2 runtime evidence
   is available rather than falling back to legacy records or direct database
   access.
   For a conversation-analysis request, set `include_message_text: true`:
   the authenticated, organization-enabled MCP session is the authorization
   boundary for its own organization's conversation content. Keep the output
   bounded to the returned turns, do not expose it to another organization,
   and summarize rather than reproduce private text.

For any asset edit, follow [the asset concurrency specification](references/asset-concurrency-spec.md). File round-trips must retain the pulled `content_hash`; a missing or stale baseline is an error, never permission to overwrite the current organization draft.

Before asking a business user to edit an asset, call
`design_get_asset_edit_contract`. Treat its server-derived operations and
field ownership as the only editable surface. Translate labels and impact into
business language; never expose raw V2 paths as the primary form.
Before restoring or rolling back, call `design_get_asset_version_control` and
show the target published version, current draft state, and affected Agents.
Use `design_prepare_asset_version_restore` followed by explicit confirmation and
`design_commit_asset_version_restore`; a restore only changes the draft and must
still pass normal review and publish gates.

Before changing either side, classify the request with [the knowledge/asset change routing specification](references/knowledge-asset-change-routing.md). Knowledge is the source of business facts; assets carry behavior. Never assume a knowledge update fixes behavior, and never sync an asset document back into knowledge automatically. Fact-bearing asset changes require a reviewed knowledge backfill proposal.

Use [the facts-versus-behavior guide](references/facts-vs-behavior.md) as the foundational classification: identify the fact source, the behavior field, the durable Fact contract (if any), and the published version that will be exercised before proposing a change.

When a user asks how to register, configure, use, publish, or troubleshoot the AI
platform, follow [the platform help workflow](references/platform-helpdesk-workflow.md).
Use https://crm.wiseai.chat for registration/login and open the public help manual at
https://crm.wiseaio.com/help/manual for operating instructions. Do not use MCP or
organization knowledge bindings for these questions, and keep public help separate from
business-role assets.

## Diagnose a live conversation

Evidence alone does not locate a defect. Work the returned runs in this order.

### 1. Segment by closure before reading anything

Print, per run, `asset_provenance:published_closure_and_agent_binding`
(`business_package_release_version`) and
`capability_retrieval:initial_menu.active_task_key`. A conversation is not
guaranteed to run on one closure: a package published mid-conversation changes
the task, the capabilities, the facts, and the reply catalog from that turn on.

Never carry a conclusion across a release boundary. A defect observed on the
previous closure says nothing about the task that replaced it, and attributing
it to the current task is the most likely way to get the diagnosis wrong.

### 2. Split the turns by whether a reply exists

`reply_generated: false` is a different investigation from a wrong reply. Do not
analyze text that was never produced.

**No reply.** Read `decision_validation:turn_decision_output` and
`message_delivery:channel_disposition`:

| Evidence | Reading |
| --- | --- |
| `fallback_reason: v2_llm_decision_repair_failed`, `attempt_count: 2` | The model could not produce a decision that passes the output schema, twice. Read `first_error`, `repair_error`, and `attempts[]`: each attempt carries its rejection reason, `output_chars`, and `likely_truncated` with a `json_error_position`. A truncated second attempt is a length problem; a named contract error such as `v2_decision_action_capability_not_presented` is a closure problem. |
| `message_delivery.status: suppress` | The runtime withheld the reply on purpose. `reason` names the gate. Fail-closed is correct behavior, but the customer received silence, so it is still a defect to report. |
| `status: error` or `has_error: true` | A runtime failure, not an asset defect. Report it as such. |

Say plainly that the customer got nothing. A suppressed turn is not a
successful turn because the run status says `success`.

Then establish whether it is isolated or a pattern before proposing anything.
`design_list_runtime_runs` with the `agent_instance_key` returns the Agent's
recent runs with their `business_package_release_version`, `delivery_status`,
and `decision_fallback_reason`, plus a `suppressed_or_failed_count`. One
failure among healthy runs on the same release is a single bad generation; a
run of failures that starts at a release boundary is a closure problem.

**A reply exists.** Line up three fields per turn:
`state_transition:journey` (where the journey moved and whether the source was
`llm_legal_transition` or `declared_completion_fallback`),
`decision:turn_decision_output.template_refs` (which reply item was cited), and
`decision_prompt:initial.collected_fact_keys` (what the model already knew). A
turn that re-asks for a fact whose key is already collected is an asset defect,
not a memory defect.

### 3. Classify the mismatch

- reply text contradicts a collected fact, or repeats a previous turn verbatim
  -> the cited reply item, or a policy whose guard condition is written as
  prose instead of being keyed to a fact;
- journey state advanced but the reply belongs to the previous state -> the
  journey node goal or the reply item bound to that state;
- the wording is internal jargon the customer questions -> the reply item, the
  journey node goal, and any bare boolean in the backing `record_schema` that
  leaves the model to invent the question;
- `knowledge_retrieval:grounding` reports `binding_missing` -> the Agent's
  resource bindings, not the assets.

### 4. Read the asset that carries the offending text

The business package's `policies` and `expression`, the installed task's
`journey_contract` and `configuration_contract`, the installation's
`skill_configuration`, and the reply items via `design_list_reply_packages`
then `design_list_reply_package_items`.

### 5. Recheck the Agent bindings whenever the closure changed

The release preflight validates the package closure, not the Agent, so it can
report `ready` with no warnings while a publish that swapped a task
installation leaves the Agent bound to the previous capability keys.

`design_inspect_business_package` and `design_prepare_business_publish` both
return `agent_binding_coverage` for every Agent running that package, and
`design_get_organization_overview` reports it for the whole organization.

It matches the way the runtime does, on `requirement_key` plus the capability
contract's `mcp_capability_key` — **not** on the contract's own
`capability_key`. Those two differ by design: several differently named
contracts can address one bound tool, so a task swap that renames capabilities
does not break the bindings as long as the new contracts keep the same
`mcp_capability_key`. Comparing contract keys against binding keys reports
healthy Agents as broken; never diagnose a binding by eye that way.

Read the coverage before publishing and after any closure change. An unbound
capability is still presented to the model. Fix it with
`design_prepare_agent_resource_update`; publishing again will not.

To fix a binding, first show the user what exists.
`design_list_resource_catalog` returns the organization's selectable MCP
servers and their tools, its FAQ libraries, and its knowledge documents. Match
them against the Agent's declared `resource_requirements`, present the
candidates, and let the user choose which to bind. Never choose a knowledge
source or a tool for them: which library answers a customer correctly is a
business judgment, not something the closure determines.

When a requirement is enabled but the catalog offers nothing that fits, that is
a configuration task, not a design choice. The catalog returns
`empty_categories`, each with a `configure_at` carrying the console `menu`
label, its `path`, and a `note` on the steps that follow.

Send the user there by the menu label the console actually shows — "知识中心 ›
文档加工" — not by a URL. People navigate by menu name, and a raw path reads as
an internal detail. Do not offer to disable the requirement as the easy way
out, and never bind something approximate to make the coverage look complete.

### 6. Name one asset and one field

State the root cause as a named asset and a named field. "The task package has
a dialogue-advance problem" is not a diagnosis. If the evidence does not reach
that precision, say which evidence is missing instead of guessing.

The repair is authoring, and it follows the same rules as writing the field in
the first place. A fix that answers this one conversation by adding an
unconditional instruction is how the next conversation breaks: state the
condition before the instruction. When the named field belongs to a sales
installation, read
[the progressive explanation skill](references/sales-progressive-explanation.md)
before proposing the edit.

### 7. Keep diagnosis local

Do not call a system Copilot diagnosis or generation endpoint. Use the bounded
runtime/conversation evidence already returned by the Design MCP and make the
diagnosis locally. The retired `design_diagnose_business_package` tool may be
present for compatibility, but returns `design_model_generator_disabled` and
must not be used.

## What this tool surface cannot tell you

Say so plainly when you reach one of these, and do not fill the gap by guessing.

- **The model's own output.** `decision_validation` names why each attempt was
  rejected, but the rejected text itself is never retained. You can see that a
  reply was truncated at a character position; you cannot read what it said.
- **What a capability would have returned.** Diagnosis reads recorded runs. A
  binding gap that the conversation never exercised is a demonstrated gap in the
  bindings, not a demonstrated runtime failure. Report it with that distinction.
- **Fact values.** Traces carry fact keys, never values. You can prove the model
  had a fact; you cannot prove what was in it.
- **A system task or business package document.** Organizations may browse the
  reusable system foundation catalog, never system compositions. A template's
  closure becomes readable only as the organization's own copy after
  materializing it.
- **Anything outside the authenticated organization.** No cross-organization
  read exists, and none should be attempted.

## Create a new role

A role in this product is a business package; the console calls it 岗位, and the
Agent instance running it is an AI成员. Creating one normally starts from a
platform template, not from an empty closure. The console states the pipeline
as: 平台现成岗位 → 复制成你的草稿 → 自动预检 → 你来发布 → 成员按新版本工作,
and the boundary as: the assistant only edits drafts, never publishes for the
user, and never touches an Agent's already-bound knowledge and tools.
Treat the matching knowledge-center business template as part of the same
design decision: the role template defines how the Agent works, and the
knowledge template defines what source content maintainers should provide for
that role.

When a business user selects a role template, keep the next step in knowledge
center language. Do not ask them to understand or fill V2 internals such as
policy keys, fact keys, capability contracts, schema fields, guard names,
`asset_ref`, or package keys. Use those mappings behind the scenes only to
match templates, validate coverage, and later compile reviewed knowledge into
assets. The user-facing output should be a knowledge checklist grouped by the
selected knowledge template's categories: what each category means in business
terms, whether it is required, what examples or starter items already exist,
what information the user still needs to provide, and where they should review
or publish it in the knowledge center.

1. `design_recommend_system_templates` with the user's requirement, then
   `design_list_system_templates` for the full list. Also call
   `design_list_knowledge_templates` and present the matching knowledge
   business templates in business language: template name, role fit,
   required knowledge categories, and any missing coverage. Match role
   templates to knowledge templates by the knowledge
   template's `asset_template_refs`: `asset_template_refs.business` must
   include the selected business role template key, or
   `asset_template_refs.task` must include a task template key that the role
   installs. Name similarity is only a hint for the user, never an automatic
   match. Present the candidates **and the `gap_reason`**. A stated gap is a
   real answer: when no role or knowledge template fits, design a closure or a
   knowledge template instead of forcing the nearest one onto the request.
2. Read what is actually readable. An organization session can browse system
   **foundation** assets but never a system task or business **composition**,
   so a template's own document is not available before materializing: choose
   from its `name`, `description`, and `role_template`. For the knowledge side,
   read `design_list_knowledge_template_items` for the selected knowledge
   template before promising what source items it seeds, and read
   `design_get_knowledge_item_kind_templates` before authoring any custom
   item fields. Convert those templates into a business-facing intake guide:
   use labels, descriptions, examples, and required/optional status; hide
   internal destination and asset mapping unless the user is explicitly doing
   platform maintenance. Read the resulting organization copy — including its
   `configuration_contract`, which decides where the organization's vocabulary
   goes — after materialization. Do not promise behavior you have not read.
3. `design_prepare_template_materialize`, show the diff, and only after the
   user confirms, `design_commit_template_materialize`.

   **Materializing publishes.** The console button is 创建并发布: it creates
   the organization's first usable release of that package, not a draft. Say
   that when you ask for confirmation. System foundation assets are not copied;
   the organization gets its own task, package, and default Agent
   configuration, and later differences are maintained in the organization
   draft and republished.
4. Create or choose the knowledge space for this role. If no suitable space
   exists, use `design_prepare_knowledge_space_create` /
   `design_commit_knowledge_space_create` to create an empty organization
   knowledge space. Then set its knowledge business template with
   `design_prepare_knowledge_space_template` /
   `design_commit_knowledge_space_template`; the `business_pack_key` must be
   the selected knowledge template key, not the role package key. If no
   knowledge template has matching `asset_template_refs`, stop and show the
   platform/admin-facing missing mapping: maintain or copy a knowledge template
   first, and set its applicable business/task template refs before creating a
   space from it. Do not make the business user map role assets manually. If
   the user wants the template's starter content, preview and import it with
   `design_prepare_knowledge_template_import` /
   `design_commit_knowledge_template_import`. Imported items are draft
   knowledge: guide the user to complete the required knowledge checklist,
   review, publish and activate the knowledge release before an Agent can use
   it. This step does not write position assets.
5. Customize the organization draft and publish it. A template arrives generic;
   this step is what makes it this organization's role. See below. When the
   materialized package installs `progressive_explanation_skill`, read
   [the progressive explanation skill](references/sales-progressive-explanation.md)
   before filling its configuration.
6. Create the Agent, then bind its real resources. A freshly materialized
   package has no knowledge or MCP binding: 岗位 defines how the work is done,
   the Agent's resources define what it is done with. Bind the Agent to the
   published knowledge release or resource bindings through the Agent resource
   tools, then run the knowledge center → asset loop when approved knowledge
   must update the role's V2 assets.

## Run the knowledge center → asset loop

Use this workflow when approved knowledge must become a published organization
position package. The knowledge center is the business-fact source; the
installed task/skill is the contract. Do not turn knowledge into runtime code,
do not edit `sys_*` assets, and do not silently change an Agent binding.

There are two independent releases. A knowledge release makes reviewed content
available to its bound AI members and supplies a pinned compile input. A
business-package release makes a separately reviewed asset draft live. The
second never happens implicitly as a side effect of the first.

1. **Inspect and repair source knowledge.** Call
   `design_get_knowledge_space`, `design_get_knowledge_publish_overview`, and
   `design_get_knowledge_compile_input`. Read item-kind templates before
   authoring. Create or revise source content with
   `design_prepare_knowledge_item_save` / `design_commit_knowledge_item_save`,
   then approve each intended revision through
   `design_prepare_knowledge_review` / `design_commit_knowledge_review`.
   Keep a source contradiction in the knowledge center: do not hide it in a
   position policy.
2. **Publish and activate the knowledge release.** Call
   `design_prepare_knowledge_publish`; show its approved-item count,
   destinations, bound AI members, RAG connection choice (if any), and the
   fact that position assets are not touched. Only after the user confirms,
   call `design_commit_knowledge_publish`. If the pipeline is asynchronous,
   re-read `design_get_knowledge_publish_overview` until the release is active
   or it reports an actionable failure. Never compile from
   `approved_not_released` when the request is for a released source.
3. **Lock a declared consumer and generate a local proposal.** Read
   `design_get_knowledge_compile_input` again. Choose an exact
   `(agent_instance_key, primary_business_package_key)` from `consumers`; do
   not infer it from a display name. Use the deterministic local planner:

   ```bash
   python scripts/knowledge_compile_planner.py --space-id <space_id> --package-key <package_key>
   ```

   The planner reads the active release and current business package through
   MCP, then emits reviewable `operations`, `findings`, `change_sets`, source
   item ids, and `base_document_hashes` without model-token use. It may append
   business policies and Eval cases when a released knowledge item maps to a
   business-package field. It must leave new positions, reply-template text,
   fact/check definitions, resource bindings, and source contradictions as
   findings for their owners. In this skill, proposal generation belongs to
   the local planner; MCP remains the read, validation, draft-write, and
   publish gate.

   The compile input also includes deterministic `impact_summary` and
   per-item `impact` metadata. Use them as routing gates before proposing
   prose changes:

   - `asset_update`: compare the released source with the referenced asset
     and include a precise draft diff.
   - `asset_create`: propose a new allowed entry with a stable lower-case key;
     do not invent a new fact, qualification, capability, or reply-template
     owner.
   - `knowledge_only`: do not manufacture an asset change merely because the
     text is relevant; verify that the knowledge release is sufficient on its
     own.
   - `unclassified`: stop asset authoring and report the category/owner gap.

   Treat `change_kind=fact` and `change_kind=behavior` separately. A
   behavior change requires impact scope and a regression Eval; a fact change
   requires a source item/version and, when durable, the corresponding
   `fact_contract`/record binding. Use
   `impact_summary.recommended_next_step` only as a workflow hint, never as
   permission to write or publish.
4. **Review by responsibility, not by prose similarity.** Each operation must
   carry the released source item/version and target an allowed V2 field.
   Existing policy/skill configuration items may be updated only when the
   server-provided contract allows it. New reply-template text belongs in the
   reply template package first; new facts, qualifications, capabilities,
   bindings, and source contradictions remain findings for their actual owner.
   Do not turn an unresolved finding into an arbitrary policy or Eval.
5. **Validate before writing when evidence is available.** After the user
   approves the exact operation list, use the local planner's
   `--prepare-draft-save` mode to let MCP perform the authoritative schema,
   scope, stale-baseline, and diff checks before any write. If the Agent or
   package has no runnable Eval gate for this path, state that clearly and keep
   the draft-save diff plus release/source receipts as the available evidence.
6. **Write drafts, then publish separately.** For a local proposal, run:

   ```bash
   python scripts/knowledge_compile_planner.py --space-id <space_id> --package-key <package_key> --prepare-draft-save
   ```

   This locally applies the reviewed operations to the current business
   package document and calls `design_prepare_draft_save`. It returns a
   confirmation token and exact diff but does not write. After the user reviews
   the diff and explicitly confirms, call `design_commit_draft_save`. This
   writes only a draft and never publishes. Read the returned release preview
   and Agent binding coverage. Then use
   `design_prepare_business_publish` / `design_commit_business_publish` as a
   separate publication decision. Check the knowledge publish overview again:
   then call `design_prepare_local_knowledge_compile_receipt` /
   `design_commit_local_knowledge_compile_receipt` with the same release,
   consumer and reviewed operations. This records only the audit link between
   the local planner and the published package; it does not call a model or
   modify an asset. Finally re-read the overview: the asset update status must
   advance from `review_ready` or `draft_written` to `published` for the
   same source release.
   If any reviewed operation changes behavior (routing, guards, prompts,
   capability selection, or task flow), call publish preparation with
   `behavior_change: true`. The publish preflight then exposes the affected
   Agents and blocks publication when their declared asset Eval policy is not
   enabled. Show `publication_impact` to the user before confirmation.
7. **Report the receipts.** Give the user the knowledge `release_key`, the
   Harness run/session id, changed organization asset keys, candidate/Eval
   result, business-package published version, remaining findings and whether
   the position asset status is `published`. A task is only closed when all of
   those identify the same organization, source release, Agent and package.

The MCP tools use prepare/commit confirmation tokens bound to one Design
session. A stale token means the release, source, consumer, or draft moved:
re-read it, regenerate the proposal, and show the new diff. Never retry a
commit with an old operation list or bypass these tools with a REST write.

## Optimize a role that has no conversations yet

The diagnosis workflow reads runtime evidence, and a role created minutes ago
has none. Optimizing it is a different job with different sources.

**The configuration contract is the interview script.** Read the materialized
task's `configuration_contract`: its `schema` states exactly what the
organization must supply, and its `required` lists what cannot be left out. Ask
for those fields and nothing more. A recruitment screening task, for example,
declares `positions[]` requiring `position_key`, `display_name`, `aliases`,
`public_facts`, and `eligibility_checks`, where each check carries its own
`question`, `assistance_allowed`, and `failed_blocks_booking`. That is a
precise question list: which roles are you hiring, what does each get called by
candidates, what may be stated publicly, what disqualifies someone, and does
failing a check stop a booking or merely get noted.

Gather the requirement as one flow — ask the user to talk through a real
customer conversation from first message to close — and then route each
sentence to exactly one asset: what the customer must understand, what has to
be learned first, what interrupts, what may never be said, what a later turn
needs to remember, what changes something outside the conversation, and what is
only wording. The same rule restated in two of those places drifts apart, and
the customer-facing copy is the one that ends up wrong.

Work in this order, and stop at the first source that answers the question:

1. **`configuration_contract` → `skill_configuration`.** Fill every required
   field from what the user tells you. Do not invent a value to satisfy the
   schema, and do not restate in a policy what the contract can hold as data.
   A schema field's `description` states how that field has to be written, not
   only what type it holds; a value that satisfies the type and contradicts the
   description is a defect the preflight will name. For a sales installation,
   read [the progressive explanation skill](references/sales-progressive-explanation.md).
2. **Journey goals.** Read every node goal in `journey_contract`. Each one
   states an assumption about how this business works; surface the ones that do
   not match and change the wording, not the state machine.
3. **Policies.** Keep only what the organization actually enforces. A policy
   whose guard depends on collected state must name the fact key it depends on.
4. **Reply items.** Read them with the reply-item tools. Template wording is
   written for the generic case; check the customer-facing text against the
   vocabulary this organization's customers use.
5. **Verify without traffic.** Run the package's declared cases with
   `design_prepare_asset_evals` / `design_commit_asset_evals` where the runtime
   policy allows it. Evals are the only evidence available before the role goes
   live; say so, and say plainly when they are not enabled.
6. **Then publish, create the Agent, and bind resources.**

Once real conversations exist, switch to the diagnosis workflow above: from
that point the runs are better evidence than any reading of the assets.

Resist two temptations. Do not rewrite a journey or a capability because the
template's shape is unfamiliar — the shape is the reusable part, and the
organization's difference belongs in configuration and wording. And do not
declare the role ready because the closure validates: a package can be `ready`
with every business value still generic.

Do not treat an existing organization package as a starting template by
copying it. Materialize the platform template that the copy came from, so the
organization keeps its own closure and can be re-synced later with
`design_prepare_system_task_sync`. That sync overwrites the organization's task
document and publishes a new version of it. Its preview lists the journey goals
and task policies the organization currently has, and sets
`incoming_document_readable: false`: the platform document replacing them
cannot be read from an organization session. Tell the user both halves — what
they have now, and that this is not a before/after diff — before asking for
confirmation.

There is deliberately no one-step "create the Agent from a template" tool here.
Materializing and creating the Agent stay separate so that selecting a template
never publishes an organization release as a side effect of picking one.

Changing what a template does for **every** organization is a platform
administrator's job and is not possible through this skill; see
[platform templates](references/platform-templates.md).

## Design workflow

Classify the user request before proposing assets:

- **Diagnose**: read the published closure, resource bindings, and optional
  trace summary. Report the smallest evidence-backed cause and a reversible
  recommendation. Do not create a draft.
- **New reusable behavior**: propose the smallest V2 closure: only the
  foundation contracts, task package, business package, and Agent blueprint
  that are genuinely needed. Reuse existing system contracts when their
  semantics fit.
- **Organization-specific behavior**: create or update an organization-owned
  draft. Read the installed task first and let its shape decide where the
  business content goes:
  - the task declares a `configuration_contract` (a `schema`, sometimes with
    `reference_contracts`) — put the organization's vocabulary and parameters
    in that installation's `skill_configuration`, validated against that
    schema. This is the preferred shape: approved positions and their aliases,
    eligibility checks, and per-organization wording parameters belong here,
    not restated as prose in a policy;
  - the task declares no configuration contract — the same content has to live
    in the business package's `policies`, `vocabulary`, and `expression`, and
    in the task's `journey_contract`. Do not invent a `skill_configuration`
    that the task cannot validate.

  Real server/tool/knowledge bindings always belong on the Agent instance. Do
  not copy system assets merely to make them editable.
- **System-wide reusable foundation**: produce a proposal only. System-scope
  assets are shared and read-only to organization users, so require an
  explicit platform-admin approval before the server creates or publishes one.

For every create or change request, return a compact design plan containing:

1. the business outcome and in/out-of-scope behavior;
2. assets to reuse, create, or change, with scope and stable key;
3. declared capabilities, facts, events, SOPs, policies, resource
   requirements, and evaluations where applicable;
4. the required organization bindings and any unresolved choices;
5. a validation and publication plan.

Prefer evidence over intent when closing a change. Where the Agent's runtime
policy allows it, run the package's declared cases with
`design_prepare_asset_evals` / `design_commit_asset_evals` after the draft is
saved and before publishing, and report the case results. An eval run spends
model tokens and records audit outcomes, so it needs its own confirmation; say
that when you ask. When evals are not enabled, say that the change is going out
unverified rather than implying it was checked.

For every write, call the matching `design_prepare_*` tool first. Use
`design_prepare_draft_bundle_save` when one change affects several assets in a
business-package closure; it preflights and writes the group atomically. Present
its validation result and exact diff, then call the matching `design_commit_*`
tool only after the user explicitly confirms the one-time token.

The `release_preview` returned by `design_prepare_draft_bundle_save` and
`design_prepare_business_publish` also carries `configuration_review`: per
installation, the findings of reading each configured value against the writing
rules its own schema states. Report every `level: "error"` finding with its
`path` and fix it before asking for confirmation — it means the value satisfies
the type and contradicts the field's stated purpose, which the closure check
cannot catch. The review never changes `status`; a package can be `ready` and
still be written badly. Never infer
approval from a request to "design" an asset. If a commit returns a
`*_confirmation_stale` code, the asset moved after the user reviewed it:
re-read it, prepare again, and show the new diff rather than retrying.

## Edit an asset as a local file

For anything larger than a one-field change, work on the document as a file
instead of assembling it inline:

1. `python scripts/design_asset_file.py --pull <record_id> --file workspace/asset.json`
   writes the asset's identity, its `content_hash`, and its document.
2. Edit `document` in that file. Change only what the diagnosis calls for.
3. `python scripts/design_asset_file.py --push --file workspace/asset.json`
   prepares the save and prints the diff. It does not write.
4. Show the diff to the user. Only after they confirm, re-run the push with
   `--confirm`.

The push sends the `content_hash` captured at pull time. If anyone published
into that window the prepare returns `design_draft_base_content_hash_stale`
with the current hash: pull again, re-apply the change onto the current
document, and show the new diff. Never resend an older document to get past it,
because a whole-document save silently deletes whatever was added meanwhile.

## Customer-facing wording

### 两类话术包的生效规则

| 话术包类型 | 可否直接修改 | 正确流程 | 生效时间 |
| --- | --- | --- | --- |
| 系统话术包 (`scope=system`) | 不可 | 复制为组织话术包 → 修改组织副本 → 切换岗位引用 → 校验并发布岗位 | 岗位发布后 |
| 组织话术包 (`scope=org`) | 可以 | 读取当前条目 → 预览差异 → 用户确认 → 提交单条话术修改 | 提交成功后，下一次命中立即生效 |

在请求确认前必须明确告诉用户：组织话术包的单条话术不是岗位草稿，提交后不会等待业务包发布，而是直接影响后续匹配到该话术的生产对话。若用户只想试稿，先复制到独立的组织话术包或使用岗位草稿中的其他行为配置，不要直接修改线上组织话术。

The text a customer actually reads usually comes from a reply template
package, referenced by the business package's `expression.reply_packages`,
`hard_templates`, and `recall_bindings`, and cited per turn in
`decision:turn_decision_output.template_refs`. These items are not V2 draft
assets and never appear in `design_list_assets`; read them with
`design_list_reply_packages` and `design_list_reply_package_items`.

When the referenced package has `scope=system`, keep it read-only. Use
`design_prepare_reply_package_clone` and `design_commit_reply_package_clone`
to create an organization copy with a distinct package key and a meaningful
name. Review the source, target, and copied item count before committing;
the authenticated session determines the organization. Never change the
system package's ownership in place.

After copying, read the new package's items to obtain their new IDs (item
keys are preserved). Edit the copied items with the reply-item update tools.
Then pull the intended organization role's current draft and replace its
source references: `expression.reply_packages`, qualified package/item
references in `hard_templates`, `recall_bindings`, and any other declared
template references in the affected closure. Preserve item keys and unrelated
references; do not blindly replace text in message bodies. Use the existing
draft save, closure validation, and business publish workflow. A copy alone
does not switch a role to the new wording. Verify the published closure
references the organization copy before reporting the switch complete.

If the role itself is a system template, first materialize an organization
role using the existing template tools. Explain that changing a shared role
affects Agents running that role. V2 resolves system and organization reply
packages; it does not support per-Agent reply override packages. For an
Agent-only request, use a separate organization role with its own reply
package and the supported instance workflow; do not claim an existing Agent
was switched unless its effective binding was verified. Never introduce
legacy user-scoped override packages or legacy Agent reply bindings.

A reply item is live wording. `design_commit_reply_item_update` is not staged
behind a business-package draft or a publish, so the next matching turn uses
the new text. Say that plainly when you ask the user to confirm one, and
prefer fixing the policy or journey node when the defect is a decision defect
rather than a wording defect.

For a declared-Eval request, call `design_prepare_asset_evals` before the run.
It is not a production customer turn, but it consumes configured-model tokens
and records Eval audit results. Obtain explicit confirmation of that effect
before `design_commit_asset_evals`; do not use Eval as an implicit approval to
save or publish assets.

## Where files go

`scripts/` and `references/` are the skill: shipped, reviewed, portable, and
identical for every user. `SKILL.md` and `mcp.json` are too.

A run that uses the skill must not edit any of them, whatever stage the skill
is in. Editing a helper mid-task removes a confirmation step for every later
session, and nobody can then say which version produced which change. Put the
workaround in `workspace/` and report what the shipped script should do
differently. Once the skill is released, that edit also fails the shipped
scripts' hash check outright, with `skill_integrity_failed`; when you see that
code, restore the files from version control rather than working around it.

`workspace/` is where everything a run produces goes: pulled asset documents,
their edited copies, exported evidence, throwaway analysis scripts. It is
gitignored and disposable. Two rules hold inside it:

- A workspace script may read anything the session is authorized to read, but
  no write may bypass the confirmation protocol. Every draft save, publish,
  Agent change, and reply-item change goes through `design_prepare_*`, a diff
  the user reads, and then `design_commit_*`. Calling a REST write endpoint
  directly with the session credential removes the gate the user relies on.
- Never write credentials, session ids, or customer message text into a file
  under `workspace/`.

Maintaining, versioning, and packaging the skill itself are a separate job:
see [the maintainer guide](references/maintaining.md).

## Included client scripts

- Use `scripts/design_mcp_client.py` to list or call MCP tools from a terminal.
  It authenticates from `.env`, caches the Design session id in
  `.session.json`, and reuses it so a prepare and its commit share one session.
  Example:
  `python scripts/design_mcp_client.py --tool design_list_assets --args-json '{"page_size": 20}'`.
  Pass `--session-id` to pin an explicit session, or `--new-session` to force a
  fresh login. Never commit `.session.json`.
- Use `scripts/design_api_client.py` only for direct, read-only diagnostic API
  evidence. It obtains its base URL from `WISECOPILOT_API_BASE_URL`; it does
  not implement any write endpoint. Example:
  `python scripts/design_api_client.py --operation platform-contract`.
- Use `scripts/design_asset_file.py` for the pull/edit/push round trip described
  above. Keep its pulled files under `workspace/`.
- Do not add a separate write path to any of these scripts. Draft saves,
  publication, Agent creation, reply-item changes, and resource binding must
  continue through MCP confirmation.

## V2 constraints

These restate the platform's own rules. Where this section and the live
platform contract disagree, the platform contract wins; report the discrepancy
instead of following the stale side.

- Use only native V2 foundation assets: `capability_contract`,
  `mcp_requirement`, `customer_expression`, `business_policy`,
  `record_schema`, `fact_contract`, `event_contract`, and `sop_playbook`.
  Compose them with `task_asset_package`, `business_asset_package`, and
  `agent_instance_blueprint`.
- Let the model make semantic choices inside the published closure. Runtime
  supplies candidate recall and safety gates; it must not replace the model
  with hard-coded business routing, and neither should an asset you author.
- Field names, required properties, and enums come from `design_get_schema`,
  never from this file.
- Model durable cross-turn information as a declared Fact. Runtime context,
  tool output, and free-form configuration do not become durable data by
  themselves.
- A capability contract is the only operation boundary. A task without a
  capability binding may explain or route, but must not claim that it performed
  an operation.
- Keep business decisions in published assets. Runtime and MCP tools may
  validate, bind resources, execute declared operations, and record evidence;
  they must not hard-code product, segment, or journey routing.
- Events are delivered through `event_contract.subscriptions[].consumers` and
  SOP execution. Do not create a separate event-to-SOP mapping asset.
- A live Agent runs an organization-owned, published business package. It must
  not run a system business package directly.
- A policy guard that depends on collected state must name the fact key it
  depends on. A condition expressed only as prose ("when the position is not
  yet confirmed") is not enforced, and the model will apply the policy outside
  its intended branch.
- A conditional instruction states its condition first. "Ask for X when X is
  unknown" written as "you must ask for X" with the condition trailing behind
  it is applied unconditionally. Runtime rejects a collection question aimed at
  a fact that is already collected, and a turn whose only defect is that
  question can lose its entire reply, so the customer receives nothing.
- Progress a later step depends on must actually be recorded. A checkpoint
  evaluated against delivered units never fires if delivery is not written to
  the declared fact; no preflight can see this, so verify it against a real
  conversation.
- Never use retired V1 asset concepts, compatibility fields, or fallback
  paths. A failed closure must remain fail-closed and observable.

## Reference routing

- Read [the Design MCP contract](references/design-mcp-contract.md) when
  connecting, selecting a tool, or designing server-side access controls.
- Read [the V2 authoring guide](references/v2-asset-authoring.md) for an asset
  creation or migration request.
- Read [the HR recruitment example](references/hr-recruitment-example.md)
  when the user asks for a recruitment role or needs a complete worked design.
- Read [the progressive explanation skill](references/sales-progressive-explanation.md)
  when a package installs `progressive_explanation_skill` and you are filling
  in, optimizing, or repairing that installation.
- Read [platform templates](references/platform-templates.md) when the user
  wants to change a template itself, or asks why a `sys_*` write is refused.
- Read [the maintainer guide](references/maintaining.md) only when changing,
  versioning, or packaging this skill. It is not needed to use it.
