import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG_DIR = ROOT / "lsq" / "devices" / "catalogs"
OUTPUT_DIR = ROOT / "docs" / "devices"


def render(catalog_path):
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    stem = catalog_path.stem.lower()
    model = catalog.get("model") or catalog.get("device") or catalog_path.stem
    transport = catalog.get("transport", "Driver-defined")
    is_psp = stem == "psp405"
    default_errors = "No SCPI error queue; verify state with status() or get_flags()" if is_psp else ("Instrument reports event status through EVENT? / EVMsg?" if stem == "mso2024b" else "Instrument reports SCPI errors through SYST:ERR?")
    lines = [f"# {model} API", "", f"Transport: {transport}", f"Source: {catalog.get('source', 'driver catalog')}", "", "| Command | Access | Parameters | Range / values | Errors | Description |", "|---|---|---|---|---|---|"]
    for item in catalog["commands"]:
        command = item["command"].replace("|", "\\|")
        access = item.get("access", "set/get").replace("query", "get")
        parameters = (item.get("parameters") or _parameters(stem, command)).replace("|", "\\|")
        limits = (item.get("limits") or item.get("range") or _limits(stem, command)).replace("|", "\\|")
        errors = item.get("errors", default_errors).replace("|", "\\|")
        description = item.get("description", "").replace("query", "get").replace("Query", "Get").replace("|", "\\|")
        lines.append(f"| `{command}` | {access} | {parameters} | {limits} | {errors} | {description} |")
    if is_psp:
        lines += ["", "## Driver interface", "", "Settings use `set_*` or action methods (such as `output_on()` / `output_off()`). Queries use `get_*` and `status()` methods.", "", "## Error handling", "", "PSP-405 control commands do not return an acknowledgement or maintain a SCPI error queue. Read back settings or flags with `status()` or `get_*` methods when verification is required.", ""]
    else:
        error_method = "get_system_error()" if stem == "dg1022z" else "get_error()"
        lines += ["", "## Driver interface", "", "Settings use `set_*` methods. Queries use `get_*` methods. The driver also exposes `set(command, ...)` and `get(command)` for every catalog entry.", "", "## Error handling", "", f"A successful write does not guarantee that the instrument accepted the value. Use `{error_method}` after a write when the procedure requires explicit instrument error verification.", ""]
    return "\n".join(lines)


def _parameters(stem, command):
    upper = command.upper()
    if stem == "dg1022z":
        if command.endswith("?"):
            return "Optional MINimum/MAXimum or name where specified"
        if upper.startswith("APPL"):
            return "frequency, amplitude, offset"
        if upper == "DATA":
            return "VOLATILE, values from -1 to 1"
        if upper == "DATA:DAC":
            return "VOLATILE, integer values"
        if upper.startswith("DATA:COPY"):
            return "destination name[,VOLATILE]"
        if upper.startswith("DATA:RENAME"):
            return "old name, new name"
        if upper.startswith("VOLT") or upper.startswith("FREQ") or upper.startswith("PULS"):
            return "value|MINimum|MAXimum"
    if command.endswith("?"):
        return "None or command-specific query argument"
    if upper.startswith("OUTP") or upper.endswith(":STAT") or upper.startswith("SYST:BEEP"):
        return "ON|OFF or instrument-defined value"
    return "value; see command syntax in the programming guide"


def _limits(stem, command):
    upper = command.upper()
    if stem == "dg1022z":
        if upper == "DATA":
            return "Each value -1 to 1; waveform length instrument-defined"
        if upper == "DATA:DAC":
            return "Each value 0 to 16383; waveform length instrument-defined"
        if upper.startswith("DATA:ATTR"):
            return "0 to 524288 points"
        if upper.startswith("FREQ"):
            return "1 uHz to 20 MHz, function-dependent"
        if upper.startswith("VOLT"):
            return "MINimum/MAXimum are function- and amplitude-dependent"
        if upper.startswith("MEM"):
            return "STATE1 to STATE10; location 0 is power-down state"
    return "Instrument-defined; see programming guide"


def main():
    selected = set(sys.argv[1:])
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for catalog_path in sorted(CATALOG_DIR.glob("*.json")):
        if selected and catalog_path.stem not in selected:
            continue
        (OUTPUT_DIR / f"{catalog_path.stem}.md").write_text(render(catalog_path), encoding="utf-8")


if __name__ == "__main__":
    main()
