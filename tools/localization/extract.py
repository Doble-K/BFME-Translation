#!/usr/bin/env python3

import json
import sys
from pathlib import Path


def extract_str(path):
    entries = []

    current_id = None
    current_text = None
    start_line = None

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line_number, line in enumerate(f, 1):
            line = line.rstrip("\n")

            if not line or line.startswith("//"):
                continue

            if current_id is None:
                if not line.startswith('"'):
                    current_id = line
                    start_line = line_number
            else:
                if line.startswith('"'):
                    current_text = line[1:-1]

                elif line == "END":
                    entries.append({
                        "id": current_id,
                        "text": current_text or "",
                        "line": start_line
                    })

                    current_id = None
                    current_text = None
                    start_line = None

    return entries


def main():
    if len(sys.argv) != 3:
        print("usage: extract.py input.str output.json")
        sys.exit(1)

    source = Path(sys.argv[1])
    output = Path(sys.argv[2])

    entries = extract_str(source)

    output.parent.mkdir(parents=True, exist_ok=True)

    with open(output, "w", encoding="utf-8") as f:
        json.dump(
            {
                "source": str(source),
                "entries": entries
            },
            f,
            indent=2,
            ensure_ascii=False
        )

    print(f"Extracted {len(entries)} entries")
    print(f"Written: {output}")


if __name__ == "__main__":
    main()
