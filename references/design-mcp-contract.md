# WiseCopilot Design MCP contract

## Endpoint and authentication

The public, stable MCP endpoint is:

```text
https://crm.wiseaio.com/design
```

It uses MCP streamable HTTP. The tool catalog is listable without a session so
that a client can register the server, but every tool other than
`design_authenticate` refuses a call that carries no valid session. That tool accepts the
locally configured username and password, optionally an organization id, and
returns a short-lived connection-scoped session. All other tools require that
session. Passwords are never returned, persisted in assets, or included in
tool result payloads.

This handshake is deliberately client-neutral: Codex, Claude, and WorkBuddy
need only register the URL named by `mcp.json` and make local `.env` values
available to the client. `mcp.json` is a portable connection manifest, not a
claim that every client accepts the same configuration-file syntax. A client
adapter maps its local MCP registration format to `transport` and `url_env`.
A client that supports an OAuth or bearer-token
transport may exchange the same credentials before connecting, provided it
still gets the same organization-scoped Design session.

The service must use HTTPS, rate-limit failed authentication, redact secrets
from logs, and reject cross-organization access. A session may only act within
the authenticated user's active organizations and role permissions.

Before a session is issued, the service checks the authenticated organization's
`wise_copilot_enabled` setting. This is an organization feature setting, not an
organization-owned runtime MCP Server: it stores no URL, credential, tool, or
Agent binding. The organization's administrator controls it in Organization
Management. Disabled organizations receive
`design_organization_mcp_not_enabled`.

## Tool surface

Tools use the `design_` prefix. Each response includes a correlation id,
organization scope, evidence version(s), and a machine-readable status.

| Tool | Access | Purpose |
| --- | --- | --- |
| `design_authenticate` | unauthenticated | Establish a short-lived connection-scoped Design session. |
| `design_get_platform_contract` | read | Return the enforced act/dimension/enum values plus an index of the schema registry. The index carries repository paths, not schema bodies. |
| `design_get_schema` | read | Return one registered schema document by its registry key, with internal `$ref` targets inlined so a versioned shell resolves to the definitions it extends. Field names, required properties and enums come from here. |
| `design_list_assets` / `design_get_asset` | read | List or inspect authorized V2 drafts and their documents. |
| `design_inspect_business_package` | read | Resolve an organization package's draft release preview and closure diagnostics. |
| `design_diagnose_business_package` | read | Request the Builder Copilot's evidence-backed package diagnosis. Pass `conversation_key` to forward that conversation's bounded turn evidence into the diagnosis instead of leaving it to infer from the requirement text alone. |
| `design_list_system_templates` / `design_recommend_system_templates` | read | List the platform's reusable business and task templates, or ask which fit a stated requirement. The recommendation writes nothing but spends model tokens, and its `gap_reason` is part of the answer. |
| `design_prepare_template_materialize` / `design_commit_template_materialize` | publish | Create an organization business package from a system template after explicit confirmation. The commit publishes the organization's first release of that package; it does not stage a draft. |
| `design_prepare_system_task_sync` / `design_commit_system_task_sync` | publish | Replace one organization task with its latest published platform source after explicit confirmation. The prepare shows every organization change the sync would overwrite; the commit overwrites the task document and publishes a new version of it. |
| `design_list_resource_catalog` | read | List the organization's selectable MCP servers and tools, FAQ libraries, and knowledge documents, so the user can choose what an Agent binds. Credentials are redacted. |
| `design_get_organization_overview` | read | One orientation call: every organization business package, the Agents running it, each Agent's binding coverage and recent run health, and an `attention` list. Use it to choose a target before diagnosing. |
| `design_list_runtime_runs` | read | Index an Agent's recent runs by status, with each run's release version, delivery status, and decision fallback reason, so a single failed turn can be told apart from a pattern. Message text is never returned. |
| `design_get_runtime_evidence` / `design_get_conversation_evidence` / `design_list_agents` / `design_get_agent_resources` | read | Read one authorized V2 run, a bounded V2 conversation evidence summary, the Agent-instance list, or one Agent's effective resource requirements and bindings. FAQ direct-reply evidence includes the matched FAQ identity, score, threshold, match mode, and published policy flags, but not a second copy of answer content. Resource credentials are redacted. Conversation message text is omitted by default and is available to an organization-enabled, authenticated MCP session when it requests conversation analysis for its own organization. |
| `design_list_reply_packages` / `design_list_reply_package_items` | read | List the organization's reply template packages and read their items, including the message body a customer receives. These are not V2 draft assets and do not appear in `design_list_assets`. |
| `design_prepare_reply_item_update` / `design_commit_reply_item_update` | live wording write | Diff and then apply one reply item change after explicit confirmation. The commit rejects a stale item baseline. This wording is not staged behind a draft or a publish, so a committed change reaches the next matching turn. |
| `design_prepare_reply_package_clone` / `design_commit_reply_package_clone` | organization copy write | Copy one accessible system reply package and all its items into the authenticated organization with a distinct key. Prepare reviews source, target and item count; commit checks the source package and item baseline and returns the new package identity. No role is published or rebound. Re-read new item IDs, edit copied items, update the intended organization role's declared references, validate and publish separately. V2 Agent-only reply overrides are unsupported. |
| `design_prepare_draft_save` / `design_commit_draft_save` | draft write | Validate one organization draft and then save precisely that prepared document after explicit confirmation. The commit re-reads the draft and refuses a baseline that moved after the reviewed diff. |
| `design_prepare_draft_bundle_save` / `design_commit_draft_bundle_save` | draft write | Validate and atomically save up to 20 organization draft documents against one package closure after explicit confirmation. The commit rejects stale target baselines and never publishes. |
| `design_prepare_asset_evals` / `design_commit_asset_evals` | evaluation | Prepare and run bounded declared Eval cases for an Agent only when its runtime policy has opted in. The confirmed run consumes model tokens and records evaluation audit outcomes, but never creates a customer runtime turn or durable customer facts. |
| `design_prepare_business_publish` / `design_commit_business_publish` | publish | Capture a ready package preflight and publish only if the digest still matches after explicit confirmation. |
| `design_prepare_agent_creation` / `design_commit_agent_creation` | instance write | Validate and create an Agent instance from a permitted blueprint after confirmation. |
| `design_prepare_agent_resource_update` / `design_commit_agent_resource_update` | instance write | Validate and update an Agent's actual resource bindings after confirmation. |

The server may add read-only tools, but new mutating tools must declare their
authorization, required confirmation, affected identities, and audit result
before being used by this skill.

The upstream API's one-step "create an Agent from a system template" endpoint is
deliberately not exposed. It exists for clients with no asset editor, and this
skill has one: keeping materialization and Agent creation separate means that
selecting a template can never publish an organization release as a side effect,
and each write keeps its own reviewed diff.

## Write protocol

A confirmation token is bound to the session that issued it and to one action.
A client that opens a new session per command can never redeem its own token,
so the client keeps one session for the whole prepare/commit exchange.

1. The client reads existing assets and diagnostics, then calls the appropriate
   `design_prepare_*` tool with its requested document or payload.
2. The service returns validation diagnostics and a canonical diff, together
   with a short-lived, one-time confirmation token. It does not mutate state.
   The diff carries bounded before/after previews per JSON pointer, including
   inside arrays, so the confirmation gate shows what actually changed; values
   on a sensitive path collapse to `[redacted]`. Draft schema validation itself
   is authoritative at commit, and the prepare result says so.
3. The user explicitly confirms the displayed diff or stated Eval cost. The
   client calls the matching `design_commit_*` tool with that token. Every
   commit re-reads its target and refuses the write when the reviewed baseline
   has moved, so a concurrent edit fails closed instead of being silently
   overwritten.
4. Publication validates that the package's preflight digest has not changed.
   Agent creation and resource updates use their own prepare/commit token.

All writes must capture actor, organization, prior revision, exact diff,
published closure versions, validation result, and correlation id. Bundle
writes are transactional; a rejected or failed write must not leave a partial
closure available to runtime.

## Scope rules

- A release preflight validates the package closure only. `design_inspect_business_package`
  and `design_prepare_business_publish` also return `agent_binding_coverage`, a
  mechanical declared-versus-bound comparison for each Agent running the
  package, matched on `requirement_key` plus the capability contract's
  `mcp_capability_key`, which is the pair the runtime itself resolves. It is advisory: a package may legitimately be published before any
  Agent is bound to it, so it never gates the publish.
- System `sys_*` foundations are shared and read-only to organization users.
  A system change needs platform-admin authority and must never rewrite an
  organization's published package silently.
- System business packages are templates only. Materialize them into an
  organization-owned package before creating or running an Agent.
- Organization tasks and packages may reference visible system foundations,
  but must retain their own published closure and resource bindings.
- Reply template items are the organization's own authored business text, so an
  organization-enabled session may read and, after confirmation, change its own
  organization's items. They remain outside the V2 draft/publish lifecycle.
- The endpoint does not expose database credentials, arbitrary SQL, raw model
  prompts, raw secret configuration, or unrestricted file access. An
  organization-enabled, authenticated MCP session may request only the bounded
  customer/reply texts of its current organization for conversation analysis.
