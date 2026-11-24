class ScriptError(Exception):
    def __init__(self, message, line=None, column=None):
        self.message, self.line, self.column = str(message), line, column
        location = f"line {line}" if line else "script"
        if column: location += f", column {column}"
        super().__init__(f"{location}: {self.message}")

class ConnectionError(Exception):
    """Instrument connection or transport failure."""

class TimeoutError(ConnectionError):
    def __init__(self, device, command=None, timeout=None, elapsed=None):
        if command is None:
            super().__init__(str(device)); self.device, self.command, self.timeout, self.elapsed = None, None, None, None; return
        self.device, self.command, self.timeout, self.elapsed = device, command, timeout, elapsed
        super().__init__(f"timeout reading from {device} after {elapsed:.3f}s (configured {timeout:.3f}s): {command}")

class AssertionFailure(ScriptError):
    def __init__(self, expression, line, actual=None, expected=None, tolerance=None):
        detail = f"assertion failed: {expression!r}"
        if actual is not None or expected is not None: detail += f"; actual={actual!r}, expected={expected!r}"
        if tolerance is not None: detail += f", tolerance={tolerance!r}"
        super().__init__(detail, line)

class LockContentionError(ConnectionError):
    """Another process owns the instrument resource lock."""
