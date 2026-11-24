# SPDX-License-Identifier: MIT
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import house_repos as hr  # noqa: E402

NOW = datetime(2026, 11, 24, tzinfo=timezone.utc)


def repo(name, vis="PUBLIC", fork=False, pushed="2026-11-01T00:00:00Z", kb=100, **k):
    return {"name": name, "visibility": vis, "isFork": fork, "pushedAt": pushed, "diskUsage": kb,
            "url": f"https://github.com/KohlJary/{name}", "defaultBranchRef": {"name": "main"}, **k}


def cfg(tmp_path, **over):
    c = dict(hr.DEFAULTS, dir=tmp_path / "repos")
    c.update(over)
    return c


def test_public_work_and_active_forks_are_kept_private_only_by_name(tmp_path):
    repos = [repo("babelr"), repo("robokohl", vis="PRIVATE"), repo("Chapter-House", vis="PRIVATE"),
             repo("gpu-broker", fork=True), repo("RetroArch", fork=True, pushed="2024-04-02T00:00:00Z"),
             repo("old", isArchived=True), repo("huge", kb=500 * 1024), repo("skipme")]
    got = [r["name"] for r in hr.chosen(repos, cfg(tmp_path, private=["Chapter-House"], exclude=["skipme"]), NOW)]
    assert got == ["babelr", "Chapter-House", "gpu-broker"]


def _origin(tmp_path, name):
    src = tmp_path / "gh" / name
    subprocess.run(["git", "init", "-q", "-b", "main", str(src)], check=True)
    (src / "README.md").write_text("one\n")
    for args in (["add", "."], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "one"]):
        subprocess.run(["git", "-C", str(src), *args], check=True)
    return src


def test_sync_clones_resets_local_changes_and_removes_only_its_own(tmp_path):
    src = _origin(tmp_path, "babelr")
    r = repo("babelr", description="chat")
    r["url"] = str(src)
    c = cfg(tmp_path)
    assert hr.sync(c, repos=[r])["cloned"] == ["babelr"]
    clone = c["dir"] / "babelr"
    (clone / "README.md").write_text("scribbled\n")
    (clone / "stray.txt").write_text("x")
    (src / "README.md").write_text("two\n")
    subprocess.run(["git", "-C", str(src), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "two"], check=True)
    assert hr.sync(c, repos=[r])["updated"] == ["babelr"]
    assert (clone / "README.md").read_text() == "two\n" and not (clone / "stray.txt").exists()
    idx = json.loads((c["dir"] / ".index.json").read_text())
    assert idx["repos"][0]["name"] == "babelr" and idx["repos"][0]["description"] == "chat"
    (c["dir"] / "not-ours").mkdir()
    assert hr.sync(c, repos=[])["removed"] == ["babelr"]
    assert (c["dir"] / "not-ours").exists() and not clone.exists()
