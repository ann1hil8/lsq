import socket
import tempfile
import threading
import unittest
from unittest.mock import patch

from lsq.connections.discovery import DeviceManager, VisaCandidate
from lsq.connections.tcp import TcpConnection
from lsq.dsl import parse_file


class _TcpServer:
    def __init__(self, responses):
        self.responses = responses; self.server = socket.socket(); self.server.bind(("127.0.0.1", 0)); self.server.listen(1); self.port = self.server.getsockname()[1]
        self.thread = threading.Thread(target=self._serve, daemon=True)

    def _serve(self):
        client, _ = self.server.accept()
        try:
            for response in self.responses:
                command = bytearray()
                while not command.endswith(b"\n"): command.extend(client.recv(1))
                client.sendall(response)
        finally:
            client.close()

    def __enter__(self):
        self.thread.start(); return self

    def __exit__(self, *_):
        self.thread.join(2); self.server.close()


class TcpTests(unittest.TestCase):
    def test_direct_tcp_ip_query(self):
        with _TcpServer([b"RIGOL TECHNOLOGIES,DG1022Z,SN,FW\n", b"RIGOL TECHNOLOGIES,DG1022Z,SN,FW\n"]) as server:
            with tempfile.TemporaryDirectory() as directory:
                manager = DeviceManager(state_path=f"{directory}/connections.json")
                manager.register("dg", {"type": "tcp", "host": "127.0.0.1", "port": server.port, "read_timeout": 2, "identify_command": "*IDN?", "identify_contains": "DG1022"})
                connection = manager.find("dg")
                self.assertEqual(connection.query("*IDN?"), "RIGOL TECHNOLOGIES,DG1022Z,SN,FW")
                self.assertEqual(manager.state.get_tcp("dg")["host"], "127.0.0.1")
                self.assertEqual(manager.state.get_tcp("dg")["port"], server.port)
            connection.close()

    def test_tcp_auto_discovery_uses_visa_identity_then_raw_tcp(self):
        with _TcpServer([b"RIGOL TECHNOLOGIES,DG1022Z,SN,FW\n"]) as server:
            with tempfile.TemporaryDirectory() as directory:
                manager = DeviceManager(state_path=f"{directory}/connections.json")
                manager.register("dg", {"type": "tcp", "discovery": "visa", "port": server.port, "identify_command": "*IDN?", "identify_contains": "DG1022", "resource_prefix": "TCPIP"})
                candidate = VisaCandidate("TCPIP0::127.0.0.1::INSTR")
                fake_visa = type("FakeVisa", (), {"close": lambda self: None})()
                with patch("lsq.connections.discovery.enumerate_visa_resources", return_value=[candidate]), patch.object(manager, "_probe_visa", return_value=fake_visa):
                    connection = manager.find("dg")
                self.assertEqual(connection.host, "127.0.0.1")
                self.assertEqual(connection.port, server.port)
                connection.close()

    def test_three_dg_tcp_examples_parse(self):
        for path in ("examples/dg1022z_tcp_auto_discovery.lsq", "examples/dg1022z_tcp_ip.lsq", "examples/dg1022z_tcp_to_usb.lsq"):
            self.assertTrue(parse_file(path).nodes, path)


if __name__ == "__main__":
    unittest.main()
