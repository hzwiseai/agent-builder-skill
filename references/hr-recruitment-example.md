# Example: create an HR recruitment role

A worked design for the most common request this skill receives. Every tool
named here exists in the deployed catalog; confirm it with
`design_get_platform_contract` before relying on any of them, and
`python scripts/check_references.py` fails the build if one stops existing.

## Business request

Create an organization recruitment Agent that explains approved vacancies,
collects only the necessary candidate information, checks eligibility, offers
an available interview time, and creates an interview invitation. It must
respect a candidate's request to stop contact and hand unusual cases to a
human recruiter.

## Find what already exists

1. `design_list_assets` with `asset_kind: "task_asset_package"` and then
   `capability_contract`, `fact_contract`, `record_schema`. Recruitment
   contracts usually already exist under `sys_recruitment_*`.
2. `design_get_asset` on the task package you intend to install. Read its
   `configuration_contract`, `journey_contract`, and `capability_bindings`
   before designing anything new.
3. `design_inspect_business_package` on a comparable organization package to
   see a working closure and its `consumption_matrix`.
4. `design_list_reply_packages` and `design_list_reply_package_items` for the
   wording the customer will actually receive.

Reuse a published contract whenever its semantics and safety boundary fit.

## Typical closure

| Layer | Responsibility |
| --- | --- |
| Capability contracts | Read approved vacancy/location information; check screening eligibility; create an interview invitation only after all required facts and authorization are present. |
| Facts and schemas | Candidate profile, job intent, work area, eligibility, interview slot, schedule acceptance, and invitation receipt. Each has a declared record schema and source. |
| Events and SOPs | Candidate invitation request, invitation created/failed, and handoff/stop-contact paths with declared idempotency and consumers. |
| Task package | A screening task whose journey asks for one missing item at a time and binds only the declared operations. If it declares a `configuration_contract`, the organization's positions, aliases, and eligibility checks go in the installation's `skill_configuration`. |
| Business package | Organization-owned recruitment service that installs the task, supplies `skill_configuration`, and declares `policies`, `vocabulary`, and `expression`. |
| Reply package | The customer-facing wording, referenced from `expression.reply_packages`. Not a V2 draft asset; edited through the reply-item tools. |
| Blueprint and instance | A recruitment Agent blueprint with required MCP/knowledge capability slots; the actual recruiting calendar, HR data service, and channel are bound only when creating the organization Agent. |

## Safe execution sequence

1. Ask for the organization, target vacancies, eligible regions, interview
   policy, human-handoff owner, and which real data/calendar systems are
   available.
2. Produce the closure plan. Prepare the documents with
   `design_prepare_draft_bundle_save` when the change spans several assets of
   one package; it preflights the whole closure and writes atomically.
3. Show the returned diff. Only after the user confirms, call
   `design_commit_draft_bundle_save`.
4. `design_prepare_business_publish` re-runs the closure preflight and returns
   a token only when the package is `ready`; publish with
   `design_commit_business_publish` after the user confirms.
5. Create the Agent with `design_prepare_agent_creation` /
   `design_commit_agent_creation`.
6. **Then check the bindings.** The publish preflight validates the package
   closure, not the Agent. Call `design_get_agent_resources` and confirm every
   capability that declares a `requirement_key` has a matching
   `mcp_capability_bindings` entry with the same `capability_key`, and that any
   required knowledge source has a non-empty binding. Fix with
   `design_prepare_agent_resource_update` / `design_commit_agent_resource_update`.
7. Run focused screening, consent, stop-contact, duplicate-invitation, and
   handoff evaluations with `design_prepare_asset_evals` /
   `design_commit_asset_evals` where the Agent's runtime policy allows it.
   Inspect the published trace evidence before declaring the role ready.

The Agent must never claim an invitation was sent merely because it planned a
capability call; it may confirm completion only from the operation receipt.
