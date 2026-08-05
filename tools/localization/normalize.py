#!/usr/bin/env python3

import json
import sys
import argparse
from pathlib import Path

from project import load_project, resolve_project_path


def normalize_text(text):
    if not text:
        return ""
    # Reemplazar saltos de línea inconsistentes y limpiar espacios extremos
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.strip()


def main():
    parser = argparse.ArgumentParser(description="Normalize catalog source and translation text.")
    parser.add_argument("catalog", nargs="?", help="Path to the localization catalog")
    parser.add_argument("--project", help="Project configuration JSON")
    args = parser.parse_args()

    try:
        project = load_project(args.project) if args.project else None
        if not args.catalog and not project:
            parser.error("indique catalog o use --project")
        catalog_path = Path(args.catalog) if args.catalog else resolve_project_path(project, "catalog")
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"Error: configuración de proyecto inválida: {error}", file=sys.stderr)
        return 1

    try:
        with catalog_path.open(encoding="utf-8") as catalog_file:
            data = json.load(catalog_file)
    except (OSError, json.JSONDecodeError) as error:
        print(f"Error: no se pudo leer el catálogo: {error}", file=sys.stderr)
        return 1

    modified = 0
    for entry in data.get("entries", []):
        old_source = entry.get("source", "")
        new_source = normalize_text(old_source)
        
        if old_source != new_source:
            entry["source"] = new_source
            modified += 1

        if "translation" in entry and entry["translation"]:
            old_trans = entry["translation"]
            new_trans = normalize_text(old_trans)
            if old_trans != new_trans:
                entry["translation"] = new_trans
                modified += 1

    try:
        with catalog_path.open("w", encoding="utf-8") as catalog_file:
            json.dump(data, catalog_file, ensure_ascii=False, indent=2)
            catalog_file.write("\n")
    except OSError as error:
        print(f"Error: no se pudo guardar el catálogo: {error}", file=sys.stderr)
        return 1

    print(f"Normalización completada. Entradas ajustadas: {modified}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
