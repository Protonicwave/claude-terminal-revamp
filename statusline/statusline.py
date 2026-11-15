"""One-line truecolour status line for Claude Code, built from the JSON sent on stdin.

Run as a script. It never raises and always exits 0: any failure prints the fallback line.
"""

import contextlib
import json
import math
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Any

FALLBACK_LINE = "◆ Claude"
GIT_TIMEOUT_SECONDS = 0.5
MAX_STDIN_BYTES = 1_048_576

ACCENT = "\x1b[38;2;217;119;87m"
TEXT = "\x1b[38;2;232;230;220m"
MUTED = "\x1b[38;2;143;139;128m"
GREEN = "\x1b[38;2;141;181;128m"
RED = "\x1b[38;2;224;122;111m"
AMBER = "\x1b[38;2;227;178;97m"
RESET = "\x1b[0m"

DIAMOND = "◆"
SEPARATOR = f"{MUTED}  │  "
# U+2212 is the required glyph for removed lines, so RUF001 does not apply.
MINUS = "−"  # noqa: RUF001
DIRTY_MARKER = " ±"

# Claude Code's JSON is arbitrary at this boundary, so values stay untyped until parsed.
type JsonObject = dict[str, Any]


@dataclass(frozen=True, slots=True)
class Status:
    """The fields of the Claude Code payload this script displays."""

    model: str
    effort: str | None
    directory: str | None
    output_style: str | None
    lines_added: int | None
    lines_removed: int | None


@dataclass(frozen=True, slots=True)
class GitState:
    """Branch name and whether the working tree has any change."""

    branch: str
    is_dirty: bool


def _section(data: JsonObject, key: str) -> JsonObject:
    value = data.get(key)
    return value if isinstance(value, dict) else {}


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if math.isfinite(value) else None


def _whole_number(value: object) -> int | None:
    number = _number(value)
    return None if number is None else int(number)


def _text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def parse_status(payload: object) -> Status | None:
    """Return the displayed fields, or None when the payload is not a JSON object."""
    if not isinstance(payload, dict):
        return None
    model = _section(payload, "model")
    workspace = _section(payload, "workspace")
    cost = _section(payload, "cost")
    return Status(
        model=_text(model.get("display_name")) or "Claude",
        effort=_text(_section(payload, "effort").get("level")),
        directory=_text(workspace.get("current_dir")) or _text(payload.get("cwd")),
        output_style=_text(_section(payload, "output_style").get("name")),
        lines_added=_whole_number(cost.get("total_lines_added")),
        lines_removed=_whole_number(cost.get("total_lines_removed")),
    )


def parse_porcelain(output: str) -> GitState | None:
    """Parse `git status --porcelain=v2 --branch` output.

    Header lines come first, so the scan stops at the first change entry.
    """
    head: str | None = None
    oid: str | None = None
    is_dirty = False
    for line in output.splitlines():
        if line.startswith("# branch.head "):
            head = line.removeprefix("# branch.head ").strip()
        elif line.startswith("# branch.oid "):
            oid = line.removeprefix("# branch.oid ").strip()
        elif not line.startswith("#") and line.strip():
            is_dirty = True
            break
    if head == "(detached)" and oid and oid != "(initial)":
        head = oid[:7]
    return GitState(branch=head, is_dirty=is_dirty) if head else None


def read_git_state(directory: str) -> GitState | None:
    """Return the git state of `directory`, or None outside a repository or on failure."""
    try:
        # Fixed argument list with git resolved from PATH, so S603 and S607 do not apply.
        result = subprocess.run(  # noqa: S603
            ["git", "--no-optional-locks", "-C", directory, "status", "--porcelain=v2", "--branch"],  # noqa: S607
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return parse_porcelain(result.stdout.decode("utf-8", errors="replace"))


def _lines_segment(status: Status) -> str | None:
    added = status.lines_added or 0
    removed = status.lines_removed or 0
    if added == 0 and removed == 0:
        return None
    return f"{GREEN}+{added} {RED}{MINUS}{removed}"


def _folder_name(directory: str) -> str:
    return os.path.basename(directory.rstrip("/\\")) or directory


def render_line(status: Status, git: GitState | None) -> str:
    """Model, effort, folder, git state, lines changed and non-default output style."""
    model = f"{ACCENT}{DIAMOND} {TEXT}{status.model}"
    if status.effort:
        model += f" {MUTED}{status.effort}"
    parts = [model]
    if status.directory:
        parts.append(f"{TEXT}{_folder_name(status.directory)}")
    if git is not None:
        parts.append(f"{TEXT}{git.branch}{AMBER + DIRTY_MARKER if git.is_dirty else ''}")
    lines = _lines_segment(status)
    if lines is not None:
        parts.append(lines)
    if status.output_style and status.output_style.lower() != "default":
        parts.append(f"{TEXT}{status.output_style}")
    return SEPARATOR.join(parts) + RESET


def build_output(raw: str) -> str:
    """Return the text to print for the stdin text `raw`."""
    try:
        status = parse_status(json.loads(raw))
    except (ValueError, RecursionError):
        status = None
    if status is None:
        return FALLBACK_LINE
    git = read_git_state(status.directory) if status.directory else None
    return render_line(status, git)


def _read_stdin() -> str:
    return sys.stdin.buffer.read(MAX_STDIN_BYTES).decode("utf-8-sig", errors="replace")


def main() -> int:
    """Print the status line. Always returns 0."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
        output = build_output(_read_stdin())
    except Exception as error:  # Process boundary: a status line must never fail the host.
        # logging is not imported: it adds about 12 ms to a budget of 150 ms.
        with contextlib.suppress(OSError):
            sys.stderr.write(f"statusline: {type(error).__name__}: {error}\n")
        output = FALLBACK_LINE
    # A closed pipe means the host stopped listening; there is nobody to tell.
    with contextlib.suppress(OSError):
        sys.stdout.write(output + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
