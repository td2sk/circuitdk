from __future__ import annotations

from decimal import Decimal

import pytest

from circuitdk import (
    A,
    Circuit,
    F,
    GHz,
    H,
    Hz,
    MHz,
    Mohm,
    THz,
    V,
    fA,
    fF,
    kA,
    kHz,
    kohm,
    kV,
    mA,
    mF,
    mH,
    mV,
    nA,
    nF,
    nH,
    nV,
    ohm,
    pA,
    pF,
    pH,
    uA,
    uF,
    uH,
    uV,
)
from circuitdk.parts import Capacitor, Inductor, Resistor
from circuitdk.units import format_schematic_value


@pytest.mark.parametrize(
    ("quantity", "expected"),
    (
        (470 * ohm, "470R"),
        (4.7 * ohm, "4R7"),
        (0.22 * ohm, "R22"),
        (0 * ohm, "0R"),
        (3 * kohm, "3k"),
        (3.3 * kohm, "3k3"),
        (1 * Mohm, "1M"),
        (100 * nF, "100n"),
        (4.7 * uF, "4u7"),
        (0.3 * uF, "0.3u"),
        (2.2 * mH, "2m2"),
        (10 * uH, "10u"),
        (0.47 * uH, "0.47u"),
        (12 * nH, "12n"),
        (2.5 * F, "2.5"),
        (1.5 * H, "1.5"),
    ),
)
def test_formats_passive_values_for_kicad(quantity, expected: str) -> None:  # type: ignore[no-untyped-def]
    assert format_schematic_value(quantity) == expected


def test_explicit_string_value_is_preserved() -> None:
    assert format_schematic_value("3k3 custom") == "3k3 custom"


def test_quantity_remains_numeric_and_converts_between_compatible_units() -> None:
    resistance = 3.3 * kohm

    assert resistance == 3300 * ohm
    assert resistance.in_unit(kohm) == Decimal("3.3")
    assert resistance.in_unit(ohm) == Decimal("3300")

    with pytest.raises(ValueError, match="cannot convert"):
        resistance.in_unit(uF)


def test_quantity_supports_scalar_multiplication_from_either_side() -> None:
    resistance = 48 * kohm

    assert resistance * 2 == 96 * kohm
    assert 2 * resistance == 96 * kohm
    assert format_schematic_value(2 * resistance) == "96k"


def test_quantity_supports_arithmetic_and_comparison() -> None:
    total = 1 * kohm + 500 * ohm
    difference = 1 * kohm - 1.5 * kohm

    assert total == 1.5 * kohm
    assert format_schematic_value(total) == "1k5"
    assert format_schematic_value(500 * ohm + 1 * kohm) == "1k5"
    assert format_schematic_value(500 * ohm + 500 * ohm) == "1000R"
    assert difference == -500 * ohm
    assert +difference is difference
    assert -difference == 500 * ohm
    assert abs(difference) == 500 * ohm
    assert 999 * ohm < 1 * kohm
    assert 1 * kohm <= 1000 * ohm
    assert 1.1 * kohm > 1000 * ohm
    assert 1 * kohm >= 1000 * ohm


def test_quantity_supports_scalar_and_same_dimension_division() -> None:
    resistance = 10 * kohm

    assert resistance / 2 == 5 * kohm
    assert resistance / (2 * kohm) == Decimal("5")

    with pytest.raises(ZeroDivisionError):
        _ = resistance / 0
    with pytest.raises(ZeroDivisionError):
        _ = resistance / (0 * ohm)


def test_mixed_scales_use_automatic_display_prefix() -> None:
    resistance = 1 * kohm + 500 * ohm
    capacitance = 0.3 * uF + 100 * nF

    assert format_schematic_value(resistance) == "1k5"
    assert format_schematic_value(capacitance) == "400n"
    assert format_schematic_value(resistance.to(ohm)) == "1500R"
    assert format_schematic_value(resistance.to(kohm)) == "1k5"
    assert resistance.to(kohm).in_unit(kohm) == Decimal("1.5")


@pytest.mark.parametrize(
    ("unit", "dimension", "scale"),
    (
        (ohm, "Ω", "1"),
        (kohm, "Ω", "1e3"),
        (Mohm, "Ω", "1e6"),
        (F, "F", "1"),
        (mF, "F", "1e-3"),
        (uF, "F", "1e-6"),
        (nF, "F", "1e-9"),
        (pF, "F", "1e-12"),
        (fF, "F", "1e-15"),
        (H, "H", "1"),
        (mH, "H", "1e-3"),
        (uH, "H", "1e-6"),
        (nH, "H", "1e-9"),
        (pH, "H", "1e-12"),
        (kV, "V", "1e3"),
        (V, "V", "1"),
        (mV, "V", "1e-3"),
        (uV, "V", "1e-6"),
        (nV, "V", "1e-9"),
        (kA, "A", "1e3"),
        (A, "A", "1"),
        (mA, "A", "1e-3"),
        (uA, "A", "1e-6"),
        (nA, "A", "1e-9"),
        (pA, "A", "1e-12"),
        (fA, "A", "1e-15"),
        (Hz, "Hz", "1"),
        (kHz, "Hz", "1e3"),
        (MHz, "Hz", "1e6"),
        (GHz, "Hz", "1e9"),
        (THz, "Hz", "1e12"),
    ),
)
def test_public_unit_constants(unit, dimension: str, scale: str) -> None:  # type: ignore[no-untyped-def]
    assert unit.symbol == dimension
    assert unit.scale == Decimal(scale)


@pytest.mark.parametrize(
    ("quantity", "human", "schematic"),
    (
        (1 * fF, "1 fF", "1f"),
        (1 * pH, "1 pH", "1p"),
        (250 * uV, "250 µV", "250 µV"),
        (3 * mA, "3 mA", "3 mA"),
        (16 * MHz, "16 MHz", "16MHz"),
        (1.5 * GHz, "1.5 GHz", "1.5GHz"),
        (1 * THz, "1 THz", "1THz"),
    ),
)
def test_extended_units_have_consistent_human_and_schematic_display(
    quantity,
    human: str,
    schematic: str,  # type: ignore[no-untyped-def]
) -> None:
    assert str(quantity) == human
    assert format_schematic_value(quantity) == schematic


@pytest.mark.parametrize(
    ("quantity", "schematic"),
    (
        (1 * THz + 0 * Hz, "1THz"),
        (1 * GHz + 0 * Hz, "1GHz"),
        (1 * MHz + 0 * Hz, "1MHz"),
        (1 * kHz + 0 * Hz, "1kHz"),
        (1 * fF + 0 * F, "1f"),
    ),
)
def test_automatic_display_uses_common_engineering_prefixes(
    quantity,
    schematic: str,  # type: ignore[no-untyped-def]
) -> None:
    assert format_schematic_value(quantity) == schematic


def test_quantity_rejects_arithmetic_across_dimensions() -> None:
    resistance = 1 * kohm
    capacitance = 1 * uF

    with pytest.raises(ValueError, match="incompatible dimensions"):
        _ = resistance + capacitance
    with pytest.raises(ValueError, match="incompatible dimensions"):
        _ = resistance - capacitance
    with pytest.raises(ValueError, match="incompatible dimensions"):
        _ = resistance / capacitance
    with pytest.raises(ValueError, match="incompatible dimensions"):
        _ = resistance < capacitance
    with pytest.raises(ValueError, match="cannot convert"):
        resistance.to(uF)


def test_passive_patterns_expose_typed_values() -> None:
    circuit = Circuit("Passives")
    resistor = Resistor(circuit, "R", resistance=4.7 * kohm)
    capacitor = Capacitor(circuit, "C", capacitance=0.3 * uF)
    inductor = Inductor(circuit, "L", inductance=2.2 * mH)

    assert resistor.resistance == 4.7 * kohm
    assert capacitor.capacitance == 0.3 * uF
    assert inductor.inductance == 2.2 * mH
    assert circuit.synth().managed_projection()["/Passives/R"]["value"] == "4k7"
