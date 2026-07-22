from __future__ import annotations

from circuitdk.conformance import compare_connectivity
from circuitdk.ir import CircuitIR, NetIR, PinRef


def _ir(*nets: tuple[str, ...]) -> CircuitIR:
    return CircuitIR(
        "/C",
        (),
        tuple(
            NetIR(
                f"N{index}",
                tuple(PinRef(f"/{pin[0]}", pin[1:], pin[1:]) for pin in members),
            )
            for index, members in enumerate(nets)
        ),
    )


def test_reports_missing_and_extra_connections_without_net_name_dependency() -> None:
    desired = _ir(("A1", "B1"), ("C1", "D1"))
    actual = _ir(("A1", "B1", "C1"), ("D1",))

    result = compare_connectivity(desired, actual)

    assert not result.ok
    assert {issue.kind for issue in result.issues} == {"missing_connection", "extra_connection"}


def test_equivalent_partitions_pass_even_with_different_net_names() -> None:
    assert compare_connectivity(_ir(("A1", "B1")), _ir(("A1", "B1"))).ok
