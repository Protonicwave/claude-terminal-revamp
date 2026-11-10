"""The install workflow: validate every input, then apply each step."""

from dataclasses import dataclass
from pathlib import Path

from installer.actions import (
    CLAUDE,
    MARKETPLACE_NAME,
    PERMISSIVE_POLICIES,
    PLUGIN_SPEC,
    TARGET_POLICY,
    LoadedSettings,
    Outcome,
    ThemeWrite,
    lists_name,
    load_settings,
    plan_themes,
    query_execution_policy,
    query_profile_path,
    record_state,
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
    EXIT_STEP_FAILED,
    Environment,
    JsonObject,
    Report,
)
from installer.profile import ProfileText, decode_profile, encode_profile, insert_block
from installer.state import PluginRecord, ProfileRecord, State, read_state

NEXT_STEPS = (
    "Next steps:",
    "  1. Reload the VS Code window.",
    "  2. Restart Claude Code.",
    "  3. Run /terminal-setup once inside Claude Code in the VS Code terminal.",
)


@dataclass(frozen=True, slots=True)
class ProfilePlan:
    path: Path
    after: ProfileText
    existed: bool
    added_break: bool


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
    existed = path.exists()
    before = decode_profile(path.read_bytes(), str(path)) if existed else ProfileText("", True)
    script = (env.repository / "config" / "prompt.ps1").as_posix()
    text, added_break = insert_block(before.text, script, str(path))
    after = ProfileText(text, before.has_bom)
    return ProfilePlan(path, after, existed, added_break), ()


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
    vscode_indent = detect_indent(plan.vscode.text)
    lines += write_settings(env.backup_stamp, plan.vscode, merged.vscode_doc, vscode_indent)
    claude_indent = detect_indent(plan.claude.text)
    lines += write_settings(env.backup_stamp, plan.claude, merged.claude_doc, claude_indent)


def _planned_themes(plan: InstallPlan) -> dict[str, str]:
    themes = dict(plan.earlier.themes)
    for write in plan.theme_writes:
        themes[write.destination.name] = sha256_hex(write.content)
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


def _apply_profile(plan: InstallPlan, lines: list[str]) -> ProfileRecord | None:
    earlier = plan.earlier.profile
    if plan.profile is None:
        return earlier
    path = plan.profile.path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encode_profile(plan.profile.after))
    lines.append(f"Updated the PowerShell profile {path}")
    added_break = plan.profile.added_break
    if earlier is not None and earlier.path == str(path):
        return ProfileRecord(str(path), earlier.created, earlier.leading_break_added or added_break)
    return ProfileRecord(str(path), not plan.profile.existed, added_break)


@dataclass(frozen=True, slots=True)
class PluginStep:
    noun: str
    name: str
    list_argv: list[str]
    add_argv: list[str]
    done: str


def _ensure(
    env: Environment, step: PluginStep, earlier_ours: bool, failures: list[str], lines: list[str]
) -> bool:
    """Add the step's item unless it is already there. Returns whether the kit owns it."""
    listed = run_step(env.run, step.list_argv, " ".join(step.list_argv))
    if not listed.ok:
        failures.append(listed.failure)
        return earlier_ours
    if lists_name(listed.output, step.name):
        if earlier_ours:
            lines.append(f"The {step.noun} is already in place from an earlier install.")
        else:
            lines.append(
                f"The {step.noun} {step.name} is already present; left as it is, "
                "and uninstall will keep it."
            )
        return earlier_ours
    added = run_step(env.run, step.add_argv, " ".join(step.add_argv[:4]))
    if added.ok:
        lines.append(step.done)
    else:
        failures.append(added.failure)
    return earlier_ours or added.ok


def _apply_plugin(
    env: Environment, earlier: PluginRecord, failures: list[str], lines: list[str]
) -> PluginRecord:
    marketplace_step = PluginStep(
        "plugin marketplace",
        MARKETPLACE_NAME,
        [CLAUDE, "plugin", "marketplace", "list"],
        [CLAUDE, "plugin", "marketplace", "add", str(env.repository)],
        "Added the plugin marketplace.",
    )
    plugin_step = PluginStep(
        "plugin",
        PLUGIN_SPEC,
        [CLAUDE, "plugin", "list"],
        [CLAUDE, "plugin", "install", PLUGIN_SPEC, "--scope", "user"],
        "Installed the plugin.",
    )
    marketplace = _ensure(env, marketplace_step, earlier.marketplace_added, failures, lines)
    installed = _ensure(env, plugin_step, earlier.installed, failures, lines)
    return PluginRecord(marketplace, installed)


def install(env: Environment) -> Report:
    """Apply every step. Raises InstallerError, before anything is written, on a bad input."""
    plan = _plan(env)
    lines: list[str] = []
    failures = list(plan.failures)
    merged = _merge(plan)
    earlier = plan.earlier
    themes = _planned_themes(plan)
    # Recorded before the first write, themes included, so an error part-way through
    # still leaves a state file that --uninstall can reverse.
    record_state(
        env.state_file,
        State(
            merged.vscode_changes,
            merged.claude_changes,
            themes,
            earlier.previous_execution_policy,
            earlier.profile,
            earlier.plugin,
        ),
    )
    _write_settings(env, plan, merged, lines)
    lines += write_themes(plan.theme_writes)
    if not env.is_windows:
        lines.append("Skipped the execution policy and PowerShell profile steps: not Windows.")
    policy = _apply_policy(env, plan, failures, lines)
    profile = _apply_profile(plan, lines)
    plugin = _apply_plugin(env, earlier.plugin, failures, lines)
    final = State(merged.vscode_changes, merged.claude_changes, themes, policy, profile, plugin)
    record_state(env.state_file, final)
    lines.append(f"Recorded state in {env.state_file}")
    if failures:
        lines.append("Some steps failed:")
        lines += [f"  {failure}" for failure in failures]
    lines += NEXT_STEPS
    return Report(tuple(lines), EXIT_STEP_FAILED if failures else EXIT_OK)
