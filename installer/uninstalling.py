"""The uninstall workflow, driven only by the state file."""

from dataclasses import dataclass
from pathlib import Path

from installer.actions import (
    CLAUDE,
    MARKETPLACE_NAME,
    PLUGIN_SPEC,
    LoadedSettings,
    load_settings,
    record_state,
    run_step,
    set_execution_policy,
    sha256_hex,
    write_settings,
)
from installer.jsonio import detect_indent
from installer.merge import Change, revert_settings
from installer.model import EXIT_OK, EXIT_STEP_FAILED, Environment, Report
from installer.profile import ProfileText, decode_profile, encode_profile, remove_block
from installer.state import PluginRecord, ProfileRecord, State, read_state


@dataclass(frozen=True, slots=True)
class LoadedProfile:
    path: Path
    before: ProfileText
    after: ProfileText


def _load_profile(record: ProfileRecord | None) -> LoadedProfile | None:
    if record is None or not Path(record.path).exists():
        return None
    path = Path(record.path)
    before = decode_profile(path.read_bytes(), str(path))
    text = remove_block(before.text, record.leading_break_added, str(path))
    return LoadedProfile(path, before, ProfileText(text, before.has_bom))


def _revert_file(
    env: Environment,
    loaded: LoadedSettings,
    changes: tuple[Change, ...],
    lines: list[str],
) -> None:
    reverted, left_alone = revert_settings(loaded.doc, changes)
    indent = detect_indent(loaded.text)
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
    if record.created and not loaded.after.text:
        loaded.path.unlink()
        lines.append(f"Deleted the PowerShell profile {loaded.path}, which the install created.")
        return
    loaded.path.write_bytes(encode_profile(loaded.after))
    lines.append(f"Removed the block from the PowerShell profile {loaded.path}")


def _restore_policy(
    env: Environment, state: State, failures: list[str], lines: list[str]
) -> str | None:
    """Returns the policy still to restore, or None when nothing is left to do."""
    previous = state.previous_execution_policy
    if previous is None:
        return None
    outcome = set_execution_policy(env.run, previous)
    if outcome.ok:
        lines.append(f"Restored the CurrentUser execution policy to {previous}.")
        return None
    failures.append(outcome.failure)
    return previous


def _run_removal(
    env: Environment, argv: list[str], done: str, failures: list[str], lines: list[str]
) -> bool:
    outcome = run_step(env.run, argv, " ".join(argv[:4]))
    if outcome.ok:
        lines.append(done)
    else:
        failures.append(outcome.failure)
    return outcome.ok


def _remove_plugin(
    env: Environment, state: State, failures: list[str], lines: list[str]
) -> PluginRecord:
    """Returns the part of the plugin record that could not be undone."""
    uninstall_argv = [CLAUDE, "plugin", "uninstall", PLUGIN_SPEC, "--scope", "user"]
    remove_argv = [CLAUDE, "plugin", "marketplace", "remove", MARKETPLACE_NAME]
    installed_left = state.plugin.installed and not _run_removal(
        env, uninstall_argv, "Uninstalled the plugin.", failures, lines
    )
    marketplace_left = state.plugin.marketplace_added and not _run_removal(
        env, remove_argv, "Removed the marketplace.", failures, lines
    )
    return PluginRecord(marketplace_added=marketplace_left, installed=installed_left)


def uninstall(env: Environment) -> Report:
    """Undo what the state file records. Raises InstallerError, before changing anything."""
    state = read_state(env.state_file)
    if state is None:
        return Report((f"Nothing to undo: {env.state_file} does not exist.",), EXIT_OK)
    vscode = load_settings(env.vscode_settings)
    claude = load_settings(env.claude_settings)
    profile = _load_profile(state.profile)
    lines: list[str] = []
    failures: list[str] = []
    _revert_file(env, vscode, state.vscode, lines)
    _revert_file(env, claude, state.claude, lines)
    _remove_themes(env, state, lines)
    _remove_profile_block(state.profile, profile, lines)
    policy_left = _restore_policy(env, state, failures, lines)
    plugin_left = _remove_plugin(env, state, failures, lines)
    if failures:
        record_state(
            env.state_file, State(previous_execution_policy=policy_left, plugin=plugin_left)
        )
        lines.append(f"Kept {env.state_file} with the steps still to undo.")
        lines.append("Some steps failed:")
        lines += [f"  {failure}" for failure in failures]
        lines.append("Run --uninstall again to retry them.")
        return Report(tuple(lines), EXIT_STEP_FAILED)
    env.state_file.unlink()
    lines.append(f"Deleted {env.state_file}")
    return Report(tuple(lines), EXIT_OK)
