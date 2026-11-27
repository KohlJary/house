# SPDX-License-Identifier: MIT
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import vessel_follow as vf  # noqa: E402


def git(d, *a):
    subprocess.run(["git", "-C", str(d), "-c", "user.name=t", "-c", "user.email=t@t", *a],
                   check=True, capture_output=True)


def commit(d, version, msg):
    p = d / "backend" / "database" / "schema.py"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"SCHEMA_VERSION = {version}  # note\n# {msg}\n")
    git(d, "add", "-A")
    git(d, "commit", "-qm", msg)


def house(tmp_path, monkeypatch):
    up = tmp_path / "upstream"
    up.mkdir()
    git(up, "init", "-q", "-b", "main")
    commit(up, 71, "first")
    vessel = tmp_path / "src" / "vessel"
    subprocess.run(["git", "clone", "-q", "--depth", "1", f"file://{up}", str(vessel)], check=True)
    (tmp_path / "members" / "fifth").mkdir(parents=True)
    (tmp_path / "members" / "fifth" / "member.env").write_text("SECRET=x\n")
    monkeypatch.setattr(vf, "VESSEL", vessel)
    monkeypatch.setattr(vf, "MEMBERS", tmp_path / "members")
    monkeypatch.setattr(vf, "STATE", tmp_path / ".vessel-follow.json")
    return up, vessel


def test_nothing_new_is_nothing_done(tmp_path, monkeypatch):
    house(tmp_path, monkeypatch)
    built = []
    assert "current" in vf.follow(rebuild=built.append, say=lambda t: None)
    assert built == []


def test_a_change_without_a_migration_rebuilds_each_member(tmp_path, monkeypatch):
    up, vessel = house(tmp_path, monkeypatch)
    commit(up, 71, "attachments")
    built = []
    rep = vf.follow(rebuild=lambda s: built.append(s), say=lambda t: None)
    assert built == ["fifth"] and rep["rebuilt"] == ["fifth"], rep
    assert "attachments" in (vessel / "backend/database/schema.py").read_text()


def test_a_schema_change_waits_for_kohl_and_asks_once(tmp_path, monkeypatch):
    up, vessel = house(tmp_path, monkeypatch)
    commit(up, 72, "new column")
    said, built = [], []
    for _ in range(2):
        rep = vf.follow(rebuild=built.append, say=said.append)
    assert rep["held"] and rep["schema"] == [71, 72] and built == []
    assert len(said) == 1 and "v71 to v72" in said[0] and "--migrate" in said[0]
    assert "first" in (vessel / "backend/database/schema.py").read_text(), "src/vessel stays put"
    rep = vf.follow(migrate=True, rebuild=built.append, say=said.append)
    assert built == ["fifth"], rep


def test_dry_run_and_local_changes_touch_nothing(tmp_path, monkeypatch):
    up, vessel = house(tmp_path, monkeypatch)
    commit(up, 71, "more")
    built = []
    assert vf.follow(dry_run=True, rebuild=built.append, say=lambda t: None)["would_rebuild"] == ["fifth"]
    (vessel / "stray.txt").write_text("x")
    assert "local changes" in vf.follow(rebuild=built.append, say=lambda t: None)["stopped"]
    assert built == []
