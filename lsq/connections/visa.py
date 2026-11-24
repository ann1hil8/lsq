import time

from .base import Connection
from .registry import register_transport
from .locking import ResourceLock
from contextlib import contextmanager
from ..errors import ConnectionError, TimeoutError


@register_transport("visa")
class VisaConnection(Connection):
    def __init__(self, name, config, resource=None, dry_run=False, logger=None):
        super().__init__(name)
        self.config = config
        self.resource_name = resource or config.get("resource")
        self.dry_run = dry_run
        self.logger = logger or (lambda *_: None)
        self.resource = None
        self.resource_lock = ResourceLock(self.resource_name or self.name)

    def open(self):
        if self.is_open:
            return
        if not self.resource_name:
            raise ConnectionError(f"no VISA resource selected for {self.name}")
        if self.dry_run:
            self.logger(f"DRY-RUN OPEN {self.name} {self.resource_name}", "normal")
            self.is_open = True
            return
        try:
            self.resource_lock.acquire()
            import pyvisa
            manager = pyvisa.ResourceManager(self.config.get("visa_backend") or "")
            self.resource = manager.open_resource(self.resource_name)
            if "read_timeout" in self.config:
                self.resource.timeout = int(float(self.config["read_timeout"]) * 1000)
            if "read_termination" in self.config:
                self.resource.read_termination = self.config["read_termination"]
            if "write_termination" in self.config:
                self.resource.write_termination = self.config["write_termination"]
            self.is_open = True
        except Exception as exc:
            self.resource_lock.release()
            raise ConnectionError(f"cannot open VISA resource {self.resource_name}: {exc}") from exc

    def close(self):
        try:
            if self.resource:
                self.resource.close()
        finally:
            self.resource = None
            self.is_open = False
            self.resource_lock.release()

    def write(self, data):
        if not self.is_open:
            raise ConnectionError(f"connection is closed: {self.name}")
        if self.dry_run:
            self.logger(f"DRY-RUN WRITE {self.name} {data!r}", "verbose")
            return len(data)
        self.logger(f"WRITE {self.name} {data!r}", "verbose")
        if isinstance(data, bytes):
            return self.resource.write_raw(data)
        return self.resource.write(str(data))

    def read(self, size=1):
        if not self.is_open:
            raise ConnectionError(f"connection is closed: {self.name}")
        if self.dry_run:
            return b""
        data = self.resource.read_bytes(size)
        self.logger(f"READ {self.name} {data!r}", "trace")
        return data

    def read_until(self, terminator):
        if not self.is_open:
            raise ConnectionError(f"connection is closed: {self.name}")
        if self.dry_run:
            return b""
        if terminator in (b"\n", b"\r\n"):
            data = self.resource.read().encode("utf-8")
            self.logger(f"READ {self.name} {data!r}", "verbose")
            return data
        active_timeout = (float(self.resource.timeout) / 1000.0) if (self.resource and getattr(self.resource, "timeout", None)) else float(self.config.get("read_timeout", 2))
        buffer = bytearray()
        started = time.monotonic()
        deadline = started + active_timeout
        while time.monotonic() < deadline:
            buffer.extend(self.read(1))
            if buffer.endswith(terminator):
                return bytes(buffer)
        raise TimeoutError(self.name, "read_until", active_timeout, time.monotonic() - started)

    @contextmanager
    def timeout_context(self, timeout):
        if timeout is None or not self.resource:
            yield; return
        old = self.resource.timeout; self.resource.timeout = int(float(timeout) * 1000)
        try: yield
        finally: self.resource.timeout = old

    def query(self, command):
        if not self.is_open:
            self.open()
        if self.dry_run:
            self.logger(f"DRY-RUN QUERY {self.name} {command!r}", "verbose")
            return ""
        self.logger(f"WRITE {self.name} {command!r}", "verbose")
        response = self.resource.query(command)
        self.logger(f"READ {self.name} {response!r}", "verbose")
        return response.rstrip("\r\n")

    def query_binary(self, command):
        if not self.is_open:
            self.open()
        if self.dry_run:
            self.logger(f"DRY-RUN QUERY {self.name} {command!r}", "verbose")
            return b""
        self.logger(f"WRITE {self.name} {command!r}", "verbose")
        previous_termination = self.resource.read_termination
        self.resource.read_termination = None
        try:
            self.resource.write(command)
            response = self.resource.read_raw()
        finally:
            self.resource.read_termination = previous_termination
        self.logger(f"READ {self.name} {response!r}", "verbose")
        return response

    def flush(self):
        if self.resource and not self.dry_run:
            try:
                self.resource.clear()
            except Exception:
                return

@register_transport("gpib")
class GpibConnection(VisaConnection):
    """GPIB resources use the VISA transport with a GPIB resource string."""
