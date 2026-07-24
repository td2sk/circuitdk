from __future__ import annotations

from decimal import Decimal

import pytest

from circuitdk import Circuit, F, H, Mohm, kohm, mH, nF, nH, ohm, uF, uH
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
