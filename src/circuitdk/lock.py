from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

LOCK_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class LockedLibrary:
    kind: str
    library_id: str
    source: str
    sha256: str


@dataclass(frozen=True, slots=True)
class CircuitLock:
    libraries: tuple[LockedLibrary, ...]
    schema_version: int = LOCK_SCHEMA_VERSION

    @classmethod
    def load(cls, path: Path) -> CircuitLock | None:
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema_version") != LOCK_SCHEMA_VERSION:
            raise ValueError(f"unsupported lock schema: {data.get('schema_version')}")
        libraries = tuple(LockedLibrary(**item) for item in data.get("libraries", []))
        return cls(libraries)

    def differences(self, other: CircuitLock) -> tuple[str, ...]:
        expected = {(item.kind, item.library_id): item for item in self.libraries}
        actual = {(item.kind, item.library_id): item for item in other.libraries}
        messages: list[str] = []
        for key in sorted(set(expected) | set(actual)):
            old = expected.get(key)
            new = actual.get(key)
            if old is None:
                messages.append(f"new {key[0]} library: {key[1]}")
            elif new is None:
                messages.append(f"removed {key[0]} library: {key[1]}")
            elif old.sha256 != new.sha256 or old.source != new.source:
                messages.append(f"changed {key[0]} library: {key[1]}")
        return tuple(messages)

    def write_atomic(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        payload = {
            "schema_version": self.schema_version,
            "libraries": [asdict(item) for item in self.libraries],
        }
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, path)
