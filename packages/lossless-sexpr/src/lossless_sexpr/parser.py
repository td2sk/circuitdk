from __future__ import annotations

from .diagnostics import ParseError
from .nodes import AtomNode, Document, ListNode, Node
from .tokens import Token, TokenKind, tokenize


def parse(source: str) -> Document:
    tokens = tokenize(source)
    index = 0

    def parse_list() -> ListNode:
        nonlocal index
        opening = tokens[index]
        index += 1
        elements: list[Token | Node] = []
        while index < len(tokens):
            token = tokens[index]
            if token.kind is TokenKind.RIGHT_PAREN:
                index += 1
                return ListNode(opening, tuple(elements), token)
            if token.kind is TokenKind.LEFT_PAREN:
                elements.append(parse_list())
            elif token.kind in {TokenKind.ATOM, TokenKind.STRING}:
                elements.append(AtomNode(token))
                index += 1
            else:
                elements.append(token)
                index += 1
        raise ParseError("unclosed list", source, opening.span.start)

    elements: list[Token | Node] = []
    while index < len(tokens):
        token = tokens[index]
        if token.kind is TokenKind.RIGHT_PAREN:
            raise ParseError("unexpected closing parenthesis", source, token.span.start)
        if token.kind is TokenKind.LEFT_PAREN:
            elements.append(parse_list())
        elif token.kind in {TokenKind.ATOM, TokenKind.STRING}:
            elements.append(AtomNode(token))
            index += 1
        else:
            elements.append(token)
            index += 1
    return Document(source, tuple(elements))
