#!/usr/bin/env python3

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from project import load_project, resolve_project_path


def migrate(data, today):
    changed = 0
    for entry in data.get("entries", []):
        entry_changed = False
        if "flags" not in entry:
            entry["flags"] = []
            entry_changed = True

        if "notes" not in entry:
            entry["notes"] = ""
            entry_changed = True

        if "translation_meta" not in entry:
            entry["translation_meta"] = {
                "origin": "ai" if entry.get("status") == "translated" else None,
                "model": None,
                "date": today if entry.get("status") == "translated" else None,
                "confidence": 1.0 if entry.get("status") == "translated" else 0.0,
            }
            entry_changed = True

        if "review" not in entry:
            entry["review"] = {
                "ai": {"checked": False, "issues": [], "last_review": None},
                "human": {"checked": False, "user": None, "date": None},
            }
            entry_changed = True

        if "history" not in entry:
            entry["history"] = []
            if entry.get("status") == "translated" and entry.get("translation"):
                entry["history"].append({
                    "date": today,
                    "action": "translated",
                    "from": "",
                    "to": entry["translation"],
                    "by": entry["translation_meta"]["origin"] or "ai",
                })
            entry_changed = True

        if entry_changed:
            changed += 1
    return changed


def main():
    parser = argparse.ArgumentParser(description="Migrate a localization catalog to the current schema.")
    parser.add_argument("catalog", nargs="?", help="Path to the localization catalog")
    parser.add_argument("--project", help="Project configuration JSON")
    args = parser.parse_args()

    try:
        project = load_project(args.project) if args.project else None
        if not args.catalog and not project:
            parser.error("indique catalog o use --project")
        catalog_path = Path(args.catalog) if args.catalog else resolve_project_path(project, "catalog")
        with catalog_path.open(encoding="utf-8") as catalog_file:
            data = json.load(catalog_file)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"Error: no se pudo cargar el catálogo: {error}", file=sys.stderr)
        return 1

    changed = migrate(data, datetime.now().strftime("%Y-%m-%d"))
    temporary_path = catalog_path.with_name(f".{catalog_path.name}.tmp")
    try:
        with temporary_path.open("w", encoding="utf-8", newline="\n") as catalog_file:
            json.dump(data, catalog_file, ensure_ascii=False, indent=2)
            catalog_file.write("\n")
        os.replace(temporary_path, catalog_path)
    except OSError as error:
        if temporary_path.exists():
            temporary_path.unlink()
        print(f"Error: no se pudo guardar el catálogo: {error}", file=sys.stderr)
        return 1

    print(f"Migradas exitosamente {changed} entradas al nuevo esquema completo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
