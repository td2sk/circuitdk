"""Public CircuitDK API."""

from .constructs import Circuit, Construct, Net, Part, Pin
from .ir import CircuitIR, IntentIR, NetIR, PartIR, PinRef
from .patterns import (
    Capacitor,
    DecouplingCapacitor,
    Interface,
    LedIndicator,
    Resistor,
    SpiInterface,
    VoltageDivider,
    pull_down,
    pull_up,
)
from .project import KicadProject
from .rules import (
    IntentIssue,
    IntentValidationResult,
    PinCoverageResult,
    validate_intents,
    validate_pin_coverage,
)
from .units import F, Quantity, Unit, V, kohm, nF, ohm, uF
from .version import __version__

__all__ = [
    "Capacitor",
    "Circuit",
    "CircuitIR",
    "Construct",
    "DecouplingCapacitor",
    "F",
    "IntentIR",
    "IntentIssue",
    "IntentValidationResult",
    "Interface",
    "KicadProject",
    "LedIndicator",
    "Net",
    "NetIR",
    "Part",
    "PartIR",
    "Pin",
    "PinCoverageResult",
    "PinRef",
    "Quantity",
    "Resistor",
    "SpiInterface",
    "Unit",
    "V",
    "VoltageDivider",
    "__version__",
    "kohm",
    "nF",
    "ohm",
    "pull_down",
    "pull_up",
    "uF",
    "validate_intents",
    "validate_pin_coverage",
]
