#!/usr/bin/env python3

import json
import argparse


def load_catalog(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_catalog(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def pending_entries(data):
    return [
        e for e in data["entries"]
        if e["status"] == "pending"
    ]


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "catalog",
        default="catalogs/spanish_work.json",
        nargs="?"
    )

    parser.add_argument(
        "--count",
        type=int,
        default=10
    )

    parser.add_argument(
        "--edit",
        action="store_true"
    )

    args = parser.parse_args()

    data = load_catalog(args.catalog)

    entries = pending_entries(data)

    print(f"Pending: {len(entries)}")

    for i, e in enumerate(entries[:args.count]):

        print("=" * 60)
        print("INDEX:", i)
        print("ID:", e["id"])
        print()
        print("EN:")
        print(e["source"])
        print()

        if args.edit:

            value = input("ES: ")

            if value.strip():

                e["translation"] = value.strip()
                e["status"] = "translated"

        else:

            print("ES:")
            print(e["translation"])

            print()


    if args.edit:
        save_catalog(args.catalog, data)
        print("Saved")


if __name__ == "__main__":
    main()
