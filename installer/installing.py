"""The install workflow: validate every input, then apply each step."""

from dataclasses import dataclass
from pathlib import Path

from installer.actions import (
    CLAUDE,
    PERMISSIVE_POLICIES,
    PLUGIN_SPEC,
    TARGET_POLICY,
    VSCODE_INDENT,
    LoadedSettings,
    Outcome,
    ThemeWrite,
    load_settings,
    plan_themes,
    query_execution_policy,
    query_profile_path,
    run_step,
    set_execution_policy,
    sha256_hex,
    write_settings,
    write_themes,
)
from installer.jsonio import detect_indent, read_required_object
from installer.merge import ONE_LEVEL_KEYS, Change, fill_placeholders, merge_settings
from installer.model import (
    EXIT_OK,
    EXIT_REFUSED,
    EXIT_STEP_FAILED,
    Environment,
    InstallerError,
    JsonObject,
    Report,
)
from installer.profile import ProfileText, decode_profile, encode_profile, insert_block
from installer.state import PluginRecord, ProfileRecord, State, dump_state, read_state

NEXT_STEPS = (
    "Next steps:",
    "  1. Reload the VS Code window.",
    "  2. Restart Claude Code.",
    "  3. Run /terminal-setup once inside Claude Code in the VS Code terminal.",
)


@dataclass(frozen=True, slots=True)
class ProfilePlan:
    path: Path
    before: ProfileText
    existed: bool


@dataclass(frozen=True, slots=True)
class InstallPlan:
    earlier: State
    vscode: LoadedSettings
    claude: LoadedSettings
    vscode_incoming: JsonObject
    claude_incoming: JsonObject
    theme_writes: list[ThemeWrite]
    policy: Outcome | None
    profile: ProfilePlan | None
    failures: tuple[str, ...]


def _plan_profile(env: Environment) -> tuple[ProfilePlan | None, tuple[str, ...]]:
    located = query_profile_path(env.run)
    if not located.ok:
        return None, (located.failure,)
    path = Path(located.output)
    if not path.exists():
        return ProfilePlan(path, ProfileText("", True), existed=False), ()
    before = decode_profile(path.read_bytes(), str(path))
    return ProfilePlan(path, before, existed=True), ()


def _plan(env: Environment) -> InstallPlan:
    earlier = read_state(env.state_file) or State()
    vscode = load_settings(env.vscode_settings)
    claude = load_settings(env.claude_settings)
    config = env.repository / "config"
    replacements = {
        "{python}": env.python_executable.replace("\\", "/"),
        "{repository}": env.repository.as_posix(),
    }
    vscode_incoming = read_required_object(config / "vscode.json")
    claude_incoming = fill_placeholders(read_required_object(config / "claude.json"), replacements)
    theme_writes = plan_themes(config / "themes", env.themes_dir, earlier.themes)
    policy = query_execution_policy(env.run) if env.is_windows else None
    profile, failures = _plan_profile(env) if env.is_windows else (None, ())
    return InstallPlan(
        earlier,
        vscode,
        claude,
        vscode_incoming,
        claude_incoming,
        theme_writes,
        policy,
        profile,
        failures,
    )


@dataclass(frozen=True, slots=True)
class MergedSettings:
    vscode_doc: JsonObject
    vscode_changes: tuple[Change, ...]
    claude_doc: JsonObject
    claude_changes: tuple[Change, ...]


def _merge(plan: InstallPlan) -> MergedSettings:
    vscode_doc, vscode_changes = merge_settings(
        plan.vscode.doc, plan.vscode_incoming, ONE_LEVEL_KEYS, plan.earlier.vscode
    )
    claude_doc, claude_changes = merge_settings(
        plan.claude.doc, plan.claude_incoming, ONE_LEVEL_KEYS, plan.earlier.claude
    )
    return MergedSettings(vscode_doc, tuple(vscode_changes), claude_doc, tuple(claude_changes))


def _write_settings(
    env: Environment, plan: InstallPlan, merged: MergedSettings, lines: list[str]
) -> None:
    lines += write_settings(env.backup_stamp, plan.vscode, merged.vscode_doc, VSCODE_INDENT)
    indent = detect_indent(plan.claude.text)
    lines += write_settings(env.backup_stamp, plan.claude, merged.claude_doc, indent)


def _record(env: Environment, state: State) -> None:
    env.state_file.parent.mkdir(parents=True, exist_ok=True)
    env.state_file.write_text(dump_state(state), encoding="utf-8", newline="\n")


def _apply_themes(plan: InstallPlan, lines: list[str]) -> dict[str, str]:
    lines += write_themes(plan.theme_writes)
    themes = dict(plan.earlier.themes)
    for write in plan.theme_writes:
        themes[write.destination.name] = sha256_hex(write.data)
    return themes


def _apply_policy(
    env: Environment, plan: InstallPlan, failures: list[str], lines: list[str]
) -> str | None:
    earlier = plan.earlier.previous_execution_policy
    if plan.policy is None:
        return earlier
    if not plan.policy.ok:
        failures.append(plan.policy.failure)
        return earlier
    current = plan.policy.output
    if current.lower() in PERMISSIVE_POLICIES:
        lines.append(f"Execution policy is {current}; left unchanged.")
        return earlier
    outcome = set_execution_policy(env.run, TARGET_POLICY)
    if not outcome.ok:
        failures.append(outcome.failure)
        return earlier
    lines.append(f"Set the CurrentUser execution policy to {TARGET_POLICY} (was {current}).")
    # A recorded value is the user's original; the policy a second run sees is the kit's own.
    return earlier or current


def _apply_profile(plan: InstallPlan, env: Environment, lines: list[str]) -> ProfileRecord | None:
    earlier = plan.earlier.profile
    if plan.profile is None:
        return earlier
    script = (env.repository / "config" / "prompt.ps1").as_posix()
    text, added_break = insert_block(plan.profile.before.text, script)
    path = plan.profile.path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encode_profile(ProfileText(text, plan.profile.before.has_bom)))
    lines.append(f"Updated the PowerShell profile {path}")
    if earlier is not None and earlier.path == str(path):
        return ProfileRecord(str(path), earlier.created, earlier.leading_break_added or added_break)
    return ProfileRecord(str(path), not plan.profile.existed, added_break)


def _apply_plugin(
    env: Environment, earlier: PluginRecord, failures: list[str], lines: list[str]
) -> PluginRecord:
    added = run_step(
        env.run,
        [CLAUDE, "plugin", "marketplace", "add", str(env.repository)],
        "claude plugin marketplace add",
    )
    installed = run_step(
        env.run,
        [CLAUDE, "plugin", "install", PLUGIN_SPEC, "--scope", "user"],
        "claude plugin install",
    )
    for outcome, done in (
        (added, "Added the plugin marketplace."),
        (installed, "Installed the plugin."),
    ):
        if outcome.ok:
            lines.append(done)
        else:
            failures.append(outcome.failure)
    return PluginRecord(earlier.marketplace_added or added.ok, earlier.installed or installed.ok)


def install(env: Environment) -> Report:
    try:
        plan = _plan(env)
    except InstallerError as err:
        return Report((f"Nothing was changed. {err}",), EXIT_REFUSED)
    lines: list[str] = []
    failures = list(plan.failures)
    merged = _merge(plan)
    earlier = plan.earlier
    # Recorded before the first write, so an error part-way through still
    # leaves a state file that --uninstall can reverse.
    _record(
        env,
        State(
            merged.vscode_changes,
            merged.claude_changes,
            earlier.themes,
            earlier.previous_execution_policy,
            earlier.profile,
            earlier.plugin,
        ),
    )
    _write_settings(env, plan, merged, lines)
    themes = _apply_themes(plan, lines)
    if not env.is_windows:
        lines.append("Skipped the execution policy and PowerShell profile steps: not Windows.")
    policy = _apply_policy(env, plan, failures, lines)
    profile = _apply_profile(plan, env, lines)
    plugin = _apply_plugin(env, earlier.plugin, failures, lines)
    final = State(merged.vscode_changes, merged.claude_changes, themes, policy, profile, plugin)
    _record(env, final)
    lines.append(f"Recorded state in {env.state_file}")
    if failures:
        lines.append("Some steps failed:")
        lines += [f"  {failure}" for failure in failures]
    lines += NEXT_STEPS
    return Report(tuple(lines), EXIT_STEP_FAILED if failures else EXIT_OK)
