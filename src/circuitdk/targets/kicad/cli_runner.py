from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from ...ir import CircuitIR, NetIR, PinRef
from .document import KicadSchematic


class KicadCliError(RuntimeError):
    def __init__(self, command: tuple[str, ...], returncode: int, output: str) -> None:
        self.command = command
        self.returncode = returncode
        self.output = output
        super().__init__(f"kicad-cli exited with {returncode}: {output.strip()}")


@dataclass(frozen=True, slots=True)
class ErcItem:
    description: str
    uuid: str | None
    x: float | None
    y: float | None


@dataclass(frozen=True, slots=True)
class ErcViolation:
    sheet: str
    severity: str
    violation_type: str
    description: str
    items: tuple[ErcItem, ...]


@dataclass(frozen=True, slots=True)
class ErcResult:
    violations: tuple[ErcViolation, ...]
    kicad_version: str

    @property
    def errors(self) -> tuple[ErcViolation, ...]:
        return tuple(item for item in self.violations if item.severity == "error")

    @property
    def warnings(self) -> tuple[ErcViolation, ...]:
        return tuple(item for item in self.violations if item.severity == "warning")

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    @property
    def ok(self) -> bool:
        return not any(item.severity in {"error", "warning"} for item in self.violations)


class KicadCli:
    def __init__(self, executable: str | Path) -> None:
        self.executable = Path(executable)

    @classmethod
    def discover(cls, environment: dict[str, str] | None = None) -> KicadCli | None:
        env = dict(os.environ if environment is None else environment)
        explicit = env.get("CIRCUITDK_KICAD_CLI")
        if explicit and Path(explicit).exists():
            return cls(explicit)
        found = shutil.which("kicad-cli")
        if found:
            return cls(found)
        program_files = env.get("ProgramFiles") or env.get("PROGRAMFILES")
        if program_files:
            candidate = Path(program_files) / "KiCad" / "10.0" / "bin" / "kicad-cli.exe"
            if candidate.exists():
                return cls(candidate)
        return None

    def version(self) -> str:
        result = self._run("version")
        return result.stdout.strip()

    def export_netlist_xml(self, schematic: Path) -> str:
        with tempfile.TemporaryDirectory(prefix="circuitdk-netlist-") as directory:
            output = Path(directory) / "netlist.xml"
            self._run(
                "sch",
                "export",
                "netlist",
                "--format",
                "kicadxml",
                "--output",
                str(output),
                str(schematic),
            )
            return output.read_text(encoding="utf-8")

    def erc(self, schematic: Path) -> ErcResult:
        with tempfile.TemporaryDirectory(prefix="circuitdk-erc-") as directory:
            output = Path(directory) / "erc.json"
            self._run(
                "sch",
                "erc",
                "--format",
                "json",
                "--severity-all",
                "--output",
                str(output),
                str(schematic),
            )
            return parse_erc_json(output.read_text(encoding="utf-8"))

    def validate(self, source: str, sibling_of: Path) -> ErcResult:
        temporary = sibling_of.with_name(f"{sibling_of.stem}.circuitdk-validate.kicad_sch")
        try:
            temporary.write_text(source, encoding="utf-8", newline="")
            self.export_netlist_xml(temporary)
            return self.erc(temporary)
        finally:
            temporary.unlink(missing_ok=True)

    def _run(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        command = (str(self.executable), *arguments)
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if completed.returncode != 0:
            output = "\n".join(item for item in (completed.stdout, completed.stderr) if item)
            raise KicadCliError(command, completed.returncode, output)
        return completed


def actual_circuit_from_xml(
    desired: CircuitIR, schematic: KicadSchematic, xml_source: str
) -> CircuitIR:
    root = ET.fromstring(xml_source)
    reference_to_id = {
        symbol.reference: circuit_id
        for circuit_id, symbol in schematic.managed_symbols.items()
        if symbol.reference is not None
    }
    components_node = root.find("components")
    if components_node is not None:
        for component in components_node.findall("comp"):
            reference = component.get("ref")
            circuit_id = _component_circuit_id(component)
            if reference and circuit_id:
                # XML includes components from hierarchical sheets, so this also maps
                # managed child-sheet symbols that are not nodes in the root file CST.
                reference_to_id[reference] = circuit_id
    desired_parts = {part.id: part for part in desired.parts}
    nets: list[NetIR] = []
    nets_node = root.find("nets")
    if nets_node is not None:
        for index, net_node in enumerate(nets_node.findall("net")):
            pins: list[PinRef] = []
            for node in net_node.findall("node"):
                reference = node.get("ref")
                number = node.get("pin")
                circuit_id = reference_to_id.get(reference)
                if circuit_id is None or number is None or circuit_id not in desired_parts:
                    continue
                try:
                    pin = desired_parts[circuit_id].pin(number)
                except KeyError:
                    pin = PinRef(circuit_id, number, node.get("pinfunction") or number)
                pins.append(pin)
            if pins:
                name = net_node.get("name") or f"actual-{index}"
                nets.append(NetIR(name, tuple(sorted(set(pins)))))
    return CircuitIR(desired.id, desired.parts, tuple(nets), desired.intents)


def _component_circuit_id(component: ET.Element) -> str | None:
    for prop in component.findall("property"):
        if prop.get("name") == "CircuitDK:ID":
            return prop.get("value")
    fields = component.find("fields")
    if fields is not None:
        for field in fields.findall("field"):
            if field.get("name") == "CircuitDK:ID":
                return field.text
    return None


def parse_erc_json(source: str) -> ErcResult:
    data = json.loads(source)
    violations: list[ErcViolation] = []
    for sheet in data.get("sheets", []):
        path = str(sheet.get("path", "/"))
        for violation in sheet.get("violations", []):
            items: list[ErcItem] = []
            for item in violation.get("items", []):
                position = item.get("pos") or {}
                items.append(
                    ErcItem(
                        str(item.get("description", "")),
                        str(item["uuid"]) if item.get("uuid") is not None else None,
                        float(position["x"]) if position.get("x") is not None else None,
                        float(position["y"]) if position.get("y") is not None else None,
                    )
                )
            violations.append(
                ErcViolation(
                    path,
                    str(violation.get("severity", "unknown")),
                    str(violation.get("type", "unknown")),
                    str(violation.get("description", "")),
                    tuple(items),
                )
            )
    return ErcResult(tuple(violations), str(data.get("kicad_version", "unknown")))
