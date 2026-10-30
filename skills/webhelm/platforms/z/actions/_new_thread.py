import json
from pathlib import Path
import _lifecycle_common as lifecycle

cfg = json.loads(Path("__CFG_PATH__").read_text(encoding="utf-8"))
print(json.dumps(lifecycle.run(cfg, "new-thread", globals())), flush=True)