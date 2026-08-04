#!/usr/bin/env python3

import json
import sys


AUTO_IDS = (
    "LETTER:",
    "NUMBER:",
)


def main():

    path = sys.argv[1]

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    changed = 0

    for e in data["entries"]:

        if e["id"].startswith(AUTO_IDS):

            e["translation"] = e["source"]
            e["status"] = "reviewed"
            changed += 1

    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )

    print(f"Updated: {changed}")


if __name__ == "__main__":
    main()
