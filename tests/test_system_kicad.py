from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from circuitdk import Circuit, KicadProject, Part, kohm
from circuitdk.targets.kicad import KicadCli, KicadSchematic, LibraryResolutionError
from lossless_sexpr import TextEdit, apply_edits


@pytest.mark.kicad
def test_real_kicad_10_accepts_deploy_and_passes_erc(tmp_path: Path) -> None:
    cli = KicadCli.discover()
    if cli is None:
        pytest.skip("KiCad CLI is not installed")
    if not cli.version().startswith("10."):
        pytest.skip(f"KiCad 10 required, found {cli.version()}")
    schematic = tmp_path / "system.kicad_sch"
    shutil.copy2(Path(__file__).parent / "fixtures/kicad10/empty.kicad_sch", schematic)
    circuit = Circuit("System")
    resistor = Part(circuit, "Resistor", symbol="Device:R", value=10 * kohm)
    resistor.pin("1").no_connect()
    resistor.pin("2").no_connect()
    project = KicadProject(circuit, schematic, state_directory=tmp_path / ".circuitdk")
    try:
        project.symbol_resolver.resolve("Device:R")
    except LibraryResolutionError as error:
        pytest.skip(str(error))

    deployed = project.deploy()
    result = project.run_tests()

    assert deployed.complete
    assert deployed.erc is not None and deployed.erc.ok
    assert result.ok
    assert result.connectivity is not None and result.connectivity.ok
    assert result.erc is not None and result.erc.violations == ()
    assert project.lock_path.exists()

    document = KicadSchematic.load(schematic)
    symbol = document.managed_symbols["/System/Resistor"]
    managed_property = symbol.find_property("CircuitDK:ID")
    assert managed_property is not None
    schematic.write_text(
        apply_edits(
            document.document.source,
            [TextEdit(managed_property.node.span, "")],
        ),
        encoding="utf-8",
    )
    project.adopt("R1", "/System/Resistor")
    project.move("/System/Resistor", "/System/Renamed")
    assert "/System/Renamed" in KicadSchematic.load(schematic).managed_symbols
    assert '<comp ref="R1">' in cli.export_netlist_xml(schematic)


@pytest.mark.kicad
@pytest.mark.parametrize("angle", [0, 90, 180, 270])
@pytest.mark.parametrize("mirror", [None, "x", "y"])
def test_asymmetric_connector_no_connects_match_kicad_pin_positions(
    tmp_path: Path, angle: int, mirror: str | None
) -> None:
    cli = KicadCli.discover()
    if cli is None or not cli.version().startswith("10."):
        pytest.skip("KiCad 10 CLI is not installed")
    schematic = tmp_path / "connector.kicad_sch"
    shutil.copy2(Path(__file__).parent / "fixtures/kicad10/empty.kicad_sch", schematic)
    circuit = Circuit("Connector")
    connector = Part(circuit, "J", symbol="Connector_Generic:Conn_01x08")
    for number in range(1, 9):
        connector.pin(str(number)).no_connect()
    project = KicadProject(
        circuit, schematic, state_directory=tmp_path / "state", validate_with_kicad=False
    )
    project.deploy()
    project.kicad_cli = cli

    # Move the symbol independently of the planner, then let KiCad's ERC judge
    # whether the newly reconciled markers really cover the transformed pins.
    document = KicadSchematic.load(schematic)
    symbol = document.managed_symbols["/Connector/J"]
    at = symbol.node.first_list("at")
    assert at is not None
    transform = f"(at 25.4 25.4 {angle})"
    if mirror is not None:
        transform += f" (mirror {mirror})"
    schematic.write_text(
        apply_edits(
            document.document.source,
            [TextEdit(at.span, transform)]
            + [TextEdit(marker.node.span, "") for marker in document.no_connects],
        ),
        encoding="utf-8",
    )

    deployed = project.deploy()

    assert deployed.erc is not None
    assert deployed.erc.violations == ()
    assert cli.erc(schematic).violations == ()
    assert not project.plan().has_changes

    # Removing one declaration must delete precisely that marker. KiCad should
    # report only pin 8 unconnected, rather than an off-pin no-connect marker.
    remaining = Circuit("Connector")
    remaining_connector = Part(remaining, "J", symbol="Connector_Generic:Conn_01x08")
    for number in range(1, 8):
        remaining_connector.pin(str(number)).no_connect()
    project.circuit = remaining
    plan = project.plan()
    assert len(plan.no_connect_actions) == 1
    assert plan.no_connect_actions[0].kind == "delete"
    assert plan.no_connect_actions[0].pin_key == "/Connector/J:8"
    project.kicad_cli = None
    project.deploy()
    violations = cli.erc(schematic).violations
    assert len(violations) == 1
    assert violations[0].violation_type == "pin_not_connected"
    assert any("[Pin_8," in item.description for item in violations[0].items)


@pytest.mark.kicad
def test_real_kicad_netlist_reports_manual_wiring_pending(tmp_path: Path) -> None:
    cli = KicadCli.discover()
    if cli is None or not cli.version().startswith("10."):
        pytest.skip("KiCad 10 CLI is not installed")
    schematic = tmp_path / "manual-wiring.kicad_sch"
    shutil.copy2(Path(__file__).parent / "fixtures/kicad10/empty.kicad_sch", schematic)
    circuit = Circuit("Manual")
    left = Part(circuit, "Left", symbol="Device:R", value=10 * kohm)
    right = Part(circuit, "Right", symbol="Device:R", value=10 * kohm)
    circuit.connect(left.pin("1"), right.pin("1"))
    left.pin("2").no_connect()
    right.pin("2").no_connect()
    project = KicadProject(circuit, schematic, state_directory=tmp_path / ".circuitdk")

    deployed = project.deploy()
    result = project.run_tests()

    assert deployed.complete
    assert deployed.erc is not None and not deployed.erc.ok
    assert result.connectivity is not None and not result.connectivity.ok
    assert any(issue.kind == "missing_connection" for issue in result.connectivity.issues)
    assert not result.ok


@pytest.mark.kicad
def test_real_kicad_10_accepts_flattened_inherited_symbol(tmp_path: Path) -> None:
    cli = KicadCli.discover()
    if cli is None or not cli.version().startswith("10."):
        pytest.skip("KiCad 10 CLI is not installed")
    schematic = tmp_path / "inherited.kicad_sch"
    shutil.copy2(Path(__file__).parent / "fixtures/kicad10/empty.kicad_sch", schematic)
    circuit = Circuit("Inherited")
    Part(circuit, "Mcu", symbol="MCU_Microchip_ATtiny:ATtiny85-20P")
    project = KicadProject(circuit, schematic, state_directory=tmp_path / ".circuitdk")

    deployed = project.deploy()
    document = KicadSchematic.load(schematic)
    embedded = document.embedded_library_symbols["MCU_Microchip_ATtiny:ATtiny85-20P"]
    unit_names: list[str] = []
    for unit in embedded.child_lists("symbol"):
        unit_name = unit.atom(1)
        if unit_name is not None:
            unit_names.append(unit_name.value)

    assert document.embedded_library_ids == {"MCU_Microchip_ATtiny:ATtiny85-20P"}
    assert embedded.first_list("extends") is None
    assert unit_names == ["ATtiny85-20P_0_1", "ATtiny85-20P_1_1"]
    assert len(tuple(embedded.walk("pin"))) == 8
    assert deployed.erc is not None
    assert not any(
        violation.violation_type == "lib_symbol_mismatch" for violation in deployed.erc.violations
    )
    assert any(
        "U1" in item.description
        for violation in deployed.erc.errors
        if violation.violation_type == "pin_not_connected"
        for item in violation.items
    )

    definition = project.symbol_resolver.resolve("MCU_Microchip_ATtiny:ATtiny85-20P")
    legacy_dependencies = project.symbol_resolver.dependencies(definition)
    legacy_source = (
        legacy_dependencies[0].source_text + "\n    " + legacy_dependencies[1].source_text
    )
    schematic.write_text(
        apply_edits(document.document.source, [TextEdit(embedded.span, legacy_source)]),
        encoding="utf-8",
        newline="",
    )

    repair_plan = project.plan()
    repaired = project.deploy()
    repaired_document = KicadSchematic.load(schematic)
    repaired_embedded = repaired_document.embedded_library_symbols[
        "MCU_Microchip_ATtiny:ATtiny85-20P"
    ]

    assert any(
        change.field == "embedded_symbol"
        for action in repair_plan.actions
        for change in action.changes
    )
    assert repaired_document.embedded_library_ids == {"MCU_Microchip_ATtiny:ATtiny85-20P"}
    assert repaired_embedded.first_list("extends") is None
    assert repaired.erc is not None
    assert not any(
        violation.violation_type == "lib_symbol_mismatch" for violation in repaired.erc.violations
    )
