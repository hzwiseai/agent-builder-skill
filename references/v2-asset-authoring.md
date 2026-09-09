# V2 asset authoring guide

This guide carries judgment: which asset shape fits a need, what belongs where,
and which boundaries must not be crossed. It deliberately carries no field
lists. Field names, required properties, and enums live in the schemas, and a
copy of them here would drift into confidently wrong advice — read them with
`design_get_schema` using a key from `design_get_platform_contract`.

## Select the smallest asset shape

| Need | V2 asset shape |
| --- | --- |
| A reusable read or write operation | `capability_contract`, plus input/output record schemas, authorization, guards, result codes, and declared tool boundary. |
| Information that persists across turns | `fact_contract` with its `record_schema`; add it to the task data contract. |
| A business occurrence or asynchronous trigger | `event_contract`; declare consumers in its native subscriptions. |
| A reusable automated or human-reviewed response procedure | `sop_playbook`. |
| A reusable decision constraint | `business_policy`. |
| A focused business behavior such as recruiting screening or appointment collection | `task_asset_package`. |
| An organization's assembled role/service | `business_asset_package` with task installations and organization-owned `skill_configuration`. |
| A reusable instance shape | `agent_instance_blueprint`; actual server/tool/knowledge/channel bindings remain on the organization Agent instance. |
| Per-organization business values inside a reusable task | The task's `configuration_contract`, filled by each installation's `skill_configuration`. |
| The exact wording a customer receives | A reply template package item. Not a V2 draft asset: read and change it with the reply-item tools, never with a draft save. |

Do not create a new asset merely to restate a label. Prefer an existing
published contract if it supplies the same semantic operation and safety
boundary.

## Read the configuration contract before asking anything

A task's `configuration_contract` is the declared boundary between what the
platform reuses and what each organization supplies. Its `schema` is also the
shortest correct interview: every required property is a question the
organization must answer, and every enum is a closed set of allowed answers.
`reference_contracts` names the identity field of a list item, so other
installations can reference one entry by that key.

Ask for exactly those fields. A value the contract does not declare has nowhere
valid to live: putting it in a policy turns data into prose the runtime cannot
check, and inventing a `skill_configuration` field the task cannot validate
fails the closure.

## Authoring checklist

1. Define customer/business outcome, refusal and handoff behavior, and
   observable completion conditions.
2. Identify the precise operation boundary. For any real effect, declare a
   capability; for explanation-only work, keep the task capability-free.
3. Define only durable facts, including source and schema. Do not persist
   arbitrary tool output or conversation text.
4. Define a journey with required facts and legal state transitions. Let the
   model make semantic choices inside that declared space.
5. Declare event producers/consumers, idempotency, policies, evaluations, and
   MCP/knowledge requirements only where they are actually needed.
6. Place business-specific product, audience, cadence, and explanation
   content in the organization package's task-installation
   `skill_configuration`, validated by the task's `configuration_contract`.
   That contract holds a JSON `schema` and, where installations reference each
   other's entries, `reference_contracts` naming the identity field of a list
   item. Read the installed task before authoring the installation: a task that
   declares no configuration contract cannot validate a `skill_configuration`,
   and its business content belongs in the package's `policies`, `vocabulary`,
   and `expression` instead.
7. Validate the complete closure. Publish only after user confirmation; then
   create/bind the Agent separately.

## Judgment the schema cannot express

- A schema says a field may exist; it does not say the field should hold this
  content. Business vocabulary belongs in a declared configuration or in the
  package's policies and expression, never spread across whichever field
  happens to accept a string.
- A schema validates one document; it does not validate the closure's meaning.
  A package can be `ready` with every business value still copied from the
  template it was materialized from.
- A schema cannot tell you that removing one journey state also touches its
  transitions, its required fact, the collection projection, the guards that
  test that fact, the evaluation cases that supply it, and the prose that
  enumerates the funnel. Removing a step means finding every reference to it
  and deciding each one, then letting the closure preflight confirm.
- A schema cannot tell you a number is wrong. A recruitment package states
  salary, age limits and schedules to real candidates: an inherited template
  value is an assumption until the organization confirms it, and it must never
  be published as though it were verified.

## Non-negotiable boundaries

- Do not use retired V1 roles, skills, talks, asset fields, mappings, or
  runtime fallbacks.
- Do not put business routing or product logic in runtime code, MCP server
  implementation, Agent `runtime_config`, or resource bindings.
- Do not bind an MCP tool without a matching capability contract and resource
  requirement. The server/tool/credential choice is an organization Agent
  resource binding, never a system task hard-code.
- Do not publish against a stale draft revision. Re-read, revalidate, and show
  the updated diff if the revision changes.
- Express a policy guard that depends on collected state as the fact key it
  depends on, not as prose. A condition that only exists as a sentence is not
  enforced, and the model will apply the policy outside its intended branch.
- Give every reply item a key that names the branch it belongs to. An item
  keyed as a generic step, whose text only fits one branch of that step, will
  be cited in the branch it does not fit.
- Describe what a bare boolean fact actually asks. A `record_schema` field with
  no description leaves the model to invent the question, and it will reach for
  the internal wording in the journey node goal.
- A capability contract addresses its tool through `mcp_capability_key`, which
  is deliberately not its own `capability_key`. Keep that key stable when you
  introduce a renamed contract for the same operation, and the organization's
  Agent bindings keep working across the change.
- Publishing validates the package closure, not the Agent. After a publish that
  changes task installations or capabilities, read `agent_binding_coverage`
  rather than comparing key names by eye.

