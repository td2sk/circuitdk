from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def schematic_source() -> str:
    return """(kicad_sch
  (version 20250114)
  (generator \"eeschema\")
  (uuid 00000000-0000-4000-8000-000000000000)
  (paper \"A4\")
  (lib_symbols)
  (symbol
    (lib_id \"Device:R\")
    (at 100 100 0)
    (unit 1)
    (exclude_from_sim no)
    (in_bom yes)
    (on_board yes)
    (dnp no)
    (uuid 11111111-1111-4111-8111-111111111111)
    (property \"Reference\" \"R1\" (at 102 100 0))
    (property \"Value\" \"10 k\" (at 100 100 0))
    (property \"Footprint\" \"Resistor_SMD:R_0603_1608Metric\" (at 100 100 0) hide)
    (property \"CircuitDK:ID\" \"/Blinky/Resistor\" (at 100 100 0) hide)
  )
)\n"""


@pytest.fixture
def schematic_path(tmp_path: Path, schematic_source: str) -> Path:
    path = tmp_path / "blinky.kicad_sch"
    path.write_text(schematic_source, encoding="utf-8", newline="")
    return path
