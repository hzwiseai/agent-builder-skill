# workspace

Everything produced while *using* this skill lives here: assets pulled with
`design_asset_file.py --pull`, the edited copies pushed back, exported
evidence, and one-off analysis scripts written for a single investigation.

The whole directory is gitignored except this file. Nothing here is part of the
skill, nothing here is portable, and nothing here should be relied on by a
later run.

Two rules that are not about tidiness:

1. **No write path may bypass the MCP confirmation protocol.** A script here
   may read freely, but every draft save, publish, Agent change, and reply-item
   change goes through `design_prepare_*` then `design_commit_*` with the user's
   explicit confirmation in between. A script that calls a REST write endpoint
   with the session's credential is not a shortcut; it removes the diff the user
   was supposed to approve.
2. **No credentials, no customer text, no session ids** in files here. `.env`
   and `.session.json` stay in the skill root and stay out of prompts, logs,
   and generated files.

Never edit a file in `scripts/` or `references/` to make a run work, even while
the skill is still in its design stage and nothing stops you. A run that edits a
helper breaks every later session, and once the skill is released the same edit
fails the hash check outright. Put the workaround here and say what the shipped
script should do differently.

If a script here earns its third use, promote it to `scripts/`: give it a
docstring saying what it does not do, keep it credential-free, and name it in
SKILL.md. Otherwise let it be thrown away with the investigation.
