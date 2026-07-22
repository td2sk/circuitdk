from __future__ import annotations

from pathlib import Path

from circuitdk import Circuit, KicadProject, Part, kohm
from circuitdk.targets.kicad import (
    InMemorySymbolResolver,
    KicadSchematic,
    SymbolDefinition,
    SymbolPinDefinition,
    plan_deployment,
)


def _project(path: Path, state_directory: Path) -> KicadProject:
    circuit = Circuit("Blinky")
    Part(
        circuit,
        "Resistor",
        symbol="Device:R",
        value=47 * kohm,
        footprint="Resistor_SMD:R_0603_1608Metric",
        pins={"1": "1", "2": "2"},
    )
    return KicadProject(circuit, path, state_directory=state_directory, validate_with_kicad=False)


def test_typed_view_finds_only_root_instance(schematic_source: str) -> None:
    schematic = KicadSchematic.from_text(schematic_source)

    assert len(schematic.symbols) == 1
    symbol = schematic.managed_symbols["/Blinky/Resistor"]
    assert symbol.library_id == "Device:R"
    value = symbol.find_property("Value")
    assert value is not None
    assert value.value == "10 k"


def test_plan_reports_field_level_change(schematic_path: Path, tmp_path: Path) -> None:
    project = _project(schematic_path, tmp_path / "state")

    plan = plan_deployment(project.synth(), KicadSchematic.load(schematic_path))

    assert len(plan.actions) == 1
    assert plan.actions[0].kind == "update"
    assert plan.actions[0].changes[0].field == "value"


def test_deploy_updates_only_value_and_writes_state_and_backup(
    schematic_path: Path, schematic_source: str, tmp_path: Path
) -> None:
    project = _project(schematic_path, tmp_path / "state")

    result = project.deploy()

    updated = schematic_path.read_text(encoding="utf-8")
    assert result.complete
    assert result.applied_updates == 1
    assert updated == schematic_source.replace('"10 k"', '"47k"')
    assert (
        schematic_path.with_suffix(".kicad_sch.bak").read_text(encoding="utf-8") == schematic_source
    )
    assert project.state_path.exists()
    assert project.drift() == ()


def test_missing_symbol_is_inserted_and_removed_symbol_is_deleted(
    schematic_path: Path, tmp_path: Path
) -> None:
    circuit = Circuit("Blinky")
    Part(circuit, "New", symbol="Device:LED", pins={"A": "1", "K": "2"})
    project = KicadProject(
        circuit,
        schematic_path,
        state_directory=tmp_path / "state",
        validate_with_kicad=False,
    )

    result = project.deploy()

    assert result.complete
    assert result.plan.pending == ()
    assert {action.kind for action in result.plan.applicable} == {"create", "delete"}
    assert set(KicadSchematic.load(schematic_path).managed_symbols) == {"/Blinky/New"}


def test_new_symbol_and_no_connects_are_inserted_with_resolved_definition(
    tmp_path: Path,
) -> None:
    source = (Path(__file__).parent / "fixtures/kicad10/empty.kicad_sch").read_text(
        encoding="utf-8"
    )
    schematic = tmp_path / "new.kicad_sch"
    schematic.write_text(source, encoding="utf-8")
    definition = SymbolDefinition(
        "Test:R",
        tmp_path / "Test.kicad_sym",
        "abc",
        '(symbol "Test:R" (property "Reference" "R" (at 0 0 0)) '
        '(symbol "R_1_1" '
        "(pin passive line (at 0 2.54 270) (length 2.54) "
        '(name "" (effects (font (size 1.27 1.27)))) '
        '(number "1" (effects (font (size 1.27 1.27))))) '
        "(pin passive line (at 0 -2.54 90) (length 2.54) "
        '(name "" (effects (font (size 1.27 1.27)))) '
        '(number "2" (effects (font (size 1.27 1.27)))))))',
        (
            SymbolPinDefinition("1", "", "passive", 1, 0, 2.54, 270),
            SymbolPinDefinition("2", "", "passive", 1, 0, -2.54, 90),
        ),
        "R",
    )
    resolver = InMemorySymbolResolver((definition,))
    circuit = Circuit("New")
    resistor = Part(circuit, "R", symbol="Test:R", pins={"1": "1", "2": "2"})
    resistor.pin("1").no_connect()
    resistor.pin("2").no_connect()
    project = KicadProject(
        circuit,
        schematic,
        state_directory=tmp_path / "state",
        symbol_resolver=resolver,
        validate_with_kicad=False,
    )

    result = project.deploy()
    updated = KicadSchematic.load(schematic)

    assert result.complete
    assert set(updated.managed_symbols) == {"/New/R"}
    assert updated.embedded_library_ids == {"Test:R"}
    assert len(updated.no_connects) == 2


def test_adopt_and_move_update_only_stable_id(
    schematic_path: Path, schematic_source: str, tmp_path: Path
) -> None:
    unmanaged = schematic_source.replace(
        '    (property "CircuitDK:ID" "/Blinky/Resistor" (at 100 100 0) hide)\n', ""
    )
    schematic_path.write_text(unmanaged, encoding="utf-8")
    project = _project(schematic_path, tmp_path / "state")

    project.adopt("R1", "/Blinky/Resistor")
    project.move("/Blinky/Resistor", "/Blinky/Renamed")

    updated = KicadSchematic.load(schematic_path)
    assert set(updated.managed_symbols) == {"/Blinky/Renamed"}


def test_moved_declaration_preserves_symbol_and_updates_id(
    schematic_path: Path, tmp_path: Path
) -> None:
    circuit = Circuit("Blinky")
    Part(
        circuit,
        "Renamed",
        symbol="Device:R",
        value=10 * kohm,
        footprint="Resistor_SMD:R_0603_1608Metric",
        pins={"1": "1", "2": "2"},
    )
    project = KicadProject(
        circuit,
        schematic_path,
        state_directory=tmp_path / "state",
        moved={"/Blinky/Resistor": "/Blinky/Renamed"},
        validate_with_kicad=False,
    )
    original_uuid = KicadSchematic.load(schematic_path).symbols[0].uuid

    project.deploy()

    symbol = KicadSchematic.load(schematic_path).managed_symbols["/Blinky/Renamed"]
    assert symbol.uuid == original_uuid


def test_symbol_type_update_embeds_definition_and_rebuilds_pin_instances(
    schematic_path: Path, tmp_path: Path
) -> None:
    pins = tuple(
        SymbolPinDefinition(str(index), f"P{index}", "passive", 1, index * 2.54, 0, 180)
        for index in range(1, 4)
    )
    definition = SymbolDefinition(
        "Test:ThreePin",
        tmp_path / "Test.kicad_sym",
        "hash",
        '(symbol "Test:ThreePin" (property "Reference" "J" (at 0 0 0)))',
        pins,
        "J",
    )
    circuit = Circuit("Blinky")
    Part(
        circuit,
        "Resistor",
        symbol="Test:ThreePin",
        value="Connector",
        pins={"P1": "1", "P2": "2", "P3": "3"},
    )
    project = KicadProject(
        circuit,
        schematic_path,
        state_directory=tmp_path / "state",
        symbol_resolver=InMemorySymbolResolver((definition,)),
        validate_with_kicad=False,
    )

    project.deploy()

    updated = KicadSchematic.load(schematic_path)
    symbol = updated.managed_symbols["/Blinky/Resistor"]
    assert symbol.library_id == "Test:ThreePin"
    assert len(symbol.node.child_lists("pin")) == 3
    assert "Test:ThreePin" in updated.embedded_library_ids
