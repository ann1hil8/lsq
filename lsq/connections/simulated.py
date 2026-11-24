from .base import Connection
from .registry import register_transport

@register_transport("simulated")
class SimulatedConnection(Connection):
    def __init__(self, name, config, logger=None):
        super().__init__(name); self.config=config; self.logger=logger or (lambda *_:None); self.model=str(config.get("model", "generic")).lower(); self.queue=bytearray(); self.voltage=float(config.get("voltage", 5)); self.current=float(config.get("current", 0)); self.output=False
    def open(self): self.is_open=True
    def close(self): self.is_open=False
    def write(self, data):
        command=(data if isinstance(data,bytes) else str(data).encode()).decode(errors="replace").strip(); response=self._respond(command)
        if response is not None: self.queue.extend(response.encode()+b"\r\n")
        return len(data)
    def read(self, size=1):
        data=bytes(self.queue[:size]); del self.queue[:size]; return data
    def read_until(self, terminator):
        result=bytearray()
        while self.queue:
            result.extend(self.read(1))
            if result.endswith(terminator): return bytes(result)
        return bytes(result)
    def flush(self):
        self.queue.clear()
    def _respond(self, command):
        if self.model == "psp405":
            if command == "L": return f"V{self.voltage:05.2f}A{self.current:05.3f}W000.0U17I5.00P085F{int(self.output)}00010"
            if command == "V": return f"V{self.voltage:05.2f}"
            if command == "A": return f"A{self.current:05.3f}"
            if command == "SV": self.voltage=0; return None
            if command.startswith("SV "): self.voltage=float(command.split()[1]); return None
            if command.startswith("SI "): self.current=float(command.split()[1]); return None
            if command == "*IDN?": return "SIMULATED,PSP405,0,1"
        if command == "*IDN?": return f"SIMULATED,{self.model},0,1"
        return "0"
