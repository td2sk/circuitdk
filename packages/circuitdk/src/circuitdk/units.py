from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Self


@dataclass(frozen=True, slots=True)
class Unit:
    symbol: str
    scale: Decimal = Decimal(1)

    def __rmul__(self, value: int | float | Decimal) -> Quantity:
        return Quantity(Decimal(str(value)) * self.scale, self.symbol)


@dataclass(frozen=True, slots=True)
class Quantity:
    base_value: Decimal
    dimension: str

    def __str__(self) -> str:
        scales = {
            "Ω": ((Decimal("1000000"), "MΩ"), (Decimal("1000"), "kΩ")),
            "F": ((Decimal("0.000001"), "µF"), (Decimal("0.000000001"), "nF")),
        }
        for scale, suffix in scales.get(self.dimension, ()):
            value = self.base_value / scale
            if value == value.to_integral_value() and abs(value) >= 1:
                return f"{value:g} {suffix}"
        return f"{self.base_value:g} {self.dimension}"

    def __mul__(self, factor: int | float | Decimal) -> Self:
        return type(self)(self.base_value * Decimal(str(factor)), self.dimension)


ohm = Unit("Ω")
kohm = Unit("Ω", Decimal("1000"))
F = Unit("F")
uF = Unit("F", Decimal("0.000001"))
nF = Unit("F", Decimal("0.000000001"))
V = Unit("V")
