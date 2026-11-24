import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .errors import ScriptError

@dataclass
class Statement:
    command: str
    args: list[str]
    line: int
    column: int = 1
    indent: int = 0

@dataclass
class IfNode:
    branches: list[tuple[str | None, list]]
    line: int

@dataclass
class LoopNode:
    kind: str
    expression: str
    body: list
    line: int

@dataclass
class TryNode:
    body: list
    catch_name: str | None
    catch_body: list
    finally_body: list
    line: int

@dataclass
class FunctionNode:
    name: str
    parameters: list[str]
    body: list
    line: int

@dataclass
class Program:
    nodes: list = field(default_factory=list)
    source: str | None = None

    def __iter__(self): return iter(self.nodes)
    def __len__(self): return len(self.nodes)
    def __getitem__(self, index): return self.nodes[index]

BLOCKS = {"if": "endif", "repeat": "endrepeat", "while": "endwhile", "try": "endtry", "function": "endfunction"}
TERMINATORS = set(BLOCKS.values()) | {"elseif", "else", "catch", "finally"}

def parse_timeout(value: str) -> float:
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)(ms|s)", str(value).strip().lower())
    if not match or float(match.group(1)) <= 0:
        raise ValueError(f"invalid timeout {value!r}; use a positive value ending in ms or s")
    amount, unit = match.groups()
    return float(amount) / 1000 if unit == "ms" else float(amount)

def _tokens(raw: str, line: int) -> list[str]:
    try:
        return shlex.split(raw, comments=True, posix=True)
    except ValueError as exc:
        raise ScriptError(str(exc), line) from exc

class _Parser:
    def __init__(self, lines: list[tuple[int, str]], source: str | None = None, include_stack: tuple[Path, ...] = (), included: set[Path] | None = None):
        self.lines, self.index, self.source = lines, 0, source
        self.include_stack = include_stack
        self.included = included if included is not None else set()

    def parse(self, stop: set[str] | None = None) -> tuple[list, str | None]:
        nodes, stop = [], stop or set()
        while self.index < len(self.lines):
            line, raw = self.lines[self.index]
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                self.index += 1
                continue
            tokens = _tokens(stripped, line)
            if not tokens:
                self.index += 1
                continue
            command = tokens[0].lower()
            if command in stop:
                break
            if command in TERMINATORS:
                raise ScriptError(f"unexpected {command}", line)
            statement = Statement(command, tokens[1:], line, raw.find(tokens[0]) + 1, len(raw) - len(raw.lstrip()))
            if command == "include": nodes.extend(self._include(statement))
            elif command == "connection":
                nodes.append(statement); self.index += 1
                while self.index < len(self.lines):
                    child_line, child_raw = self.lines[self.index]
                    if not child_raw.strip(): self.index += 1; continue
                    if len(child_raw) - len(child_raw.lstrip()) <= statement.indent:
                        if child_raw.strip().lower() == "end": self.index += 1
                        break
                    child_tokens = _tokens(child_raw.strip(), child_line)
                    if child_tokens and child_tokens[0].lower() == "end": self.index += 1; break
                    if child_tokens: statement.args.extend(child_tokens)
                    self.index += 1
            elif command == "if": nodes.append(self._if(statement))
            elif command in {"repeat", "while"}: nodes.append(self._loop(statement))
            elif command == "try": nodes.append(self._try(statement))
            elif command == "function": nodes.append(self._function(statement))
            else:
                self._validate_timeout(statement); nodes.append(statement); self.index += 1
        return nodes, self.source

    def _validate_timeout(self, statement):
        for arg in statement.args:
            if arg.startswith("timeout="):
                try: parse_timeout(arg.split("=", 1)[1])
                except ValueError as exc: raise ScriptError(str(exc), statement.line) from exc

    def _include(self, statement):
        if len(statement.args) != 1: raise ScriptError("include requires exactly one path", statement.line)
        if not self.source: raise ScriptError("include requires a file-backed script", statement.line)
        path = (Path(self.source).parent / statement.args[0]).resolve()
        if path in self.include_stack:
            chain = " -> ".join(str(item) for item in (*self.include_stack, path))
            raise ScriptError(f"circular include: {chain}", statement.line)
        if path in self.included:
            self.index += 1; return []
        try: text = path.read_text(encoding="utf-8")
        except OSError as exc: raise ScriptError(f"cannot include {path}: {exc}", statement.line) from exc
        self.included.add(path)
        child = _Parser(list(enumerate(text.splitlines(), 1)), str(path), (*self.include_stack, path), self.included)
        nodes, _ = child.parse(); self.index += 1; return nodes

    def _if(self, start):
        self.index += 1
        first, _ = self.parse({"elseif", "else", "endif"})
        branches = [(" ".join(start.args), first)]
        while self.index < len(self.lines):
            line, raw = self.lines[self.index]; tokens = _tokens(raw.strip(), line); command = tokens[0].lower() if tokens else ""
            if command == "elseif":
                self.index += 1; body, _ = self.parse({"elseif", "else", "endif"}); branches.append((" ".join(tokens[1:]), body))
            elif command == "else":
                self.index += 1; body, _ = self.parse({"endif"}); branches.append((None, body))
            elif command == "endif":
                self.index += 1; return IfNode(branches, start.line)
            else: break
        raise ScriptError("missing endif", start.line)

    def _loop(self, start):
        self.index += 1; body, _ = self.parse({"end" + start.command})
        if self.index >= len(self.lines): raise ScriptError(f"missing end{start.command}", start.line)
        line, raw = self.lines[self.index]; tokens = _tokens(raw.strip(), line)
        if not tokens or tokens[0].lower() != "end" + start.command: raise ScriptError(f"expected end{start.command}", line)
        self.index += 1; return LoopNode(start.command, " ".join(start.args), body, start.line)

    def _try(self, start):
        self.index += 1; body, _ = self.parse({"catch", "finally", "endtry"}); catch_name = None; catch_body = []; finally_body = []
        if self.index < len(self.lines):
            line, raw = self.lines[self.index]; tokens = _tokens(raw.strip(), line)
            if tokens and tokens[0].lower() == "catch":
                if len(tokens) != 2: raise ScriptError("catch requires a variable name", line)
                catch_name = tokens[1]; self.index += 1; catch_body, _ = self.parse({"finally", "endtry"})
            if self.index < len(self.lines):
                line, raw = self.lines[self.index]; tokens = _tokens(raw.strip(), line)
                if tokens and tokens[0].lower() == "finally": self.index += 1; finally_body, _ = self.parse({"endtry"})
        if self.index >= len(self.lines): raise ScriptError("missing endtry", start.line)
        line, raw = self.lines[self.index]; tokens = _tokens(raw.strip(), line)
        if not tokens or tokens[0].lower() != "endtry": raise ScriptError("expected endtry", line)
        self.index += 1; return TryNode(body, catch_name, catch_body, finally_body, start.line)

    def _function(self, start):
        if not start.args: raise ScriptError("function requires a name", start.line)
        self.index += 1; body, _ = self.parse({"endfunction"})
        if self.index >= len(self.lines): raise ScriptError("missing endfunction", start.line)
        line, raw = self.lines[self.index]; tokens = _tokens(raw.strip(), line)
        if not tokens or tokens[0].lower() != "endfunction": raise ScriptError("expected endfunction", line)
        self.index += 1; return FunctionNode(start.args[0], start.args[1:], body, start.line)

def parse_script(text: str) -> Program:
    parser = _Parser(list(enumerate(text.splitlines(), 1)))
    nodes, _ = parser.parse()
    return Program(nodes)

def parse_file(path: str | Path) -> Program:
    resolved = Path(path).resolve(); parser = _Parser(list(enumerate(resolved.read_text(encoding="utf-8").splitlines(), 1)), str(resolved), (resolved,), {resolved})
    nodes, _ = parser.parse(); return Program(nodes, str(resolved))

def split_assignment(args: Iterable[str]) -> tuple[str, str]:
    args = list(args)
    if "=" not in args: raise ValueError("expected '='")
    index = args.index("="); return " ".join(args[:index]), " ".join(args[index + 1:])

def interpolate(value, variables):
    return re.sub(r"\$\{([A-Za-z_]\w*)\}", lambda m: str(variables.get(m.group(1), "")), str(value))
