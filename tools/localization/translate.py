#!/usr/bin/env python3

import argparse
import copy
import json
import sys
from datetime import datetime
from pathlib import Path

from validate_translation import DEFAULT_RULES, protected_tokens, protected_tokens_match
from project import load_project, resolve_project_path
from catalog_edit import (
    CatalogEditError,
    EntryConflictError,
    EntryReservedError,
    catalog_snapshot,
    commit_entry,
    entry_revision,
)


AUTO_ID_PREFIXES = ("LETTER:", "NUMBER:")
SYSTEM_ID_PREFIXES = ("LETTER:", "NUMBER:", "Version:")


def load_catalog(path):
    with open(path, encoding="utf-8") as catalog_file:
        return json.load(catalog_file)


def pending_entries(
    data,
    include_shadowed=False,
    include_orphans=False,
    include_empty=False,
    review=False,
    advanced=False,
):
    return [
        entry
        for entry in data.get("entries", [])
        if (
            entry.get("status") == "pending"
            or (
                review
                and entry.get("status") in {"translated", "reviewed"}
                and "needs_review" in entry.get("flags", [])
            )
        )
        and (
            include_shadowed
            or entry.get("duplicate_meta", {}).get("selected", True)
        )
        and (
            advanced
            or not (
                isinstance(entry.get("id"), str)
                and entry["id"].startswith(AUTO_ID_PREFIXES)
            )
        )
        and not (
            isinstance(entry.get("id"), str)
            and entry["id"].startswith(("Version:",))
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
    return protected_tokens_match(entry.get("source", ""), value, rules)


def record_translation(entry, value, today, review=False):
    old_translation = entry.get("translation", "")
    entry["translation"] = value
    if not review:
        entry["status"] = "translated"
    entry.setdefault("flags", [])
    if review:
        entry["flags"] = [flag for flag in entry["flags"] if flag != "needs_review"]
    elif "needs_review" not in entry["flags"]:
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
    if review:
        entry.setdefault("review", {}).setdefault("human", {})
        entry["review"]["human"].update({
            "checked": True,
            "user": "human",
            "date": today,
        })


def complete_review(entry, today):
    entry.setdefault("flags", [])
    entry["flags"] = [flag for flag in entry["flags"] if flag != "needs_review"]
    entry.setdefault("review", {}).setdefault("human", {})
    entry["review"]["human"].update({
        "checked": True,
        "user": "human",
        "date": today,
    })


def main():
    parser = argparse.ArgumentParser(description="Review or manually translate pending entries.")
    parser.add_argument("catalog", nargs="?", help="Path to the work catalog")
    parser.add_argument("--project", help="Project configuration JSON")
    parser.add_argument(
        "--language",
        help="Target language label used by the interactive prompt",
    )
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
    parser.add_argument(
        "--review",
        action="store_true",
        help="Review existing translations marked needs_review",
    )
    parser.add_argument(
        "--advanced",
        action="store_true",
        help="Include automatic IDs such as LETTER:* and NUMBER:*",
    )
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    args = parser.parse_args()

    if args.count < 1:
        parser.error("--count debe ser mayor que cero")

    try:
        project = load_project(args.project) if args.project else None
        if not args.catalog and not project:
            parser.error("indique catalog o use --project")
        catalog_path = Path(args.catalog) if args.catalog else resolve_project_path(project, "catalog")
        target_language = args.language or (project or {}).get("language", "TARGET")
        data, reservations = catalog_snapshot(catalog_path=catalog_path)
        with args.rules.open(encoding="utf-8") as rules_file:
            rules = json.load(rules_file)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"Error: no se pudo cargar el catálogo o las reglas: {error}", file=sys.stderr)
        return 1

    entries = pending_entries(
        data,
        args.include_shadowed,
        args.include_orphans,
        args.include_empty,
        args.review,
        args.advanced,
    )
    print(f"Pending: {len(entries)}")
    reserved_count = sum(
        1 for entry in entries if reservations.get(entry.get("id"))
    )
    if reserved_count:
        print(f"Reserved skipped: {reserved_count}")
    if args.advanced:
        print("AVISO: las entradas LETTER:* y NUMBER:* pueden ser hotkeys o controles automaticos.")
        print("Modificalas solo si deseas cambiar intencionalmente los controles del juego.")

    batch = [
        {
            "entry": copy.deepcopy(entry),
            "expected_revision": entry_revision(entry),
        }
        for entry in entries
        if not reservations.get(entry.get("id"))
    ][:args.count]
    index = 0
    while index < len(batch):
        item = batch[index]
        entry = item["entry"]
        print("=" * 60)
        print("INDEX:", index)
        print("ID:", entry.get("id"))
        print()
        print("EN:")
        print(entry.get("source", ""))
        print()
        protected = protected_tokens(entry.get("source", ""), rules)
        if protected:
            print(f"Variables protegidas: {protected}")
            print("Conserva estas variables exactamente; modifica solo el texto que las rodea.")
            print()

        if not args.edit:
            print(f"{target_language}:")
            print(entry.get("translation", ""))
            print()
            index += 1
            continue

        print("Comandos: :back volver, :skip saltar, :keep aceptar, :quit salir")
        while True:
            value = input(f"{target_language}: ").strip()
            if value == ":back":
                index = max(0, index - 1)
                break
            if value == ":quit":
                return 0
            if value == ":keep" and args.review:
                try:
                    updated = commit_entry(
                        entry.get("id"),
                        item["expected_revision"],
                        "review",
                        catalog_path=catalog_path,
                    )
                except (CatalogEditError, OSError, json.JSONDecodeError) as error:
                    print(f"EDIT ERROR: {error}")
                    if isinstance(error, (EntryConflictError, EntryReservedError)):
                        index += 1
                        break
                    continue
                batch[index] = {
                    "entry": updated,
                    "expected_revision": updated["entry_revision"],
                }
                print("Review accepted")
                index += 1
                break
            if value in {"", ":skip"}:
                index += 1
                break
            if not valid_translation(entry, value, rules):
                expected = protected_tokens(entry.get("source", ""), rules)
                actual = protected_tokens(value, rules)
                print(f"TOKEN ERROR: se esperaba {expected}, se recibió {actual}")
                print("Corrige los tokens protegidos o deja vacío para saltar esta entrada.")
                continue

            try:
                updated = commit_entry(
                    entry.get("id"),
                    item["expected_revision"],
                    "save",
                    catalog_path=catalog_path,
                    translation=value,
                    mark_reviewed=args.review,
                )
            except (CatalogEditError, OSError, json.JSONDecodeError) as error:
                print(f"EDIT ERROR: {error}")
                if isinstance(error, (EntryConflictError, EntryReservedError)):
                    index += 1
                    break
                continue
            batch[index] = {
                "entry": updated,
                "expected_revision": updated["entry_revision"],
            }
            print("Saved")
            index += 1
            break

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
