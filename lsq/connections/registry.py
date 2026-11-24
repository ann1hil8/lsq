from .base import Connection
TRANSPORTS = {}
def register_transport(name):
    def decorator(factory): TRANSPORTS[name] = factory; return factory
    return decorator
def create_transport(name, *args, **kwargs):
    if name not in TRANSPORTS: raise ValueError(f"unknown transport: {name}")
    return TRANSPORTS[name](*args, **kwargs)
