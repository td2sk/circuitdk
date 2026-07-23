from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Any

import typer

from .config import load_project
from .version import __version__

app = typer.Typer(
    no_args_is_help=True,
    invoke_without_command=True,
    help="Code-first circuit design for KiCad.",
)
logger = logging.getLogger("circuitdk")

ConfigOption = Annotated[
    Path,
    typer.Option("--config", "-c", help="Path to circuitdk.toml."),
]
JsonOption = Annotated[
    bool,
    typer.Option("--json", help="Emit machine-readable JSON."),
]

GREEN = typer.colors.GREEN
YELLOW = typer.colors.YELLOW
RED = typer.colors.RED
CYAN = typer.colors.CYAN


def _status(text: str, *, color: str) -> None:
    typer.secho(text, fg=color, bold=True)


def _erc_groups(result):  # type: ignore[no-untyped-def]
    if result.erc is None:
        return (), (), ()
    wiring = tuple(
        violation
        for violation in result.erc.errors
        if violation.violation_type == "pin_not_connected"
    )
    electrical = tuple(
        violation
        for violation in result.erc.errors
        if violation.violation_type != "pin_not_connected"
    )
    return wiring, electrical, result.erc.warnings


def _project(config: Path):  # type: ignore[no-untyped-def]
    try:
        return load_project(config)
    except Exception as error:
        logger.debug("project loading failed", exc_info=True)
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(1) from error


def _emit(payload: Any, *, as_json: bool) -> None:
    if as_json:
        typer.echo(json.dumps(payload, indent=2, sort_keys=True, default=str))


@app.callback()
def main(
    verbose: Annotated[int, typer.Option("--verbose", "-v", count=True)] = 0,
    show_version: Annotated[
        bool,
        typer.Option("--version", help="Show the installed version and exit.", is_eager=True),
    ] = False,
) -> None:
    if show_version:
        typer.echo(f"CircuitDK {__version__}")
        raise typer.Exit()
    level = logging.DEBUG if verbose > 1 else logging.INFO if verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


@app.command()
def synth(config: ConfigOption = Path("circuitdk.toml"), json_output: JsonOption = False) -> None:
    """Synthesize deterministic desired Circuit IR."""
    ir = _project(config).synth()
    if json_output:
        _emit(ir.to_dict(), as_json=True)
    else:
        typer.echo(f"Synthesized {ir.id}: {len(ir.parts)} parts, {len(ir.nets)} nets")


@app.command("diff")
def diff_command(
    config: ConfigOption = Path("circuitdk.toml"),
    json_output: JsonOption = False,
) -> None:
    """Show desired-to-actual managed changes."""
    plan = _project(config).plan()
    payload = {"has_changes": plan.has_changes, "actions": [asdict(a) for a in plan.actions]}
    payload["no_connect_actions"] = [asdict(action) for action in plan.no_connect_actions]
    if json_output:
        _emit(payload, as_json=True)
    elif not plan.actions and not plan.no_connect_actions:
        _status("✅ NO CHANGES — Circuit is up to date.", color=GREEN)
    else:
        typer.echo("CircuitDK diff\n")
        counts = {"create": 0, "update": 0, "delete": 0}
        for action in plan.actions:
            marker = {"create": "+", "update": "~", "delete": "-"}[action.kind]
            color = {"create": GREEN, "update": YELLOW, "delete": RED}[action.kind]
            counts[action.kind] += 1
            suffix = f" (pending: {action.reason})" if not action.applicable else ""
            typer.secho(f"{marker} {action.circuit_id}{suffix}", fg=color, bold=True)
            for change in action.changes:
                typer.echo(f"    {change.field}: {change.actual!r} → {change.desired!r}")
        for action in plan.no_connect_actions:
            marker = "+" if action.kind == "create" else "-"
            color = GREEN if action.kind == "create" else RED
            counts[action.kind] += 1
            suffix = f" (pending: {action.reason})" if not action.applicable else ""
            typer.secho(f"{marker} no-connect {action.pin_key}{suffix}", fg=color, bold=True)
        typer.echo()
        _status(
            "\u2139\ufe0f CHANGES FOUND — "
            f"{counts['create']} create, {counts['update']} update, "
            f"{counts['delete']} delete.",
            color=CYAN,
        )
        raise typer.Exit(2)


@app.command()
def drift(config: ConfigOption = Path("circuitdk.toml"), json_output: JsonOption = False) -> None:
    """Show KiCad-side changes since the previous deploy."""
    changes = _project(config).drift()
    payload = [asdict(change) for change in changes]
    if json_output:
        _emit(payload, as_json=True)
    elif not changes:
        typer.echo("No managed drift (or no previous state).")
    else:
        for change in changes:
            typer.echo(
                f"! {change.circuit_id} {change.field}: {change.applied!r} -> {change.actual!r}"
            )
        raise typer.Exit(2)


@app.command()
def deploy(
    config: ConfigOption = Path("circuitdk.toml"),
    no_backup: Annotated[bool, typer.Option(help="Do not create a .bak file.")] = False,
    json_output: JsonOption = False,
) -> None:
    """Apply safe managed updates atomically."""
    try:
        result = _project(config).deploy(backup=not no_backup)
    except Exception as error:
        logger.debug("deployment failed", exc_info=True)
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(1) from error
    wiring, electrical, warnings = _erc_groups(result)
    payload = {
        "apply_status": "succeeded" if result.reconciled else "incomplete",
        "applied_creates": result.applied_creates,
        "applied_updates": result.applied_updates,
        "applied_deletes": result.applied_deletes,
        "applied_no_connect_changes": result.applied_no_connect_changes,
        "pending_actions": result.pending_actions,
        "backup": str(result.backup) if result.backup else None,
        "complete": result.complete,
        "reconciled": result.reconciled,
        "structural_validation": result.structural_validation,
        "electrical_validation": result.electrical_validation,
        "manual_wiring_required": bool(wiring),
        "manual_wiring_issue_count": len(wiring),
        "electrical_error_count": len(electrical),
        "ready": result.ready,
        "erc_error_count": len(result.erc.errors) if result.erc is not None else None,
        "erc_warning_count": len(result.erc.warnings) if result.erc is not None else None,
        "erc_violations": (
            [asdict(item) for item in result.erc.violations] if result.erc is not None else None
        ),
    }
    if json_output:
        _emit(payload, as_json=True)
    else:
        typer.echo("CircuitDK deploy\n")
        _status(
            "☑ APPLY SUCCEEDED" if result.reconciled else "❌ APPLY INCOMPLETE",
            color=GREEN if result.reconciled else RED,
        )
        applied = (
            result.applied_creates
            + result.applied_updates
            + result.applied_deletes
            + result.applied_no_connect_changes
        )
        if applied:
            typer.echo(
                "  Applied "
                f"{result.applied_creates} create(s), "
                f"{result.applied_updates} update(s), "
                f"{result.applied_deletes} delete(s), and "
                f"{result.applied_no_connect_changes} no-connect change(s)."
            )
        else:
            typer.echo("  No managed changes were applied.")
        if result.pending_actions:
            typer.echo(f"  {result.pending_actions} managed action(s) could not be applied.")

        if result.erc is None:
            typer.echo()
            _status("⚠ STRUCTURAL VALIDATION SKIPPED", color=YELLOW)
            typer.echo("  kicad-cli validation is unavailable or disabled.")
            typer.echo()
            _status("⚠ ELECTRICAL VALIDATION SKIPPED", color=YELLOW)
        else:
            typer.echo()
            _status("☑ SCHEMATIC VALID", color=GREEN)
            typer.echo("  KiCad parsed the schematic and exported its netlist.")
            if wiring:
                typer.echo()
                _status("⚠ MANUAL WIRING REQUIRED", color=YELLOW)
                typer.echo(f"  {len(wiring)} pin connection(s) are not yet realized.")
                for violation in wiring:
                    typer.echo(f"  warning [{violation.violation_type}]: {violation.description}")
                typer.echo("  Complete the wiring in KiCad, then run `circuitdk test`.")
            if electrical:
                typer.echo()
                _status("❌ ELECTRICAL VALIDATION FAILED", color=RED)
                for violation in electrical:
                    typer.echo(f"  error [{violation.violation_type}]: {violation.description}")
            elif not wiring:
                typer.echo()
                if warnings:
                    _status("⚠ ELECTRICAL VALIDATION PASSED WITH WARNINGS", color=YELLOW)
                else:
                    _status("☑ ELECTRICAL VALIDATION PASSED", color=GREEN)
            if warnings:
                typer.echo()
                _status("⚠ ERC WARNINGS", color=YELLOW)
                for violation in warnings:
                    typer.echo(f"  warning [{violation.violation_type}]: {violation.description}")

        typer.echo()
        if not result.reconciled:
            _status("❌ FAILED — Deployment was not fully applied.", color=RED)
        elif result.erc is None:
            _status(
                "⚠️ VALIDATION SKIPPED — Deployment was applied; electrical state was not verified.",
                color=YELLOW,
            )
        elif electrical:
            _status(
                "❌ INVALID — Deployment was applied, but electrical violations remain.",
                color=RED,
            )
        elif wiring:
            _status(
                "⚠️ ACTION REQUIRED — Deployment was applied; complete the manual wiring.",
                color=YELLOW,
            )
        elif warnings:
            _status(
                "⚠️ COMPLETE WITH WARNINGS — Circuit is valid; "
                f"review {len(warnings)} ERC warning(s).",
                color=YELLOW,
            )
        else:
            _status("✅ COMPLETE — Circuit is up to date and electrically valid.", color=GREEN)
    if not result.reconciled or electrical:
        raise typer.Exit(2)


@app.command("test")
def test_command(
    config: ConfigOption = Path("circuitdk.toml"),
    json_output: JsonOption = False,
) -> None:
    """Check managed fields, connectivity, libraries, and KiCad ERC."""
    result = _project(config).run_tests()
    payload = {
        "ok": result.ok,
        "actions": [asdict(action) for action in result.plan.actions],
        "no_connect_actions": [asdict(action) for action in result.plan.no_connect_actions],
        "connectivity_issues": (
            [asdict(issue) for issue in result.connectivity.issues]
            if result.connectivity is not None
            else None
        ),
        "erc_violations": (
            [asdict(item) for item in result.erc.violations if item.severity != "exclusion"]
            if result.erc is not None
            else None
        ),
        "unspecified_pins": result.pin_coverage.unspecified,
        "library_issues": result.library_issues,
        "infrastructure_errors": result.infrastructure_errors,
    }
    if json_output:
        _emit(payload, as_json=True)
    else:
        typer.echo("PASS circuit conformance" if result.ok else "FAIL circuit conformance")
        for issue in result.connectivity.issues if result.connectivity is not None else ():
            typer.echo(f"  connectivity: {issue.message}")
        for violation in result.erc.violations if result.erc is not None else ():
            if violation.severity != "exclusion":
                typer.echo(f"  ERC {violation.severity}: {violation.description}")
        for pin in result.pin_coverage.unspecified:
            typer.echo(f"  unspecified pin: {pin}")
        for issue in result.library_issues:
            typer.echo(f"  library: {issue}")
        for error in result.infrastructure_errors:
            typer.echo(f"  infrastructure: {error}")
    if not result.ok:
        raise typer.Exit(2)


@app.command()
def inspect(
    config: ConfigOption = Path("circuitdk.toml"),
    json_output: JsonOption = True,
) -> None:
    """Inspect desired, actual, plan, and drift state."""
    _emit(_project(config).inspect(), as_json=json_output)


@app.command()
def adopt(
    reference: Annotated[str, typer.Option("--reference", "-r")],
    circuit_id: Annotated[str, typer.Option("--id")],
    config: ConfigOption = Path("circuitdk.toml"),
) -> None:
    """Adopt an existing KiCad symbol by reference."""
    try:
        _project(config).adopt(reference, circuit_id)
    except Exception as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(f"Adopted {reference} as {circuit_id}.")


@app.command("move")
def move_command(
    old_id: Annotated[str, typer.Option("--from")],
    new_id: Annotated[str, typer.Option("--to")],
    config: ConfigOption = Path("circuitdk.toml"),
) -> None:
    """Rename a managed logical ID in the schematic."""
    try:
        _project(config).move(old_id, new_id)
    except Exception as error:
        typer.echo(f"error: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(f"Moved {old_id} to {new_id}.")


@app.command()
def lock(
    config: ConfigOption = Path("circuitdk.toml"),
    check: Annotated[bool, typer.Option(help="Fail when the current libraries differ.")] = False,
) -> None:
    """Write or verify resolved symbol and footprint library hashes."""
    project = _project(config)
    current, issues = project.library_lock()
    from .lock import CircuitLock

    previous = CircuitLock.load(project.lock_path)
    differences = previous.differences(current) if previous is not None else ("lockfile missing",)
    if issues:
        for issue in issues:
            typer.echo(f"warning: {issue}", err=True)
    if check:
        if differences:
            for difference in differences:
                typer.echo(f"! {difference}")
            raise typer.Exit(2)
        typer.echo("Library lock is current.")
        return
    current.write_atomic(project.lock_path)
    typer.echo(f"Wrote {project.lock_path} with {len(current.libraries)} entries.")


if __name__ == "__main__":
    app()
