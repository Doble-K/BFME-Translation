#!/usr/bin/env python3

import json
import sys
from pathlib import Path


def normalize_text(text):
    if not text:
        return ""
    # Reemplazar saltos de línea inconsistentes y limpiar espacios extremos
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.strip()


def main():
    catalog_path = sys.argv[1] if len(sys.argv) > 1 else "catalogs/spanish_work.json"

    with open(catalog_path, "r", encoding="utf-8") as f:
        data = json.load(f)

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

    with open(catalog_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Normalización completada. Entradas ajustadas: {modified}")


if __name__ == "__main__":
    main()
