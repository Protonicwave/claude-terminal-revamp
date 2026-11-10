import sys
from datetime import datetime
from pathlib import Path

import pytest

from installer.environment import build_environment, vscode_settings_path
from installer.model import Host, InstallerError
from installer.runner import EXIT_NOT_FOUND, EXIT_TIMED_OUT, run_command

HOME = Path("/home/someone")
NOW = datetime(2026, 1, 2, 3, 4, 5)


def host(platform: str, env_vars: dict[str, str] | None = None) -> Host:
    return Host(platform, env_vars or {}, HOME, "python", NOW)


def test_windows_vscode_settings_live_under_appdata() -> None:
    path = vscode_settings_path(host("win32", {"APPDATA": "/appdata"}))
    assert path == Path("/appdata/Code/User/settings.json")


def test_windows_without_appdata_is_refused() -> None:
    with pytest.raises(InstallerError, match="APPDATA"):
        vscode_settings_path(host("win32"))


def test_macos_vscode_settings_live_under_application_support() -> None:
    expected = HOME / "Library" / "Application Support" / "Code" / "User" / "settings.json"
    assert vscode_settings_path(host("darwin")) == expected


def test_linux_vscode_settings_live_under_dot_config() -> None:
    assert vscode_settings_path(host("linux")) == HOME / ".config/Code/User/settings.json"


def test_build_environment_places_claude_files_under_dot_claude(tmp_path: Path) -> None:
    env = build_environment(host("linux"), tmp_path, run_command)
    assert env.claude_settings == HOME / ".claude" / "settings.json"
    assert env.state_file == HOME / ".claude" / "terminal-kit-state.json"
    assert env.themes_dir == HOME / ".claude" / "themes"
    assert env.backup_stamp == "20260102-030405"
    assert env.is_windows is False


def test_run_command_returns_exit_code_and_output() -> None:
    code = "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)"
    result = run_command([sys.executable, "-c", code])
    assert (result.returncode, result.stdout.strip(), result.stderr.strip()) == (3, "out", "err")


def test_run_command_reports_a_missing_executable() -> None:
    result = run_command(["terminal-kit-no-such-command"])
    assert result.returncode == EXIT_NOT_FOUND
    assert "terminal-kit-no-such-command" in result.stderr


def test_run_command_reports_a_timeout() -> None:
    result = run_command([sys.executable, "-c", "import time; time.sleep(10)"], timeout_seconds=0.5)
    assert result.returncode == EXIT_TIMED_OUT
    assert "no result within" in result.stderr
