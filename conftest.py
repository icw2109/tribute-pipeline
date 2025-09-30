# Ensure src/ is on sys.path for tests
import sys
from pathlib import Path
root = Path(__file__).parent
src = root / "src"
if str(src) not in sys.path:
    sys.path.insert(0, str(src))
