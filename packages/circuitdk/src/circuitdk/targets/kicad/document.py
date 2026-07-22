from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lossless_sexpr import AtomNode, Document, ListNode, TextEdit, parse, quote

MANAGED_ID_PROPERTY = "CircuitDK:ID"


@dataclass(frozen=True, slots=True)
class KicadProperty:
    node: ListNode

    @property
    def name_atom(self) -> AtomNode:
        atom = self.node.atom(1)
        if atom is None:
            raise ValueError("malformed KiCad property: missing name")
        return atom

    @property
    def value_atom(self) -> AtomNode:
        atom = self.node.atom(2)
        if atom is None:
            raise ValueError("malformed KiCad property: missing value")
        return atom

    @property
    def name(self) -> str:
        return self.name_atom.value

    @property
    def value(self) -> str:
        return self.value_atom.value

    def set_value(self, value: str) -> TextEdit:
        return TextEdit(self.value_atom.span, quote(value))


@dataclass(frozen=True, slots=True)
class KicadSymbol:
    node: ListNode

    @property
    def library_id_node(self) -> ListNode:
        node = self.node.first_list("lib_id")
        if node is None:
            raise ValueError("malformed schematic symbol: missing lib_id")
        return node

    @property
    def library_id_atom(self) -> AtomNode:
        atom = self.library_id_node.atom(1)
        if atom is None:
            raise ValueError("malformed schematic symbol: empty lib_id")
        return atom

    @property
    def library_id(self) -> str:
        return self.library_id_atom.value

    @property
    def uuid(self) -> str:
        node = self.node.first_list("uuid")
        atom = node.atom(1) if node is not None else None
        if atom is None:
            raise ValueError("malformed schematic symbol: missing uuid")
        return atom.value

    @property
    def properties(self) -> tuple[KicadProperty, ...]:
        return tuple(KicadProperty(node) for node in self.node.child_lists("property"))

    @property
    def reference(self) -> str | None:
        value = self.find_property("Reference")
        return value.value if value is not None else None

    @property
    def position(self) -> tuple[float, float, float]:
        node = self.node.first_list("at")

        def value(index: int) -> float:
            atom = node.atom(index) if node is not None else None
            return float(atom.value) if atom is not None else 0.0

        return value(1), value(2), value(3)

    @property
    def mirror(self) -> str | None:
        node = self.node.first_list("mirror")
        atom = node.atom(1) if node is not None else None
        return atom.value if atom is not None else None

    def find_property(self, name: str) -> KicadProperty | None:
        return next((item for item in self.properties if item.name == name), None)

    @property
    def property_insertion_offset(self) -> int:
        anchors = [
            node.span.start for head in ("pin", "instances") for node in self.node.child_lists(head)
        ]
        return min(anchors, default=self.node.closing.span.start)

    @property
    def circuit_id(self) -> str | None:
        prop = self.find_property(MANAGED_ID_PROPERTY)
        return prop.value if prop is not None else None

    def flag(self, name: str) -> tuple[str, AtomNode] | None:
        node = self.node.first_list(name)
        atom = node.atom(1) if node is not None else None
        return (atom.value, atom) if atom is not None else None


@dataclass(frozen=True, slots=True)
class KicadNoConnect:
    node: ListNode

    @property
    def position(self) -> tuple[float, float]:
        at = self.node.first_list("at")
        x = at.atom(1) if at is not None else None
        y = at.atom(2) if at is not None else None
        if x is None or y is None:
            raise ValueError("malformed no_connect: missing position")
        return float(x.value), float(y.value)


@dataclass(frozen=True, slots=True)
class KicadSchematic:
    path: Path
    document: Document
    root: ListNode

    @classmethod
    def load(cls, path: str | Path) -> KicadSchematic:
        file_path = Path(path)
        source = file_path.read_text(encoding="utf-8")
        document = parse(source)
        roots = [node for node in document.roots() if isinstance(node, ListNode)]
        if len(roots) != 1 or roots[0].head != "kicad_sch":
            raise ValueError("expected one kicad_sch root expression")
        return cls(file_path, document, roots[0])

    @classmethod
    def from_text(cls, source: str, path: str | Path = "memory.kicad_sch") -> KicadSchematic:
        document = parse(source)
        roots = [node for node in document.roots() if isinstance(node, ListNode)]
        if len(roots) != 1 or roots[0].head != "kicad_sch":
            raise ValueError("expected one kicad_sch root expression")
        return cls(Path(path), document, roots[0])

    @property
    def symbols(self) -> tuple[KicadSymbol, ...]:
        result: list[KicadSymbol] = []
        for node in self.root.child_lists("symbol"):
            if node.first_list("lib_id") is not None and node.first_list("uuid") is not None:
                result.append(KicadSymbol(node))
        return tuple(result)

    @property
    def root_uuid(self) -> str:
        node = self.root.first_list("uuid")
        atom = node.atom(1) if node is not None else None
        if atom is None:
            raise ValueError("schematic root has no uuid")
        return atom.value

    @property
    def library_symbols_node(self) -> ListNode:
        node = self.root.first_list("lib_symbols")
        if node is None:
            raise ValueError("schematic has no lib_symbols section")
        return node

    @property
    def embedded_library_ids(self) -> frozenset[str]:
        return frozenset(self.embedded_library_symbols)

    @property
    def embedded_library_symbols(self) -> dict[str, ListNode]:
        return {
            atom.value: node
            for node in self.library_symbols_node.child_lists("symbol")
            if (atom := node.atom(1)) is not None
        }

    @property
    def symbol_insertion_offset(self) -> int:
        anchors = [
            node.span.start
            for head in ("sheet", "sheet_instances")
            if (node := self.root.first_list(head)) is not None
        ]
        return min(anchors, default=self.root.closing.span.start)

    @property
    def no_connects(self) -> tuple[KicadNoConnect, ...]:
        return tuple(KicadNoConnect(node) for node in self.root.child_lists("no_connect"))

    @property
    def no_connect_insertion_offset(self) -> int:
        later_sections = {
            "bus_entry",
            "wire",
            "bus",
            "image",
            "polyline",
            "text",
            "text_box",
            "label",
            "global_label",
            "hierarchical_label",
            "symbol",
            "sheet",
            "sheet_instances",
        }
        offsets = [
            node.span.start for node in self.root.child_lists() if node.head in later_sections
        ]
        return min(offsets, default=self.root.closing.span.start)

    @property
    def managed_symbols(self) -> dict[str, KicadSymbol]:
        result: dict[str, KicadSymbol] = {}
        for symbol in self.symbols:
            circuit_id = symbol.circuit_id
            if circuit_id is None:
                continue
            if circuit_id in result:
                raise ValueError(f"duplicate CircuitDK:ID in schematic: {circuit_id}")
            result[circuit_id] = symbol
        return result
