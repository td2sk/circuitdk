from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SourceLocation:
    offset: int
    line: int
    column: int


class ParseError(ValueError):
    """A syntax error carrying a precise source location."""

    def __init__(self, message: str, source: str, offset: int) -> None:
        line = source.count("\n", 0, offset) + 1
        line_start = source.rfind("\n", 0, offset) + 1
        self.location = SourceLocation(offset, line, offset - line_start + 1)
        super().__init__(f"{message} at {line}:{self.location.column}")
