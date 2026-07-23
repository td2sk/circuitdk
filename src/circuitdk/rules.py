from __future__ import annotations

from dataclasses import dataclass

from .ir import CircuitIR


@dataclass(frozen=True, slots=True)
class PinCoverageResult:
    unspecified: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.unspecified


def validate_pin_coverage(circuit: CircuitIR) -> PinCoverageResult:
    connected = {pin.key for net in circuit.nets for pin in net.pins}
    no_connects = {pin.key for pin in circuit.no_connects}
    declared = {pin.key for part in circuit.parts for pin in part.pins}
    return PinCoverageResult(tuple(sorted(declared - connected - no_connects)))
