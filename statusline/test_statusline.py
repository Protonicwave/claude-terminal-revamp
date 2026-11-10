"""Behaviour tests for the status line, driven through its public entry points."""

import copy
import io
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest

import statusline

SCRIPT = Path(__file__).with_name("statusline.py")
ANSI = re.compile(r"\x1b\[[0-9;]*m")
TIMING_BUDGET_SECONDS = 0.150
TIMING_RUNS = 3


def plain(text: str) -> str:
    return ANSI.sub("", text)


def full_payload(directory: Path) -> dict:
    return {
        "model": {"display_name": "Opus"},
        "effort": {"level": "high"},
        "workspace": {"current_dir": str(directory)},
        "cwd": str(directory),
        "output_style": {"name": "Explanatory"},
        "cost": {"total_cost_usd": 0.84, "total_lines_added": 120, "total_lines_removed": 8},
        "context_window": {"used_percentage": 42, "context_window_size": 200000},
        "rate_limits": {"five_hour": {"used_percentage": 37}},
    }


def run(monkeypatch, capsys, stdin, columns=None) -> str:
    """Run main() in-process with `stdin` (object, str or bytes) and return stdout."""
    if isinstance(stdin, bytes):
        data = stdin
    elif isinstance(stdin, str):
        data = stdin.encode("utf-8")
    else:
        data = json.dumps(stdin).encode("utf-8")
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(data)))
    if columns is None:
        monkeypatch.delenv("COLUMNS", raising=False)
    else:
        monkeypatch.setenv("COLUMNS", columns)
    assert statusline.main() == 0
    return capsys.readouterr().out


def git(directory: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", *args],
        cwd=directory,
        check=True,
        capture_output=True,
    )


def make_repo(root: Path, *, dirty: bool) -> Path:
    repo = root / "project"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "commit", "--allow-empty", "-m", "initial")
    if dirty:
        (repo / "changed.txt").write_text("change\n", encoding="utf-8")
    return repo


@pytest.fixture
def clean_repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path, dirty=False)


def edited(payload: dict, path: str, *, null: bool) -> dict:
    """Copy `payload` with the dotted `path` removed, or set to None when `null` is true."""
    result = copy.deepcopy(payload)
    *parents, leaf = path.split(".")
    node = result
    for key in parents:
        node = node[key]
    if null:
        node[leaf] = None
    else:
        del node[leaf]
    return result


def without(payload: dict, path: str) -> dict:
    return edited(payload, path, null=False)


def test_full_json_prints_both_lines(monkeypatch, capsys, clean_repo):
    output = run(monkeypatch, capsys, full_payload(clean_repo))
    first, second = plain(output).splitlines()
    assert first == "◆ Opus high  │  project  │  main  │  Explanatory"
    assert second == (
        "━━━━────── 42% of 200k"
        " · $0.84 · +120 −8 · 5h 37%"
    )


def test_every_line_ends_with_reset_and_uses_truecolour(monkeypatch, capsys, clean_repo):
    lines = run(monkeypatch, capsys, full_payload(clean_repo)).splitlines()
    assert len(lines) == 2
    assert all(line.endswith(statusline.RESET) for line in lines)
    assert lines[0].startswith("\x1b[38;2;217;119;87m◆")


MISSING_FIELDS = [
    "model.display_name",
    "effort.level",
    "output_style.name",
    "cost.total_cost_usd",
    "cost.total_lines_added",
    "cost.total_lines_removed",
    "context_window.used_percentage",
    "context_window.context_window_size",
    "rate_limits.five_hour",
]


@pytest.mark.parametrize("path", MISSING_FIELDS)
def test_missing_and_null_fields_render_the_same(monkeypatch, capsys, clean_repo, path):
    payload = full_payload(clean_repo)
    missing = run(monkeypatch, capsys, edited(payload, path, null=False))
    null = run(monkeypatch, capsys, edited(payload, path, null=True))
    assert missing == null
    assert missing != run(monkeypatch, capsys, payload)


def test_missing_model_uses_default_name(monkeypatch, capsys, clean_repo):
    payload = without(full_payload(clean_repo), "model.display_name")
    assert plain(run(monkeypatch, capsys, payload)).startswith("◆ Claude high")


def test_missing_effort_drops_only_the_effort(monkeypatch, capsys, clean_repo):
    output = run(monkeypatch, capsys, without(full_payload(clean_repo), "effort.level"))
    assert plain(output).startswith("◆ Opus  │  project")


def test_missing_cost_drops_only_the_cost(monkeypatch, capsys, clean_repo):
    output = run(monkeypatch, capsys, without(full_payload(clean_repo), "cost.total_cost_usd"))
    assert plain(output).splitlines()[1].endswith("42% of 200k · +120 −8 · 5h 37%")


def test_missing_context_size_keeps_percentage(monkeypatch, capsys, clean_repo):
    payload = without(full_payload(clean_repo), "context_window.context_window_size")
    second = plain(run(monkeypatch, capsys, payload)).splitlines()[1]
    assert second.startswith("━━━━────── 42% ·")


def test_missing_context_percentage_drops_the_bar(monkeypatch, capsys, clean_repo):
    payload = without(full_payload(clean_repo), "context_window.used_percentage")
    assert plain(run(monkeypatch, capsys, payload)).splitlines()[1] == (
        "$0.84 · +120 −8 · 5h 37%"
    )


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("cost.total_lines_added", "+0 −8"),
        ("cost.total_lines_removed", "+120 −0"),
    ],
)
def test_one_missing_line_count_counts_as_zero(monkeypatch, capsys, clean_repo, path, expected):
    payload = without(full_payload(clean_repo), path)
    assert expected in plain(run(monkeypatch, capsys, payload)).splitlines()[1]


def test_both_line_counts_zero_omits_the_segment(monkeypatch, capsys, clean_repo):
    payload = full_payload(clean_repo)
    payload["cost"]["total_lines_added"] = 0
    payload["cost"]["total_lines_removed"] = 0
    second = plain(run(monkeypatch, capsys, payload)).splitlines()[1]
    assert "+" not in second
    assert second.endswith("$0.84 · 5h 37%")


def test_missing_directory_omits_folder_and_git(monkeypatch, capsys, clean_repo):
    payload = without(without(full_payload(clean_repo), "workspace.current_dir"), "cwd")
    assert plain(run(monkeypatch, capsys, payload)).splitlines()[0] == (
        "◆ Opus high  │  Explanatory"
    )


def test_cwd_is_used_when_workspace_directory_is_missing(monkeypatch, capsys, clean_repo):
    payload = without(full_payload(clean_repo), "workspace.current_dir")
    assert "project  │  main" in plain(run(monkeypatch, capsys, payload)).splitlines()[0]


def test_default_output_style_is_hidden(monkeypatch, capsys, clean_repo):
    payload = full_payload(clean_repo)
    payload["output_style"]["name"] = "default"
    assert plain(run(monkeypatch, capsys, payload)).splitlines()[0].endswith("main")


def test_no_line_two_data_prints_line_one_only(monkeypatch, capsys):
    output = run(monkeypatch, capsys, {"model": {"display_name": "Opus"}})
    assert plain(output) == "◆ Opus\n"


def test_empty_object_prints_default_model(monkeypatch, capsys):
    assert plain(run(monkeypatch, capsys, {})) == "◆ Claude\n"


def test_non_numeric_values_are_ignored(monkeypatch, capsys):
    payload = {
        "cost": {"total_cost_usd": "free", "total_lines_added": True},
        "context_window": {"used_percentage": "high"},
        "rate_limits": {"five_hour": {"used_percentage": False}},
    }
    assert plain(run(monkeypatch, capsys, payload)) == "◆ Claude\n"


@pytest.mark.parametrize("five_hour", [{"resets_at": 5}, "soon", None, [], {"utilization": "x"}])
def test_five_hour_without_a_numeric_percentage_is_skipped(monkeypatch, capsys, five_hour):
    payload = {"cost": {"total_cost_usd": 1}, "rate_limits": {"five_hour": five_hour}}
    assert plain(run(monkeypatch, capsys, payload)) == "◆ Claude\n$1.00\n"


@pytest.mark.parametrize("key", ["used_percentage", "used_percent", "utilization"])
def test_five_hour_percentage_keys(monkeypatch, capsys, key):
    payload = {"rate_limits": {"five_hour": {key: 12.4}}}
    assert plain(run(monkeypatch, capsys, payload)) == "◆ Claude\n5h 12%\n"


@pytest.mark.parametrize(
    ("percent", "colour", "filled"),
    [
        (0, statusline.ACCENT, 0),
        (59, statusline.ACCENT, 6),
        (60, statusline.AMBER, 6),
        (85, statusline.AMBER, 9),
        (86, statusline.RED, 9),
        (100, statusline.RED, 10),
        (250, statusline.RED, 10),
        (-5, statusline.ACCENT, 0),
    ],
)
def test_context_bar_colour_and_fill(monkeypatch, capsys, percent, colour, filled):
    payload = {"context_window": {"used_percentage": percent}}
    second = run(monkeypatch, capsys, payload).splitlines()[1]
    assert second.startswith(colour + "━" * filled)
    assert plain(second).count("─") == 10 - filled


@pytest.mark.parametrize(
    ("size", "label"), [(200000, "200k"), (1000000, "1M"), (128000, "128k"), (500, "500")]
)
def test_context_size_labels(monkeypatch, capsys, size, label):
    payload = {"context_window": {"used_percentage": 10, "context_window_size": size}}
    assert plain(run(monkeypatch, capsys, payload)).splitlines()[1].endswith(f"10% of {label}")


def test_no_repository_omits_git_segment(monkeypatch, capsys, tmp_path):
    payload = {"model": {"display_name": "Opus"}, "workspace": {"current_dir": str(tmp_path)}}
    assert plain(run(monkeypatch, capsys, payload)) == f"◆ Opus  │  {tmp_path.name}\n"


def test_clean_repository_shows_branch_without_marker(monkeypatch, capsys, clean_repo):
    output = run(monkeypatch, capsys, {"workspace": {"current_dir": str(clean_repo)}})
    assert plain(output) == "◆ Claude  │  project  │  main\n"


def test_dirty_repository_shows_amber_marker(monkeypatch, capsys, tmp_path):
    repo = make_repo(tmp_path, dirty=True)
    output = run(monkeypatch, capsys, {"workspace": {"current_dir": str(repo)}})
    assert plain(output) == "◆ Claude  │  project  │  main ±\n"
    assert f"main{statusline.AMBER} ±" in output


def test_detached_head_shows_short_hash(monkeypatch, capsys, clean_repo):
    git(clean_repo, "checkout", "--detach")
    output = run(monkeypatch, capsys, {"workspace": {"current_dir": str(clean_repo)}})
    assert re.search(r"project {2}│ {2}[0-9a-f]{7}\n$", plain(output))


@pytest.mark.parametrize(
    "error", [subprocess.TimeoutExpired(cmd="git", timeout=0.5), FileNotFoundError("git")]
)
def test_git_failure_omits_git_segment(monkeypatch, capsys, clean_repo, error):
    def fail(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(subprocess, "run", fail)
    output = run(monkeypatch, capsys, {"workspace": {"current_dir": str(clean_repo)}})
    assert plain(output) == "◆ Claude  │  project\n"


def test_git_takes_no_index_lock_and_has_a_timeout(monkeypatch, capsys, clean_repo):
    calls = []
    real_run = subprocess.run

    def record(command, **kwargs):
        calls.append((command, kwargs["timeout"]))
        return real_run(command, **kwargs)

    monkeypatch.setattr(subprocess, "run", record)
    run(monkeypatch, capsys, {"workspace": {"current_dir": str(clean_repo)}})
    # --no-optional-locks keeps a status refresh from holding .git/index.lock
    # while the user commits.
    command = [
        "git", "--no-optional-locks", "-C", str(clean_repo), "status", "--porcelain=v2", "--branch"
    ]
    assert calls == [(command, 0.5)]


@pytest.mark.parametrize(("columns", "line_count"), [("59", 1), ("0", 1), ("60", 2), ("200", 2)])
def test_columns_below_sixty_prints_line_one_only(monkeypatch, capsys, columns, line_count):
    payload = {"cost": {"total_cost_usd": 1}}
    assert len(run(monkeypatch, capsys, payload, columns=columns).splitlines()) == line_count


@pytest.mark.parametrize("columns", ["", "wide", " 80 "])
def test_unusable_or_wide_columns_keep_line_two(monkeypatch, capsys, columns):
    payload = {"cost": {"total_cost_usd": 1}}
    assert len(run(monkeypatch, capsys, payload, columns=columns).splitlines()) == 2


@pytest.mark.parametrize(
    "stdin",
    [
        "",
        "   ",
        "not json",
        "{",
        "[]",
        "null",
        "42",
        '"text"',
        b"\xff\xfe\x00",
        pytest.param("[" * 100000, id="deeply-nested"),
    ],
)
def test_invalid_stdin_prints_fallback(monkeypatch, capsys, stdin):
    assert run(monkeypatch, capsys, stdin) == "◆ Claude\n"


def test_utf8_byte_order_mark_is_accepted(monkeypatch, capsys):
    stdin = b"\xef\xbb\xbf" + json.dumps({"model": {"display_name": "Opus"}}).encode("utf-8")
    assert plain(run(monkeypatch, capsys, stdin)) == "◆ Opus\n"


def run_script(payload: dict | str, **env: str) -> subprocess.CompletedProcess[bytes]:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=text.encode("utf-8"),
        capture_output=True,
        env={**os.environ, **env},
        check=False,
    )


def test_script_writes_utf8_whatever_the_console_encoding(clean_repo):
    result = run_script(full_payload(clean_repo), PYTHONIOENCODING="ascii", PYTHONUTF8="0")
    assert result.returncode == 0
    assert "◆ Opus" in plain(result.stdout.decode("utf-8"))


def test_script_exits_zero_on_invalid_stdin():
    result = run_script("not json")
    assert result.returncode == 0
    assert result.stdout.decode("utf-8") == "◆ Claude\n"


@pytest.mark.timing
def test_timing(clean_repo):
    payload = full_payload(clean_repo)
    durations = []
    for _ in range(TIMING_RUNS):
        started = time.perf_counter()
        result = run_script(payload)
        durations.append(time.perf_counter() - started)
        assert result.returncode == 0
    best = min(durations)
    budget_ms = TIMING_BUDGET_SECONDS * 1000
    print(f"best of {TIMING_RUNS}: {best * 1000:.1f} ms (budget {budget_ms:.0f} ms)")
    assert best < TIMING_BUDGET_SECONDS
