#!/usr/bin/env python3

import json
import re
import argparse


def tokens(text):
    return sorted(re.findall(r"%\w", text))


parser = argparse.ArgumentParser(description="Validate protected translation tokens.")
parser.add_argument(
    "catalog",
    nargs="?",
    default="catalogs/spanish_work.json",
    help="Path to the localization catalog",
)
args = parser.parse_args()

with open(args.catalog, encoding="utf-8") as catalog_file:
    data = json.load(catalog_file)

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

if errors:
    raise SystemExit(1)
