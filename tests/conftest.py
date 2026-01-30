# SPDX-License-Identifier: LGPL-3.0-or-later
import os
import sys
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _THIS_DIR.parent

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

os.environ.setdefault("PYTHONPATH", str(_REPO_ROOT))

# Import fixtures from the fixtures directory
pytest_plugins = ["tests.fixtures.test_images"]
