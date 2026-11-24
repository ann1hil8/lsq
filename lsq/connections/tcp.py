import socket
import time
from contextlib import contextmanager

from .base import Connection
from .locking import ResourceLock
from .registry import register_transport
from ..errors import ConnectionError, TimeoutError


def _terminator(value):
    if value is None: return b"\n"
    if isinstance(value, bytes): return value
    values = {"none": b"", "lf": b"\n", "cr": b"\r", "crlf": b"\r\n", "\\n": b"\n", "\\r": b"\r", "\\r\\n": b"\r\n"}
    return values.get(str(value).lower(), str(value).encode("ascii"))


@register_transport("tcp")
class TcpConnection(Connection):
    def __init__(self, name, config, host=None, port=None, dry_run=False, logger=None):
        super().__init__(name)
        self.config = config
        self.host = host or config.get("host")
        raw_port = port if port is not None else config.get("port")
        self.port = int(raw_port) if raw_port is not None else None
        self.dry_run = dry_run
        self.logger = logger or (lambda *_: None)
        self.socket = None
        self.resource_lock = ResourceLock(f"{self.host}:{self.port}")

    def open(self):
        if self.is_open: return
        if not self.host or self.port is None: raise ConnectionError(f"host and port are required for {self.name}")
        if self.dry_run:
            self.is_open = True
            return
        try:
            self.resource_lock.acquire()
            self.socket = socket.create_connection((self.host, self.port), float(self.config.get("read_timeout", 2)))
            self.is_open = True
        except OSError as exc:
            self.resource_lock.release()
            raise ConnectionError(f"cannot open {self.name} at {self.host}:{self.port}: {exc}") from exc

    def close(self):
        try:
            if self.socket: self.socket.close()
        finally:
            self.socket = None
            self.is_open = False
            self.resource_lock.release()

    def write(self, data):
        if not self.is_open: raise ConnectionError(f"connection is closed: {self.name}")
        payload = data if isinstance(data, bytes) else str(data).encode()
        if not payload.endswith(_terminator(self.config.get("write_termination", "lf"))):
            payload += _terminator(self.config.get("write_termination", "lf"))
        if self.dry_run:
            self.logger(f"DRY-RUN WRITE {self.name} {payload!r}", "verbose")
            return len(payload)
        self.logger(f"WRITE {self.name} {payload!r}", "verbose")
        self.socket.sendall(payload)
        return len(payload)

    def read(self, size=1):
        if not self.is_open: raise ConnectionError(f"connection is closed: {self.name}")
        if self.dry_run: return b""
        data = self.socket.recv(size)
        self.logger(f"READ {self.name} {data!r}", "trace")
        return data

    def read_until(self, terminator):
        if not self.is_open: raise ConnectionError(f"connection is closed: {self.name}")
        if self.dry_run: return b""
        if not terminator: return self.read(4096)
        active_timeout = float(self.socket.gettimeout()) if self.socket.gettimeout() is not None else float(self.config.get("read_timeout", 2))
        result = bytearray(); started = time.monotonic(); deadline = started + active_timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0: break
            self.socket.settimeout(remaining)
            try: data = self.read(1)
            except socket.timeout: break
            if not data: raise ConnectionError(f"remote peer closed connection: {self.name}")
            result.extend(data)
            if result.endswith(terminator): return bytes(result)
        raise TimeoutError(self.name, "read_until", active_timeout, time.monotonic() - started)

    def query(self, command):
        self.write(command)
        response = self.read_until(_terminator(self.config.get("read_termination", "lf")))
        return response.decode("utf-8", errors="replace").rstrip("\r\n")

    def flush(self):
        return None

    @contextmanager
    def timeout_context(self, timeout):
        old = self.socket.gettimeout() if self.socket else None
        if self.socket and timeout is not None: self.socket.settimeout(timeout)
        try: yield
        finally:
            if self.socket: self.socket.settimeout(old)
