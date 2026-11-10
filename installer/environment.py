"""Resolves every path the installer touches from the host description."""

from pathlib import Path

from installer.model import Environment, Host, InstallerError, Runner

BACKUP_STAMP_FORMAT = "%Y%m%d-%H%M%S"


def vscode_settings_path(host: Host) -> Path:
    if host.platform == "win32":
        appdata = host.env_vars.get("APPDATA")
        if not appdata:
            raise InstallerError("APPDATA is not set, so the VS Code settings path is unknown")
        return Path(appdata) / "Code" / "User" / "settings.json"
    if host.platform == "darwin":
        return host.home / "Library" / "Application Support" / "Code" / "User" / "settings.json"
    return host.home / ".config" / "Code" / "User" / "settings.json"


def build_environment(host: Host, repository: Path, run: Runner) -> Environment:
    claude_dir = host.home / ".claude"
    return Environment(
        repository=repository.resolve(),
        vscode_settings=vscode_settings_path(host),
        claude_settings=claude_dir / "settings.json",
        state_file=claude_dir / "terminal-kit-state.json",
        themes_dir=claude_dir / "themes",
        is_windows=host.platform == "win32",
        python_executable=host.python_executable,
        backup_stamp=host.now.strftime(BACKUP_STAMP_FORMAT),
        run=run,
    )
