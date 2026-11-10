from installer.merge import (
    ONE_LEVEL_KEYS,
    Change,
    fill_placeholders,
    merge_settings,
    revert_settings,
)


def test_fill_placeholders_reaches_strings_inside_lists_and_objects() -> None:
    value = {"a": ["{x}/one", 3, {"b": "{x}"}], "c": True}
    assert fill_placeholders(value, {"{x}": "y"}) == {"a": ["y/one", 3, {"b": "y"}], "c": True}


def test_merge_sets_top_level_keys_whole_and_records_previous_values() -> None:
    merged, changes = merge_settings(
        {"size": 10, "keep": 1, "list": [1]}, {"size": 14, "list": [2], "new": True}, set(), []
    )
    assert merged == {"size": 14, "keep": 1, "list": [2], "new": True}
    by_path = {change.path: change for change in changes}
    assert by_path[("size",)] == Change(("size",), 10, False, 14)
    assert by_path[("new",)] == Change(("new",), None, True, True)


def test_merge_goes_one_level_deep_for_listed_keys() -> None:
    current = {"workbench.colorCustomizations": {"editor.background": "#000", "x": "old"}}
    incoming = {"workbench.colorCustomizations": {"x": "new", "y": "added"}}
    merged, changes = merge_settings(current, incoming, ONE_LEVEL_KEYS, [])
    assert merged["workbench.colorCustomizations"] == {
        "editor.background": "#000",
        "x": "new",
        "y": "added",
    }
    assert {change.path for change in changes} == {
        ("workbench.colorCustomizations", "x"),
        ("workbench.colorCustomizations", "y"),
    }


def test_merge_sets_a_listed_key_whole_when_the_user_has_none() -> None:
    merged, changes = merge_settings({}, {"k": {"a": 1}}, {"k"}, [])
    assert merged == {"k": {"a": 1}}
    assert [change.path for change in changes] == [("k",)]


def test_merge_replaces_a_listed_key_that_is_not_an_object() -> None:
    merged, changes = merge_settings({"k": "text"}, {"k": {"a": 1}}, {"k"}, [])
    assert merged == {"k": {"a": 1}}
    assert changes[0].previous == "text"


def test_merge_keeps_the_original_previous_value_on_a_second_run() -> None:
    first, first_changes = merge_settings({"size": 10}, {"size": 14}, set(), [])
    second, second_changes = merge_settings(first, {"size": 16}, set(), first_changes)
    assert second == {"size": 16}
    assert second_changes == [Change(("size",), 10, False, 16)]


def test_merge_keeps_a_whole_key_record_after_the_key_became_an_object() -> None:
    first, first_changes = merge_settings({}, {"k": {"a": 1}}, {"k"}, [])
    _, second_changes = merge_settings(first, {"k": {"a": 2}}, {"k"}, first_changes)
    assert second_changes == [Change(("k",), None, True, {"a": 2})]


def test_merge_carries_forward_records_for_keys_no_longer_in_the_config() -> None:
    _, first_changes = merge_settings({}, {"old": 1}, set(), [])
    _, second_changes = merge_settings({"old": 1}, {"new": 2}, set(), first_changes)
    assert {change.path for change in second_changes} == {("old",), ("new",)}


def test_merge_does_not_change_its_inputs() -> None:
    current = {"k": {"a": 1}}
    merge_settings(current, {"k": {"a": 2}}, {"k"}, [])
    assert current == {"k": {"a": 1}}


def test_revert_restores_previous_and_deletes_absent_keys() -> None:
    original = {"size": 10, "nest": {"a": 1}}
    incoming = {"size": 14, "new": 1, "nest": {"a": 2, "b": 3}}
    merged, changes = merge_settings(original, incoming, {"nest"}, [])
    reverted, left_alone = revert_settings(merged, changes)
    assert reverted == original
    assert left_alone == []


def test_revert_leaves_a_value_the_user_changed() -> None:
    merged, changes = merge_settings({"size": 10}, {"size": 14}, set(), [])
    merged["size"] = 20
    reverted, left_alone = revert_settings(merged, changes)
    assert reverted == {"size": 20}
    assert [change.path for change in left_alone] == [("size",)]


def test_revert_leaves_a_key_the_user_deleted() -> None:
    _, changes = merge_settings({"size": 10}, {"size": 14}, set(), [])
    reverted, left_alone = revert_settings({}, changes)
    assert reverted == {}
    assert len(left_alone) == 1


def test_revert_does_not_treat_true_as_equal_to_one() -> None:
    _, changes = merge_settings({}, {"flag": 1}, set(), [])
    reverted, left_alone = revert_settings({"flag": True}, changes)
    assert reverted == {"flag": True}
    assert len(left_alone) == 1
