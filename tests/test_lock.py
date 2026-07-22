from __future__ import annotations

from pathlib import Path

from circuitdk.lock import CircuitLock, LockedLibrary


def test_lock_round_trip_and_difference_detection(tmp_path: Path) -> None:
    path = tmp_path / "circuitdk.lock.json"
    initial = CircuitLock((LockedLibrary("symbol", "Device:R", "Device.kicad_sym", "aaa"),))
    changed = CircuitLock((LockedLibrary("symbol", "Device:R", "Device.kicad_sym", "bbb"),))

    initial.write_atomic(path)

    loaded = CircuitLock.load(path)
    assert loaded == initial
    assert initial.differences(changed) == ("changed symbol library: Device:R",)
