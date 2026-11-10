import pytest

from installer.model import InstallerError
from installer.profile import (
    BOM,
    END_MARKER,
    START_MARKER,
    ProfileText,
    decode_profile,
    encode_profile,
    insert_block,
    remove_block,
)

SCRIPT = "C:/repo/config/prompt.ps1"


def block(eol: str, script: str = SCRIPT) -> str:
    return eol.join([START_MARKER, f". '{script}'", END_MARKER])


def test_insert_into_an_empty_profile_uses_windows_line_endings() -> None:
    text, added_break = insert_block("", SCRIPT)
    assert text == block("\r\n") + "\r\n"
    assert added_break is False


def test_insert_appends_after_existing_lines() -> None:
    text, added_break = insert_block("a = 1\r\nb = 2\r\n", SCRIPT)
    assert text == "a = 1\r\nb = 2\r\n" + block("\r\n") + "\r\n"
    assert added_break is False


def test_insert_adds_a_line_break_when_the_file_has_no_final_newline() -> None:
    text, added_break = insert_block("a = 1", SCRIPT)
    assert text == "a = 1\n" + block("\n") + "\n"
    assert added_break is True


def test_insert_replaces_an_existing_block_and_keeps_everything_else() -> None:
    old = "top\r\n" + block("\r\n", "C:/old/prompt.ps1") + "\r\nbottom\r\n"
    text, added_break = insert_block(old, SCRIPT)
    assert text == "top\r\n" + block("\r\n") + "\r\nbottom\r\n"
    assert added_break is False


def test_insert_replaces_a_block_that_ends_the_file_without_a_newline() -> None:
    old = "top\n" + block("\n", "C:/old/prompt.ps1")
    text, _ = insert_block(old, SCRIPT)
    assert text == "top\n" + block("\n")


def test_insert_doubles_a_single_quote_in_the_path() -> None:
    text, _ = insert_block("", "C:/O'Neil/prompt.ps1")
    assert ". 'C:/O''Neil/prompt.ps1'" in text


@pytest.mark.parametrize("original", ["", "a = 1\r\n", "a = 1\n", "a = 1", "a = 1\r\nb = 2"])
def test_remove_restores_the_original_text_exactly(original: str) -> None:
    inserted, added_break = insert_block(original, SCRIPT)
    assert remove_block(inserted, added_break) == original


def test_remove_keeps_a_line_break_when_text_follows_the_block() -> None:
    inserted, _ = insert_block("a = 1", SCRIPT)
    edited = inserted + "later = 2\n"
    assert remove_block(edited, True) == "a = 1\nlater = 2\n"


def test_remove_without_a_block_returns_the_text_unchanged() -> None:
    assert remove_block("a = 1\n", False) == "a = 1\n"


@pytest.mark.parametrize("has_bom", [True, False])
def test_decode_and_encode_round_trip_the_byte_order_mark(has_bom: bool) -> None:
    data = (BOM if has_bom else b"") + "caf\u00e9 = 1\r\n".encode()
    decoded = decode_profile(data, "profile")
    assert decoded == ProfileText("caf\u00e9 = 1\r\n", has_bom)
    assert encode_profile(decoded) == data


def test_decode_rejects_bytes_that_are_not_utf8() -> None:
    with pytest.raises(InstallerError, match="not valid UTF-8"):
        decode_profile(b"\xff\xfe\x00", "profile")
