#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""The house's copy of Kohl's work: one clean clone per repo, in one place.

Kohl, 2026-11-24: "a copy of all of our repos in the workspace … so the external
agents and even the daemons/agents can easily access the codebase for analysis
from one spot instead of hunting around my mess of a directory tree."

    house_repos.py sync [--dry-run]   clone what's new, bring the rest up to date
    house_repos.py list               what's in it

Each clone sits at <dir>/<repo> on its default branch, exactly as GitHub has it:
pushed work only, never a live checkout, so no local data, .env or databases. They're
read-only copies for reading. Nobody works in them, so each sync resets them to the
remote (fetch, hard reset, clean).

Which repos (KohlJary on GitHub, via `gh`):
  - every repo that isn't a fork, plus forks pushed in the last FORK_DAYS days
    (gpu-broker, say; not a 2022 fork of someone else's emulator);
  - public ones only, unless named in "private" in the config. A private repo here
    is read by the guests (ChatGPT, Gemini, Claude.ai), which means sending it to
    their companies. That's Kohl's call, repo by repo;
  - nothing named in "exclude", and nothing over MAX_MB unless it's named in "private"
    or "include".

Config (optional), HOUSE_REPOS_CONFIG or <house>/house-repos.json:
  {"owner": "KohlJary", "dir": "~/house/repos", "private": [], "include": [],
   "exclude": [], "fork_days": 365, "max_mb": 150}

<dir>/.index.json records what's there (name, description, branch, last push), and
it's what the connector's list_repos reads.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOUSE = Path(__file__).resolve().parent.parent
DEFAULTS = {"owner": "KohlJary", "dir": "~/house/repos", "private": [], "include": [],
            "exclude": [], "fork_days": 365, "max_mb": 150}
GH_FIELDS = "name,visibility,isFork,isArchived,diskUsage,pushedAt,description,defaultBranchRef,url"
# Private clones authenticate through gh's own credentials; nothing is written to disk.
GIT = ["git", "-c", "credential.helper=", "-c", "credential.helper=!gh auth git-credential"]


def config() -> dict:
    p = Path(os.environ.get("HOUSE_REPOS_CONFIG") or HOUSE / "house-repos.json")
    c = dict(DEFAULTS)
    if p.exists():
        c.update(json.loads(p.read_text()))
    c["dir"] = Path(os.path.expanduser(c["dir"]))
    return c


def chosen(repos: list[dict], c: dict, now: datetime | None = None) -> list[dict]:
    """The repos the house keeps a copy of, by the rules in the module docstring."""
    now = now or datetime.now(timezone.utc)
    private, include, exclude = set(c["private"]), set(c["include"]), set(c["exclude"])
    out = []
    for r in repos:
        name = r["name"]
        if name in exclude or r.get("isArchived"):
            continue
        if r.get("visibility", "").upper() != "PUBLIC" and name not in private:
            continue
        if r.get("isFork") and name not in include and name not in private:
            pushed = datetime.fromisoformat(r["pushedAt"].replace("Z", "+00:00"))
            if now - pushed > timedelta(days=c["fork_days"]):
                continue
        if (r.get("diskUsage") or 0) > c["max_mb"] * 1024 and name not in include | private:
            continue
        out.append(r)
    return sorted(out, key=lambda r: r["name"].lower())


def github(owner: str, run=subprocess.run) -> list[dict]:
    r = run(["gh", "repo", "list", owner, "-L", "500", "--json", GH_FIELDS],
            capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def _git(*args: str, run=subprocess.run) -> subprocess.CompletedProcess:
    return run([*GIT, *args], capture_output=True, text=True)


def sync(c: dict, dry_run: bool = False, run=subprocess.run, repos: list[dict] | None = None) -> dict:
    keep = chosen(repos if repos is not None else github(c["owner"], run), c)
    d = c["dir"]
    index_path = d / ".index.json"
    try:
        before = {r["name"] for r in json.loads(index_path.read_text())["repos"]}
    except (OSError, ValueError, KeyError):
        before = set()
    report = {"cloned": [], "updated": [], "removed": [], "failed": []}
    if dry_run:
        report["would_keep"] = [r["name"] for r in keep]
        report["would_remove"] = sorted(before - {r["name"] for r in keep})
        return report
    d.mkdir(parents=True, exist_ok=True)
    index = []
    for r in keep:
        name, branch = r["name"], (r.get("defaultBranchRef") or {}).get("name") or "main"
        dest = d / name
        if not (dest / ".git").exists():
            res = _git("clone", "-q", "--single-branch", "-b", branch, r["url"], str(dest), run=run)
            (report["cloned"] if res.returncode == 0 else report["failed"]).append(name)
        else:
            ok = True
            for step in (["fetch", "-q", "--prune", "origin", branch],
                         ["checkout", "-q", "-f", "-B", branch, f"origin/{branch}"],
                         ["clean", "-qfdx"]):
                if _git("-C", str(dest), *step, run=run).returncode != 0:
                    ok = False
                    break
            (report["updated"] if ok else report["failed"]).append(name)
        if (dest / ".git").exists():
            index.append({"name": name, "description": r.get("description") or "", "branch": branch,
                          "pushed": r.get("pushedAt"), "private": r.get("visibility", "").upper() != "PUBLIC"})
    # Only remove what this tool put here (it's in the old index), never anything else.
    for name in sorted(before - {r["name"] for r in keep}):
        target = d / name
        if target.is_dir() and target.parent == d:
            shutil.rmtree(target)
            report["removed"].append(name)
    tmp = index_path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"synced": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                               "repos": index}, indent=1))
    os.replace(tmp, index_path)
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sync")
    s.add_argument("--dry-run", action="store_true")
    sub.add_parser("list")
    a = ap.parse_args(argv)
    c = config()
    if a.cmd == "list":
        try:
            idx = json.loads((c["dir"] / ".index.json").read_text())
        except OSError:
            print("Nothing synced yet: run sync.")
            return 1
        print(f"{len(idx['repos'])} repos in {c['dir']}, synced {idx['synced']}")
        for r in idx["repos"]:
            print(f"  {r['name']:<28} {'(private) ' if r['private'] else ''}{r['description'][:70]}")
        return 0
    rep = sync(c, dry_run=a.dry_run)
    print(json.dumps(rep, indent=1))
    return 1 if rep["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
