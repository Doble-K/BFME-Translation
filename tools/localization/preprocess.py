#!/usr/bin/env python3

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from project import load_project, resolve_project_path


AUTO_IDS = (
    "LETTER:",
    "NUMBER:",
)


def preserve_system_entries(data, today):
    changed = 0
    for entry in data.get("entries", []):
        if not isinstance(entry.get("id"), str) or not entry["id"].startswith(AUTO_IDS):
            continue

        old_translation = entry.get("translation", "")
        entry_changed = (
            entry.get("translation") != entry.get("source", "")
            or entry.get("status") != "preserved"
            or "system_preserved" not in entry.get("flags", [])
        )
        entry["translation"] = entry.get("source", "")
        entry["status"] = "preserved"
        entry.setdefault("flags", [])
        if "system_preserved" not in entry["flags"]:
            entry["flags"].append("system_preserved")
        entry["translation_meta"] = {
            "origin": "system",
            "model": None,
            "date": today,
            "confidence": 1.0,
        }
        if entry_changed:
            entry.setdefault("history", []).append({
                "date": today,
                "action": "auto_preserved",
                "from": old_translation,
                "to": entry["source"],
                "by": "system",
            })
            changed += 1
    return changed


def main():
    parser = argparse.ArgumentParser(
        description="Preserve system entries without treating them as translations."
    )
    parser.add_argument("catalog", nargs="?", help="Path to the localization catalog")
    parser.add_argument("--project", help="Project configuration JSON")
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write the preserved entries to the catalog",
    )
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

    changed = preserve_system_entries(data, datetime.now().strftime("%Y-%m-%d"))
    print(f"Entradas del sistema que requieren preservación: {changed}")
    if not args.write or not changed:
        return 1 if changed else 0

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

    print(f"Catálogo actualizado: {catalog_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
