import re
from dataclasses import dataclass

from ..errors import ConnectionError
from .state import ConnectionState


@dataclass
class SerialCandidate:
    port: str
    vid: int | None = None
    pid: int | None = None
    usb_serial: str | None = None
    manufacturer: str | None = None
    description: str | None = None


@dataclass
class VisaCandidate:
    resource: str
    description: str | None = None


def enumerate_serial_ports():
    try:
        from serial.tools import list_ports
    except ImportError as exc:
        raise ConnectionError("pyserial is required for serial discovery") from exc
    result = []
    for item in list_ports.comports():
        result.append(SerialCandidate(item.device, item.vid, item.pid, item.serial_number, item.manufacturer, item.description))
    return result


def enumerate_visa_resources(backend=""):
    try:
        import pyvisa
    except ImportError as exc:
        raise ConnectionError("pyvisa is required for VISA discovery") from exc
    try:
        manager = pyvisa.ResourceManager(backend or "")
        return [VisaCandidate(resource) for resource in manager.list_resources()]
    except Exception as exc:
        raise ConnectionError(f"VISA discovery failed: {exc}") from exc


class DeviceManager:
    def __init__(self, logger=None, dry_run=False, state_path=None):
        self.logger = logger or (lambda *_: None)
        self.dry_run = dry_run
        self.connections = {}
        self.profiles = {}
        self.state = ConnectionState(state_path, self.logger)

    def register(self, name, config):
        self.profiles[name] = config

    def list_ports(self):
        return enumerate_serial_ports()

    def _matches(self, profile, candidate):
        checks = (("vid", candidate.vid), ("pid", candidate.pid), ("usb_serial", candidate.usb_serial), ("manufacturer", candidate.manufacturer), ("description", candidate.description))
        for key, actual in checks:
            expected = profile.get(f"match_{key}")
            if expected is None:
                continue
            if key in ("vid", "pid"):
                try:
                    expected = int(str(expected), 0)
                except ValueError:
                    return False
                if actual != expected:
                    return False
            elif actual is None or str(expected).lower() not in str(actual).lower():
                return False
        return True

    def find(self, name):
        if name in self.connections:
            existing = self.connections[name]
            if not getattr(existing, "is_open", False):
                existing.open()
            return existing
        profile = self.profiles[name]
        transport = str(profile.get("type", "serial")).lower()
        if transport == "simulated":
            from .simulated import SimulatedConnection
            connection = SimulatedConnection(name, profile, self.logger); connection.open(); self.connections[name] = connection; self.logger(f"DISCOVER {name} -> simulated", "normal"); return connection
        if transport == "tcp":
            return self._find_tcp(name, profile)
        if str(profile.get("type", "serial")).lower() in {"visa", "gpib"}:
            try:
                return self._find_visa(name, profile)
            except ConnectionError:
                if str(profile.get("fallback_type", "")).lower() != "tcp": raise
                fallback = dict(profile)
                fallback["type"] = "tcp"
                fallback["host"] = profile.get("fallback_host", profile.get("host"))
                fallback["port"] = profile.get("fallback_port", profile.get("port", 5555))
                self.logger(f"VISA DISCOVERY FAILED {name}; EXPLICIT TCP FALLBACK", "normal")
                return self._find_tcp(name, fallback)
        from .serial import SerialConnection
        from .serial import parse_terminator
        candidates = [] if self.dry_run else enumerate_serial_ports()
        matches = [candidate for candidate in candidates if self._matches(profile, candidate)]
        if profile.get("port"):
            matches = [candidate for candidate in matches if candidate.port == profile["port"]]
        if self.dry_run and not matches:
            raise ConnectionError(f"dry-run discovery requires an explicit port for {name}")
        if not matches:
            raise ConnectionError(f"no serial port matches {name}")
        identify = profile.get("identify_command")
        if not identify and len(matches) != 1:
            ports = ", ".join(candidate.port for candidate in matches)
            raise ConnectionError(f"multiple ports match {name}: {ports}; identify_command is required")
        cached_port = self.state.get_port(name)
        if cached_port:
            cached = [candidate for candidate in matches if candidate.port == cached_port]
            if cached:
                self.logger(f"CACHE PROBE {name} -> {cached_port}", "verbose")
                connection = self._probe(name, profile, cached[0], identify, parse_terminator)
                if connection:
                    self.connections[name] = connection
                    self.logger(f"DISCOVER {name} -> {connection.port}", "normal")
                    return connection
            else:
                self.logger(f"CACHE MISS {name} -> {cached_port}", "verbose")
        identified = []
        for candidate in matches:
            if candidate.port == cached_port:
                continue
            connection = self._probe(name, profile, candidate, identify, parse_terminator)
            if connection:
                identified.append(connection)
        if len(identified) != 1:
            for connection in identified:
                connection.close()
            if not identified:
                raise ConnectionError(f"no serial port identified as {name}")
            ports = ", ".join(connection.port for connection in identified)
            raise ConnectionError(f"multiple ports identified as {name}: {ports}")
        connection = identified[0]
        self.connections[name] = connection
        self.state.save_connection(name, next(candidate for candidate in matches if candidate.port == connection.port))
        self.logger(f"DISCOVER {name} -> {connection.port}", "normal")
        return connection

    def _find_visa(self, name, profile):
        from .visa import VisaConnection
        resources = [VisaCandidate(str(profile["resource"]))] if profile.get("resource") else enumerate_visa_resources(profile.get("visa_backend", ""))
        prefix = profile.get("resource_prefix")
        if prefix:
            resources = [item for item in resources if item.resource.upper().startswith(str(prefix).upper())]
        cached_resource = self.state.get_resource(name)
        if cached_resource:
            cached = [item for item in resources if item.resource == cached_resource]
            if cached:
                self.logger(f"CACHE PROBE {name} -> {cached_resource}", "verbose")
                connection = self._probe_visa(name, profile, cached[0])
                if connection:
                    self.connections[name] = connection
                    self.logger(f"DISCOVER {name} -> {connection.resource_name}", "normal")
                    return connection
        candidates = [item for item in resources if item.resource != cached_resource]
        identified = [connection for item in candidates if (connection := self._probe_visa(name, profile, item))]
        if len(identified) != 1:
            for connection in identified:
                connection.close()
            if not identified:
                raise ConnectionError(f"no VISA resource identified as {name}")
            resources_text = ", ".join(connection.resource_name for connection in identified)
            raise ConnectionError(f"multiple VISA resources identified as {name}: {resources_text}")
        connection = identified[0]
        self.connections[name] = connection
        self.state.save_resource(name, connection.resource_name)
        self.logger(f"DISCOVER {name} -> {connection.resource_name}", "normal")
        return connection

    def _find_tcp(self, name, profile):
        from .tcp import TcpConnection
        host = profile.get("host")
        cached = None if host else self.state.get_tcp(name)
        if cached:
            host, port = cached["host"], int(cached["port"])
            self.logger(f"CACHE PROBE {name} -> {host}:{port}", "verbose")
        else:
            port = int(profile.get("port", 5555))
        resource = None
        if not host and str(profile.get("discovery", "")).lower() in {"visa", "auto"}:
            resources = enumerate_visa_resources(profile.get("visa_backend", ""))
            prefix = str(profile.get("resource_prefix", "TCPIP")).upper()
            resources = [candidate for candidate in resources if candidate.resource.upper().startswith(prefix)]
            cached = self.state.get_resource(name)
            ordered = sorted(resources, key=lambda item: item.resource != cached)
            matches = []
            for candidate in ordered:
                probe = self._probe_visa(name, profile, candidate)
                if probe:
                    matches.append((candidate, probe))
            if len(matches) != 1:
                for _, probe in matches: probe.close()
                if not matches: raise ConnectionError(f"no TCP VISA-discovered resource identified as {name}")
                raise ConnectionError("multiple TCP VISA-discovered resources identified as " + ", ".join(item.resource for item, _ in matches))
            resource, probe = matches[0]
            parts = resource.resource.split("::")
            if len(parts) < 2 or not parts[1]:
                probe.close()
                raise ConnectionError(f"cannot extract TCP host from VISA resource {resource.resource}")
            host = parts[1]
            probe.close()
            self.state.save_resource(name, resource.resource)
        if not host: raise ConnectionError(f"TCP discovery requires host or discovery=visa for {name}")
        connection = TcpConnection(name, {**profile, "port": port}, host=host, port=port, dry_run=self.dry_run, logger=self.logger)
        connection.open()
        identify = profile.get("identify_command")
        if identify:
            response = connection.query(str(identify))
            regex = profile.get("identify_regex")
            contains = profile.get("identify_contains")
            valid = bool(re.search(regex, response)) if regex else (str(contains).lower() in response.lower() if contains else True)
            if not valid:
                connection.close()
                raise ConnectionError(f"TCP endpoint {host}:{port} is not {name}: {response!r}")
            self.logger(f"IDENTIFY {name} -> {host}:{port}: {response!r}", "verbose")
            identity = self._identity(response)
        else:
            identity = None
        self.connections[name] = connection
        self.state.save_tcp(name, host, port, identity, resource.resource if resource else None)
        self.logger(f"DISCOVER {name} -> {host}:{port}", "normal")
        return connection

    @staticmethod
    def _identity(response):
        fields = [field.strip() for field in str(response).rstrip("\r\n").split(",")]
        return {"manufacturer": fields[0], "model": fields[1], "serial_number": fields[2]} if len(fields) >= 3 else {"raw": str(response).strip()}

    def _probe_visa(self, name, profile, candidate):
        from .visa import VisaConnection
        connection = VisaConnection(name, profile, candidate.resource, self.dry_run, self.logger)
        try:
            connection.open()
            response = connection.query(profile.get("identify_command", "*IDN?"))
            regex = profile.get("identify_regex")
            contains = profile.get("identify_contains")
            valid = bool(re.search(regex, response)) if regex else (str(contains).lower() in response.lower() if contains else True)
            if valid:
                self.logger(f"IDENTIFY {name} -> {candidate.resource}: {response!r}", "verbose")
                return connection
            connection.close()
        except Exception as exc:
            self.logger(f"PROBE FAIL {name} -> {candidate.resource}: {exc}", "verbose")
            connection.close()
        return None

    def _probe(self, name, profile, candidate, identify, parse_terminator):
        from .serial import SerialConnection
        connection = SerialConnection(name, profile, candidate.port, self.dry_run, self.logger)
        try:
            if identify:
                connection.open()
                connection.flush()
                preamble = profile.get("identify_preamble", ())
                if isinstance(preamble, str):
                    preamble = [preamble]
                preamble_terminator = parse_terminator(profile.get("identify_preamble_terminator", profile.get("identify_terminator", "cr")))
                for command in preamble:
                    connection.write(str(command).encode() + preamble_terminator)
                connection.write(str(identify).encode() + parse_terminator(profile.get("identify_terminator", "cr")))
                response = connection.read_until(parse_terminator(profile.get("identify_ends", "crlf"))).decode("utf-8", errors="replace").rstrip("\r\n")
                regex = profile.get("identify_regex")
                contains = profile.get("identify_contains")
                valid = bool(re.search(regex, response)) if regex else (str(contains).lower() in response.lower() if contains else True)
                if valid:
                    self.logger(f"IDENTIFY {name} -> {candidate.port}: {response!r}", "verbose")
                    return connection
                connection.close()
                return None
            connection.open()
            return connection
        except Exception as exc:
            self.logger(f"PROBE FAIL {name} -> {candidate.port}: {exc}", "verbose")
            connection.close()
            return None

    def get(self, name):
        return self.connections[name]

    def forget(self, name):
        connection = self.connections.pop(name, None)
        if connection:
            connection.close()
