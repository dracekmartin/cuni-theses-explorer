"""Each experiment has its own module named common, so the one loaded before is dropped."""

import sys
from pathlib import Path
from typing import Any


def pytest_pycollect_makemodule(module_path: Path, parent: Any) -> None:
    sys.modules.pop("common", None)
    # importlib mode does not put the folder of a test file on sys.path.
    sys.path.insert(0, str(module_path.parent))
