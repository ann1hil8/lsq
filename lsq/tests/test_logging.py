import unittest
from contextlib import redirect_stdout
from io import StringIO

from lsq.logging_utils import Logger


class LoggingTests(unittest.TestCase):
    def capture(self, logger, message, level):
        output = StringIO()
        with redirect_stdout(output):
            logger(message, level)
        return output.getvalue()

    def test_levels(self):
        logger = Logger("normal")
        self.assertEqual(self.capture(logger, "bytes", "trace"), "")
        self.assertEqual(self.capture(logger, "message", "verbose"), "")
        self.assertEqual(self.capture(logger, "event", "normal"), "event\n")
        logger.set_level("trace")
        self.assertEqual(self.capture(logger, "bytes", "trace"), "bytes\n")
