from __future__ import annotations

import pytest

from lossless_sexpr import EditConflictError, ParseError, TextEdit, apply_edits, parse


def test_round_trip_is_byte_for_byte_lossless() -> None:
    source = '(root\n  ; unknown syntax stays here\n  (child "a\\"b" 1.00)\n)\n'

    document = parse(source)

    assert document.render() == source
    assert document.lists("child")[0].atom(1).value == 'a"b'  # type: ignore[union-attr]


def test_minimal_edit_changes_only_selected_atom() -> None:
    source = '(property "Value" "10 k" (at 1 2))'
    value = parse(source).lists("property")[0].atom(2)
    assert value is not None

    result = apply_edits(source, [TextEdit(value.span, '"47 k"')])

    assert result == '(property "Value" "47 k" (at 1 2))'
    assert parse(result).render() == result


def test_overlapping_edits_are_rejected() -> None:
    with pytest.raises(EditConflictError):
        apply_edits("abcdef", [TextEdit.replace(1, 4, "x"), TextEdit.replace(3, 5, "y")])


@pytest.mark.parametrize("source", ["(open", ")", '(x "open)'])
def test_invalid_input_has_source_location(source: str) -> None:
    with pytest.raises(ParseError, match=r"at 1:"):
        parse(source)
