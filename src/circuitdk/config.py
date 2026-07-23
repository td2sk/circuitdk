from __future__ import annotations

import importlib
import sys
import tomllib
from pathlib import Path
from typing import Any

from .project import KicadProject


def load_project(config_path: str | Path = "circuitdk.toml") -> KicadProject:
    path = Path(config_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"configuration file not found: {path}")
    data: dict[str, Any] = tomllib.loads(path.read_text(encoding="utf-8"))
    project_config = data.get("project")
    if not isinstance(project_config, dict):
        raise ValueError("configuration requires a [project] table")
    entrypoint = project_config.get("entrypoint")
    if not isinstance(entrypoint, str) or ":" not in entrypoint:
        raise ValueError("project.entrypoint must have the form 'module:object'")
    module_name, object_name = entrypoint.split(":", 1)
    sys.path.insert(0, str(path.parent))
    try:
        module = importlib.import_module(module_name)
    finally:
        sys.path.pop(0)
    project = getattr(module, object_name, None)
    if not isinstance(project, KicadProject):
        raise TypeError(f"{entrypoint} is not a KicadProject")
    state_directory = project_config.get("state_directory")
    if isinstance(state_directory, str) and project.state_directory == Path(".circuitdk"):
        project.state_directory = path.parent / state_directory
    if not project.schematic.is_absolute():
        project.schematic = path.parent / project.schematic
    return project
