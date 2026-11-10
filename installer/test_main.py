from pathlib import Path

import pytest

import install
from installer.conftest import FakeRunner


@pytest.fixture
def runner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeRunner:
    fake = FakeRunner()
    monkeypatch.setattr(install, "run_command", fake)
    monkeypatch.setattr(install.sys, "platform", "linux")
    monkeypatch.setattr(install.Path, "home", lambda: tmp_path)
    return fake


def test_a_refusal_prints_nothing_was_changed_and_exits_two(
    runner: FakeRunner, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    settings = tmp_path / ".config" / "Code" / "User" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text("{", encoding="utf-8")

    assert install.main([]) == 2

    output = capsys.readouterr().out
    assert output.startswith("Nothing was changed. ")
    assert str(settings) in output
    assert runner.calls == []
    assert not (tmp_path / ".claude" / "terminal-kit-state.json").exists()


def test_uninstall_without_a_state_file_prints_the_report_and_exits_zero(
    runner: FakeRunner, capsys: pytest.CaptureFixture[str]
) -> None:
    assert install.main(["--uninstall"]) == 0
    assert "Nothing to undo" in capsys.readouterr().out
    assert runner.calls == []
