from __future__ import annotations

from pathlib import Path

import pytest

import circuitdk.project as project_module
from circuitdk import Circuit, KicadProject, Part
from circuitdk.targets.kicad.libraries import (
    EmbeddedSymbolDefinition,
    SymbolDefinition,
    SymbolPinDefinition,
)


class _StaticSymbolResolver:
    def __init__(self, definition: SymbolDefinition) -> None:
        self.definition = definition

    def resolve(self, library_id: str) -> SymbolDefinition:
        assert library_id == self.definition.library_id
        return self.definition

    def materialize_for_schematic(self, library_id: str) -> EmbeddedSymbolDefinition:
        raise AssertionError(f"unexpected materialization: {library_id}")

    def dependencies(self, definition: SymbolDefinition) -> tuple[SymbolDefinition, ...]:
        return ()


def test_synth_with_explicit_pins_does_not_load_kicad_infrastructure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected_call(*args: object, **kwargs: object) -> None:
        raise AssertionError(f"unexpected KiCad infrastructure load: {args!r} {kwargs!r}")

    monkeypatch.setattr(project_module.KicadSymbolResolver, "for_project", unexpected_call)
    monkeypatch.setattr(project_module.KicadFootprintResolver, "for_project", unexpected_call)
    monkeypatch.setattr(project_module.KicadCli, "discover", unexpected_call)

    circuit = Circuit("Lazy")
    part = Part(circuit, "Part", symbol="Test:Part", pins={"IN": "1"})
    part.pin("IN").no_connect()
    project = KicadProject(circuit, tmp_path / "missing.kicad_sch")

    synthesized = project.synth()

    assert synthesized.parts[0].pins[0].number == "1"


def test_unchanged_plan_with_explicit_pins_does_not_load_library_resolvers(
    schematic_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected_call(*args: object, **kwargs: object) -> None:
        raise AssertionError(f"unexpected library resolver load: {args!r} {kwargs!r}")

    monkeypatch.setattr(project_module.KicadSymbolResolver, "for_project", unexpected_call)
    monkeypatch.setattr(project_module.KicadFootprintResolver, "for_project", unexpected_call)

    circuit = Circuit("Blinky")
    Part(
        circuit,
        "Resistor",
        symbol="Device:R",
        value="10 k",
        footprint="Resistor_SMD:R_0603_1608Metric",
        pins={"1": "1", "2": "2"},
    )
    project = KicadProject(circuit, schematic_path, validate_with_kicad=False)

    assert not project.plan().has_changes


def test_pin_override_preserves_alias_and_resolves_other_library_pins(tmp_path: Path) -> None:
    definition = SymbolDefinition(
        library_id="Test:Mcu",
        source_path=tmp_path / "Test.kicad_sym",
        source_sha256="test",
        source_text="",
        pins=(
            SymbolPinDefinition("4", "GND", "power_in", 1, 0, 0, 0),
            SymbolPinDefinition("5", "AREF/PB0", "bidirectional", 1, 0, 0, 0),
            SymbolPinDefinition("8", "VCC", "power_in", 1, 0, 0, 0),
        ),
        reference_prefix="U",
    )
    circuit = Circuit("Aliases")
    mcu = Part(circuit, "Mcu", symbol="Test:Mcu", pin_overrides={"PB0": "5"})
    circuit.power("VCC").connect(mcu.pin("VCC"))
    circuit.ground().connect(mcu.pin("GND"))
    mcu.pin("PB0").no_connect()
    project = KicadProject(
        circuit,
        tmp_path / "missing.kicad_sch",
        symbol_resolver=_StaticSymbolResolver(definition),
        validate_with_kicad=False,
    )

    desired = project.synth()
    resolved_mcu = desired.part("/Aliases/Mcu")

    assert resolved_mcu.pin("PB0").number == "5"
    assert resolved_mcu.pin("VCC").number == "8"
    assert resolved_mcu.pin("GND").number == "4"
    assert desired.no_connects == (resolved_mcu.pin("PB0"),)


def test_explicit_pins_and_pin_overrides_are_mutually_exclusive() -> None:
    circuit = Circuit("Invalid")

    with pytest.raises(ValueError, match="cannot be used together"):
        Part(
            circuit,
            "Part",
            symbol="Test:Part",
            pins={"IN": "1"},
            pin_overrides={"INPUT": "1"},
        )
