#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Keep the house's members on the vessel's latest main.

Kohl, 2026-11-26: Cass runs the vessel from a checkout, the members (Eris) from
src/vessel in docker, and the members kept falling behind. This brings them along:

    vessel_follow.py            fetch main; if it moved, update src/vessel and rebuild each member
    vessel_follow.py --dry-run  say what it would do
    vessel_follow.py --migrate  the same, and go ahead when main changes the database schema

A change that bumps SCHEMA_VERSION migrates a daughter's database when she restarts, and
that needs Kohl's yes. So it waits instead: src/vessel stays where it is, and it says so
once (in #workshop, if daedalus-house is here) until Kohl runs it with --migrate.

src/vessel is a read-only clone nobody works in. If it has local changes anyway, nothing
is touched and it says why.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HOUSE = Path(__file__).resolve().parent.parent
VESSEL = HOUSE / "src" / "vessel"
MEMBERS = HOUSE / "members"
STATE = HOUSE / ".vessel-follow.json"
SCHEMA = "backend/database/schema.py"


def _git(*args: str, run=subprocess.run) -> subprocess.CompletedProcess:
    return run(["git", "-C", str(VESSEL), *args], capture_output=True, text=True)


def schema_version(rev: str, run=subprocess.run) -> int | None:
    r = _git("show", f"{rev}:{SCHEMA}", run=run)
    m = re.search(r"^SCHEMA_VERSION\s*=\s*(\d+)", r.stdout, re.M) if r.returncode == 0 else None
    return int(m.group(1)) if m else None


def members() -> list[str]:
    """Slugs with a member.env (only its existence is read here, never its contents)."""
    return sorted(p.parent.name for p in MEMBERS.glob("*/member.env")) if MEMBERS.is_dir() else []


def _state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def _say(text: str, post=True) -> None:
    print(text)
    tool = shutil.which("daedalus-house")
    if post and tool:
        subprocess.run([tool, "post", text], capture_output=True, text=True, timeout=60)


def follow(dry_run: bool = False, migrate: bool = False, run=subprocess.run,
           rebuild=None, say=_say) -> dict:
    rebuild = rebuild or (lambda slug: run([str(HOUSE / "house"), "member", "up", slug], cwd=HOUSE))
    if _git("status", "--porcelain", run=run).stdout.strip():
        return {"stopped": "src/vessel has local changes; left as it is"}
    if _git("fetch", "-q", "--depth", "1", "origin", "main", run=run).returncode != 0:
        return {"stopped": "couldn't fetch the vessel's main"}
    head = _git("rev-parse", "HEAD", run=run).stdout.strip()
    new = _git("rev-parse", "origin/main", run=run).stdout.strip()
    if not new or head == new:
        return {"current": head[:8]}
    old_v, new_v = schema_version("HEAD", run), schema_version("origin/main", run)
    out = {"from": head[:8], "to": new[:8], "schema": [old_v, new_v], "members": members()}
    if old_v != new_v and not migrate:
        out["held"] = "schema changes: waiting for Kohl"
        st = _state()
        if not dry_run and st.get("asked_about") != new:
            say(f"@kohl The vessel's main ({new[:8]}) moves the database schema from v{old_v} to v{new_v}, "
                f"so the house members ({', '.join(out['members']) or 'none'}) stay on {head[:8]} for now. "
                "Restarting them on it migrates their databases. When you're ready: "
                "~/house/tools/vessel_follow.py --migrate")
            STATE.write_text(json.dumps({**st, "asked_about": new}))
        return out
    if dry_run:
        out["would_rebuild"] = out["members"]
        return out
    if _git("reset", "-q", "--hard", "origin/main", run=run).returncode != 0:
        return {**out, "stopped": "couldn't move src/vessel to main"}
    out["rebuilt"], out["failed"] = [], []
    for slug in out["members"]:
        r = rebuild(slug)
        (out["rebuilt"] if getattr(r, "returncode", 0) == 0 else out["failed"]).append(slug)
    if out["failed"]:
        say(f"Rebuilding {', '.join(out['failed'])} on the vessel's {new[:8]} failed; "
            "`./house logs vessel` in ~/house says why.")
    STATE.write_text(json.dumps({**_state(), "on": new}))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--migrate", action="store_true", help="Kohl's yes to a schema change")
    a = ap.parse_args(argv)
    rep = follow(dry_run=a.dry_run, migrate=a.migrate)
    print(json.dumps(rep, indent=1))
    return 1 if rep.get("failed") or rep.get("stopped") else 0


if __name__ == "__main__":
    sys.exit(main())
