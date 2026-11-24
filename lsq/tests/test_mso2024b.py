import unittest

from lsq.devices.mso2024b import MSO2024B


class FakeConnection:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.writes = []

    def open(self):
        pass

    def close(self):
        pass

    def write(self, data):
        self.writes.append(data)

    def query(self, command):
        self.writes.append(command)
        return self.responses.pop(0)

    def query_binary(self, command):
        self.writes.append(command)
        return self.responses.pop(0)


class MSO2024BTests(unittest.TestCase):
    def test_profile(self):
        self.assertEqual(MSO2024B.connection_defaults["type"], "visa")
        self.assertEqual(MSO2024B.identification["identify_contains"], "MSO2024B")

    def test_channel_and_trigger_controls(self):
        connection = FakeConnection(["1", "1.0", "DC", "CH1", "READY"])
        driver = MSO2024B(connection)
        driver.set_channel(1, True)
        self.assertEqual(driver.get_channel(1), "1")
        self.assertEqual(driver.get_channel_scale(1), 1.0)
        self.assertEqual(driver.get_channel_coupling(1), "DC")
        self.assertEqual(driver.get_trigger_source(), "CH1")
        self.assertEqual(driver.get_trigger_state(), "READY")

    def test_waveform_block(self):
        raw = b"#15\x01\x02\x03\x04\x05\r\n"
        connection = FakeConnection(["RI", "1", "5", "1e-6", "0", "0", "1", "0", "0", "s", "V", "MSB", raw, "RIB"])
        result = MSO2024B(connection).get_waveform()
        self.assertEqual(len(result["voltage"]), 5)
        self.assertEqual(result["voltage"][0], 1.0)

    def test_save_screenshot(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            connection = FakeConnection([b"#14PNG!"]) 
            path = MSO2024B(connection).save_screenshot(f"{directory}/scope.png")
            self.assertEqual(connection.writes, ["SAVE:IMAGE:FILEFORMAT PNG", "HARDCOPY START"])
            with open(path, "rb") as image:
                self.assertEqual(image.read(), b"PNG!")

    def test_save_screenshot_accepts_direct_png(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            png = b"\x89PNG\r\n\x1a\nimage-data"
            connection = FakeConnection([png])
            path = MSO2024B(connection).save_screenshot(f"{directory}/scope.png")
            with open(path, "rb") as image:
                self.assertEqual(image.read(), png)


if __name__ == "__main__":
    unittest.main()
