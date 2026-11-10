import json
from pathlib import Path

import pytest

from installer.conftest import Sandbox
from installer.installing import install
from installer.model import Report
from installer.profile import BOM, END_MARKER, START_MARKER
from installer.uninstalling import uninstall

SET_POLICY = "Set-ExecutionPolicy"


def text_of(report: Report) -> str:
    return "\n".join(report.lines)


def profile_block(sandbox: Sandbox, eol: str) -> bytes:
    script = f"{sandbox.root_posix()}/config/prompt.ps1"
    return eol.join([START_MARKER, f". '{script}'", END_MARKER]).encode()


def policy_commands(sandbox: Sandbox) -> list[str]:
    return [call for call in sandbox.runner.commands() if SET_POLICY in call]


# Install into missing files


def test_fresh_install_into_missing_files(sandbox: Sandbox) -> None:
    report = install(sandbox.env())

    assert report.exit_code == 0
    vscode = sandbox.read_json(sandbox.vscode)
    assert vscode["terminal.integrated.fontSize"] == 14
    assert vscode["workbench.colorCustomizations"]["terminal.background"] == "#262624"
    claude = sandbox.read_json(sandbox.claude)
    expected = f'"C:/Python/python.exe" "{sandbox.root_posix()}/statusline/statusline.py"'
    assert claude["statusLine"]["command"] == expected
    assert json.loads((sandbox.themes / "claude-warm.json").read_text(encoding="utf-8"))
    assert sandbox.state.exists()
    assert not list(sandbox.vscode.parent.glob("*.bak"))
    assert not list(sandbox.claude.parent.glob("*.bak"))
    output = text_of(report)
    assert "Reload the VS Code window" in output
    assert "Restart Claude Code" in output
    assert "/terminal-setup" in output


def test_a_write_error_part_way_leaves_a_state_uninstall_can_use(
    sandbox: Sandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_on_themes(*_: object) -> list[str]:
        raise OSError("disk full")

    monkeypatch.setattr("installer.installing.write_themes", fail_on_themes)

    with pytest.raises(OSError, match="disk full"):
        install(sandbox.env())

    assert sandbox.read_json(sandbox.vscode)["terminal.integrated.fontSize"] == 14
    assert sandbox.state.exists()
    report = uninstall(sandbox.uninstall_env())
    assert report.exit_code == 0
    assert "terminal.integrated.fontSize" not in sandbox.read_json(sandbox.vscode)


def test_install_runs_the_policy_and_plugin_commands(sandbox: Sandbox) -> None:
    install(sandbox.env())
    commands = sandbox.runner.commands()
    set_policy = (
        f"powershell -NoProfile -Command {SET_POLICY} RemoteSigned -Scope CurrentUser -Force"
    )
    assert set_policy in commands
    assert f"claude plugin marketplace add {sandbox.repository.resolve()}" in commands
    assert "claude plugin install terminal-maths@claude-terminal-revamp --scope user" in commands
    assert commands.index(f"claude plugin marketplace add {sandbox.repository.resolve()}") < (
        commands.index("claude plugin install terminal-maths@claude-terminal-revamp --scope user")
    )


def test_install_with_the_real_config_fills_every_placeholder(
    real_config_sandbox: Sandbox,
) -> None:
    sandbox = real_config_sandbox
    report = install(sandbox.env())
    assert report.exit_code == 0
    command = sandbox.read_json(sandbox.claude)["statusLine"]["command"]
    assert "{" not in command
    assert command.endswith('statusline/statusline.py"')
    assert (sandbox.themes / "claude-warm.json").exists()


# Install into existing files


def test_install_preserves_existing_values_and_backs_up_each_file(sandbox: Sandbox) -> None:
    sandbox.write_json(
        sandbox.vscode, {"editor.fontSize": 12, "terminal.integrated.fontSize": 10}, 4
    )
    sandbox.write_json(sandbox.claude, {"model": "opus", "theme": "dark"}, 4)
    original_claude = sandbox.claude.read_text(encoding="utf-8")
    original_vscode = sandbox.vscode.read_text(encoding="utf-8")

    install(sandbox.env())

    vscode = sandbox.read_json(sandbox.vscode)
    assert vscode["editor.fontSize"] == 12
    assert vscode["terminal.integrated.fontSize"] == 14
    assert '\n  "editor.fontSize"' in sandbox.vscode.read_text(encoding="utf-8")
    claude_text = sandbox.claude.read_text(encoding="utf-8")
    assert '\n    "model": "opus"' in claude_text
    assert claude_text.endswith("}\n")
    claude_backup = sandbox.claude.with_name("settings.json.terminal-kit-20261110-093000.bak")
    vscode_backup = sandbox.vscode.with_name("settings.json.terminal-kit-20261110-093000.bak")
    assert claude_backup.read_text(encoding="utf-8") == original_claude
    assert vscode_backup.read_text(encoding="utf-8") == original_vscode


def test_install_merges_listed_keys_one_level_deep(sandbox: Sandbox) -> None:
    sandbox.write_json(
        sandbox.vscode,
        {
            "workbench.colorCustomizations": {
                "editor.background": "#000",
                "terminal.background": "#111",
            }
        },
    )
    install(sandbox.env())
    colours = sandbox.read_json(sandbox.vscode)["workbench.colorCustomizations"]
    assert colours["editor.background"] == "#000"
    assert colours["terminal.background"] == "#262624"
    assert colours["terminal.foreground"] == "#E8E6DC"


def test_second_install_keeps_the_original_previous_values(sandbox: Sandbox) -> None:
    original = {
        "terminal.integrated.fontSize": 10,
        "workbench.colorCustomizations": {"terminal.background": "#111"},
    }
    sandbox.write_json(sandbox.vscode, original)

    install(sandbox.env())
    install(sandbox.env())

    changes = sandbox.read_json(sandbox.state)["vscode"]
    font = next(c for c in changes if c["path"] == ["terminal.integrated.fontSize"])
    assert font["previous"] == 10
    uninstall(sandbox.uninstall_env())
    assert sandbox.read_json(sandbox.vscode) == original


# Refusals


@pytest.mark.parametrize("which", ["vscode", "claude"])
def test_a_settings_file_with_comments_stops_the_run_and_changes_nothing(
    sandbox: Sandbox, which: str
) -> None:
    broken = getattr(sandbox, which)
    other = sandbox.claude if which == "vscode" else sandbox.vscode
    broken.parent.mkdir(parents=True)
    broken.write_text('{\n  // a comment\n  "a": 1,\n}\n', encoding="utf-8")

    report = install(sandbox.env())

    assert report.exit_code == 2
    assert str(broken) in text_of(report)
    assert "line 2" in text_of(report)
    assert not other.exists()
    assert not sandbox.state.exists()
    assert not sandbox.themes.exists()
    assert not sandbox.profile.exists()
    assert sandbox.runner.calls == []
    assert broken.read_text(encoding="utf-8").startswith("{\n  // a comment")


def test_a_conflicting_theme_file_stops_the_run_before_any_write(sandbox: Sandbox) -> None:
    theme = sandbox.themes / "claude-warm.json"
    theme.parent.mkdir(parents=True)
    theme.write_text('{"mine": true}', encoding="utf-8")

    report = install(sandbox.env())

    assert report.exit_code == 2
    assert "claude-warm.json" in text_of(report)
    assert theme.read_text(encoding="utf-8") == '{"mine": true}'
    assert not sandbox.vscode.exists()
    assert not sandbox.claude.exists()
    assert not sandbox.state.exists()
    assert sandbox.runner.calls == []


def test_a_missing_repository_config_file_stops_the_run(sandbox: Sandbox) -> None:
    (sandbox.repository / "config" / "claude.json").unlink()
    report = install(sandbox.env())
    assert report.exit_code == 2
    assert "claude.json is missing" in text_of(report)


def test_a_profile_that_is_not_utf8_stops_the_run(sandbox: Sandbox) -> None:
    sandbox.profile.parent.mkdir(parents=True)
    sandbox.profile.write_bytes(b"\xff\xfe\x00")
    report = install(sandbox.env())
    assert report.exit_code == 2
    assert not sandbox.state.exists()
    assert not sandbox.vscode.exists()


def test_a_damaged_state_file_stops_install_and_uninstall(sandbox: Sandbox) -> None:
    sandbox.state.parent.mkdir(parents=True)
    sandbox.state.write_text('{"version": 9}', encoding="utf-8")
    assert install(sandbox.env()).exit_code == 2
    assert uninstall(sandbox.uninstall_env()).exit_code == 2
    assert sandbox.state.read_text(encoding="utf-8") == '{"version": 9}'


# Themes


def test_an_identical_theme_that_we_did_not_install_is_left_alone(sandbox: Sandbox) -> None:
    theme = sandbox.themes / "claude-warm.json"
    theme.parent.mkdir(parents=True)
    theme.write_bytes((sandbox.repository / "config/themes/claude-warm.json").read_bytes())

    assert install(sandbox.env()).exit_code == 0
    assert sandbox.read_json(sandbox.state)["themes"] == {}
    uninstall(sandbox.uninstall_env())
    assert theme.exists()


def test_a_theme_we_installed_is_replaced_on_reinstall(sandbox: Sandbox) -> None:
    theme = sandbox.themes / "claude-warm.json"
    install(sandbox.env())
    theme.write_text("{}", encoding="utf-8")
    install(sandbox.env())
    assert json.loads(theme.read_text(encoding="utf-8"))["name"] == "Claude Warm"


def test_uninstall_removes_the_themes_it_created(sandbox: Sandbox) -> None:
    install(sandbox.env())
    uninstall(sandbox.uninstall_env())
    assert not (sandbox.themes / "claude-warm.json").exists()


def test_uninstall_keeps_a_theme_whose_content_changed(sandbox: Sandbox) -> None:
    install(sandbox.env())
    theme = sandbox.themes / "claude-warm.json"
    theme.write_text('{"edited": true}', encoding="utf-8")
    report = uninstall(sandbox.uninstall_env())
    assert theme.exists()
    assert "Kept theme claude-warm.json" in text_of(report)


def test_uninstall_copes_with_a_theme_that_is_already_gone(sandbox: Sandbox) -> None:
    install(sandbox.env())
    (sandbox.themes / "claude-warm.json").unlink()
    report = uninstall(sandbox.uninstall_env())
    assert report.exit_code == 0
    assert "already gone" in text_of(report)


# PowerShell profile


def test_a_new_profile_is_written_as_utf8_with_a_byte_order_mark(sandbox: Sandbox) -> None:
    install(sandbox.env())
    assert sandbox.profile.read_bytes() == BOM + profile_block(sandbox, "\r\n") + b"\r\n"


def test_uninstall_deletes_a_profile_that_install_created(sandbox: Sandbox) -> None:
    install(sandbox.env())
    uninstall(sandbox.uninstall_env())
    assert not sandbox.profile.exists()


def test_uninstall_keeps_a_created_profile_the_user_added_to(sandbox: Sandbox) -> None:
    install(sandbox.env())
    with sandbox.profile.open("ab") as handle:
        handle.write(b"Set-Alias g git\r\n")
    uninstall(sandbox.uninstall_env())
    assert sandbox.profile.read_bytes() == BOM + b"Set-Alias g git\r\n"


def test_an_existing_profile_without_a_byte_order_mark_keeps_none(sandbox: Sandbox) -> None:
    original = b"Set-Alias a b\r\n"
    sandbox.profile.parent.mkdir(parents=True)
    sandbox.profile.write_bytes(original)

    install(sandbox.env())
    assert sandbox.profile.read_bytes() == original + profile_block(sandbox, "\r\n") + b"\r\n"
    uninstall(sandbox.uninstall_env())
    assert sandbox.profile.read_bytes() == original


def test_an_existing_profile_with_a_byte_order_mark_keeps_it(sandbox: Sandbox) -> None:
    original = BOM + b"x = 1"
    sandbox.profile.parent.mkdir(parents=True)
    sandbox.profile.write_bytes(original)

    install(sandbox.env())
    assert sandbox.profile.read_bytes().startswith(BOM)
    assert sandbox.profile.read_bytes().count(BOM) == 1
    uninstall(sandbox.uninstall_env())
    assert sandbox.profile.read_bytes() == original


def test_installing_twice_leaves_one_block_and_a_full_undo(sandbox: Sandbox) -> None:
    original = b"x = 1"
    sandbox.profile.parent.mkdir(parents=True)
    sandbox.profile.write_bytes(original)

    install(sandbox.env())
    install(sandbox.env())
    assert sandbox.profile.read_bytes().count(START_MARKER.encode()) == 1
    uninstall(sandbox.uninstall_env())
    assert sandbox.profile.read_bytes() == original


def test_installing_twice_into_a_new_profile_still_deletes_it_on_uninstall(
    sandbox: Sandbox,
) -> None:
    install(sandbox.env())
    install(sandbox.env())
    uninstall(sandbox.uninstall_env())
    assert not sandbox.profile.exists()


def test_a_changed_profile_path_is_recorded_afresh(sandbox: Sandbox, tmp_path: Path) -> None:
    install(sandbox.env())
    other = tmp_path / "other" / "profile.ps1"
    sandbox.runner.respond("$PROFILE", stdout=f"{other}\n")
    install(sandbox.env())
    assert sandbox.read_json(sandbox.state)["profile"]["path"] == str(other)


def test_uninstall_notes_a_profile_that_has_gone(sandbox: Sandbox) -> None:
    install(sandbox.env())
    sandbox.profile.unlink()
    report = uninstall(sandbox.uninstall_env())
    assert report.exit_code == 0
    assert "no longer exists" in text_of(report)


def test_uninstall_refuses_a_profile_that_is_not_utf8(sandbox: Sandbox) -> None:
    install(sandbox.env())
    sandbox.profile.write_bytes(b"\xff\xfe\x00")
    report = uninstall(sandbox.uninstall_env())
    assert report.exit_code == 2
    assert sandbox.state.exists()


@pytest.mark.parametrize(
    ("response", "fragment"),
    [
        (dict(returncode=1, stderr="no shell"), "no shell"),
        (dict(returncode=0, stdout="  \r\n"), "returned nothing"),
    ],
)
def test_a_profile_path_query_failure_is_reported_and_other_steps_still_run(
    sandbox: Sandbox, response: dict, fragment: str
) -> None:
    sandbox.runner.respond("$PROFILE", **response)
    report = install(sandbox.env())
    assert report.exit_code == 1
    assert fragment in text_of(report)
    assert sandbox.state.exists()
    assert sandbox.vscode.exists()
    assert not sandbox.profile.exists()
    assert "claude plugin install" in " ".join(sandbox.runner.commands())


# Execution policy


def test_a_restrictive_policy_is_set_and_restored(sandbox: Sandbox) -> None:
    install(sandbox.env())
    assert len(policy_commands(sandbox)) == 1
    assert sandbox.read_json(sandbox.state)["previous_execution_policy"] == "Restricted"

    uninstall(sandbox.uninstall_env())
    assert policy_commands(sandbox)[-1].endswith(
        "Set-ExecutionPolicy Restricted -Scope CurrentUser -Force"
    )


def test_an_undefined_policy_is_restored_as_undefined(sandbox: Sandbox) -> None:
    sandbox.runner.respond("Get-ExecutionPolicy", stdout="Undefined\r\n")
    install(sandbox.env())
    uninstall(sandbox.uninstall_env())
    assert "Set-ExecutionPolicy Undefined -Scope CurrentUser -Force" in policy_commands(sandbox)[-1]


@pytest.mark.parametrize("policy", ["RemoteSigned", "Unrestricted", "bypass"])
def test_a_permissive_policy_is_left_alone(sandbox: Sandbox, policy: str) -> None:
    sandbox.runner.respond("Get-ExecutionPolicy", stdout=f"{policy}\r\n")
    install(sandbox.env())
    uninstall(sandbox.uninstall_env())
    assert policy_commands(sandbox) == []


def test_a_second_install_keeps_the_original_policy(sandbox: Sandbox) -> None:
    install(sandbox.env())
    sandbox.runner.respond("Get-ExecutionPolicy", stdout="RemoteSigned\r\n")
    install(sandbox.env())
    assert sandbox.read_json(sandbox.state)["previous_execution_policy"] == "Restricted"


def test_a_failed_policy_query_is_reported(sandbox: Sandbox) -> None:
    sandbox.runner.respond("Get-ExecutionPolicy", returncode=1, stderr="blocked")
    report = install(sandbox.env())
    assert report.exit_code == 1
    assert "blocked" in text_of(report)
    assert policy_commands(sandbox) == []


def test_unexpected_policy_output_is_reported(sandbox: Sandbox) -> None:
    sandbox.runner.respond("Get-ExecutionPolicy", stdout="two words\r\n")
    report = install(sandbox.env())
    assert report.exit_code == 1
    assert "two words" in text_of(report)


def test_a_failed_policy_change_is_reported_and_not_recorded(sandbox: Sandbox) -> None:
    sandbox.runner.respond(SET_POLICY, returncode=1, stderr="denied")
    report = install(sandbox.env())
    assert report.exit_code == 1
    assert "denied" in text_of(report)
    assert sandbox.read_json(sandbox.state)["previous_execution_policy"] is None
    assert sandbox.profile.exists()


def test_a_failed_policy_restore_is_reported(sandbox: Sandbox) -> None:
    install(sandbox.env())
    sandbox.runner.respond(SET_POLICY, returncode=1, stderr="locked")
    report = uninstall(sandbox.uninstall_env())
    assert report.exit_code == 1
    assert "locked" in text_of(report)
    assert not sandbox.state.exists()


# Plugin


def test_a_failing_plugin_command_gives_exit_one_and_later_steps_still_run(
    sandbox: Sandbox,
) -> None:
    sandbox.runner.respond("marketplace add", returncode=1, stderr="boom")

    report = install(sandbox.env())

    assert report.exit_code == 1
    assert "boom" in text_of(report)
    assert "claude plugin install" in " ".join(sandbox.runner.commands())
    assert (sandbox.themes / "claude-warm.json").exists()
    assert sandbox.profile.exists()
    plugin = sandbox.read_json(sandbox.state)["plugin"]
    assert plugin == {"marketplace_added": False, "installed": True}


def test_a_failing_plugin_install_is_recorded_as_not_installed(sandbox: Sandbox) -> None:
    sandbox.runner.respond("plugin install", returncode=1, stderr="no such plugin")
    report = install(sandbox.env())
    assert report.exit_code == 1
    plugin = sandbox.read_json(sandbox.state)["plugin"]
    assert plugin == {"marketplace_added": True, "installed": False}
    uninstall(sandbox.uninstall_env())
    commands = " | ".join(sandbox.runner.commands())
    assert "plugin uninstall" not in commands
    assert "marketplace remove claude-terminal-revamp" in commands


def test_uninstall_removes_the_plugin_then_the_marketplace(sandbox: Sandbox) -> None:
    install(sandbox.env())
    sandbox.runner.calls.clear()
    uninstall(sandbox.uninstall_env())
    plugin_calls = [c for c in sandbox.runner.commands() if c.startswith("claude")]
    assert plugin_calls == [
        "claude plugin uninstall terminal-maths@claude-terminal-revamp --scope user",
        "claude plugin marketplace remove claude-terminal-revamp",
    ]


def test_a_failing_plugin_uninstall_is_reported_and_the_state_is_still_deleted(
    sandbox: Sandbox,
) -> None:
    install(sandbox.env())
    sandbox.runner.respond("plugin uninstall", returncode=1, stderr="nope")
    report = uninstall(sandbox.uninstall_env())
    assert report.exit_code == 1
    assert "nope" in text_of(report)
    assert "Removed the marketplace" in text_of(report)
    assert not sandbox.state.exists()


# Uninstall


def test_uninstall_restores_values_and_deletes_keys_that_were_absent(sandbox: Sandbox) -> None:
    sandbox.write_json(sandbox.claude, {"theme": "dark", "model": "opus"})
    original = sandbox.claude.read_text(encoding="utf-8")
    install(sandbox.env())

    report = uninstall(sandbox.uninstall_env())

    assert report.exit_code == 0
    assert sandbox.read_json(sandbox.claude) == {"theme": "dark", "model": "opus"}
    assert sandbox.read_json(sandbox.vscode) == {}
    backup = sandbox.claude.with_name("settings.json.terminal-kit-20261110-104505.bak")
    assert backup.exists()
    assert backup.read_text(encoding="utf-8") != original
    assert not sandbox.state.exists()


def test_uninstall_keeps_a_value_the_user_changed_and_lists_it(sandbox: Sandbox) -> None:
    sandbox.write_json(sandbox.vscode, {"terminal.integrated.fontSize": 10})
    install(sandbox.env())
    settings = sandbox.read_json(sandbox.vscode)
    settings["terminal.integrated.fontSize"] = 20
    sandbox.write_json(sandbox.vscode, settings)

    report = uninstall(sandbox.uninstall_env())

    assert sandbox.read_json(sandbox.vscode) == {"terminal.integrated.fontSize": 20}
    assert "Left your newer value for terminal.integrated.fontSize" in text_of(report)


def test_uninstall_lists_a_key_the_user_deleted(sandbox: Sandbox) -> None:
    install(sandbox.env())
    settings = sandbox.read_json(sandbox.claude)
    del settings["theme"]
    sandbox.write_json(sandbox.claude, settings)
    report = uninstall(sandbox.uninstall_env())
    assert "Left your newer value for theme" in text_of(report)


def test_uninstall_copes_with_a_settings_file_that_has_gone(sandbox: Sandbox) -> None:
    install(sandbox.env())
    sandbox.vscode.unlink()
    report = uninstall(sandbox.uninstall_env())
    assert report.exit_code == 0
    assert not sandbox.vscode.exists()


def test_uninstall_refuses_settings_that_are_not_strict_json_and_changes_nothing(
    sandbox: Sandbox,
) -> None:
    install(sandbox.env())
    sandbox.claude.write_text('{\n  "a": 1,\n}\n', encoding="utf-8")
    sandbox.runner.calls.clear()

    report = uninstall(sandbox.uninstall_env())

    assert report.exit_code == 2
    assert sandbox.state.exists()
    assert (sandbox.themes / "claude-warm.json").exists()
    assert sandbox.runner.calls == []


def test_uninstall_without_a_state_file_has_nothing_to_undo(sandbox: Sandbox) -> None:
    report = uninstall(sandbox.uninstall_env())
    assert report.exit_code == 0
    assert "Nothing to undo" in text_of(report)
    assert sandbox.runner.calls == []
    assert not sandbox.vscode.exists()


# Other platforms


def test_other_platforms_skip_the_powershell_steps(linux_sandbox: Sandbox) -> None:
    sandbox = linux_sandbox
    report = install(sandbox.env())

    assert report.exit_code == 0
    assert "not Windows" in text_of(report)
    assert sandbox.vscode == sandbox.home / ".config/Code/User/settings.json"
    assert sandbox.vscode.exists()
    assert not sandbox.profile.exists()
    assert not any("powershell" in c for c in sandbox.runner.commands())
    assert any(c.startswith("claude plugin install") for c in sandbox.runner.commands())
    state = sandbox.read_json(sandbox.state)
    assert state["profile"] is None
    assert state["previous_execution_policy"] is None


def test_uninstall_on_another_platform_reverses_install_without_powershell(
    linux_sandbox: Sandbox,
) -> None:
    sandbox = linux_sandbox
    sandbox.write_json(sandbox.claude, {"theme": "dark"})
    install(sandbox.env())
    report = uninstall(sandbox.uninstall_env())
    assert report.exit_code == 0
    assert sandbox.read_json(sandbox.claude) == {"theme": "dark"}
    assert not any("powershell" in c for c in sandbox.runner.commands())


def test_uninstall_skips_the_marketplace_when_it_was_never_added(sandbox: Sandbox) -> None:
    sandbox.runner.respond("marketplace add", returncode=1, stderr="boom")
    install(sandbox.env())
    sandbox.runner.calls.clear()
    uninstall(sandbox.uninstall_env())
    claude_calls = [c for c in sandbox.runner.commands() if c.startswith("claude")]
    assert claude_calls == [
        "claude plugin uninstall terminal-maths@claude-terminal-revamp --scope user"
    ]
