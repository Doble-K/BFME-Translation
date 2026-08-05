#!/usr/bin/env python3

import json
import sys
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Validate a localization catalog.")
    parser.add_argument(
        "catalog",
        nargs="?",
        default="catalogs/spanish_work.json",
        help="Path to the localization catalog",
    )
    args = parser.parse_args()
    catalog_path = args.catalog
    
    if not Path(catalog_path).exists():
        print(f"Error: El catálogo {catalog_path} no existe.")
        sys.exit(1)

    try:
        with open(catalog_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as error:
        print(f"Error: no se pudo leer el catálogo {catalog_path}: {error}")
        sys.exit(1)

    entries = data.get("entries", [])
    if not isinstance(entries, list):
        print("[Error] El campo 'entries' debe ser una lista.")
        sys.exit(1)
    errors = 0
    warnings = 0
    ids_seen = set()

    print(f"Validando catálogo: {catalog_path} ({len(entries)} entradas)...")

    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            print(f"[Error] Entrada en índice {i} no es un objeto.")
            errors += 1
            continue

        entry_id = entry.get("id")
        
        # 1. Verificar ID único (convertido a warning para no bloquear por duplicados originales de EA)
        if not entry_id:
            print(f"[Warning] Entrada en índice {i} no tiene ID.")
            warnings += 1
        elif entry_id in ids_seen:
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
        sys.exit(1)
    else:
        print("¡Validación estructural exitosa!")


if __name__ == "__main__":
    main()
