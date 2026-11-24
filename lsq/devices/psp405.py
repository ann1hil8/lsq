import re
import time

from .generic import GenericDevice


class PSP405(GenericDevice):
    """Driver for the GW Instek PSP-405 serial command set."""

    connection_defaults = {"type": "serial", "baud": 2400, "data_bits": 8, "parity": "none", "stop_bits": 1, "dtr": True, "read_timeout": 2, "command_delay": 0.5}
    identification = {"identify_command": "L", "identify_terminator": "cr", "identify_ends": "crlf", "identify_regex": r"^V[0-9]+\.[0-9]{2}A[0-9]+\.[0-9]{3}W[0-9]+\.[0-9]U[0-9]{2}I[0-9]+\.[0-9]{2}P[0-9]{3}F[01]{6}$"}

    def _query(self, command, terminator=b"\r\n"):
        self.connection.open()
        self.connection.flush()
        self.connection.write(command.encode("ascii") + b"\r")
        return self.connection.read_until(terminator).decode("ascii", errors="replace").rstrip("\r\n")

    def _command(self, command):
        self.connection.open()
        self.connection.flush()
        self.connection.write(command.encode("ascii") + b"\r")
        delay = float(getattr(self.connection, "config", {}).get("command_delay", 0.5))
        if delay > 0:
            time.sleep(delay)

    def get_status(self):
        return self._query("L")

    def status(self):
        raw = self.get_status()
        match = re.fullmatch(r"V(\d+\.\d{2})A(\d+\.\d{3})W(\d+\.\d)U(\d{2})I(\d+\.\d{2})P(\d{3})F([01]{6})", raw)
        if not match:
            raise ValueError(f"invalid PSP-405 status response: {raw!r}")
        voltage, current, power, voltage_limit, current_limit, power_limit, flags = match.groups()
        return {"raw": raw, "voltage": float(voltage), "current": float(current), "power": float(power), "voltage_limit": int(voltage_limit), "current_limit": float(current_limit), "power_limit": int(power_limit), "relay_on": flags[0] == "1", "overtemperature": flags[1] == "1", "fine_step": flags[2] == "1", "wheel_unlocked": flags[3] == "1", "remote": flags[4] == "1", "locked": flags[5] == "1"}

    def get_voltage(self):
        return float(self._query("V")[1:])

    def get_current(self):
        return float(self._query("A")[1:])

    def get_power(self):
        return float(self._query("W")[1:])

    def get_voltage_limit(self):
        return int(self._query("U")[1:])

    def get_current_limit(self):
        return float(self._query("I")[1:])

    def get_power_limit(self):
        return int(self._query("P")[1:])

    def get_flags(self):
        raw = self._query("F")
        if not re.fullmatch(r"F[01]{6}", raw):
            raise ValueError(f"invalid PSP-405 flag response: {raw!r}")
        flags = raw[1:]
        return {"raw": raw, "relay": flags[0], "temperature": flags[1], "step": flags[2], "wheel": flags[3], "remote": flags[4], "lock": flags[5]}

    def get_positive_offset(self):
        return int(self._query("B")[1:])

    def get_negative_offset(self):
        return int(self._query("D")[1:])

    def get_offset_status(self):
        raw = self._query("Q")
        if not re.fullmatch(r"Q[01]{6}", raw):
            raise ValueError(f"invalid PSP-405 offset response: {raw!r}")
        return {"raw": raw, "negative_enabled": raw[1] == "1", "positive_enabled": raw[2] == "1"}

    def shutdown(self):
        self.output_off()

    def set_voltage(self, value):
        value = float(value)
        if not 0 <= value <= 40.0:
            raise ValueError("PSP-405 voltage must be between 0 and 40.0 V")
        self._command(f"SV {value:05.2f}")

    def set_voltage_limit(self, value):
        value = int(float(value))
        if not 0 <= value <= 40:
            raise ValueError("PSP-405 voltage limit must be between 0 and 40 V")
        self._command(f"SU {value:02d}")

    def set_current_limit(self, value):
        value = float(value)
        if not 0 <= value <= 5.0:
            raise ValueError("PSP-405 current limit must be between 0 and 5.0 A")
        self._command(f"SI {value:04.2f}")

    def set_power_limit(self, value):
        value = int(float(value))
        if not 0 <= value <= 200:
            raise ValueError("PSP-405 power limit must be between 0 and 200 W")
        self._command(f"SP {value:03d}")

    def increase_voltage(self):
        self._command("SV+")

    def decrease_voltage(self):
        self._command("SV-")

    def increase_voltage_limit(self):
        self._command("SU+")

    def decrease_voltage_limit(self):
        self._command("SU-")

    def increase_current_limit(self):
        self._command("SI+")

    def decrease_current_limit(self):
        self._command("SI-")

    def increase_power_limit(self):
        self._command("SP+")

    def decrease_power_limit(self):
        self._command("SP-")

    def set_max_voltage_limit(self):
        self._command("SUM")

    def set_max_current_limit(self):
        self._command("SIM")

    def set_max_power_limit(self):
        self._command("SPM")

    def set_fine_step(self):
        self._command("KF")

    def set_coarse_step(self):
        self._command("KN")

    def toggle_output(self):
        self._command("KO")

    def output_on(self):
        self._command("KOE")

    def output_off(self):
        self._command("KOD")

    def save_settings(self):
        self._command("EEP")

    def increase_positive_offset(self):
        self._command("SB+")

    def decrease_positive_offset(self):
        self._command("SB-")

    def increase_negative_offset(self):
        self._command("SD+")

    def decrease_negative_offset(self):
        self._command("SD-")
