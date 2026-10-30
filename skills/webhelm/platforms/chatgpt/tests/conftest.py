import sys
from pathlib import Path

PLATFORM = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(PLATFORM / "runtime"), str(PLATFORM / "actions")]
