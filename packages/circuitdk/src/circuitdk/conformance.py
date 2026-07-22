from __future__ import annotations

from dataclasses import dataclass

from .ir import CircuitIR


@dataclass(frozen=True, slots=True)
class ConnectivityIssue:
    kind: str
    pins: tuple[str, ...]
    message: str


@dataclass(frozen=True, slots=True)
class ConformanceResult:
    issues: tuple[ConnectivityIssue, ...]

    @property
    def ok(self) -> bool:
        return not self.issues


def compare_connectivity(desired: CircuitIR, actual: CircuitIR) -> ConformanceResult:
    """Compare connectivity as pin partitions, ignoring net names and wire geometry."""

    desired_index = _partition_index(desired)
    actual_index = _partition_index(actual)
    issues: list[ConnectivityIssue] = []
    all_pins = sorted(set(desired_index) | set(actual_index))

    seen_missing: set[tuple[str, ...]] = set()
    seen_extra: set[tuple[str, ...]] = set()
    for pin in all_pins:
        expected = desired_index.get(pin, frozenset({pin}))
        observed = actual_index.get(pin, frozenset({pin}))
        missing = tuple(sorted(expected - observed))
        extra = tuple(sorted(observed - expected))
        if missing:
            key = tuple(sorted({pin, *missing}))
            if key not in seen_missing:
                seen_missing.add(key)
                issues.append(
                    ConnectivityIssue(
                        "missing_connection",
                        key,
                        f"{pin} is not connected to {', '.join(missing)}",
                    )
                )
        if extra:
            key = tuple(sorted({pin, *extra}))
            if key not in seen_extra:
                seen_extra.add(key)
                issues.append(
                    ConnectivityIssue(
                        "extra_connection",
                        key,
                        f"{pin} is unexpectedly connected to {', '.join(extra)}",
                    )
                )
    return ConformanceResult(tuple(issues))


def _partition_index(circuit: CircuitIR) -> dict[str, frozenset[str]]:
    result: dict[str, frozenset[str]] = {}
    for net in circuit.nets:
        members = frozenset(pin.key for pin in net.pins)
        for member in members:
            result[member] = members
    return result
