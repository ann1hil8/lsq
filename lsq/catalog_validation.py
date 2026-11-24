import importlib
import json
from pathlib import Path

def validate_catalogs(device_root):
    from .devices.base import BaseDriver
    root = Path(device_root); errors = []
    docs_dir = root.parent.parent / "docs" / "devices"
    for catalog_path in sorted((root / "catalogs").glob("*.json")):
        try: catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        except Exception as exc: errors.append(f"{catalog_path.name}: invalid JSON: {exc}"); continue
        model = catalog.get("model")
        if not model: errors.append(f"{catalog_path.name}: missing model")
        commands = catalog.get("commands", [])
        if not commands and not catalog.get("command_count"): errors.append(f"{catalog_path.name}: no commands")
        module_name = catalog_path.stem
        try: module = importlib.import_module(f"lsq.devices.{module_name}")
        except Exception as exc: errors.append(f"{catalog_path.name}: driver import failed: {exc}"); continue
        classes = [value for value in vars(module).values() if isinstance(value, type) and value.__module__ == module.__name__ and issubclass(value, BaseDriver) and value is not BaseDriver]
        if not classes: errors.append(f"{catalog_path.name}: no driver class"); continue
        driver = classes[0]
        for item in commands:
            method = item.get("method") if isinstance(item, dict) else None
            if method and not hasattr(driver, method): errors.append(f"{catalog_path.name}: missing driver method {method}")
        if docs_dir.parent.is_dir():
            doc = docs_dir / f"{module_name}.md"
            if not doc.exists(): errors.append(f"{catalog_path.name}: missing generated documentation {doc.name}")
            elif commands:
                text = doc.read_text(encoding="utf-8")
                for item in commands:
                    command = item.get("command") if isinstance(item, dict) else None
                    if command and command.split(":", 1)[0].lower() not in text.lower(): errors.append(f"{catalog_path.name}: command family {command} missing from documentation")
    return errors
