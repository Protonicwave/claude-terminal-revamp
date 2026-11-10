"""The real command runner. Tests inject a fake with the same shape."""

import shutil
import subprocess
from collections.abc import Sequence

from installer.model import CommandResult

COMMAND_TIMEOUT_SECONDS = 120
EXIT_NOT_FOUND = 127
EXIT_TIMED_OUT = 124


def run_command(
    argv: Sequence[str], timeout_seconds: float = COMMAND_TIMEOUT_SECONDS
) -> CommandResult:
    # shutil.which applies PATHEXT, so claude.cmd resolves without shell=True.
    executable = shutil.which(argv[0]) or argv[0]
    try:
        completed = subprocess.run(  # noqa: S603 - argv is a list built from constants and paths
            [executable, *argv[1:]],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdin=subprocess.DEVNULL,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError as err:
        return CommandResult(EXIT_NOT_FOUND, "", f"{argv[0]}: command not found ({err})")
    except subprocess.TimeoutExpired:
        return CommandResult(
            EXIT_TIMED_OUT, "", f"{argv[0]}: no result within {timeout_seconds} seconds"
        )
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)
