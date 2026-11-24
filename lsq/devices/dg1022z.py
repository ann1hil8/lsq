import json
import re
from pathlib import Path

from .generic import GenericDevice


class DG1022Z(GenericDevice):
    """Rigol DG1022Z driver using the DG1000Z SCPI command tree."""

    connection_defaults = {"type": "visa", "resource_prefix": "USB", "read_timeout": 5, "read_termination": "\n", "write_termination": "\n"}
    identification = {"identify_command": "*IDN?", "identify_contains": "DG1022"}
    waveform_commands = {"sine": "SIN", "sinusoid": "SIN", "square": "SQU", "ramp": "RAMP", "pulse": "PULS", "noise": "NOIS", "dc": "DC", "user": "USER", "triangle": "TRI"}
    catalog = json.loads((Path(__file__).parent / "catalogs" / "dg1022z.json").read_text(encoding="utf-8"))

    @staticmethod
    def _bool(value):
        if isinstance(value, bool):
            return value
        if str(value).lower() in {"1", "true", "on", "yes"}:
            return True
        if str(value).lower() in {"0", "false", "off", "no"}:
            return False
        raise ValueError(f"invalid boolean value: {value}")

    @staticmethod
    def _channel(channel):
        channel = int(channel)
        if channel not in (1, 2):
            raise ValueError("DG1022Z channel must be 1 or 2")
        return channel

    def _write(self, command):
        self.connection.open()
        self.connection.write(command)

    def _read(self, command):
        self.connection.open()
        return self.connection.query(command).strip()

    @staticmethod
    def _resolve(command, channel=1):
        command = command.replace("<n>", str(DG1022Z._channel(channel)))
        command = command.replace("[", "").replace("]", "").lstrip(":")
        parts = []
        for part in command.split(":"):
            parts.append("".join(character for character in part if character.isupper() or character.isdigit() or character in "*?"))
        return ":".join(parts)

    def set(self, command, *values, channel=1):
        """Set any documented DG1000Z command."""
        command = self._resolve(command, channel)
        suffix = " " + ",".join(map(str, values)) if values else ""
        self._write(command + suffix)

    def get(self, command, *values, channel=1):
        """Get any documented DG1000Z command."""
        command = self._resolve(command, channel)
        if not command.endswith("?"):
            command += "?"
        if values:
            command += " " + ",".join(map(str, values))
        return self._read(command)

    def set_command(self, command, *values, channel=1):
        self.set(command, *values, channel=channel)

    def get_command(self, command, *values, channel=1):
        return self.get(command, *values, channel=channel)

    def identify(self):
        return self.get("*IDN?")

    def reset(self):
        self.set("*RST")

    def clear_status(self):
        self.set("*CLS")

    def get_operation_complete(self):
        return self.get("*OPC?")

    def apply(self, waveform, frequency=None, amplitude=None, offset=None, phase=None, channel=1):
        key = str(waveform).lower()
        if key not in self.waveform_commands:
            raise ValueError(f"unsupported DG1022Z waveform: {waveform}")
        values = [value for value in (frequency, amplitude, offset, phase) if value is not None]
        self.set(f":SOURce[<n>]:APPLy:{self.waveform_commands[key]}", *values, channel=channel)

    def get_apply(self, channel=1):
        return self.get(":SOURce[<n>]:APPLy?", channel=channel)

    def set_function(self, waveform, channel=1):
        key = str(waveform).lower()
        if key not in self.waveform_commands:
            raise ValueError(f"unsupported DG1022Z waveform: {waveform}")
        self.set(":SOURce[<n>]:FUNCtion", self.waveform_commands[key], channel=channel)

    def get_function(self, channel=1):
        return self.get(":SOURce[<n>]:FUNCtion?", channel=channel)

    def set_frequency(self, value, channel=1):
        self.set(":SOURce[<n>]:FREQuency", value, channel=channel)
        
    def get_frequency(self, channel=1):
        return float(re.sub(r"^CH[12]:", "", self.get(":SOURce[<n>]:FREQuency?", channel=channel)))

    def set_amplitude(self, value, channel=1):
        self.set(":SOURce[<n>]:VOLTage", value, channel=channel)

    def get_amplitude(self, channel=1):
        return float(self.get(":SOURce[<n>]:VOLTage?", channel=channel))

    def set_offset(self, value, channel=1):
        self.set(":SOURce[<n>]:VOLTage:OFFSet", value, channel=channel)

    def get_offset(self, channel=1):
        return float(self.get(":SOURce[<n>]:VOLTage:OFFSet?", channel=channel))

    def set_output(self, enabled, channel=1):
        self.set(":OUTPut[<n>]", "ON" if self._bool(enabled) else "OFF", channel=channel)

    def get_output(self, channel=1):
        return self.get(":OUTPut[<n>]?", channel=channel)

    def set_waveform(self, values, channel=1):
        values = [float(value) for value in values]
        if not values or any(value < -1 or value > 1 for value in values):
            raise ValueError("DG1022Z waveform values must be between -1 and 1")
        self.set(":SOURce[<n>]:TRACe:DATA", "VOLATILE," + ",".join(str(value) for value in values), channel=channel)

    def set_dac_waveform(self, values, channel=1):
        values = [int(value) for value in values]
        if not values or any(value < 0 or value > 16383 for value in values):
            raise ValueError("DG1022Z DAC waveform values must be between 0 and 16383")
        self.set(":SOURce[<n>]:TRACe:DATA:DAC", "VOLATILE," + ",".join(str(value) for value in values), channel=channel)

    def get_system_error(self):
        return self.get(":SYSTem:ERRor?")

    def set_burst_state(self, enabled, channel=1):
        self.set(":SOURce[<n>]:BURSt:STATe", "ON" if self._bool(enabled) else "OFF", channel=channel)

    def get_burst_state(self, channel=1):
        return self.get(":SOURce[<n>]:BURSt:STATe?", channel=channel)

    def close(self):
        if self.connection is None:
            self.opened = False
            return

        try:
            if getattr(self.connection, "is_open", False):
                self.set_system_klock_state("OFF")
        finally:
            self.connection.close()
            self.opened = False


def _method_name(command):
    name = command.replace("<n>", "channel").replace("[", "").replace("]", "")
    name = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").lower()
    return name


def _install_catalog_methods():
    for item in DG1022Z.catalog["commands"]:
        name = _method_name(item["command"])
        if not name:
            continue
        if item["access"] in {"set", "set/get"} and not hasattr(DG1022Z, f"set_{name}"):
            setattr(DG1022Z, f"set_{name}", lambda self, *values, channel=1, _command=item["command"]: self.set(_command, *values, channel=channel))
        if item["access"] in {"get", "set/get"} and not hasattr(DG1022Z, f"get_{name}"):
            setattr(DG1022Z, f"get_{name}", lambda self, *values, channel=1, _command=item["command"]: self.get(_command, *values, channel=channel))


_install_catalog_methods()
