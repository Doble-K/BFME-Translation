#!/usr/bin/env python3

import json
import sys
from pathlib import Path


def main():
    catalog_path = sys.argv[1] if len(sys.argv) > 1 else "catalogs/spanish_work.json"
    
    if not Path(catalog_path).exists():
        print(f"Error: El catálogo {catalog_path} no existe.")
        sys.exit(1)

    with open(catalog_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    entries = data.get("entries", [])
    errors = 0
    warnings = 0
    ids_seen = set()

    print(f"Validando catálogo: {catalog_path} ({len(entries)} entradas)...")

    for i, entry in enumerate(entries):
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

        if "status" not in entry:
            print(f"[Error] [{entry_id}] Falta el campo 'status'.")
            errors += 1
        elif entry["status"] not in ["pending", "translated", "reviewed"]:
            print(f"[Warning] [{entry_id}] Estado desconocido: {entry['status']}")
            warnings += 1

        # 3. Verificar metadatos de traducción si está traducido
        if entry.get("status") == "translated" and not entry.get("translation"):
            print(f"[Error] [{entry_id}] Estado 'translated' pero el texto de traducción está vacío.")
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
