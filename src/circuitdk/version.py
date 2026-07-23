"""CircuitDK package version."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("circuitdk")
except PackageNotFoundError:  # pragma: no cover - only possible outside an installed environment
    __version__ = "0.0.0+unknown"
