import hashlib
import os
from pathlib import Path
from .base import Connection
from ..errors import LockContentionError

class ResourceLock:
    def __init__(self, key):
        root = Path(os.environ.get("LSQ_LOCK_DIR", Path.home() / ".lsq" / "locks")); root.mkdir(parents=True, exist_ok=True)
        normalized = os.path.realpath(key.strip()) if key.strip().startswith("/dev/") else key.strip()
        self.path = root / (hashlib.sha256(normalized.lower().encode()).hexdigest() + ".lock"); self.handle = None
    def acquire(self):
        self.handle = self.path.open("a+")
        try:
            if os.name == "nt":
                import msvcrt
                self.handle.seek(0); msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, IOError) as exc:
            self.handle.close(); self.handle = None
            raise LockContentionError(f"resource is locked by another LSQ process: {self.path.name}") from exc
    def release(self):
        if not self.handle: return
        try:
            if os.name == "nt":
                import msvcrt
                self.handle.seek(0); msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close(); self.handle = None
