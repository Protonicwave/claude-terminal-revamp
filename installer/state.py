"""The state file: everything the installer needs to reverse itself."""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from installer.jsonio import dumps, parse_object
from installer.merge import Change
from installer.model import InstallerError, JsonObject

STATE_VERSION = 1
# Interpolated into a PowerShell command on uninstall, so only a bare policy name is accepted.
POLICY_NAME = re.compile(r"[A-Za-z]+")


@dataclass(frozen=True, slots=True)
class ProfileRecord:
    path: str
    created: bool
    leading_break_added: bool


@dataclass(frozen=True, slots=True)
class PluginRecord:
    marketplace_added: bool = False
    installed: bool = False


@dataclass(frozen=True, slots=True)
class State:
    vscode: tuple[Change, ...] = ()
    claude: tuple[Change, ...] = ()
    themes: Mapping[str, str] = field(default_factory=dict)
    previous_execution_policy: str | None = None
    profile: ProfileRecord | None = None
    plugin: PluginRecord = field(default_factory=PluginRecord)


def _require(condition: object, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _change_to_json(change: Change) -> JsonObject:
    return {
        "path": list(change.path),
        "previous": change.previous,
        "was_absent": change.was_absent,
        "applied": change.applied,
    }


def _change_from_json(item: JsonObject) -> Change:
    path = item["path"]
    _require(
        isinstance(path, list) and path and all(isinstance(part, str) for part in path),
        f"change path {path!r} must be a non-empty list of strings",
    )
    _require(isinstance(item["was_absent"], bool), "was_absent must be true or false")
    return Change(tuple(path), item["previous"], item["was_absent"], item["applied"])


def _profile_to_json(profile: ProfileRecord | None) -> JsonObject | None:
    if profile is None:
        return None
    return {
        "path": profile.path,
        "created": profile.created,
        "leading_break_added": profile.leading_break_added,
    }


def _object(value: object, name: str) -> JsonObject:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object, got {value!r}")
    return value


def _flag(item: JsonObject, key: str) -> bool:
    value = item[key]
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be true or false, got {value!r}")
    return value


def _profile_from_json(raw: object) -> ProfileRecord | None:
    if raw is None:
        return None
    item = _object(raw, "profile")
    path = item["path"]
    if not isinstance(path, str):
        raise ValueError(f"profile path {path!r} must be a string")
    return ProfileRecord(path, _flag(item, "created"), _flag(item, "leading_break_added"))


def _to_json(state: State) -> JsonObject:
    return {
        "version": STATE_VERSION,
        "vscode": [_change_to_json(change) for change in state.vscode],
        "claude": [_change_to_json(change) for change in state.claude],
        "themes": dict(state.themes),
        "previous_execution_policy": state.previous_execution_policy,
        "profile": _profile_to_json(state.profile),
        "plugin": {
            "marketplace_added": state.plugin.marketplace_added,
            "installed": state.plugin.installed,
        },
    }


def _from_json(raw: JsonObject) -> State:
    _require(raw.get("version") == STATE_VERSION, f"unsupported version {raw.get('version')!r}")
    policy: Any = raw["previous_execution_policy"]
    _require(
        policy is None or POLICY_NAME.fullmatch(policy),
        f"execution policy {policy!r} must be a bare policy name",
    )
    themes = raw["themes"]
    _require(
        isinstance(themes, dict)
        and all(
            isinstance(name, str) and isinstance(digest, str) for name, digest in themes.items()
        ),
        "themes must map file names to digests",
    )
    plugin = _object(raw["plugin"], "plugin")
    return State(
        vscode=tuple(_change_from_json(item) for item in raw["vscode"]),
        claude=tuple(_change_from_json(item) for item in raw["claude"]),
        themes=themes,
        previous_execution_policy=policy,
        profile=_profile_from_json(raw["profile"]),
        plugin=PluginRecord(_flag(plugin, "marketplace_added"), _flag(plugin, "installed")),
    )


def dump_state(state: State) -> str:
    return dumps(_to_json(state))


def parse_state(text: str, label: str) -> State:
    raw = parse_object(text, label)
    try:
        return _from_json(raw)
    except (KeyError, TypeError, ValueError) as err:
        raise InstallerError(f"{label} is not a state file this installer wrote: {err!r}") from err


def read_state(path: Path) -> State | None:
    if not path.exists():
        return None
    return parse_state(path.read_text(encoding="utf-8"), str(path))
