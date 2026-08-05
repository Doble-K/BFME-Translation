#!/usr/bin/env python3

import argparse
import copy
import json
import os
import sys
from collections import Counter, defaultdict
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
    new_id_counts = Counter(new_ids)
    existing_entries = defaultdict(list)
    for entry in catalog_entries:
        existing_entries[entry.get("id")].append(entry)
    retired_entries = catalog_data.get("retired_entries", [])
    retired_by_id = defaultdict(list)
    for entry in retired_entries:
        retired_by_id[entry.get("id")].append(entry)
    new_id_set = set(new_ids)
    today = datetime.now().strftime("%Y-%m-%d")

    active_entries_to_retire = [
        entry for entry in catalog_entries if entry.get("id") not in new_id_set
    ]
    for entry in active_entries_to_retire:
        retired_entry = copy.deepcopy(entry)
        add_flag(retired_entry, "source_removed")
        retired_entry["retired_meta"] = {
            "date": today,
            "reason": "source_removed",
            "active": False,
        }
        retired_entry.setdefault("history", []).append({
            "date": today,
            "action": "source_removed",
            "from": entry.get("source", ""),
            "to": "",
            "by": "system",
        })
        retired_entries.append(retired_entry)

    updated_entries = []
    added_count = 0
    modified_count = 0
    restored_count = 0
    restored_ids = set()

    occurrences = defaultdict(int)
    for new_entry in new_entries:
        entry_id = new_entry["id"]
        new_text = new_entry["text"]
        occurrences[entry_id] += 1
        occurrence = occurrences[entry_id]
        duplicate = (
            isinstance(entry_id, str)
            and bool(entry_id.strip())
            and new_id_counts[entry_id] > 1
        )
        selected = not duplicate or occurrence == new_id_counts[entry_id]
        previous_entries = existing_entries.get(entry_id, [])
        if not isinstance(entry_id, str) or not entry_id.strip():
            previous = (
                previous_entries[occurrence - 1]
                if occurrence <= len(previous_entries)
                else None
            )
        else:
            previous = previous_entries[-1] if previous_entries else None
        restored = False
        if previous is None and retired_by_id.get(entry_id):
            previous = retired_by_id[entry_id][-1]
            restored = True

        if previous is not None:
            entry = copy.deepcopy(previous)
            entry.setdefault("flags", [])
            entry.setdefault("history", [])
            old_source = entry.get("source", "")
            old_translation = entry.get("translation", "")
            entry["id"] = entry_id
            entry["line"] = new_entry.get("line", entry.get("line", 0))

            if restored:
                entry.setdefault("flags", [])
                entry["flags"] = [
                    flag for flag in entry["flags"] if flag != "source_removed"
                ]
                add_flag(entry, "source_restored")
                entry.pop("retired_meta", None)
                entry.setdefault("history", []).append({
                    "date": today,
                    "action": "source_restored",
                    "from": "",
                    "to": entry.get("source", ""),
                    "by": "system",
                })
                restored_count += 1
                restored_ids.add(entry_id)

            if duplicate:
                entry["duplicate_meta"] = {
                    "policy": "last",
                    "occurrence": occurrence,
                    "total": new_id_counts[entry_id],
                    "selected": selected,
                }
                add_flag(entry, "duplicate_id")
                if not selected:
                    entry["translation"] = ""
                    entry["status"] = "pending"
                    add_flag(entry, "duplicate_shadowed")
            elif isinstance(entry_id, str) and not entry_id.strip():
                entry["orphan_meta"] = {
                    "occurrence": occurrence,
                    "total": new_id_counts[entry_id],
                }
                add_flag(entry, "orphan_id")

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

        entry = {
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
        }
        if duplicate:
            entry["duplicate_meta"] = {
                "policy": "last",
                "occurrence": occurrence,
                "total": new_id_counts[entry_id],
                "selected": selected,
            }
            entry["flags"].append("duplicate_id")
            if not selected:
                entry["flags"].append("duplicate_shadowed")
        elif isinstance(entry_id, str) and not entry_id.strip():
            entry["orphan_meta"] = {
                "occurrence": occurrence,
                "total": new_id_counts[entry_id],
            }
            entry["flags"].append("orphan_id")
        updated_entries.append(entry)
        added_count += 1

    catalog_data["entries"] = updated_entries
    catalog_data["retired_entries"] = [
        entry for entry in retired_entries if entry.get("id") not in restored_ids
    ]
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
    print(f" - Entradas retiradas conservadas: {len(active_entries_to_retire)}")
    print(f" - Entradas retiradas restauradas: {restored_count}")
    print(f" - Total de entradas en catálogo: {len(updated_entries)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
