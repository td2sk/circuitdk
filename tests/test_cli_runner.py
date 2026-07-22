from __future__ import annotations

from circuitdk.conformance import compare_connectivity
from circuitdk.ir import CircuitIR, NetIR, PartIR, PinRef
from circuitdk.targets.kicad import KicadSchematic, actual_circuit_from_xml, parse_erc_json


def test_xml_netlist_maps_kicad_references_back_to_logical_ids(
    schematic_source: str,
) -> None:
    pin1 = PinRef("/Blinky/Resistor", "1", "1")
    pin2 = PinRef("/Blinky/Resistor", "2", "2")
    part = PartIR("/Blinky/Resistor", "Device:R", "10 k", None, (pin1, pin2))
    desired = CircuitIR("/Blinky", (part,), (NetIR("GND", (pin1, pin2)),))
    xml = """<?xml version="1.0"?>
<export><nets><net code="1" name="GND">
  <node ref="R1" pin="1" pinfunction="1"/>
  <node ref="R1" pin="2" pinfunction="2"/>
</net></nets></export>"""

    actual = actual_circuit_from_xml(desired, KicadSchematic.from_text(schematic_source), xml)

    assert compare_connectivity(desired, actual).ok
    assert actual.nets[0].pins == (pin1, pin2)


def test_erc_json_is_parsed_as_structured_diagnostics() -> None:
    result = parse_erc_json(
        """{
  "kicad_version": "10.0.1",
  "sheets": [{
    "path": "/",
    "violations": [{
      "description": "Pin not connected",
      "severity": "error",
      "type": "pin_not_connected",
      "items": [{"description": "R1 pin 1", "uuid": "abc", "pos": {"x": 1, "y": 2}}]
    }]
  }]
}"""
    )

    assert not result.ok
    assert result.kicad_version == "10.0.1"
    assert result.violations[0].violation_type == "pin_not_connected"
    assert result.violations[0].items[0].x == 1.0


def test_xml_component_property_maps_hierarchical_managed_symbol(
    schematic_source: str,
) -> None:
    pin = PinRef("/Root/Child/U", "1", "IN")
    part = PartIR("/Root/Child/U", "Test:U", "U", None, (pin,))
    desired = CircuitIR("/Root", (part,), (NetIR("SIGNAL", (pin,)),))
    xml = """<export>
  <components><comp ref="U2">
    <property name="CircuitDK:ID" value="/Root/Child/U"/>
    <sheetpath names="/Child" tstamps="/root/child"/>
  </comp></components>
  <nets><net code="1" name="SIGNAL"><node ref="U2" pin="1"/></net></nets>
</export>"""

    actual = actual_circuit_from_xml(desired, KicadSchematic.from_text(schematic_source), xml)

    assert actual.nets[0].pins == (pin,)
