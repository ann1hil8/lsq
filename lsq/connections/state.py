import json
import os
import tempfile
from pathlib import Path


def default_state_path():
    root = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(root) / "lsq" / "connections.json"


class ConnectionState:
    def __init__(self, path=None, logger=None):
        self.path = Path(path) if path else default_state_path()
        self.logger = logger or (lambda *_: None)
        self.values = self._load()

    def _load(self):
        try:
            with self.path.open("r", encoding="utf-8") as stream:
                data = json.load(stream)
            if isinstance(data, dict) and "entries" in data: return data.get("entries", {})
            return data if isinstance(data, dict) else {}
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError) as exc:
            self.logger(f"STATE IGNORE {self.path}: {exc}")
            return {}

    def get_port(self, name):
        value = self.values.get(name, {})
        return value.get("port") if isinstance(value, dict) else None

    def get_resource(self, name):
        value = self.values.get(name, {})
        return value.get("resource") if isinstance(value, dict) else None

    def get_tcp(self, name):
        value = self.values.get(name, {})
        if not isinstance(value, dict) or value.get("transport") != "tcp" or not value.get("host"):
            return None
        return {"host": value["host"], "port": int(value.get("port", 5555)), "identity": value.get("identity")}

    def _persist(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(prefix="connections-", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(self.values, stream, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        except Exception:
            try: os.unlink(temporary)
            except FileNotFoundError: temporary = None
            raise

    def save_connection(self, name, candidate):
        self.values[name] = {"port": candidate.port, "vid": candidate.vid, "pid": candidate.pid, "usb_serial": candidate.usb_serial, "description": candidate.description}
        self._persist()

    def save_resource(self, name, resource):
        self.values[name] = {"resource": resource}
        self._persist()

    def save_tcp(self, name, host, port=5555, identity=None, resource=None):
        entry = {"transport": "tcp", "host": str(host), "port": int(port), "identity": identity}
        if resource: entry["resource"] = resource
        self.values[name] = entry
        self._persist()

    def clear(self):
        self.values = {}
        try: self.path.unlink()
        except FileNotFoundError: return
