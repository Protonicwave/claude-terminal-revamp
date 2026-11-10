"""Two-line truecolour status line for Claude Code, built from the JSON sent on stdin.

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
NARROW_COLUMNS_LIMIT = 60
BAR_CELLS = 10
AMBER_PERCENT = 60
RED_PERCENT = 85
FIVE_HOUR_PERCENT_KEYS = (
    "used_percentage",
    "used_percent",
    "utilization",
    "percentage",
    "percent",
)
MILLION = 1_000_000
THOUSAND = 1_000

ACCENT = "\x1b[38;2;217;119;87m"
TEXT = "\x1b[38;2;232;230;220m"
MUTED = "\x1b[38;2;143;139;128m"
GREEN = "\x1b[38;2;141;181;128m"
RED = "\x1b[38;2;224;122;111m"
AMBER = "\x1b[38;2;227;178;97m"
RESET = "\x1b[0m"

DIAMOND = "◆"
SEPARATOR = f"{MUTED}  │  "
DOT_SEPARATOR = f"{MUTED} · "
BAR_USED = "━"
BAR_UNUSED = "─"
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
    cost_usd: float | None
    lines_added: int | None
    lines_removed: int | None
    context_percent: float | None
    context_size: int | None
    five_hour_percent: float | None


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


def _five_hour_percent(section: JsonObject) -> float | None:
    for key in FIVE_HOUR_PERCENT_KEYS:
        number = _number(section.get(key))
        if number is not None:
            return number
    return None


def parse_status(payload: object) -> Status | None:
    """Return the displayed fields, or None when the payload is not a JSON object."""
    if not isinstance(payload, dict):
        return None
    model = _section(payload, "model")
    workspace = _section(payload, "workspace")
    cost = _section(payload, "cost")
    context = _section(payload, "context_window")
    rate_limits = _section(_section(payload, "rate_limits"), "five_hour")
    return Status(
        model=_text(model.get("display_name")) or "Claude",
        effort=_text(_section(payload, "effort").get("level")),
        directory=_text(workspace.get("current_dir")) or _text(payload.get("cwd")),
        output_style=_text(_section(payload, "output_style").get("name")),
        cost_usd=_number(cost.get("total_cost_usd")),
        lines_added=_whole_number(cost.get("total_lines_added")),
        lines_removed=_whole_number(cost.get("total_lines_removed")),
        context_percent=_number(context.get("used_percentage")),
        context_size=_whole_number(context.get("context_window_size")),
        five_hour_percent=_five_hour_percent(rate_limits),
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
            ["git", "-C", directory, "status", "--porcelain=v2", "--branch"],  # noqa: S607
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


def _round_half_up(value: float) -> int:
    return math.floor(value + 0.5)


def _format_size(size: int) -> str:
    if size >= MILLION:
        return f"{size / MILLION:g}M"
    if size >= THOUSAND:
        return f"{size / THOUSAND:g}k"
    return str(size)


def _bar_colour(percent: float) -> str:
    if percent > RED_PERCENT:
        return RED
    if percent >= AMBER_PERCENT:
        return AMBER
    return ACCENT


def _context_segment(status: Status) -> str | None:
    if status.context_percent is None:
        return None
    percent = min(max(status.context_percent, 0.0), 100.0)
    used_cells = min(_round_half_up(percent / BAR_CELLS), BAR_CELLS)
    unused_cells = BAR_CELLS - used_cells
    bar = f"{_bar_colour(percent)}{BAR_USED * used_cells}{MUTED}{BAR_UNUSED * unused_cells}"
    label = f"{TEXT} {_round_half_up(percent)}%"
    if status.context_size is not None:
        label += f" of {_format_size(status.context_size)}"
    return bar + label


def _cost_segment(status: Status) -> str | None:
    if status.cost_usd is None:
        return None
    return f"{TEXT}${status.cost_usd:.2f}"


def _lines_segment(status: Status) -> str | None:
    added = status.lines_added or 0
    removed = status.lines_removed or 0
    if added == 0 and removed == 0:
        return None
    return f"{GREEN}+{added} {RED}{MINUS}{removed}"


def _five_hour_segment(status: Status) -> str | None:
    if status.five_hour_percent is None:
        return None
    return f"{TEXT}5h {_round_half_up(status.five_hour_percent)}%"


def _folder_name(directory: str) -> str:
    return os.path.basename(directory.rstrip("/\\")) or directory


def render_header(status: Status, git: GitState | None) -> str:
    """Line 1: model, effort, folder, git state and non-default output style."""
    model = f"{ACCENT}{DIAMOND} {TEXT}{status.model}"
    if status.effort:
        model += f" {MUTED}{status.effort}"
    parts = [model]
    if status.directory:
        parts.append(f"{TEXT}{_folder_name(status.directory)}")
    if git is not None:
        parts.append(f"{TEXT}{git.branch}{AMBER + DIRTY_MARKER if git.is_dirty else ''}")
    if status.output_style and status.output_style.lower() != "default":
        parts.append(f"{TEXT}{status.output_style}")
    return SEPARATOR.join(parts) + RESET


def render_usage(status: Status) -> str | None:
    """Line 2: context bar, cost, lines changed and five-hour limit; None when nothing is known."""
    segments = (
        _context_segment(status),
        _cost_segment(status),
        _lines_segment(status),
        _five_hour_segment(status),
    )
    present = [segment for segment in segments if segment]
    return DOT_SEPARATOR.join(present) + RESET if present else None


def _is_narrow(columns: str | None) -> bool:
    if columns is None:
        return False
    try:
        return int(columns.strip()) < NARROW_COLUMNS_LIMIT
    except ValueError:
        return False


def build_output(raw: str, columns: str | None) -> str:
    """Return the text to print for the stdin text `raw` and the COLUMNS value `columns`."""
    try:
        status = parse_status(json.loads(raw))
    except (ValueError, RecursionError):
        status = None
    if status is None:
        return FALLBACK_LINE
    git = read_git_state(status.directory) if status.directory else None
    lines = [render_header(status, git)]
    usage = None if _is_narrow(columns) else render_usage(status)
    if usage is not None:
        lines.append(usage)
    return "\n".join(lines)


def _read_stdin() -> str:
    return sys.stdin.buffer.read(MAX_STDIN_BYTES).decode("utf-8-sig", errors="replace")


def main() -> int:
    """Print the status line. Always returns 0."""
    try:
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
        output = build_output(_read_stdin(), os.environ.get("COLUMNS"))
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
