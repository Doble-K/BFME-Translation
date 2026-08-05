#!/usr/bin/env python3

import argparse
import json
import os
import sys
from pathlib import Path

from project import load_project, resolve_project_path


ESCAPES = {
    "\n": r"\n",
    "\t": r"\t",
    "\r": r"\r",
}


def normalize_data(data):
    """Replace real control characters where the source uses SAGE escapes."""
    changed = 0

    for entry in data.get("entries", []):
        source = entry.get("source", "")
        translation = entry.get("translation", "")

        if entry.get("status") not in {"translated", "preserved"} or not translation:
            continue

        normalized = translation
        for actual, escaped in ESCAPES.items():
            if escaped in source:
                normalized = normalized.replace(actual, escaped)

        if normalized != translation:
            entry["translation"] = normalized
            changed += 1

    return changed


def main():
    parser = argparse.ArgumentParser(
        description="Normalize real control characters to SAGE escape sequences."
    )
    parser.add_argument("catalog", nargs="?", help="Path to the localization catalog")
    parser.add_argument("--project", help="Project configuration JSON")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="Check for required normalization without modifying the catalog",
    )
    mode.add_argument(
        "--write",
        action="store_true",
        help="Write normalized data back to the catalog",
    )
    args = parser.parse_args()

    try:
        project = load_project(args.project) if args.project else None
        if not args.catalog and not project:
            parser.error("indique catalog o use --project")
        path = Path(args.catalog) if args.catalog else resolve_project_path(project, "catalog")
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"Error: no se pudo cargar el catálogo: {error}", file=sys.stderr)
        return 1

    changed = normalize_data(data)
    print(f"Escape sequences needing normalization: {changed}")

    if args.write and changed:
        temporary_path = path.with_name(f".{path.name}.tmp")
        with temporary_path.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary_path, path)
        print(f"Normalized catalog: {path}")

    if changed and not args.write:
        raise SystemExit(1)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
