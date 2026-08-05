#!/usr/bin/env python3

import json
import sys
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Create a work catalog from an extracted source catalog.")
    parser.add_argument("input", help="Extracted source JSON")
    parser.add_argument("output", help="New work catalog JSON")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow replacing an existing output catalog",
    )
    args = parser.parse_args()

    source_file = args.input
    output_path = Path(args.output)
    if output_path.exists() and not args.force:
        print(
            f"Error: el catálogo de salida ya existe: {output_path}. "
            "Use --force solo si desea reemplazarlo.",
            file=sys.stderr,
        )
        return 1

    with open(source_file, encoding="utf-8") as f:
        data = json.load(f)

    result = {
        "source": data["source"],
        "language": "Spanish",
        "entries": []
    }

    for entry in data["entries"]:
        result["entries"].append({
            "id": entry["id"],
            "source": entry["text"],
            "translation": "",
            "status": "pending",
            "line": entry["line"],
            "flags": [],
            "notes": "",
            "translation_meta": {
                "origin": None,
                "model": None,
                "date": None,
                "confidence": 0.0
            },
            "review": {
                "ai": {
                    "checked": False,
                    "issues": [],
                    "last_review": None
                },
                "human": {
                    "checked": False,
                    "user": None,
                    "date": None
                }
            },
            "history": []
        })

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Created {output_path}")
    print(f"Entries: {len(result['entries'])}")


if __name__ == "__main__":
    raise SystemExit(main())
