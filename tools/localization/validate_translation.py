#!/usr/bin/env python3

import json
import re


def tokens(text):
    return sorted(re.findall(r"%\w", text))


data=json.load(open("catalogs/spanish_work.json"))

errors=0

for e in data["entries"]:

    if e["status"] != "translated":
        continue

    src=tokens(e["source"])
    dst=tokens(e["translation"])

    if src != dst:
        print("TOKEN ERROR")
        print(e["id"])
        print("EN:", e["source"])
        print("ES:", e["translation"])
        print()
        errors += 1


print("Errors:", errors)
