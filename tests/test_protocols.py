from __future__ import annotations

import warnings

import pytest

from circuitdk import Circuit, Part
from circuitdk.protocols import I2C, SPI, UART, ProtocolPinWarning, pin_override


def _part(circuit: Circuit, name: str, pins: tuple[str, ...]) -> Part:
    return Part(
        circuit,
        name,
        symbol=f"Test:{name}",
        pins={pin: str(index) for index, pin in enumerate(pins, start=1)},
    )


def _net_members(circuit: Circuit) -> set[frozenset[str]]:
    return {frozenset(pin.key for pin in net.pins) for net in circuit.synth().nets}


def test_spi_connects_shared_bus_and_peripheral_selects() -> None:
    circuit = Circuit("Board")
    controller = _part(
        circuit,
        "Controller",
        ("SPI1_SCK", "SPI1_MOSI", "SPI1_MISO", "CS0", "CS1"),
    )
    first = _part(circuit, "First", ("SCLK", "SDI", "SDO", "nCS"))
    second = _part(circuit, "Second", ("SCK", "MOSI", "MISO", "NSS"))

    spi = SPI(
        circuit,
        "Sensors",
        controller=controller,
        sck="SPI1_SCK",
        mosi="SPI1_MOSI",
        miso="SPI1_MISO",
    )
    spi.add_peripheral(
        device=first,
        sck="SCLK",
        sdi="SDI",
        sdo="SDO",
        controller_cs="CS0",
        device_cs="nCS",
    )
    spi.add_peripheral(
        device=second,
        sck="SCK",
        mosi="MOSI",
        miso="MISO",
        controller_cs="CS1",
        device_cs="NSS",
    )

    members = _net_members(circuit)
    assert (
        frozenset(
            {
                controller.pin("SPI1_SCK").ref.key,
                first.pin("SCLK").ref.key,
                second.pin("SCK").ref.key,
            }
        )
        in members
    )
    assert (
        frozenset(
            {
                controller.pin("SPI1_MOSI").ref.key,
                first.pin("SDI").ref.key,
                second.pin("MOSI").ref.key,
            }
        )
        in members
    )
    assert (
        frozenset(
            {
                controller.pin("SPI1_MISO").ref.key,
                first.pin("SDO").ref.key,
                second.pin("MISO").ref.key,
            }
        )
        in members
    )


def test_spi_supports_pin_numbers_and_one_way_data() -> None:
    circuit = Circuit("Board")
    controller = _part(circuit, "Controller", ("SCK", "MOSI"))
    display = _part(circuit, "Display", ("SCLK", "DIN"))

    spi = SPI(circuit, "DisplayBus", controller=controller, sck=1, sdo=2)
    spi.add_peripheral(device=display, sck=1, sdi=2)

    assert len(circuit.synth().nets) == 2


def test_spi_rejects_duplicate_aliases_and_half_of_a_chip_select() -> None:
    circuit = Circuit("Board")
    controller = _part(circuit, "Controller", ("SCK", "MOSI", "CS"))
    sensor = _part(circuit, "Sensor", ("SCK", "SDI", "NCS"))

    with pytest.raises(ValueError, match="aliases"):
        SPI(circuit, "InvalidAliases", controller=controller, sck="SCK", mosi="MOSI", sdo="MOSI")

    spi = SPI(circuit, "Bus", controller=controller, sck="SCK", mosi="MOSI")
    with pytest.raises(ValueError, match="specified together"):
        spi.add_peripheral(
            device=sensor,
            sck="SCK",
            sdi="SDI",
            controller_cs="CS",
        )


def test_protocol_warns_only_for_clear_role_mismatches() -> None:
    circuit = Circuit("Board")
    controller = _part(circuit, "Controller", ("MISO", "GPIO2", "MOSI"))

    with pytest.warns(ProtocolPinWarning, match="assigned as SPI clock"):
        SPI(circuit, "Wrong", controller=controller, sck="MISO", mosi="MOSI")

    with warnings.catch_warnings():
        warnings.simplefilter("error", ProtocolPinWarning)
        SPI(circuit, "Unknown", controller=controller, sck="GPIO2", mosi="MOSI")


def test_pin_override_suppresses_name_and_owner_warnings() -> None:
    circuit = Circuit("Board")
    controller = _part(circuit, "Controller", ("MOSI",))
    external = _part(circuit, "External", ("MISO",))

    with warnings.catch_warnings():
        warnings.simplefilter("error", ProtocolPinWarning)
        SPI(
            circuit,
            "Overridden",
            controller=controller,
            sck=pin_override(
                external.pin("MISO"),
                reason="The legacy symbol name is incorrect.",
            ),
            mosi="MOSI",
        )

    with pytest.raises(ValueError, match="non-empty reason"):
        pin_override(external.pin("MISO"), reason=" ")


def test_i2c_connects_multiple_peripherals_and_detects_swaps() -> None:
    circuit = Circuit("Board")
    controller = _part(circuit, "Controller", ("I2C1_SCL", "I2C1_SDA"))
    sensor = _part(circuit, "Sensor", ("SCL", "SDA"))
    eeprom = _part(circuit, "Eeprom", ("SCL", "SDA"))

    bus = I2C(
        circuit,
        "ControlBus",
        controller=controller,
        scl="I2C1_SCL",
        sda="I2C1_SDA",
    )
    bus.add_peripheral(device=sensor, scl="SCL", sda="SDA")
    bus.add_peripheral(device=eeprom, scl="SCL", sda="SDA")
    assert len(circuit.synth().nets) == 2

    with pytest.warns(ProtocolPinWarning, match="I2C clock"):
        I2C(
            circuit,
            "Swapped",
            controller=controller,
            scl="I2C1_SDA",
            sda="I2C1_SCL",
        )


def test_uart_cross_connects_and_supports_one_way_links() -> None:
    circuit = Circuit("Board")
    controller = _part(circuit, "Controller", ("UART0_TXD", "UART0_RXD"))
    adapter = _part(circuit, "Adapter", ("TX", "RX"))

    UART(
        circuit,
        "Debug",
        left=controller,
        left_tx="UART0_TXD",
        left_rx="UART0_RXD",
        right=adapter,
        right_tx="TX",
        right_rx="RX",
    )
    members = _net_members(circuit)
    assert frozenset({controller.pin("UART0_TXD").ref.key, adapter.pin("RX").ref.key}) in members
    assert frozenset({controller.pin("UART0_RXD").ref.key, adapter.pin("TX").ref.key}) in members

    tx_only = Circuit("TxOnly")
    source = _part(tx_only, "Source", ("TX",))
    sink = _part(tx_only, "Sink", ("RX",))
    UART(tx_only, "Log", left=source, left_tx="TX", right=sink, right_rx="RX")
    assert len(tx_only.synth().nets) == 1
