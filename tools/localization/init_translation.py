#!/usr/bin/env python3

import json
import sys


def main():
    if len(sys.argv) != 3:
        print("Usage: init_translation.py <input.json> <output.json>")
        sys.exit(1)

    source_file = sys.argv[1]
    output_file = sys.argv[2]

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
            "line": entry["line"]
        })

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Created {output_file}")
    print(f"Entries: {len(result['entries'])}")


if __name__ == "__main__":
    main()
