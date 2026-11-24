import json
import tempfile
import unittest
from pathlib import Path

from lsq.connections.discovery import SerialCandidate
from lsq.connections.state import ConnectionState


class ConnectionStateTests(unittest.TestCase):
    def test_save_and_load_port(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "connections.json"
            state = ConnectionState(path)
            state.save_connection("psp", SerialCandidate("COM8", 0x1234, 0x5678, "adapter", description="USB serial"))
            self.assertEqual(ConnectionState(path).get_port("psp"), "COM8")
            self.assertEqual(json.loads(path.read_text())["psp"]["vid"], 0x1234)
