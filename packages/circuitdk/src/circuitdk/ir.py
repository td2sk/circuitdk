from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .units import Quantity, format_schematic_value


@dataclass(frozen=True, slots=True, order=True)
class PinRef:
    part_id: str
    number: str
    name: str

    @property
    def key(self) -> str:
        return f"{self.part_id}:{self.number}"


@dataclass(frozen=True, slots=True)
class PartIR:
    id: str
    symbol: str
    value: str | Quantity
    footprint: str | None
    pins: tuple[PinRef, ...]
    in_bom: bool = True
    on_board: bool = True
    dnp: bool = False
    resolve_pins: bool = False

    def pin(self, name_or_number: str) -> PinRef:
        matches = tuple(
            pin for pin in self.pins if pin.name == name_or_number or pin.number == name_or_number
        )
        if not matches:
            raise KeyError(f"pin {name_or_number!r} does not exist on {self.id}")
        if len(matches) > 1:
            raise KeyError(f"pin {name_or_number!r} is ambiguous on {self.id}")
        return matches[0]


@dataclass(frozen=True, slots=True)
class NetIR:
    id: str
    pins: tuple[PinRef, ...]
    kind: str = "signal"
    voltage: str | None = None


@dataclass(frozen=True, slots=True)
class IntentIR:
    kind: str
    subject: str
    parameters: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class CircuitIR:
    id: str
    parts: tuple[PartIR, ...]
    nets: tuple[NetIR, ...]
    intents: tuple[IntentIR, ...] = ()
    no_connects: tuple[PinRef, ...] = ()
    schema_version: int = 1

    def part(self, circuit_id: str) -> PartIR:
        return next(part for part in self.parts if part.id == circuit_id)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        for part, serialized in zip(self.parts, result["parts"], strict=True):
            serialized["value"] = format_schematic_value(part.value)
        return result

    def managed_projection(self) -> dict[str, dict[str, object]]:
        return {
            part.id: {
                "symbol": part.symbol,
                "value": format_schematic_value(part.value),
                "footprint": part.footprint,
                "in_bom": part.in_bom,
                "on_board": part.on_board,
                "dnp": part.dnp,
            }
            for part in self.parts
        }
