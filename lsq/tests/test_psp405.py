import unittest
from unittest.mock import patch

from lsq.devices.psp405 import PSP405


class FakeConnection:
    def __init__(self, response):
        self.response = response
        self.writes = []
        self.config = {"command_delay": 0}

    def open(self):
        pass

    def flush(self):
        pass

    def write(self, data):
        self.writes.append(data)

    def read_until(self, _):
        return self.response.encode()


class PSP405Tests(unittest.TestCase):
    def test_status(self):
        connection = FakeConnection("V20.00A2.500W050.0U40I5.00P200F101100\r\n")
        result = PSP405(connection).status()
        self.assertEqual(result["voltage"], 20.0)
        self.assertTrue(result["relay_on"])
        self.assertFalse(result["overtemperature"])
        self.assertEqual(connection.writes, [b"L\r"])

    def test_set_voltage_format(self):
        connection = FakeConnection("OK\r\n")
        connection.config["command_delay"] = 0.5
        with patch("lsq.devices.psp405.time.sleep") as sleep:
            PSP405(connection).set_voltage(10.5)
        sleep.assert_called_once_with(0.5)
        self.assertEqual(connection.writes, [b"SV 10.50\r"])

    def test_all_control_commands(self):
        connection = FakeConnection("OK\r\n")
        driver = PSP405(connection)
        commands = [(driver.set_power_limit, (85,), b"SP 085\r"), (driver.increase_voltage, (), b"SV+\r"), (driver.decrease_voltage, (), b"SV-\r"), (driver.increase_voltage_limit, (), b"SU+\r"), (driver.decrease_voltage_limit, (), b"SU-\r"), (driver.increase_current_limit, (), b"SI+\r"), (driver.decrease_current_limit, (), b"SI-\r"), (driver.increase_power_limit, (), b"SP+\r"), (driver.decrease_power_limit, (), b"SP-\r"), (driver.set_max_voltage_limit, (), b"SUM\r"), (driver.set_max_current_limit, (), b"SIM\r"), (driver.set_max_power_limit, (), b"SPM\r"), (driver.set_fine_step, (), b"KF\r"), (driver.set_coarse_step, (), b"KN\r"), (driver.toggle_output, (), b"KO\r"), (driver.output_on, (), b"KOE\r"), (driver.output_off, (), b"KOD\r"), (driver.save_settings, (), b"EEP\r"), (driver.increase_positive_offset, (), b"SB+\r"), (driver.decrease_positive_offset, (), b"SB-\r"), (driver.increase_negative_offset, (), b"SD+\r"), (driver.decrease_negative_offset, (), b"SD-\r")]
        for method, arguments, expected in commands:
            method(*arguments)
            self.assertEqual(connection.writes[-1], expected)

    def test_get_parsing(self):
        connection = FakeConnection("Q110000\r\n")
        result = PSP405(connection).get_offset_status()
        self.assertTrue(result["negative_enabled"])
        self.assertTrue(result["positive_enabled"])
