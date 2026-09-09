"""Detect drift in the skill's shipped files before any script uses them.

A released skill fails quietly and expensively when a shipped script is edited
during a run: a helper loses its confirmation step, a later session inherits
the edit, and nobody can say which version produced which change.  This module
hashes the shipped surface, compares it to ``integrity.json``, and refuses to
run on a mismatch.

The lock belongs to the released skill, not to the one being written.  While
``stage`` is ``design`` the shipped files are expected to change every hour, so
verification reports drift but never blocks; ``--release`` records the hashes,
flips the stage, and sets the read-only bit in one step.

It is a drift detector, not a sandbox.  Anything that can edit a script can
also edit this file.  Its job is to make a change loud, attributable, and
deliberate rather than silent.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

SKILL_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = SKILL_ROOT / "scripts" / "integrity.json"
# The shipped surface: identical for every user of the skill. Run artifacts in
# workspace/ and local configuration are deliberately excluded.
SHIPPED_GLOBS = ("SKILL.md", "VERSION", "mcp.json", ".env.example", "references/*.md", "scripts/*.py", "workspace/README.md")
DESIGN_STAGE = "design"
RELEASED_STAGE = "released"


class SkillIntegrityError(RuntimeError):
    pass


def shipped_files() -> list[Path]:
    found: list[Path] = []
    for pattern in SHIPPED_GLOBS:
        found.extend(path for path in sorted(SKILL_ROOT.glob(pattern)) if path.is_file())
    return [path for path in found if path != MANIFEST]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def current_manifest() -> dict[str, str]:
    return {str(path.relative_to(SKILL_ROOT)): digest(path) for path in shipped_files()}


def _stored() -> dict[str, object]:
    try:
        stored = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SkillIntegrityError(f"cannot read {MANIFEST.name}: {exc}") from exc
    if not isinstance(stored, dict):
        raise SkillIntegrityError(f"{MANIFEST.name} is not an object")
    return stored


def stage() -> str:
    """Return the recorded lifecycle stage, defaulting to an unlocked skill."""

    try:
        recorded = str(_stored().get("stage") or DESIGN_STAGE)
    except SkillIntegrityError:
        return DESIGN_STAGE
    return recorded if recorded in {DESIGN_STAGE, RELEASED_STAGE} else DESIGN_STAGE


def recorded_manifest() -> dict[str, str]:
    files = _stored().get("files")
    if not isinstance(files, dict):
        raise SkillIntegrityError(f"{MANIFEST.name} has no files map")
    return {str(key): str(value) for key, value in files.items()}


def differences() -> dict[str, list[str]]:
    current, recorded = current_manifest(), recorded_manifest()
    return {
        "modified": sorted(key for key in current.keys() & recorded.keys() if current[key] != recorded[key]),
        "added": sorted(current.keys() - recorded.keys()),
        "removed": sorted(recorded.keys() - current.keys()),
    }


def verify() -> None:
    """Raise when the shipped surface no longer matches the recorded manifest."""

    drift = differences()
    if not any(drift.values()):
        return
    detail = "; ".join(f"{name}: {', '.join(paths)}" for name, paths in drift.items() if paths)
    raise SkillIntegrityError(
        f"wisecopilot shipped files changed ({detail}). "
        "Restore them from version control, or, if the change was intended, "
        "review it and run: python scripts/_integrity.py --bless"
    )


def enforce() -> None:
    """Fail closed at script start once the skill is released.

    A skill still being designed changes constantly and by intent, so locking it
    would only teach whoever is authoring it to route around the check.
    """

    if stage() != RELEASED_STAGE:
        return
    try:
        verify()
    except SkillIntegrityError as exc:
        print(json.dumps({"status": "error", "code": "skill_integrity_failed", "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)


def protect(read_only: bool) -> list[str]:
    """Set or clear the read-only bit on every shipped file."""

    changed: list[str] = []
    for path in shipped_files() + ([MANIFEST] if MANIFEST.exists() else []):
        mode = 0o444 if read_only else 0o644
        if path.stat().st_mode & 0o777 != mode:
            path.chmod(mode)
            changed.append(str(path.relative_to(SKILL_ROOT)))
    return changed


def bless(next_stage: str | None = None) -> dict[str, str]:
    files = current_manifest()
    if MANIFEST.exists():
        MANIFEST.chmod(0o644)
    MANIFEST.write_text(
        json.dumps({
            "note": "sha256 of the skill's shipped files; regenerate only after reviewing a deliberate change.",
            "stage": next_stage or stage(),
            "files": files,
        }, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return files


def main() -> int:
    argument = sys.argv[1] if len(sys.argv) > 1 else "--verify"
    if argument == "--bless":
        files = bless()
        print(json.dumps({"status": "blessed", "stage": stage(), "file_count": len(files)}, ensure_ascii=False, indent=2))
        return 0
    if argument == "--release":
        # One deliberate step: record what is being released, then lock it.
        files = bless(RELEASED_STAGE)
        changed = protect(True)
        print(json.dumps({"status": "released", "stage": stage(), "file_count": len(files), "locked": changed}, ensure_ascii=False, indent=2))
        return 0
    if argument == "--reopen":
        bless(DESIGN_STAGE)
        changed = protect(False)
        print(json.dumps({"status": "reopened", "stage": stage(), "unlocked": changed}, ensure_ascii=False, indent=2))
        return 0
    if argument in {"--protect", "--unprotect"}:
        changed = protect(argument == "--protect")
        print(json.dumps({"status": argument.lstrip("-"), "stage": stage(), "changed": changed}, ensure_ascii=False, indent=2))
        return 0
    if argument != "--verify":
        print(json.dumps({"status": "error", "message": "use --verify, --bless, --release, --reopen, --protect or --unprotect"}, ensure_ascii=False), file=sys.stderr)
        return 1
    current_stage = stage()
    try:
        verify()
    except SkillIntegrityError as exc:
        enforced = current_stage == RELEASED_STAGE
        print(json.dumps({
            "status": "drifted", "stage": current_stage, "enforced": enforced,
            "message": str(exc) if enforced else "Shipped files differ from the recorded hashes. The skill is still in design, so scripts keep running; run --bless to record the current state.",
            "differences": differences(),
        }, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2 if enforced else 0
    print(json.dumps({"status": "intact", "stage": current_stage, "file_count": len(current_manifest())}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
