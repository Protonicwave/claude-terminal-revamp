"""Strict JSON reading and writing for settings files."""

import json
import re
from pathlib import Path
from typing import Any

from installer.model import InstallerError, JsonObject

DEFAULT_INDENT = 2
_INDENT_PATTERN = re.compile(r"^([ \t]+)\S", re.MULTILINE)


def parse_object(text: str, label: str) -> JsonObject:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as err:
        raise InstallerError(
            f"{label} is not strict JSON (line {err.lineno}, column {err.colno}): {err.msg}"
        ) from err
    if not isinstance(value, dict):
        raise InstallerError(
            f"{label} must hold a JSON object at the top level, got {type(value).__name__}"
        )
    return value


def read_required_object(path: Path) -> JsonObject:
    if not path.is_file():
        raise InstallerError(f"{path} is missing")
    return parse_object(path.read_text(encoding="utf-8-sig"), str(path))


def detect_indent(text: str) -> str | int:
    match = _INDENT_PATTERN.search(text)
    return match.group(1) if match else DEFAULT_INDENT


def dumps(value: Any, indent: str | int = DEFAULT_INDENT) -> str:  # JSON boundary
    return json.dumps(value, indent=indent, ensure_ascii=False) + "\n"
