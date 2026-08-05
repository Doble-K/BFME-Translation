#!/usr/bin/env python3

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from project import load_project, resolve_project_path
from validate_translation import DEFAULT_RULES, protected_tokens


def save_catalog(path, data):
    temporary_path = path.with_name(f".{path.name}.tmp")
    try:
        with temporary_path.open("w", encoding="utf-8", newline="\n") as catalog_file:
            json.dump(data, catalog_file, ensure_ascii=False, indent=2)
            catalog_file.write("\n")
        os.replace(temporary_path, path)
    except OSError:
        if temporary_path.exists():
            temporary_path.unlink()
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Approve suggested localization entries for compilation."
    )
    parser.add_argument("catalog", nargs="?", help="Path to the work catalog")
    parser.add_argument("--project", help="Project configuration JSON")
    parser.add_argument("--id", action="append", dest="entry_ids", help="Exact ID to approve")
    parser.add_argument(
        "--all-suggested",
        action="store_true",
        help="Approve every suggested entry after token validation",
    )
    parser.add_argument("--actor", default="human", help="Actor recorded in history")
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    args = parser.parse_args()

    if not args.entry_ids and not args.all_suggested:
        parser.error("indique al menos --id ID o --all-suggested")

    try:
        project = load_project(args.project) if args.project else None
        if not args.catalog and not project:
            parser.error("indique catalog o use --project")
        catalog_path = Path(args.catalog) if args.catalog else resolve_project_path(project, "catalog")
        with catalog_path.open(encoding="utf-8") as catalog_file:
            data = json.load(catalog_file)
        with args.rules.open(encoding="utf-8") as rules_file:
            rules = json.load(rules_file)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"Error: no se pudo cargar la aprobación: {error}", file=sys.stderr)
        return 1

    selected_ids = set(args.entry_ids or [])
    selected = []
    for entry in data.get("entries", []):
        if entry.get("status") != "suggested":
            continue
        if args.all_suggested or entry.get("id") in selected_ids:
            selected.append(entry)

    if args.entry_ids:
        found_ids = {entry.get("id") for entry in selected}
        missing_ids = sorted(selected_ids - found_ids)
        if missing_ids:
            print(f"Error: IDs no sugeridos o inexistentes: {', '.join(missing_ids)}", file=sys.stderr)
            return 1

    if not selected:
        print("No hay entradas suggested para aprobar.", file=sys.stderr)
        return 1

    for entry in selected:
        expected = protected_tokens(entry.get("source", ""), rules)
        actual = protected_tokens(entry.get("translation", ""), rules)
        if expected != actual:
            print(f"TOKEN ERROR: {entry.get('id')}", file=sys.stderr)
            print(f"EXPECTED: {expected}", file=sys.stderr)
            print(f"ACTUAL:   {actual}", file=sys.stderr)
            return 1

    today = datetime.now().strftime("%Y-%m-%d")
    for entry in selected:
        entry["status"] = "translated"
        entry.setdefault("translation_meta", {})
        entry["translation_meta"]["approved_by"] = args.actor
        entry["translation_meta"]["approved_date"] = today
        entry.setdefault("history", []).append({
            "date": today,
            "action": "approved",
            "from": "suggested",
            "to": "translated",
            "by": args.actor,
        })

    try:
        save_catalog(catalog_path, data)
    except OSError as error:
        print(f"Error: no se pudo guardar el catálogo: {error}", file=sys.stderr)
        return 1

    print(f"Entradas aprobadas: {len(selected)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
