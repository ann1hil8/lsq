import json
import tempfile
import unittest
from pathlib import Path

from lsq.dsl import parse_script
from lsq.runtime import Runtime


class OutputTests(unittest.TestCase):
    def test_save_waveform_formats(self):
        with tempfile.TemporaryDirectory() as directory:
            script = parse_script('''
set waveform = ignored
''')
            runtime = Runtime(script, output_dir=directory)
            runtime.variables["waveform"] = {"raw": b"abc", "time": [0.0, 1.0], "voltage": [2.0, 3.0]}
            runtime._save(parse_script('save waveform file=waveform.json format=json')[0])
            runtime._save(parse_script('save waveform file=waveform.csv format=csv')[0])
            saved = json.loads(Path(directory, "waveform.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["raw"]["encoding"], "base64")
            self.assertEqual(Path(directory, "waveform.csv").read_text(encoding="utf-8").splitlines()[1], "0.0,2.0")


if __name__ == "__main__":
    unittest.main()
