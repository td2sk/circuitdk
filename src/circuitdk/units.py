from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Self, overload

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

_AUTO_DISPLAY_SCALES: dict[str, tuple[Decimal, ...]] = {
    "Ω": (Decimal("1000000"), Decimal("1000"), Decimal("1")),
    "F": (Decimal("1"), Decimal("0.000001"), Decimal("0.000000001")),
    "H": (
        Decimal("1"),
        Decimal("0.001"),
        Decimal("0.000001"),
        Decimal("0.000000001"),
    ),
    "V": (Decimal("1"),),
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
    display_scale: Decimal | None = field(default=Decimal(1), compare=False, repr=False)

    def __str__(self) -> str:
        scale = self._effective_display_scale()
        suffix = _HUMAN_SUFFIXES.get((self.dimension, scale), self.dimension)
        return f"{_decimal_text(self.base_value / scale)} {suffix}"

    def __add__(self, other: Quantity) -> Self:
        self._require_same_dimension(other)
        return type(self)(
            self.base_value + other.base_value,
            self.dimension,
            display_scale=self._combined_display_scale(other),
        )

    def __sub__(self, other: Quantity) -> Self:
        self._require_same_dimension(other)
        return type(self)(
            self.base_value - other.base_value,
            self.dimension,
            display_scale=self._combined_display_scale(other),
        )

    def __mul__(self, factor: int | float | Decimal) -> Self:
        return type(self)(
            self.base_value * Decimal(str(factor)),
            self.dimension,
            display_scale=self.display_scale,
        )

    def __rmul__(self, factor: int | float | Decimal) -> Self:
        return self * factor

    @overload
    def __truediv__(self, divisor: Quantity) -> Decimal: ...

    @overload
    def __truediv__(self, divisor: int | float | Decimal) -> Self: ...

    def __truediv__(self, divisor: Quantity | int | float | Decimal) -> Self | Decimal:
        if isinstance(divisor, Quantity):
            self._require_same_dimension(divisor)
            if divisor.base_value == 0:
                raise ZeroDivisionError("cannot divide by a zero quantity")
            return self.base_value / divisor.base_value
        scalar = Decimal(str(divisor))
        if scalar == 0:
            raise ZeroDivisionError("cannot divide a quantity by zero")
        return type(self)(
            self.base_value / scalar,
            self.dimension,
            display_scale=self.display_scale,
        )

    def __pos__(self) -> Self:
        return self

    def __neg__(self) -> Self:
        return type(self)(
            -self.base_value,
            self.dimension,
            display_scale=self.display_scale,
        )

    def __abs__(self) -> Self:
        return type(self)(
            abs(self.base_value),
            self.dimension,
            display_scale=self.display_scale,
        )

    def __lt__(self, other: Quantity) -> bool:
        self._require_same_dimension(other)
        return self.base_value < other.base_value

    def __le__(self, other: Quantity) -> bool:
        self._require_same_dimension(other)
        return self.base_value <= other.base_value

    def __gt__(self, other: Quantity) -> bool:
        self._require_same_dimension(other)
        return self.base_value > other.base_value

    def __ge__(self, other: Quantity) -> bool:
        self._require_same_dimension(other)
        return self.base_value >= other.base_value

    def to(self, unit: Unit) -> Self:
        """Return an equivalent quantity expressed using ``unit``."""
        self._require_unit_dimension(unit)
        return type(self)(
            self.base_value,
            self.dimension,
            display_scale=unit.scale,
        )

    def in_unit(self, unit: Unit) -> Decimal:
        """Return the numeric value expressed in ``unit``."""
        self._require_unit_dimension(unit)
        return self.base_value / unit.scale

    def _effective_display_scale(self) -> Decimal:
        if self.display_scale is not None:
            return self.display_scale
        scales = _AUTO_DISPLAY_SCALES.get(self.dimension, (Decimal(1),))
        magnitude = abs(self.base_value)
        if magnitude == 0:
            return Decimal(1)
        for scale in scales:
            displayed = magnitude / scale
            if Decimal(1) <= displayed < Decimal(1000):
                return scale
        return scales[-1] if magnitude < scales[-1] else scales[0]

    def _combined_display_scale(self, other: Quantity) -> Decimal | None:
        if self.display_scale == other.display_scale:
            return self.display_scale
        return None

    def _require_same_dimension(self, other: Quantity) -> None:
        if not isinstance(other, Quantity):
            raise TypeError(f"expected Quantity, got {type(other).__name__}")
        if self.dimension != other.dimension:
            raise ValueError(f"incompatible dimensions: {self.dimension} and {other.dimension}")

    def _require_unit_dimension(self, unit: Unit) -> None:
        if unit.symbol != self.dimension:
            raise ValueError(f"cannot convert {self.dimension} to {unit.symbol}")


def format_schematic_value(value: str | Quantity) -> str:
    """Format a code-owned value for a KiCad schematic property."""
    if isinstance(value, str):
        return value
    scale = value._effective_display_scale()
    marker = _SCHEMATIC_PREFIXES.get((value.dimension, scale))
    if marker is None:
        return str(value)
    number = _decimal_text(value.base_value / scale)
    if value.dimension == "Ω" and marker == "R":
        return _replace_decimal(number, marker, omit_leading_zero=True)
    if "." in number and abs(value.base_value / scale) >= 1 and marker:
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
