#!/usr/bin/env python3

import json
import sys
from datetime import datetime


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
            e["status"] = "preserved"
            e.setdefault("flags", [])
            if "system_preserved" not in e["flags"]:
                e["flags"].append("system_preserved")
            e["translation_meta"] = {
                "origin": "system",
                "model": None,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "confidence": 1.0,
            }
            e.setdefault("history", []).append({
                "date": datetime.now().strftime("%Y-%m-%d"),
                "action": "auto_preserved",
                "from": e.get("translation", ""),
                "to": e.get("source", ""),
                "by": "system",
            })
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
