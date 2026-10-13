"""Each experiment has its own module named common, so the one loaded before is dropped."""

import sys
from pathlib import Path
from typing import Any


def pytest_pycollect_makemodule(module_path: Path, parent: Any) -> None:
    sys.modules.pop("common", None)
