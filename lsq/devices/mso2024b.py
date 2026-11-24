import json
import re
import struct
from pathlib import Path

from .generic import GenericDevice


class MSO2024B(GenericDevice):
    """Tektronix MSO2024B USB-VISA driver."""

    connection_defaults = {"type": "visa", "resource_prefix": "USB", "read_timeout": 10, "read_termination": "\n", "write_termination": "\n"}
    identification = {"identify_command": "*IDN?", "identify_contains": "MSO2024B"}
    catalog = json.loads((Path(__file__).parent / "catalogs" / "mso2024b.json").read_text(encoding="utf-8"))

    @staticmethod
    def _channel(channel):
        channel = int(channel)
        if channel not in range(1, 5):
            raise ValueError("MSO2024B analog channel must be 1 through 4")
        return channel

    @staticmethod
    def _measurement(measurement):
        measurement = int(measurement)
        if measurement not in range(1, 5):
            raise ValueError("MSO2024B measurement must be 1 through 4")
        return measurement

    @staticmethod
    def _bool(value):
        value = str(value).upper()
        if value in {"1", "ON", "TRUE"}:
            return True
        if value in {"0", "OFF", "FALSE"}:
            return False
        raise ValueError(f"invalid boolean value: {value}")

    def _write(self, command):
        self.connection.open()
        self.connection.write(str(command))

    def _query(self, command):
        self.connection.open()
        return self.connection.query(str(command)).strip()

    def identify(self):
        return self._query("*IDN?")

    def clear_status(self):
        self._write("*CLS")

    def reset(self):
        self._write("*RST")

    def get_error(self):
        return self._query("EVENT?")

    def set_channel(self, channel, enabled):
        self._write(f"SEL:CH{self._channel(channel)} {'ON' if self._bool(enabled) else 'OFF'}")

    def get_channel(self, channel):
        return self._query(f"SEL:CH{self._channel(channel)}?")

    def set_channel_scale(self, channel, value):
        self._write(f"CH{self._channel(channel)}:SCALE {value}")

    def get_channel_scale(self, channel):
        return float(self._query(f"CH{self._channel(channel)}:SCALE?"))

    def set_channel_position(self, channel, value):
        self._write(f"CH{self._channel(channel)}:POSITION {value}")

    def get_channel_position(self, channel):
        return float(self._query(f"CH{self._channel(channel)}:POSITION?"))

    def set_channel_coupling(self, channel, value):
        value = str(value).upper()
        if value not in {"AC", "DC", "GND"}:
            raise ValueError("channel coupling must be AC, DC, or GND")
        self._write(f"CH{self._channel(channel)}:COUPLING {value}")

    def get_channel_coupling(self, channel):
        return self._query(f"CH{self._channel(channel)}:COUPLING?")

    def set_channel_termination(self, channel, value):
        self._write(f"CH{self._channel(channel)}:TERMINATION {value}")

    def get_channel_termination(self, channel):
        return self._query(f"CH{self._channel(channel)}:TERMINATION?")

    def set_channel_invert(self, channel, enabled):
        self._write(f"CH{self._channel(channel)}:INVERT {'ON' if self._bool(enabled) else 'OFF'}")

    def get_channel_invert(self, channel):
        return self._query(f"CH{self._channel(channel)}:INVERT?")

    def set_acquisition_mode(self, mode):
        self._write(f"ACQ:MODE {str(mode).upper()}")

    def get_acquisition_mode(self):
        return self._query("ACQ:MODE?")

    def set_acquisition_state(self, running):
        self._write(f"ACQ:STATE {'RUN' if self._bool(running) else 'STOP'}")

    def get_acquisition_state(self):
        return self._query("ACQ:STATE?")

    def set_stop_after(self, mode):
        self._write(f"ACQ:STOPAFTER {str(mode).upper()}")

    def get_stop_after(self):
        return self._query("ACQ:STOPAFTER?")

    def set_averages(self, count):
        count = int(count)
        if count < 2:
            raise ValueError("average count must be at least 2")
        self._write(f"ACQ:NUMAVG {count}")

    def get_averages(self):
        return int(float(self._query("ACQ:NUMAVG?")))

    def set_horizontal_scale(self, value):
        self._write(f"HOR:MAIN:SCALE {value}")

    def get_horizontal_scale(self):
        return float(self._query("HOR:MAIN:SCALE?"))

    def set_horizontal_position(self, value):
        self._write(f"HOR:MAIN:POSITION {value}")

    def get_horizontal_position(self):
        return float(self._query("HOR:MAIN:POSITION?"))

    def set_trigger_source(self, source):
        self._write(f"TRIG:A:EDGE:SOURCE {str(source).upper()}")

    def get_trigger_source(self):
        return self._query("TRIG:A:EDGE:SOURCE?")

    def set_trigger_slope(self, slope):
        self._write(f"TRIG:A:EDGE:SLOPE {str(slope).upper()}")

    def get_trigger_slope(self):
        return self._query("TRIG:A:EDGE:SLOPE?")

    def set_trigger_level(self, value, source="CH1"):
        self._write(f"TRIG:A:LEVEL:{str(source).upper()} {value}")

    def get_trigger_level(self, source="CH1"):
        return float(self._query(f"TRIG:A:LEVEL:{str(source).upper()}?"))

    def get_trigger_state(self):
        return self._query("TRIG:STATE?")

    def force_trigger(self):
        self._write("TRIG:FORCE")

    def autoset(self):
        self._write("AUTOSET EXECUTE")

    def set_measurement(self, measurement, measurement_type, source):
        measurement = self._measurement(measurement)
        self._write(f"MEASU:MEAS{measurement}:TYPE {str(measurement_type).upper()}")
        self._write(f"MEASU:MEAS{measurement}:SOURCE1 {str(source).upper()}")

    def get_measurement(self, measurement):
        measurement = self._measurement(measurement)
        return float(self._query(f"MEASU:MEAS{measurement}:VAL?"))

    def set_immediate_measurement(self, measurement_type, source):
        self._write(f"MEASU:IMMED:TYPE {str(measurement_type).upper()}")
        self._write(f"MEASU:IMMED:SOURCE1 {str(source).upper()}")

    def get_immediate_measurement(self):
        return float(self._query("MEASU:IMMED:VALUE?"))

    def configure_waveform(self, source="CH1", start=1, stop=10000, encoding="RIB", width=1):
        self._write(f"DAT:SOU {str(source).upper()}")
        self._write(f"DAT:STAR {int(start)}")
        self._write(f"DAT:STOP {int(stop)}")
        self._write(f"DAT:ENC {str(encoding).upper()}")
        self._write(f"DAT:WID {int(width)}")

    def get_waveform_preamble(self):
        fields = {"format": "BN_FMT", "type": "BYT_NR", "points": "NR_PT", "x_increment": "XINCR", "x_zero": "XZERO", "point_offset": "PT_OFF", "y_multiplier": "YMULT", "y_zero": "YZERO", "y_offset": "YOFF", "x_unit": "XUNIT", "y_unit": "YUNIT", "byte_order": "BYT_OR"}
        result = {}
        for key, field in fields.items():
            value = self._query(f"WFMO:{field}?")
            result[key] = float(value) if key in {"points", "x_increment", "x_zero", "point_offset", "y_multiplier", "y_zero", "y_offset"} else value
        return result

    def _query_binary(self, command):
        self.connection.open()
        return self.connection.query_binary(command)

    @staticmethod
    def _block(raw):
        marker = raw.find(b"#")
        if marker < 0:
            raise ValueError("waveform response is not an IEEE 488.2 block")
        digits = int(raw[marker + 1:marker + 2])
        if digits == 0:
            return raw[marker + 2:]
        size_start = marker + 2
        size = int(raw[size_start:size_start + digits])
        data_start = size_start + digits
        if len(raw) < data_start + size:
            raise ValueError(f"truncated IEEE 488.2 block: expected {size} bytes, got {len(raw) - data_start}")
        return raw[data_start:data_start + size]

    @staticmethod
    def _image_data(raw):
        signatures = (b"\x89PNG\r\n\x1a\n", b"BM", b"II*\x00", b"MM\x00*")
        for signature in signatures:
            marker = raw.find(signature)
            if marker >= 0:
                return raw[marker:]
        if b"#" in raw:
            return MSO2024B._block(raw)
        raise ValueError(f"screenshot response is neither an IEEE 488.2 block nor a recognized image; received {raw[:32]!r}")

    def get_waveform(self):
        preamble = self.get_waveform_preamble()
        raw = self._block(self._query_binary("CURV?"))
        width = int(preamble["type"])
        encoding = self._query("DAT:ENC?").upper()
        if encoding.startswith("ASC"):
            samples = [float(item) for item in raw.decode().strip().split(",") if item]
        else:
            fmt = ">" if encoding.endswith("IB") else "<"
            code = "b" if width == 1 else "h"
            samples = list(struct.unpack(fmt + code * (len(raw) // width), raw))
        voltages = [(sample - preamble["y_offset"]) * preamble["y_multiplier"] + preamble["y_zero"] for sample in samples]
        times = [(index - preamble["point_offset"]) * preamble["x_increment"] + preamble["x_zero"] for index in range(len(voltages))]
        return {"preamble": preamble, "raw": raw, "time": times, "voltage": voltages}

    def get_waveform_summary(self, channel="CH1", start=1, stop=1000, encoding="RIB", width=1):
        self.configure_waveform(channel, start, stop, encoding, width)
        waveform = self.get_waveform()
        if not waveform["voltage"]:
            raise ValueError("waveform contains no points")
        return {"source": str(channel).upper(), "points": len(waveform["voltage"]), "time_start": waveform["time"][0], "time_end": waveform["time"][-1], "voltage_min": min(waveform["voltage"]), "voltage_max": max(waveform["voltage"]), "sample_interval": waveform["preamble"]["x_increment"]}

    def save_screenshot(self, file):
        path = Path(file)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._write("SAVE:IMAGE:FILEFORMAT PNG")
        path.write_bytes(self._image_data(self._query_binary("HARDCOPY START")))
        return str(path)

    @staticmethod
    def _resolve(command, channel=1):
        cmd = str(command).replace("<x>", str(int(channel)))
        return cmd.replace("[", "").replace("]", "")

    def set(self, command, *values, channel=1):
        cmd = self._resolve(command, channel=channel)
        suffix = " " + ",".join(map(str, values)) if values else ""
        self._write(cmd + suffix)

    def get(self, command, *values, channel=1):
        cmd = self._resolve(command, channel=channel)
        if not cmd.endswith("?"):
            cmd += "?"
        if values:
            cmd += " " + ",".join(map(str, values))
        return self._query(cmd)

    def close(self):
        if self.connection:
            self.connection.close()
        self.opened = False


def _method_name(command):
    return re.sub(r"[^A-Za-z0-9]+", "_", command.replace("<x>", "x")).strip("_").lower()


def _install_catalog_methods():
    for item in MSO2024B.catalog["commands"]:
        if any(ch in item["command"] for ch in (" ", "{", "}", "|")):
            continue
        name = _method_name(item["command"])
        if not name:
            continue
        if item["access"] in {"set", "set/get"} and not hasattr(MSO2024B, f"set_{name}"):
            setattr(MSO2024B, f"set_{name}", lambda self, *values, channel=1, _command=item["command"]: self.set(_command, *values, channel=channel))
        if item["access"] in {"get", "set/get"} and not hasattr(MSO2024B, f"get_{name}"):
            setattr(MSO2024B, f"get_{name}", lambda self, *values, channel=1, _command=item["command"]: self.get(_command, *values, channel=channel))


_install_catalog_methods()
