#!/usr/bin/env python3

import argparse
import json
import re
import sys
from pathlib import Path

from project import load_project, resolve_project_path


DEFAULT_RULES = Path(__file__).resolve().parents[2] / "rules" / "protected_tokens.json"


def protected_tokens(text, rules):
    """Return protected literals and regex matches in their source order."""
    matches = []

    for literal in (
        rules.get("format_specifiers", [])
        + rules.get("control_characters", [])
        + rules.get("sage_tags", [])
    ):
        for match in re.finditer(re.escape(literal), text):
            matches.append((match.start(), match.group()))

    for pattern in rules.get("regex_patterns", []):
        try:
            compiled = re.compile(pattern)
        except re.error as error:
            raise ValueError(f"Patrón protegido inválido {pattern!r}: {error}") from error
        for match in compiled.finditer(text):
            matches.append((match.start(), match.group()))

    return [token for _, token in sorted(matches)]


def main():
    parser = argparse.ArgumentParser(description="Validate protected translation tokens.")
    parser.add_argument(
        "catalog",
        nargs="?",
        help="Path to the localization catalog",
    )
    parser.add_argument("--project", help="Project configuration JSON")
    parser.add_argument(
        "--rules",
        type=Path,
        default=DEFAULT_RULES,
        help="Path to protected token rules",
    )
    args = parser.parse_args()

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
        print(f"Error: no se pudo cargar la validación: {error}", file=sys.stderr)
        return 1

    errors = 0
    for index, entry in enumerate(data.get("entries", [])):
        if entry.get("status") not in {"translated", "reviewed", "preserved"}:
            continue

        source = entry.get("source")
        translation = entry.get("translation")
        entry_id = entry.get("id", f"<índice {index}>")
        if not isinstance(source, str) or not isinstance(translation, str):
            print(f"ERROR {entry_id}: source y translation deben ser texto")
            errors += 1
            continue
        if not translation:
            print(f"ERROR {entry_id}: la traducción está vacía")
            errors += 1
            continue

        expected = protected_tokens(source, rules)
        actual = protected_tokens(translation, rules)
        if expected != actual:
            print(f"TOKEN ERROR: {entry_id}")
            print(f"SOURCE: {source}")
            print(f"TRANSLATION: {translation}")
            print(f"EXPECTED: {expected}")
            print(f"ACTUAL:   {actual}")
            print()
            errors += 1

    print(f"Errors: {errors}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
