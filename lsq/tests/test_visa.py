import sys
import types
import unittest
from unittest.mock import patch

from lsq.connections.visa import VisaConnection


class FakeResource:
    def __init__(self):
        self.timeout = None
        self.read_termination = None
        self.write_termination = None
        self.writes = []

    def write(self, value):
        self.writes.append(value)
        return len(value)

    def query(self, value):
        self.writes.append(value)
        return "RIGOL TECHNOLOGIES,DG1022Z,SN,FW\n"

    def read_raw(self):
        self.read_termination_during_read = self.read_termination
        return b"\x89PNG\r\n\x1a\nimage-data"

    def close(self):
        pass


class FakeManager:
    def __init__(self, resource):
        self.resource = resource

    def open_resource(self, _):
        return self.resource

    def list_resources(self):
        return ("USB0::1::2::SN::INSTR",)


class VisaConnectionTests(unittest.TestCase):
    def test_open_configures_resource_and_query(self):
        resource = FakeResource()
        fake_pyvisa = types.SimpleNamespace(ResourceManager=lambda _backend="": FakeManager(resource))
        connection = VisaConnection("dg1022", {"read_timeout": 3, "read_termination": "\n", "write_termination": "\n"}, "USB0::1::2::SN::INSTR")
        with patch.dict(sys.modules, {"pyvisa": fake_pyvisa}):
            connection.open()
            self.assertEqual(connection.query("*IDN?"), "RIGOL TECHNOLOGIES,DG1022Z,SN,FW")
        self.assertEqual(resource.timeout, 3000)
        self.assertEqual(resource.writes, ["*IDN?"])

    def test_binary_query_disables_text_termination(self):
        resource = FakeResource()
        connection = VisaConnection("scope", {"read_termination": "\n"}, "USB0::1::2::SN::INSTR")
        connection.resource = resource
        connection.is_open = True
        resource.read_termination = "\n"
        self.assertEqual(connection.query_binary("HARDCOPY START"), b"\x89PNG\r\n\x1a\nimage-data")
        self.assertIsNone(resource.read_termination_during_read)
        self.assertEqual(resource.read_termination, "\n")


if __name__ == "__main__":
    unittest.main()
