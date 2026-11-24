import time
from contextlib import contextmanager

from .base import Connection
from ..errors import ConnectionError, TimeoutError
from .locking import ResourceLock
from .registry import register_transport


TERMINATORS = {"none": b"", "cr": b"\r", "lf": b"\n", "crlf": b"\r\n"}


def parse_bool(value):
    if isinstance(value, bool):
        return value
    value = str(value).lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"invalid boolean value: {value}")


def parse_terminator(value):
    value = str(value).lower()
    if value in TERMINATORS:
        return TERMINATORS[value]
    if value.startswith("hex:"):
        try:
            return bytes.fromhex(value[4:])
        except ValueError as exc:
            raise ValueError(f"invalid hexadecimal terminator: {value}") from exc
    raise ValueError(f"unknown terminator: {value}")


def parse_parity(value):
    values = {"none": "N", "even": "E", "odd": "O", "mark": "M", "space": "S"}
    if str(value).lower() not in values:
        raise ValueError(f"unknown parity: {value}")
    return values[str(value).lower()]


@register_transport("serial")
class SerialConnection(Connection):
    def __init__(self, name, config, port=None, dry_run=False, logger=None):
        super().__init__(name)
        self.config = config
        self.port = port or config.get("port")
        self.dry_run = dry_run
        self.logger = logger or (lambda *_: None)
        self.serial = None
        self.resource_lock = ResourceLock(str(self.port or self.name))

    def open(self):
        if self.is_open:
            return
        if not self.port:
            raise ConnectionError(f"no port selected for {self.name}")
        if self.dry_run:
            self.logger(f"DRY-RUN OPEN {self.name} {self.port}", "normal")
            self.is_open = True
            return
        try:
            self.resource_lock.acquire()
            import serial
            self.serial = serial.Serial(
                port=self.port,
                baudrate=int(self.config.get("baud", 9600)),
                bytesize=int(self.config.get("data_bits", 8)),
                parity=parse_parity(self.config.get("parity", "none")),
                stopbits=float(self.config.get("stop_bits", 1)),
                timeout=float(self.config.get("read_timeout", 2)),
                write_timeout=float(self.config.get("write_timeout", 2)),
                xonxoff=parse_bool(self.config.get("xonxoff", False)),
                rtscts=parse_bool(self.config.get("rtscts", False)),
                dsrdtr=parse_bool(self.config.get("dsrdtr", False)),
            )
            if "dtr" in self.config:
                self.serial.dtr = parse_bool(self.config["dtr"])
            if "rts" in self.config:
                self.serial.rts = parse_bool(self.config["rts"])
            self.is_open = True
        except Exception as exc:
            self.resource_lock.release()
            raise ConnectionError(f"cannot open {self.name} on {self.port}: {exc}") from exc

    def close(self):
        try:
            if self.serial:
                self.serial.close()
        finally:
            self.serial = None
            self.is_open = False
            self.resource_lock.release()

    def write(self, data):
        if not self.is_open:
            raise ConnectionError(f"connection is closed: {self.name}")
        payload = data if isinstance(data, bytes) else str(data).encode("utf-8")
        if self.dry_run:
            self.logger(f"DRY-RUN WRITE {self.name} {payload!r}", "verbose")
            return len(payload)
        self.logger(f"WRITE {self.name} {payload!r}", "verbose")
        return self.serial.write(payload)

    def read(self, size=1):
        if not self.is_open:
            raise ConnectionError(f"connection is closed: {self.name}")
        if self.dry_run:
            return b""
        data = self.serial.read(size)
        self.logger(f"READ {self.name} {data!r}", "trace")
        return data

    def read_until(self, terminator):
        if not self.is_open:
            raise ConnectionError(f"connection is closed: {self.name}")
        if self.dry_run:
            return b""
        if not terminator:
            return self.read(self.serial.in_waiting or 1)
        active_timeout = float(self.serial.timeout) if (self.serial and self.serial.timeout is not None) else float(self.config.get("read_timeout", 2))
        buffer = bytearray()
        started = time.monotonic()
        deadline = started + active_timeout
        while time.monotonic() < deadline:
            data = self.read(1)
            if data:
                buffer.extend(data)
                if buffer.endswith(terminator):
                    self.logger(f"READ {self.name} {bytes(buffer)!r}", "verbose")
                    return bytes(buffer)
        raise TimeoutError(self.name, "read_until", active_timeout, time.monotonic() - started)

    @contextmanager
    def timeout_context(self, timeout):
        if timeout is None or self.dry_run or self.serial is None:
            yield; return
        old = self.serial.timeout
        self.serial.timeout = timeout
        try: yield
        finally: self.serial.timeout = old

    def flush(self):
        if self.serial and not self.dry_run:
            self.serial.reset_input_buffer()
            self.serial.reset_output_buffer()
