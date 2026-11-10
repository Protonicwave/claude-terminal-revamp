import json
from pathlib import Path

import pytest

from installer.merge import Change
from installer.model import InstallerError
from installer.state import (
    PluginRecord,
    ProfileRecord,
    State,
    dump_state,
    parse_state,
    read_state,
)

FULL_STATE = State(
    vscode=(Change(("a", "b"), 1, False, 2),),
    claude=(Change(("c",), None, True, {"d": [1]}),),
    themes={"claude-warm.json": "abc123"},
    previous_execution_policy="Undefined",
    profile=ProfileRecord("C:/profile.ps1", True, False),
    plugin=PluginRecord(marketplace_added=True, installed=False),
)


def valid() -> dict:
    return json.loads(dump_state(FULL_STATE))


def test_state_round_trips() -> None:
    assert parse_state(dump_state(FULL_STATE), "state") == FULL_STATE


def test_empty_state_round_trips() -> None:
    assert parse_state(dump_state(State()), "state") == State()


def test_read_state_returns_none_when_the_file_is_missing(tmp_path: Path) -> None:
    assert read_state(tmp_path / "absent.json") is None


def test_read_state_reads_a_written_file(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    path.write_text(dump_state(FULL_STATE), encoding="utf-8")
    assert read_state(path) == FULL_STATE


def break_version(raw: dict) -> None:
    raw["version"] = 2


def break_policy(raw: dict) -> None:
    raw["previous_execution_policy"] = "Remote Signed; calc"


def break_path(raw: dict) -> None:
    raw["vscode"][0]["path"] = "a.b"


def break_empty_path(raw: dict) -> None:
    raw["vscode"][0]["path"] = []


def break_absent_flag(raw: dict) -> None:
    raw["vscode"][0]["was_absent"] = "no"


def break_themes(raw: dict) -> None:
    raw["themes"] = {"a": 1}


def break_profile_created(raw: dict) -> None:
    raw["profile"]["created"] = "no"


def break_profile_break(raw: dict) -> None:
    raw["profile"]["leading_break_added"] = 1


def break_profile_path(raw: dict) -> None:
    raw["profile"]["path"] = 5


def break_profile_shape(raw: dict) -> None:
    raw["profile"] = "x"


def break_plugin_flag(raw: dict) -> None:
    raw["plugin"]["installed"] = "yes"


def break_plugin_shape(raw: dict) -> None:
    raw["plugin"] = []


def break_missing_key(raw: dict) -> None:
    del raw["plugin"]


@pytest.mark.parametrize(
    "damage",
    [
        break_version,
        break_policy,
        break_path,
        break_empty_path,
        break_absent_flag,
        break_themes,
        break_missing_key,
        break_profile_created,
        break_profile_break,
        break_profile_path,
        break_profile_shape,
        break_plugin_flag,
        break_plugin_shape,
    ],
)
def test_parse_state_rejects_damaged_files(damage) -> None:
    raw = valid()
    damage(raw)
    with pytest.raises(InstallerError, match="not a state file"):
        parse_state(json.dumps(raw), "state")


def test_parse_state_rejects_text_that_is_not_json() -> None:
    with pytest.raises(InstallerError, match="not strict JSON"):
        parse_state("{", "state")
