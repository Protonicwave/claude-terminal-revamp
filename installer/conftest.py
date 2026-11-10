"""Fixtures: a sandbox that points every path into tmp_path and fakes the command runner."""

import json
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from installer.environment import build_environment
from installer.model import CommandResult, Environment, Host

REAL_REPOSITORY = Path(__file__).resolve().parents[1]
INSTALL_TIME = datetime(2026, 11, 10, 9, 30, 0)
UNINSTALL_TIME = datetime(2026, 11, 10, 10, 45, 5)
FAKE_PYTHON = r"C:\Python\python.exe"

VSCODE_CONFIG = {
    "terminal.integrated.fontSize": 14,
    "terminal.integrated.lineHeight": 1.3,
    "workbench.colorCustomizations": {
        "terminal.background": "#262624",
        "terminal.foreground": "#E8E6DC",
    },
    "workbench.editorAssociations": {"**/typeset/*.md": "vscode.markdown.preview.editor"},
}
CLAUDE_CONFIG = {
    "theme": "custom:claude-warm",
    "statusLine": {"command": '"{python}" "{repository}/statusline/statusline.py"'},
}
THEME = {"name": "Claude Warm", "base": "dark"}


class FakeRunner:
    """Records each argv and answers from the first rule whose fragment appears in it."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self._rules: list[tuple[str, CommandResult]] = []

    def respond(
        self, fragment: str, returncode: int = 0, stdout: str = "", stderr: str = ""
    ) -> None:
        self._rules.insert(0, (fragment, CommandResult(returncode, stdout, stderr)))

    def __call__(self, argv: Sequence[str]) -> CommandResult:
        self.calls.append(list(argv))
        line = " ".join(argv)
        for fragment, result in self._rules:
            if fragment in line:
                return result
        return CommandResult(0, "", "")

    def commands(self) -> list[str]:
        return [" ".join(call) for call in self.calls]


class Sandbox:
    def __init__(self, root: Path, platform: str, repository: Path | None = None) -> None:
        self.platform = platform
        self.home = root / "home"
        self.appdata = root / "appdata"
        self.profile = root / "Documents" / "PowerShell" / "profile.ps1"
        self.runner = FakeRunner()
        self.runner.respond("Get-ExecutionPolicy", stdout="Restricted\r\n")
        self.runner.respond("$PROFILE", stdout=f"{self.profile}\r\n")
        if repository is None:
            repository = root / "repo"
            self.write_json(repository / "config" / "vscode.json", VSCODE_CONFIG)
            self.write_json(repository / "config" / "claude.json", CLAUDE_CONFIG)
            self.write_json(repository / "config" / "themes" / "claude-warm.json", THEME)
        self.repository = repository
        env = self.env()
        self.vscode = env.vscode_settings
        self.claude = env.claude_settings
        self.state = env.state_file
        self.themes = env.themes_dir

    def env(self, now: datetime = INSTALL_TIME) -> Environment:
        host = Host(self.platform, {"APPDATA": str(self.appdata)}, self.home, FAKE_PYTHON, now)
        return build_environment(host, self.repository, self.runner)

    def uninstall_env(self) -> Environment:
        return self.env(UNINSTALL_TIME)

    @staticmethod
    def write_json(path: Path, value: Any, indent: int = 2) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=indent) + "\n", encoding="utf-8")

    @staticmethod
    def read_json(path: Path) -> Any:
        return json.loads(path.read_text(encoding="utf-8"))

    def root_posix(self) -> str:
        return self.repository.resolve().as_posix()


@pytest.fixture
def sandbox(tmp_path: Path) -> Sandbox:
    return Sandbox(tmp_path, "win32")


@pytest.fixture
def linux_sandbox(tmp_path: Path) -> Sandbox:
    return Sandbox(tmp_path, "linux")


@pytest.fixture
def real_config_sandbox(tmp_path: Path) -> Sandbox:
    return Sandbox(tmp_path, "win32", REAL_REPOSITORY)
