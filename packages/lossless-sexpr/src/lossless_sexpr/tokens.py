from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from .nodes import SourceSpan


class TokenKind(Enum):
    LEFT_PAREN = auto()
    RIGHT_PAREN = auto()
    ATOM = auto()
    STRING = auto()
    WHITESPACE = auto()
    COMMENT = auto()


@dataclass(frozen=True, slots=True)
class Token:
    kind: TokenKind
    text: str
    span: SourceSpan

    @property
    def is_trivia(self) -> bool:
        return self.kind in {TokenKind.WHITESPACE, TokenKind.COMMENT}


def tokenize(source: str) -> tuple[Token, ...]:
    tokens: list[Token] = []
    index = 0
    length = len(source)
    while index < length:
        start = index
        char = source[index]
        if char.isspace():
            index += 1
            while index < length and source[index].isspace():
                index += 1
            kind = TokenKind.WHITESPACE
        elif char == ";":
            index += 1
            while index < length and source[index] not in "\r\n":
                index += 1
            kind = TokenKind.COMMENT
        elif char == "(":
            index += 1
            kind = TokenKind.LEFT_PAREN
        elif char == ")":
            index += 1
            kind = TokenKind.RIGHT_PAREN
        elif char == '"':
            index += 1
            escaped = False
            while index < length:
                current = source[index]
                index += 1
                if escaped:
                    escaped = False
                elif current == "\\":
                    escaped = True
                elif current == '"':
                    break
            else:
                from .diagnostics import ParseError

                raise ParseError("unterminated string", source, start)
            kind = TokenKind.STRING
        else:
            index += 1
            while index < length:
                current = source[index]
                if current.isspace() or current in "();":
                    break
                index += 1
            kind = TokenKind.ATOM
        tokens.append(Token(kind, source[start:index], SourceSpan(start, index)))
    return tuple(tokens)
