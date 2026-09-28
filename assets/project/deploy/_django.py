"""Bootstrap Django for deploy scripts run by path (`python deploy/<script>.py`).

Each script puts the repository root on `sys.path` before importing this module.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def setup(default_settings: str = "config.settings.test") -> Path:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", default_settings)
    import django

    django.setup()
    return ROOT
