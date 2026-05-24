"""pytest-Setup.

Lädt ``_utils`` direkt aus der Datei (via importlib), ohne
``custom_components/plant_care/`` auf den sys.path zu legen. Der direkte
Path-Eintrag würde die plant_care-eigene ``calendar.py`` (HA-Platform)
Pythons stdlib ``calendar`` shadowen – ``datetime.strptime`` importiert
intern stdlib ``calendar``, das hätte beim Test-Import gekracht.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
UTILS_PATH = REPO_ROOT / "custom_components" / "plant_care" / "_utils.py"

if "_utils" not in sys.modules:
    spec = importlib.util.spec_from_file_location("_utils", UTILS_PATH)
    assert spec and spec.loader, "Could not load _utils spec"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules["_utils"] = module
