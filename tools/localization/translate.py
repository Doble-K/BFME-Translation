#!/usr/bin/env python3

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from validate_translation import DEFAULT_RULES, protected_tokens
from project import load_project, resolve_project_path


AUTO_ID_PREFIXES = ("LETTER:", "NUMBER:")


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
        data = load_catalog(catalog_path)
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
    if args.advanced:
        print("AVISO: las entradas LETTER:* y NUMBER:* pueden ser hotkeys o controles automaticos.")
        print("Modificalas solo si deseas cambiar intencionalmente los controles del juego.")

    batch = entries[:args.count]
    index = 0
    while index < len(batch):
        entry = batch[index]
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

        print("Comandos: :back volver, :skip saltar, :quit salir")
        while True:
            value = input(f"{target_language}: ").strip()
            if value == ":back":
                index = max(0, index - 1)
                break
            if value == ":quit":
                return 0
            if value in {"", ":skip"}:
                index += 1
                break
            if not valid_translation(entry, value, rules):
                expected = protected_tokens(entry.get("source", ""), rules)
                actual = protected_tokens(value, rules)
                print(f"TOKEN ERROR: se esperaba {expected}, se recibió {actual}")
                print("Corrige los tokens protegidos o deja vacío para saltar esta entrada.")
                continue

            record_translation(entry, value, datetime.now().strftime("%Y-%m-%d"))
            save_catalog(catalog_path, data)
            print("Saved")
            index += 1
            break

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
