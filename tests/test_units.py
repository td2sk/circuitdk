from __future__ import annotations

from decimal import Decimal

import pytest

from circuitdk import (
    Capacitor,
    Circuit,
    F,
    H,
    Inductor,
    Mohm,
    Resistor,
    kohm,
    mH,
    nF,
    nH,
    ohm,
    uF,
    uH,
)
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


def test_passive_patterns_expose_typed_values() -> None:
    circuit = Circuit("Passives")
    resistor = Resistor(circuit, "R", resistance=4.7 * kohm)
    capacitor = Capacitor(circuit, "C", capacitance=0.3 * uF)
    inductor = Inductor(circuit, "L", inductance=2.2 * mH)

    assert resistor.resistance == 4.7 * kohm
    assert capacitor.capacitance == 0.3 * uF
    assert inductor.inductance == 2.2 * mH
    assert circuit.synth().managed_projection()["/Passives/R"]["value"] == "4k7"
