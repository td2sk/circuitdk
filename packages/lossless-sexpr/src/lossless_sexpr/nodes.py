from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .tokens import Token


@dataclass(frozen=True, slots=True)
class SourceSpan:
    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start < 0 or self.end < self.start:
            raise ValueError("invalid source span")


@dataclass(frozen=True, slots=True)
class AtomNode:
    token: Token

    @property
    def span(self) -> SourceSpan:
        return self.token.span

    @property
    def raw(self) -> str:
        return self.token.text

    @property
    def value(self) -> str:
        from .strings import unquote
        from .tokens import TokenKind

        return unquote(self.raw) if self.token.kind is TokenKind.STRING else self.raw


@dataclass(frozen=True, slots=True)
class ListNode:
    opening: Token
    elements: tuple[Token | AtomNode | ListNode, ...]
    closing: Token

    @property
    def span(self) -> SourceSpan:
        return SourceSpan(self.opening.span.start, self.closing.span.end)

    def children(self) -> tuple[Node, ...]:
        return tuple(item for item in self.elements if isinstance(item, (AtomNode, ListNode)))

    @property
    def head(self) -> str | None:
        children = self.children()
        if children and isinstance(children[0], AtomNode):
            return children[0].value
        return None

    def child_lists(self, head: str | None = None) -> tuple[ListNode, ...]:
        items = tuple(item for item in self.children() if isinstance(item, ListNode))
        if head is None:
            return items
        return tuple(item for item in items if item.head == head)

    def first_list(self, head: str) -> ListNode | None:
        return next(iter(self.child_lists(head)), None)

    def atom(self, index: int) -> AtomNode | None:
        children = self.children()
        if index < 0 or index >= len(children):
            return None
        child = children[index]
        return child if isinstance(child, AtomNode) else None

    def walk(self, head: str | None = None) -> Iterator[ListNode]:
        if head is None or self.head == head:
            yield self
        for child in self.child_lists():
            yield from child.walk(head)


Node = AtomNode | ListNode


@dataclass(frozen=True, slots=True)
class Document:
    source: str
    elements: tuple[Token | Node, ...]

    def render(self) -> str:
        return self.source

    def roots(self) -> tuple[Node, ...]:
        return tuple(item for item in self.elements if isinstance(item, (AtomNode, ListNode)))

    def lists(self, head: str | None = None) -> tuple[ListNode, ...]:
        result: list[ListNode] = []
        for root in self.roots():
            if isinstance(root, ListNode):
                result.extend(root.walk(head))
        return tuple(result)
