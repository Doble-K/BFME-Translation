#!/usr/bin/env python3

import argparse
import json
from collections import Counter
from pathlib import Path


def entry_text(entry):
    if "text" in entry:
        return entry.get("text") or ""
    if "translation" in entry:
        return entry.get("translation") or ""
    return entry.get("source") or ""


def load_catalog(path):
    with Path(path).open(encoding="utf-8") as catalog_file:
        data = json.load(catalog_file)

    entries = data.get("entries")
    if not isinstance(entries, list):
        raise ValueError("El catálogo debe contener una lista entries")

    values = {}
    ids = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
            raise ValueError(f"Entrada inválida en índice {index}")
        entry_id = entry["id"]
        ids.append(entry_id)
        values[entry_id] = entry_text(entry)

    duplicate_ids = sorted(
        entry_id for entry_id, count in Counter(ids).items() if count > 1
    )
    return data, values, duplicate_ids


def compare(reference_path, target_path, output_path, reference_name, target_name):
    reference_data, reference, reference_duplicates = load_catalog(reference_path)
    target_data, target, target_duplicates = load_catalog(target_path)

    missing = sorted(set(reference) - set(target))
    extra = sorted(set(target) - set(reference))
    common = set(reference) & set(target)
    same = [
        {"id": entry_id, "text": reference[entry_id]}
        for entry_id in sorted(common)
        if target[entry_id] == reference[entry_id]
    ]
    empty = sorted(entry_id for entry_id in common if not target[entry_id])

    result = {
        "reference": {
            "name": reference_name,
            "path": str(reference_path),
            "entries": len(reference),
            "source": reference_data.get("source"),
            "duplicate_ids": reference_duplicates,
        },
        "target": {
            "name": target_name,
            "path": str(target_path),
            "entries": len(target),
            "source": target_data.get("source"),
            "duplicate_ids": target_duplicates,
        },
        "missing_in_target": missing,
        "same_as_reference": same,
        "empty_in_target": empty,
        "extra_in_target": extra,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as report_file:
        json.dump(result, report_file, indent=2, ensure_ascii=False)
        report_file.write("\n")
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Compare two SAGE catalogs by IDs and effective text."
    )
    parser.add_argument("reference", help="Reference catalog JSON")
    parser.add_argument("target", help="Target catalog JSON")
    parser.add_argument(
        "--output",
        default="reports/generated/comparison_report.json",
        help="Output report JSON",
    )
    parser.add_argument("--reference-name", default="reference")
    parser.add_argument("--target-name", default="target")
    args = parser.parse_args()

    try:
        result = compare(
            Path(args.reference),
            Path(args.target),
            Path(args.output),
            args.reference_name,
            args.target_name,
        )
    except (OSError, json.JSONDecodeError, ValueError) as error:
        parser.error(str(error))

    print(f"{args.reference_name}: {result['reference']['entries']}")
    print(f"{args.target_name}: {result['target']['entries']}")
    print(f"Missing in target: {len(result['missing_in_target'])}")
    print(f"Same as reference: {len(result['same_as_reference'])}")
    print(f"Empty in target: {len(result['empty_in_target'])}")
    print(f"Extra in target: {len(result['extra_in_target'])}")
    print(f"Report: {args.output}")


if __name__ == "__main__":
    main()
