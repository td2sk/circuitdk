from __future__ import annotations

from dataclasses import dataclass

from .nodes import SourceSpan


class EditConflictError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class TextEdit:
    span: SourceSpan
    replacement: str

    @classmethod
    def replace(cls, start: int, end: int, replacement: str) -> TextEdit:
        return cls(SourceSpan(start, end), replacement)


def apply_edits(source: str, edits: list[TextEdit] | tuple[TextEdit, ...]) -> str:
    ordered = sorted(edits, key=lambda edit: (edit.span.start, edit.span.end))
    previous_end = 0
    for edit in ordered:
        if edit.span.end > len(source):
            raise ValueError("edit extends beyond source")
        if edit.span.start < previous_end:
            raise EditConflictError("text edits overlap")
        previous_end = edit.span.end

    result = source
    for edit in reversed(ordered):
        result = result[: edit.span.start] + edit.replacement + result[edit.span.end :]
    return result
