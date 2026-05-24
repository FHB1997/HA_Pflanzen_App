"""pytest-Setup.

Macht ``_utils`` (und weitere reine Hilfsmodule) direkt importierbar,
ohne ``custom_components/plant_care/__init__.py`` zu laden – das würde
sonst homeassistant + voluptuous als Test-Dependencies erzwingen.
"""
from __future__ import annotations

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
PLANT_CARE_DIR = REPO_ROOT / "custom_components" / "plant_care"

for path in (str(PLANT_CARE_DIR), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)
