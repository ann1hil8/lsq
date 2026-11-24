import unittest

from lsq.dsl import interpolate, parse_script
from lsq.runtime import ExpressionEvaluator, Runtime


class DslTests(unittest.TestCase):
    def test_parse_and_interpolate(self):
        statements = parse_script('send supply "VOLT ${value}" terminate=lf')
        self.assertEqual(statements[0].command, "send")
        self.assertEqual(interpolate(statements[0].args[1], {"value": 12.5}), "VOLT 12.5")

    def test_expression(self):
        evaluator = ExpressionEvaluator({"x": 3})
        self.assertTrue(evaluator.evaluate('x < 4 and contains("READY", "EA")'))
        self.assertEqual(evaluator.evaluate("x * 2"), 6)

    def test_device_driver_supplies_connection_profile(self):
        runtime = Runtime(parse_script("device psp405 driver=psp405"))
        runtime.run()
        profile = runtime.connections.profiles["psp405"]
        self.assertEqual(profile["baud"], 2400)
        self.assertEqual(profile["identify_command"], "L")

    def test_dg1022_driver_supplies_usb_visa_profile(self):
        runtime = Runtime(parse_script("device dg1022 driver=dg1022z"))
        runtime.run()
        profile = runtime.connections.profiles["dg1022"]
        self.assertEqual(profile["type"], "visa")
        self.assertEqual(profile["resource_prefix"], "USB")
        self.assertEqual(profile["identify_command"], "*IDN?")


if __name__ == "__main__":
    unittest.main()
