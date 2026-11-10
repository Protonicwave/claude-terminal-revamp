"""Pure merge and revert of settings documents, with a record of what was replaced."""

import copy
import json
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from installer.model import JsonObject

# These keys hold objects whose members belong to different owners, so they merge one level deep.
ONE_LEVEL_KEYS = frozenset({"workbench.colorCustomizations", "workbench.editorAssociations"})

_MISSING = object()


@dataclass(frozen=True, slots=True)
class Change:
    """One key path the installer set, with the value it replaced."""

    path: tuple[str, ...]
    previous: Any  # JSON boundary
    was_absent: bool
    applied: Any  # JSON boundary


def fill_placeholders(value: Any, replacements: Mapping[str, str]) -> Any:  # JSON boundary
    # Recursion depth follows the repository's own config files, which this project controls.
    if isinstance(value, str):
        for token, text in replacements.items():
            value = value.replace(token, text)
        return value
    if isinstance(value, list):
        return [fill_placeholders(item, replacements) for item in value]
    if isinstance(value, dict):
        return {key: fill_placeholders(item, replacements) for key, item in value.items()}
    return value


def get_path(document: JsonObject, path: tuple[str, ...]) -> Any:
    node: Any = document
    for part in path:
        if not isinstance(node, dict) or part not in node:
            return _MISSING
        node = node[part]
    return node


def _set_path(document: JsonObject, path: tuple[str, ...], value: Any) -> None:
    parent = get_path(document, path[:-1])
    parent[path[-1]] = value


def _delete_path(document: JsonObject, path: tuple[str, ...]) -> None:
    parent = get_path(document, path[:-1])
    del parent[path[-1]]


def _same(left: Any, right: Any) -> bool:
    # Plain == treats 1 and True as equal; the serialised form does not.
    return json.dumps(left, sort_keys=True) == json.dumps(right, sort_keys=True)


def _targets(
    current: JsonObject,
    key: str,
    value: Any,
    one_level_keys: Collection[str],
    earlier_paths: Collection[tuple[str, ...]],
) -> list[tuple[tuple[str, ...], Any]]:
    merges_inside = (
        key in one_level_keys
        and isinstance(value, dict)
        and isinstance(current.get(key), dict)
        and (key,) not in earlier_paths
    )
    if merges_inside:
        return [((key, member), item) for member, item in value.items()]
    return [((key,), value)]


def _record(
    document: JsonObject, path: tuple[str, ...], applied: Any, earlier: Change | None
) -> Change:
    if earlier is not None:
        return Change(path, earlier.previous, earlier.was_absent, applied)
    current = get_path(document, path)
    if current is _MISSING:
        return Change(path, None, True, applied)
    return Change(path, copy.deepcopy(current), False, applied)


def merge_settings(
    current: JsonObject,
    incoming: JsonObject,
    one_level_keys: Collection[str],
    earlier: Iterable[Change],
) -> tuple[JsonObject, list[Change]]:
    """Return the merged document and every change now owned by the installer.

    A path already recorded keeps its original previous value, so a second run never
    records its own earlier output as the user's value.
    """
    merged = copy.deepcopy(current)
    earlier_by_path = {change.path: change for change in earlier}
    changes: dict[tuple[str, ...], Change] = {}
    for key, value in incoming.items():
        for path, applied in _targets(current, key, value, one_level_keys, earlier_by_path):
            changes[path] = _record(merged, path, applied, earlier_by_path.get(path))
            _set_path(merged, path, copy.deepcopy(applied))
    untouched = [change for path, change in earlier_by_path.items() if path not in changes]
    return merged, [*changes.values(), *untouched]


def revert_settings(
    current: JsonObject, changes: Iterable[Change]
) -> tuple[JsonObject, list[Change]]:
    """Return the reverted document and the changes left alone because the user moved on."""
    reverted = copy.deepcopy(current)
    left_alone: list[Change] = []
    for change in changes:
        now = get_path(reverted, change.path)
        if now is _MISSING or not _same(now, change.applied):
            left_alone.append(change)
        elif change.was_absent:
            _delete_path(reverted, change.path)
        else:
            _set_path(reverted, change.path, copy.deepcopy(change.previous))
    return reverted, left_alone
