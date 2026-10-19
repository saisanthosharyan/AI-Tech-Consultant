import sys
import importlib.util
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

TASK1_DIR = ROOT_DIR / "task1-knowledge-brain"
TASK2_DIR = ROOT_DIR / "task2-inbox-agent"
TASK3_DIR = ROOT_DIR / "task3-meeting-to-scope"

for p in [TASK1_DIR, TASK2_DIR, TASK3_DIR]:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

def load_module_from_file(module_name: str, file_path: Path):
    """Dynamically loads and registers a module under a distinct namespace in sys.modules."""
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    if spec and spec.loader:
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        spec.loader.exec_module(mod)
        return mod
    return None
