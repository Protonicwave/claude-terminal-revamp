"""Effects: files and commands. Decisions live in the pure modules."""

import hashlib
import re
import shutil
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path

from installer.jsonio import dumps, parse_object
from installer.model import InstallerError, JsonObject, Runner
from installer.state import POLICY_NAME, State, dump_state

POWERSHELL = "powershell"
CLAUDE = "claude"
MARKETPLACE_NAME = "claude-terminal-revamp"
PLUGIN_SPEC = "terminal-maths@claude-terminal-revamp"
PERMISSIVE_POLICIES = frozenset({"remotesigned", "unrestricted", "bypass"})
TARGET_POLICY = "RemoteSigned"


@dataclass(frozen=True, slots=True)
class Outcome:
    ok: bool
    output: str
    failure: str


def run_step(run: Runner, argv: list[str], label: str) -> Outcome:
    result = run(argv)
    if result.returncode == 0:
        return Outcome(True, result.stdout.strip(), "")
    failure = f"{label} failed with exit code {result.returncode}: {result.stderr.strip()}"
    return Outcome(False, "", failure)


def query_execution_policy(run: Runner) -> Outcome:
    argv = [POWERSHELL, "-NoProfile", "-Command", "Get-ExecutionPolicy -Scope CurrentUser"]
    outcome = run_step(run, argv, "Reading the execution policy")
    if outcome.ok and not POLICY_NAME.fullmatch(outcome.output):
        return Outcome(False, "", f"Execution policy query returned {outcome.output!r}")
    return outcome


def set_execution_policy(run: Runner, policy: str) -> Outcome:
    command = f"Set-ExecutionPolicy {policy} -Scope CurrentUser -Force"
    argv = [POWERSHELL, "-NoProfile", "-Command", command]
    return run_step(run, argv, f"Setting the execution policy to {policy}")


def query_profile_path(run: Runner) -> Outcome:
    argv = [POWERSHELL, "-NoProfile", "-Command", "$PROFILE"]
    outcome = run_step(run, argv, "Reading the PowerShell profile path")
    if outcome.ok and not outcome.output:
        return Outcome(False, "", "The PowerShell profile path query returned nothing")
    return outcome


def lists_name(output: str, name: str) -> bool:
    """Whether a `claude plugin ... list` output names exactly this marketplace or plugin."""
    return re.search(rf"(?<![\w.-]){re.escape(name)}(?![\w.-])", output) is not None


def record_state(path: Path, state: State) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_state(state), encoding="utf-8", newline="\n")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True, slots=True)
class LoadedSettings:
    path: Path
    doc: JsonObject
    text: str


def load_settings(path: Path) -> LoadedSettings:
    if not path.exists():
        return LoadedSettings(path, {}, "")
    text = path.read_text(encoding="utf-8-sig")
    return LoadedSettings(path, parse_object(text, str(path)), text)


def write_settings(
    stamp: str, loaded: LoadedSettings, new_doc: JsonObject, indent: str | int
) -> list[str]:
    path = loaded.path
    if new_doc == loaded.doc:
        return [f"Unchanged: {path}"]
    lines: list[str] = []
    if path.exists():
        backup = path.with_name(f"{path.name}.terminal-kit-{stamp}.bak")
        shutil.copy2(path, backup)
        lines.append(f"Backed up {path} to {backup.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(new_doc, indent), encoding="utf-8", newline="\n")
    lines.append(f"Wrote {path}")
    return lines


@dataclass(frozen=True, slots=True)
class ThemeWrite:
    destination: Path
    content: bytes


def plan_themes(source_dir: Path, themes_dir: Path, recorded: Collection[str]) -> list[ThemeWrite]:
    """Choose the theme files to write, refusing to overwrite a file that is not ours."""
    writes: list[ThemeWrite] = []
    for source in sorted(source_dir.glob("*.json")):
        content = source.read_bytes()
        destination = themes_dir / source.name
        if destination.exists() and source.name not in recorded:
            if destination.read_bytes() != content:
                raise InstallerError(
                    f"{destination} exists with different content and was not installed by "
                    "this kit; move it aside and run again"
                )
            continue
        writes.append(ThemeWrite(destination, content))
    return writes


def write_themes(writes: list[ThemeWrite]) -> list[str]:
    lines: list[str] = []
    for write in writes:
        write.destination.parent.mkdir(parents=True, exist_ok=True)
        write.destination.write_bytes(write.content)
        lines.append(f"Installed theme {write.destination.name}")
    return lines
