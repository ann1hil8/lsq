import json
import re
import sys
from pathlib import Path


STOP_MARKER = "Status and Events"


def syntax_entries(text):
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if i > 3000 and "Commands Listed in Alphabetical Order" in line)
    end = next(i for i, line in enumerate(lines[start:], start) if line.strip() == STOP_MARKER)
    entries = []
    index = start
    while index < end:
        if not re.search(r"\bSyntax\s*:?(?:\s|$)", lines[index]):
            index += 1
            continue
        parts = []
        first = re.sub(r"^.*?\bSyntax\s*:?,?\s*", "", lines[index]).strip()
        if first:
            parts.append(first)
        index += 1
        while index < end:
            value = lines[index].strip()
            if not value:
                break
            if re.match(r"^(Related Commands|Arguments|Conditions|Examples|Group|Returns|NOTE|Description)\b", value):
                break
            if "MSO2000" in value and "Manual" in value:
                break
            parts.append(value)
            index += 1
        if parts:
            syntax = " ".join(parts)
            syntax = re.sub(r"\s+", " ", syntax).strip()
            cleaned = re.sub(r"^DPO Models:\s*", "", syntax).lstrip("-•").strip()
            command = cleaned.split()[0] if cleaned else ""
            if command and (command[0].isalpha() or command[0] == "*") and command.count("{") == command.count("}"):
                entries.append((command, syntax))
        index += 1
    unique = {}
    for command, syntax in entries:
        unique.setdefault((command, syntax), None)
    return [{"command": command, "syntax": syntax, "access": access(syntax), "description": "Defined by the Tektronix MSO2000B/DPO2000 series programmer manual."} for command, syntax in sorted(unique)]


def access(syntax):
    command_tokens = syntax.split()
    query = "?" in syntax
    set_form = bool(command_tokens and not command_tokens[0].endswith("?"))
    if query and set_form:
        return "set/get"
    if query:
        return "get"
    return "set"


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: python tools/import_mso2024b_catalog.py PATH_TO_PROGRAMMER_MANUAL.txt")
    source = Path(sys.argv[1])
    target = Path(__file__).parents[1] / "lsq" / "devices" / "catalogs" / "mso2024b.json"
    commands = syntax_entries(source.read_text(encoding="utf-8", errors="replace"))
    catalog = {"model": "Tektronix MSO2024B", "transport": "USB VISA", "source": source.name, "command_count": len(commands), "commands": commands}
    target.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(commands)} commands to {target}")


if __name__ == "__main__":
    main()
