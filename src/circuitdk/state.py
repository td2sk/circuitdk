from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .version import __version__

STATE_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class ProjectState:
    applied: dict[str, dict[str, object]]
    schematic_sha256: str
    schema_version: int = STATE_SCHEMA_VERSION
    tool_version: str = __version__

    @classmethod
    def load(cls, path: Path) -> ProjectState | None:
        if not path.exists():
            return None
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema_version") != STATE_SCHEMA_VERSION:
            raise ValueError(f"unsupported state schema: {data.get('schema_version')}")
        applied = data.get("applied")
        if not isinstance(applied, dict):
            raise ValueError("invalid state: applied must be an object")
        return cls(
            applied=applied,
            schematic_sha256=str(data.get("schematic_sha256", "")),
            schema_version=int(data["schema_version"]),
            tool_version=str(data.get("tool_version", "unknown")),
        )

    def write_atomic(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        payload = {
            "schema_version": self.schema_version,
            "tool_version": self.tool_version,
            "schematic_sha256": self.schematic_sha256,
            "applied": self.applied,
        }
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
