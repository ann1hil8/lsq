import argparse
from pathlib import Path

from .connections.discovery import enumerate_serial_ports, enumerate_visa_resources
from .connections.state import ConnectionState
from .dsl import parse_file
from .errors import ConnectionError, ScriptError
from .runtime import Runtime

def main(argv=None):
    parser = argparse.ArgumentParser(description="LSQ laboratory instrument control and test automation")
    parser.add_argument("script", nargs="?", help="LSQ script")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--verbosity", choices=("quiet", "normal", "verbose", "trace"))
    parser.add_argument("-v", action="count", default=0, dest="verbosity_count")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--list-ports", action="store_true")
    parser.add_argument("--list-resources", action="store_true")
    parser.add_argument("--clear-state", action="store_true")
    parser.add_argument("--validate-catalog", action="store_true")
    parser.add_argument("--hardware-test")
    parser.add_argument("--state-file")
    parser.add_argument("--output-dir", default=".")
    parser.add_argument("--loop-limit", type=int, default=100000)
    args = parser.parse_args(argv)
    try:
        if args.clear_state:
            ConnectionState(args.state_file).clear(); return 0
        if args.list_ports:
            for port in enumerate_serial_ports(): print(f"{port.port}: VID={port.vid!s} PID={port.pid!s} SERIAL={port.usb_serial!s} DESCRIPTION={port.description!s}")
            return 0
        if args.list_resources:
            for resource in enumerate_visa_resources(): print(f"{resource.resource}")
            return 0
        if args.validate_catalog:
            from .catalog_validation import validate_catalogs
            errors = validate_catalogs(Path(__file__).parent / "devices")
            if errors:
                for error in errors: print(f"ERROR: {error}")
                return 1
            print("catalog validation passed"); return 0
        script = args.hardware_test or args.script
        if not script: parser.error("script is required unless an inspection option is used")
        level = args.verbosity or {1:"verbose", 2:"verbose", 3:"trace"}.get(args.verbosity_count)
        Runtime(parse_file(script), args.verbose, args.dry_run, args.state_file, level, level is not None, args.output_dir, args.loop_limit).run()
        return 0
    except (ConnectionError, OSError, ScriptError, ValueError) as exc:
        print(f"ERROR: {exc}"); return 1
