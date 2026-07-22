from __future__ import annotations

from dataclasses import dataclass

from .ir import CircuitIR, IntentIR


@dataclass(frozen=True, slots=True)
class IntentIssue:
    intent_kind: str
    subject: str
    message: str


@dataclass(frozen=True, slots=True)
class IntentValidationResult:
    issues: tuple[IntentIssue, ...]

    @property
    def ok(self) -> bool:
        return not self.issues


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


def validate_intents(circuit: CircuitIR) -> IntentValidationResult:
    issues: list[IntentIssue] = []
    net_by_pin = {pin.key: net for net in circuit.nets for pin in net.pins}
    parts = {part.id: part for part in circuit.parts}
    nets = {net.id: net for net in circuit.nets}
    for intent in circuit.intents:
        params = dict(intent.parameters)
        if intent.kind == "default_logic_level":
            resistor_id = params.get("resistor")
            level = params.get("level")
            if resistor_id not in parts:
                issues.append(_issue(intent, "pull resistor is missing"))
                continue
            resistor_nets = {
                net_by_pin[pin.key].id for pin in parts[resistor_id].pins if pin.key in net_by_pin
            }
            signal_net = net_by_pin.get(intent.subject)
            required_kind = "ground" if level == "low" else "power"
            if signal_net is None or signal_net.id not in resistor_nets:
                issues.append(
                    _issue(intent, "signal is not connected through the declared resistor")
                )
            if not any(nets[net_id].kind == required_kind for net_id in resistor_nets):
                issues.append(_issue(intent, f"resistor is not connected to a {required_kind} net"))
        elif intent.kind == "decoupling":
            capacitor_id = params.get("capacitor")
            ground_id = params.get("ground")
            if capacitor_id not in parts:
                issues.append(_issue(intent, "decoupling capacitor is missing"))
                continue
            capacitor_nets = {
                net_by_pin[pin.key].id for pin in parts[capacitor_id].pins if pin.key in net_by_pin
            }
            power_net = net_by_pin.get(intent.subject)
            if power_net is None or power_net.id not in capacitor_nets:
                issues.append(_issue(intent, "capacitor is not connected to the power pin"))
            if ground_id not in capacitor_nets:
                issues.append(_issue(intent, "capacitor is not connected to the declared ground"))
        elif intent.kind == "current_limited_led":
            resistor_id = params.get("resistor")
            if resistor_id not in parts or intent.subject not in parts:
                issues.append(_issue(intent, "LED or current-limiting resistor is missing"))
                continue
            led_net_ids = {
                net_by_pin[pin.key].id
                for pin in parts[intent.subject].pins
                if pin.key in net_by_pin
            }
            resistor_net_ids = {
                net_by_pin[pin.key].id for pin in parts[resistor_id].pins if pin.key in net_by_pin
            }
            if not led_net_ids & resistor_net_ids:
                issues.append(_issue(intent, "LED is not connected through its declared resistor"))
        elif intent.kind == "voltage_divider":
            upper_id = params.get("upper")
            lower_id = params.get("lower")
            output = nets.get(intent.subject)
            if upper_id not in parts or lower_id not in parts or output is None:
                issues.append(_issue(intent, "divider parts or output net are missing"))
                continue
            output_parts = {pin.part_id for pin in output.pins}
            if upper_id not in output_parts or lower_id not in output_parts:
                issues.append(
                    _issue(intent, "divider output is not between upper and lower resistors")
                )
    return IntentValidationResult(tuple(issues))


def _issue(intent: IntentIR, message: str) -> IntentIssue:
    return IntentIssue(intent.kind, intent.subject, message)
