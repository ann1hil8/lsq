import threading
import time
from abc import ABC

class BaseDriver(ABC):
    connection_defaults = {}
    identification = {}
    def __init__(self, connection=None):
        self.connection = connection; self.lock = threading.RLock(); self.opened = False; self.started = False; self.recovered = False
        self.telemetry = {"commands": 0, "errors": 0, "bytes_sent": 0, "bytes_received": 0, "latency": 0.0}
    def bind_connection(self, connection): self.connection = connection
    def open(self):
        if self.connection: self.connection.open()
        self.opened = True
    def startup(self): self.started = True
    def recover(self): self.recovered = True
    def shutdown(self): self.started = False
    def close(self):
        if self.connection: self.connection.close()
        self.opened = False
    def emergency_safe_state(self):
        with self.lock:
            for method in ("output_off", "disable_output", "set_output"):
                if hasattr(self, method):
                    try:
                        getattr(self, method)(False)
                    except TypeError:
                        getattr(self, method)()
                    break
    def set_local_mode(self):
        if hasattr(self, "set_local"): self.set_local()
