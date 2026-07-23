from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Self

_SCHEMATIC_PREFIXES: dict[tuple[str, Decimal], str] = {
    ("Ω", Decimal("1")): "R",
    ("Ω", Decimal("1000")): "k",
    ("Ω", Decimal("1000000")): "M",
    ("F", Decimal("1")): "",
    ("F", Decimal("0.000001")): "u",
    ("F", Decimal("0.000000001")): "n",
    ("H", Decimal("1")): "",
    ("H", Decimal("0.001")): "m",
    ("H", Decimal("0.000001")): "u",
    ("H", Decimal("0.000000001")): "n",
}

_HUMAN_SUFFIXES: dict[tuple[str, Decimal], str] = {
    ("Ω", Decimal("1")): "Ω",
    ("Ω", Decimal("1000")): "kΩ",
    ("Ω", Decimal("1000000")): "MΩ",
    ("F", Decimal("1")): "F",
    ("F", Decimal("0.000001")): "µF",
    ("F", Decimal("0.000000001")): "nF",
    ("H", Decimal("1")): "H",
    ("H", Decimal("0.001")): "mH",
    ("H", Decimal("0.000001")): "µH",
    ("H", Decimal("0.000000001")): "nH",
}


@dataclass(frozen=True, slots=True)
class Unit:
    symbol: str
    scale: Decimal = Decimal(1)

    def __rmul__(self, value: int | float | Decimal) -> Quantity:
        return Quantity(
            Decimal(str(value)) * self.scale,
            self.symbol,
            display_scale=self.scale,
        )


@dataclass(frozen=True, slots=True)
class Quantity:
    base_value: Decimal
    dimension: str
    display_scale: Decimal = field(default=Decimal(1), compare=False, repr=False)

    def __str__(self) -> str:
        suffix = _HUMAN_SUFFIXES.get((self.dimension, self.display_scale), self.dimension)
        return f"{_decimal_text(self.base_value / self.display_scale)} {suffix}"

    def __mul__(self, factor: int | float | Decimal) -> Self:
        return type(self)(
            self.base_value * Decimal(str(factor)),
            self.dimension,
            display_scale=self.display_scale,
        )

    def in_unit(self, unit: Unit) -> Decimal:
        """Return the numeric value expressed in ``unit``."""
        if unit.symbol != self.dimension:
            raise ValueError(f"cannot convert {self.dimension} to {unit.symbol}")
        return self.base_value / unit.scale


def format_schematic_value(value: str | Quantity) -> str:
    """Format a code-owned value for a KiCad schematic property."""
    if isinstance(value, str):
        return value
    marker = _SCHEMATIC_PREFIXES.get((value.dimension, value.display_scale))
    if marker is None:
        return str(value)
    number = _decimal_text(value.base_value / value.display_scale)
    if value.dimension == "Ω" and marker == "R":
        return _replace_decimal(number, marker, omit_leading_zero=True)
    if "." in number and abs(value.base_value / value.display_scale) >= 1 and marker:
        return _replace_decimal(number, marker)
    return f"{number}{marker}"


def _replace_decimal(number: str, marker: str, *, omit_leading_zero: bool = False) -> str:
    sign = ""
    unsigned = number
    if unsigned.startswith("-"):
        sign, unsigned = "-", unsigned[1:]
    whole, fraction = unsigned.split(".", 1) if "." in unsigned else (unsigned, "")
    if omit_leading_zero and whole == "0" and fraction:
        whole = ""
    return f"{sign}{whole}{marker}{fraction}"


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


ohm = Unit("Ω")
kohm = Unit("Ω", Decimal("1000"))
Mohm = Unit("Ω", Decimal("1000000"))
F = Unit("F")
uF = Unit("F", Decimal("0.000001"))
nF = Unit("F", Decimal("0.000000001"))
H = Unit("H")
mH = Unit("H", Decimal("0.001"))
uH = Unit("H", Decimal("0.000001"))
nH = Unit("H", Decimal("0.000000001"))
V = Unit("V")
