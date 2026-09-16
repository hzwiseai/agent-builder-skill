#!/usr/bin/env python3
"""Build a distributable copy of this skill from the working repository.

The skill is authored inside the WorkTool repository but installed elsewhere,
so packaging is where the two diverge: the repository copy stays writable and
in its ``design`` stage, while the package is sealed at ``released``.

Local configuration is left behind by construction: ``.env`` holds real
production credentials and ``.session.json`` holds a live Design session, and
both belong to one checkout.  The build then re-reads the packaged tree and
discards it if either name is present anyway, so an exclusion rule that stops
matching fails the build instead of shipping a credential.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

SKILL_ROOT = Path(__file__).resolve().parents[1]
SKILL_NAME = SKILL_ROOT.name
# Present in a working checkout, never in a package.
NEVER_DISTRIBUTE = (".env", ".session.json")
DROPPED_NAMES = {".git", ".venv", "venv", "__pycache__", ".DS_Store", ".pytest_cache"}


# WorkBuddy 只接受 SKILL.md 位于 ZIP 根，且路径最多两层。
WORKBUDDY_MAX_DEPTH = 2


def declared_version() -> str:
    """VERSION 是版本的唯一来源；SKILL.md 里的 version 必须与它一致。

    两处都要有：VERSION 供人和 CI 读取，frontmatter 供 marketplace 解析。
    本 skill 有完整性封存，无法在打包时注入 frontmatter，因此只能靠断言防漂移。
    """
    version = (SKILL_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    frontmatter = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8").split("---", 2)[1]
    declared = next(
        (line.split(":", 1)[1].strip().strip('"') for line in frontmatter.splitlines()
         if line.strip().startswith("version:")),
        None,
    )
    if declared != version:
        raise ValueError(f"VERSION({version}) 与 SKILL.md frontmatter({declared}) 不一致")
    return version


def _fail(message: str, **extra: object) -> int:
    print(json.dumps({"status": "error", "message": message, **extra}, ensure_ascii=False, indent=2), file=sys.stderr)
    return 1


def staged_paths() -> list[Path]:
    """Return only the files that belong to every installation of the skill."""

    shipped: list[Path] = []
    for path in sorted(SKILL_ROOT.rglob("*")):
        relative = path.relative_to(SKILL_ROOT)
        if any(part in DROPPED_NAMES or part.endswith(".pyc") for part in relative.parts):
            continue
        if relative.name in NEVER_DISTRIBUTE:
            continue
        # workspace/ holds one run's artifacts; only its rules travel. Matching
        # the exact path matters: an earlier build lives at
        # workspace/dist/<skill>/workspace/README.md and would otherwise be
        # packaged again, nesting one build inside the next.
        if relative.parts[0] == "workspace" and relative != Path("workspace/README.md"):
            continue
        if path.is_file():
            shipped.append(path)
    return shipped


def build(destination: Path, archive: bool, workbuddy: bool = False) -> int:
    try:
        version = declared_version()
    except (OSError, ValueError) as exc:
        return _fail(f"版本校验失败: {exc}")
    shipped = staged_paths()
    if destination.exists():
        shutil.rmtree(destination)
    for path in shipped:
        target = destination / path.relative_to(SKILL_ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)

    sealed = subprocess.run(
        [sys.executable, str(destination / "scripts" / "_integrity.py"), "--release"],
        capture_output=True, text=True, check=False,
    )
    if sealed.returncode != 0:
        return _fail("could not seal the packaged skill", detail=sealed.stderr.strip()[:800])

    leaked = [
        str(path.relative_to(destination)) for path in destination.rglob("*")
        if path.is_file() and path.name in NEVER_DISTRIBUTE
    ]
    if leaked:
        shutil.rmtree(destination)
        return _fail("packaged tree contained local configuration; build discarded", leaked=leaked)

    result: dict[str, object] = {
        "status": "packaged",
        "skill": SKILL_NAME,
        "directory": str(destination),
        "file_count": sum(1 for path in destination.rglob("*") if path.is_file()),
        "stage": json.loads((destination / "scripts" / "integrity.json").read_text(encoding="utf-8"))["stage"],
        "version": version,
        "layout": "workbuddy" if workbuddy else "standard",
    }
    if archive:
        bundle = destination.with_suffix(".zip")
        bundle.unlink(missing_ok=True)
        with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as handle:
            for path in sorted(destination.rglob("*")):
                if not path.is_file():
                    continue
                relative = path.relative_to(destination)
                name = relative if workbuddy else Path(SKILL_NAME) / relative
                if workbuddy and len(name.parts) > WORKBUDDY_MAX_DEPTH:
                    bundle.unlink(missing_ok=True)
                    return _fail("WorkBuddy 目录层级超限，包已丢弃", path=str(name),
                                 max_depth=WORKBUDDY_MAX_DEPTH)
                handle.write(path, name)
        result["archive"] = str(bundle)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Package this skill for distribution, sealed and credential-free.")
    parser.add_argument("--out", type=Path, default=SKILL_ROOT / "workspace" / "dist" / SKILL_NAME,
                        help="Staging directory for the packaged skill.")
    parser.add_argument("--no-archive", action="store_true", help="Leave the packaged tree without zipping it.")
    parser.add_argument("--workbuddy", action="store_true",
                        help="Flatten the ZIP to root + one directory level for WorkBuddy.")
    args = parser.parse_args()
    return build(args.out.resolve(), not args.no_archive, workbuddy=args.workbuddy)


if __name__ == "__main__":
    raise SystemExit(main())
