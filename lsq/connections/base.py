from abc import ABC, abstractmethod
from contextlib import contextmanager


class Connection(ABC):
    def __init__(self, name):
        self.name = name
        self.is_open = False

    @abstractmethod
    def open(self): ...

    @abstractmethod
    def close(self): ...

    @abstractmethod
    def write(self, data): ...

    @abstractmethod
    def read(self, size=1): ...

    @abstractmethod
    def read_until(self, terminator): ...

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *_):
        self.close()

    @contextmanager
    def timeout_context(self, timeout):
        yield
