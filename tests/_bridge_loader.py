"""Test helpers for loading bridge modules without full Home Assistant deps."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
import importlib.util
from pathlib import Path
import sys
import types


def _ensure_homeassistant_stubs() -> None:
    if "homeassistant" not in sys.modules:
        homeassistant = types.ModuleType("homeassistant")
        homeassistant.__path__ = []
        sys.modules["homeassistant"] = homeassistant

    if "homeassistant.const" not in sys.modules:
        const_mod = types.ModuleType("homeassistant.const")

        class Platform(str, Enum):
            SWITCH = "switch"
            SELECT = "select"
            BINARY_SENSOR = "binary_sensor"

        const_mod.Platform = Platform
        sys.modules["homeassistant.const"] = const_mod

    if "homeassistant.exceptions" not in sys.modules:
        exc_mod = types.ModuleType("homeassistant.exceptions")

        class HomeAssistantError(Exception):
            """Minimal test stub of HA exception type."""

        exc_mod.HomeAssistantError = HomeAssistantError
        sys.modules["homeassistant.exceptions"] = exc_mod

    if "homeassistant.util" not in sys.modules:
        util_mod = types.ModuleType("homeassistant.util")
        util_mod.__path__ = []
        sys.modules["homeassistant.util"] = util_mod

    if "homeassistant.util.dt" not in sys.modules:
        dt_mod = types.ModuleType("homeassistant.util.dt")
        dt_mod.utcnow = lambda: datetime.now(UTC)
        sys.modules["homeassistant.util.dt"] = dt_mod


def _ensure_package_stubs(base_dir: Path) -> None:
    custom_components_dir = base_dir / "custom_components"
    integration_dir = custom_components_dir / "jvc_dla_wifi_bridge"

    custom_components_pkg = types.ModuleType("custom_components")
    custom_components_pkg.__path__ = [str(custom_components_dir)]
    sys.modules["custom_components"] = custom_components_pkg

    integration_pkg = types.ModuleType("custom_components.jvc_dla_wifi_bridge")
    integration_pkg.__path__ = [str(integration_dir)]
    sys.modules["custom_components.jvc_dla_wifi_bridge"] = integration_pkg


def _load_module(name: str, path: Path):
    if name in sys.modules:
        del sys.modules[name]

    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module: {name}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_bridge_modules():
    """Load const and bridge modules with minimal dependency stubs."""
    base_dir = Path(__file__).resolve().parents[1]
    integration_dir = base_dir / "custom_components" / "jvc_dla_wifi_bridge"

    _ensure_homeassistant_stubs()
    _ensure_package_stubs(base_dir)

    const_mod = _load_module(
        "custom_components.jvc_dla_wifi_bridge.const", integration_dir / "const.py"
    )
    bridge_mod = _load_module(
        "custom_components.jvc_dla_wifi_bridge.bridge", integration_dir / "bridge.py"
    )

    return const_mod, bridge_mod
