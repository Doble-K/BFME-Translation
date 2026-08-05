#!/usr/bin/env python3

import argparse
import json
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path


def add_flag(entry, flag):
    flags = entry.setdefault("flags", [])
    if flag not in flags:
        flags.append(flag)


def reset_review(entry):
    review = entry.setdefault("review", {})
    review.setdefault("ai", {})
    review.setdefault("human", {})
    review["ai"].update({"checked": False, "last_review": None})
    review["ai"].setdefault("issues", [])
    review["human"].update({"checked": False, "user": None, "date": None})


def main():
    parser = argparse.ArgumentParser(description="Update a translation catalog from a new source catalog.")
    parser.add_argument("new_source", help="New extracted source catalog")
    parser.add_argument("catalog", help="Current work catalog")
    args = parser.parse_args()

    try:
        with open(args.new_source, encoding="utf-8") as source_file:
            new_data = json.load(source_file)
        with open(args.catalog, encoding="utf-8") as catalog_file:
            catalog_data = json.load(catalog_file)
    except (OSError, json.JSONDecodeError) as error:
        print(f"Error: no se pudo cargar el catálogo: {error}", file=sys.stderr)
        return 1

    new_entries = new_data.get("entries", [])
    catalog_entries = catalog_data.get("entries", [])
    new_ids = [entry.get("id") for entry in new_entries]
    catalog_ids = [entry.get("id") for entry in catalog_entries]
    duplicate_new_ids = {entry_id for entry_id, count in Counter(new_ids).items() if count > 1}
    duplicate_catalog_ids = {
        entry_id for entry_id, count in Counter(catalog_ids).items() if count > 1
    }
    if duplicate_new_ids or duplicate_catalog_ids:
        print("Error: no se puede actualizar un catálogo con IDs duplicados.", file=sys.stderr)
        if duplicate_new_ids:
            print(f"  En la nueva fuente: {sorted(duplicate_new_ids)}", file=sys.stderr)
        if duplicate_catalog_ids:
            print(f"  En el catálogo actual: {sorted(duplicate_catalog_ids)}", file=sys.stderr)
        return 1

    existing_entries = {entry["id"]: entry for entry in catalog_entries}
    updated_entries = []
    added_count = 0
    modified_count = 0
    today = datetime.now().strftime("%Y-%m-%d")

    for new_entry in new_entries:
        entry_id = new_entry["id"]
        new_text = new_entry["text"]

        if entry_id in existing_entries:
            entry = existing_entries[entry_id]
            entry.setdefault("flags", [])
            entry.setdefault("history", [])
            old_source = entry.get("source", "")
            old_translation = entry.get("translation", "")
            entry["line"] = new_entry.get("line", entry.get("line", 0))

            if old_source != new_text:
                entry["source"] = new_text
                entry["translation"] = ""
                entry["status"] = "pending"
                add_flag(entry, "source_updated")
                add_flag(entry, "needs_review")
                entry["translation_meta"] = {
                    "origin": None,
                    "model": None,
                    "date": None,
                    "confidence": 0.0,
                }
                reset_review(entry)
                entry["history"].append({
                    "date": today,
                    "action": "source_updated",
                    "from": old_source,
                    "to": new_text,
                    "by": "system",
                })
                if old_translation:
                    entry["history"].append({
                        "date": today,
                        "action": "translation_invalidated",
                        "from": old_translation,
                        "to": "",
                        "by": "system",
                    })
                modified_count += 1

            updated_entries.append(entry)
            continue

        updated_entries.append({
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
                "confidence": 0.0,
            },
            "review": {
                "ai": {"checked": False, "issues": [], "last_review": None},
                "human": {"checked": False, "user": None, "date": None},
            },
            "history": [{
                "date": today,
                "action": "created",
                "from": "",
                "to": "",
                "by": "system",
            }],
        })
        added_count += 1

    catalog_data["entries"] = updated_entries
    catalog_path = Path(args.catalog)
    temporary_path = catalog_path.with_name(f".{catalog_path.name}.tmp")
    try:
        with temporary_path.open("w", encoding="utf-8", newline="\n") as catalog_file:
            json.dump(catalog_data, catalog_file, ensure_ascii=False, indent=2)
            catalog_file.write("\n")
        os.replace(temporary_path, catalog_path)
    except OSError as error:
        if temporary_path.exists():
            temporary_path.unlink()
        print(f"Error: no se pudo guardar el catálogo: {error}", file=sys.stderr)
        return 1

    print("Actualización completada:")
    print(f" - Líneas nuevas agregadas: {added_count}")
    print(f" - Entradas invalidadas por cambio de fuente: {modified_count}")
    print(f" - Total de entradas en catálogo: {len(updated_entries)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
