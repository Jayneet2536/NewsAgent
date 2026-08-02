"""src/main.py — thin re-export shim.

All real application logic now lives in src/api/.
This module exists only for backward-compatibility with any tooling that
imports or launches ``src.main:app`` directly.
"""

from .api.main import app  # noqa: F401  (re-exported)
