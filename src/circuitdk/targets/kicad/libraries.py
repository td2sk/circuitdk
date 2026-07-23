from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from lossless_sexpr import AtomNode, ListNode, TextEdit, apply_edits, parse, quote


class LibraryResolutionError(LookupError):
    pass


@dataclass(frozen=True, slots=True)
class SymbolPinDefinition:
    number: str
    name: str
    electrical_type: str
    unit: int
    x: float
    y: float
    angle: float
    hidden: bool = False


@dataclass(frozen=True, slots=True)
class SymbolDefinition:
    library_id: str
    source_path: Path
    source_sha256: str
    source_text: str
    pins: tuple[SymbolPinDefinition, ...]
    reference_prefix: str
    extends: str | None = None

    def pin(self, name_or_number: str) -> SymbolPinDefinition:
        matches = tuple(
            pin for pin in self.pins if pin.name == name_or_number or pin.number == name_or_number
        )
        if not matches:
            raise KeyError(f"pin {name_or_number!r} is not defined by {self.library_id}")
        if len(matches) > 1:
            by_number = tuple(pin for pin in matches if pin.number == name_or_number)
            if len(by_number) == 1:
                return by_number[0]
            raise KeyError(f"pin {name_or_number!r} is ambiguous in {self.library_id}")
        return matches[0]


@dataclass(frozen=True, slots=True)
class EmbeddedSymbolDefinition:
    library_id: str
    source_text: str


@dataclass(frozen=True, slots=True)
class FootprintDefinition:
    library_id: str
    source_path: Path
    source_sha256: str
    pads: tuple[str, ...]
    mount_type: str | None


class SymbolResolver(Protocol):
    def resolve(self, library_id: str) -> SymbolDefinition: ...

    def materialize_for_schematic(self, library_id: str) -> EmbeddedSymbolDefinition: ...

    def dependencies(self, definition: SymbolDefinition) -> tuple[SymbolDefinition, ...]: ...


class FootprintResolver(Protocol):
    def resolve(self, library_id: str) -> FootprintDefinition: ...


@dataclass(frozen=True, slots=True)
class LibraryTableEntry:
    name: str
    uri: str


class LibraryTable:
    def __init__(self, entries: dict[str, LibraryTableEntry], variables: dict[str, str]) -> None:
        self.entries = entries
        self.variables = variables

    @classmethod
    def load(cls, paths: tuple[Path, ...], variables: dict[str, str]) -> LibraryTable:
        entries: dict[str, LibraryTableEntry] = {}
        seen: set[Path] = set()
        for path in paths:
            _load_table_entries(path, variables, entries, seen)
        return cls(entries, variables)

    def resolve_uri(self, nickname: str) -> Path:
        try:
            entry = self.entries[nickname]
        except KeyError as error:
            raise LibraryResolutionError(
                f"library nickname is not configured: {nickname}"
            ) from error
        expanded = _expand_variables(entry.uri, self.variables)
        if expanded.startswith("file://"):
            expanded = expanded[7:]
        return Path(expanded).expanduser().resolve()


@dataclass(frozen=True, slots=True)
class _ParsedSymbolLibrary:
    source: str
    source_sha256: str
    symbols: dict[str, ListNode]


class KicadSymbolResolver:
    def __init__(self, table: LibraryTable) -> None:
        self.table = table
        self._cache: dict[str, SymbolDefinition] = {}
        self._library_cache: dict[Path, _ParsedSymbolLibrary] = {}
        self._embedded_cache: dict[str, EmbeddedSymbolDefinition] = {}

    @classmethod
    def for_project(
        cls,
        project_directory: Path,
        *,
        kicad_major: int = 10,
        environment: dict[str, str] | None = None,
    ) -> KicadSymbolResolver:
        env = dict(os.environ if environment is None else environment)
        variables = dict(env)
        variables["KIPRJMOD"] = str(project_directory.resolve())
        for name, value in _default_kicad_variables(kicad_major, env).items():
            variables.setdefault(name, value)
        tables = (
            *_global_table_candidates("sym-lib-table", kicad_major, env),
            project_directory / "sym-lib-table",
        )
        return cls(LibraryTable.load(tables, variables))

    def resolve(self, library_id: str) -> SymbolDefinition:
        if library_id in self._cache:
            return self._cache[library_id]
        nickname, separator, symbol_name = library_id.partition(":")
        if not separator:
            raise LibraryResolutionError(f"invalid symbol library id: {library_id}")
        path = self.table.resolve_uri(nickname)
        if not path.exists():
            raise LibraryResolutionError(f"symbol library does not exist: {path}")
        library = self._load_library(path)
        source = library.source
        node = library.symbols.get(symbol_name)
        if node is None:
            raise LibraryResolutionError(f"symbol {symbol_name!r} not found in {path}")
        name_atom = node.atom(1)
        if name_atom is None:
            raise LibraryResolutionError(f"malformed symbol definition in {path}")
        raw = source[node.span.start : node.span.end]
        extends = _atom_value(node.first_list("extends"), 1)
        local_edits = [
            TextEdit.replace(
                name_atom.span.start - node.span.start,
                name_atom.span.end - node.span.start,
                quote(library_id),
            )
        ]
        base: SymbolDefinition | None = None
        if extends is not None:
            base_id = f"{nickname}:{extends}"
            extends_node = node.first_list("extends")
            extends_atom = extends_node.atom(1) if extends_node is not None else None
            if extends_atom is not None:
                local_edits.append(
                    TextEdit.replace(
                        extends_atom.span.start - node.span.start,
                        extends_atom.span.end - node.span.start,
                        quote(base_id),
                    )
                )
            base = self.resolve(base_id)
        embedded = apply_edits(raw, local_edits)
        own_pins = _symbol_pins(node)
        pins = _merge_pins(base.pins if base is not None else (), own_pins)
        own_prefix = _reference_prefix(node)
        definition = SymbolDefinition(
            library_id=library_id,
            source_path=path,
            source_sha256=library.source_sha256,
            source_text=embedded,
            pins=pins,
            reference_prefix=own_prefix or (base.reference_prefix if base is not None else "U"),
            extends=extends,
        )
        self._cache[library_id] = definition
        return definition

    def _load_library(self, path: Path) -> _ParsedSymbolLibrary:
        cached = self._library_cache.get(path)
        if cached is not None:
            return cached
        source = path.read_text(encoding="utf-8")
        document = parse(source)
        root = _single_root(document.lists("kicad_symbol_lib"), path)
        symbols = {
            name: node
            for node in root.child_lists("symbol")
            if (name := _atom_value(node, 1)) is not None
        }
        library = _ParsedSymbolLibrary(source, _sha256(source), symbols)
        self._library_cache[path] = library
        return library

    def dependencies(self, definition: SymbolDefinition) -> tuple[SymbolDefinition, ...]:
        if definition.extends is None:
            return (definition,)
        nickname = definition.library_id.split(":", 1)[0]
        base_id = f"{nickname}:{definition.extends}"
        base = self.resolve(base_id)
        return (*self.dependencies(base), definition)

    def materialize_for_schematic(self, library_id: str) -> EmbeddedSymbolDefinition:
        cached = self._embedded_cache.get(library_id)
        if cached is not None:
            return cached
        definition = self.resolve(library_id)
        chain = self.dependencies(definition)
        root_definition = chain[0]
        root_library, root_node = self._library_symbol(root_definition.library_id)
        root_source = root_library.source
        raw = root_source[root_node.span.start : root_node.span.end]
        leaf_name = library_id.split(":", 1)[1]
        root_name = root_definition.library_id.split(":", 1)[1]
        edits: list[TextEdit] = []

        name_atom = root_node.atom(1)
        if name_atom is None:
            raise LibraryResolutionError(
                f"malformed symbol definition: {root_definition.library_id}"
            )
        edits.append(
            TextEdit.replace(
                name_atom.span.start - root_node.span.start,
                name_atom.span.end - root_node.span.start,
                quote(library_id),
            )
        )

        effective_properties: dict[str, str] = {}
        for item in chain:
            library, node = self._library_symbol(item.library_id)
            for prop in node.child_lists("property"):
                prop_name = _atom_value(prop, 1)
                if prop_name is not None:
                    effective_properties[prop_name] = library.source[
                        prop.span.start : prop.span.end
                    ]

        root_property_names: set[str] = set()
        for prop in root_node.child_lists("property"):
            prop_name = _atom_value(prop, 1)
            if prop_name is None:
                continue
            root_property_names.add(prop_name)
            replacement = effective_properties[prop_name]
            edits.append(
                TextEdit.replace(
                    prop.span.start - root_node.span.start,
                    prop.span.end - root_node.span.start,
                    replacement,
                )
            )

        additional_properties = [
            source
            for name, source in effective_properties.items()
            if name not in root_property_names
        ]
        if additional_properties:
            unit_nodes = root_node.child_lists("symbol")
            embedded_fonts = root_node.first_list("embedded_fonts")
            insertion = (
                unit_nodes[0].span.start
                if unit_nodes
                else (
                    embedded_fonts.span.start
                    if embedded_fonts is not None
                    else root_node.closing.span.start
                )
            )
            rendered = "".join(f"\n\t\t{source}" for source in additional_properties)
            edits.append(
                TextEdit.replace(
                    insertion - root_node.span.start,
                    insertion - root_node.span.start,
                    rendered,
                )
            )

        for unit_node in root_node.child_lists("symbol"):
            unit_name_atom = unit_node.atom(1)
            if unit_name_atom is None:
                continue
            match = re.search(r"(_\d+_\d+)$", unit_name_atom.value)
            suffix = match.group(1) if match is not None else unit_name_atom.value[len(root_name) :]
            edits.append(
                TextEdit.replace(
                    unit_name_atom.span.start - root_node.span.start,
                    unit_name_atom.span.end - root_node.span.start,
                    quote(f"{leaf_name}{suffix}"),
                )
            )

        embedded = EmbeddedSymbolDefinition(library_id, apply_edits(raw, edits))
        self._embedded_cache[library_id] = embedded
        return embedded

    def _library_symbol(self, library_id: str) -> tuple[_ParsedSymbolLibrary, ListNode]:
        nickname, separator, symbol_name = library_id.partition(":")
        if not separator:
            raise LibraryResolutionError(f"invalid symbol library id: {library_id}")
        path = self.table.resolve_uri(nickname)
        library = self._load_library(path)
        try:
            return library, library.symbols[symbol_name]
        except KeyError as error:
            raise LibraryResolutionError(f"symbol {symbol_name!r} not found in {path}") from error


class InMemorySymbolResolver:
    def __init__(self, definitions: tuple[SymbolDefinition, ...]) -> None:
        self.definitions = {definition.library_id: definition for definition in definitions}

    def resolve(self, library_id: str) -> SymbolDefinition:
        try:
            return self.definitions[library_id]
        except KeyError as error:
            raise LibraryResolutionError(f"symbol is not registered: {library_id}") from error

    def dependencies(self, definition: SymbolDefinition) -> tuple[SymbolDefinition, ...]:
        return (definition,)

    def materialize_for_schematic(self, library_id: str) -> EmbeddedSymbolDefinition:
        definition = self.resolve(library_id)
        return EmbeddedSymbolDefinition(library_id, definition.source_text)


class KicadFootprintResolver:
    def __init__(self, table: LibraryTable) -> None:
        self.table = table
        self._cache: dict[str, FootprintDefinition] = {}

    @classmethod
    def for_project(
        cls,
        project_directory: Path,
        *,
        kicad_major: int = 10,
        environment: dict[str, str] | None = None,
    ) -> KicadFootprintResolver:
        env = dict(os.environ if environment is None else environment)
        variables = dict(env)
        variables["KIPRJMOD"] = str(project_directory.resolve())
        for name, value in _default_kicad_variables(kicad_major, env).items():
            variables.setdefault(name, value)
        tables = (
            *_global_table_candidates("fp-lib-table", kicad_major, env),
            project_directory / "fp-lib-table",
        )
        return cls(LibraryTable.load(tables, variables))

    def resolve(self, library_id: str) -> FootprintDefinition:
        if library_id in self._cache:
            return self._cache[library_id]
        nickname, separator, footprint_name = library_id.partition(":")
        if not separator:
            raise LibraryResolutionError(f"invalid footprint library id: {library_id}")
        directory = self.table.resolve_uri(nickname)
        path = directory / f"{footprint_name}.kicad_mod" if directory.is_dir() else directory
        if not path.exists():
            raise LibraryResolutionError(f"footprint does not exist: {path}")
        source = path.read_text(encoding="utf-8")
        document = parse(source)
        roots = document.lists("footprint")
        if len(roots) != 1:
            raise LibraryResolutionError(f"expected one footprint in {path}")
        root = roots[0]
        pads = tuple(
            sorted(
                {
                    value
                    for node in root.child_lists("pad")
                    if (value := _atom_value(node, 1)) is not None and value
                }
            )
        )
        attr = root.first_list("attr")
        mount_type = _atom_value(attr, 1)
        definition = FootprintDefinition(library_id, path, _sha256(source), pads, mount_type)
        self._cache[library_id] = definition
        return definition


def validate_symbol_footprint(
    symbol: SymbolDefinition, footprint: FootprintDefinition
) -> tuple[str, ...]:
    pin_numbers = {pin.number for pin in symbol.pins if pin.number}
    pad_numbers = set(footprint.pads)
    issues = [
        f"symbol pin {number} has no footprint pad" for number in sorted(pin_numbers - pad_numbers)
    ]
    issues.extend(
        f"footprint pad {number} has no symbol pin" for number in sorted(pad_numbers - pin_numbers)
    )
    return tuple(issues)


def _symbol_pins(node: ListNode) -> tuple[SymbolPinDefinition, ...]:
    pins: dict[tuple[str, int], SymbolPinDefinition] = {}
    for unit_node in node.child_lists("symbol"):
        unit_name = _atom_value(unit_node, 1) or ""
        match = re.search(r"_(\d+)_\d+$", unit_name)
        unit = int(match.group(1)) if match else 1
        for pin_node in unit_node.walk("pin"):
            number_node = pin_node.first_list("number")
            name_node = pin_node.first_list("name")
            at_node = pin_node.first_list("at")
            number = _atom_value(number_node, 1)
            name = _atom_value(name_node, 1)
            if number is None or name is None:
                continue
            electrical_type = _atom_value(pin_node, 1) or "unspecified"
            x = _float_atom(at_node, 1)
            y = _float_atom(at_node, 2)
            angle = _float_atom(at_node, 3)
            hidden = any(
                isinstance(child, AtomNode) and child.value == "hide"
                for child in pin_node.children()
            )
            pins[(number, unit)] = SymbolPinDefinition(
                number, name, electrical_type, unit, x, y, angle, hidden
            )
    return tuple(sorted(pins.values(), key=lambda pin: (pin.unit, pin.number)))


def _reference_prefix(node: ListNode) -> str | None:
    for prop in node.child_lists("property"):
        if _atom_value(prop, 1) == "Reference":
            return _atom_value(prop, 2) or "U"
    return None


def _merge_pins(
    base: tuple[SymbolPinDefinition, ...],
    own: tuple[SymbolPinDefinition, ...],
) -> tuple[SymbolPinDefinition, ...]:
    merged = {(pin.number, pin.unit): pin for pin in base}
    merged.update({(pin.number, pin.unit): pin for pin in own})
    return tuple(merged[key] for key in sorted(merged))


def _global_table_candidates(name: str, major: int, env: dict[str, str]) -> tuple[Path, ...]:
    candidates: list[Path] = []
    appdata = env.get("APPDATA")
    if appdata:
        candidates.append(Path(appdata) / "kicad" / f"{major}.0" / name)
    xdg = env.get("XDG_CONFIG_HOME")
    home = env.get("USERPROFILE") or env.get("HOME")
    if xdg:
        candidates.append(Path(xdg) / "kicad" / f"{major}.0" / name)
    elif home:
        candidates.append(Path(home) / ".config" / "kicad" / f"{major}.0" / name)
        candidates.append(Path(home) / "Library" / "Preferences" / "kicad" / f"{major}.0" / name)
    return tuple(candidates)


def _default_kicad_variables(major: int, env: dict[str, str]) -> dict[str, str]:
    result: dict[str, str] = {}
    program_files = env.get("ProgramFiles") or env.get("PROGRAMFILES")
    candidates: list[Path] = []
    if program_files:
        candidates.append(Path(program_files) / "KiCad" / f"{major}.0" / "share" / "kicad")
    candidates.extend((Path("/usr/share/kicad"), Path("/usr/local/share/kicad")))
    for base in candidates:
        symbols = base / "symbols"
        footprints = base / "footprints"
        if symbols.exists():
            result.setdefault(f"KICAD{major}_SYMBOL_DIR", str(symbols))
        if footprints.exists():
            result.setdefault(f"KICAD{major}_FOOTPRINT_DIR", str(footprints))
    return result


def _expand_variables(value: str, variables: dict[str, str]) -> str:
    pattern = re.compile(r"\$\{([^}]+)}")

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in variables:
            raise LibraryResolutionError(f"undefined KiCad path variable: {name}")
        return variables[name]

    return pattern.sub(replace, value)


def _load_table_entries(
    path: Path,
    variables: dict[str, str],
    entries: dict[str, LibraryTableEntry],
    seen: set[Path],
) -> None:
    resolved = path.expanduser().resolve()
    if resolved in seen or not resolved.exists():
        return
    seen.add(resolved)
    document = parse(resolved.read_text(encoding="utf-8"))
    for node in document.lists("lib"):
        name = _child_value(node, "name")
        uri = _child_value(node, "uri")
        library_type = _child_value(node, "type")
        if not name or not uri:
            continue
        if library_type == "Table":
            nested = Path(_expand_variables(uri, variables))
            _load_table_entries(nested, variables, entries, seen)
        else:
            entries[name] = LibraryTableEntry(name, uri)


def _child_value(node: ListNode, head: str) -> str | None:
    return _atom_value(node.first_list(head), 1)


def _atom_value(node: ListNode | None, index: int) -> str | None:
    atom = node.atom(index) if node is not None else None
    return atom.value if atom is not None else None


def _float_atom(node: ListNode | None, index: int) -> float:
    value = _atom_value(node, index)
    return float(value) if value is not None else 0.0


def _single_root(nodes: tuple[ListNode, ...], path: Path) -> ListNode:
    if len(nodes) != 1:
        raise LibraryResolutionError(f"expected one library root in {path}")
    return nodes[0]


def _sha256(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()
