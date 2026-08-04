import json
from datetime import datetime

path = "catalogs/spanish_work.json"

with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

changed = 0

for entry in data.get("entries", []):
    # Asegurar campos básicos
    if "flags" not in entry:
        entry["flags"] = []

    if "notes" not in entry:
        entry["notes"] = ""

    # Metadatos de origen
    if "translation_meta" not in entry:
        entry["translation_meta"] = {
            "origin": "ai" if entry.get("status") == "translated" else None,
            "model": None,
            "date": datetime.now().strftime("%Y-%m-%d") if entry.get("status") == "translated" else None,
            "confidence": 1.0 if entry.get("status") == "translated" else 0.0
        }

    # Estructura de revisión
    if "review" not in entry:
        entry["review"] = {
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
        }

    # Historial de cambios
    if "history" not in entry:
        entry["history"] = []
        if entry.get("status") == "translated" and entry.get("translation"):
            entry["history"].append({
                "date": datetime.now().strftime("%Y-%m-%d"),
                "action": "translated",
                "from": "",
                "to": entry["translation"],
                "by": entry["translation_meta"]["origin"] or "ai"
            })

    changed += 1

with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"Migradas exitosamente {changed} entradas al nuevo esquema completo.")
