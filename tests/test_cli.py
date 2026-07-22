from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import circuitdk.cli as cli_module
from circuitdk.project import DeployResult
from circuitdk.targets.kicad import ErcResult, ErcViolation
from circuitdk.targets.kicad.planner import Action, DeploymentPlan, FieldChange

app = cli_module.app


def test_version_reports_installed_package_version() -> None:
    result = CliRunner().invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == f"CircuitDK {cli_module.__version__}"


class _DeployProject:
    def __init__(self, result: DeployResult) -> None:
        self.result = result

    def deploy(self, *, backup: bool) -> DeployResult:
        assert backup
        return self.result


class _PlanProject:
    def __init__(self, plan: DeploymentPlan) -> None:
        self._plan = plan

    def plan(self) -> DeploymentPlan:
        return self._plan


def _deploy_result(erc: ErcResult | None) -> DeployResult:
    return DeployResult(DeploymentPlan(()), 0, 0, 0, 0, 0, None, erc)


def _violation(severity: str, violation_type: str, description: str) -> ErcViolation:
    return ErcViolation("/", severity, violation_type, description, ())


def test_help_exposes_initial_release_commands() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    for command in (
        "synth",
        "diff",
        "deploy",
        "test",
        "drift",
        "inspect",
        "adopt",
        "move",
        "lock",
    ):
        assert command in result.stdout


def test_deploy_distinguishes_applied_state_from_erc_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    erc = ErcResult(
        (
            _violation("error", "pin_not_connected", "Pin not connected"),
            _violation("warning", "lib_symbol_mismatch", "Symbol differs from library"),
        ),
        "10.0.1",
    )
    monkeypatch.setattr(cli_module, "load_project", lambda _: _DeployProject(_deploy_result(erc)))

    result = CliRunner().invoke(app, ["deploy", "--config", str(Path("test.toml"))])

    assert result.exit_code == 0
    assert "APPLY SUCCEEDED" in result.stdout
    assert "No managed changes were applied." in result.stdout
    assert "SCHEMATIC VALID" in result.stdout
    assert "MANUAL WIRING REQUIRED" in result.stdout
    assert "ERC WARNINGS" in result.stdout
    assert "Complete the wiring in KiCad" in result.stdout
    assert "ACTION REQUIRED — Deployment was applied" in result.stdout


def test_deploy_warning_does_not_fail_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    erc = ErcResult(
        (_violation("warning", "lib_symbol_mismatch", "Symbol differs from library"),),
        "10.0.1",
    )
    monkeypatch.setattr(cli_module, "load_project", lambda _: _DeployProject(_deploy_result(erc)))

    result = CliRunner().invoke(app, ["deploy"])

    assert result.exit_code == 0
    assert "ELECTRICAL VALIDATION PASSED WITH WARNINGS" in result.stdout
    assert "COMPLETE WITH WARNINGS" in result.stdout


def test_deploy_json_exposes_each_status_axis(monkeypatch: pytest.MonkeyPatch) -> None:
    erc = ErcResult(
        (_violation("error", "pin_not_connected", "Pin not connected"),),
        "10.0.1",
    )
    monkeypatch.setattr(cli_module, "load_project", lambda _: _DeployProject(_deploy_result(erc)))

    result = CliRunner().invoke(app, ["deploy", "--json"])
    payload = json.loads(result.stdout)

    assert result.exit_code == 0
    assert payload["apply_status"] == "succeeded"
    assert payload["reconciled"] is True
    assert payload["structural_validation"] == "passed"
    assert payload["electrical_validation"] == "failed"
    assert payload["manual_wiring_required"] is True
    assert payload["manual_wiring_issue_count"] == 1
    assert payload["electrical_error_count"] == 0
    assert payload["erc_error_count"] == 1
    assert payload["erc_warning_count"] == 0
    assert payload["ready"] is False


def test_deploy_reports_skipped_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli_module, "load_project", lambda _: _DeployProject(_deploy_result(None)))

    result = CliRunner().invoke(app, ["deploy"])

    assert result.exit_code == 0
    assert "STRUCTURAL VALIDATION SKIPPED" in result.stdout
    assert "ELECTRICAL VALIDATION SKIPPED" in result.stdout
    assert "VALIDATION SKIPPED — Deployment was applied" in result.stdout


def test_diff_uses_distinct_colors_and_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = DeploymentPlan(
        (
            Action("create", "/Blinky/New"),
            Action(
                "update",
                "/Blinky/Changed",
                (FieldChange("value", "10k", "1k"),),
            ),
            Action("delete", "/Blinky/Old"),
        )
    )
    monkeypatch.setattr(cli_module, "load_project", lambda _: _PlanProject(plan))

    result = CliRunner().invoke(app, ["diff"], color=True)

    assert result.exit_code == 2
    assert "\x1b[32m\x1b[1m+ /Blinky/New" in result.stdout
    assert "\x1b[33m\x1b[1m~ /Blinky/Changed" in result.stdout
    assert "\x1b[31m\x1b[1m- /Blinky/Old" in result.stdout
    assert "CHANGES FOUND — 1 create, 1 update, 1 delete." in result.stdout


def test_deploy_complete_has_green_final_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli_module,
        "load_project",
        lambda _: _DeployProject(_deploy_result(ErcResult((), "10.0.1"))),
    )

    result = CliRunner().invoke(app, ["deploy"], color=True)

    assert result.exit_code == 0
    assert "COMPLETE — Circuit is up to date and electrically valid." in result.stdout
    assert "\x1b[32m\x1b[1m✅ COMPLETE" in result.stdout


def test_deploy_electrical_error_is_distinct_from_apply_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    erc = ErcResult(
        (_violation("error", "pin_conflict", "Two outputs are connected"),),
        "10.0.1",
    )
    monkeypatch.setattr(cli_module, "load_project", lambda _: _DeployProject(_deploy_result(erc)))

    result = CliRunner().invoke(app, ["deploy"])

    assert result.exit_code == 2
    assert "APPLY SUCCEEDED" in result.stdout
    assert "ELECTRICAL VALIDATION FAILED" in result.stdout
    assert "INVALID — Deployment was applied" in result.stdout
