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
    parser = argparse.ArgumentParser(description="Review suggested localization entries.")
    subparsers = parser.add_subparsers(dest="operation", required=True)

    approve_parser = subparsers.add_parser("approve", help="Approve suggestions for compilation")
    reject_parser = subparsers.add_parser("reject", help="Reject suggestions without deleting them")
    human_review_parser = subparsers.add_parser("review", help="Complete human review of translations")
    for operation_parser in (approve_parser, reject_parser, human_review_parser):
        operation_parser.add_argument("catalog", nargs="?", help="Path to the work catalog")
        operation_parser.add_argument("--project", help="Project configuration JSON")
        operation_parser.add_argument("--id", action="append", dest="entry_ids", help="Exact ID to review")
        operation_parser.add_argument(
            "--all-suggested",
            "--all-translated",
            "--all",
            dest="all_entries",
            action="store_true",
            help="Review every eligible entry",
        )
        operation_parser.add_argument("--actor", default="human", help="Actor recorded in history")
    approve_parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    human_review_parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    reject_parser.add_argument("--reason", required=True, help="Reason for rejecting the suggestions")
    args = parser.parse_args()

    if not args.entry_ids and not args.all_entries:
        parser.error("indique al menos --id ID o --all-suggested")

    try:
        project = load_project(args.project) if args.project else None
        if not args.catalog and not project:
            parser.error("indique catalog o use --project")
        catalog_path = Path(args.catalog) if args.catalog else resolve_project_path(project, "catalog")
        with catalog_path.open(encoding="utf-8") as catalog_file:
            data = json.load(catalog_file)
        rules = None
        if args.operation in {"approve", "review"}:
            with args.rules.open(encoding="utf-8") as rules_file:
                rules = json.load(rules_file)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"Error: no se pudo cargar la aprobación: {error}", file=sys.stderr)
        return 1

    selected_ids = set(args.entry_ids or [])
    selected = []
    for entry in data.get("entries", []):
        expected_status = "translated" if args.operation == "review" else "suggested"
        if entry.get("status") != expected_status:
            continue
        if args.all_entries or entry.get("id") in selected_ids:
            selected.append(entry)

    if args.entry_ids:
        found_ids = {entry.get("id") for entry in selected}
        missing_ids = sorted(selected_ids - found_ids)
        if missing_ids:
            print(f"Error: IDs no sugeridos o inexistentes: {', '.join(missing_ids)}", file=sys.stderr)
            return 1

    if not selected:
        print("No hay entradas suggested para revisar.", file=sys.stderr)
        return 1

    if args.operation in {"approve", "review"}:
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
        new_status = {
            "approve": "translated",
            "reject": "rejected",
            "review": "reviewed",
        }[args.operation]
        entry["status"] = new_status
        entry.setdefault("translation_meta", {})
        action = "approved" if args.operation == "approve" else "rejected"
        if args.operation == "review":
            action = "reviewed"
        entry["translation_meta"][f"{action}_by"] = args.actor
        entry["translation_meta"][f"{action}_date"] = today
        if args.operation == "reject":
            entry["translation_meta"]["rejection_reason"] = args.reason
            entry.setdefault("flags", [])
            if "rejected" not in entry["flags"]:
                entry["flags"].append("rejected")
        elif args.operation == "review":
            entry.setdefault("flags", [])
            entry["flags"] = [flag for flag in entry["flags"] if flag != "needs_review"]
        entry.setdefault("history", []).append({
            "date": today,
            "action": action,
            "from": "translated" if args.operation == "review" else "suggested",
            "to": new_status,
            "by": args.actor,
            **({"reason": args.reason} if args.operation == "reject" else {}),
        })

    try:
        save_catalog(catalog_path, data)
    except OSError as error:
        print(f"Error: no se pudo guardar el catálogo: {error}", file=sys.stderr)
        return 1

    print(f"Entradas {args.operation}: {len(selected)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
