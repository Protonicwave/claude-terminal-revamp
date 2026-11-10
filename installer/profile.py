"""Pure handling of the marked block in a PowerShell profile."""

import re
from dataclasses import dataclass

from installer.model import InstallerError

START_MARKER = "# >>> claude-terminal-revamp >>>"
END_MARKER = "# <<< claude-terminal-revamp <<<"
BOM = b"\xef\xbb\xbf"

_BLOCK_PATTERN = re.compile(
    rf"^{re.escape(START_MARKER)}.*?^{re.escape(END_MARKER)}[^\r\n]*(?P<terminator>\r\n|\n)?",
    re.MULTILINE | re.DOTALL,
)


@dataclass(frozen=True, slots=True)
class ProfileText:
    text: str
    has_bom: bool


def decode_profile(data: bytes, label: str) -> ProfileText:
    has_bom = data.startswith(BOM)
    body = data[len(BOM) :] if has_bom else data
    try:
        return ProfileText(body.decode("utf-8"), has_bom)
    except UnicodeDecodeError as err:
        raise InstallerError(f"{label} is not valid UTF-8, so its block cannot be edited") from err


def encode_profile(profile: ProfileText) -> bytes:
    body = profile.text.encode("utf-8")
    return BOM + body if profile.has_bom else body


def _line_ending(text: str) -> str:
    # An empty profile is only ever created on Windows, where CRLF is the convention.
    return "\n" if text and "\r\n" not in text else "\r\n"


def _render_block(script_path: str, eol: str) -> str:
    quoted = script_path.replace("'", "''")
    return eol.join([START_MARKER, f". '{quoted}'", END_MARKER])


def insert_block(text: str, script_path: str) -> tuple[str, bool]:
    """Insert or replace the block. The flag says whether a line break was added before it."""
    eol = _line_ending(text)
    block = _render_block(script_path, eol)
    match = _BLOCK_PATTERN.search(text)
    if match:
        terminator = match.group("terminator") or ""
        return text[: match.start()] + block + terminator + text[match.end() :], False
    lead = eol if text and not text.endswith("\n") else ""
    return text + lead + block + eol, bool(lead)


def remove_block(text: str, leading_break_added: bool) -> str:
    match = _BLOCK_PATTERN.search(text)
    if not match:
        return text
    before, after = text[: match.start()], text[match.end() :]
    if leading_break_added and not after:
        # The break was added by the install, and the block is still the last thing in the file.
        before = before.removesuffix("\n").removesuffix("\r")
    return before + after
