import json
import re
from pathlib import Path

from .generic import GenericDevice


class E3634A(GenericDevice):
    """Agilent/Keysight E3634A single-output RS-232 SCPI driver."""

    connection_defaults = {"type": "serial", "baud": 9600, "data_bits": 8, "parity": "none", "stop_bits": 2, "dtr": True, "dsrdtr": True, "rtscts": False, "xonxoff": False, "read_timeout": 3, "write_timeout": 3}
    identification = {"identify_preamble": ["SYST:REM"], "identify_preamble_terminator": "lf", "identify_command": "*IDN?", "identify_terminator": "lf", "identify_ends": "lf", "identify_contains": "E3634A"}
    catalog = json.loads((Path(__file__).parent / "catalogs" / "e3634a.json").read_text(encoding="utf-8"))

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

    def startup(self):
        """Enter remote mode, clear stale status, and leave output disabled."""
        self._write("SYST:REM")
        self._write("*CLS")
        self.set_output(False)
        return self.identify()

    def recover(self):
        """Reopen the serial link, re-enter remote mode, and clear status."""
        self.connection.close()
        self.connection.open()
        return self.startup()

    def shutdown(self):
        """Disable output and return the instrument to local control."""
        self.set_output(False)
        self._write("SYST:LOC")

    def identify(self):
        return self._query("*IDN?")

    def set_display(self, enabled):
        self._write(f"DISP {'ON' if self._bool(enabled) else 'OFF'}")

    def get_display(self):
        return self._query("DISP?")

    def set_display_text(self, text):
        text = str(text)
        if len(text) > 12:
            raise ValueError("E3634A display text is limited to 12 characters")
        self._write(f'DISP:TEXT "{text}"')

    def get_display_text(self):
        return self._query("DISP:TEXT?")

    def clear_display_text(self):
        self._write("DISP:TEXT:CLE")

    def beep(self):
        self._write("SYST:BEEP")

    def set_relay(self, enabled):
        self._write(f"OUTP:REL {'ON' if self._bool(enabled) else 'OFF'}")

    def get_relay(self):
        return self._query("OUTP:REL?")

    def get_scpi_version(self):
        return self._query("SYST:VERS?")

    def get_questionable_event(self):
        return self._query("STAT:QUES:EVEN?")

    def set_questionable_enable(self, value):
        self._write(f"STAT:QUES:ENAB {int(value)}")

    def get_questionable_enable(self):
        return self._query("STAT:QUES:ENAB?")

    def set_trigger_delay(self, value):
        self._write(f"TRIG:DEL {value}")

    def get_trigger_delay(self):
        return self._number(self._query("TRIG:DEL?"), "trigger delay")

    def set_trigger_source(self, value):
        value = str(value).upper()
        if value not in {"BUS", "IMM", "IMMEDIATE"}:
            raise ValueError("E3634A trigger source must be BUS or IMM")
        self._write(f"TRIG:SOUR {'IMM' if value == 'IMMEDIATE' else value}")

    def get_trigger_source(self):
        return self._query("TRIG:SOUR?")

    def set_voltage_step(self, value):
        self._write(f"SOUR:VOLT:STEP {value}")

    def get_voltage_step(self):
        return self._number(self._query("SOUR:VOLT:STEP?"), "voltage step")

    def set_current_step(self, value):
        self._write(f"SOUR:CURR:STEP {value}")

    def get_current_step(self):
        return self._number(self._query("SOUR:CURR:STEP?"), "current step")

    def set_triggered_voltage(self, value):
        self._write(f"SOUR:VOLT:TRIG {value}")

    def get_triggered_voltage(self):
        return self._number(self._query("SOUR:VOLT:TRIG?"), "triggered voltage")

    def set_triggered_current(self, value):
        self._write(f"SOUR:CURR:TRIG {value}")

    def get_triggered_current(self):
        return self._number(self._query("SOUR:CURR:TRIG?"), "triggered current")

    def set_application(self, voltage, current=None):
        values = [voltage] if current is None else [voltage, current]
        self._write("APPL " + ",".join(map(str, values)))

    def get_application(self):
        return self._query("APPL?")

    def get_standard_event_enable(self):
        return self._query("*ESE?")

    def set_standard_event_enable(self, value):
        self._write(f"*ESE {int(value)}")

    def get_standard_event_status(self):
        return self._query("*ESR?")

    def get_status_byte(self):
        return self._query("*STB?")

    def get_service_request_enable(self):
        return self._query("*SRE?")

    def set_service_request_enable(self, value):
        self._write(f"*SRE {int(value)}")

    def set_power_on_status_clear(self, enabled):
        self._write(f"*PSC {1 if self._bool(enabled) else 0}")

    def get_power_on_status_clear(self):
        return self._query("*PSC?")

    def trigger(self):
        self._write("*TRG")

    def wait(self):
        self._write("*WAI")

    def device_clear(self):
        self.connection.open()
        self.connection.flush()
        self.connection.write(b"\x03")

    def reset(self):
        self._write("*RST")

    def clear_status(self):
        self._write("*CLS")

    def get_error(self):
        return self._query("SYST:ERR?")

    def get_errors(self):
        errors = []
        while True:
            error = self.get_error()
            errors.append(error)
            if re.match(r"\+?0\s*,", error):
                return errors
            if len(errors) >= 20:
                raise RuntimeError("E3634A error queue did not terminate after 20 entries")

    def get_voltage(self):
        return self._number(self._query("VOLT?"), "voltage")

    def set_voltage(self, value):
        value = self._number(value, "voltage")
        if not 0 <= value <= 50:
            raise ValueError("E3634A voltage must be between 0 and 50 V")
        self._write(f"VOLT {value}")

    def get_current(self):
        return self._number(self._query("CURR?"), "current")

    def set_current(self, value):
        value = self._number(value, "current")
        if not 0 <= value <= 7:
            raise ValueError("E3634A current must be between 0 and 7 A")
        self._write(f"CURR {value}")

    def get_measured_voltage(self):
        return self._number(self._query("MEAS:VOLT?"), "measured voltage")

    def get_measured_current(self):
        return self._number(self._query("MEAS:CURR?"), "measured current")

    def get_output(self):
        return self._query("OUTP?").strip().upper()

    def set_output(self, enabled):
        self._write(f"OUTP {'ON' if self._bool(enabled) else 'OFF'}")

    def get_voltage_range(self):
        return self._query("VOLT:RANG?").strip().upper()

    def set_voltage_range(self, value):
        value = str(value).upper()
        aliases = {"25": "P25V", "25V": "P25V", "50": "P50V", "50V": "P50V", "LOW": "P25V", "HIGH": "P50V"}
        if value not in aliases:
            raise ValueError("E3634A voltage range must be 25V/P25V or 50V/P50V")
        self._write(f"VOLT:RANG {aliases[value]}")

    def get_ovp_state(self):
        return self._query("VOLT:PROT:STAT?").strip().upper()

    def set_ovp_state(self, enabled):
        self._write(f"VOLT:PROT:STAT {'ON' if self._bool(enabled) else 'OFF'}")

    def clear_ovp(self):
        self._write("VOLT:PROT:CLE")

    def get_ovp_level(self):
        return self._number(self._query("VOLT:PROT?"), "OVP level")

    def set_ovp_level(self, value):
        value = self._number(value, "OVP level")
        if not 0 <= value <= 55:
            raise ValueError("E3634A OVP level must be between 0 and 55 V")
        self._write(f"VOLT:PROT {value}")

    def get_ocp_state(self):
        return self._query("CURR:PROT:STAT?").strip().upper()

    def set_ocp_state(self, enabled):
        self._write(f"CURR:PROT:STAT {'ON' if self._bool(enabled) else 'OFF'}")

    def clear_ocp(self):
        self._write("CURR:PROT:CLE")

    def get_ocp_level(self):
        return self._number(self._query("CURR:PROT?"), "OCP level")

    def set_ocp_level(self, value):
        value = self._number(value, "OCP level")
        if not 0 <= value <= 7.5:
            raise ValueError("E3634A OCP level must be between 0 and 7.5 A")
        self._write(f"CURR:PROT {value}")

    def get_mode(self):
        return self._query("STAT:QUES:COND?")

    def get_operation_complete(self):
        return self._query("*OPC?")

    def set(self, command, *values):
        if str(command).upper() == "CTRL-C":
            return self.device_clear()
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
    return re.sub(r"[^A-Za-z0-9]+", "_", command).strip("_").lower()


def _install_catalog_methods():
    for item in E3634A.catalog["commands"]:
        name = _method_name(item["command"])
        if not name:
            continue
        if item["access"] in {"set", "set/get"} and not hasattr(E3634A, f"set_{name}"):
            setattr(E3634A, f"set_{name}", lambda self, *values, _command=item["command"]: self.set(_command, *values))
        if item["access"] in {"get", "set/get"} and not hasattr(E3634A, f"get_{name}"):
            setattr(E3634A, f"get_{name}", lambda self, *values, _command=item["command"]: self.get(_command, *values))


_install_catalog_methods()
