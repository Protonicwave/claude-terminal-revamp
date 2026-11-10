"""Plain types shared across the installer."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

# Settings files are arbitrary JSON, so their values are untyped at this boundary.
JsonObject = dict[str, Any]

EXIT_OK = 0
EXIT_STEP_FAILED = 1
EXIT_REFUSED = 2


class InstallerError(Exception):
    """A refusal that stops the run before anything is written."""


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


Runner = Callable[[Sequence[str]], CommandResult]


@dataclass(frozen=True, slots=True)
class Host:
    """Facts about the machine, injected so tests can describe any platform."""

    platform: str
    env_vars: Mapping[str, str]
    home: Path
    python_executable: str
    now: datetime


@dataclass(frozen=True, slots=True)
class Environment:
    repository: Path
    vscode_settings: Path
    claude_settings: Path
    state_file: Path
    themes_dir: Path
    is_windows: bool
    python_executable: str
    backup_stamp: str
    run: Runner


@dataclass(frozen=True, slots=True)
class Report:
    lines: tuple[str, ...]
    exit_code: int
