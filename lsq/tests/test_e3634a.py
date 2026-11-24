import unittest

from lsq.devices.e3634a import E3634A


class FakeConnection:
    def __init__(self, responses=None):
        self.config = {}
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

    def read_until(self, _):
        return (self.responses.pop(0) + "\n").encode()


class E3634ATests(unittest.TestCase):
    def test_connection_profile(self):
        self.assertEqual(E3634A.connection_defaults["data_bits"], 8)
        self.assertEqual(E3634A.connection_defaults["parity"], "none")
        self.assertEqual(E3634A.connection_defaults["stop_bits"], 2)
        self.assertTrue(E3634A.connection_defaults["dsrdtr"])
        self.assertEqual(E3634A.identification["identify_preamble"], ["SYST:REM"])

    def test_manual_command_catalog(self):
        commands = {item["command"] for item in E3634A.catalog["commands"]}
        self.assertGreaterEqual(len(commands), 55)
        for command in {"DISP", "APPL", "CAL:COUN", "SOUR:VOLT:PROT:TRIP", "STAT:QUES:ENAB", "*ESE", "*STB", "SYST:RWLOCK", "CTRL-C"}:
            self.assertIn(command, commands)
        self.assertTrue(hasattr(E3634A, "get_sour_volt_prot_trip"))
        self.assertTrue(hasattr(E3634A, "set_cal_sec_code"))

    def test_startup_and_shutdown(self):
        connection = FakeConnection(["HEWLETT-PACKARD,E3634A,0,1.0-1.0-1.0"])
        result = E3634A(connection).startup()
        self.assertIn("E3634A", result)
        self.assertEqual(connection.writes, [b"SYST:REM\n", b"*CLS\n", b"OUTP OFF\n", b"*IDN?\n"])

    def test_setters_and_getters(self):
        connection = FakeConnection(["25V", "12.5", "2.0", "12.4", "1.9", "OFF"])
        driver = E3634A(connection)
        driver.set_voltage(12.5)
        driver.set_current(2)
        self.assertEqual(driver.get_voltage_range(), "25V")
        self.assertEqual(driver.get_voltage(), 12.5)
        self.assertEqual(driver.get_current(), 2.0)
        self.assertEqual(driver.get_measured_voltage(), 12.4)
        self.assertEqual(driver.get_measured_current(), 1.9)
        self.assertEqual(driver.get_output(), "OFF")
        self.assertEqual(connection.writes[:2], [b"VOLT 12.5\n", b"CURR 2.0\n"])

    def test_error_queue(self):
        connection = FakeConnection(['-102,"Syntax error"', '+0,"No error"'])
        self.assertEqual(E3634A(connection).get_errors(), ['-102,"Syntax error"', '+0,"No error"'])

    def test_extended_controls(self):
        connection = FakeConnection(["1996.0", "0", "BUS", "0.1"])
        driver = E3634A(connection)
        driver.set_display(False)
        driver.beep()
        driver.set_trigger_source("immediate")
        self.assertEqual(driver.get_scpi_version(), "1996.0")
        self.assertEqual(driver.get_standard_event_status(), "0")
        self.assertEqual(driver.get_trigger_source(), "BUS")
        self.assertEqual(driver.get_trigger_delay(), 0.1)
        self.assertEqual(connection.writes[:3], [b"DISP OFF\n", b"SYST:BEEP\n", b"TRIG:SOUR IMM\n"])


if __name__ == "__main__":
    unittest.main()
