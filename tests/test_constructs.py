from __future__ import annotations

import pytest

from circuitdk import (
    Circuit,
    DecouplingCapacitor,
    LedIndicator,
    Part,
    SpiInterface,
    V,
    VoltageDivider,
    kohm,
    nF,
    pull_down,
    validate_intents,
    validate_pin_coverage,
)


def test_synthesizes_deterministic_parts_and_net_partitions() -> None:
    circuit = Circuit("Blinky")
    gnd = circuit.ground()
    vcc = circuit.power("VCC", voltage=5 * V)
    mcu = Part(
        circuit,
        "Mcu",
        symbol="MCU:Chip",
        pins={"OUT": "1", "VCC": "2", "GND": "3"},
    )
    resistor = Part(
        circuit,
        "Resistor",
        symbol="Device:R",
        value=1 * kohm,
        pins={"1": "1", "2": "2"},
    )
    vcc.connect(mcu.pin("VCC"))
    gnd.connect(mcu.pin("GND"), resistor.pin("2"))
    circuit.connect(mcu.pin("OUT"), resistor.pin("1"))

    first = circuit.synth()
    second = circuit.synth()

    assert first == second
    assert [part.id for part in first.parts] == ["/Blinky/Mcu", "/Blinky/Resistor"]
    assert len(first.nets) == 3
    assert first.part("/Blinky/Resistor").value == "1 kΩ"


def test_connecting_two_named_nets_is_rejected() -> None:
    circuit = Circuit("Invalid")
    left = circuit.net("LEFT")
    right = circuit.net("RIGHT")
    part = Part(circuit, "Part", symbol="Test:P", pins={"1": "1"})
    left.connect(part.pin("1"))
    right.connect(part.pin("1"))

    with pytest.raises(ValueError, match="shorted"):
        circuit.synth()


def test_high_level_patterns_register_parts_connectivity_and_intent() -> None:
    circuit = Circuit("Patterns")
    gnd = circuit.ground()
    mcu = Part(
        circuit,
        "Mcu",
        symbol="MCU:Chip",
        pins={"OUT": "1", "RESET": "2", "VCC": "3", "GND": "4"},
    )
    gnd.connect(mcu.pin("GND"))

    LedIndicator(circuit, "Status", drive=mcu.pin("OUT"), return_to=gnd, series_resistance=1 * kohm)
    pull_down(circuit, "ResetDefault", signal=mcu.pin("RESET"), ground=gnd, resistance=10 * kohm)
    DecouplingCapacitor(
        circuit,
        "McuDecoupling",
        power_pin=mcu.pin("VCC"),
        ground=gnd,
        capacitance=100 * nF,
    )

    ir = circuit.synth()
    assert len(ir.parts) == 5
    assert {intent.kind for intent in ir.intents} == {
        "current_limited_led",
        "decoupling",
        "default_logic_level",
    }
    assert validate_intents(ir).ok


def test_voltage_divider_and_interfaces_create_semantic_connectivity() -> None:
    circuit = Circuit("Interfaces")
    gnd = circuit.ground()
    supply = circuit.power("VCC", voltage=5 * V)
    divider = VoltageDivider(
        circuit,
        "BatterySense",
        input_net=supply,
        return_to=gnd,
        upper_resistance=100 * kohm,
        lower_resistance=100 * kohm,
    )
    controller = Part(
        circuit,
        "Controller",
        symbol="Test:Controller",
        pins={"SCK": "1", "MOSI": "2", "MISO": "3", "CS": "4"},
    )
    sensor = Part(
        circuit,
        "Sensor",
        symbol="Test:Sensor",
        pins={"SCK": "1", "MOSI": "2", "MISO": "3", "CS": "4"},
    )
    controller_spi = SpiInterface(
        controller,
        "Spi",
        sck=controller.pin("SCK"),
        mosi=controller.pin("MOSI"),
        miso=controller.pin("MISO"),
        chip_select=controller.pin("CS"),
    )
    sensor_spi = SpiInterface(
        sensor,
        "Spi",
        sck=sensor.pin("SCK"),
        mosi=sensor.pin("MOSI"),
        miso=sensor.pin("MISO"),
        chip_select=sensor.pin("CS"),
    )
    controller_spi.connect(sensor_spi)

    ir = circuit.synth()

    assert divider.output.path == "/Interfaces/BatterySense/Output"
    assert validate_intents(ir).ok
    assert sum(len(net.pins) == 2 for net in ir.nets) >= 4


def test_pin_cannot_be_connected_and_no_connect() -> None:
    circuit = Circuit("InvalidNoConnect")
    part = Part(circuit, "P", symbol="Test:P", pins={"1": "1", "2": "2"})
    circuit.connect(part.pin("1"), part.pin("2"))
    part.pin("1").no_connect()

    with pytest.raises(ValueError, match="both connected and no-connect"):
        circuit.synth()


def test_pin_coverage_distinguishes_no_connect_from_unspecified() -> None:
    circuit = Circuit("Coverage")
    part = Part(circuit, "P", symbol="Test:P", pins={"USED": "1", "NC": "2"})
    part.pin("NC").no_connect()

    coverage = validate_pin_coverage(circuit.synth())

    assert coverage.unspecified == ("/Coverage/P:1",)
