# Maintaining and releasing the skill

For whoever changes the skill itself. Using the skill never requires any of
this; see `SKILL.md` for that.

## Lifecycle stages

`scripts/integrity.json` records a `stage` and the sha256 of every shipped
file:

- **`design`** — the skill is still being written, so the shipped files change
  by intent. Scripts run normally; `python scripts/_integrity.py --verify`
  still reports drift, as information rather than a failure.
- **`released`** — every shipped script verifies the hashes before it does
  anything and exits with `skill_integrity_failed` on a mismatch, and the files
  carry the read-only bit.

| Command | Use |
| --- | --- |
| `python scripts/_integrity.py --verify` | Report drift and the current stage. |
| `python scripts/_integrity.py --bless` | Record the current files while staying in the same stage. |
| `python scripts/_integrity.py --release` | Record the files, move to `released`, and set the read-only bit. Used inside a package build; run it on the working copy only for a deliberate local freeze. |
| `python scripts/_integrity.py --reopen` | Return to `design` and clear the read-only bit for the next round. |

`SKILL.md` is hashed as its `name` line plus its body. The rest of the
frontmatter is catalogue metadata that installers rewrite (one replaces
`version` and the display fields with `install_method: upload`), so a fresh
install verifies as intact instead of teaching people to `--bless` whatever
they find. Every other shipped file is hashed byte for byte.

None of this is a sandbox. Anything that can edit a script can edit the
manifest too. It makes a change loud and deliberate, not impossible.

## Before a release

```bash
python scripts/check_references.py
```

It fails when the shipped Markdown names a `design_*` tool the live service
does not expose. An invented tool name in a reference file is worse than a
missing one, because the routing rules send a designer straight to that file
and the name reads as authoritative. Run it against the environment you are
releasing for.

## Packaging

The skill is authored inside the platform repository and installed elsewhere,
so a release is a package build, not a flag flip on the working copy:

```bash
python scripts/package_skill.py
```

It copies the shipped surface into `workspace/dist/`, seals that copy at
`released`, and zips it. The repository copy stays in `design` and stays
writable.

`.env` and `.session.json` belong to one checkout and never enter a package.
The build re-reads the packaged tree afterwards and discards it if either name
appears, so an exclusion rule that stops matching fails the build instead of
shipping a credential.

## Adding a script

A script under `scripts/` is part of the skill contract. It must be portable
across MCP clients, must not hold credentials, must not add a write path that
bypasses `design_prepare_*` / `design_commit_*`, and must be named in
`SKILL.md`. Promote a `workspace/` script only once it has proven reusable.

## Adding a tool to the reference

When the Design MCP gains a tool, update the table in
[the Design MCP contract](design-mcp-contract.md) with its access level and
what it affects, and state whether a committed change is staged behind a draft
or reaches live conversations immediately. A mutating tool also needs its
authorization, required confirmation, affected identities, and audit result
recorded there before this skill uses it.
