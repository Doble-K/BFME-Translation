#!/usr/bin/env python3

import json
import sys
import argparse
from pathlib import Path

from project import load_project, resolve_project_path


def main():
    parser = argparse.ArgumentParser(description="Validate a localization catalog.")
    parser.add_argument(
        "catalog",
        nargs="?",
        help="Path to the localization catalog",
    )
    parser.add_argument("--project", help="Project configuration JSON")
    parser.add_argument(
        "--strict-duplicates",
        action="store_true",
        help="Treat duplicate non-whitespace IDs as errors",
    )
    parser.add_argument(
        "--ignore-id",
        action="append",
        default=[],
        help="Ignore an exact ID when checking duplicates; may be repeated",
    )
    args = parser.parse_args()
    try:
        project = load_project(args.project) if args.project else None
        if not args.catalog and not project:
            parser.error("indique catalog o use --project")
        catalog_path = Path(args.catalog) if args.catalog else resolve_project_path(project, "catalog")
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"Error: configuración de proyecto inválida: {error}", file=sys.stderr)
        return 1
    
    if not catalog_path.exists():
        print(f"Error: El catálogo {catalog_path} no existe.")
        return 1

    try:
        with catalog_path.open(encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as error:
        print(f"Error: no se pudo leer el catálogo {catalog_path}: {error}")
        return 1

    entries = data.get("entries", [])
    if not isinstance(entries, list):
        print("[Error] El campo 'entries' debe ser una lista.")
        return 1
    errors = 0
    warnings = 0
    ids_seen = set()
    ignored_ids = set(args.ignore_id)

    print(f"Validando catálogo: {catalog_path} ({len(entries)} entradas)...")

    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            print(f"[Error] Entrada en índice {i} no es un objeto.")
            errors += 1
            continue

        entry_id = entry.get("id")
        
        # 1. IDs vacíos o de espacios no se eliminan: se reportan como huérfanos.
        if not entry_id:
            print(f"[Warning] Entrada en índice {i} no tiene ID.")
            warnings += 1
        elif not isinstance(entry_id, str):
            print(f"[Error] ID en índice {i} debe ser texto.")
            errors += 1
        elif not entry_id.strip():
            print(f"[Warning] ID huérfano compuesto solo por espacios en índice {i}.")
            warnings += 1
        elif entry_id in ids_seen:
            if entry_id in ignored_ids:
                print(f"[Info] ID duplicado ignorado explícitamente: {entry_id}")
            elif args.strict_duplicates:
                print(f"[Error] ID duplicado encontrado: {entry_id}")
                errors += 1
            else:
                print(f"[Warning] ID duplicado encontrado: {entry_id}")
                warnings += 1
        else:
            ids_seen.add(entry_id)

        # 2. Verificar campos obligatorios
        if "source" not in entry:
            print(f"[Error] [{entry_id}] Falta el campo 'source'.")
            errors += 1
        elif not isinstance(entry["source"], str):
            print(f"[Error] [{entry_id}] El campo 'source' debe ser texto.")
            errors += 1

        if "status" not in entry:
            print(f"[Error] [{entry_id}] Falta el campo 'status'.")
            errors += 1
        elif entry["status"] not in ["pending", "translated", "reviewed"]:
            print(f"[Error] [{entry_id}] Estado desconocido: {entry['status']}")
            errors += 1

        # 3. Verificar texto de traducción en estados finalizados
        if entry.get("status") in ["translated", "reviewed"] and not entry.get("translation"):
            print(f"[Error] [{entry_id}] Estado '{entry.get('status')}' pero el texto de traducción está vacío.")
            errors += 1

    print("\n--- Resumen de Validación ---")
    print(f"Errores estructurales: {errors}")
    print(f"Advertencias: {warnings}")

    if errors > 0:
        return 1
    else:
        print("¡Validación estructural exitosa!")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
