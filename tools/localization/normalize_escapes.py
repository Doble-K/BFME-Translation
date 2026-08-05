#!/usr/bin/env python3

import argparse
import json
import os
from pathlib import Path


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

        if entry.get("status") != "translated" or not translation:
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
    parser.add_argument("catalog", help="Path to the localization catalog")
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

    path = Path(args.catalog)
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)

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


if __name__ == "__main__":
    main()
