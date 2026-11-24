import unittest

from lsq.devices.dg1022z import DG1022Z


class FakeVisaConnection:
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.writes = []

    def open(self):
        pass

    def write(self, command):
        self.writes.append(command)

    def query(self, command):
        self.writes.append(command)
        return self.responses.get(command, "")

    def close(self):
        pass


class DG1022ZTests(unittest.TestCase):
    def test_identification(self):
        connection = FakeVisaConnection({"*IDN?": "RIGOL TECHNOLOGIES,DG1022Z,DG1,00.01\n"})
        self.assertIn("DG1022Z", DG1022Z(connection).identify())
        self.assertEqual(connection.writes, ["*IDN?"])

    def test_apply_and_channel_two(self):
        connection = FakeVisaConnection()
        driver = DG1022Z(connection)
        driver.apply("sine", 1000, 2.0, 0.1)
        driver.apply("square", 2000, 1.0, 0, channel=2)
        self.assertEqual(connection.writes, ["SOUR1:APPL:SIN 1000,2.0,0.1", "SOUR2:APPL:SQU 2000,1.0,0"])

    def test_typed_getters_and_controls(self):
        connection = FakeVisaConnection({"SOUR2:FREQ?": "1000\n", "SOUR2:VOLT:OFFS?": "-0.25\n"})
        driver = DG1022Z(connection)
        self.assertEqual(driver.get_frequency(channel=2), 1000.0)
        self.assertEqual(driver.get_offset(channel=2), -0.25)
        driver.set_output(True, channel=2)
        driver.set_burst_state(False, channel=2)
        self.assertEqual(connection.writes, ["SOUR2:FREQ?", "SOUR2:VOLT:OFFS?", "OUTP2 ON", "SOUR2:BURS:STAT OFF"])

    def test_boolean_strings_are_parsed(self):
        connection = FakeVisaConnection()
        DG1022Z(connection).set_output("false")
        self.assertEqual(connection.writes, ["OUTP1 OFF"])

    def test_waveform_data_limits(self):
        connection = FakeVisaConnection()
        driver = DG1022Z(connection)
        driver.set_waveform([-1, 0, 1])
        driver.set_dac_waveform([0, 8192, 16383])
        self.assertEqual(connection.writes, ["SOUR1:TRAC:DATA VOLATILE,-1.0,0.0,1.0", "SOUR1:TRAC:DATA:DAC VOLATILE,0,8192,16383"])
        with self.assertRaises(ValueError):
            driver.set_dac_waveform([16384])


if __name__ == "__main__":
    unittest.main()
