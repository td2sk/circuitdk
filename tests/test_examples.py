from __future__ import annotations

import runpy
import shutil
from pathlib import Path

from circuitdk import KicadProject
from circuitdk.targets.kicad import KicadSchematic


def test_blinky_example_bootstraps_test_schematic(tmp_path: Path) -> None:
    source = Path(__file__).parents[1] / "examples" / "blinky" / "circuit.py"
    example = tmp_path / "circuit.py"
    shutil.copy2(source, example)

    namespace = runpy.run_path(str(example), run_name="circuitdk_blinky_example")

    project = namespace["project"]
    assert isinstance(project, KicadProject)
    assert project.schematic == tmp_path / "hardware" / "blinky.kicad_sch"
    assert KicadSchematic.load(project.schematic).symbols == ()
