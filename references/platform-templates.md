# Platform templates: the boundary this skill does not cross

Read this when the user asks to change what a platform template does for every
organization, rather than what their own role does.

## The two jobs are not the same job

| | Organization role (岗位) | Platform template |
| --- | --- | --- |
| Who | An organization administrator | A platform administrator |
| Scope | `scope=org`, owned by one organization | `scope=system`, `sys_*`, shared and read-only to every organization |
| Tools | The Design MCP, through this skill | The WorkTool repository and its sync script |
| Blast radius | One organization's conversations | Every organization that materializes it |

The Design MCP refuses a `sys_*` write with
`design_system_asset_write_requires_platform_workflow`. That refusal is the
contract, not a limitation to work around: an organization-scoped session must
not be able to change assets other organizations depend on.

## What this skill can do

- List the templates: `design_list_system_templates`.
- Ask which fit a requirement: `design_recommend_system_templates`.
- Read a template's card: its `name`, `description`, and `role_template`. The
  system task and business **documents** are not readable from an organization
  session — only system *foundation* assets are — so the closure becomes
  readable as the organization's own copy after materializing.
- Materialize one into the organization: `design_prepare_template_materialize`.
- Pull an organization task back to the latest platform source:
  `design_prepare_system_task_sync`, which shows exactly which organization
  changes the sync would overwrite.

Almost every "the template is wrong" request is really "our role needs to
behave differently", and that is an organization change: materialize, then
customize the organization draft. Reach for a platform change only when the
behavior should become the default for organizations that have not asked for
it.

## What a platform change actually requires

It happens in the repository, not through this skill:

1. Edit the versioned source under
   `server/app/business_assets/v2/system_templates/*.template.v2.json`. Keys
   must start with `sys_task_template_` or `sys_business_template_`.
2. Dry run, then apply:

   ```bash
   python scripts/sync_v2_system_assets.py --db --json
   python scripts/sync_v2_system_assets.py --db --apply --json
   ```

   The sync deduplicates on content hash: unchanged content publishes no new
   version, changed content publishes a new immutable one.
3. System assets carry only reusable flow and resource requirements.
   Organization knowledge, real MCP bindings, industry policy, and specific
   wording stay in the organization overlay after materialization.

## What to tell the user

Say plainly that changing a template is a platform-administrator action that
this skill cannot perform, name the repository path and the sync command above
so the request is actionable, and offer the organization-scoped alternative
that usually solves the real problem. Never simulate the change by editing the
organization copy and calling it a template fix.
