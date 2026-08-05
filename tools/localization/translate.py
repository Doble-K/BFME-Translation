#!/usr/bin/env python3

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from validate_translation import DEFAULT_RULES, protected_tokens


def load_catalog(path):
    with open(path, encoding="utf-8") as catalog_file:
        return json.load(catalog_file)


def save_catalog(path, data):
    catalog_path = Path(path)
    temporary_path = catalog_path.with_name(f".{catalog_path.name}.tmp")
    try:
        with temporary_path.open("w", encoding="utf-8", newline="\n") as catalog_file:
            json.dump(data, catalog_file, ensure_ascii=False, indent=2)
            catalog_file.write("\n")
        os.replace(temporary_path, catalog_path)
    except OSError:
        if temporary_path.exists():
            temporary_path.unlink()
        raise


def pending_entries(data, include_shadowed=False, include_orphans=False, include_empty=False):
    return [
        entry
        for entry in data.get("entries", [])
        if entry.get("status") == "pending"
        and (
            include_shadowed
            or entry.get("duplicate_meta", {}).get("selected", True)
        )
        and (
            include_orphans
            or (
                "orphan_meta" not in entry
                and isinstance(entry.get("id"), str)
                and bool(entry["id"].strip())
            )
        )
        and (include_empty or bool(entry.get("source", "")))
    ]


def valid_translation(entry, value, rules):
    return protected_tokens(entry.get("source", ""), rules) == protected_tokens(value, rules)


def record_translation(entry, value, today):
    old_translation = entry.get("translation", "")
    entry["translation"] = value
    entry["status"] = "translated"
    entry.setdefault("flags", [])
    if "needs_review" not in entry["flags"]:
        entry["flags"].append("needs_review")
    entry["translation_meta"] = {
        "origin": "human",
        "model": None,
        "date": today,
        "confidence": 1.0,
    }
    entry.setdefault("history", []).append({
        "date": today,
        "action": "translated" if not old_translation else "edited",
        "from": old_translation,
        "to": value,
        "by": "human",
    })


def main():
    parser = argparse.ArgumentParser(description="Review or manually translate pending entries.")
    parser.add_argument("catalog", nargs="?", default="catalogs/spanish_work.json")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--edit", action="store_true")
    parser.add_argument(
        "--include-shadowed",
        action="store_true",
        help="Include duplicate entries hidden by the last-wins policy",
    )
    parser.add_argument(
        "--include-orphans",
        action="store_true",
        help="Include entries with whitespace-only IDs",
    )
    parser.add_argument(
        "--include-empty",
        action="store_true",
        help="Include entries with an empty source string",
    )
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    args = parser.parse_args()

    if args.count < 1:
        parser.error("--count debe ser mayor que cero")

    try:
        data = load_catalog(args.catalog)
        with args.rules.open(encoding="utf-8") as rules_file:
            rules = json.load(rules_file)
    except (OSError, json.JSONDecodeError) as error:
        print(f"Error: no se pudo cargar el catálogo o las reglas: {error}", file=sys.stderr)
        return 1

    entries = pending_entries(
        data,
        args.include_shadowed,
        args.include_orphans,
        args.include_empty,
    )
    print(f"Pending: {len(entries)}")

    for index, entry in enumerate(entries[:args.count]):
        print("=" * 60)
        print("INDEX:", index)
        print("ID:", entry.get("id"))
        print()
        print("EN:")
        print(entry.get("source", ""))
        print()

        if not args.edit:
            print("ES:")
            print(entry.get("translation", ""))
            print()
            continue

        value = input("ES: ").strip()
        if not value:
            continue
        if not valid_translation(entry, value, rules):
            expected = protected_tokens(entry.get("source", ""), rules)
            actual = protected_tokens(value, rules)
            print(f"TOKEN ERROR: se esperaba {expected}, se recibió {actual}")
            continue

        record_translation(entry, value, datetime.now().strftime("%Y-%m-%d"))
        save_catalog(args.catalog, data)
        print("Saved")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
