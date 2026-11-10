"""The uninstall workflow, driven only by the state file."""

from dataclasses import dataclass
from pathlib import Path

from installer.actions import (
    CLAUDE,
    MARKETPLACE_NAME,
    PLUGIN_SPEC,
    VSCODE_INDENT,
    LoadedSettings,
    load_settings,
    run_step,
    set_execution_policy,
    sha256_hex,
    write_settings,
)
from installer.jsonio import detect_indent
from installer.merge import Change, revert_settings
from installer.model import (
    EXIT_OK,
    EXIT_REFUSED,
    EXIT_STEP_FAILED,
    Environment,
    InstallerError,
    Report,
)
from installer.profile import ProfileText, decode_profile, encode_profile, remove_block
from installer.state import ProfileRecord, State, read_state


@dataclass(frozen=True, slots=True)
class LoadedProfile:
    path: Path
    text: ProfileText


def _load_profile(record: ProfileRecord | None) -> LoadedProfile | None:
    if record is None or not Path(record.path).exists():
        return None
    path = Path(record.path)
    return LoadedProfile(path, decode_profile(path.read_bytes(), str(path)))


def _revert_file(
    env: Environment,
    loaded: LoadedSettings,
    changes: tuple[Change, ...],
    indent: str | int,
    lines: list[str],
) -> None:
    reverted, left_alone = revert_settings(loaded.doc, changes)
    lines += write_settings(env.backup_stamp, loaded, reverted, indent)
    lines += [
        f"Left your newer value for {' > '.join(change.path)} in {loaded.path}"
        for change in left_alone
    ]


def _remove_themes(env: Environment, state: State, lines: list[str]) -> None:
    for name, digest in sorted(state.themes.items()):
        path = env.themes_dir / name
        if not path.exists():
            lines.append(f"Theme {name} is already gone.")
        elif sha256_hex(path.read_bytes()) == digest:
            path.unlink()
            lines.append(f"Removed theme {name}")
        else:
            lines.append(f"Kept theme {name}: its content changed since install.")


def _remove_profile_block(
    record: ProfileRecord | None, loaded: LoadedProfile | None, lines: list[str]
) -> None:
    if record is None:
        return
    if loaded is None:
        lines.append(f"The PowerShell profile {record.path} no longer exists.")
        return
    text = remove_block(loaded.text.text, record.leading_break_added)
    if record.created and not text:
        loaded.path.unlink()
        lines.append(f"Deleted the PowerShell profile {loaded.path}, which the install created.")
        return
    loaded.path.write_bytes(encode_profile(ProfileText(text, loaded.text.has_bom)))
    lines.append(f"Removed the block from the PowerShell profile {loaded.path}")


def _restore_policy(env: Environment, state: State, failures: list[str], lines: list[str]) -> None:
    previous = state.previous_execution_policy
    if previous is None:
        return
    outcome = set_execution_policy(env.run, previous)
    if outcome.ok:
        lines.append(f"Restored the CurrentUser execution policy to {previous}.")
    else:
        failures.append(outcome.failure)


def _remove_plugin(env: Environment, state: State, failures: list[str], lines: list[str]) -> None:
    steps = []
    if state.plugin.installed:
        steps.append(
            (
                [CLAUDE, "plugin", "uninstall", PLUGIN_SPEC, "--scope", "user"],
                "Uninstalled the plugin.",
            )
        )
    if state.plugin.marketplace_added:
        steps.append(
            (
                [CLAUDE, "plugin", "marketplace", "remove", MARKETPLACE_NAME],
                "Removed the marketplace.",
            )
        )
    for argv, done in steps:
        outcome = run_step(env.run, argv, " ".join(argv[:4]))
        if outcome.ok:
            lines.append(done)
        else:
            failures.append(outcome.failure)


def uninstall(env: Environment) -> Report:
    try:
        state = read_state(env.state_file)
        if state is None:
            return Report((f"Nothing to undo: {env.state_file} does not exist.",), EXIT_OK)
        vscode = load_settings(env.vscode_settings)
        claude = load_settings(env.claude_settings)
        profile = _load_profile(state.profile)
    except InstallerError as err:
        return Report((f"Nothing was changed. {err}",), EXIT_REFUSED)
    lines: list[str] = []
    failures: list[str] = []
    _revert_file(env, vscode, state.vscode, VSCODE_INDENT, lines)
    _revert_file(env, claude, state.claude, detect_indent(claude.text), lines)
    _remove_themes(env, state, lines)
    _remove_profile_block(state.profile, profile, lines)
    _restore_policy(env, state, failures, lines)
    _remove_plugin(env, state, failures, lines)
    env.state_file.unlink()
    lines.append(f"Deleted {env.state_file}")
    if failures:
        lines.append("Some steps failed:")
        lines += [f"  {failure}" for failure in failures]
    return Report(tuple(lines), EXIT_STEP_FAILED if failures else EXIT_OK)
