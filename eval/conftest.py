"""Make the scripts in eval/ importable from the tests; eval/ is not a package."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
