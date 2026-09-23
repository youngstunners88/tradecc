"""Does every advertised entry point exist, and does anything call it?

Failure #1 from the Hydra paper run, as a check. `package.json` advertised
`hunt`, `promote`, `replay` and `smoke`; none of those four files existed. The
gate was blamed for weeks. The manifest described a system that had never run.

This is a reconciliation in the sense of `reconcile.py`: an authoritative list
(what the manifest promises) diffed against reality (what is on disk). The
failure is an ABSENCE, so nothing reports it on its own.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

__all__ = ["EntryPoint", "scripts_from_package_json", "missing_entrypoints", "check"]

# Pull the file out of a script command: `tsx scripts/x.ts --flag` -> scripts/x.ts
_FILE = re.compile(r"(?<![\w/.-])((?:[\w.*-]+/)*[\w.*-]+\.(?:ts|js|mjs|py|sh))")


@dataclass(frozen=True)
class EntryPoint:
    name: str
    command: str
    file: str | None

    @property
    def advertised(self) -> bool:
        return self.file is not None


def scripts_from_package_json(path: Path) -> list[EntryPoint]:
    data = json.loads(Path(path).read_text())
    out: list[EntryPoint] = []
    for name, command in (data.get("scripts") or {}).items():
        m = _FILE.search(command)
        out.append(EntryPoint(name=name, command=command, file=m.group(1) if m else None))
    return out


def missing_entrypoints(entries: list[EntryPoint], root: Path) -> list[EntryPoint]:
    """Advertised entry points whose file is not on disk.

    A glob is NOT a missing file. `node --test packages/*/tests/*.test.ts`
    names a pattern, not a path, and reporting it as absent would make this
    check cry wolf on a healthy repo -- which is how a checker gets ignored,
    and an ignored checker is the same as no checker.

    A glob that matches NOTHING is a real failure, and it is the one the CI
    workflow's own "fail if no tests were found" step already guards, so it is
    deliberately left there rather than duplicated here.
    """
    out: list[EntryPoint] = []
    for e in entries:
        if not e.advertised:
            continue
        file = str(e.file)
        if "*" in file:
            if not list(root.glob(file)):
                out.append(e)
            continue
        if not (root / file).exists():
            out.append(e)
    return out


def check(package_json: Path, root: Path | None = None) -> tuple[bool, str]:
    """(ok, report). Not ok when the manifest promises something absent."""
    package_json = Path(package_json)
    root = Path(root) if root is not None else package_json.parent
    entries = scripts_from_package_json(package_json)
    if not entries:
        # Vacuous, and vacuous is never a pass -- same rule as reconcile.py.
        return False, (
            "VACUOUS: no scripts declared, so this check proves nothing. "
            "Verify you are reading the right manifest."
        )
    gone = missing_entrypoints(entries, root)
    if not gone:
        named = sum(1 for e in entries if e.advertised)
        return True, f"OK: {named} advertised entry point(s), all present."
    lines = [f"MISSING ({len(gone)}): the manifest advertises files that do not exist."]
    for e in gone:
        lines.append(f"  {e.name}: {e.command}   -> {e.file} NOT FOUND")
    lines.append(
        "An advertised script with no file is why a validation clock reads "
        "zero while every library passes its tests."
    )
    return False, "\n".join(lines)
