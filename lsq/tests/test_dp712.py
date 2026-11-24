import unittest

from lsq.devices.dp712 import DP712


class FakeSerialConnection:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.writes = []

    def open(self):
        pass

    def close(self):
        pass

    def flush(self):
        pass

    def write(self, data):
        self.writes.append(data)

    def read_until(self, _terminator):
        return self.responses.pop(0).encode() + b"\n"


class DP712Tests(unittest.TestCase):
    def test_profile(self):
        self.assertEqual(DP712.connection_defaults["baud"], 9600)
        self.assertEqual(DP712.connection_defaults["data_bits"], 8)
        self.assertEqual(DP712.connection_defaults["parity"], "none")
        self.assertEqual(DP712.connection_defaults["stop_bits"], 1)
        self.assertNotIn("identify_preamble", DP712.identification)
        self.assertEqual(DP712.identification["identify_contains"], "DP712")

    def test_identification_and_measurements(self):
        connection = FakeSerialConnection(["RIGOL TECHNOLOGIES,DP712,DP712123,00.01", "12.000,0.500,6.000"])
        driver = DP712(connection)
        self.assertIn("DP712", driver.identify())
        self.assertEqual(driver.get_measurements(), {"voltage": 12.0, "current": 0.5, "power": 6.0})
        self.assertEqual(connection.writes, [b"*IDN?\n", b"MEAS:ALL? CH1\n"])

    def test_controls(self):
        connection = FakeSerialConnection(["12.000", "0.500", "ON"])
        driver = DP712(connection)
        driver.set_voltage(12)
        driver.set_current(0.5)
        self.assertEqual(driver.get_voltage(), 12.0)
        self.assertEqual(driver.get_current(), 0.5)
        driver.set_output(True)
        self.assertEqual(driver.get_output(), "ON")
        self.assertEqual(connection.writes, [b"SOUR1:VOLT 12.0\n", b"SOUR1:CURR 0.5\n", b"SOUR1:VOLT?\n", b"SOUR1:CURR?\n", b"OUTP CH1,ON\n", b"OUTP? CH1\n"])

    def test_limits(self):
        driver = DP712(FakeSerialConnection())
        with self.assertRaises(ValueError):
            driver.set_voltage(53.1)
        with self.assertRaises(ValueError):
            driver.set_current(3.21)
        with self.assertRaises(ValueError):
            driver.apply(voltage=54)
        with self.assertRaises(ValueError):
            driver.set_ovp_level(54)
        with self.assertRaises(ValueError):
            driver.set_ocp_level(3.21)

    def test_catalog_source_commands_use_dp712_channel_header(self):
        connection = FakeSerialConnection(["1"])
        driver = DP712(connection)
        driver.set_sour1_curr_prot(1)
        driver.get_sour1_curr_prot()
        self.assertEqual(connection.writes, [b"SOUR1:CURR:PROT 1\n", b"SOUR1:CURR:PROT?\n"])

    def test_startup_does_not_lock_front_panel(self):
        connection = FakeSerialConnection()
        connection.config = {"command_delay": 0}
        driver = DP712(connection)
        driver.startup()
        self.assertEqual(connection.writes, [])

    def test_explicit_local_command(self):
        connection = FakeSerialConnection()
        connection.config = {"command_delay": 0}
        DP712(connection).set_local()
        self.assertEqual(connection.writes, [b"SYST:LOC\n"])

    def test_shutdown_releases_front_panel(self):
        connection = FakeSerialConnection()
        connection.config = {"command_delay": 0}
        DP712(connection).shutdown()
        self.assertEqual(connection.writes, [b"SYST:LOC\n"])


if __name__ == "__main__":
    unittest.main()
