"""The house CLI: config, preflight and seeding, with docker and Babelr faked."""
import importlib.machinery
import importlib.util
import subprocess
from pathlib import Path

import pytest

_path = str(Path(__file__).resolve().parent.parent / "house")
_loader = importlib.machinery.SourceFileLoader("house_cli", _path)
_spec = importlib.util.spec_from_loader("house_cli", _loader)
H = importlib.util.module_from_spec(_spec)
_loader.exec_module(H)

ENV = {"ANTHROPIC_API_KEY": "sk-ant-x", "HOUSE_DAEMON_NAME": "Wren", "HOUSE_OWNER": "sam"}


def test_a_new_daemon_cant_take_a_house_members_name():
    for taken in ("Cass", "cass", "RoboKohl", "Daedalus", "Kohl"):
        assert "its own name" in H.check_daemon_name(taken)
    assert H.check_daemon_name("Wren") is None
    assert H.check_daemon_name("x") and H.check_daemon_name("")


def test_config_asks_only_for_what_is_missing_and_keeps_secrets(monkeypatch):
    monkeypatch.setattr(H, "ask", lambda *a, **k: pytest.fail("asked"))
    v = H.gather_config({}, env=ENV)
    assert (v["DAEMON_NAME"], v["DAEMON_LABEL"], v["OWNER_USERNAME"]) == ("Wren", "wren", "sam")
    assert len(v["OWNER_PASSWORD"]) >= 12 and v["SESSION_SECRET"] != v["JWT_SECRET_KEY"]
    again = H.gather_config(v, env={})
    assert again == v  # a second `up` changes nothing


def test_config_refuses_a_bad_key_and_cass(monkeypatch):
    with pytest.raises(SystemExit, match="Anthropic API key"):
        H.gather_config({}, env={**ENV, "ANTHROPIC_API_KEY": "nope"})
    with pytest.raises(SystemExit, match="its own name"):
        H.gather_config({}, env={**ENV, "HOUSE_DAEMON_NAME": "Cass"})


def test_env_file_is_private(tmp_path):
    p = tmp_path / "house.env"
    H.write_env({"A": "1"}, p)
    assert p.stat().st_mode & 0o077 == 0 and H.read_env(p) == {"A": "1"}


def _run(results):
    def run(cmd, **kw):
        key = " ".join(cmd[:3])
        rc, err = results.get(key, (0, ""))
        return subprocess.CompletedProcess(cmd, rc, stdout="", stderr=err)
    return run


def test_preflight_names_each_problem_in_plain_words(monkeypatch):
    v = H.gather_config({}, env=ENV)
    monkeypatch.setattr(H, "_port_taken", lambda p: p == 3000)
    got = H.preflight(v, run=_run({"docker info": (1, "permission denied while trying to connect")}),
                      which=lambda n: "/usr/bin/" + n)
    assert any("docker group" in p for p in got)
    assert any("Port 3000 is taken" in p and "BABELR_PORT" in p for p in got)
    monkeypatch.setattr(H, "_port_taken", lambda p: False)
    got = H.preflight(v, run=_run({}), which=lambda n: None if n == "docker" else "/x")
    assert got == ["docker isn't installed (https://docs.docker.com/engine/install/)."]


class FakeBabelr:
    def __init__(self):
        self.calls, self.users, self.servers, self.agents = [], {}, [], []

    def call(self, method, path, body=None, token=None, ok=None):
        self.calls.append((method, path))
        if path == "/auth/register":
            if body["username"] in self.users:
                return 409, {"error": "Username already taken"}
            self.users[body["username"]] = body
            return 201, {"id": "u1"}
        if path == "/auth/login":
            return (200, {}) if any(u["password"] == body["password"] for u in self.users.values()) \
                else (401, {"error": "bad"})
        if path == "/auth/me":
            return 200, {"id": "u1"}
        if path == "/servers":
            if method == "GET":
                return 200, self.servers
            self.servers.append({"id": "s1", "name": body["name"]})
            return 201, {"id": "s1"}
        if path == "/agents":
            if method == "GET":
                return 200, self.agents
            self.agents.append({"id": "a1", "preferredUsername": body["username"]})
            assert body["username"] == "wren" and body["displayName"] == "Wren"
            return 201, {"id": "a1"}
        if path == "/servers/s1/agents":
            return 201, {}
        if path == "/agents/a1/tokens":
            assert "dms:read" in body["scopes"] and "channels:post" in body["scopes"]
            return 201, {"token": "tok-secret"}
        raise AssertionError(path)


def test_seed_makes_owner_server_agent_and_token_once():
    v = H.gather_config({}, env=ENV)
    api, placed = FakeBabelr(), []
    state = H.seed(v, {}, api, lambda tok, owner: placed.append((tok, owner)))
    assert placed == [("tok-secret", "sam")]
    assert state["server_id"] == "s1" and state["agent_id"] == "a1" and state["token_placed"]
    n = len(api.calls)
    state = H.seed(v, state, api, lambda *a: pytest.fail("token minted twice"))
    assert ("POST", "/agents") not in api.calls[n:] and ("POST", "/servers") not in api.calls[n:]


def test_seed_explains_a_changed_password():
    v = H.gather_config({}, env=ENV)
    api = FakeBabelr()
    api.users["sam"] = {"password": "something else"}
    with pytest.raises(SystemExit, match="OWNER_PASSWORD"):
        H.seed(v, {}, api, lambda *a: None)
