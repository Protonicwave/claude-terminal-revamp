from pathlib import Path

import pytest

from installer.jsonio import detect_indent, dumps, parse_object, read_required_object
from installer.model import InstallerError


def test_parse_object_names_the_file_and_line_of_a_comment() -> None:
    with pytest.raises(InstallerError, match=r"settings\.json is not strict JSON \(line 2"):
        parse_object('{\n  // note\n  "a": 1\n}', "settings.json")


def test_parse_object_rejects_a_trailing_comma() -> None:
    with pytest.raises(InstallerError, match="line 3"):
        parse_object('{\n  "a": 1,\n}', "settings.json")


def test_parse_object_rejects_a_top_level_list() -> None:
    with pytest.raises(InstallerError, match="got list"):
        parse_object("[]", "settings.json")


def test_read_required_object_rejects_a_missing_file(tmp_path: Path) -> None:
    with pytest.raises(InstallerError, match="is missing"):
        read_required_object(tmp_path / "absent.json")


def test_read_required_object_reads_a_file_with_a_byte_order_mark(tmp_path: Path) -> None:
    path = tmp_path / "bom.json"
    path.write_bytes(b"\xef\xbb\xbf" + b'{"a": 1}')
    assert read_required_object(path) == {"a": 1}


@pytest.mark.parametrize(
    ("text", "expected"),
    [('{\n    "a": 1\n}', "    "), ('{\n\t"a": 1\n}', "\t"), ('{"a": 1}', 2), ("", 2)],
)
def test_detect_indent(text: str, expected: str | int) -> None:
    assert detect_indent(text) == expected


def test_dumps_keeps_non_ascii_and_ends_with_a_newline() -> None:
    assert dumps({"a": "café"}, 4) == '{\n    "a": "café"\n}\n'
