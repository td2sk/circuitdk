from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from lossless_sexpr import TextEdit, apply_edits, parse

from .conformance import ConformanceResult, compare_connectivity
from .constructs import Circuit
from .ir import CircuitIR, NetIR, PartIR, PinRef
from .lock import CircuitLock, LockedLibrary
from .rules import PinCoverageResult, validate_pin_coverage
from .state import ProjectState
from .targets.kicad.cli_runner import ErcResult, KicadCli, actual_circuit_from_xml
from .targets.kicad.document import KicadSchematic, KicadSymbol
from .targets.kicad.libraries import (
    FootprintResolver,
    KicadFootprintResolver,
    KicadSymbolResolver,
    LibraryResolutionError,
    SymbolResolver,
    validate_symbol_footprint,
)
from .targets.kicad.planner import (
    DeploymentPlan,
    edits_for_plan,
    plan_deployment,
)


@dataclass(frozen=True, slots=True)
class DeployResult:
    plan: DeploymentPlan
    applied_creates: int
    applied_updates: int
    applied_deletes: int
    applied_no_connect_changes: int
    pending_actions: int
    backup: Path | None
    erc: ErcResult | None

    @property
    def complete(self) -> bool:
        """Backward-compatible alias for managed-state reconciliation."""
        return self.pending_actions == 0

    @property
    def reconciled(self) -> bool:
        return self.pending_actions == 0

    @property
    def structural_validation(self) -> str:
        return "passed" if self.erc is not None else "skipped"

    @property
    def electrical_validation(self) -> str:
        if self.erc is None:
            return "skipped"
        if self.erc.errors:
            return "failed"
        if self.erc.warnings:
            return "warning"
        return "passed"

    @property
    def ready(self) -> bool:
        return self.reconciled and self.erc is not None and not self.erc.has_errors


@dataclass(frozen=True, slots=True)
class Drift:
    circuit_id: str
    field: str
    applied: object
    actual: object


@dataclass(frozen=True, slots=True)
class ProjectTestResult:
    plan: DeploymentPlan
    connectivity: ConformanceResult | None
    erc: ErcResult | None
    pin_coverage: PinCoverageResult
    library_issues: tuple[str, ...]
    infrastructure_errors: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return (
            not self.plan.has_changes
            and self.connectivity is not None
            and self.connectivity.ok
            and self.erc is not None
            and self.erc.ok
            and self.pin_coverage.ok
            and not self.library_issues
            and not self.infrastructure_errors
        )


class KicadProject:
    def __init__(
        self,
        circuit: Circuit,
        schematic: str | Path,
        *,
        state_directory: str | Path = ".circuitdk",
        symbol_resolver: SymbolResolver | None = None,
        footprint_resolver: FootprintResolver | None = None,
        moved: dict[str, str] | None = None,
        kicad_cli: KicadCli | None = None,
        validate_with_kicad: bool = True,
    ) -> None:
        self.circuit = circuit
        self.schematic = Path(schematic)
        self.state_directory = Path(state_directory)
        self._symbol_resolver = symbol_resolver
        self._footprint_resolver = footprint_resolver
        self.moved = dict(moved or {})
        self._kicad_cli = kicad_cli
        self._kicad_cli_loaded = kicad_cli is not None or not validate_with_kicad

    @property
    def symbol_resolver(self) -> SymbolResolver:
        if self._symbol_resolver is None:
            self._symbol_resolver = KicadSymbolResolver.for_project(self.schematic.parent.resolve())
        return self._symbol_resolver

    @symbol_resolver.setter
    def symbol_resolver(self, resolver: SymbolResolver) -> None:
        self._symbol_resolver = resolver

    @property
    def footprint_resolver(self) -> FootprintResolver:
        if self._footprint_resolver is None:
            self._footprint_resolver = KicadFootprintResolver.for_project(
                self.schematic.parent.resolve()
            )
        return self._footprint_resolver

    @footprint_resolver.setter
    def footprint_resolver(self, resolver: FootprintResolver) -> None:
        self._footprint_resolver = resolver

    @property
    def kicad_cli(self) -> KicadCli | None:
        if not self._kicad_cli_loaded:
            self._kicad_cli = KicadCli.discover()
            self._kicad_cli_loaded = True
        return self._kicad_cli

    @kicad_cli.setter
    def kicad_cli(self, cli: KicadCli | None) -> None:
        self._kicad_cli = cli
        self._kicad_cli_loaded = True

    @property
    def state_path(self) -> Path:
        safe_name = self.circuit.construct_id.replace("/", "_")
        return self.state_directory / f"{safe_name}.state.json"

    @property
    def lock_path(self) -> Path:
        return self.state_directory / "circuitdk.lock.json"

    def synth(self) -> CircuitIR:
        circuit = self.circuit.synth()
        if not any(part.resolve_pins for part in circuit.parts):
            return circuit
        return _resolve_library_pins(circuit, self.symbol_resolver)

    def plan(self) -> DeploymentPlan:
        plan, _ = self._plan_with_resolver(self.synth(), KicadSchematic.load(self.schematic))
        return plan

    def _plan_with_resolver(
        self, desired: CircuitIR, schematic: KicadSchematic
    ) -> tuple[DeploymentPlan, SymbolResolver | None]:
        preliminary = plan_deployment(desired, schematic, None, self.moved)
        needs_symbols = (
            any(
                action.kind == "create"
                or any(change.field in {"symbol", "embedded_symbol"} for change in action.changes)
                for action in preliminary.actions
            )
            or bool(desired.no_connects)
            or bool(schematic.no_connects)
        )
        if not needs_symbols:
            return preliminary, None
        resolver = self.symbol_resolver
        return plan_deployment(desired, schematic, resolver, self.moved), resolver

    def library_lock(self) -> tuple[CircuitLock, tuple[str, ...]]:
        locked: list[LockedLibrary] = []
        issues: list[str] = []
        for part in self.synth().parts:
            try:
                symbol = self.symbol_resolver.resolve(part.symbol)
                locked.append(
                    LockedLibrary(
                        "symbol", part.symbol, str(symbol.source_path), symbol.source_sha256
                    )
                )
            except LibraryResolutionError as error:
                issues.append(str(error))
                continue
            if part.footprint is None:
                continue
            try:
                footprint = self.footprint_resolver.resolve(part.footprint)
                locked.append(
                    LockedLibrary(
                        "footprint",
                        part.footprint,
                        str(footprint.source_path),
                        footprint.source_sha256,
                    )
                )
                issues.extend(
                    f"{part.id}: {message}"
                    for message in validate_symbol_footprint(symbol, footprint)
                )
            except LibraryResolutionError as error:
                issues.append(str(error))
        unique = {(item.kind, item.library_id): item for item in locked}
        lock = CircuitLock(tuple(unique[key] for key in sorted(unique)))
        return lock, tuple(issues)

    def drift(self) -> tuple[Drift, ...]:
        state = ProjectState.load(self.state_path)
        if state is None:
            return ()
        actual = _actual_projection(KicadSchematic.load(self.schematic))
        drift: list[Drift] = []
        for circuit_id in sorted(set(state.applied) | set(actual)):
            old_fields = state.applied.get(circuit_id, {})
            new_fields = actual.get(circuit_id, {})
            for field in sorted(set(old_fields) | set(new_fields)):
                if old_fields.get(field) != new_fields.get(field):
                    drift.append(
                        Drift(circuit_id, field, old_fields.get(field), new_fields.get(field))
                    )
        return tuple(drift)

    def deploy(self, *, backup: bool = True) -> DeployResult:
        schematic = KicadSchematic.load(self.schematic)
        original = schematic.document.source
        original_hash = _sha256(original)
        desired = self.synth()
        plan, resolver = self._plan_with_resolver(desired, schematic)
        edits = edits_for_plan(plan, schematic, desired, resolver)
        patched = apply_edits(original, edits)

        # Reparse before touching the user's file.
        parse(patched)
        validated = KicadSchematic.from_text(patched, self.schematic)
        deploy_erc = (
            self.kicad_cli.validate(patched, self.schematic) if self.kicad_cli is not None else None
        )

        current = self.schematic.read_text(encoding="utf-8")
        if _sha256(current) != original_hash:
            raise RuntimeError("schematic changed while deploy was in progress")

        backup_path: Path | None = None
        if edits:
            temporary = self.schematic.with_suffix(self.schematic.suffix + ".circuitdk.tmp")
            temporary.write_text(patched, encoding="utf-8", newline="")
            if backup:
                backup_path = self.schematic.with_suffix(self.schematic.suffix + ".bak")
                shutil.copy2(self.schematic, backup_path)
            os.replace(temporary, self.schematic)

        state = ProjectState(
            applied=_actual_projection(validated),
            schematic_sha256=_sha256(patched),
        )
        state.write_atomic(self.state_path)
        lock, _ = self.library_lock()
        lock.write_atomic(self.lock_path)
        return DeployResult(
            plan,
            sum(action.kind == "create" for action in plan.applicable),
            sum(action.kind == "update" for action in plan.applicable),
            sum(action.kind == "delete" for action in plan.applicable),
            sum(action.applicable for action in plan.no_connect_actions),
            plan.pending_count,
            backup_path,
            deploy_erc,
        )

    def run_tests(self) -> ProjectTestResult:
        desired = self.synth()
        schematic = KicadSchematic.load(self.schematic)
        plan, _ = self._plan_with_resolver(desired, schematic)
        _, library_issues = self.library_lock()
        pin_coverage = validate_pin_coverage(desired)
        if self.kicad_cli is None:
            return ProjectTestResult(
                plan,
                None,
                None,
                pin_coverage,
                library_issues,
                ("kicad-cli was not found; set CIRCUITDK_KICAD_CLI",),
            )
        try:
            netlist = self.kicad_cli.export_netlist_xml(self.schematic)
            actual = actual_circuit_from_xml(desired, schematic, netlist)
            connectivity = compare_connectivity(desired, actual)
            erc = self.kicad_cli.erc(self.schematic)
        except Exception as error:
            return ProjectTestResult(
                plan,
                None,
                None,
                pin_coverage,
                library_issues,
                (str(error),),
            )
        return ProjectTestResult(
            plan,
            connectivity,
            erc,
            pin_coverage,
            library_issues,
            (),
        )

    def inspect(self) -> dict[str, Any]:
        desired = self.synth()
        schematic = KicadSchematic.load(self.schematic)
        plan, _ = self._plan_with_resolver(desired, schematic)
        return {
            "desired": desired.to_dict(),
            "actual_managed": _actual_projection(schematic),
            "plan": _plan_dict(plan),
            "drift": [asdict(item) for item in self.drift()],
            "libraries": _library_inspection(self),
        }

    def adopt(self, reference: str, circuit_id: str) -> None:
        if circuit_id not in {part.id for part in self.synth().parts}:
            raise KeyError(f"desired circuit has no part {circuit_id}")
        schematic = KicadSchematic.load(self.schematic)
        matches = [symbol for symbol in schematic.symbols if symbol.reference == reference]
        if len(matches) != 1:
            raise ValueError(f"expected exactly one schematic symbol with reference {reference}")
        symbol = matches[0]
        if symbol.circuit_id is not None:
            raise ValueError(f"{reference} is already managed as {symbol.circuit_id}")
        x, y, _ = symbol.position
        property_text = (
            f'(property "CircuitDK:ID" "{circuit_id}"\n'
            f"      (at {x:g} {y:g} 0)\n"
            "      (hide yes)\n"
            "      (effects (font (size 1.27 1.27)))\n"
            "    )\n    "
        )
        edit = TextEdit.replace(
            symbol.property_insertion_offset,
            symbol.property_insertion_offset,
            property_text,
        )
        self._write_schematic(apply_edits(schematic.document.source, [edit]))

    def move(self, old_id: str, new_id: str) -> None:
        schematic = KicadSchematic.load(self.schematic)
        symbol = schematic.managed_symbols.get(old_id)
        if symbol is None:
            raise KeyError(f"managed symbol does not exist: {old_id}")
        prop = symbol.find_property("CircuitDK:ID")
        if prop is None:
            raise RuntimeError("managed symbol has no CircuitDK:ID property")
        self._write_schematic(apply_edits(schematic.document.source, [prop.set_value(new_id)]))

    def _write_schematic(self, source: str) -> None:
        KicadSchematic.from_text(source, self.schematic)
        if self.kicad_cli is not None:
            self.kicad_cli.validate(source, self.schematic)
        temporary = self.schematic.with_suffix(self.schematic.suffix + ".circuitdk.tmp")
        temporary.write_text(source, encoding="utf-8", newline="")
        backup = self.schematic.with_suffix(self.schematic.suffix + ".bak")
        shutil.copy2(self.schematic, backup)
        os.replace(temporary, self.schematic)


def _sha256(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _resolve_library_pins(circuit: CircuitIR, resolver: SymbolResolver) -> CircuitIR:
    replacements: dict[str, PinRef] = {}
    parts: list[PartIR] = []
    for part in circuit.parts:
        if not part.resolve_pins:
            parts.append(part)
            continue
        definition = resolver.resolve(part.symbol)
        pins = [
            PinRef(part.id, pin.number, pin.name or pin.number)
            for pin in definition.pins
            if pin.unit == 1
        ]
        for pin in part.pins:
            overridden = pin.name != pin.number
            resolved = definition.pin(pin.number if overridden else pin.name)
            replacement = PinRef(
                part.id,
                resolved.number,
                pin.name if overridden else resolved.name or pin.name,
            )
            replacements[pin.key] = replacement
            pins = [item for item in pins if item.number != replacement.number]
            pins.append(replacement)
        parts.append(
            PartIR(
                part.id,
                part.symbol,
                part.value,
                part.footprint,
                tuple(sorted(pins)),
                part.in_bom,
                part.on_board,
                part.dnp,
                True,
            )
        )

    def replace(pin: PinRef) -> PinRef:
        return replacements.get(pin.key, pin)

    nets = tuple(
        NetIR(net.id, tuple(sorted(replace(pin) for pin in net.pins)), net.kind, net.voltage)
        for net in circuit.nets
    )
    no_connects = tuple(sorted(replace(pin) for pin in circuit.no_connects))
    return CircuitIR(
        circuit.id,
        tuple(parts),
        nets,
        no_connects,
        circuit.schema_version,
    )


def _actual_projection(schematic: KicadSchematic) -> dict[str, dict[str, object]]:
    return {
        circuit_id: _symbol_projection(symbol)
        for circuit_id, symbol in sorted(schematic.managed_symbols.items())
    }


def _symbol_projection(symbol: KicadSymbol) -> dict[str, object]:
    value = symbol.find_property("Value")
    footprint = symbol.find_property("Footprint")
    return {
        "symbol": symbol.library_id,
        "value": value.value if value is not None else None,
        "footprint": (footprint.value or None) if footprint is not None else None,
        "in_bom": _bool_flag(symbol, "in_bom"),
        "on_board": _bool_flag(symbol, "on_board"),
        "dnp": _bool_flag(symbol, "dnp"),
    }


def _bool_flag(symbol: KicadSymbol, name: str) -> bool | None:
    flag = symbol.flag(name)
    return flag[0] == "yes" if flag is not None else None


def _plan_dict(plan: DeploymentPlan) -> dict[str, object]:
    return {
        "has_changes": plan.has_changes,
        "actions": [asdict(action) for action in plan.actions],
        "no_connect_actions": [asdict(action) for action in plan.no_connect_actions],
    }


def _library_inspection(project: KicadProject) -> dict[str, object]:
    current, issues = project.library_lock()
    previous = CircuitLock.load(project.lock_path)
    return {
        "issues": issues,
        "lock_differences": previous.differences(current) if previous is not None else (),
        "resolved": [asdict(item) for item in current.libraries],
    }
