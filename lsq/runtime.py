import ast
import base64
import importlib
import json
import operator
import re
import signal
import threading
import time
from pathlib import Path

from .connections.discovery import DeviceManager
from .connections.serial import parse_terminator
from .dsl import FunctionNode, IfNode, LoopNode, Program, Statement, TryNode, interpolate, parse_timeout, split_assignment
from .errors import AssertionFailure, ScriptError, TimeoutError
from .logging_utils import Logger

class BreakSignal(Exception):
    """Internal loop break control signal."""
class ContinueSignal(Exception):
    """Internal loop continue control signal."""
class ReturnSignal(Exception):
    def __init__(self, value=None): self.value = value

class ExpressionEvaluator:
    operators = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.Mod: operator.mod, ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt, ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge}
    def __init__(self, variables, functions=None): self.variables, self.functions = variables, functions or {}
    def evaluate(self, expression):
        text = re.sub(r"\$\{([A-Za-z_]\w*)\}", lambda m: repr(self.variables.get(m.group(1))), str(expression))
        try: return self._eval(ast.parse(text, mode="eval").body)
        except Exception as exc: raise ValueError(f"invalid expression {expression!r}: {exc}") from exc
    def _eval(self, node):
        if isinstance(node, ast.Constant): return node.value
        if isinstance(node, ast.Name):
            if node.id in self.variables: return self.variables[node.id]
            if node.id == "True": return True
            if node.id == "False": return False
            if node.id == "None": return None
            return node.id
        if isinstance(node, ast.List): return [self._eval(x) for x in node.elts]
        if isinstance(node, ast.Tuple): return tuple(self._eval(x) for x in node.elts)
        if isinstance(node, ast.Dict): return {self._eval(k): self._eval(v) for k, v in zip(node.keys, node.values)}
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.Not, ast.USub, ast.UAdd)):
            value = self._eval(node.operand); return (not value) if isinstance(node.op, ast.Not) else (-value if isinstance(node.op, ast.USub) else value)
        if isinstance(node, ast.BoolOp):
            values = [self._eval(x) for x in node.values]; return all(values) if isinstance(node.op, ast.And) else any(values)
        if isinstance(node, ast.BinOp) and type(node.op) in self.operators: return self.operators[type(node.op)](self._eval(node.left), self._eval(node.right))
        if isinstance(node, ast.Compare):
            left = self._eval(node.left)
            for op, right_node in zip(node.ops, node.comparators):
                right = self._eval(right_node)
                if not self.operators[type(op)](left, right): return False
                left = right
            return True
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            args = [self._eval(x) for x in node.args]; name = node.func.id
            if name == "contains" and len(args) == 2:
                return (str(args[1]) in args[0]) if isinstance(args[0], str) else (args[1] in args[0])
            if name == "matches" and len(args) == 2: return re.search(str(args[1]), str(args[0])) is not None
            if name == "number" and len(args) == 1: return float(args[0])
            if name == "get" and len(args) >= 2:
                return self.functions["get"](args[0], args[1], *args[2:])
            if name in self.functions: return self.functions[name](*args)
        raise ValueError(f"unsupported expression node: {ast.dump(node)}")

class Runtime:
    def __init__(self, statements, verbose=False, dry_run=False, state_path=None, verbosity=None, verbosity_override=False, output_dir=None, loop_limit=100000):
        self.program = statements if isinstance(statements, Program) else Program(list(statements)); self.statements = self.program.nodes
        self.variables = {"response": "", "return_value": ""}; self.devices = {}; self.drivers = {}; self.functions = {}
        self.loop_limit = loop_limit; self.verbosity_override = verbosity_override
        self.logger = Logger(verbosity or ("verbose" if verbose else "normal")); self.output_dir = Path(output_dir or ".").resolve(); self.output_dir.mkdir(parents=True, exist_ok=True); self.variables["output_dir"] = str(self.output_dir)
        self.connections = DeviceManager(self.log, dry_run, state_path); self._cleanup_done = False; self._signal_previous = {}; self._index_functions(self.statements)

    def log(self, message, level="normal"): self.logger(message, level)
    def _index_functions(self, nodes):
        for node in nodes:
            if isinstance(node, FunctionNode): self.functions[node.name] = node
            elif isinstance(node, (IfNode, LoopNode, TryNode)):
                children = node.body if isinstance(node, (LoopNode, TryNode)) else [body for _, body in node.branches]
                if isinstance(node, TryNode): children = node.body + node.catch_body + node.finally_body
                self._index_functions(children)

    def run(self):
        self._install_signals()
        try:
            self._execute(self.statements)
        except BaseException:
            self._cleanup(True)
            raise
        finally:
            self._cleanup(False)
            self._restore_signals()

    def _install_signals(self):
        if threading.current_thread() is not threading.main_thread(): return
        for sig in (signal.SIGINT, signal.SIGTERM):
            self._signal_previous[sig] = signal.getsignal(sig); signal.signal(sig, self._signal_handler)
    def _restore_signals(self):
        for sig, handler in self._signal_previous.items(): signal.signal(sig, handler)
        self._signal_previous.clear()
    def _signal_handler(self, signum, _frame):
        self._cleanup(True); raise KeyboardInterrupt(f"signal {signum}")
    def _cleanup(self, emergency):
        if self._cleanup_done: return
        self._cleanup_done = True
        for name, driver in reversed(list(self.drivers.items())):
            bound = getattr(driver, "connection", None) is not None
            if not bound: continue
            try:
                if emergency and hasattr(driver, "emergency_safe_state"): driver.emergency_safe_state()
                if hasattr(driver, "set_local_mode"): driver.set_local_mode()
                if hasattr(driver, "shutdown") and getattr(driver, "started", False): driver.shutdown(); driver.started = False
            except Exception as exc: self.log(f"CLEANUP FAIL {name}: {exc}", "verbose")
            try:
                if getattr(driver, "connection", None) is not None: driver.close()
            except Exception as exc: self.log(f"CLOSE FAIL {name}: {exc}", "verbose")
        for conn_name, connection in reversed(list(self.connections.connections.items())):
            try:
                if getattr(connection, "is_open", False): connection.close()
            except Exception as exc: self.log(f"CLOSE FAIL {conn_name}: {exc}", "verbose")

    def _execute(self, nodes):
        for node in nodes:
            if isinstance(node, Statement): self._statement(node)
            elif isinstance(node, IfNode): self._if(node)
            elif isinstance(node, LoopNode): self._loop(node)
            elif isinstance(node, TryNode): self._try(node)
            elif isinstance(node, FunctionNode): continue

    def _statement(self, statement):
        c, a = statement.command, statement.args
        try:
            if c == "connection":
                if not a: raise ValueError("connection requires a name")
                self.connections.register(a[0], self._options(a[1:])); return
            if c == "device": self._device_declare(statement); return
            if c == "discover":
                if len(a) != 1: raise ValueError("discover requires a connection name")
                self.connections.find(a[0]); return
            if c == "open":
                if len(a) != 1: raise ValueError("open requires a connection name")
                self._open(a[0]); return
            if c == "close":
                if len(a) != 1: raise ValueError("close requires a connection name")
                self._close(a[0]); return
            if c == "send": self._send(statement); return
            if c == "expect": self._expect(statement); return
            if c == "device_call": self._device_call(statement); return
            if c == "set":
                name, expression = split_assignment(a); self.variables[name] = self._eval(expression); return
            if c == "print": print(interpolate(" ".join(a), self.variables)); return
            if c == "save": self._save(statement); return
            if c == "log":
                if not self.verbosity_override: self.logger.set_level(self._options(a).get("level", "normal")); return
            if c == "sleep":
                if len(a) != 1: raise ValueError("sleep requires a duration")
                time.sleep(self._seconds(a[0])); return
            if c == "fail": raise ScriptError(interpolate(" ".join(a), self.variables), statement.line)
            if c == "call": self._call(statement); return
            if c == "return": raise ReturnSignal(self._eval(" ".join(a)) if a else None)
            if c == "break": raise BreakSignal()
            if c == "continue": raise ContinueSignal()
            if c == "assert": self._assert(statement); return
            raise ScriptError(f"unknown command: {c}", statement.line)
        except (BreakSignal, ContinueSignal, ReturnSignal, ScriptError): raise
        except Exception as exc: raise ScriptError(str(exc), statement.line) from exc

    def _eval(self, expression): return ExpressionEvaluator(self.variables, {"get": self._get}).evaluate(expression)
    def _get(self, device, method, *args):
        node = Statement("device_call", [str(device), str(method), *[str(x) for x in args]], 0); self._device_call(node); return self.variables.get("return_value")
    def _device_declare(self, statement):
        if not statement.args: raise ValueError("device requires a name")
        name = statement.args[0]; options = self._options(statement.args[1:]); driver_name = options.get("driver")
        if not driver_name: raise ValueError("device requires driver=NAME")
        cls = self._driver_class(driver_name); connection_name = options.get("connection", name); profile = dict(getattr(cls, "connection_defaults", {})); profile.update(getattr(cls, "identification", {})); profile.update({k:v for k,v in options.items() if k not in {"driver", "connection"}})
        if connection_name not in self.connections.profiles:
            self.connections.register(connection_name, profile)
        else:
            existing = self.connections.profiles[connection_name]
            for key, value in profile.items(): existing.setdefault(key, value)
        self.devices[name] = {"driver": driver_name, "connection": connection_name}; self.drivers[name] = cls(None)
    def _open(self, name):
        connection = self.connections.get(name); connection.open()
        for device, config in self.devices.items():
            if config.get("connection", device) == name:
                driver = self.drivers[device]; driver.connection = connection
                if hasattr(driver, "open"): driver.open()
                if hasattr(driver, "startup") and not getattr(driver, "started", False): driver.startup(); driver.started = True
    def _close(self, name):
        connection = self.connections.get(name)
        matched = False

        for device, config in self.devices.items():
            if config.get("connection", device) != name:
                continue

            matched = True
            driver = self.drivers.get(device)

            if driver is not None:
                if hasattr(driver, "shutdown") and getattr(driver, "started", False):
                    driver.shutdown()
                    driver.started = False

                driver.close()

        if not matched and getattr(connection, "is_open", False):
            connection.close()
    def _options(self, args):
        result = {}
        for item in args:
            if "=" in item:
                key, value = item.split("=", 1); key = key.replace("-", "_"); result[key] = value
        for key in ("read_timeout", "write_timeout", "timeout"):
            if key in result: result[key] = parse_timeout(result[key]) if isinstance(result[key], str) and re.search(r"(?:ms|s)$", result[key]) else float(result[key])
        return result
    def _seconds(self, value): return parse_timeout(value) if re.search(r"(?:ms|s)$", str(value)) else float(value)
    def _send(self, statement):
        if len(statement.args) < 2: raise ValueError("send requires CONNECTION PAYLOAD")
        connection = self.connections.get(statement.args[0]); options = self._options(statement.args[2:]); payload = interpolate(statement.args[1], self.variables).encode(); connection.open(); connection.write(payload + parse_terminator(options.get("terminate", "none")))
    def _expect(self, statement):
        if not statement.args: raise ValueError("expect requires CONNECTION")
        connection = self.connections.get(statement.args[0]); options = self._options(statement.args[1:]); count = int(options.get("count", 1))
        if count < 1: raise ValueError("expect count must be >= 1")
        connection.open(); results = []; started = time.monotonic(); timeout = options.get("timeout")
        try:
            manager = connection.timeout_context(timeout) if timeout and hasattr(connection, "timeout_context") else _NullContext()
            with manager:
                for _ in range(count):
                    data = connection.read(int(options["bytes"])) if "bytes" in options else connection.read_until(parse_terminator(options.get("ends", "lf")))
                    value = data.decode(errors="replace").rstrip("\r\n"); results.append(value)
        except TimeoutError: raise
        except Exception as exc:
            if timeout and ("timeout" in str(exc).lower() or time.monotonic() - started >= timeout): raise TimeoutError(statement.args[0], "expect", timeout, time.monotonic() - started) from exc
            raise
        self.variables["response"], self.variables["responses"] = results[-1], results
        if options.get("contains") and options["contains"] not in results[-1]: raise ValueError(f"response does not contain {options['contains']!r}")
        if options.get("regex") and not re.search(options["regex"], results[-1]): raise ValueError(f"response does not match {options['regex']!r}")
        if options.get("save"): self.variables[options["save"]] = results[-1] if count == 1 else results
    def _if(self, node):
        for expression, body in node.branches:
            if expression is None or bool(self._eval(expression)): self._execute(body); return
    def _loop(self, node):
        count = 0
        while node.kind == "repeat" and count < int(self._eval(node.expression)) or node.kind == "while" and bool(self._eval(node.expression)):
            if self.loop_limit and count >= self.loop_limit: raise ScriptError(f"loop exceeded {self.loop_limit} iterations", node.line)
            try: self._execute(node.body)
            except BreakSignal: break
            except ContinueSignal: count += 1; continue
            count += 1
    def _try(self, node):
        pending = None
        try: self._execute(node.body)
        except (BreakSignal, ContinueSignal, ReturnSignal) as exc: pending = exc
        except Exception as exc:
            if node.catch_name:
                self.variables[node.catch_name] = {"message": str(exc), "type": type(exc).__name__, "device": getattr(exc, "device", None), "command": getattr(exc, "command", None), "line": getattr(exc, "line", node.line)}
                try: self._execute(node.catch_body)
                except Exception as caught: pending = caught
            else: pending = exc
        finally:
            try: self._execute(node.finally_body)
            except Exception as exc: pending = exc
        if pending: raise pending
    def _call(self, statement):
        if len(statement.args) < 1 or statement.args[0] not in self.functions: raise ValueError(f"unknown function: {statement.args[0]}")
        fn = self.functions[statement.args[0]]; args = [self._eval(x) for x in statement.args[1:]]
        if len(args) != len(fn.parameters): raise ValueError(f"function {fn.name} expects {len(fn.parameters)} arguments, got {len(args)}")
        old = {p: self.variables.get(p, _Missing) for p in fn.parameters}; self.variables.update(dict(zip(fn.parameters, args)))
        try: self._execute(fn.body)
        except ReturnSignal as ret: self.variables["return_value"] = ret.value
        finally:
            for key, value in old.items(): self.variables.pop(key, None) if value is _Missing else self.variables.__setitem__(key, value)
    def _device_call(self, statement):
        if len(statement.args) < 2: raise ValueError("device_call requires DEVICE METHOD")
        name, method = statement.args[:2]; driver = self.drivers.get(name)
        if driver is None: raise ValueError(f"unknown device: {name}")
        kw_tokens = [x for x in statement.args[2:] if re.match(r"^[A-Za-z_][A-Za-z0-9_-]*=", x)]
        pos_tokens = [x for x in statement.args[2:] if not re.match(r"^[A-Za-z_][A-Za-z0-9_-]*=", x)]
        positional = [self._eval(x) for x in pos_tokens]; options = self._options(kw_tokens); kwargs = {k:v for k,v in options.items() if k != "save"}
        if "file" in kwargs: kwargs["file"] = str(self._output_path(kwargs["file"]))
        if "channel" in kwargs: kwargs["channel"] = int(kwargs["channel"])
        result = getattr(driver, method)(*positional, **kwargs); self.variables["return_value"] = result
        if options.get("save"): self.variables[options["save"]] = result
        if result is not None: self.variables["response"] = result
    def _assert(self, statement):
        args = statement.args
        if args and args[0].lower() == "approximately":
            if len(args) < 3: raise ValueError("assert approximately requires actual expected tolerance=VALUE")
            actual, expected = self._eval(args[1]), self._eval(args[2]); options = self._options(args[3:]); tolerance = float(options.get("tolerance", 0));
            if abs(float(actual) - float(expected)) > tolerance: raise AssertionFailure(" ".join(args), statement.line, actual, expected, tolerance)
        elif not bool(self._eval(" ".join(args))): raise AssertionFailure(" ".join(args), statement.line)
    def _output_path(self, value):
        path = Path(interpolate(value, self.variables)); return path if path.is_absolute() else self.output_dir / path
    @staticmethod
    def _json_value(value):
        if isinstance(value, bytes): return {"encoding":"base64", "data":base64.b64encode(value).decode()}
        if isinstance(value, dict): return {str(k):Runtime._json_value(v) for k,v in value.items()}
        if isinstance(value, (list, tuple)): return [Runtime._json_value(v) for v in value]
        return value
    def _save(self, statement):
        if not statement.args or statement.args[0] not in self.variables: raise ValueError("save requires a known variable")
        options = self._options(statement.args[1:]); path = self._output_path(options.get("file", statement.args[0] + ".json")); path.parent.mkdir(parents=True, exist_ok=True); format_name = options.get("format", path.suffix.lstrip(".") or "json"); value = self.variables[statement.args[0]]
        if format_name in {"json", "js"}: path.write_text(json.dumps(self._json_value(value), indent=2), encoding="utf-8")
        elif format_name in {"text", "txt"}: path.write_text(str(value), encoding="utf-8")
        elif format_name == "raw": path.write_bytes(value)
        elif format_name == "csv":
            if not isinstance(value, dict) or not {"time", "voltage"}.issubset(value): raise ValueError("CSV requires time and voltage arrays")
            path.write_text("time_s,voltage_v\n" + "\n".join(f"{x},{y}" for x, y in zip(value["time"], value["voltage"])) + "\n", encoding="utf-8")
        else: raise ValueError(f"unsupported save format: {format_name}")
        self.log(f"SAVED {statement.args[0]} -> {path}")
    def _driver_class(self, name):
        from .devices.base import BaseDriver
        module = importlib.import_module(f"lsq.devices.{name}")
        classes = [x for x in vars(module).values() if isinstance(x, type) and x.__module__ == module.__name__ and issubclass(x, BaseDriver) and x is not BaseDriver]
        if not classes: raise ValueError(f"driver module {name} defines no driver class")
        return classes[0]

class _NullContext:
    def __enter__(self): return self
    def __exit__(self, *args): return False
class _Missing:
    """Sentinel for an unbound function parameter."""
