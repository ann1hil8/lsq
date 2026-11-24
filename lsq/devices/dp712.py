import json
import re
import time
from pathlib import Path

from .generic import GenericDevice


class DP712(GenericDevice):
    """RIGOL DP712 single-output RS-232 SCPI driver."""

    connection_defaults = {"type": "serial", "baud": 9600, "data_bits": 8, "parity": "none", "stop_bits": 1, "dtr": True, "dsrdtr": False, "rtscts": False, "xonxoff": False, "read_timeout": 3, "write_timeout": 3}
    identification = {"identify_command": "*IDN?", "identify_terminator": "lf", "identify_ends": "lf", "identify_contains": "DP712"}
    catalog = json.loads((Path(__file__).parent / "catalogs" / "dp712.json").read_text(encoding="utf-8"))

    def _write(self, command):
        self.connection.open()
        self.connection.flush()
        self.connection.write(str(command).encode("ascii") + b"\n")

    def _query(self, command):
        self.connection.open()
        self.connection.flush()
        self.connection.write(str(command).encode("ascii") + b"\n")
        return self.connection.read_until(b"\n").decode("ascii", errors="replace").rstrip("\r\n")

    @staticmethod
    def _bool(value):
        value = str(value).strip().upper()
        if value in {"1", "ON", "TRUE"}:
            return True
        if value in {"0", "OFF", "FALSE"}:
            return False
        raise ValueError(f"invalid boolean value: {value}")

    @staticmethod
    def _number(value, name):
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid {name} value: {value!r}") from exc

    @staticmethod
    def _channel(channel="CH1"):
        value = str(channel).upper()
        if value not in {"CH1", "P50V"}:
            raise ValueError("DP712 channel must be CH1 or P50V")
        return value

    @staticmethod
    def _source(channel="CH1"):
        DP712._channel(channel)
        return "SOUR1"

    def startup(self):
        return None

    def recover(self):
        self.connection.close()
        self.connection.open()
        return self.startup()

    def shutdown(self):
        self._write("SYST:LOC")
        time.sleep(float(getattr(self.connection, "config", {}).get("command_delay", 0.1)))

    def identify(self):
        return self._query("*IDN?")

    def reset(self):
        self._write("*RST")

    def get_error(self):
        return self._query("SYST:ERR?")

    def get_errors(self):
        errors = []
        while True:
            error = self.get_error()
            errors.append(error)
            if re.match(r"\+?0\s*,", error) or error.startswith("0,"):
                return errors
            if len(errors) >= 20:
                raise RuntimeError("DP712 error queue did not terminate after 20 entries")

    def set_output(self, enabled, channel="CH1"):
        self._write(f"OUTP {self._channel(channel)},{'ON' if self._bool(enabled) else 'OFF'}")

    def get_output(self, channel="CH1"):
        return self._query(f"OUTP? {self._channel(channel)}").strip().upper()

    def set_voltage(self, value, channel="CH1"):
        value = self._number(value, "voltage")
        if not 0 <= value <= 53:
            raise ValueError("DP712 voltage must be between 0 and 53 V")
        self._write(f"{self._source(channel)}:VOLT {value}")

    def get_voltage(self, channel="CH1"):
        return self._number(self._query(f"{self._source(channel)}:VOLT?"), "voltage")

    def set_current(self, value, channel="CH1"):
        value = self._number(value, "current")
        if not 0 <= value <= 3.2:
            raise ValueError("DP712 current must be between 0 and 3.2 A")
        self._write(f"{self._source(channel)}:CURR {value}")

    def get_current(self, channel="CH1"):
        return self._number(self._query(f"{self._source(channel)}:CURR?"), "current")

    def apply(self, voltage=None, current=None, channel="CH1"):
        if voltage is not None:
            voltage = self._number(voltage, "voltage")
            if not 0 <= voltage <= 53:
                raise ValueError("DP712 voltage must be between 0 and 53 V")
        if current is not None:
            current = self._number(current, "current")
            if not 0 <= current <= 3.2:
                raise ValueError("DP712 current must be between 0 and 3.2 A")
        values = [self._channel(channel)]
        if voltage is not None:
            values.append(str(voltage))
        if current is not None:
            values.append(str(current))
        if len(values) == 1:
            raise ValueError("apply requires voltage and/or current")
        self._write("APPL " + ",".join(values))

    def get_application(self, channel="CH1", item=None):
        command = f"APPL? {self._channel(channel)}"
        if item:
            command += f",{str(item).upper()}"
        return self._query(command)

    def get_measured_voltage(self, channel="CH1"):
        return self._number(self._query(f"MEAS:VOLT? {self._channel(channel)}"), "measured voltage")

    def get_measured_current(self, channel="CH1"):
        return self._number(self._query(f"MEAS:CURR? {self._channel(channel)}"), "measured current")

    def get_measured_power(self, channel="CH1"):
        return self._number(self._query(f"MEAS:POW? {self._channel(channel)}"), "measured power")

    def get_measurements(self, channel="CH1"):
        values = self._query(f"MEAS:ALL? {self._channel(channel)}").split(",")
        if len(values) != 3:
            raise ValueError(f"unexpected DP712 measurement response: {values!r}")
        return {"voltage": self._number(values[0], "measured voltage"), "current": self._number(values[1], "measured current"), "power": self._number(values[2], "measured power")}

    def get_mode(self, channel="CH1"):
        return self._query(f"OUTP:MODE? {self._channel(channel)}")

    def get_cvcc(self, channel="CH1"):
        return self._query(f"OUTP:CVCC? {self._channel(channel)}")

    def set_ovp(self, enabled, channel="CH1"):
        self._write(f"OUTP:OVP {self._channel(channel)},{'ON' if self._bool(enabled) else 'OFF'}")

    def get_ovp(self, channel="CH1"):
        return self._query(f"OUTP:OVP? {self._channel(channel)}")

    def set_ovp_level(self, value, channel="CH1"):
        value = self._number(value, "OVP level")
        if not 0 <= value <= 53:
            raise ValueError("DP712 OVP level must be between 0 and 53 V")
        self._write(f"OUTP:OVP:VAL {self._channel(channel)},{value}")

    def get_ovp_level(self, channel="CH1"):
        return self._number(self._query(f"OUTP:OVP:VAL? {self._channel(channel)}"), "OVP level")

    def get_ovp_alarm(self, channel="CH1"):
        return self._query(f"OUTP:OVP:ALAR? {self._channel(channel)}")

    def get_ovp_questionable(self, channel="CH1"):
        return self._query(f"OUTP:OVP:QUES? {self._channel(channel)}")

    def clear_ovp(self, channel="CH1"):
        self._write(f"OUTP:OVP:CLEAR {self._channel(channel)}")

    def set_ocp(self, enabled, channel="CH1"):
        self._write(f"OUTP:OCP {self._channel(channel)},{'ON' if self._bool(enabled) else 'OFF'}")

    def get_ocp(self, channel="CH1"):
        return self._query(f"OUTP:OCP? {self._channel(channel)}")

    def set_ocp_level(self, value, channel="CH1"):
        value = self._number(value, "OCP level")
        if not 0 <= value <= 3.2:
            raise ValueError("DP712 OCP level must be between 0 and 3.2 A")
        self._write(f"OUTP:OCP:VAL {self._channel(channel)},{value}")

    def get_ocp_level(self, channel="CH1"):
        return self._number(self._query(f"OUTP:OCP:VAL? {self._channel(channel)}"), "OCP level")

    def get_ocp_alarm(self, channel="CH1"):
        return self._query(f"OUTP:OCP:ALAR? {self._channel(channel)}")

    def get_ocp_questionable(self, channel="CH1"):
        return self._query(f"OUTP:OCP:QUES? {self._channel(channel)}")

    def clear_ocp(self, channel="CH1"):
        self._write(f"OUTP:OCP:CLEAR {self._channel(channel)}")

    def set_display(self, enabled):
        self._write(f"DISP:WIND:STAT {'ON' if self._bool(enabled) else 'OFF'}")

    def get_display(self):
        return self._query("DISP:WIND:STAT?")

    def beep(self):
        self._write("SYST:BEEP:IMM")

    def set_beeper(self, enabled):
        self._write(f"SYST:BEEP {'ON' if self._bool(enabled) else 'OFF'}")

    def get_beeper(self):
        return self._query("SYST:BEEP?")

    def set_brightness(self, value):
        self._write(f"SYST:BRIG {value}")

    def get_brightness(self):
        return self._number(self._query("SYST:BRIG?"), "brightness")

    def get_fan(self):
        return self._query("SYST:FAN?")

    def set_remote_lock(self, enabled):
        self._write(f"SYST:RWLOCK {'ON' if self._bool(enabled) else 'OFF'}")

    def set_local(self):
        self._write("SYST:LOC")
        time.sleep(float(getattr(self.connection, "config", {}).get("command_delay", 0.1)))

    def set_remote(self):
        self._write("SYST:REM")

    def get_version(self):
        return self._query("SYST:VERS?")

    def set(self, command, *values):
        suffix = " " + ",".join(map(str, values)) if values else ""
        self._write(str(command) + suffix)

    def get(self, command, *values):
        command = str(command)
        if not command.endswith("?"):
            command += "?"
        if values:
            command += " " + ",".join(map(str, values))
        return self._query(command)


def _method_name(command):
    return re.sub(r"[^A-Za-z0-9]+", "_", command.replace("<n>", "n")).strip("_").lower()


def _install_catalog_methods():
    for item in DP712.catalog["commands"]:
        name = _method_name(item["command"])
        if not name:
            continue
        if item["access"] in {"set", "set/get"} and not hasattr(DP712, f"set_{name}"):
            setattr(DP712, f"set_{name}", lambda self, *values, _command=item["command"]: self.set(_command, *values))
        if item["access"] in {"get", "set/get"} and not hasattr(DP712, f"get_{name}"):
            setattr(DP712, f"get_{name}", lambda self, *values, _command=item["command"]: self.get(_command, *values))


_install_catalog_methods()
