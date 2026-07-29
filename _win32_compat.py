"""Small, dependency-free Windows process compatibility helpers."""
from __future__ import annotations

import sys


CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
