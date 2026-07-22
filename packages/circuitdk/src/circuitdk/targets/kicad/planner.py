from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from uuid import NAMESPACE_URL, uuid5

from lossless_sexpr import TextEdit, quote

from ...ir import CircuitIR, PartIR
from ...units import format_schematic_value
from .document import KicadSchematic, KicadSymbol
from .libraries import (
    EmbeddedSymbolDefinition,
    LibraryResolutionError,
    SymbolDefinition,
    SymbolResolver,
)

ActionKind = Literal["create", "update", "delete"]


@dataclass(frozen=True, slots=True)
class FieldChange:
    field: str
    actual: object
    desired: object


@dataclass(frozen=True, slots=True)
class Action:
    kind: ActionKind
    circuit_id: str
    changes: tuple[FieldChange, ...] = ()
    applicable: bool = True
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class NoConnectAction:
    kind: Literal["create", "delete"]
    pin_key: str
    x: float
    y: float
    applicable: bool = True
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class DeploymentPlan:
    actions: tuple[Action, ...]
    no_connect_actions: tuple[NoConnectAction, ...] = ()

    @property
    def has_changes(self) -> bool:
        return bool(self.actions or self.no_connect_actions)

    @property
    def pending(self) -> tuple[Action, ...]:
        return tuple(action for action in self.actions if not action.applicable)

    @property
    def applicable(self) -> tuple[Action, ...]:
        return tuple(action for action in self.actions if action.applicable)

    @property
    def pending_count(self) -> int:
        return len(self.pending) + sum(not action.applicable for action in self.no_connect_actions)


def plan_deployment(
    desired: CircuitIR,
    schematic: KicadSchematic,
    resolver: SymbolResolver | None = None,
    moved: dict[str, str] | None = None,
) -> DeploymentPlan:
    desired_parts = {part.id: part for part in desired.parts}
    moves = moved or {}
    actual: dict[str, KicadSymbol] = {}
    original_ids: dict[str, str] = {}
    for actual_id, symbol in schematic.managed_symbols.items():
        effective_id = moves.get(actual_id, actual_id)
        if effective_id in actual:
            raise ValueError(f"moved declarations produce duplicate id: {effective_id}")
        actual[effective_id] = symbol
        original_ids[effective_id] = actual_id

    actions: list[Action] = []
    for circuit_id in sorted(desired_parts.keys() - actual.keys()):
        reason: str | None = None
        if resolver is None:
            reason = "no KiCad symbol library resolver is configured"
        else:
            try:
                resolver.resolve(desired_parts[circuit_id].symbol)
            except LibraryResolutionError as error:
                reason = str(error)
        actions.append(Action("create", circuit_id, applicable=reason is None, reason=reason))

    for circuit_id in sorted(actual.keys() - desired_parts.keys()):
        actions.append(Action("delete", original_ids[circuit_id]))

    for circuit_id in sorted(actual.keys() & desired_parts.keys()):
        changes = list(_changes(desired_parts[circuit_id], actual[circuit_id]))
        embedded = schematic.embedded_library_symbols.get(actual[circuit_id].library_id)
        if (
            actual[circuit_id].library_id == desired_parts[circuit_id].symbol
            and embedded is not None
            and embedded.first_list("extends") is not None
        ):
            changes.append(FieldChange("embedded_symbol", "inherited", "flattened"))
        original_id = original_ids[circuit_id]
        if original_id != circuit_id:
            changes.insert(0, FieldChange("circuit_id", original_id, circuit_id))
        if changes:
            missing_fields = _missing_patch_fields(actual[circuit_id], tuple(changes))
            resolution_error: str | None = None
            if any(change.field in {"symbol", "embedded_symbol"} for change in changes):
                if resolver is None:
                    resolution_error = "no KiCad symbol library resolver is configured"
                else:
                    try:
                        resolver.resolve(desired_parts[circuit_id].symbol)
                    except LibraryResolutionError as error:
                        resolution_error = str(error)
            reason = resolution_error
            if missing_fields:
                reason = f"schematic lacks managed fields: {', '.join(missing_fields)}"
            actions.append(
                Action(
                    "update",
                    circuit_id,
                    tuple(changes),
                    applicable=not missing_fields and resolution_error is None,
                    reason=reason,
                )
            )
    no_connect_actions = _plan_no_connects(desired, schematic, resolver, actual, actions)
    return DeploymentPlan(tuple(actions), no_connect_actions)


def edits_for_plan(
    plan: DeploymentPlan,
    schematic: KicadSchematic,
    desired: CircuitIR,
    resolver: SymbolResolver | None = None,
) -> tuple[TextEdit, ...]:
    symbols = schematic.managed_symbols
    desired_parts = {part.id: part for part in desired.parts}
    edits: list[TextEdit] = []
    definitions_to_insert: dict[str, EmbeddedSymbolDefinition] = {}
    flattened_ids: set[str] = set()
    cleanup_candidates: set[str] = set()
    instances: list[str] = []
    used_references = {symbol.reference for symbol in schematic.symbols if symbol.reference}
    create_index = 0

    def ensure_flattened(library_id: str) -> None:
        if resolver is None:
            raise RuntimeError("flattening a symbol requires a resolver")
        if library_id in flattened_ids or library_id in definitions_to_insert:
            return
        embedded = resolver.materialize_for_schematic(library_id)
        existing = schematic.embedded_library_symbols.get(library_id)
        if existing is None:
            definitions_to_insert[library_id] = embedded
            return
        if existing.first_list("extends") is None:
            return
        edits.append(TextEdit(existing.span, embedded.source_text))
        flattened_ids.add(library_id)
        definition = resolver.resolve(library_id)
        cleanup_candidates.update(
            dependency.library_id for dependency in resolver.dependencies(definition)[:-1]
        )

    for action in plan.applicable:
        if action.kind == "delete":
            edits.append(TextEdit(symbols[action.circuit_id].node.span, ""))
            continue
        if action.kind == "create":
            if resolver is None:
                raise RuntimeError("planner marked create applicable without a resolver")
            part = desired_parts[action.circuit_id]
            definition = resolver.resolve(part.symbol)
            ensure_flattened(part.symbol)
            reference = _allocate_reference(definition.reference_prefix, used_references)
            used_references.add(reference)
            instances.append(
                _render_symbol_instance(part, definition, schematic, reference, create_index)
            )
            create_index += 1
            continue

        symbol = symbols.get(action.circuit_id)
        if symbol is None:
            original_id = next(
                str(change.actual) for change in action.changes if change.field == "circuit_id"
            )
            symbol = symbols[original_id]
        part = desired_parts[action.circuit_id]
        for change in action.changes:
            if change.field == "symbol":
                edits.append(TextEdit(symbol.library_id_atom.span, quote(str(change.desired))))
                if resolver is None:
                    raise RuntimeError("planner allowed symbol update without resolver")
                definition = resolver.resolve(str(change.desired))
                ensure_flattened(str(change.desired))
                pin_nodes = symbol.node.child_lists("pin")
                pin_numbers = tuple(pin.number for pin in definition.pins if pin.unit == 1)
                pin_text = _render_pin_instances(pin_numbers, symbol.uuid)
                if pin_nodes:
                    edits.append(
                        TextEdit.replace(
                            pin_nodes[0].span.start,
                            pin_nodes[-1].span.end,
                            pin_text,
                        )
                    )
                else:
                    instances_node = symbol.node.first_list("instances")
                    offset = (
                        instances_node.span.start
                        if instances_node is not None
                        else symbol.node.closing.span.start
                    )
                    edits.append(TextEdit.replace(offset, offset, pin_text + "\n    "))
            elif change.field == "embedded_symbol":
                ensure_flattened(part.symbol)
            elif change.field in {"value", "footprint", "circuit_id"}:
                property_name = {
                    "value": "Value",
                    "footprint": "Footprint",
                    "circuit_id": "CircuitDK:ID",
                }[change.field]
                prop = symbol.find_property(property_name)
                if prop is None:
                    raise RuntimeError(f"planner allowed missing property {property_name}")
                edits.append(prop.set_value("" if change.desired is None else str(change.desired)))
            else:
                flag = symbol.flag(change.field)
                if flag is None:
                    raise RuntimeError(f"planner allowed missing flag {change.field}")
                edits.append(TextEdit(flag[1].span, "yes" if change.desired else "no"))

    if cleanup_candidates:
        protected_ids = {item.library_id for item in schematic.symbols}
        for library_id, node in schematic.embedded_library_symbols.items():
            if library_id in flattened_ids:
                continue
            extends = node.first_list("extends")
            extends_atom = extends.atom(1) if extends is not None else None
            if extends_atom is None:
                continue
            target = extends_atom.value
            protected_ids.add(
                target if ":" in target else f"{library_id.split(':', 1)[0]}:{target}"
            )
        for library_id in sorted(cleanup_candidates - protected_ids):
            node = schematic.embedded_library_symbols.get(library_id)
            if node is not None:
                edits.append(TextEdit(node.span, ""))

    if definitions_to_insert:
        rendered = "".join(
            "\n" + _indent(definition.source_text, 4)
            for definition in definitions_to_insert.values()
        )
        edits.append(
            TextEdit.replace(
                schematic.library_symbols_node.closing.span.start,
                schematic.library_symbols_node.closing.span.start,
                rendered + "\n  ",
            )
        )
    no_connect_insertions: list[str] = []
    actual_no_connects = {_coordinate_key(*item.position): item for item in schematic.no_connects}
    for action in plan.no_connect_actions:
        if not action.applicable:
            continue
        if action.kind == "delete":
            existing = actual_no_connects[_coordinate_key(action.x, action.y)]
            edits.append(TextEdit(existing.node.span, ""))
        else:
            marker_uuid = uuid5(
                NAMESPACE_URL,
                f"circuitdk:{schematic.root_uuid}:no-connect:{action.pin_key}",
            )
            no_connect_insertions.append(
                "  (no_connect\n"
                f"    (at {action.x:g} {action.y:g})\n"
                f"    (uuid {quote(str(marker_uuid))})\n"
                "  )"
            )
    if no_connect_insertions:
        rendered = "\n".join(no_connect_insertions) + "\n  "
        edits.append(
            TextEdit.replace(
                schematic.no_connect_insertion_offset,
                schematic.no_connect_insertion_offset,
                rendered,
            )
        )
    if instances:
        rendered = "".join("\n" + instance for instance in instances)
        edits.append(
            TextEdit.replace(
                schematic.symbol_insertion_offset,
                schematic.symbol_insertion_offset,
                rendered + "\n  ",
            )
        )
    return tuple(edits)


def _render_symbol_instance(
    part: PartIR,
    definition: SymbolDefinition,
    schematic: KicadSchematic,
    reference: str,
    index: int,
) -> str:
    x, y = _staging_position(index)
    symbol_uuid = uuid5(NAMESPACE_URL, f"circuitdk:{schematic.root_uuid}:{part.id}:symbol")
    pin_numbers = tuple(pin.number for pin in definition.pins if pin.unit == 1)
    if not pin_numbers:
        pin_numbers = tuple(pin.number for pin in part.pins)
    pins = _render_pin_instances(pin_numbers, str(symbol_uuid))
    footprint = part.footprint or ""
    reference_property = _render_property("Reference", reference, x + 2.54, y)
    value_property = _render_property("Value", format_schematic_value(part.value), x, y + 2.54)
    footprint_property = _render_property("Footprint", footprint, x, y, hidden=True)
    datasheet_property = _render_property("Datasheet", "~", x, y, hidden=True)
    description_property = _render_property("Description", "", x, y, hidden=True)
    circuit_id_property = _render_property("CircuitDK:ID", part.id, x, y, hidden=True)
    return f"""  (symbol
    (lib_id {quote(part.symbol)})
    (at {x} {y} 0)
    (unit 1)
    (body_style 1)
    (exclude_from_sim no)
    (in_bom {"yes" if part.in_bom else "no"})
    (on_board {"yes" if part.on_board else "no"})
    (in_pos_files {"yes" if part.on_board else "no"})
    (dnp {"yes" if part.dnp else "no"})
    (fields_autoplaced yes)
    (uuid {quote(str(symbol_uuid))})
{reference_property}
{value_property}
{footprint_property}
{datasheet_property}
{description_property}
{circuit_id_property}
{pins}
    (instances
      (project {quote(schematic.path.stem)}
        (path {quote(f"/{schematic.root_uuid}")}
          (reference {quote(reference)})
          (unit 1)
        )
      )
    )
  )"""


def _render_property(name: str, value: str, x: float, y: float, *, hidden: bool = False) -> str:
    hide = "\n      (hide yes)" if hidden else ""
    return (
        f"    (property {quote(name)} {quote(value)}\n"
        f"      (at {x:g} {y:g} 0){hide}\n"
        "      (effects (font (size 1.27 1.27)))\n"
        "    )"
    )


def _allocate_reference(prefix: str, used: set[str]) -> str:
    normalized = re.sub(r"[^A-Za-z#]", "", prefix) or "U"
    number = 1
    while f"{normalized}{number}" in used:
        number += 1
    return f"{normalized}{number}"


def _render_pin_instances(pin_numbers: tuple[str, ...], symbol_uuid: str) -> str:
    return "\n".join(
        (
            f"    (pin {quote(number)} "
            f"(uuid {quote(str(uuid5(NAMESPACE_URL, f'{symbol_uuid}:pin:{number}')))}))"
        )
        for number in pin_numbers
    )


def _staging_position(index: int) -> tuple[float, float]:
    # Keep symbol origins and common 1.27 mm pin pitches on KiCad's 50 mil grid.
    return 203.2 + (index % 4) * 30.48, 50.8 + (index // 4) * 30.48


def _plan_no_connects(
    desired: CircuitIR,
    schematic: KicadSchematic,
    resolver: SymbolResolver | None,
    actual_symbols: dict[str, KicadSymbol],
    symbol_actions: list[Action],
) -> tuple[NoConnectAction, ...]:
    if not desired.no_connects:
        expected_keys: dict[tuple[float, float], str] = {}
    else:
        expected_keys = {}
    managed_pin_positions: dict[tuple[float, float], str] = {}
    create_ids = [action.circuit_id for action in symbol_actions if action.kind == "create"]
    part_by_id = {part.id: part for part in desired.parts}
    pending: list[NoConnectAction] = []

    if resolver is not None:
        for part_id, symbol in actual_symbols.items():
            try:
                actual_definition = resolver.resolve(symbol.library_id)
            except LibraryResolutionError:
                continue
            for pin_definition in actual_definition.pins:
                if pin_definition.unit != 1:
                    continue
                x, y = _pin_position(
                    symbol.position,
                    pin_definition.x,
                    pin_definition.y,
                    symbol.mirror,
                )
                managed_pin_positions[_coordinate_key(x, y)] = f"{part_id}:{pin_definition.number}"

        for part_id, part in part_by_id.items():
            try:
                definition = resolver.resolve(part.symbol)
            except LibraryResolutionError:
                continue
            symbol = actual_symbols.get(part_id)
            position = (
                symbol.position
                if symbol is not None
                else (
                    (*_staging_position(create_ids.index(part_id)), 0.0)
                    if part_id in create_ids
                    else None
                )
            )
            if position is None:
                continue
            mirror = symbol.mirror if symbol is not None else None
            for pin in part.pins:
                try:
                    pin_definition = definition.pin(pin.number)
                except KeyError:
                    continue
                x, y = _pin_position(position, pin_definition.x, pin_definition.y, mirror)
                managed_pin_positions[_coordinate_key(x, y)] = pin.key

        for pin in desired.no_connects:
            part = part_by_id.get(pin.part_id)
            symbol = actual_symbols.get(pin.part_id)
            if part is None:
                continue
            try:
                definition = resolver.resolve(part.symbol)
                pin_definition = definition.pin(pin.number)
            except (LibraryResolutionError, KeyError) as error:
                pending.append(NoConnectAction("create", pin.key, 0, 0, False, str(error)))
                continue
            position = (
                symbol.position
                if symbol is not None
                else (
                    (*_staging_position(create_ids.index(pin.part_id)), 0.0)
                    if pin.part_id in create_ids
                    else None
                )
            )
            if position is None:
                pending.append(
                    NoConnectAction("create", pin.key, 0, 0, False, "symbol position is unknown")
                )
                continue
            mirror = symbol.mirror if symbol is not None else None
            x, y = _pin_position(position, pin_definition.x, pin_definition.y, mirror)
            expected_keys[_coordinate_key(x, y)] = pin.key
    elif desired.no_connects:
        pending.extend(
            NoConnectAction("create", pin.key, 0, 0, False, "no symbol resolver is configured")
            for pin in desired.no_connects
        )

    actual_keys = {_coordinate_key(*item.position) for item in schematic.no_connects}
    actions = list(pending)
    for coordinate, pin_key in expected_keys.items():
        if coordinate not in actual_keys:
            actions.append(NoConnectAction("create", pin_key, *coordinate))
    for coordinate in actual_keys - set(expected_keys):
        pin_key = managed_pin_positions.get(coordinate)
        if pin_key is not None:
            actions.append(NoConnectAction("delete", pin_key, *coordinate))
    return tuple(sorted(actions, key=lambda action: (action.pin_key, action.kind)))


def _pin_position(
    symbol_position: tuple[float, float, float],
    local_x: float,
    local_y: float,
    mirror: str | None = None,
) -> tuple[float, float]:
    x, y, angle = symbol_position
    if mirror == "x":
        local_y = -local_y
    elif mirror == "y":
        local_x = -local_x
    rotation = round(angle) % 360
    dx, dy = {
        0: (local_x, local_y),
        90: (-local_y, local_x),
        180: (-local_x, -local_y),
        270: (local_y, -local_x),
    }.get(rotation, (local_x, local_y))
    return x + dx, y + dy


def _coordinate_key(x: float, y: float) -> tuple[float, float]:
    return round(x, 6), round(y, 6)


def _indent(source: str, spaces: int) -> str:
    prefix = " " * spaces
    return "\n".join(prefix + line if line else line for line in source.splitlines())


def _changes(desired: PartIR, actual: KicadSymbol) -> tuple[FieldChange, ...]:
    observed: dict[str, object] = {
        "symbol": actual.library_id,
        "value": _property_value(actual, "Value"),
        "footprint": _property_value(actual, "Footprint") or None,
        "in_bom": _flag_value(actual, "in_bom"),
        "on_board": _flag_value(actual, "on_board"),
        "dnp": _flag_value(actual, "dnp"),
    }
    expected: dict[str, object] = {
        "symbol": desired.symbol,
        "value": format_schematic_value(desired.value),
        "footprint": desired.footprint,
        "in_bom": desired.in_bom,
        "on_board": desired.on_board,
        "dnp": desired.dnp,
    }
    return tuple(
        FieldChange(field, observed[field], expected[field])
        for field in expected
        if observed[field] != expected[field]
    )


def _property_value(symbol: KicadSymbol, name: str) -> str | None:
    prop = symbol.find_property(name)
    return prop.value if prop is not None else None


def _flag_value(symbol: KicadSymbol, name: str) -> bool | None:
    flag = symbol.flag(name)
    return flag[0] == "yes" if flag is not None else None


def _missing_patch_fields(symbol: KicadSymbol, changes: tuple[FieldChange, ...]) -> list[str]:
    missing: list[str] = []
    for change in changes:
        if change.field == "value" and symbol.find_property("Value") is None:
            missing.append("Value")
        elif change.field == "footprint" and symbol.find_property("Footprint") is None:
            missing.append("Footprint")
        elif change.field == "circuit_id" and symbol.find_property("CircuitDK:ID") is None:
            missing.append("CircuitDK:ID")
        elif change.field in {"in_bom", "on_board", "dnp"} and symbol.flag(change.field) is None:
            missing.append(change.field)
    return missing
