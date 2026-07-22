from __future__ import annotations

from pathlib import Path

import pytest

import circuitdk.targets.kicad.libraries as library_module
from circuitdk.targets.kicad import (
    KicadFootprintResolver,
    KicadSymbolResolver,
    LibraryTable,
)
from lossless_sexpr import parse


def test_project_symbol_table_resolves_pins_and_hash(tmp_path: Path) -> None:
    library = tmp_path / "Test.kicad_sym"
    library.write_text(
        """(kicad_symbol_lib
  (version 20250114)
  (generator "circuitdk-test")
  (symbol "Chip"
    (property "Reference" "U" (at 0 0 0))
    (symbol "Chip_1_1"
      (pin input line (at -2.54 0 0) (length 2.54)
        (name "IN" (effects (font (size 1.27 1.27))))
        (number "1" (effects (font (size 1.27 1.27)))))
      (pin output line (at 2.54 0 180) (length 2.54)
        (name "OUT" (effects (font (size 1.27 1.27))))
        (number "2" (effects (font (size 1.27 1.27)))))
    )
  )
)\n""",
        encoding="utf-8",
    )
    (tmp_path / "sym-lib-table").write_text(
        '(sym_lib_table (version 7) (lib (name "Test") (type "KiCad") '
        '(uri "${KIPRJMOD}/Test.kicad_sym") (options "") (descr "")))\n',
        encoding="utf-8",
    )

    definition = KicadSymbolResolver.for_project(tmp_path, environment={}).resolve("Test:Chip")

    assert definition.reference_prefix == "U"
    assert definition.pin("IN").number == "1"
    assert definition.pin("2").electrical_type == "output"
    assert definition.source_sha256
    assert '(symbol "Test:Chip"' in definition.source_text


def test_nested_table_and_footprint_pads(tmp_path: Path) -> None:
    footprints = tmp_path / "Test.pretty"
    footprints.mkdir()
    (footprints / "TwoPad.kicad_mod").write_text(
        '(footprint "TwoPad" (version 20250114) (generator "test") '
        '(layer "F.Cu") (attr smd) '
        '(pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu")) '
        '(pad "2" smd rect (at 2 0) (size 1 1) (layers "F.Cu")))',
        encoding="utf-8",
    )
    nested = tmp_path / "nested-fp-table"
    nested.write_text(
        f'(fp_lib_table (version 7) (lib (name "Test") (type "KiCad") '
        f'(uri "{footprints.as_posix()}") (options "") (descr "")))',
        encoding="utf-8",
    )
    root = tmp_path / "fp-lib-table"
    root.write_text(
        f'(fp_lib_table (version 7) (lib (name "Nested") (type "Table") '
        f'(uri "{nested.as_posix()}") (options "") (descr "")))',
        encoding="utf-8",
    )

    footprint = KicadFootprintResolver(LibraryTable.load((root,), {})).resolve("Test:TwoPad")

    assert footprint.pads == ("1", "2")
    assert footprint.mount_type == "smd"


def test_symbols_in_same_library_file_are_parsed_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    library = tmp_path / "Test.kicad_sym"
    library.write_text(
        """(kicad_symbol_lib
  (version 20250114)
  (generator "circuitdk-test")
  (symbol "First" (property "Reference" "U" (at 0 0 0)))
  (symbol "Second" (property "Reference" "U" (at 0 0 0)))
)
""",
        encoding="utf-8",
    )
    table_path = tmp_path / "sym-lib-table"
    table_path.write_text(
        '(sym_lib_table (version 7) (lib (name "Test") (type "KiCad") '
        '(uri "${KIPRJMOD}/Test.kicad_sym") (options "") (descr "")))\n',
        encoding="utf-8",
    )
    resolver = KicadSymbolResolver.for_project(tmp_path, environment={})
    original_parse = library_module.parse
    parse_count = 0

    def counting_parse(source: str):  # type: ignore[no-untyped-def]
        nonlocal parse_count
        parse_count += 1
        return original_parse(source)

    monkeypatch.setattr(library_module, "parse", counting_parse)

    assert resolver.resolve("Test:First").reference_prefix == "U"
    assert resolver.resolve("Test:Second").reference_prefix == "U"
    assert parse_count == 1


def test_inherited_symbol_is_flattened_for_schematic(tmp_path: Path) -> None:
    library = tmp_path / "Test.kicad_sym"
    library.write_text(
        """(kicad_symbol_lib
  (version 20250114)
  (generator "circuitdk-test")
  (symbol "Base"
    (exclude_from_sim no)
    (in_bom yes)
    (on_board yes)
    (property "Reference" "U" (at 0 0 0))
    (property "Value" "Base" (at 0 0 0))
    (symbol "Base_0_1"
      (rectangle (start -2.54 -2.54) (end 2.54 2.54)
        (stroke (width 0.254) (type default)) (fill (type background))))
    (symbol "Base_1_1"
      (pin input line (at -5.08 0 0) (length 2.54)
        (name "IN" (effects (font (size 1.27 1.27))))
        (number "1" (effects (font (size 1.27 1.27)))))))
  (symbol "Derived"
    (extends "Base")
    (property "Reference" "U" (at 0 0 0))
    (property "Value" "Derived" (at 0 0 0))
    (property "Description" "Derived part" (at 0 0 0) (hide yes)))
)
""",
        encoding="utf-8",
    )
    (tmp_path / "sym-lib-table").write_text(
        '(sym_lib_table (version 7) (lib (name "Test") (type "KiCad") '
        '(uri "${KIPRJMOD}/Test.kicad_sym") (options "") (descr "")))\n',
        encoding="utf-8",
    )
    resolver = KicadSymbolResolver.for_project(tmp_path, environment={})

    embedded = resolver.materialize_for_schematic("Test:Derived")
    node = parse(embedded.source_text).lists("symbol")[0]
    properties: dict[str, str] = {}
    for prop in node.child_lists("property"):
        name_atom = prop.atom(1)
        value_atom = prop.atom(2)
        if name_atom is not None and value_atom is not None:
            properties[name_atom.value] = value_atom.value
    unit_names: list[str] = []
    for unit in node.child_lists("symbol"):
        unit_name = unit.atom(1)
        if unit_name is not None:
            unit_names.append(unit_name.value)
    symbol_name = node.atom(1)
    body = node.first_list("symbol")

    assert symbol_name is not None and symbol_name.value == "Test:Derived"
    assert node.first_list("extends") is None
    assert properties == {
        "Reference": "U",
        "Value": "Derived",
        "Description": "Derived part",
    }
    assert unit_names == ["Derived_0_1", "Derived_1_1"]
    assert body is not None and body.first_list("rectangle") is not None
    assert len(tuple(node.walk("pin"))) == 1
