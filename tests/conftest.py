"""Load the integration's pure modules without importing Home Assistant.

`custom_components/phomemo_t02/__init__.py` imports Home Assistant, so a plain
`import custom_components.phomemo_t02.protocol` would drag HA into the test run.
Instead we build a synthetic package rooted at the integration directory, which
lets `protocol.py`'s relative `from .const import ...` resolve normally.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG_DIR = ROOT / "custom_components" / "phomemo_t02"
PKG_NAME = "phomemo_t02_pure"


def _ensure_package() -> types.ModuleType:
    if PKG_NAME in sys.modules:
        return sys.modules[PKG_NAME]
    pkg = types.ModuleType(PKG_NAME)
    pkg.__path__ = [str(PKG_DIR)]  # type: ignore[attr-defined]
    sys.modules[PKG_NAME] = pkg
    return pkg


def load(module: str) -> types.ModuleType:
    """Import a single module from the integration by name."""
    _ensure_package()
    full = f"{PKG_NAME}.{module}"
    if full in sys.modules:
        return sys.modules[full]
    spec = importlib.util.spec_from_file_location(full, PKG_DIR / f"{module}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[full] = mod
    spec.loader.exec_module(mod)
    return mod
