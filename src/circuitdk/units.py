from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Self, overload

_ENGINEERING_PREFIXES: tuple[tuple[Decimal, str, str], ...] = (
    (Decimal("1e12"), "T", "T"),
    (Decimal("1e9"), "G", "G"),
    (Decimal("1e6"), "M", "M"),
    (Decimal("1e3"), "k", "k"),
    (Decimal("1"), "", ""),
    (Decimal("1e-3"), "m", "m"),
    (Decimal("1e-6"), "u", "µ"),
    (Decimal("1e-9"), "n", "n"),
    (Decimal("1e-12"), "p", "p"),
    (Decimal("1e-15"), "f", "f"),
)

_PREFIX_BY_SCALE = {
    scale: (schematic_prefix, human_prefix)
    for scale, schematic_prefix, human_prefix in _ENGINEERING_PREFIXES
}
_ENGINEERING_SCALES = tuple(scale for scale, _, _ in _ENGINEERING_PREFIXES)


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
        prefix = _PREFIX_BY_SCALE.get(scale)
        if prefix is None:
            return f"{_decimal_text(self.base_value)} {self.dimension}"
        return f"{_decimal_text(self.base_value / scale)} {prefix[1]}{self.dimension}"

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
        magnitude = abs(self.base_value)
        if magnitude == 0:
            return Decimal(1)
        for scale in _ENGINEERING_SCALES:
            displayed = magnitude / scale
            if Decimal(1) <= displayed < Decimal(1000):
                return scale
        return (
            _ENGINEERING_SCALES[-1]
            if magnitude < _ENGINEERING_SCALES[-1]
            else _ENGINEERING_SCALES[0]
        )

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
    prefix = _PREFIX_BY_SCALE.get(scale)
    if prefix is None:
        return str(value)
    number = _decimal_text(value.base_value / scale)
    schematic_prefix = prefix[0]
    if value.dimension == "Ω":
        marker = schematic_prefix or "R"
        if scale == Decimal(1):
            return _replace_decimal(number, marker, omit_leading_zero=True)
        if "." in number and abs(value.base_value / scale) >= 1:
            return _replace_decimal(number, marker)
        return f"{number}{marker}"
    if value.dimension in {"F", "H"}:
        if "." in number and abs(value.base_value / scale) >= 1 and schematic_prefix:
            return _replace_decimal(number, schematic_prefix)
        return f"{number}{schematic_prefix}"
    if value.dimension == "Hz":
        return f"{number}{schematic_prefix}Hz"
    return str(value)


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
mF = Unit("F", Decimal("0.001"))
uF = Unit("F", Decimal("0.000001"))
nF = Unit("F", Decimal("0.000000001"))
pF = Unit("F", Decimal("0.000000000001"))
fF = Unit("F", Decimal("0.000000000000001"))

H = Unit("H")
mH = Unit("H", Decimal("0.001"))
uH = Unit("H", Decimal("0.000001"))
nH = Unit("H", Decimal("0.000000001"))
pH = Unit("H", Decimal("0.000000000001"))

V = Unit("V")
kV = Unit("V", Decimal("1000"))
mV = Unit("V", Decimal("0.001"))
uV = Unit("V", Decimal("0.000001"))
nV = Unit("V", Decimal("0.000000001"))

A = Unit("A")
kA = Unit("A", Decimal("1000"))
mA = Unit("A", Decimal("0.001"))
uA = Unit("A", Decimal("0.000001"))
nA = Unit("A", Decimal("0.000000001"))
pA = Unit("A", Decimal("0.000000000001"))
fA = Unit("A", Decimal("0.000000000000001"))

Hz = Unit("Hz")
kHz = Unit("Hz", Decimal("1000"))
MHz = Unit("Hz", Decimal("1000000"))
GHz = Unit("Hz", Decimal("1000000000"))
THz = Unit("Hz", Decimal("1000000000000"))
