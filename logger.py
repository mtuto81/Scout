import json
import os
import sys
from datetime import datetime

class Logger:
    def __init__(self, log_file="log.jsonl", enabled=None):
        # Use NDJSON (JSON Lines) to append logs without re-reading the full file.
        self.log_file = log_file
        if enabled is None:
            enabled = os.environ.get("SCOUT_ENABLE_LOGS") == "1" or not getattr(sys, "frozen", False)
        self.enabled = enabled
        if not enabled and os.path.exists(self.log_file):
            try:
                os.remove(self.log_file)
            except Exception:
                pass

    def log(self, data):
        """Append a single JSON object as a newline to the log file (NDJSON)."""
        if not self.enabled:
            return
        data["timestamp"] = str(datetime.now())
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
        except Exception:
            # Best-effort logging: ignore failures to prevent systemic crashes
            pass
