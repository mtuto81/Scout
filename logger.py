import json
from datetime import datetime

class Logger:
    def __init__(self, log_file="log.jsonl"):
        # Use NDJSON (JSON Lines) to append logs without re-reading the full file.
        self.log_file = log_file

    def log(self, data):
        """Append a single JSON object as a newline to the log file (NDJSON)."""
        data["timestamp"] = str(datetime.now())
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
        except Exception:
            # Best-effort logging: ignore failures to prevent systemic crashes
            pass

