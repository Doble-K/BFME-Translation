#!/usr/bin/env python3

import json
import sys
from datetime import datetime

def main():
    if len(sys.argv) != 3:
        print("Usage: update.py <new_source.json> <catalog.json>")
        sys.exit(1)

    new_source_file = sys.argv[1]
    catalog_file = sys.argv[2]

    # Cargar nueva fuente del juego
    with open(new_source_file, "r", encoding="utf-8") as f:
        new_data = json.load(f)

    # Cargar catálogo actual de trabajo
    with open(catalog_file, "r", encoding="utf-8") as f:
        catalog_data = json.load(f)

    # Crear un diccionario rápido de las entradas existentes por ID
    existing_entries = {entry["id"]: entry for entry in catalog_data.get("entries", [])}
    
    updated_entries = []
    added_count = 0
    modified_count = 0
    today = datetime.now().strftime("%Y-%m-%d")

    for new_entry in new_data.get("entries", []):
        entry_id = new_entry["id"]
        new_text = new_entry["text"]

        if entry_id in existing_entries:
            # La entrada ya existe, verificar si cambió el texto original (source)
            entry = existing_entries[entry_id]
            if entry["source"] != new_text:
                # El texto fuente cambió en la nueva versión del juego
                old_source = entry["source"]
                entry["source"] = new_text
                # Marcar que requiere revisión por cambio de fuente
                if "source_updated" not in entry["flags"]:
                    entry["flags"].append("source_updated")
                
                # Registrar en el historial
                entry["history"].append({
                    "date": today,
                    "action": "source_updated",
                    "from": old_source,
                    "to": new_text,
                    "by": "system"
                })
                modified_count += 1
            
            updated_entries.append(entry)
        else:
            # Es una línea completamente nueva
            new_work_entry = {
                "id": entry_id,
                "source": new_text,
                "translation": "",
                "status": "pending",
                "line": new_entry.get("line", 0),
                "flags": ["new_entry"],
                "notes": "",
                "translation_meta": {
                    "origin": None,
                    "model": None,
                    "date": None,
                    "confidence": 0.0
                },
                "review": {
                    "ai": {
                        "checked": False,
                        "issues": [],
                        "last_review": None
                    },
                    "human": {
                        "checked": False,
                        "user": None,
                        "date": None
                    }
                },
                "history": [
                    {
                        "date": today,
                        "action": "created",
                        "from": "",
                        "to": "",
                        "by": "system"
                    }
                ]
            }
            updated_entries.append(new_work_entry)
            added_count += 1

    catalog_data["entries"] = updated_entries

    with open(catalog_file, "w", encoding="utf-8") as f:
        json.dump(catalog_data, f, ensure_ascii=False, indent=2)

    print(f"Actualización completada:")
    print(f" - Líneas nuevas agregadas: {added_count}")
    print(f" - Líneas con fuente modificada: {modified_count}")
    print(f" - Total de entradas en catálogo: {len(updated_entries)}")

if __name__ == "__main__":
    main()
